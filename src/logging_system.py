"""Logging system for Modbus polling data."""

from dataclasses import dataclass
from datetime import datetime
from collections import deque
from typing import Dict, Any, List, Optional
import time
import json
import os
from pathlib import Path


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

    def __init__(self, max_entries: int = 3000, log_file: Optional[str] = None):
        """Initialize log manager.

        Args:
            max_entries: Maximum number of log entries to keep per device
            log_file: Path to persistent log file (default: logs/system_events.jsonl)
        """
        self.max_entries = max_entries
        self.input_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.output_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.event_logs: deque[EventEntry] = deque(maxlen=max_entries)
        self._logged_once: set[str] = set()  # Track messages logged once

        # Set up log file path
        if log_file is None:
            log_file = "logs/system_events.jsonl"
        self.log_file = Path(log_file)

        # Create logs directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing logs from file
        self._load_logs_from_file()

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

        # Write to file immediately for persistence
        self._append_log_to_file(entry)

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

    def log_once(self, level: str, message: str) -> bool:
        """Log a message only once, preventing duplicates.

        Args:
            level: Event level ("INFO", "WARNING", "ERROR", "CRITICAL")
            message: Event message

        Returns:
            bool: True if message was logged, False if already logged before
        """
        message_key = f"{level}:{message}"
        if message_key not in self._logged_once:
            self._logged_once.add(message_key)
            self.log_event(level, message)
            return True
        return False

    def info_once(self, message: str) -> bool:
        """Log an info event only once."""
        return self.log_once("INFO", message)

    def warning_once(self, message: str) -> bool:
        """Log a warning event only once."""
        return self.log_once("WARNING", message)

    def error_once(self, message: str) -> bool:
        """Log an error event only once."""
        return self.log_once("ERROR", message)

    def critical_once(self, message: str) -> bool:
        """Log a critical event only once."""
        return self.log_once("CRITICAL", message)

    def clear_logged_once(self, message: str = None, level: str = None) -> None:
        """Clear logged once cache to allow messages to be logged again.

        Args:
            message: Specific message to clear (if None, clears all)
            level: Specific level to clear (if None, clears all levels)
        """
        if message is None and level is None:
            # Clear all
            self._logged_once.clear()
        elif message and level:
            # Clear specific message at specific level
            message_key = f"{level}:{message}"
            self._logged_once.discard(message_key)
        elif message:
            # Clear message at all levels
            for lvl in ["INFO", "WARNING", "ERROR", "CRITICAL"]:
                message_key = f"{lvl}:{message}"
                self._logged_once.discard(message_key)
        elif level:
            # Clear all messages at specific level
            to_remove = [key for key in self._logged_once if key.startswith(f"{level}:")]
            for key in to_remove:
                self._logged_once.discard(key)

    def get_recent_events(self, count: int = 50) -> List[EventEntry]:
        """Get most recent event logs.

        Args:
            count: Number of recent entries to return

        Returns:
            List of recent EventEntry objects
        """
        return list(self.event_logs)[-count:] if self.event_logs else []

    def _load_logs_from_file(self) -> None:
        """Load event logs from persistent files on startup.

        Loads from both the current file and the backup (.old) file to get more history.
        """
        # Load from backup file first (older logs)
        backup_file = Path(str(self.log_file) + '.old')
        if backup_file.exists():
            self._load_single_log_file(backup_file)

        # Then load from current file (newer logs)
        if self.log_file.exists():
            self._load_single_log_file(self.log_file)

    def _load_single_log_file(self, file_path: Path) -> None:
        """Load logs from a single file.

        Args:
            file_path: Path to log file to load
        """
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        entry = EventEntry(
                            timestamp=data['timestamp'],
                            level=data['level'],
                            message=data['message']
                        )
                        self.event_logs.append(entry)
                    except (json.JSONDecodeError, KeyError) as e:
                        # Skip malformed lines
                        continue

        except Exception as e:
            # If we can't load logs, just skip this file
            print(f"Warning: Could not load logs from {file_path}: {e}")

    def _append_log_to_file(self, entry: EventEntry) -> None:
        """Append a single log entry to the persistent file.

        Args:
            entry: EventEntry to write to file
        """
        try:
            with open(self.log_file, 'a') as f:
                data = {
                    'timestamp': entry.timestamp,
                    'level': entry.level,
                    'message': entry.message,
                    'formatted_time': entry.get_formatted_time()
                }
                f.write(json.dumps(data) + '\n')
        except Exception as e:
            # Silently fail - don't crash the app if we can't write logs
            pass

    def rotate_log_file(self) -> None:
        """Rotate log file if it gets too large.

        Creates a new file and deletes the old backup, keeping only 2 files at a time:
        - system_events.jsonl (current)
        - system_events.jsonl.old (previous rotation)
        """
        if not self.log_file.exists():
            return

        try:
            # Check file size or line count
            line_count = 0
            with open(self.log_file, 'r') as f:
                for _ in f:
                    line_count += 1

            # Only rotate if we've exceeded max_entries
            if line_count <= self.max_entries:
                return

            # Define backup file path
            backup_file = Path(str(self.log_file) + '.old')

            # Delete old backup if it exists
            if backup_file.exists():
                backup_file.unlink()

            # Rename current file to backup
            self.log_file.rename(backup_file)

            # New file will be created automatically on next log write
            # (by _append_log_to_file)

        except Exception as e:
            # Silently fail - don't crash if rotation fails
            pass
