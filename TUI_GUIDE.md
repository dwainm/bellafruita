# Bella Fruita TUI Guide

## Overview

The TUI (Terminal User Interface) is built with **Textual**, a Python framework for building rich terminal applications. It provides real-time monitoring and control of the Modbus system.

## How the TUI Works

### 1. **Application Structure**

```
ModbusTUI (Main App)
├── CommsStatusWidget      - Shows connection status & retry button
├── Inputs Section         - 16 input switches in 2 columns
├── Register Section       - Version register display/input
├── HeartbeatWidget       - INPUT/OUTPUT pulse indicators
└── LogDisplayWidget      - Scrollable colored logs
```

### 2. **Key Components**

#### **CommsStatusWidget** (`src/tui.py:52-79`)
- **Purpose**: Shows if comms are alive or dead
- **States**:
  - Connected: `[✓ CONNECTED]` (green background)
  - Dead: `[⚠️ COMMUNICATIONS FAILED - MOTORS STOPPED]` (yellow/red)
- **Retry Button**: Appears when comms fail, calls `controller.retry_connection()`
- **How it updates**:
  - `poll_and_update()` checks `controller.comms_dead` every 200ms
  - Calls `comms_status_widget.set_status(dead)` to update display

#### **InputControl** (`src/tui.py:10-49`)
- **Purpose**: Single input widget (switch or read-only indicator)
- **Mock Mode**: Shows interactive `Switch` widget
- **Live Mode**: Shows `●` (active) or `○` (inactive) indicator
- **Reactive**: `state` property automatically updates display when changed

#### **HeartbeatWidget** (`src/tui.py:82-118`)
- **Purpose**: Visual pulse showing polling is active
- **Indicators**: `INPUT: ●` and `OUTPUT: ●`
- **How it works**:
  1. Every poll, `pulse_input()` and `pulse_output()` turn indicators to `●`
  2. After 250ms, `reset_pulses()` turns them back to `○`
  3. Creates a blinking effect at poll rate

#### **LogDisplayWidget** (`src/tui.py:121-196`)
- **Purpose**: Shows recent Modbus poll results with colors
- **Format**:
  ```
  [12:34:56.789] INPUT:
    [S1] [S2] [CS1] ... (green=active, red=inactive)

  [12:34:56.790] OUTPUT:
    [M1] [M2] [REG0=12345] (green=true/non-zero, red=false/zero)
  ```
- **Updates**: Every 3 seconds (configurable via `TUI_LOG_REFRESH_RATE`)
- **Rich Markup**: Uses Textual's Rich markup for colored backgrounds:
  - `[black on green] label [/black on green]` = green block
  - `[white on red] label [/white on red]` = red block

### 3. **Update Loops**

The TUI runs **3 independent timers** (set in `on_mount()`):

#### **Fast Poll Loop** (200ms - `TUI_POLL_RATE`)
```python
def poll_and_update(self):
    # 1. Read all inputs → log them → pulse INPUT heartbeat
    input_data = controller.read_and_log_all_inputs()
    heartbeat_widget.pulse_input()

    # 2. Read all outputs → log them → pulse OUTPUT heartbeat
    output_data = controller.read_and_log_all_outputs()
    heartbeat_widget.pulse_output()

    # 3. Check comms health (auto-stops motors if dead)
    controller.check_and_handle_comms_failure()

    # 4. Update comms status banner
    comms_status_widget.set_status(controller.comms_dead)

    # 5. Update input widget states
    for i in range(1, 17):
        input_widgets[i].state = input_data[labels[i]]

    # 6. Update register display
    holding_register_0 = output_data['REG0']
```

#### **Log Display Loop** (3 seconds - `TUI_LOG_REFRESH_RATE`)
```python
def update_log_display(self):
    # Get recent logs from stacks (3000 deep)
    input_logs = controller.log_manager.get_recent_input_logs(count=5)
    output_logs = controller.log_manager.get_recent_output_logs(count=5)

    # Update log widget with formatted, colored text
    log_widget.update_logs(input_logs, output_logs)
```

#### **Heartbeat Reset Loop** (250ms - `TUI_HEARTBEAT_RESET_RATE`)
```python
def reset_heartbeat(self):
    # Turn both indicators off (creates blink effect)
    heartbeat_widget.reset_pulses()
```

### 4. **Event Handlers**

#### **Switch Toggle** (Mock Mode Only)
```python
@on(Switch.Changed)
def on_switch_changed_event(self, event: Switch.Changed):
    # When user toggles a switch, update mock input state
    input_num = extract_from_id(event.switch.id)
    controller.input_client.set_input_state(input_num, event.value)
```

#### **Register Input** (Mock Mode Only)
```python
@on(Input.Submitted, "#register_0_input")
def on_register_input_submitted(self, event: Input.Submitted):
    # When user submits register value, write to mock
    value = int(event.value)
    controller.output_client.write_register(0, value)
```

#### **Retry Button**
```python
@on(Button.Pressed, "#retry_button")
def on_retry_button_pressed(self, event: Button.Pressed):
    # Attempt to reconnect
    if controller.retry_connection():
        comms_status_widget.set_status(False)  # Hide warning
```

### 5. **Data Flow**

```
┌──────────────────────────────────────────────────────────┐
│ Fast Poll Loop (200ms)                                   │
│                                                          │
│  1. Read Modbus Devices                                 │
│     ├─> Input Module (16 coils)                         │
│     └─> Output Module (4 coils + 1 register)            │
│                                                          │
│  2. Store in Log Stacks (deque, 3000 deep)              │
│     ├─> input_logs                                      │
│     └─> output_logs                                     │
│                                                          │
│  3. Update TUI Display                                  │
│     ├─> Input widgets (switches/indicators)             │
│     ├─> Register display                                │
│     ├─> Heartbeat pulses                                │
│     └─> Comms status banner                             │
│                                                          │
│  4. Check Comms Health                                  │
│     └─> If REG0=0 for 5s → Emergency stop motors        │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ Log Display Loop (3 seconds)                             │
│                                                          │
│  1. Fetch recent logs from stacks                       │
│  2. Format with colors (green/red blocks)               │
│  3. Update LogDisplayWidget                             │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ Heartbeat Reset Loop (250ms)                             │
│                                                          │
│  1. Turn off heartbeat indicators                       │
│     (Creates blink effect with poll loop)               │
└──────────────────────────────────────────────────────────┘
```

### 6. **Textual Framework Concepts**

#### **Reactive Properties**
```python
class Widget(Static):
    state = reactive(False)  # Property that triggers updates

    def watch_state(self, new_value):
        # Called automatically when state changes
        self.update_display()
```

#### **CSS Styling**
```python
CSS = """
    #my-widget {
        border: solid $primary;
        padding: 1;
    }
"""
```

#### **Event Decorators**
```python
@on(Button.Pressed, "#my_button")
def handle_button(self, event):
    # Automatically called when button pressed
    pass
```

#### **Composition**
```python
def compose(self):
    with Container():      # Layout container
        yield Widget1()    # Add widgets
        yield Widget2()
```

### 7. **Mock vs Live Mode**

#### **Mock Mode** (`USE_MOCK = True`)
- Inputs: Interactive switches
- Register: Editable input field
- Data source: `MockModbusClient.inputs` dict
- No network calls

#### **Live Mode** (`USE_MOCK = False`)
- Inputs: Read-only indicators (●/○)
- Register: Read-only label
- Data source: Real Modbus TCP connections
- Polls actual hardware

### 8. **Customization**

All timing and behavior is configurable via constants at the top of `main.py`:

```python
TUI_POLL_RATE = 0.2             # How often to read Modbus (seconds)
TUI_LOG_REFRESH_RATE = 3.0      # How often to update logs (seconds)
TUI_HEARTBEAT_RESET_RATE = 0.25 # Heartbeat blink rate (seconds)
LOG_STACK_SIZE = 3000           # Max log entries to keep
COMMS_TIMEOUT = 5.0             # Seconds before declaring comms dead
```

### 9. **Key Files**

- **`main.py`**: Configuration constants, ConveyorController class
- **`src/tui.py`**: All TUI widgets and display logic
- **`src/logging_system.py`**: LogManager, LogEntry, comms health check
- **`src/modbus/mock.py`**: MockModbusClient with 16 input definitions
- **`src/modbus/client.py`**: Real PyModbus wrapper

### 10. **Common Tasks**

#### Change poll rate:
```python
# In main.py, line 33
TUI_POLL_RATE = 0.5  # Slow down to 500ms
```

#### Add new input:
```python
# In src/modbus/mock.py, add to inputs dict:
17: {'label': 'NEW_INPUT', 'description': 'My new sensor', 'state': False}
```

#### Change log format:
```python
# In src/tui.py, LogDisplayWidget.update_logs()
# Modify the formatting logic (lines 125-154)
```

#### Add new widget:
```python
# 1. Create widget class in src/tui.py
# 2. Add to ModbusTUI.compose()
# 3. Update in poll_and_update() if needed
```

---

## Quick Reference

| Component | Update Rate | Purpose |
|-----------|-------------|---------|
| Input switches | 200ms | Show/control sensor states |
| Register display | 200ms | Show version number |
| Heartbeat | 200ms pulse, 250ms reset | Visual polling indicator |
| Comms status | 200ms | Connection health banner |
| Log display | 3 seconds | Recent poll history |
| Log stack | On every poll | Store last 3000 entries |

**Key Insight**: The TUI is just a display layer. The real work happens in `ConveyorController` which reads Modbus, stores logs, checks health, and controls motors. The TUI just visualizes this data.
