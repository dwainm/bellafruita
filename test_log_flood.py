#!/usr/bin/env python3
"""Test script to flood the logging system with events.

Tests log rotation, file handling, and UI adaptability under high event volume.

Usage:
    python test_log_flood.py                    # Generate 15000 events (triggers rotation)
    python test_log_flood.py --count 5000       # Generate specific number of events
    python test_log_flood.py --with-web         # Start web UI after flooding
    python test_log_flood.py --with-tui         # Start TUI after flooding
    python test_log_flood.py --cleanup          # Remove test log files
"""

import argparse
import sys
import time
import random
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.logging_system import LogManager
from config import AppConfig


def generate_test_events(log_manager: LogManager, count: int, batch_size: int = 100):
    """Generate test events with various levels and messages."""

    levels = ['INFO', 'INFO', 'INFO', 'WARNING', 'ERROR']  # Weighted towards INFO

    messages = [
        "Mode: READY -> MOVING_C3_TO_C2",
        "Mode: MOVING_C3_TO_C2 -> READY",
        "Mode: READY -> MOVING_C2_TO_PALM",
        "Mode: MOVING_C2_TO_PALM -> READY",
        "Mode: READY -> MOVING_BOTH",
        "Started MOVING_C3_TO_C2 - Motor 2 started",
        "Started MOVING_C2_TO_PALM - MOTOR_2 running",
        "MOTOR_2 stopped after 1s delay",
        "Motor 3 started after 2 second delay",
        "Completed MOVING_C3_TO_C2 - both motors stopped",
        "C3_Timer - Started",
        "C3_Timer - Reset",
        "Bin detected on S1",
        "Bin detected on S2",
        "PALM_Run_Signal active",
        "KLAAR_GEWEEG flag set via API",
        "Communications healthy - VERSION heartbeat OK",
        "Auto mode selected",
        "Manual mode selected",
        "Crate positioning sensors aligned",
    ]

    warning_messages = [
        "C3_Timer not found, using default 30s delay",
        "Slow poll cycle detected: 150ms",
        "WebSocket client disconnected",
        "Retrying Modbus connection...",
    ]

    error_messages = [
        "Failed to read from input terminal",
        "Modbus timeout on output write",
        "E-Stop signal detected",
        "Motor trip detected: M1_Trip",
    ]

    print(f"Generating {count} test events...")
    start_time = time.time()

    for i in range(count):
        level = random.choice(levels)

        if level == 'INFO':
            msg = random.choice(messages)
        elif level == 'WARNING':
            msg = random.choice(warning_messages)
        else:
            msg = random.choice(error_messages)

        # Add sequence number for tracking
        msg = f"[{i+1}/{count}] {msg}"

        log_manager.log_event(level, msg)

        # Progress update every batch_size events
        if (i + 1) % batch_size == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            print(f"  Generated {i+1}/{count} events ({rate:.0f}/sec)")

    elapsed = time.time() - start_time
    print(f"Done! Generated {count} events in {elapsed:.1f}s ({count/elapsed:.0f}/sec)")


def check_log_files(log_dir: Path):
    """Show current log file status."""
    print("\nLog files:")
    total_lines = 0
    total_size = 0

    for path in sorted(log_dir.glob("system_events*.jsonl")):
        size = path.stat().st_size
        with open(path) as f:
            lines = sum(1 for _ in f)
        total_lines += lines
        total_size += size
        print(f"  {path.name}: {lines} lines, {size/1024:.1f}KB")

    print(f"  Total: {total_lines} lines, {total_size/1024:.1f}KB")


def cleanup_logs(log_dir: Path):
    """Remove all test log files."""
    print("Cleaning up log files...")
    for path in log_dir.glob("system_events*.jsonl"):
        print(f"  Removing {path.name}")
        path.unlink()
    print("Done!")


def main():
    parser = argparse.ArgumentParser(description='Test log flooding and rotation')
    parser.add_argument('--count', type=int, default=15000,
                        help='Number of events to generate (default: 15000)')
    parser.add_argument('--with-web', action='store_true',
                        help='Start web UI after flooding')
    parser.add_argument('--with-tui', action='store_true',
                        help='Start TUI after flooding')
    parser.add_argument('--cleanup', action='store_true',
                        help='Remove test log files and exit')
    parser.add_argument('--retention-days', type=int, default=7,
                        help='Log retention days for testing (default: 7)')
    parser.add_argument('--max-entries', type=int, default=10000,
                        help='Max entries before rotation (default: 10000)')
    args = parser.parse_args()

    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)

    if args.cleanup:
        cleanup_logs(log_dir)
        return

    # Show current state
    print("=== Log Flood Test ===\n")
    print(f"Settings:")
    print(f"  max_entries: {args.max_entries} (rotate when exceeded)")
    print(f"  retention_days: {args.retention_days}")
    print(f"  events to generate: {args.count}")
    print()

    check_log_files(log_dir)
    print()

    # Create log manager with test settings
    log_manager = LogManager(
        max_entries=args.max_entries,
        retention_days=args.retention_days
    )

    # Generate flood of events
    generate_test_events(log_manager, args.count)

    # Force rotation check
    print("\nChecking rotation...")
    log_manager.rotate_log_file()

    # Show results
    check_log_files(log_dir)

    # Optionally start UI
    if args.with_web:
        print("\nStarting web UI on http://localhost:7681 ...")
        import subprocess
        subprocess.run(['python', 'main.py', '--mock', '--view', 'web'])
    elif args.with_tui:
        print("\nStarting TUI...")
        import subprocess
        subprocess.run(['python', 'main.py', '--mock', '--view', 'tui'])


if __name__ == '__main__':
    main()
