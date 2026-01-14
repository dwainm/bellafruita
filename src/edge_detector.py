"""Edge detection wrapper for sensor data in rules.

Provides rising_edge() and falling_edge() methods to detect signal transitions
within a configurable time window, solving the problem of missing brief button
presses that occur between poll cycles.
"""

import time
from typing import Any, Optional
from collections import deque


class EdgeDetectorDict(dict):
    """Dictionary wrapper that adds edge detection methods for signals.

    This allows rules to detect signal transitions (rising/falling edges) within
    a time window, rather than just checking the current level. This is critical
    for catching brief button presses that might be shorter than the poll interval.

    Example:
        # In a rule condition:
        if data.rising_edge('E_Stop'):  # Detects button press
            # This triggers even if button was only pressed for 50ms
            # and we're polling at 100ms intervals
    """

    def __init__(self, current_data: dict, log_manager, default_window_ms: float = 500.0):
        """Initialize EdgeDetectorDict with current data and log access.

        Args:
            current_data: Current sensor/output data dict
            log_manager: LogManager instance for accessing historical data
            default_window_ms: Default time window for edge detection in milliseconds
        """
        super().__init__(current_data)
        self.log_manager = log_manager
        self.default_window_ms = default_window_ms

    def rising_edge(self, signal: str, window_ms: Optional[float] = None) -> bool:
        """Detect rising edge (False->True transition) within time window.

        Args:
            signal: Signal name to check (e.g., 'E_Stop', 'S1')
            window_ms: Time window in milliseconds (uses default if not specified)

        Returns:
            True if signal transitioned from False to True within the window
        """
        window = window_ms if window_ms is not None else self.default_window_ms
        return self._detect_edge(signal, 'rising', window)

    def falling_edge(self, signal: str, window_ms: Optional[float] = None) -> bool:
        """Detect falling edge (True->False transition) within time window.

        Args:
            signal: Signal name to check (e.g., 'S2', 'MOTOR_2')
            window_ms: Time window in milliseconds (uses default if not specified)

        Returns:
            True if signal transitioned from True to False within the window
        """
        window = window_ms if window_ms is not None else self.default_window_ms
        return self._detect_edge(signal, 'falling', window)

    def extended_hold(self, signal: str, value: bool, hold_seconds: float = 1.0) -> bool:
        """Check if signal has been held at a specific value for a duration.

        This is useful for debouncing signals that might have brief glitches.
        For example, checking if a trip signal has been FALSE for 1+ seconds
        before triggering an emergency stop.

        Args:
            signal: Signal name to check (e.g., 'M1_Trip', 'E_Stop')
            value: The value to check for (True or False)
            hold_seconds: How long the signal must be held (in seconds)

        Returns:
            True if signal has been continuously at 'value' for 'hold_seconds'

        Example:
            # Check if M1_Trip has been FALSE (tripped) for 1+ seconds
            if data.extended_hold('M1_Trip', False, 1.0):
                # Genuine trip condition - take action
        """
        logs = self.log_manager.input_logs

        if len(logs) < 2:
            return False

        # Calculate time window
        current_time = time.time()
        cutoff_time = current_time - hold_seconds

        # Collect all values within the hold window
        values_in_window = []
        for entry in reversed(logs):
            if entry.timestamp < cutoff_time:
                break
            values_in_window.append((entry.timestamp, entry.data.get(signal)))

        # Need enough history to cover the hold period
        if not values_in_window:
            return False

        # Check if we have data covering the entire hold period
        oldest_timestamp = values_in_window[-1][0]
        if oldest_timestamp > cutoff_time:
            # Not enough history - can't confirm hold
            return False

        # Check that ALL values in the window match the desired value
        for timestamp, signal_value in values_in_window:
            if signal_value != value:
                return False  # Found a different value - not held continuously

        return True  # All values match - signal has been held

    def _detect_edge(self, signal: str, edge_type: str, window_ms: float) -> bool:
        """Internal method to detect edges in log history.

        Args:
            signal: Signal name
            edge_type: 'rising' or 'falling'
            window_ms: Time window in milliseconds

        Returns:
            True if edge detected within window
        """
        # Get input logs (most signals are inputs)
        logs = self.log_manager.input_logs

        if len(logs) < 2:
            return False

        # Calculate time window
        current_time = time.time()
        window_seconds = window_ms / 1000.0
        cutoff_time = current_time - window_seconds

        # Collect values within the time window (iterate backwards from newest)
        values_in_window = []
        for entry in reversed(logs):
            if entry.timestamp < cutoff_time:
                break
            values_in_window.append((entry.timestamp, entry.data.get(signal)))

        if len(values_in_window) < 2:
            return False

        # Reverse to get chronological order (oldest first)
        values_in_window.reverse()

        # Look for the specified edge transition
        for i in range(len(values_in_window) - 1):
            current_val = values_in_window[i][1]
            next_val = values_in_window[i + 1][1]

            if edge_type == 'rising':
                if current_val == False and next_val == True:
                    return True
            elif edge_type == 'falling':
                if current_val == True and next_val == False:
                    return True

        return False
