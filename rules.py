"""Rules for Bella Fruita apple sorting machine.

Define custom automation rules here.
Rules can:
- Set state variables without taking actions (e.g., state['READY'] = True)
- Check state from other rules to compose complex logic
- Trigger motor actions based on sensor combinations
"""

from src.rules import Rule


class SystemReadyRule(Rule):
    """Set READY state when sensor 1 is active and sensor 2 is inactive."""

    def __init__(self):
        super().__init__("System Ready Check")

    def condition(self, data, state):
        return data.get('S1', True) and data.get('S2', True)

    def action(self, controller, state):
        """Set READY state without motor actions."""
        if not state.get('READY', False):
            state['READY'] = True
            controller.log_manager.info("System is READY")


class ConveyorStartRule(Rule):
    """Start conveyor when system is READY and crate sensor detects a crate."""

    def __init__(self):
        super().__init__("Start Conveyor")

    def condition(self, data, state):
        """Check if READY and crate sensor CS1 is triggered."""
        # Compose logic: uses state from SystemReadyRule
        return state.get('READY', True ) and data.get('Auto_Select', True)

    def action(self, controller, state):
        """Turn on main conveyor motor and reset READY state."""
        # controller.procon.set('output', 'MOTOR_1', True)
        state['CONVEYOR_RUNNING'] = True
        controller.log_manager.info("Not really: Conveyor started")


class ConveyorStopRule(Rule):
    """Stop conveyor when emergency stop is pressed."""

    def __init__(self):
        super().__init__("Emergency Stop")

    def condition(self, data, state):
        """Check if emergency stop button is pressed."""
        return data.get('E_Stop', False)

    def action(self, controller, state):
        """Stop all motors and clear all state."""
        controller.emergency_stop_all_motors()
        state.clear()
        controller.log_manager.critical("Emergency stop activated!")


class FeederControlRule(Rule):
    """Control feeder belt based on conveyor state and crate height."""

    def __init__(self):
        super().__init__("Feeder Control")

    def condition(self, data, state):
        """Check if conveyor is running and crate is not full."""
        conveyor_running = state.get('CONVEYOR_RUNNING', False)
        crate_not_full = not data.get('CS3', False)  # CS3 = full height sensor
        return conveyor_running and crate_not_full

    def action(self, controller, state):
        """Turn on feeder motor."""
        controller.procon.set('output', 'MOTOR_2', True)


class FeederStopRule(Rule):
    """Stop feeder when crate is full."""

    def __init__(self):
        super().__init__("Stop Feeder")

    def condition(self, data, state):
        """Check if crate height sensor CS3 is triggered."""
        return data.get('CS3', False)

    def action(self, controller, state):
        """Turn off feeder motor and set CRATE_FULL state."""
        controller.procon.set('output', 'MOTOR_2', False)
        state['CRATE_FULL'] = True
        controller.log_manager.info("Crate full - feeder stopped")


class ManualModeRule(Rule):
    """Allow manual forward control when manual mode is selected."""

    def __init__(self):
        super().__init__("Manual Forward")

    def condition(self, data, state):
        """Check if manual mode selected and forward button pressed."""
        manual_mode = data.get('Manual_Select', False)
        forward_pressed = data.get('Manual_Forward', False)
        return manual_mode and forward_pressed

    def action(self, controller, state):
        """Run motor in manual mode."""
        controller.procon.set('output', 'MOTOR_1', True)
        state['MANUAL_MODE'] = True


class AutoModeResumeRule(Rule):
    """Resume automatic operation when auto mode is selected."""

    def __init__(self):
        super().__init__("Auto Mode Resume")

    def condition(self, data, state):
        """Check if auto mode selected after being in manual."""
        was_manual = state.get('MANUAL_MODE', False)
        auto_selected = data.get('Auto_Select', False)
        return was_manual and auto_selected

    def action(self, controller, state):
        """Clear manual mode state."""
        state['MANUAL_MODE'] = False
        controller.log_manager.info("Switched to automatic mode")


# Function to create all rules and add to engine
def setup_rules(rule_engine):
    """Add all rules to the rule engine.

    Args:
        rule_engine: RuleEngine instance

    Example:
        from src.rules import RuleEngine
        from rules import setup_rules

        engine = RuleEngine(controller)
        setup_rules(engine)
    """
    rule_engine.add_rule(SystemReadyRule())
    rule_engine.add_rule(ConveyorStartRule())
    # rule_engine.add_rule(ConveyorStopRule())
    # rule_engine.add_rule(FeederControlRule())
    # rule_engine.add_rule(FeederStopRule())
    # rule_engine.add_rule(ManualModeRule())
    # rule_engine.add_rule(AutoModeResumeRule())
