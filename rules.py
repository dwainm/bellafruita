"""Rules for Bella Fruita apple sorting machine - PLC Tipper Sequence.

Based on: Open PLC Tipper Info.pdf
Define custom automation rules here.
"""

from src.rules import Rule
import time


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
            state['COMMS_OK'] = False
            controller.log_manager.critical("Communications FAILED - VERSION=0 for 5+ seconds. Reset required!")
            # Stop all motors for safety
            controller.emergency_stop_all_motors()
        elif comms_healthy and not state.get('COMMS_FAILED', False):
            # Comms are healthy and not in failed state
            if not state.get('COMMS_OK', False):
                state['COMMS_OK'] = True
                controller.log_manager.info("Communications OK - VERSION register valid")


class CommsResetRule(Rule):
    """Reset COMMS_FAILED latch when reset button pressed."""

    def __init__(self):
        super().__init__("Comms Reset")

    def condition(self, data, state):
        # Check if reset button pressed and comms currently failed
        return (
            state.get('COMMS_FAILED', False) and
            data.get('Reset_Btn', False)
        )

    def action(self, controller, state):
        """Clear COMMS_FAILED if comms are now healthy."""
        # Verify comms are actually healthy before allowing reset
        comms_healthy = controller.log_manager.check_comms_health(timeout_seconds=5.0)

        if comms_healthy:
            state['COMMS_FAILED'] = False
            state['COMMS_OK'] = True
            controller.log_manager.info("Communications RESET - system can now restart")
        else:
            controller.log_manager.warning("Reset attempted but communications still unhealthy")


class ReadyRule(Rule):
    """Set READY state when all safety conditions are met."""

    def __init__(self):
        super().__init__("System Ready Check")

    def condition(self, data, state):
        """Check if all conditions for READY are met."""
        return (
            data.get('Auto_Select', False) and
            state.get('COMMS_OK', False) and
            not state.get('COMMS_FAILED', False) and  # Cannot be READY if comms failed
            not state.get('E_STOP_TRIGGERED', False) and  # Cannot be READY until E_Stop reset
            data.get('M1_Trip', False) and  # Trip signals are normally closed (FALSE = OK)
            data.get('M2_Trip', False) and
            data.get('DHLM_Trip_Signal', False) and
            not data.get('E_Stop', False)  # E_Stop FALSE = not pressed
        )

    def action(self, controller, state):
        """Set READY state."""
        if not state.get('READY', False):
            state['READY'] = True
            controller.log_manager.info("System is READY")


class ClearReadyRule(Rule):
    """Clear READY state when conditions are no longer met."""

    def __init__(self):
        super().__init__("Clear Ready State")

    def condition(self, data, state):
        """Check if READY should be cleared."""
        ready_conditions = (
            data.get('Auto_Select', False) and
            state.get('COMMS_OK', False) and
            not state.get('COMMS_FAILED', False) and
            not state.get('E_STOP_TRIGGERED', False) and
            data.get('M1_Trip', False) and
            data.get('M2_Trip', False) and
            data.get('DHLM_Trip_Signal', False) and
            not data.get('E_Stop', False)
        )
        return state.get('READY', False) and not ready_conditions

    def action(self, controller, state):
        """Clear READY state and stop motors."""
        state['READY'] = False
        # Comment out motor actions
        # controller.procon.set('output', 'MOTOR_2', False)
        # controller.procon.set('output', 'MOTOR_3', False)
        controller.log_manager.warning("System no longer READY - motors would stop")


class StartConveyor2Rule(Rule):
    """Start Conveyor 2 when button pressed and conditions met."""

    def __init__(self):
        super().__init__("Start Conveyor 2")

    def condition(self, data, state):
        """Check if we can start Conveyor 2."""
        return (
            state.get('READY', False) and
            data.get('PALM_Run_Signal', False) and
            not data.get('S2', False) and
            data.get('Klaar_Geweeg_Btn', False)  # Momentary button
        )

    def action(self, controller, state):
        """Start Conveyor 2."""
        # Comment out actual motor start
        # controller.procon.set('output', 'MOTOR_2', True)
        state['CONVEYOR_2_RUN'] = True
        controller.log_manager.info("Conveyor 2 START triggered (motor action commented out)")


class Timer1StartRule(Rule):
    """Start 30-second timer when READY and S1 is FALSE."""

    def __init__(self):
        super().__init__("Timer 1 Start")

    def condition(self, data, state):
        """Check if timer should start."""
        return (
            state.get('READY', False) and
            not data.get('S1', False) and
            'TIMER_1_START' not in state
        )

    def action(self, controller, state):
        """Start timer."""
        state['TIMER_1_START'] = time.time()
        controller.log_manager.info("Timer 1 started (30 seconds)")


class Conveyor3StartWithTimerRule(Rule):
    """Start Conveyor 3 when Conveyor 2 running and S2 active after timer."""

    def __init__(self):
        super().__init__("Start Conveyor 3 with Timer")

    def condition(self, data, state):
        """Check if Conveyor 3 should start."""
        timer_started = state.get('TIMER_1_START', 0)
        timer_elapsed = timer_started > 0 and (time.time() - timer_started) >= 30

        return (
            state.get('READY', False) and
            state.get('CONVEYOR_2_RUN', False) and
            data.get('S2', False) and
            timer_elapsed
        )

    def action(self, controller, state):
        """Start Conveyor 3."""
        # Comment out actual motor start
        # controller.procon.set('output', 'MOTOR_3', True)
        state['CONVEYOR_3_RUN'] = True
        controller.log_manager.info("Conveyor 3 START triggered (motor action commented out)")


class StopConveyorsOnS2FalseRule(Rule):
    """Stop both conveyors when S2 becomes FALSE."""

    def __init__(self):
        super().__init__("Stop Conveyors on S2 False")

    def condition(self, data, state):
        """Check if conveyors should stop."""
        return (
            not data.get('S2', False) and
            (state.get('CONVEYOR_2_RUN', False) or state.get('CONVEYOR_3_RUN', False))
        )

    def action(self, controller, state):
        """Stop both conveyors."""
        # Comment out actual motor stops
        # controller.procon.set('output', 'MOTOR_2', False)
        # controller.procon.set('output', 'MOTOR_3', False)
        state['CONVEYOR_2_RUN'] = False
        state['CONVEYOR_3_RUN'] = False
        state.pop('TIMER_1_START', None)  # Reset timer
        controller.log_manager.info("Conveyors 2 & 3 STOP triggered (motor actions commented out)")


class PALMChaintrackControlRule(Rule):
    """Control conveyors based on PALM Chaintrack run signal."""

    def __init__(self):
        super().__init__("PALM Chaintrack Control")

    def condition(self, data, state):
        """Check PALM run signal and S2 state."""
        palm_running = data.get('PALM_Run_Signal', False)
        s2_active = data.get('S2', False)

        # Start condition: PALM running and S2 not active
        start_condition = palm_running and not s2_active and not state.get('PALM_CONVEYOR_ACTIVE', False)

        # Stop condition: S2 becomes active while PALM conveyors running
        stop_condition = s2_active and state.get('PALM_CONVEYOR_ACTIVE', False)

        return start_condition or stop_condition

    def action(self, controller, state):
        """Start or stop conveyors based on PALM signal."""
        palm_running = controller.procon.get('input', 'PALM_Run_Signal')
        s2_active = controller.procon.get('input', 'S2')

        if palm_running and not s2_active:
            # Start conveyors
            # Comment out actual motor starts
            # controller.procon.set('output', 'MOTOR_2', True)
            # controller.procon.set('output', 'MOTOR_3', True)
            state['PALM_CONVEYOR_ACTIVE'] = True
            state['CONVEYOR_2_RUN'] = True
            state['CONVEYOR_3_RUN'] = True
            controller.log_manager.info("PALM: Conveyors 2 & 3 START (motor actions commented out)")
        elif s2_active:
            # Stop conveyors
            # Comment out actual motor stops
            # controller.procon.set('output', 'MOTOR_2', False)
            # controller.procon.set('output', 'MOTOR_3', False)
            state['PALM_CONVEYOR_ACTIVE'] = False
            state['CONVEYOR_2_RUN'] = False
            state['CONVEYOR_3_RUN'] = False
            controller.log_manager.info("PALM: Conveyors 2 & 3 STOP on S2 active (motor actions commented out)")


class Conveyor3DependencyRule(Rule):
    """Safety rule: Conveyor 3 cannot run if Conveyor 2 is not running."""

    def __init__(self):
        super().__init__("Conveyor 3 Dependency Check")

    def condition(self, data, state):
        """Check if Conveyor 3 is running without Conveyor 2."""
        return (
            state.get('CONVEYOR_3_RUN', False) and
            not state.get('CONVEYOR_2_RUN', False)
        )

    def action(self, controller, state):
        """Stop Conveyor 3 if Conveyor 2 is not running."""
        # Comment out actual motor stop
        # controller.procon.set('output', 'MOTOR_3', False)
        state['CONVEYOR_3_RUN'] = False
        controller.log_manager.warning("SAFETY: Conveyor 3 cannot run without Conveyor 2 (motor action commented out)")


class EmergencyStopRule(Rule):
    """Emergency stop all motors when E_Stop is pressed."""

    def __init__(self):
        super().__init__("Emergency Stop")

    def condition(self, data, state):
        """Check if emergency stop button is pressed."""
        return data.get('E_Stop', False) and not state.get('E_STOP_TRIGGERED', False)

    def action(self, controller, state):
        """Stop all motors and set E_STOP latch."""
        controller.emergency_stop_all_motors()
        # Clear all state except the E_STOP_TRIGGERED latch
        state.clear()
        state['E_STOP_TRIGGERED'] = True
        controller.log_manager.critical("EMERGENCY STOP activated! Reset required to restart.")


class EmergencyStopResetRule(Rule):
    """Reset E_STOP latch when reset button pressed and E_Stop released."""

    def __init__(self):
        super().__init__("Emergency Stop Reset")

    def condition(self, data, state):
        """Check if reset button pressed and E_Stop released."""
        return (
            state.get('E_STOP_TRIGGERED', False) and
            not data.get('E_Stop', False) and  # E_Stop must be released
            data.get('Reset_Btn', False)
        )

    def action(self, controller, state):
        """Clear E_STOP_TRIGGERED latch."""
        state['E_STOP_TRIGGERED'] = False
        controller.log_manager.info("Emergency stop RESET - system can now restart")


# Function to create all rules and add to engine
def setup_rules(rule_engine):
    """Add all rules to the rule engine.

    Args:
        rule_engine: RuleEngine instance
    """
    # Add rules in priority order
    rule_engine.add_rule(EmergencyStopRule())          # Highest priority - emergency stop
    rule_engine.add_rule(EmergencyStopResetRule())     # Allow reset after emergency stop
    rule_engine.add_rule(CommsHealthCheckRule())       # Monitor comms health continuously
    rule_engine.add_rule(CommsResetRule())             # Allow reset after comms failure
    rule_engine.add_rule(ReadyRule())
    rule_engine.add_rule(ClearReadyRule())
    rule_engine.add_rule(StartConveyor2Rule())
    rule_engine.add_rule(Timer1StartRule())
    rule_engine.add_rule(Conveyor3StartWithTimerRule())
    rule_engine.add_rule(StopConveyorsOnS2FalseRule())
    rule_engine.add_rule(PALMChaintrackControlRule())
    rule_engine.add_rule(Conveyor3DependencyRule())    # Safety rule
