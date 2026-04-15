"""Logging system for Modbus polling data."""

from dataclasses import dataclass
from datetime import datetime
from collections import deque
from typing import Dict, Any, List, Optional
import time
import json
import os
import threading
from pathlib import Path
import atexit


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
    level: str  # "INFO", "WARNING", "ERROR", "CRITICAL", "DEBUG"
    message: str
    context: Optional[Dict[str, Any]] = None  # Additional context for DEBUG logs

    def get_formatted_time(self) -> str:
        """Get formatted timestamp string."""
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds


class LogManager:
    """Manages log stacks for Modbus devices."""

    def __init__(self, max_entries: int = 3000, log_file: Optional[str] = None,
                 debug_mode: bool = False, retention_days: int = 7):
        """Initialize log manager.

        Args:
            max_entries: Maximum number of log entries to keep per device
            log_file: Path to persistent log file (default: logs/system_events.jsonl)
            debug_mode: Enable debug logging (default: False)
            retention_days: Delete rotated log files older than this many days
        """
        self.max_entries = max_entries
        self.retention_days = retention_days
        self.input_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.output_logs: deque[LogEntry] = deque(maxlen=max_entries)
        self.event_logs: deque[EventEntry] = deque(maxlen=max_entries)
        self._logged_once: set[str] = set()  # Track messages logged once
        self.debug_mode = debug_mode
        self._last_cleanup_time: float = 0.0
        self._log_buffer: list[EventEntry] = []
        self._buffer_lock = threading.Lock()
        self._flush_threshold = 50
        atexit.register(self._flush_buffer)

        # Set up log file path
        if log_file is None:
            log_file = "logs/system_events.jsonl"
        self.log_file = Path(log_file)

        # Create logs directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Clean up old rotated log files on startup
        self._cleanup_old_log_files()

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

    def log_event(self, level: str, message: str, **context) -> None:
        """Log a system event with optional context."""
        entry = EventEntry(
            timestamp=time.time(),
            level=level.upper(),
            message=message,
            context=context if context else None
        )
        # Only add to in-memory logs if not DEBUG (UI never sees DEBUG)
        if entry.level != "DEBUG":
            self.event_logs.append(entry)
        # Skip DEBUG file writes unless debug_mode is enabled
        if entry.level == "DEBUG" and not self.debug_mode:
            return
        with self._buffer_lock:
            self._log_buffer.append(entry)
            if len(self._log_buffer) >= self._flush_threshold:
                self._write_buffer_to_file()

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

    def debug(self, message: str, **context) -> None:
        """Log a debug event - always writes to file, never shown in UI."""
        self.log_event("DEBUG", message, **context)

    def debug_rule(self, rule_name: str, conditions: Dict[str, Any]) -> None:
        """Log DEBUG when a rule condition is met - file only.
         
        Args:
            rule_name: Name of the rule that fired
            conditions: Dict of condition names and their boolean values
        """
        self.log_event(
            "DEBUG",
            f"[Rule Triggered] {rule_name}",
            rule=rule_name,
            conditions=conditions
        )

    def log_io_changes(self, current_io: Dict[str, Any]) -> None:
        """Log DEBUG for any I/O values that changed since last call.
        
        Args:
            current_io: Current I/O state dict (inputs + outputs)
        """
        if not hasattr(self, '_prev_io'):
            self._prev_io = {}
        
        changes = {}
        for key, value in current_io.items():
            if key not in self._prev_io or self._prev_io[key] != value:
                changes[key] = {'from': self._prev_io.get(key), 'to': value}
        
        if changes:
            # Build readable message: "I/O: S1=False, MOTOR_2=True"
            change_strs = [f"{k}={v['to']}" for k, v in changes.items()]
            msg = f"I/O: {', '.join(change_strs)}"
            self.debug(msg, changes=changes)
        
        self._prev_io = current_io.copy()

    def log_mem_changes(self, current_mem: Dict[str, Any]) -> None:
        """Log DEBUG for any memory values that changed since last call.
        
        Args:
            current_mem: Current memory state dict
        """
        if not hasattr(self, '_prev_mem'):
            self._prev_mem = {}
        
        changes = {}
        for key, value in current_mem.items():
            if key not in self._prev_mem or self._prev_mem[key] != value:
                changes[key] = {'from': self._prev_mem.get(key), 'to': value}
        
        if changes:
            # Build readable message: "MEM: _MODE=MOVING, C3_Timer=12345"
            change_strs = [f"{k}={v['to']}" for k, v in changes.items()]
            msg = f"MEM: {', '.join(change_strs)}"
            self.debug(msg, changes=changes)
        
        self._prev_mem = current_mem.copy()

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

    def get_recent_events(self, count: int = 2000, include_debug: bool = False) -> List[EventEntry]:
        """Get most recent event logs.
        
        Args:
            count: Maximum number of events to return
            include_debug: If True, include DEBUG events (default: False)
            
        Returns:
            List of EventEntry objects, newest last
            
        Note: DEBUG events are not stored in memory (file-only), so include_debug
              only affects future implementations if DEBUG storage changes.
        """
        events = list(self.event_logs)
        if not include_debug:
            events = [e for e in events if e.level != "DEBUG"]
        return events[-count:] if events else []

    def _retention_cutoff(self) -> float:
        """Return the oldest timestamp we want to keep."""
        return time.time() - (self.retention_days * 86400)

    def _load_logs_from_file(self) -> None:
        """Load event logs from persistent files on startup.

        Loads from all rotated log files within retention period, oldest first.
        """
        cutoff = self._retention_cutoff()
        log_dir = self.log_file.parent
        base_name = self.log_file.stem  # system_events

        # Find all rotated log files (system_events.YYYY-MM-DD*.jsonl)
        rotated_files = sorted(log_dir.glob(f"{base_name}.*.jsonl"))

        # Load rotated files first (oldest to newest based on filename)
        for path in rotated_files:
            self._load_single_log_file(path, cutoff=cutoff)

        # Load legacy .old backup if it exists
        backup_file = Path(str(self.log_file) + '.old')
        if backup_file.exists():
            self._load_single_log_file(backup_file, cutoff=cutoff)

        # Load current file last (newest)
        if self.log_file.exists():
            self._load_single_log_file(self.log_file, cutoff=cutoff)

    def _load_single_log_file(self, file_path: Path, cutoff: float = 0.0) -> None:
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
                # Add context for DEBUG logs (rule, conditions, mem_state, io_state)
                if entry.context:
                    data.update(entry.context)
                f.write(json.dumps(data) + '\n')
        except Exception:
            pass

    def _write_buffer_to_file(self) -> None:
        """Write all buffered entries to file in one batch."""
        if not self._log_buffer:
            return
        try:
            with open(self.log_file, 'a') as f:
                for entry in self._log_buffer:
                    data = {
                        'timestamp': entry.timestamp,
                        'level': entry.level,
                        'message': entry.message,
                        'formatted_time': entry.get_formatted_time()
                    }
                    if entry.context:
                        data.update(entry.context)
                    f.write(json.dumps(data) + '\n')
            self._log_buffer.clear()
        except Exception:
            pass

    def _flush_buffer(self) -> None:
        """Flush remaining buffer to file (called on shutdown)."""
        with self._buffer_lock:
            if self._log_buffer:
                self._write_buffer_to_file()

    def cleanup_old_entries(self) -> None:
        """Remove entries older than retention_days from memory and disk.

        Keeps in-memory events within retention_days.
        Rotates current log to a timestamped backup when max_entries is exceeded.
        Deletes rotated files older than retention_days.
        """
        cutoff = self._retention_cutoff()
        now = time.time()
        should_cleanup_files = (now - self._last_cleanup_time) >= 86400

        # Trim in-memory deque — rebuild without old entries
        fresh = [e for e in self.event_logs if e.timestamp >= cutoff]
        if len(fresh) < len(self.event_logs):
            self.event_logs.clear()
            self.event_logs.extend(fresh)

        if not self.log_file.exists():
            if should_cleanup_files:
                self._cleanup_old_log_files()
                self._last_cleanup_time = now
            return

        try:
            # Check line count
            line_count = 0
            with open(self.log_file, 'r') as f:
                for _ in f:
                    line_count += 1

            # Only rotate if we've exceeded max_entries
            if line_count <= self.max_entries:
                # Clean up old rotated files once per day
                if should_cleanup_files:
                    self._cleanup_old_log_files()
                    self._last_cleanup_time = now
                return

            # Create timestamped backup filename (e.g., system_events.2026-03-06.jsonl)
            from datetime import datetime
            date_str = datetime.now().strftime('%Y-%m-%d')
            base_name = self.log_file.stem  # system_events
            backup_name = f"{base_name}.{date_str}.jsonl"
            backup_file = self.log_file.parent / backup_name

            # If backup for today already exists, append a counter
            counter = 1
            while backup_file.exists():
                backup_name = f"{base_name}.{date_str}.{counter}.jsonl"
                backup_file = self.log_file.parent / backup_name
                counter += 1

            # Rename current file to backup
            self.log_file.rename(backup_file)

            # Clean up old rotated files
            self._cleanup_old_log_files()
            self._last_cleanup_time = now

            # New file will be created automatically on next log write

        except Exception:
            # Silently fail - don't crash if rotation fails
            pass

        # Clean up old rotated files once per day when not rotated
        if should_cleanup_files:
            self._cleanup_old_log_files()
            self._last_cleanup_time = now

    def _cleanup_old_log_files(self) -> None:
        """Delete rotated log files older than retention_days."""
        try:
            cutoff_time = time.time() - (self.retention_days * 86400)
            log_dir = self.log_file.parent
            base_name = self.log_file.stem

            # Find all rotated log files (<base_name>.YYYY-MM-DD*.jsonl)
            for path in log_dir.glob(f"{base_name}.*.jsonl"):
                # Skip the current log file
                if path == self.log_file:
                    continue

                # Check file modification time
                if path.stat().st_mtime < cutoff_time:
                    path.unlink()

        except Exception:
            # Silently fail - don't crash if cleanup fails
            pass
