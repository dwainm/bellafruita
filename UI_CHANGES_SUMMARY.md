# UI Improvements Summary

## Changes Made

This update makes the Bella Fruita TUI more compact by consolidating UI elements:

### 1. Heartbeat Moved into CommsStatusWidget
- **Before**: Separate "Heartbeat" container with its own border and title
- **After**: Heartbeat indicators (INPUT:○ OUTPUT:○) integrated on the left side of CommsStatusWidget
- **Space saved**: ~3 lines of vertical space

### 2. Holding Register Moved into Input Coils Section  
- **Before**: Separate "Holding Registers" container with its own border and title
- **After**: Register (REG0) placed at the bottom of the right column in Input Coils section
- **Space saved**: ~3 lines of vertical space

### 3. Updated Section Title
- Changed "Input Coils" to "Input Coils & Registers" to reflect the consolidated content

## Total Space Savings
- **Removed containers**: 2 (Heartbeat + Registers)
- **Vertical lines saved**: ~6-8 lines
- **Result**: More compact, efficient UI with better use of screen real estate

## New Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ INPUT:● OUTPUT:○  ✓ CONNECTED              [Retry Connection]  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Input Coils & Registers                                         │
│                                                                 │
│ [Switch] S1        Sensor 1       [Switch] Manual_Select       │
│ [Switch] S2        Sensor 2       [Switch] Auto_Select         │
│ [Switch] CS1       Crate Sensor   [Switch] Manual_Forward      │
│ [Switch] CS2       Crate Sensor   [Switch] Manual_Reverse      │
│ [Switch] CS3       Crate Sensor   [Switch] M1_TC               │
│ [Switch] M1_Trip   Motor Trip     [Switch] M2_TC               │
│ [Switch] M2_Trip   Motor Trip     [Switch] PALM_Run            │
│ [Switch] E_Stop    Emergency      [Switch] DHLM_Trip           │
│                                   REG0 (Ver): 12345            │
└─────────────────────────────────────────────────────────────────┘

[Active Rules section]
[Register History section]  
[System Log section]
```

## Code Changes

### Modified Files
- `src/tui.py`: Main UI component file

### Key Changes

1. **CommsStatusWidget** - Added heartbeat functionality:
   - Added `input_beat` and `output_beat` reactive properties
   - Added `pulse_input()`, `pulse_output()`, and `reset_pulses()` methods
   - Integrated heartbeat indicators into the horizontal layout
   - Added CSS styling for heartbeat labels and indicators

2. **HeartbeatWidget** - Removed entirely:
   - Functionality moved to CommsStatusWidget
   - Container removed from compose() method

3. **Holding Register** - Moved into Input Coils section:
   - Removed separate register-container
   - Added register input/display to bottom of right input column
   - Added compact CSS classes: `register-label-compact`, `register-display-compact`

4. **ModbusTUI** - Updated references:
   - Removed `self.heartbeat_widget` instance variable
   - Updated `poll_and_update()` to use `self.comms_status_widget.pulse_input/output()`
   - Updated `reset_heartbeat()` to use `self.comms_status_widget.reset_pulses()`

## Benefits

✅ **More compact UI** - Removed redundant containers  
✅ **Better visibility** - Heartbeat status at top of screen in status bar  
✅ **Logical grouping** - Register with related input coils  
✅ **More space** - Additional vertical space for logs and active rules  
✅ **Cleaner appearance** - Professional, streamlined interface  

## Testing

The changes were tested in mock mode to verify:
- ✓ CommsStatusWidget correctly displays heartbeat indicators
- ✓ Heartbeat pulse and reset methods work correctly
- ✓ Register input/display appears in Input Coils section
- ✓ All 16 input widgets still function properly
- ✓ Poll and update cycles run without errors
- ✓ No breaking changes to existing functionality
