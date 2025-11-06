"""Rule-based control system for industrial automation.

Rules can:
1. Check conditions based on sensor data and system state
2. Set state variables (e.g., mem.set('READY', True))
3. Trigger actions (e.g., turn motors on/off via procon)
4. Compose complex logic by checking state from other rules
"""

import time
from typing import Callable, Dict, Any, Optional
from src.mem import MachineMemory


class Rule:
    """Base class for automation rules.

    Create custom rules by subclassing and overriding condition() and action().

    Example:
        class ReadyRule(Rule):
            def __init__(self):
                super().__init__("System Ready Check")

            def condition(self, procon, mem):
                return procon.get('S1') and not procon.get('S2')

            def action(self, controller, procon, mem):
                mem.set_mode('READY')  # Just set state, no motor action

        class StartConveyorRule(Rule):
            def __init__(self):
                super().__init__("Start Conveyor")

            def condition(self, procon, mem):
                # Compose logic: check mode and sensor
                return mem.mode() == 'READY' and procon.get('CS1')

            def action(self, controller, procon, mem):
                procon.set('MOTOR_2', True)
                mem.set_mode('MOVING')
    """

    def __init__(self, name: str):
        """Initialize rule.

        Args:
            name: Human-readable name for this rule
        """
        self.name = name
        self.enabled = True
        self.last_triggered: Optional[float] = None
        self.trigger_count = 0

    def condition(self, procon, mem: MachineMemory) -> bool:
        """Check if rule should trigger.

        Args:
            procon: Procon API for reading I/O and edge detection
            mem: Machine memory for reading internal state

        Returns:
            True if rule should trigger, False otherwise
        """
        return False

    def action(self, controller, procon, mem: MachineMemory) -> None:
        """Execute rule action.

        Args:
            controller: ConveyorController instance
            procon: Procon API for writing outputs
            mem: Machine memory for writing internal state
        """
        pass


class RuleEngine:
    """Executes rules sequentially like PLC ladder logic.

    LADDER LOGIC BEHAVIOR:
    - Rules execute in order from first to last (top to bottom)
    - Each rule evaluates its condition, then executes its action
    - Later rules can override earlier rules (LAST WRITE WINS)
    - State changes are immediately visible to subsequent rules
    - Safety rules should be added LAST to ensure they always win

    Example execution order:
    1. Normal control rules (start conveyors, timers, etc.)
    2. Interlock rules (safety dependencies)
    3. Emergency rules (E-Stop, comms failure) - ALWAYS LAST
    """

    def __init__(self, controller):
        """Initialize rule engine.

        Args:
            controller: ConveyorController instance
        """
        self.controller = controller

        # MEMORY PERSISTENCE (Like PLC Memory):
        # MachineMemory instance created ONCE and PERSISTS across all scan cycles.
        # Rules can set values that remain until explicitly changed or cleared.
        # Examples: mem.set_mode('READY'), mem.set('TIMER_START', 1234567890)
        # Memory is NOT rebuilt each scan - only explicit clear() wipes it.
        self.mem = MachineMemory()

        self.rules: list[Rule] = []
        self.active_rules: list[str] = []  # Cleared each scan, memory is NOT

    def add_rule(self, rule: Rule) -> None:
        """Add a rule to the engine.

        IMPORTANT: Rules execute in the order they are added!
        Add safety/emergency rules LAST so they can override normal operation.

        Args:
            rule: Rule instance to add
        """
        self.rules.append(rule)
        self.controller.log_manager.info(f"Added rule: {rule.name}")

    def evaluate(self, sensor_data: Dict[str, Any]) -> None:
        """Evaluate all rules sequentially (ladder logic style).

        Executes like a PLC scan:
        1. Read inputs (via procon) - FRESH each scan
        2. Execute all rules in order (top to bottom)
        3. Later rules can override earlier rules
        4. Safety rules at the end always take precedence

        IMPORTANT - Memory Persistence:
        - procon.get(): Fresh inputs read each scan (like PLC input registers)
        - self.mem: PERSISTS across scans (like PLC memory bits)
        - Only active_rules is cleared each scan
        - Memory values remain until explicitly changed by rules or cleared

        Args:
            sensor_data: Current sensor/register readings (used to update logs)
        """
        # Clear active rules list (NOT memory - memory persists!)
        self.active_rules.clear()

        # Get procon instance from controller (already has edge detection)
        procon = self.controller.procon

        # Execute ALL rules in order (like PLC ladder rungs)
        for rule in self.rules:
            if not rule.enabled:
                continue

            try:
                # Check if rule should trigger (like ladder contacts)
                if rule.condition(procon, self.mem):
                    self.active_rules.append(rule.name)
                    rule.last_triggered = time.time()
                    rule.trigger_count += 1

                    # Execute rule action (like ladder coil)
                    rule.action(self.controller, procon, self.mem)

            except Exception as e:
                self.controller.log_manager.error(f"Error in rule '{rule.name}': {e}")

    def get_active_rules(self) -> list[str]:
        """Get list of currently triggered rule names.

        Returns:
            List of rule names that triggered in last evaluation
        """
        return self.active_rules.copy()

    def get_state(self) -> Dict[str, Any]:
        """Get copy of current memory state.

        Returns:
            Copy of memory state dictionary
        """
        return self.mem._state.copy()

    def set_state(self, key: str, value: Any) -> None:
        """Set a memory variable.

        Args:
            key: Memory variable name
            value: Value to set
        """
        self.mem.set(key, value)

    def clear_state(self) -> None:
        """Clear all memory variables.

        IMPORTANT: Memory is NOT cleared automatically each scan!
        Memory only clears when:
        1. This method is called explicitly
        2. Emergency stop rule calls mem.clear()
        3. Manual intervention via API

        Otherwise memory persists indefinitely across all scans.
        """
        self.mem.clear()

    def enable_rule(self, rule_name: str) -> None:
        """Enable a rule by name.

        Args:
            rule_name: Name of rule to enable
        """
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                self.controller.log_manager.info(f"Enabled rule: {rule_name}")
                return

    def disable_rule(self, rule_name: str) -> None:
        """Disable a rule by name.

        Args:
            rule_name: Name of rule to disable
        """
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                self.controller.log_manager.info(f"Disabled rule: {rule_name}")
                return

    def get_rule_status(self) -> list[Dict[str, Any]]:
        """Get status of all rules.

        Returns:
            List of dicts with rule info: name, enabled, trigger_count, last_triggered
        """
        return [
            {
                'name': rule.name,
                'enabled': rule.enabled,
                'trigger_count': rule.trigger_count,
                'last_triggered': rule.last_triggered
            }
            for rule in self.rules
        ]
