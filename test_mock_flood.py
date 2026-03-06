#!/usr/bin/env python3
"""Simulate rapid bin movement cycles to stress test the UI.

Run mock mode in one terminal:
    python main.py --mock --view web

Then run this in another terminal:
    python test_mock_flood.py              # 10 cycles, 0.5s between events
    python test_mock_flood.py --cycles 50  # 50 cycles
    python test_mock_flood.py --fast       # 0.1s between events
    python test_mock_flood.py --turbo      # 0.02s between events (50/sec)
"""

import argparse
import requests
import time
import sys
import threading
import queue

BASE_URL = "http://localhost:7682"
MAIN_URL = "http://localhost:7681"

# Match PLC rule timing thresholds so mock behavior is closer to production
PALM_HOLD_SECONDS = 2.2      # rules.py: PALM_Run_Signal must hold 2s
SAFETY_HOLD_SECONDS = 1.2    # rules.py: E_Stop/trip holds use 1s debounce
ESTOP_DIVISOR = 500          # Roughly 1 E-Stop per 500 requested cycles
ESTOP_MIN_CYCLES = 100       # For medium+ runs, force at least one E-Stop


class RequestDispatcher:
    """Send HTTP requests on a background thread to avoid main-loop stalls."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue(maxsize=2000)
        self._stop = threading.Event()
        self._session = requests.Session()
        self._thread = threading.Thread(target=self._run, daemon=True, name="MockFloodRequestDispatcher")
        self._thread.start()

    def submit(self, method: str, url: str, json_data=None, timeout: float = 0.35):
        """Queue a request for background execution."""
        try:
            self._queue.put((method, url, json_data, timeout), timeout=1.0)
        except queue.Full:
            print("  WARN: request queue full, dropping request")

    def flush(self):
        """Wait until queued requests are sent."""
        self._queue.join()

    def pending(self) -> int:
        return self._queue.qsize()

    def close(self):
        """Stop dispatcher thread cleanly."""
        self.flush()
        self._stop.set()
        self._queue.put((None, None, None, None))
        self._thread.join(timeout=1.0)
        self._session.close()

    def _run(self):
        while not self._stop.is_set():
            method, url, json_data, timeout = self._queue.get()
            if method is None:
                self._queue.task_done()
                break

            try:
                self._session.request(method=method, url=url, json=json_data, timeout=timeout)
            except requests.exceptions.RequestException:
                pass
            finally:
                self._queue.task_done()


DISPATCHER = RequestDispatcher()


def set_input(label: str, value: bool, delay: float = 0.1):
    """Set a mock input by label."""
    # Map label to input number
    label_to_input = {
        'S1': 1, 'S2': 2, 'CS1': 3, 'CS2': 4, 'CS3': 5,
        'M1_Trip': 6, 'M2_Trip': 7, 'E_Stop': 8,
        'Manual_Select': 9, 'Auto_Select': 10,
        'CPS_1': 11, 'CPS_2': 12, 'Reset_Btn': 13,
        'PALM_Run_Signal': 14, 'DHLM_Trip_Signal': 15
    }

    input_num = label_to_input.get(label)
    if not input_num:
        print(f"Unknown input: {label}")
        return

    try:
        DISPATCHER.submit(
            method="POST",
            url=f"{BASE_URL}/api/inputs/{input_num}",
            json_data={"value": value},
        )
        status = "ON" if value else "OFF"
        print(f"  {label} = {status}")
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {e}")

    time.sleep(delay)


def set_klaar_geweeg():
    """Trigger KLAAR_GEWEEG via API."""
    try:
        DISPATCHER.submit(method="POST", url=f"{MAIN_URL}/tipbins")
        print("  KLAAR_GEWEEG triggered")
    except:
        pass


def simulate_c3_to_c2_cycle(delay: float):
    """Simulate a bin moving from C3 to C2."""
    print("\n=== C3 → C2 Cycle ===")

    # Initial: bin on C3, nothing on C2
    set_input('S1', False, delay)  # Bin on C3 (S1=False means bin present)
    set_input('S2', True, delay)   # No bin on C2

    # Wait a bit (simulating 30s delay in fast mode)
    time.sleep(delay * 3)

    # Bin moves: leaves C3, arrives at C2
    set_input('S1', True, delay)   # Bin left C3
    set_input('S2', False, delay)  # Bin arrived at C2

    print("  Cycle complete")


def simulate_c2_to_palm_cycle(delay: float):
    """Simulate a bin moving from C2 to PALM."""
    print("\n=== C2 → PALM Cycle ===")

    # Initial: bin on C2, PALM ready
    set_input('S1', True, delay)   # No bin on C3
    set_input('S2', False, delay)  # Bin on C2
    set_input('PALM_Run_Signal', True, delay)  # PALM ready

    # Wait long enough to satisfy PALM 2s hold rule
    time.sleep(max(delay * 5, PALM_HOLD_SECONDS))

    # Trigger move
    set_klaar_geweeg()
    time.sleep(delay * 2)

    # Bin leaves C2
    set_input('S2', True, delay)   # Bin left C2

    print("  Cycle complete")


def simulate_both_bins_cycle(delay: float):
    """Simulate both bins moving simultaneously."""
    print("\n=== Both Bins Cycle ===")

    # Initial: bins on both C3 and C2
    set_input('S1', False, delay)  # Bin on C3
    set_input('S2', False, delay)  # Bin on C2
    set_input('PALM_Run_Signal', True, delay)

    # Wait long enough to satisfy PALM 2s hold rule
    time.sleep(max(delay * 5, PALM_HOLD_SECONDS))

    # Trigger move
    set_klaar_geweeg()
    time.sleep(delay * 3)

    # Bins move
    set_input('S1', True, delay)   # C3 bin left
    set_input('S2', True, delay)   # C2 bin left

    # C3 bin arrives at C2
    time.sleep(delay * 2)
    set_input('S2', False, delay)

    print("  Cycle complete")


def simulate_estop(delay: float):
    """Simulate E-Stop press, hold, release, and recovery."""
    print("\n=== E-Stop Event ===")

    # E-Stop pressed (active low - False means pressed)
    set_input('E_Stop', False, delay)
    print("  E-Stop PRESSED - waiting...")
    # Hold long enough to satisfy 1s debounce in EmergencyStopRule
    time.sleep(max(delay * 5, SAFETY_HOLD_SECONDS))

    # Release E-Stop
    set_input('E_Stop', True, delay)
    print("  E-Stop released")

    # Recovery sequence: cycle Auto switch off then on
    print("  Recovery: cycling Auto switch...")
    set_input('Auto_Select', False, delay)
    set_input('Manual_Select', True, delay * 2)
    set_input('Manual_Select', False, delay)
    set_input('Auto_Select', True, delay)

    # Press Reset button
    print("  Pressing Reset...")
    set_input('Reset_Btn', True, delay)
    time.sleep(delay * 2)
    set_input('Reset_Btn', False, delay)

    print("  E-Stop recovery complete")


def simulate_mode_switch(delay: float):
    """Simulate Auto/Manual mode switch."""
    print("\n=== Mode Switch ===")
    set_input('Auto_Select', False, delay)
    set_input('Manual_Select', True, delay * 2)
    set_input('Manual_Select', False, delay)
    set_input('Auto_Select', True, delay)
    print("  Back to Auto")


def simulate_motor_trip(delay: float):
    """Simulate motor trip and recovery."""
    print("\n=== Motor Trip Event ===")

    # Motor 1 trips (active low - False means tripped)
    set_input('M1_Trip', False, delay)
    print("  M1 TRIPPED - waiting...")
    # Hold long enough to satisfy 1s debounce in ClearReadyRule
    time.sleep(max(delay * 5, SAFETY_HOLD_SECONDS))

    # Clear the trip
    set_input('M1_Trip', True, delay)
    print("  M1 trip cleared")

    # Recovery: cycle mode switch and reset
    print("  Recovery sequence...")
    set_input('Auto_Select', False, delay)
    set_input('Manual_Select', True, delay)
    set_input('Manual_Select', False, delay)
    set_input('Auto_Select', True, delay)

    set_input('Reset_Btn', True, delay)
    time.sleep(delay)
    set_input('Reset_Btn', False, delay)

    print("  Motor trip recovery complete")


def run_flood(cycles: int, delay: float):
    """Run rapid simulation cycles."""
    print(f"Starting flood test: {cycles} cycles, {delay}s delay between events")
    print(f"Mock control: {BASE_URL}")
    print(f"Main dashboard: {MAIN_URL}")

    # Check connection
    try:
        requests.get(f"{BASE_URL}/api/inputs", timeout=2)
    except:
        print("\nERROR: Cannot connect to mock control server on port 7682")
        print("Make sure you're running: python main.py --mock --view web")
        sys.exit(1)

    # Setup initial state
    print("\n=== Initial Setup ===")
    set_input('Auto_Select', True, delay)
    set_input('Manual_Select', False, delay)
    set_input('E_Stop', True, delay)      # E-Stop not pressed
    set_input('M1_Trip', True, delay)     # No trip
    set_input('M2_Trip', True, delay)     # No trip
    set_input('DHLM_Trip_Signal', True, delay)
    set_input('CPS_1', True, delay)       # Crates positioned
    set_input('CPS_2', True, delay)
    set_input('PALM_Run_Signal', True, delay)

    # Set VERSION register so comms look healthy
    try:
        requests.post(f"{BASE_URL}/api/registers/version", json={"value": 1234}, timeout=1)
        print("  VERSION = 1234")
    except:
        pass

    start_time = time.time()

    # Plan sparse E-Stop injections: about cycles / ESTOP_DIVISOR, spread across the run
    estop_count = cycles // ESTOP_DIVISOR
    if cycles >= ESTOP_MIN_CYCLES:
        estop_count = max(1, estop_count)
    estop_cycles = set()
    if estop_count > 0:
        step = cycles / (estop_count + 1)
        for n in range(estop_count):
            idx = int(round((n + 1) * step)) - 1
            idx = max(1, min(cycles - 1, idx))
            estop_cycles.add(idx)

    if estop_count > 0:
        print(f"Planned E-Stop events: {estop_count} (~1 per {ESTOP_DIVISOR} cycles)")
    else:
        print(f"Planned E-Stop events: 0 (need >= {ESTOP_MIN_CYCLES} cycles for automatic E-Stop)")

    for i in range(cycles):
        print(f"\n{'='*40}")
        print(f"CYCLE {i+1}/{cycles}")
        print('='*40)

        # Use E-Stop sparingly to keep turbo runs realistic and fast
        if i in estop_cycles:
            simulate_estop(delay)
            if DISPATCHER.pending() > 500:
                DISPATCHER.flush()
            continue

        # Mix of non-E-Stop scenarios
        scenario = i % 5

        if scenario == 0:
            simulate_c3_to_c2_cycle(delay)
        elif scenario == 1:
            simulate_c2_to_palm_cycle(delay)
        elif scenario == 2:
            simulate_both_bins_cycle(delay)
        elif scenario == 3:
            simulate_mode_switch(delay)
        elif scenario == 4:
            simulate_motor_trip(delay)

        # Backpressure: if queue grows too much, let sender catch up
        if DISPATCHER.pending() > 500:
            DISPATCHER.flush()

    elapsed = time.time() - start_time
    print(f"\n{'='*40}")
    print(f"FLOOD COMPLETE")
    print(f"  Cycles: {cycles}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Rate: {cycles/elapsed:.1f} cycles/sec")
    print('='*40)


def main():
    parser = argparse.ArgumentParser(description='Flood mock with realistic events')
    parser.add_argument('--cycles', type=int, default=10, help='Number of cycles (default: 10)')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between events in seconds (default: 0.5)')
    parser.add_argument('--fast', action='store_true', help='Fast mode (0.1s delay)')
    parser.add_argument('--turbo', action='store_true', help='Turbo mode (0.02s delay)')
    args = parser.parse_args()

    delay = args.delay
    if args.fast:
        delay = 0.1
    if args.turbo:
        delay = 0.02

    try:
        run_flood(args.cycles, delay)
    finally:
        DISPATCHER.close()


if __name__ == '__main__':
    main()
