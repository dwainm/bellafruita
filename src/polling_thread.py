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
    comms_failed: bool = False
    connected: bool = False

    # Rule engine state (copy)
    rule_state: Dict[str, Any] = field(default_factory=dict)
    active_rules: list = field(default_factory=list)

    # Thread synchronization
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Heartbeat counters (incremented on each successful read)
    input_heartbeat: int = 0
    output_heartbeat: int = 0

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
        self.comms_failed = rule_state.get('COMMS_FAILED', False)

    def get_snapshot(self) -> dict:
        """Get a thread-safe snapshot of all state."""
        with self.lock:
            return {
                'input_data': self.input_data.copy(),
                'output_data': self.output_data.copy(),
                'comms_failed': self.comms_failed,
                'connected': self.connected,
                'rule_state': self.rule_state.copy(),
                'active_rules': self.active_rules.copy(),
                'input_heartbeat': self.input_heartbeat,
                'output_heartbeat': self.output_heartbeat,
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

    def stop(self) -> None:
        """Signal the thread to stop."""
        self._stop_event.set()

    def run(self) -> None:
        """Main polling loop - runs in background thread."""
        self.controller.log_manager.info("Polling thread started")

        while not self._stop_event.is_set():
            loop_start = time.time()

            try:
                # Check if we should skip reads due to comms failure
                should_read = True
                with self.state.lock:
                    comms_failed = self.state.comms_failed

                if comms_failed:
                    # Communications have failed - SKIP all reads until operator acknowledges
                    # Operator must cycle the auto_start switch (off then on) to reset COMMS_FAILED
                    should_read = False

                # Perform blocking I/O (outside the lock!)
                if should_read:
                    input_data = self.controller.read_and_log_all_inputs()
                    output_data = self.controller.read_and_log_all_outputs()
                else:
                    # During comms failure, still attempt to read inputs for operator acknowledgment
                    # (Auto_Select switch cycling). Inputs and outputs are on separate PLCs,
                    # so inputs might still be readable even if output PLC has failed.
                    try:
                        input_data = self.controller.read_and_log_all_inputs()
                    except Exception as e:
                        self.controller.log_manager.error(f"Failed to read inputs during comms failure: {e}")
                        input_data = {}
                    output_data = {}

                # ALWAYS evaluate rules, even during comms failure
                # This allows CommsResetRule to detect operator acknowledgment via Auto_Select switch
                if self.rule_engine:
                    sensor_data = {**input_data, **output_data}
                    self.rule_engine.evaluate(sensor_data)

                # Update shared state (quick operation with lock)
                with self.state.lock:
                    if should_read:
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

            # Sleep for remainder of poll interval
            elapsed = time.time() - loop_start
            sleep_time = max(0, self.poll_interval - elapsed)
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

        self.controller.log_manager.info("Polling thread stopped")
