"""Main control logic for Bella Fruita apple sorting machine feeder."""

import argparse
from src.modbus import create_modbus_client, Procon, MODBUS_MAP, get_all_labels
from src.logging_system import LogManager
from src.tui import run_tui
from src.rules import RuleEngine

# ============================================================================
# CONFIGURATION - Edit these values as needed
# ============================================================================

# Application Mode (can be overridden with --mock flag)
USE_MOCK = False   # Default: False for production hardware

# Modbus Connection Settings
INPUT_IP = "172.20.231.25"      # IP address of input Modbus terminal (sensors)
OUTPUT_IP = "172.20.231.49"     # IP address of output Modbus terminal (motors)
INPUT_SLAVE_ID = 1              # Modbus slave ID for input terminal
OUTPUT_SLAVE_ID = 1             # Modbus slave ID for output terminal

# Modbus Address Mapping (Legacy - use Procon API with labels instead)
SENSOR1_ADDRESS = 0             # Address of first sensor (use 'S1' label with Procon API)
MOTOR_ONE_ADDRESS = 0           # Address of first motor (use 'MOTOR_1' label with Procon API)

# Timing Configuration
POLL_INTERVAL = 0.1             # Fast poll interval in seconds (100ms = 0.1)
LOG_STACK_SIZE = 3000           # Maximum number of log entries to keep
COMMS_TIMEOUT = 5.0             # Seconds before declaring comms dead (if REG0=0)

# TUI Update Rates
TUI_POLL_RATE = 0.1             # TUI display update rate in seconds (100ms = 10Hz)
TUI_LOG_REFRESH_RATE = 3.0      # Log display refresh rate in seconds
TUI_HEARTBEAT_RESET_RATE = 0.25 # Heartbeat indicator reset rate in seconds


class ConveyorController:
    """Controller for apple sorting conveyor system."""

    def __init__(self, input_ip: str, output_ip: str, mock: bool = False):
        """Initialize conveyor controller with input and output clients.

        Args:
            input_ip: IP address of input Modbus terminal (sensors)
            output_ip: IP address of output Modbus terminal (motors)
            mock: If True, use mock clients for testing
        """
        self.input_client = create_modbus_client(input_ip, mock=mock)
        self.output_client = create_modbus_client(output_ip, mock=mock)
        self.procon = Procon(self.input_client, self.output_client, INPUT_SLAVE_ID, OUTPUT_SLAVE_ID)
        self.mock = mock
        self.log_manager = LogManager(max_entries=LOG_STACK_SIZE)
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
            self.log_manager.info("Connected to both terminals")

        return input_ok and output_ok

    def close(self):
        """Close both Modbus connections."""
        self.input_client.close()
        self.output_client.close()

    def motor_one_on(self) -> bool:
        """Turn motor one on.

        Returns:
            bool: True if successful
        """
        return self.procon.set('output', 'motor_1', True)

    def motor_one_off(self) -> bool:
        """Turn motor one off.

        Returns:
            bool: True if successful
        """
        return self.procon.set('output', 'motor_1', False)

    def sensor1_broken(self) -> bool:
        """Check if sensor 1 is broken (beam interrupted).

        Returns:
            bool: True if sensor beam is broken
        """
        result = self.procon.get('input', 's1')
        return result if result is not None else False

    def comms_check(self) -> bool:
        """Check communication with output terminal.

        Returns:
            bool: True if communication OK
        """
        result = self.procon.get('output', 'version')
        return result is not None and result != 0

    def read_sensor_state(self) -> dict:
        """Read current sensor state.

        Returns:
            dict: Sensor state data
        """
        return {
            "sensor1_broken": self.sensor1_broken(),
            "comms_ok": self.comms_check()
        }

    def read_and_log_all_inputs(self) -> dict:
        """Read all 16 inputs and log them.

        Returns:
            dict: Dictionary of all input states with labels
        """
        # Use Procon API to read all input coils - works for both mock and real
        input_data = self.procon.get_all('input', 'coils')

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
        comms_healthy = self.log_manager.check_comms_health(timeout_seconds=COMMS_TIMEOUT)

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
            for motor in ['motor_1', 'motor_2', 'motor_3', 'motor_4']:
                self.procon.set('output', motor, False)
            self.log_manager.info("All motors stopped")
        except Exception as e:
            self.log_manager.error(f"Error stopping motors: {e}")

    def retry_connection(self) -> bool:
        """Attempt to reconnect to Modbus terminals.

        Returns:
            bool: True if reconnection successful
        """
        self.log_manager.info("Attempting to reconnect...")

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
            self.log_manager.info("Reconnection successful")
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
    args = parser.parse_args()

    # Determine if using mock mode (command-line flag overrides config)
    use_mock = args.mock or USE_MOCK

    # Create controller
    controller = ConveyorController(
        input_ip=INPUT_IP,
        output_ip=OUTPUT_IP,
        mock=use_mock
    )

    # Log mode
    mode = "MOCK" if use_mock else "LIVE"
    controller.log_manager.info(f"Starting in {mode} mode")

    # Create rule engine
    rule_engine = RuleEngine(controller)

    # Setup rules from rules.py
    from rules import setup_rules
    setup_rules(rule_engine)

    try:
        # Run with TUI (editable in mock mode, read-only in real mode)
        run_tui(controller=controller, rule_engine=rule_engine, editable=use_mock)

    except KeyboardInterrupt:
        controller.log_manager.info("Shutting down")
        controller.motor_one_off()
    finally:
        controller.close()
        controller.log_manager.info("Connections closed")


if __name__ == "__main__":
    main()
