"""Main control logic for Bella Fruita apple sorting machine feeder."""

import argparse
import os
from config import AppConfig
from src.modbus import create_modbus_client, Procon, MODBUS_MAP, get_all_labels
from src.logging_system import LogManager
from src.tui import run_tui
from src.rule_engine import RuleEngine
from src.polling_thread import PollingThread, SystemState


class ConveyorController:
    """Controller for apple sorting conveyor system."""

    def __init__(self, config: AppConfig):
        """Initialize conveyor controller.

        Args:
            config: Application configuration
        """
        self.config = config
        self.input_client = create_modbus_client(
            config.modbus.input_ip,
            mock=config.use_mock,
            timeout=config.modbus.timeout,
            retries=config.modbus.retries
        )
        self.output_client = create_modbus_client(
            config.modbus.output_ip,
            mock=config.use_mock,
            timeout=config.modbus.timeout,
            retries=config.modbus.retries
        )
        # Check for debug mode from environment variable
        debug_mode = os.environ.get('DEBUG', '0') == '1'
        self.log_manager = LogManager(
            max_entries=config.system.log_stack_size,
            debug_mode=debug_mode
        )
        self.procon = Procon(
            self.input_client,
            self.output_client,
            config.modbus.input_slave_id,
            config.modbus.output_slave_id,
            self.log_manager
        )
        self.comms_dead = False

    def connect(self) -> bool:
        """Connect to both Modbus terminals.

        Returns:
            bool: True if both connections successful
        """
        input_ok = self.input_client.connect()
        output_ok = self.output_client.connect()

        if not input_ok:
            self.log_manager.error("Cannot connect to input terminal")
        if not output_ok:
            self.log_manager.error("Cannot connect to output terminal")

        if input_ok and output_ok:
            self.log_manager.debug("Connected to both terminals")

        return input_ok and output_ok

    def close(self):
        """Close both Modbus connections."""
        self.input_client.close()
        self.output_client.close()

    def read_and_log_all_inputs(self) -> dict:
        """Read all inputs (coils + registers) and log them.

        Returns:
            dict: Dictionary of all input states with labels
        """
        # Use Procon API to read all input coils and registers - works for both mock and real
        input_data = {}
        input_data.update(self.procon.get_all('input', 'coils'))
        input_data.update(self.procon.get_all('input', 'registers'))

        # Log the data
        self.log_manager.log_input(input_data)
        return input_data

    def read_and_log_all_outputs(self) -> dict:
        """Read all outputs (coils + registers) and log them.

        Returns:
            dict: Dictionary of all output states
        """
        # Use Procon API to read all output coils and registers
        output_data = {}
        output_data.update(self.procon.get_all('output', 'coils'))
        output_data.update(self.procon.get_all('output', 'registers'))

        # Log the data
        self.log_manager.log_output(output_data)
        return output_data

    def check_and_handle_comms_failure(self) -> bool:
        """Check comms health and stop motors if dead.

        Returns:
            bool: True if comms healthy, False if dead
        """
        comms_healthy = self.log_manager.check_comms_health(
            timeout_seconds=self.config.system.comms_timeout
        )

        if not comms_healthy and not self.comms_dead:
            # Comms just died - emergency stop all motors
            self.log_manager.critical("Communications failed! Stopping all motors...")
            self.emergency_stop_all_motors()
            self.comms_dead = True
        elif comms_healthy and self.comms_dead:
            # Comms recovered
            self.log_manager.info("Communications restored")
            self.comms_dead = False

        return comms_healthy

    def emergency_stop_all_motors(self) -> None:
        """Emergency stop - write False to all output coils."""
        try:
            # Stop all motors using Procon API
            for motor in ['MOTOR_2', 'MOTOR_3']:
                self.procon.set('output', motor, False)
            self.log_manager.info("All motors stopped")
        except Exception as e:
            self.log_manager.error(f"Error stopping motors: {e}")

    def retry_connection(self) -> bool:
        """Attempt to reconnect to Modbus terminals.

        Returns:
            bool: True if reconnection successful
        """
        self.log_manager.debug("Attempting to reconnect...")

        # Close existing connections
        try:
            self.input_client.close()
            self.output_client.close()
        except Exception as e:
            self.log_manager.error(f"Error closing connections: {e}")

        # Try to reconnect
        input_ok = self.input_client.connect()
        output_ok = self.output_client.connect()

        if input_ok and output_ok:
            self.log_manager.debug("Reconnection successful")
            self.comms_dead = False
            return True
        else:
            if not input_ok:
                self.log_manager.error("Input terminal connection failed")
            if not output_ok:
                self.log_manager.error("Output terminal connection failed")
            return False




# ============================================================================
# Main execution
# ============================================================================

def main():
    """Main entry point."""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Bella Fruita - Apple Sorting Machine Control System'
    )
    parser.add_argument(
        '--mock',
        action='store_true',
        help='Run in mock mode (testing without hardware)'
    )
    parser.add_argument(
        '--view',
        choices=['tui', 'web', 'logs'],
        default='tui',
        help='UI mode: tui (textual interface), web (browser dashboard), logs (headless)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=7681,
        help='Port for web server (only used with --view web, default: 7681 same as ttyd)'
    )
    args = parser.parse_args()

    # Create configuration
    config = AppConfig.create_default(use_mock=args.mock)

    # Create controller
    controller = ConveyorController(config)

    # Log mode
    mode = "MOCK" if config.use_mock else "LIVE"
    controller.log_manager.debug(f"Starting in {mode} mode")


    # Create rule engine
    rule_engine = RuleEngine(controller)

    # Setup rules from rules.py
    from rules import setup_rules
    setup_rules(rule_engine)

    # Create shared state for thread-safe communication
    shared_state = SystemState()

    # Create and start background polling thread
    polling_thread = PollingThread(
        controller=controller,
        rule_engine=rule_engine,
        state=shared_state,
        poll_interval=config.system.poll_interval
    )

    try:
        # Start polling thread BEFORE UI (so data is ready)
        polling_thread.start()
        controller.log_manager.debug("Background polling thread started")

        # Route to appropriate viewer based on --view argument
        if args.view == 'web':
            # Web dashboard mode
            from src.web_server import run_web_dashboard
            controller.log_manager.info(f"Starting in WEB mode on port {args.port}")
            run_web_dashboard(shared_state, controller.log_manager, config, port=args.port)

        elif args.view == 'logs':
            # Headless logs-only mode
            controller.log_manager.info("Starting in LOGS-ONLY mode (headless)")
            controller.log_manager.info("Press Ctrl+C to stop")
            # Just keep running until interrupted
            import time
            while True:
                time.sleep(1)

        else:  # args.view == 'tui' (default)
            # Textual TUI mode (editable in mock mode, read-only in real mode)
            controller.log_manager.info("Starting in TUI mode")
            run_tui(
                controller=controller,
                rule_engine=rule_engine,
                config=config,
                editable=config.use_mock,
                shared_state=shared_state
            )

    except KeyboardInterrupt:
        controller.log_manager.info("Shutting down")
        # Turn off comms LED
        try:
            controller.procon.set('LED_GREEN', False)
        except:
            pass
    finally:
        # Stop polling thread
        controller.log_manager.info("Stopping polling thread...")
        polling_thread.stop()
        try:
            polling_thread.join(timeout=2.0)
        except KeyboardInterrupt:
            # User hit Ctrl+C again during shutdown - force exit
            pass

        # Close connections
        try:
            controller.close()
            controller.log_manager.info("Connections closed")
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
