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

    def __init__(self, max_entries: int = 50000, log_file: Optional[str] = None,
                 debug_mode: bool = False, retention_days: int = 7):
        """Initialize log manager.

        Args:
            max_entries: Maximum number of log entries to keep per device
            log_file: Path to persistent log file (default: logs/system_events.jsonl)
            debug_mode: Enable debug logging (default: False)
            retention_days: Number of days of event history to keep on disk
        """
        self.max_entries = max_entries
        self.retention_days = retention_days
        self.input_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.output_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.event_logs: deque[EventEntry] = deque(maxlen=max_entries)
        self._logged_once: set[str] = set()  # Track messages logged once
        self.debug_mode = debug_mode
        self._last_cleanup_time: float = 0.0  # Track when we last rewrote the log file

        # Set up log file path
        if log_file is None:
            log_file = "logs/system_events.jsonl"
        self.log_file = Path(log_file)

        # Create logs directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing logs from file (filtered to retention window)
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
        """Get most recent input logs."""
        return list(self.input_logs)[-count:] if self.input_logs else []

    def get_recent_output_logs(self, count: int = 10) -> List[LogEntry]:
        """Get most recent output logs."""
        return list(self.output_logs)[-count:] if self.output_logs else []

    def check_comms_health(self, timeout_seconds: float = 5.0) -> bool:
        """Check if communications are healthy based on recent logs."""
        if not self.output_logs:
            return True  # No logs yet - assume healthy on startup

        current_time = time.time()
        cutoff_time = current_time - timeout_seconds

        last_log_time = self.output_logs[-1].timestamp
        if last_log_time < cutoff_time:
            return False

        for entry in reversed(self.output_logs):
            if entry.timestamp < cutoff_time:
                break
            version_value = entry.data.get('VERSION', 0)
            if version_value != 0:
                return True

        return False

    def get_last_input_timestamp(self) -> float:
        """Get timestamp of last input log."""
        return self.input_logs[-1].timestamp if self.input_logs else 0

    def get_last_output_timestamp(self) -> float:
        """Get timestamp of last output log."""
        return self.output_logs[-1].timestamp if self.output_logs else 0

    def log_event(self, level: str, message: str) -> None:
        """Log a system event."""
        entry = EventEntry(
            timestamp=time.time(),
            level=level.upper(),
            message=message
        )
        self.event_logs.append(entry)
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

    def debug(self, message: str) -> None:
        """Log a debug event (only when debug_mode is enabled)."""
        if self.debug_mode:
            self.log_event("DEBUG", message)

    def log_once(self, level: str, message: str) -> bool:
        """Log a message only once, preventing duplicates."""
        message_key = f"{level}:{message}"
        if message_key not in self._logged_once:
            self._logged_once.add(message_key)
            self.log_event(level, message)
            return True
        return False

    def info_once(self, message: str) -> bool:
        return self.log_once("INFO", message)

    def warning_once(self, message: str) -> bool:
        return self.log_once("WARNING", message)

    def error_once(self, message: str) -> bool:
        return self.log_once("ERROR", message)

    def critical_once(self, message: str) -> bool:
        return self.log_once("CRITICAL", message)

    def clear_logged_once(self, message: str = None, level: str = None) -> None:
        """Clear logged once cache to allow messages to be logged again."""
        if message is None and level is None:
            self._logged_once.clear()
        elif message and level:
            self._logged_once.discard(f"{level}:{message}")
        elif message:
            for lvl in ["INFO", "WARNING", "ERROR", "CRITICAL"]:
                self._logged_once.discard(f"{lvl}:{message}")
        elif level:
            to_remove = [key for key in self._logged_once if key.startswith(f"{level}:")]
            for key in to_remove:
                self._logged_once.discard(key)

    def get_recent_events(self, count: int = 2000) -> List[EventEntry]:
        """Get most recent event logs."""
        return list(self.event_logs)[-count:] if self.event_logs else []

    def _retention_cutoff(self) -> float:
        """Return the oldest timestamp we want to keep."""
        return time.time() - (self.retention_days * 86400)

    def _load_logs_from_file(self) -> None:
        """Load event logs from persistent files on startup.

        Loads from the backup (.old) file first, then the current file.
        Entries older than retention_days are skipped.
        """
        cutoff = self._retention_cutoff()

        # Load backup first (older logs), then current (newer logs)
        backup_file = Path(str(self.log_file) + '.old')
        for path in [backup_file, self.log_file]:
            if path.exists():
                self._load_single_log_file(path, cutoff=cutoff)

    def _load_single_log_file(self, file_path: Path, cutoff: float = 0.0) -> None:
        """Load logs from a single file, skipping entries older than cutoff."""
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = data['timestamp']

                        # Skip entries outside retention window
                        if ts < cutoff:
                            continue

                        level = data['level']
                        if level == 'DEBUG' and not self.debug_mode:
                            continue

                        entry = EventEntry(
                            timestamp=ts,
                            level=level,
                            message=data['message']
                        )
                        self.event_logs.append(entry)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception as e:
            print(f"Warning: Could not load logs from {file_path}: {e}")

    def _append_log_to_file(self, entry: EventEntry) -> None:
        """Append a single log entry to the persistent file."""
        try:
            with open(self.log_file, 'a') as f:
                data = {
                    'timestamp': entry.timestamp,
                    'level': entry.level,
                    'message': entry.message,
                    'formatted_time': entry.get_formatted_time()
                }
                f.write(json.dumps(data) + '\n')
        except Exception:
            pass

    def cleanup_old_entries(self) -> None:
        """Remove entries older than retention_days from memory and disk.

        Rewrites the log file at most once per day to avoid excessive I/O.
        The in-memory deque is always trimmed immediately.
        """
        cutoff = self._retention_cutoff()
        now = time.time()

        # Trim in-memory deque — rebuild without old entries
        fresh = [e for e in self.event_logs if e.timestamp >= cutoff]
        if len(fresh) < len(self.event_logs):
            self.event_logs.clear()
            self.event_logs.extend(fresh)

        # Rewrite file once per day to remove old lines
        if now - self._last_cleanup_time < 86400:
            return
        self._last_cleanup_time = now

        if not self.log_file.exists():
            return

        try:
            # Read all lines that are still within retention window
            kept_lines = []
            with open(self.log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data['timestamp'] >= cutoff:
                            kept_lines.append(line)
                    except (json.JSONDecodeError, KeyError):
                        continue

            # Rewrite file with only the kept lines
            with open(self.log_file, 'w') as f:
                for line in kept_lines:
                    f.write(line + '\n')

            # Remove the .old backup — it's now beyond retention anyway
            backup_file = Path(str(self.log_file) + '.old')
            if backup_file.exists():
                backup_file.unlink()

        except Exception:
            pass
