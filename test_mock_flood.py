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

BASE_URL = "http://localhost:7682"
MAIN_URL = "http://localhost:7681"


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
        resp = requests.post(
            f"{BASE_URL}/api/inputs/{input_num}",
            json={"value": value},
            timeout=1
        )
        status = "ON" if value else "OFF"
        print(f"  {label} = {status}")
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {e}")

    time.sleep(delay)


def set_klaar_geweeg():
    """Trigger KLAAR_GEWEEG via API."""
    try:
        requests.post(f"{MAIN_URL}/tipbins", timeout=1)
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

    # Wait for PALM hold time
    time.sleep(delay * 5)

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

    # Wait for PALM hold
    time.sleep(delay * 5)

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
    time.sleep(delay * 5)  # Hold for a bit

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
    time.sleep(delay * 5)

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

    for i in range(cycles):
        print(f"\n{'='*40}")
        print(f"CYCLE {i+1}/{cycles}")
        print('='*40)

        # Mix of different scenarios
        scenario = i % 6

        if scenario == 0:
            simulate_c3_to_c2_cycle(delay)
        elif scenario == 1:
            simulate_c2_to_palm_cycle(delay)
        elif scenario == 2:
            simulate_both_bins_cycle(delay)
        elif scenario == 3:
            simulate_mode_switch(delay)
        elif scenario == 4:
            simulate_estop(delay)
        elif scenario == 5:
            simulate_motor_trip(delay)

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

    run_flood(args.cycles, delay)


if __name__ == '__main__':
    main()
