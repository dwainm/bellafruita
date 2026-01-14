# Bella Fruita - PLC Control System

Industrial control system for apple sorting machine. Controls bin movement between conveyors (C3→C2→PALM) via Modbus TCP to Procon terminals.

## Tech Stack
- Python 3.9+, PyModbus, Textual (TUI), FastAPI (web), Uvicorn
- Hardware: Procon Modbus PLCs, Raspberry Pi

## Project Structure
```
main.py          - Entry point, CLI args (--mock, --view tui/web/logs)
rules.py         - 21 PLC ladder-logic rules (sequential, safety rules LAST)
io_mapping.py    - Modbus address↔label mapping (16 inputs, 4 outputs)
config.py        - IPs, timeouts, settings

src/
  modbus/
    api.py       - Procon API: high-level I/O (procon.get('S1'), edge detection)
    client.py    - PyModbus TCP wrapper
    mock.py      - Hardware simulation for testing
  rule_engine.py - Evaluates rules sequentially each scan cycle
  polling_thread.py - Background: read inputs → eval rules → write outputs
  mem.py         - Internal state storage (modes, timers)
  edge_detector.py - Rising/falling edge, hold detection
  tui.py         - Textual terminal UI (live I/O, logs, mock switches)
  web_server.py  - FastAPI + WebSocket dashboard
  logging_system.py - Event logs, JSONL persistence

logs/            - Persistent JSONL event logs
static/          - Web assets
```

## Key Concepts

**Modes**: READY, MOVING_C3_TO_C2, MOVING_C2_TO_PALM, MOVING_BOTH, MANUAL, ERROR_SAFETY, ERROR_ESTOP, ERROR_COMMS, ERROR_COMMS_ACK

**I/O Labels** (io_mapping.py):
- Inputs: S1, S2 (sensors), CS1-3 (crate), M1_Trip, M2_Trip, DHLM_Trip_Signal, E_Stop, Manual_Select, Auto_Select, Reset_Btn, PALM_Run_Signal, CPS_1, CPS_2, Klaar_Geweeg_Btn
- Outputs: LED_GREEN, MOTOR_2, MOTOR_3, LED_RED

**Rules Pattern**: Each rule has `evaluate(procon, mem, io_state)` returning dict of outputs. Safety rules last = highest priority.

**Edge Detection**: `procon.rising_edge('label')`, `procon.falling_edge('label')`, `procon.extended_hold('label', seconds)`

## Running
```bash
./start.sh --mock           # Mock mode (no hardware)
./start.sh --view tui       # Terminal UI
./start.sh --view web       # Web dashboard :7681
python main.py --mock --view tui  # Direct
```

## Architecture
```
UI (TUI/Web) ← reads ← SystemState ← updates ← PollingThread
                                                    ↓
                                              RuleEngine (21 rules)
                                                    ↓
                                              Modbus (Procon API)
                                                    ↓
                                              PLC Hardware
```
