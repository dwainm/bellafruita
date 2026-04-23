# Motor Stop Investigation Report

**Date:** 2026-04-23  
**Issue:** Motors not stopping during MOVING_BOTH mode in some cases

## Summary

Investigated 70,591 log entries spanning Jan 9-17, 2026. Identified 6 anomaly sessions where motors did not stop automatically and required manual intervention.

## Findings

### Data Analysis

| Metric | Normal Sessions | Anomaly Sessions |
|--------|-----------------|------------------|
| Count | 174 | 6 |
| MOTOR_3 runtime | ~8.6 sec | ~13-14 sec |
| Completion message | Yes | No |
| MANUAL triggered | No | Yes (operator intervention) |

### Root Cause

Comparing I/O log timing between normal and anomaly sessions:

**Normal session (e.g., session 1):**
```
07:05:35.313 - CS3=True
07:05:35.465 - S1=True          <- logged on its own line (152ms gap)
07:05:36.041 - Completed
```

**Anomaly session (e.g., session 175):**
```
07:07:14.509 - CS3=True
07:07:20.766 - S1=True, S2=False, Manual_Select=True, MOTOR_2=False, MOTOR_3=False...
              ^-- 6+ second gap, then everything logged at once
```

### Key Observation

In anomaly sessions, there is a **6-second gap** where no I/O changes are logged. When logging resumes, multiple state changes appear on the same line - including `S1=True`, `S2=False`, and `Manual_Select=True`.

The completion rule requires `S1=True AND S2=False AND mode=MOVING_BOTH`. By the time these values are logged, `Manual_Select=True` has also been processed, switching mode to MANUAL before completion can fire.

### Completion Rule Logic

From `rules.py:681-687`:
```python
def condition(self, procon, mem):
    return (
        mem.mode() == 'MOVING_BOTH' and
        procon.get('S1') and      # C3 is empty (no bin)
        not procon.get('S2')      # C2 has bin arrived
    )
```

Video footage confirms the crate physically arrived (sensors should have triggered), but the software wasn't detecting/acting on the sensor state changes in time.

## Configuration

- **Modbus timeout:** 1.0 second (config.py)
- **Poll interval:** 100ms
- **Comms failure detection:** 10 seconds of VERSION=0

The 6-second gap cannot be explained by the 1-second timeout alone. Something else is blocking the polling loop.

## Fix Attempt

### 1. Reduced Modbus Timeout

Changed `config.py`:
```python
timeout: float = 0.3  # Was 1.0
```

Rationale: Pi is physically next to Modbus controller. Network latency should be milliseconds. Faster timeout = fail fast, retry next cycle.

### 2. Added Timing Instrumentation

Added to `src/polling_thread.py`:
- `[TIMING] Slow Modbus read: Xms` - warns if read >500ms
- `[TIMING] Read failed after Xms` - shows timing on failed reads  
- `[TIMING] Slow rule evaluation: Xms` - warns if rules >100ms
- `[TIMING] Slow poll loop: Xms` - warns if full loop >1 second

This will help diagnose the source of the 6-second gaps in future logs.

## Recommended Next Steps

1. **Deploy and monitor** - Run with new timing instrumentation to identify blocking source
2. **Consider latched approach** - If timing issues persist, implement edge-detection latches:
   - Latch on S2 falling edge (True→False)
   - Latch on S1 rising edge (False→True)
   - Complete when both latches set (more robust to timing issues)
3. **Cache last known values** - If read fails, use cached sensor values so rules can still evaluate

## Files Modified

- `config.py` - Reduced Modbus timeout from 1.0s to 0.3s
- `src/polling_thread.py` - Added timing instrumentation
