"""Background polling thread for Modbus data acquisition.

This module handles all blocking I/O in a separate thread, keeping the UI responsive.
"""

import threading
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class SystemState:
    """Thread-safe shared state between polling thread and UI.

    This class holds all system data that needs to be shared between
    the background polling thread and the UI thread.
    """
    # Data from Modbus devices
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)

    # System status
    in_error_comms_mode: bool = False
    connected: bool = False

    # Rule engine state (copy)
    rule_state: Dict[str, Any] = field(default_factory=dict)
    active_rules: list = field(default_factory=list)

    # Thread synchronization
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Heartbeat counters (incremented on each successful read)
    input_heartbeat: int = 0
    output_heartbeat: int = 0

    # External trigger for klaar_geweeg button press
    klaar_geweeg: bool = False

    def update_from_poll(self, input_data: Dict[str, Any], output_data: Dict[str, Any]) -> None:
        """Update state from polling thread (must be called with lock held)."""
        self.input_data = input_data.copy()
        self.output_data = output_data.copy()
        self.input_heartbeat += 1
        self.output_heartbeat += 1

    def update_rule_state(self, rule_state: Dict[str, Any], active_rules: list) -> None:
        """Update rule engine state (must be called with lock held)."""
        self.rule_state = rule_state.copy()
        self.active_rules = active_rules.copy()
        # Derive error comms mode from mode
        mode = rule_state.get('_MODE')
        self.in_error_comms_mode = mode in ('ERROR_COMMS', 'ERROR_COMMS_ACK')

    def get_snapshot(self) -> dict:
        """Get a thread-safe snapshot of all state."""
        with self.lock:
            # Inject klaar_geweeg into rule_state so it shows in State Variables
            rule_state_with_virtual = self.rule_state.copy()
            rule_state_with_virtual['KLAAR_GEWEEG'] = self.klaar_geweeg

            return {
                'input_data': self.input_data.copy(),
                'output_data': self.output_data.copy(),
                'in_error_comms_mode': self.in_error_comms_mode,
                'connected': self.connected,
                'rule_state': rule_state_with_virtual,
                'active_rules': self.active_rules.copy(),
                'input_heartbeat': self.input_heartbeat,
                'output_heartbeat': self.output_heartbeat,
                'klaar_geweeg': self.klaar_geweeg,
            }


class PollingThread(threading.Thread):
    """Background thread for polling Modbus devices and evaluating rules.

    This thread runs independently of the UI, performing all blocking I/O operations.
    The UI thread only reads the shared state, ensuring it never blocks.
    """

    def __init__(self, controller, rule_engine, state: SystemState, poll_interval: float = 0.1):
        """Initialize polling thread.

        Args:
            controller: ConveyorController instance
            rule_engine: RuleEngine instance (optional)
            state: Shared SystemState instance
            poll_interval: Polling interval in seconds
        """
        super().__init__(daemon=True, name="ModbusPollingThread")
        self.controller = controller
        self.rule_engine = rule_engine
        self.state = state
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._rotation_counter = 0  # Counter for periodic log rotation

    def stop(self) -> None:
        """Signal the thread to stop."""
        self._stop_event.set()

    def run(self) -> None:
        """Main polling loop - runs in background thread."""
        self.controller.log_manager.debug("Polling thread started")

        while not self._stop_event.is_set():
            loop_start = time.time()

            try:
                # Check if we should skip reads due to comms failure
                should_read = True
                with self.state.lock:
                    in_error_comms_mode = self.state.in_error_comms_mode

                if in_error_comms_mode:
                    # Communications have failed - SKIP all reads until operator acknowledges
                    # Operator must cycle the auto_start switch (off then on) to reset COMMS_FAILED
                    should_read = False

                # Perform blocking I/O (outside the lock!)
                # Always wrap in try/except to handle broken connections gracefully
                try:
                    if should_read:
                        input_data = self.controller.read_and_log_all_inputs()
                        output_data = self.controller.read_and_log_all_outputs()
                    else:
                        # During comms failure, keep trying to read inputs to detect recovery
                        # This allows comms health check to see when VERSION heartbeat returns
                        input_data = self.controller.read_and_log_all_inputs()
                        output_data = self.controller.read_and_log_all_outputs()
                except Exception as e:
                    # Read failed - will keep retrying next cycle
                    if in_error_comms_mode:
                        self.controller.log_manager.debug(f"Read failed during ERROR_COMMS (will retry): {e}")
                    else:
                        self.controller.log_manager.error(f"Read failed during normal operation: {e}")
                    input_data = {}
                    output_data = {}

                # ALWAYS evaluate rules, even during comms failure
                # This allows CommsResetRule to detect operator acknowledgment via Auto_Select switch
                if self.rule_engine:
                    sensor_data = {**input_data, **output_data}
                    self.rule_engine.evaluate(sensor_data)

                # Update shared state (quick operation with lock)
                with self.state.lock:
                    # Update state if we have valid data (even during ERROR_COMMS recovery)
                    if input_data or output_data:
                        self.state.update_from_poll(input_data, output_data)

                    if self.rule_engine:
                        self.state.update_rule_state(
                            self.rule_engine.get_state(),
                            self.rule_engine.get_active_rules()
                        )
                    else:
                        # Fallback: use controller's comms check
                        self.controller.check_and_handle_comms_failure()
                        self.state.comms_failed = self.controller.comms_dead

            except Exception as e:
                self.controller.log_manager.error(f"Polling thread error: {e}")

            # Rotate log file periodically (every ~1000 loops to avoid excessive file I/O)
            self._rotation_counter += 1
            if self._rotation_counter >= 1000:
                self.controller.log_manager.rotate_log_file()
                self._rotation_counter = 0

            # Sleep for remainder of poll interval
            elapsed = time.time() - loop_start
            sleep_time = max(0, self.poll_interval - elapsed)
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

        self.controller.log_manager.debug("Polling thread stopped")
