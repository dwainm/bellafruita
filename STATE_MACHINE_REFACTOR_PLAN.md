# OPERATION_MODE State Machine Refactor Plan

## States
- `ERROR` - Safety violated (E-Stop, comms fail, trips) - motors stopped
- `READY` - Safe and idle, waiting for operations
- `MOVING_C3_TO_C2` - Moving single bin from C3→C2
- `MOVING_C2_TO_PALM` - Moving single bin from C2→PALM
- `MOVING_BOTH` - Moving both bins simultaneously

## Sensors
- `S1=True` - Bin present on Conveyor 3
- `S2=True` - Bin present on Conveyor 2

## State Transitions

### Safety (OPERATION_MODE replaces READY boolean)
- `ReadyRule`: All safety OK → Set `OPERATION_MODE='READY'`
- `ClearReadyRule`: Safety violated → Set `OPERATION_MODE='ERROR'`, stop motors
- `EmergencyStopRule`: E-Stop → Set `OPERATION_MODE='ERROR'`, stop all

### Operations (all check `OPERATION_MODE=='READY'`)
1. **C3→C2 (single bin)**: `READY` + S1 + !S2 + 30s elapsed → `MOVING_C3_TO_C2`
2. **C2→PALM (single bin)**: `READY` + !S1 + S2 + button + PALM → `MOVING_C2_TO_PALM`
3. **Both bins**: `READY` + S1 + S2 + button + PALM → `MOVING_BOTH`

### Completion (back to READY)
1. **C3→C2 done**: `MOVING_C3_TO_C2` + S2 becomes true → Stop both motors → `READY`
2. **C2→PALM done**: `MOVING_C2_TO_PALM` + S2 becomes false → Stop MOTOR_2 → `READY`
3. **Both done**: `MOVING_BOTH` + S2 becomes false → Stop MOTOR_3 immediately, Timer(2s) stop MOTOR_2 → `READY`

## Delayed Actions (using threading.Timer)
```python
from threading import Timer

# Delayed STOP (no emergency check needed)
def stop_motor():
    controller.procon.set('output', 'MOTOR_2', False)
Timer(2.0, stop_motor).start()

# Delayed START (check emergency before executing)
def start_motor():
    if not state.get('E_STOP_TRIGGERED') and not state.get('COMMS_FAILED'):
        controller.procon.set('output', 'MOTOR_2', True)
Timer(30.0, start_motor).start()
```

## Rules Changes

### KEEP (7 rules - modify safety rules to use OPERATION_MODE)
- ✏️ `ReadyRule` - Set `OPERATION_MODE='READY'` instead of `READY=True`
- ✏️ `ClearReadyRule` - Set `OPERATION_MODE='ERROR'` instead of `READY=False`
- ✏️ `EmergencyStopRule` - Set `OPERATION_MODE='ERROR'`
- `CommsHealthCheckRule`
- `CommsResetRule`
- `EmergencyStopResetRule`
- ✏️ `Timer1StartRule` - Trigger: READY + S1 + !S2 (forklift loading C3)

### DELETE (7 rules)
- `StartConveyor2Rule`
- `StopConveyor2Rule`
- `Conveyor3StartWithTimerRule`
- `StartConveyor3Timer`
- `StopConveyor3After2seconds`
- `MoveBinFrom3to2`
- `Conveyor3DependencyRule`

### CREATE (6 new rules)
1. `InitiateMoveC3toC2` - Start C3→C2 move
2. `CompleteMoveC3toC2` - Finish C3→C2 move
3. `InitiateMoveC2toPalm` - Start C2→PALM move
4. `CompleteMoveC2toPalm` - Finish C2→PALM move
5. `InitiateMoveBoth` - Start both bins move
6. `CompleteMoveBoth` - Finish both bins (with 2s delay for MOTOR_2)

## Implementation Order
1. Add OPERATION_MODE to ReadyRule/ClearReadyRule/EmergencyStopRule
2. Modify Timer1StartRule for S1+!S2 trigger
3. Delete old 7 rules
4. Create 6 new operation rules
5. Update setup_rules() function
6. Test state transitions

## Key Design Principles
- Single source of truth: `OPERATION_MODE` (no separate READY boolean)
- All operation rules check `OPERATION_MODE=='READY'`
- Ladder logic: Later rules can override (emergency rules last)
- Simple Timer() calls in actions (no separate timer rules)
- No redundant safety checks (perfect the state machine)
