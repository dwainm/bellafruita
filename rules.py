"""Rules for Bella Fruita apple sorting machine - PLC Tipper Sequence.

Based on: Open PLC Tipper Info.pdf

LADDER LOGIC EXECUTION MODEL:
This rule system works like PLC ladder logic:

1. Rules execute SEQUENTIALLY (top to bottom, like ladder rungs)
2. Later rules can OVERRIDE earlier rules (last write wins)
3. State changes are IMMEDIATELY visible to subsequent rules
4. EMERGENCY rules are placed LAST so they always win

Example:
- Rung 1: "Start Conveyor 2 if button pressed"  → Sets CONVEYOR_2_RUN = True
- Rung 2: "Stop Conveyor 2 if S2 active"        → Can override, sets CONVEYOR_2_RUN = False
- Rung 3: "E-Stop pressed"                      → ALWAYS WINS, stops everything

This makes the logic easy to reason about and debug, just like ladder logic.
Order matters - add safety rules LAST to ensure they can override normal operation.
"""

from src.rule_engine import Rule


class CommsHealthCheckRule(Rule):
    """Check comms health using log stack - detect prolonged VERSION=0."""

    def __init__(self):
        super().__init__("Comms Health Monitor")

    def condition(self, data, state):
        # Always run this check
        return True

    def action(self, controller, state):
        """Monitor comms health and set COMMS_FAILED latch if needed."""
        # Use log manager to check if VERSION has been 0 for last 5 seconds
        comms_healthy = controller.log_manager.check_comms_health(timeout_seconds=5.0)

        if not comms_healthy and not state.get('COMMS_FAILED', False):
            # Comms have failed - latch the failure state
            state['COMMS_FAILED'] = True
            controller.log_manager.critical("Communications FAILED - VERSION=0 for 5+ seconds. Reset required!")
            # Stop all motors for safety
            controller.emergency_stop_all_motors()


class CommsResetRule(Rule):
    """Reset COMMS_FAILED latch when reset button pressed."""

    def __init__(self):
        super().__init__("Comms Reset")

    def condition(self, data, state):
        # Check if reset triggered (Auto_Select switched to manual) and comms currently failed
        return (
            state.get('COMMS_FAILED', False) and
            data.falling_edge('Auto_Select')  # Detect switch to manual (reset position)
        )

    def action(self, controller, state):
        """Clear COMMS_FAILED if comms are now healthy."""
        # Verify comms are actually healthy before allowing reset
        comms_healthy = controller.log_manager.check_comms_health(timeout_seconds=5.0)

        if comms_healthy:
            state['COMMS_FAILED'] = False
            controller.log_manager.info("Communications RESET - system can now restart")
        else:
            controller.log_manager.warning("Reset attempted but communications still unhealthy")


class ReadyRule(Rule):
    """Set READY state when all safety conditions are met."""

    def __init__(self):
        super().__init__("System Ready Check")

    def condition(self, data, state):
        """Check if all conditions for READY are met and we're in ERROR state."""
        safety_ok = (
            data.get('Auto_Select') and
            not state.get('COMMS_FAILED') and  # Cannot be READY if comms failed
            not state.get('E_STOP_TRIGGERED') and  # Cannot be READY until E_Stop reset
            data.get('M1_Trip') and  # Trip signals are normally closed (FALSE = TRIPPED, TRUE = ok)
            data.get('M2_Trip') and
            data.get('DHLM_Trip_Signal') and
            data.get('E_Stop')  # E_Stop TRUE = not pressed
        )
        # Only transition to READY from ERROR or uninitialized state, don't override MOVING states
        current_mode = state.get('OPERATION_MODE')
        return safety_ok and (current_mode == 'ERROR' or current_mode is None)

    def action(self, controller, state):
        """Set OPERATION_MODE to READY state."""
        state['OPERATION_MODE'] = 'READY'
        controller.log_manager.info("System is READY")
        controller.procon.set('output', 'MOTOR_2', False)
        controller.procon.set('output', 'MOTOR_3', False)
        controller.log_manager.info("READY: Motors OFF ")


class ClearReadyRule(Rule):
    """Clear READY state when conditions are no longer met."""

    def __init__(self):
        super().__init__("Clear Ready State")

    def condition(self, data, state):
        """Check if OPERATION_MODE should be set to ERROR - overrides any state."""
        safety_violated = (
            not data.get('Auto_Select') or
            state.get('COMMS_FAILED') or
            state.get('E_STOP_TRIGGERED') or
            not data.get('M1_Trip') or
            not data.get('M2_Trip') or
            not data.get('DHLM_Trip_Signal') or
            not data.get('E_Stop')
        )
        return safety_violated and state.get('OPERATION_MODE') != 'ERROR'

    def action(self, controller, state):
        """Set OPERATION_MODE to ERROR and stop motors."""
        state['OPERATION_MODE'] = 'ERROR'
        controller.procon.set('output', 'MOTOR_2', False)
        controller.procon.set('output', 'MOTOR_3', False)
        controller.log_manager.warning("Safety violated - OPERATION_MODE set to ERROR")


class InitiateMoveC3toC2(Rule):
    """Start C3→C2 move: single bin from C3 to C2 after 30s delay."""

    def __init__(self):
        super().__init__("Initiate Move C3→C2")

    def condition(self, data, state):
        """Check if C3→C2 move should start."""
        return (
            state.get('OPERATION_MODE') == 'READY' and
            data.get('S1') and  # Bin present on C3
            not data.get('S2')  # No bin on C2
        )

    def action(self, controller, state):
        """Set state to MOVING_C3_TO_C2 and schedule motors to start in 30s."""
        from threading import Timer

        # Immediately transition to MOVING state
        state['OPERATION_MODE'] = 'MOVING_C3_TO_C2'
        controller.log_manager.info("Entering MOVING_C3_TO_C2 - motors will start in 30 seconds")

        # Delayed motor start (30 seconds)
        def start_motors():
            # Check emergency conditions before starting
            if not state.get('E_STOP_TRIGGERED') and not state.get('COMMS_FAILED'):
                controller.procon.set('output', 'MOTOR_2', True)
                controller.procon.set('output', 'MOTOR_3', True)
                controller.log_manager.info("MOVING_C3_TO_C2: Motors started after 30s delay")

        Timer(30.0, start_motors).start()


class CompleteMoveC3toC2(Rule):
    """Complete C3→C2 move when bin reaches C2."""

    def __init__(self):
        super().__init__("Complete Move C3→C2")

    def condition(self, data, state):
        """Check if C3→C2 move is complete."""
        return (
            state.get('OPERATION_MODE') == 'MOVING_C3_TO_C2' and
            data.get('S2')  # Bin detected on C2
        )

    def action(self, controller, state):
        """Stop both motors and return to READY."""
        controller.procon.set('output', 'MOTOR_2', False)
        controller.procon.set('output', 'MOTOR_3', False)
        state['OPERATION_MODE'] = 'READY'
        controller.log_manager.info("Completed MOVING_C3_TO_C2 - both motors stopped, returning to READY")


class InitiateMoveC2toPalm(Rule):
    """Start C2→PALM move: single bin from C2 to PALM."""

    def __init__(self):
        super().__init__("Initiate Move C2→PALM")

    def condition(self, data, state):
        """Check if C2→PALM move should start."""
        return (
            state.get('OPERATION_MODE') == 'READY' and
            not data.get('S1') and  # No bin on C3
            data.get('S2') and  # Bin present on C2
            data.rising_edge('Klaar_Geweeg_Btn') and  # Button press detected (edge)
            data.get('PALM_Run_Signal')  # PALM ready
        )

    def action(self, controller, state):
        """Start MOTOR_2 and set state to MOVING_C2_TO_PALM."""
        if not state.get('E_STOP_TRIGGERED') and not state.get('COMMS_FAILED'):
            controller.procon.set('output', 'MOTOR_2', True)
            state['OPERATION_MODE'] = 'MOVING_C2_TO_PALM'
            controller.log_manager.info("Started MOVING_C2_TO_PALM - MOTOR_2 running")


class CompleteMoveC2toPalm(Rule):
    """Complete C2→PALM move when bin leaves C2."""

    def __init__(self):
        super().__init__("Complete Move C2→PALM")

    def condition(self, data, state):
        """Check if C2→PALM move is complete."""
        return (
            state.get('OPERATION_MODE') == 'MOVING_C2_TO_PALM' and
            not data.get('S2')  # Bin left C2
        )

    def action(self, controller, state):
        """Stop MOTOR_2 and return to READY."""
        controller.procon.set('output', 'MOTOR_2', False)
        state['OPERATION_MODE'] = 'READY'
        controller.log_manager.info("Completed MOVING_C2_TO_PALM - MOTOR_2 stopped, returning to READY")


class InitiateMoveBoth(Rule):
    """Start moving both bins simultaneously."""

    def __init__(self):
        super().__init__("Initiate Move Both")

    def condition(self, data, state):
        """Check if both bins move should start."""
        return (
            state.get('OPERATION_MODE') == 'READY' and
            data.get('S1') and  # Bin present on C3
            data.get('S2') and  # Bin present on C2
            data.rising_edge('Klaar_Geweeg_Btn') and  # Button press detected (edge)
            data.get('PALM_Run_Signal')  # PALM ready
        )

    def action(self, controller, state):
        """Start both motors and set state to MOVING_BOTH."""
        if not state.get('E_STOP_TRIGGERED') and not state.get('COMMS_FAILED'):
            controller.procon.set('output', 'MOTOR_2', True)
            controller.procon.set('output', 'MOTOR_3', True)
            state['OPERATION_MODE'] = 'MOVING_BOTH'
            controller.log_manager.info("Started MOVING_BOTH - both motors running")


class CompleteMoveBoth(Rule):
    """Complete moving both bins with delayed MOTOR_2 stop."""

    def __init__(self):
        super().__init__("Complete Move Both")

    def condition(self, data, state):
        """Check if both bins move is complete."""
        return (
            state.get('OPERATION_MODE') == 'MOVING_BOTH' and
            not data.get('S2')  # Bin left C2
        )

    def action(self, controller, state):
        """Stop MOTOR_3 immediately, delay MOTOR_2 stop by 2s."""
        from threading import Timer

        # Stop MOTOR_3 immediately
        controller.procon.set('output', 'MOTOR_3', False)

        # Delayed stop for MOTOR_2 (2 seconds)
        def stop_motor_2():
            controller.procon.set('output', 'MOTOR_2', False)
            controller.log_manager.info("MOTOR_2 stopped after 2s delay")

        Timer(2.0, stop_motor_2).start()

        state['OPERATION_MODE'] = 'READY'
        controller.log_manager.info("Completed MOVING_BOTH - MOTOR_3 stopped, MOTOR_2 will stop in 2s, returning to READY")


class EmergencyStopRule(Rule):
    """Emergency stop all motors when E_Stop is pressed."""

    def __init__(self):
        super().__init__("Emergency Stop")

    def condition(self, data, state):
        """Check if emergency stop button is pressed."""
        return not data.get('E_Stop')

    def action(self, controller, state):
        """Stop all motors and set OPERATION_MODE to ERROR."""
        controller.emergency_stop_all_motors()
        # Clear all state except the E_STOP_TRIGGERED latch
        state.clear()
        state['E_STOP_TRIGGERED'] = True
        state['OPERATION_MODE'] = 'ERROR'
        controller.log_manager.critical("EMERGENCY STOP activated! Reset required to restart.")


class TestKlaarGeweeButtonEdge(Rule):
    """Test rule: Set state when Klaar_Geweeg button pressed."""

    def __init__(self):
        super().__init__("Test Klaar Geweeg Button Edge")

    def condition(self, data, state):
        """Detect button press."""
        return data.rising_edge('Klaar_Geweeg_Btn')

    def action(self, controller, state):
        """Set test state value."""
        state['TEST_KLAAR_GEWEEG_PRESSED'] = True
        controller.log_manager.info("TEST: Klaar_Geweeg_Btn rising edge detected!")


class TestAutoSelectEdge(Rule):
    """Test rule: Set state when Auto_Select switched off (falling edge)."""

    def __init__(self):
        super().__init__("Test Auto Select Edge")

    def condition(self, data, state):
        """Detect auto select switch turned off."""
        return data.falling_edge('Auto_Select')

    def action(self, controller, state):
        """Set test state value."""
        state['TEST_AUTO_SELECT_OFF'] = True
        controller.log_manager.info("TEST: Auto_Select falling edge detected (turned OFF)!")


class TestClearKlaarGeweeButton(Rule):
    """Test rule: Clear state when no button edge detected."""

    def __init__(self):
        super().__init__("Test Clear Klaar Geweeg Button")

    def condition(self, data, state):
        """Clear if no edge and state is set."""
        return (
            state.get('TEST_KLAAR_GEWEEG_PRESSED', False) and
            not data.rising_edge('Klaar_Geweeg_Btn')
        )

    def action(self, controller, state):
        """Clear test state value."""
        state.pop('TEST_KLAAR_GEWEEG_PRESSED', None)
        controller.log_manager.info("TEST: Cleared Klaar_Geweeg_Btn state")


class TestClearAutoSelect(Rule):
    """Test rule: Clear state when no auto select falling edge detected."""

    def __init__(self):
        super().__init__("Test Clear Auto Select")

    def condition(self, data, state):
        """Clear if no edge and state is set."""
        return (
            state.get('TEST_AUTO_SELECT_OFF', False) and
            not data.falling_edge('Auto_Select')
        )

    def action(self, controller, state):
        """Clear test state value."""
        state.pop('TEST_AUTO_SELECT_OFF', None)
        controller.log_manager.info("TEST: Cleared Auto_Select state")


class EmergencyStopResetRule(Rule):
    """Reset E_STOP latch when reset button pressed and E_Stop released."""

    def __init__(self):
        super().__init__("Emergency Stop Reset")

    def condition(self, data, state):
        """Check if reset triggered (Auto_Select switched to manual) and E_Stop released."""
        return (
            state.get('E_STOP_TRIGGERED') and
            data.get('E_Stop') and  # E_Stop must be released
            data.falling_edge('Auto_Select')  # Detect switch to manual (reset position)
        )

    def action(self, controller, state):
        """Clear E_STOP_TRIGGERED latch."""
        state['E_STOP_TRIGGERED'] = False
        controller.log_manager.info("Emergency stop RESET - system can now restart")


# Function to create all rules and add to engine
def setup_rules(rule_engine):
    """Add all rules to the rule engine.

    LADDER LOGIC ORDER (like PLC rungs):
    1. Test/Debug rules (edge detection tests)
    2. Comms monitoring and reset logic
    3. System ready checks and OPERATION_MODE management
    4. Normal operation (state machine transitions)
    5. EMERGENCY OVERRIDES (E-Stop, comms failure) - ALWAYS LAST

    Args:
        rule_engine: RuleEngine instance
    """
    # ===== SECTION 0: Test/Debug Rules =====
    # Uncomment these to test edge detection
    # rule_engine.add_rule(TestKlaarGeweeButtonEdge())   # Test button edge detection
    # rule_engine.add_rule(TestAutoSelectEdge())         # Test auto select edge detection
    # rule_engine.add_rule(TestClearKlaarGeweeButton())  # Clear button test state
    # rule_engine.add_rule(TestClearAutoSelect())        # Clear auto select test state

    # ===== SECTION 1: Communications Monitoring =====
    rule_engine.add_rule(CommsHealthCheckRule())       # Monitor comms health continuously
    rule_engine.add_rule(CommsResetRule())             # Allow reset after comms failure

    # ===== SECTION 2: System Ready State Management =====
    rule_engine.add_rule(ReadyRule())                  # Set OPERATION_MODE='READY' when conditions met
    rule_engine.add_rule(ClearReadyRule())             # Set OPERATION_MODE='ERROR' when conditions lost

    # ===== SECTION 3: State Machine Operations =====
    # C3→C2 operation (single bin from C3 to C2)
    rule_engine.add_rule(InitiateMoveC3toC2())         # Start C3→C2 move with 30s delay
    rule_engine.add_rule(CompleteMoveC3toC2())         # Complete when S2 becomes true

    # C2→PALM operation (single bin from C2 to PALM)
    rule_engine.add_rule(InitiateMoveC2toPalm())       # Start C2→PALM move on button
    rule_engine.add_rule(CompleteMoveC2toPalm())       # Complete when S2 becomes false

    # Both bins operation (C3→C2 and C2→PALM simultaneously)
    rule_engine.add_rule(InitiateMoveBoth())           # Start both bins move on button
    rule_engine.add_rule(CompleteMoveBoth())           # Complete with 2s delay for MOTOR_2

    # ===== SECTION 4: EMERGENCY OVERRIDES (ALWAYS EXECUTE LAST) =====
    # These rules execute last and can override all previous rules
    rule_engine.add_rule(EmergencyStopRule())          # E-Stop stops everything, sets OPERATION_MODE='ERROR'
    rule_engine.add_rule(EmergencyStopResetRule())     # Allow reset after emergency
