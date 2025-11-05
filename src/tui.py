"""Textual TUI for monitoring and controlling Modbus system."""

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Header, Footer, Static, Switch, Input, Label
from textual.reactive import reactive
from textual import on

from io_mapping import MODBUS_MAP

# Constants for heartbeat indicators
HEARTBEAT_ACTIVE = "●"
HEARTBEAT_INACTIVE = "○"


class InputControl(Static):
    """Widget for a single input control."""

    state = reactive(False)

    def __init__(
        self,
        input_number: int,
        label: str,
        description: str,
        editable: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.input_number = input_number
        self.input_label = label
        self.description = description
        self.editable = editable
        self.switch = None
        self.state_indicator = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Horizontal(classes="input-row"):
            if self.editable:
                self.switch = Switch(value=self.state, id=f"switch_{self.input_number}")
                yield self.switch
            else:
                self.state_indicator = Label(HEARTBEAT_ACTIVE if self.state else HEARTBEAT_INACTIVE, classes="state-indicator")
                yield self.state_indicator

            yield Label(f"{self.input_label:12}", classes="input-label")
            yield Label(self.description, classes="input-description")

    def watch_state(self, new_state: bool) -> None:
        """Called when state changes."""
        if self.switch and self.editable:
            self.switch.value = new_state
        # Update the indicator if in read-only mode
        if not self.editable and self.state_indicator:
            self.state_indicator.update(HEARTBEAT_ACTIVE if new_state else HEARTBEAT_INACTIVE)


class ActiveRulesWidget(Static):
    """Widget showing active rules and system state."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rules_text = "[dim]No rules active[/dim]"

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Static(self.rules_text, id="rules_content", markup=True)

    def update_rules(self, active_rules: list, state: dict) -> None:
        """Update display with active rules and state.

        Args:
            active_rules: List of rule names currently triggered
            state: Current state dictionary
        """
        lines = []

        # Show active rules
        if active_rules:
            lines.append("[bold cyan]Active Rules:[/bold cyan]")
            for rule_name in active_rules:
                lines.append(f"  ▶ {rule_name}")
        else:
            lines.append("[dim]No rules active[/dim]")

        # Show state variables
        if state:
            lines.append("")
            lines.append("[bold yellow]State Variables:[/bold yellow]")
            for key, value in sorted(state.items()):
                # Color code boolean values
                if isinstance(value, bool):
                    color = "green" if value else "red"
                    lines.append(f"  {key}: [bold {color}]{value}[/bold {color}]")
                else:
                    lines.append(f"  {key}: {value}")

        self.rules_text = "\n".join(lines)
        rules_content = self.query_one("#rules_content", Static)
        rules_content.update(self.rules_text)


class CommsStatusWidget(Static):
    """Widget showing communication status and heartbeat indicators."""

    input_beat = reactive(False)
    output_beat = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._initialized = False
        self._status_text = None
        self._input_indicator = None
        self._output_indicator = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Horizontal(classes="comms-status-row"):
            # Status in the center
            yield Static("[dim]Waiting for connection attempt...[/dim]", id="comms_status_text", classes="comms-status-text")
            # Heartbeat indicators on the right
            yield Label("INPUT:", classes="heartbeat-label")
            yield Label(HEARTBEAT_INACTIVE, id="input_indicator", classes="heartbeat-indicator")
            yield Label("OUTPUT:", classes="heartbeat-label")
            yield Label(HEARTBEAT_INACTIVE, id="output_indicator", classes="heartbeat-indicator")

    def on_mount(self) -> None:
        """Called when widget is mounted."""
        self._status_text = self.query_one("#comms_status_text", Static)
        self._input_indicator = self.query_one("#input_indicator", Label)
        self._output_indicator = self.query_one("#output_indicator", Label)

    def watch_input_beat(self, value: bool) -> None:
        """Update input heartbeat indicator."""
        if self._input_indicator:
            self._input_indicator.update(HEARTBEAT_ACTIVE if value else HEARTBEAT_INACTIVE)

    def watch_output_beat(self, value: bool) -> None:
        """Update output heartbeat indicator."""
        if self._output_indicator:
            self._output_indicator.update(HEARTBEAT_ACTIVE if value else HEARTBEAT_INACTIVE)

    def pulse_input(self) -> None:
        """Pulse input indicator."""
        self.input_beat = True

    def pulse_output(self) -> None:
        """Pulse output indicator."""
        self.output_beat = True

    def reset_pulses(self) -> None:
        """Reset both pulses."""
        self.input_beat = False
        self.output_beat = False

    def set_status(self, dead: bool) -> None:
        """Update comms status."""
        if not self._status_text:
            return

        self._initialized = True
        if dead:
            # Reset heartbeat indicators when comms are dead
            self.reset_pulses()
            # Comms dead - show warning (operator must cycle Auto_Select switch to reset)
            self._status_text.update("[bold red on yellow] ⚠️  COMMUNICATIONS FAILED - CYCLE AUTO_SELECT SWITCH TO RESET [/bold red on yellow]")
        else:
            # Comms OK - show connected
            self._status_text.update("[bold black on green] ✓ CONNECTED [/bold black on green]")


class EventLogWidget(Static):
    """Widget showing system events with severity levels."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.event_text = ""

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Static(self.event_text, id="event_content", markup=True)

    def update_events(self, events: list, count: int = 1000) -> None:
        """Update event display with recent entries.

        Args:
            events: List of recent EventEntry objects
            count: Number of entries to display
        """
        lines = []

        # Show recent events (newest first)
        for event in reversed(events[-count:]):
            timestamp = event.get_formatted_time()

            # Color code by severity level
            if event.level == "CRITICAL":
                level_style = "[bold white on red]"
                end_style = "[/bold white on red]"
            elif event.level == "ERROR":
                level_style = "[bold red]"
                end_style = "[/bold red]"
            elif event.level == "WARNING":
                level_style = "[bold yellow]"
                end_style = "[/bold yellow]"
            else:  # INFO
                level_style = "[bold cyan]"
                end_style = "[/bold cyan]"

            lines.append(f"[dim]{timestamp}[/dim] {level_style}{event.level:8}{end_style} {event.message}")

        self.event_text = "\n".join(lines) if lines else "[dim]No events yet[/dim]"
        event_content = self.query_one("#event_content", Static)
        event_content.update(self.event_text)


class LogDisplayWidget(Static):
    """Widget showing recent log entries with colors."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log_text = ""

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Static(self.log_text, id="log_content", markup=True)

    def update_logs(self, input_logs: list, output_logs: list, count: int = 5) -> None:
        """Update log display with recent entries.

        Args:
            input_logs: List of recent input LogEntry objects
            output_logs: List of recent output LogEntry objects
            count: Number of entries to display
        """
        lines = []

        # Show recent logs (newest first)
        all_logs = []
        for log in input_logs[-count:]:
            all_logs.append(('INPUT', log))
        for log in output_logs[-count:]:
            all_logs.append(('OUTPUT', log))

        # Sort by timestamp (newest last)
        all_logs.sort(key=lambda x: x[1].timestamp)

        for device_type, log in all_logs:
            timestamp = log.get_formatted_time()
            lines.append(f"[bold][{timestamp}] {device_type}:[/bold]")

            if device_type == 'INPUT':
                # Format input data - 8 per line for readability with colored blocks
                input_items = list(log.data.items())
                for i in range(0, len(input_items), 8):
                    row = input_items[i:i+8]
                    formatted = []
                    for key, value in row:
                        if value:
                            formatted.append(f"[black on green] {key:12} [/black on green]")
                        else:
                            formatted.append(f"[white on red] {key:12} [/white on red]")
                    lines.append("  " + " ".join(formatted))

            else:  # OUTPUT
                # Format output data with colored blocks
                output_items = []
                for key, value in log.data.items():
                    if key == 'REG0':
                        # Register value
                        if value == 0:
                            output_items.append(f"[white on red] {key}={value} [/white on red]")
                        else:
                            output_items.append(f"[black on green] {key}={value} [/black on green]")
                    else:
                        # Boolean coil
                        if value:
                            output_items.append(f"[black on green] {key} [/black on green]")
                        else:
                            output_items.append(f"[white on red] {key} [/white on red]")
                lines.append("  " + " ".join(output_items))

            lines.append("")  # Blank line between entries

        self.log_text = "\n".join(lines)
        log_content = self.query_one("#log_content", Static)
        log_content.update(self.log_text)


        # Import App from Textualise
class ModbusTUI(App): 
    """Textual TUI for Modbus monitoring and control."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
        padding: 1;
    }

    .connection-status {
        text-align: center;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    #inputs-container {
        height: auto;
        border: solid $primary;
        padding: 1;
        margin-bottom: 1;
    }

    .inputs-columns {
        height: auto;
    }

    .input-column {
        width: 50%;
        height: auto;
    }

    #outputs-container {
        margin-top: 1;
        margin-bottom: 1;
        border: solid $accent;
        padding: 1;
        height: auto;
    }

    .outputs-row {
        height: auto;
    }

    .section-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .input-row {
        height: auto;
        margin-bottom: 0;
    }

    .state-indicator {
        width: 3;
        color: $success;
        text-align: center;
    }

    .input-label {
        width: 15;
        color: $text;
    }

    .input-description {
        width: auto;
        color: $text-muted;
    }

    .register-row {
        height: auto;
        margin-top: 1;
    }

    .register-label {
        width: 25;
        color: $text;
    }

    .register-label-compact {
        width: 12;
        color: $text;
    }

    .register-display-compact {
        width: 10;
        color: $success;
    }

    Input {
        width: 20;
    }

    #comms-status-container {
        height: auto;
        border: solid $error;
        padding: 1;
        margin-bottom: 1;
    }

    .comms-status-row {
        height: auto;
        align: center middle;
    }

    .comms-status-text {
        width: auto;
        text-align: center;
        margin-left: 2;
    }


    .heartbeat-label {
        color: $text;
        margin-left: 1;
    }

    .heartbeat-indicator {
        color: $warning;
        text-align: center;
        margin-right: 1;
    }

    #active-rules-container {
        height: auto;
        max-height: 15;
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
        overflow-y: auto;
    }

    #event-log-container {
        height: auto;
        max-height: 30;
        border: solid $warning;
        padding: 1;
        margin-bottom: 1;
    }

    #log-container {
        height: auto;
        max-height: 20;
        border: solid $primary;
        padding: 1;
        overflow-y: auto;
    }

    #log_content {
        height: auto;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    holding_register_0 = reactive(0)

    def __init__(
        self,
        controller,
        rule_engine=None,
        config=None,
        editable: bool = False,
        shared_state=None,
        **kwargs
    ):
        """Initialize TUI.

        Args:
            controller: ConveyorController instance
            rule_engine: RuleEngine instance (optional)
            config: Application configuration (optional)
            editable: If True, show editable controls (mock mode)
            shared_state: SystemState instance for thread-safe data sharing
        """
        super().__init__(**kwargs)
        self.controller = controller
        self.rule_engine = rule_engine
        self.config = config
        self.editable = editable
        self.shared_state = shared_state  # Thread-safe shared state
        self.input_widgets = {}
        self.output_widgets = {}
        self.register_input = None
        self.comms_status_widget = None
        self.event_widget = None
        self.active_rules_widget = None
        self.log_widget = None
        self.connected = False
        self.last_input_heartbeat = 0  # Track heartbeat changes
        self.last_output_heartbeat = 0

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        # yield Header()

        with ScrollableContainer(id="main-container"):
            # Connection status header
            # Mode indicator
            # mode = "MOCK MODE (Editable)" if self.editable else "LIVE MODE (Read-Only)"
            # yield Static(f"[bold]{mode}[/bold]", classes="section-title")

            # Comms status section (now includes heartbeat)
            with Container(id="comms-status-container"):
                self.comms_status_widget = CommsStatusWidget()
                yield self.comms_status_widget

            # Inputs section - Two columns (now includes holding registers)
            with Container(id="inputs-container"):
                yield Static("Input Coils & Registers", classes="section-title")

                with Horizontal(classes="inputs-columns"):
                    # Get all defined inputs from MODBUS_MAP (sorted by address)
                    all_inputs = sorted(MODBUS_MAP['INPUT']['coils'].items())
                    mid_point = (len(all_inputs) + 1) // 2  # Split into two columns

                    # Left column (first half of defined inputs)
                    with Vertical(classes="input-column"):
                        for address, map_info in all_inputs[:mid_point]:
                            input_number = address + 1  # Convert to 1-indexed for display
                            label = map_info.get('label', f'Input {input_number}')
                            description = map_info.get('description', '')

                            widget = InputControl(
                                input_number=input_number,
                                label=label,
                                description=description,
                                editable=self.editable
                            )
                            self.input_widgets[input_number] = widget
                            yield widget

                    # Right column (second half of defined inputs + holding register)
                    with Vertical(classes="input-column"):
                        for address, map_info in all_inputs[mid_point:]:
                            input_number = address + 1  # Convert to 1-indexed for display
                            label = map_info.get('label', f'Input {input_number}')
                            description = map_info.get('description', '')

                            widget = InputControl(
                                input_number=input_number,
                                label=label,
                                description=description,
                                editable=self.editable
                            )
                            self.input_widgets[input_number] = widget
                            yield widget

                        # Add holding register at bottom of right column
                        with Horizontal(classes="register-row"):
                            yield Label("REG0 (Ver):", classes="register-label-compact")

                            if self.editable:
                                self.register_input = Input(
                                    value=str(self.holding_register_0),
                                    placeholder="Enter value",
                                    type="integer",
                                    id="register_0_input"
                                )
                                yield self.register_input
                            else:
                                yield Label(
                                    str(self.holding_register_0),
                                    id="register_0_display",
                                    classes="register-display-compact"
                                )

            # Output Coils section (read-only display)
            with Container(id="outputs-container"):
                yield Static("Output Coils (Read-Only)", classes="section-title")

                # Get all defined outputs from MODBUS_MAP (sorted by address)
                all_outputs = sorted(MODBUS_MAP['OUTPUT']['coils'].items())

                for address, map_info in all_outputs:
                    # Use 0-indexed address directly for outputs (0, 1, 2, 3)
                    label = map_info.get('label', f'Output {address}')
                    description = map_info.get('description', '')

                    widget = InputControl(
                        input_number=address,  # Keep 0-indexed for outputs
                        label=label,
                        description=description,
                        editable=False  # Always read-only for outputs
                    )
                    # Store output widgets with 0-indexed address
                    self.output_widgets[address] = widget
                    yield widget

            # Active rules section (if rule engine provided)
            if self.rule_engine:
                with Container(id="active-rules-container"):
                    yield Static("Active Rules", classes="section-title")
                    self.active_rules_widget = ActiveRulesWidget()
                    yield self.active_rules_widget

            # System log section
            with ScrollableContainer(id="event-log-container"):
                yield Static("System Log", classes="section-title")
                self.event_widget = EventLogWidget()
                yield self.event_widget

            # Register history section (at bottom)
            with ScrollableContainer(id="log-container"):
                yield Static("Register History", classes="section-title")
                self.log_widget = LogDisplayWidget()
                yield self.log_widget

        yield Footer()

    async def on_mount(self) -> None:
        """Called when app is mounted."""
        # Use config if available, otherwise use defaults
        tui_config = self.config.tui if self.config else None
        log_refresh_rate = tui_config.log_refresh_rate if tui_config else 3.0
        render_rate = tui_config.poll_rate if tui_config else 0.1
        heartbeat_reset_rate = tui_config.heartbeat_reset_rate if tui_config else 0.25

        # Set up rendering intervals (fast, non-blocking)
        self.set_interval(log_refresh_rate, self.update_log_display)
        self.set_interval(render_rate, self.render_state)  # Render shared state
        self.set_interval(heartbeat_reset_rate, self.reset_heartbeat)

        # Attempt connection after TUI is fully loaded (0.5 second delay)
        self.set_timer(0.5, self.attempt_connection)

    def attempt_connection(self) -> None:
        """Attempt to connect to Modbus terminals."""
        # Show connecting message
        self.comms_status_widget.update("[bold cyan]Connecting to Modbus terminals...[/bold cyan]")
        self.controller.log_manager.info("Connecting to Modbus terminals...")

        self.connected = self.controller.connect()

        if self.connected:
            self.comms_status_widget.update("[bold green]✓ Connected to Modbus terminals[/bold green]")
            # Update shared state
            if self.shared_state:
                with self.shared_state.lock:
                    self.shared_state.connected = True
            # Update comms status to connected
            if self.comms_status_widget:
                self.comms_status_widget.set_status(False)
            # Hide connection status after 2 seconds
            self.set_timer(2.0, lambda: self.comms_status_widget.update(""))
        else:
            self.comms_status_widget.update("[bold red]✗ Failed to connect - Check event log[/bold red]")
            # Update shared state
            if self.shared_state:
                with self.shared_state.lock:
                    self.shared_state.connected = False
            # Set comms dead status
            if self.comms_status_widget:
                self.comms_status_widget.set_status(True)

    @on(Switch.Changed)
    def on_switch_changed_event(self, event: Switch.Changed) -> None:
        """Handle switch toggle events."""
        if self.editable and hasattr(self.controller.input_client, 'set_input_state'):
            # Extract input number from switch ID
            switch_id = event.switch.id
            if switch_id and switch_id.startswith("switch_"):
                input_num = int(switch_id.split("_")[1])
                self.controller.input_client.set_input_state(input_num, event.value)

                # Immediately evaluate rules for instant reactivity
                if self.rule_engine:
                    # Read current state from all inputs/outputs
                    input_data = self.controller.read_and_log_all_inputs()
                    output_data = self.controller.read_and_log_all_outputs()
                    sensor_data = {**input_data, **output_data}

                    # Evaluate rules immediately
                    self.rule_engine.evaluate(sensor_data)

                    # Update active rules display immediately
                    if self.active_rules_widget:
                        active_rules = self.rule_engine.get_active_rules()
                        state = self.rule_engine.get_state()
                        self.active_rules_widget.update_rules(active_rules, state)

    @on(Input.Submitted, "#register_0_input")
    def on_register_input_submitted(self, event: Input.Submitted) -> None:
        """Handle register input submission."""
        if self.editable:
            try:
                value = int(event.value)
                self.controller.output_client.write_register(0, value, device_id=1)
                self.holding_register_0 = value

                # Immediately evaluate rules for instant reactivity
                if self.rule_engine:
                    # Read current state from all inputs/outputs
                    input_data = self.controller.read_and_log_all_inputs()
                    output_data = self.controller.read_and_log_all_outputs()
                    sensor_data = {**input_data, **output_data}

                    # Evaluate rules immediately
                    self.rule_engine.evaluate(sensor_data)

                    # Update active rules display immediately
                    if self.active_rules_widget:
                        active_rules = self.rule_engine.get_active_rules()
                        state = self.rule_engine.get_state()
                        self.active_rules_widget.update_rules(active_rules, state)
            except ValueError:
                pass


    def render_state(self) -> None:
        """Render UI from shared state - NEVER BLOCKS!

        This method only reads from thread-safe shared state and updates widgets.
        All blocking I/O happens in the background polling thread.
        """
        if not self.shared_state:
            return  # No shared state, nothing to render

        # Get thread-safe snapshot of state (very fast)
        snapshot = self.shared_state.get_snapshot()

        input_data = snapshot['input_data']
        output_data = snapshot['output_data']
        comms_failed = snapshot['comms_failed']
        input_heartbeat = snapshot['input_heartbeat']
        output_heartbeat = snapshot['output_heartbeat']

        # Update comms status
        self.comms_status_widget.set_status(comms_failed)

        # Pulse heartbeat indicators if data is fresh (heartbeat changed)
        if input_heartbeat != self.last_input_heartbeat:
            self.last_input_heartbeat = input_heartbeat
            if not comms_failed:
                self.comms_status_widget.pulse_input()

        if output_heartbeat != self.last_output_heartbeat:
            self.last_output_heartbeat = output_heartbeat
            if not comms_failed:
                self.comms_status_widget.pulse_output()

        # Update input widget states
        if hasattr(self.controller.input_client, 'inputs'):
            # Mock mode - read from inputs dict (1-indexed addresses)
            for address, input_info in self.controller.input_client.inputs.items():
                if address in self.input_widgets:
                    self.input_widgets[address].state = input_info['state']
        else:
            # Real hardware - use the data we just read (label-based)
            for address, widget in self.input_widgets.items():
                # Convert address (1-indexed) to 0-indexed for MODBUS_MAP lookup
                map_address = address - 1
                from io_mapping import MODBUS_MAP
                map_info = MODBUS_MAP['INPUT']['coils'].get(map_address, {})
                label = map_info.get('label', '')
                if label:
                    widget.state = input_data.get(label, False)

        # Update output widget states (always read-only)
        for address, widget in self.output_widgets.items():
            # Address is already 0-indexed (0, 1, 2, 3)
            from io_mapping import MODBUS_MAP
            map_info = MODBUS_MAP['OUTPUT']['coils'].get(address, {})
            label = map_info.get('label', '')
            if label:
                widget.state = output_data.get(label, False)

        # Update register display
        self.holding_register_0 = output_data.get('VERSION', 0)
        if not self.editable:
            label = self.query_one("#register_0_display", Label)
            label.update(str(self.holding_register_0))

    def update_log_display(self) -> None:
        """Update log display with recent entries (called every 3 seconds)."""
        input_logs = self.controller.log_manager.get_recent_input_logs(count=5)
        output_logs = self.controller.log_manager.get_recent_output_logs(count=5)
        self.log_widget.update_logs(input_logs, output_logs, count=5)

        # Update event log
        events = self.controller.log_manager.get_recent_events(count=1000)
        self.event_widget.update_events(events, count=1000)

        # Auto-scroll to top to show newest events
        try:
            event_container = self.query_one("#event-log-container", ScrollableContainer)
            event_container.scroll_home(animate=False)
        except Exception:
            pass  # Container not ready yet

        # Update active rules display from shared state (thread-safe)
        if self.active_rules_widget and self.shared_state:
            snapshot = self.shared_state.get_snapshot()
            active_rules = snapshot['active_rules']
            state = snapshot['rule_state']
            self.active_rules_widget.update_rules(active_rules, state)

    def reset_heartbeat(self) -> None:
        """Reset heartbeat indicators."""
        self.comms_status_widget.reset_pulses()

    def watch_holding_register_0(self, new_value: int) -> None:
        """Called when holding register changes."""
        if self.register_input and self.editable:
            self.register_input.value = str(new_value)


def run_tui(controller, rule_engine=None, config=None, editable: bool = False, shared_state=None):
    """Run the Textual TUI.

    Args:
        controller: ConveyorController instance
        rule_engine: RuleEngine instance (optional)
        config: Application configuration (optional)
        editable: If True, show editable controls (mock mode)
        shared_state: SystemState instance for thread-safe data sharing
    """
    app = ModbusTUI(
        controller=controller,
        rule_engine=rule_engine,
        config=config,
        editable=editable,
        shared_state=shared_state
    )
    app.run()
