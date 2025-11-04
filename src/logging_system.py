"""Logging system for Modbus polling data."""

from dataclasses import dataclass
from datetime import datetime
from collections import deque
from typing import Dict, Any, List
import time


@dataclass
class LogEntry:
    """Single log entry for a Modbus device poll."""
    timestamp: float
    device_id: str  # "INPUT" or "OUTPUT"
    data: Dict[str, Any]  # Key-value pairs of what was read

    def get_formatted_time(self) -> str:
        """Get formatted timestamp string."""
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds


@dataclass
class EventEntry:
    """Single event log entry for system events."""
    timestamp: float
    level: str  # "INFO", "WARNING", "ERROR", "CRITICAL"
    message: str

    def get_formatted_time(self) -> str:
        """Get formatted timestamp string."""
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds


class LogManager:
    """Manages log stacks for Modbus devices."""

    def __init__(self, max_entries: int = 3000):
        """Initialize log manager.

        Args:
            max_entries: Maximum number of log entries to keep per device
        """
        self.input_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.output_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.event_logs: deque[EventEntry] = deque(maxlen=max_entries)

    def log_input(self, data: Dict[str, Any]) -> None:
        """Log input module read.

        Args:
            data: Dictionary of input values (e.g., {'S1': True, 'S2': False, ...})
        """
        entry = LogEntry(
            timestamp=time.time(),
            device_id="INPUT",
            data=data
        )
        self.input_logs.append(entry)

    def log_output(self, data: Dict[str, Any]) -> None:
        """Log output module read.

        Args:
            data: Dictionary of output values (e.g., {'M1': True, 'REG0': 12345, ...})
        """
        entry = LogEntry(
            timestamp=time.time(),
            device_id="OUTPUT",
            data=data
        )
        self.output_logs.append(entry)

    def get_recent_input_logs(self, count: int = 10) -> List[LogEntry]:
        """Get most recent input logs.

        Args:
            count: Number of recent entries to return

        Returns:
            List of recent LogEntry objects
        """
        return list(self.input_logs)[-count:] if self.input_logs else []

    def get_recent_output_logs(self, count: int = 10) -> List[LogEntry]:
        """Get most recent output logs.

        Args:
            count: Number of recent entries to return

        Returns:
            List of recent LogEntry objects
        """
        return list(self.output_logs)[-count:] if self.output_logs else []

    def check_comms_health(self, timeout_seconds: float = 5.0) -> bool:
        """Check if communications are healthy based on recent logs.

        Checks if version register (VERSION) has been 0 or missing for too long,
        or if we haven't received any output logs recently (indicating read failures).

        Args:
            timeout_seconds: How long to wait before declaring comms dead

        Returns:
            bool: True if comms healthy, False if dead
        """
        if not self.output_logs:
            return True  # No logs yet - assume healthy on startup

        current_time = time.time()
        cutoff_time = current_time - timeout_seconds

        # Check if we have any recent logs at all (detects total read failure)
        last_log_time = self.output_logs[-1].timestamp
        if last_log_time < cutoff_time:
            return False  # No recent logs - comms dead

        # Check recent output logs for valid version numbers
        for entry in reversed(self.output_logs):
            if entry.timestamp < cutoff_time:
                break  # Too old, stop checking

            # Check for VERSION register (using label from MODBUS_MAP)
            version_value = entry.data.get('VERSION', 0)
            if version_value != 0:
                return True  # Found valid version number

        # No valid version number in last timeout_seconds
        return False

    def get_last_input_timestamp(self) -> float:
        """Get timestamp of last input log."""
        return self.input_logs[-1].timestamp if self.input_logs else 0

    def get_last_output_timestamp(self) -> float:
        """Get timestamp of last output log."""
        return self.output_logs[-1].timestamp if self.output_logs else 0

    def log_event(self, level: str, message: str) -> None:
        """Log a system event.

        Args:
            level: Event level ("INFO", "WARNING", "ERROR", "CRITICAL")
            message: Event message
        """
        entry = EventEntry(
            timestamp=time.time(),
            level=level.upper(),
            message=message
        )
        self.event_logs.append(entry)

    def info(self, message: str) -> None:
        """Log an info event."""
        self.log_event("INFO", message)

    def warning(self, message: str) -> None:
        """Log a warning event."""
        self.log_event("WARNING", message)

    def error(self, message: str) -> None:
        """Log an error event."""
        self.log_event("ERROR", message)

    def critical(self, message: str) -> None:
        """Log a critical event."""
        self.log_event("CRITICAL", message)

    def get_recent_events(self, count: int = 50) -> List[EventEntry]:
        """Get most recent event logs.

        Args:
            count: Number of recent entries to return

        Returns:
            List of recent EventEntry objects
        """
        return list(self.event_logs)[-count:] if self.event_logs else []
