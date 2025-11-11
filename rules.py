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
from threading import Timer
import time


class CommsHealthCheckRule(Rule):
    """Check comms health and transition to ERROR_COMMS if failed."""

    def __init__(self):
        super().__init__("Comms Health Monitor")

    def condition(self, procon, mem):
        # Always run this check
        return True

    def action(self, controller, procon, mem):
        """Monitor comms health and set ERROR_COMMS mode if needed."""
        comms_healthy = controller.log_manager.check_comms_health(timeout_seconds=5.0)

        if not comms_healthy and mem.mode() not in ['ERROR_COMMS', 'ERROR_COMMS_ACK']:
            # Comms have failed - enter ERROR_COMMS mode
            mem.set_mode('ERROR_COMMS')
            controller.log_manager.critical("Communications FAILED - VERSION=0 for 5+ seconds. Disconnecting and attempting reconnection...")
            # Stop all motors for safety
            controller.emergency_stop_all_motors()
            # Disconnect
            controller.input_client.close()
            controller.output_client.close()
        elif comms_healthy and mem.mode() == 'ERROR_COMMS':
            # Comms have recovered! Wait for operator to acknowledge by flipping to Manual
            controller.log_manager.info_once("Communications RESTORED - VERSION heartbeat detected. Flip switch to Manual to acknowledge.")
            # Clear the reconnection message cache
            controller.log_manager.clear_logged_once(message="Attempting to reconnect and restore communications...")
        elif mem.mode() == 'ERROR_COMMS':
            # In error mode and still unhealthy, keep trying to reconnect
            controller.log_manager.info_once("Attempting to reconnect and restore communications...")

            # Try to reconnect if not already connected
            try:
                input_ok = controller.input_client.connect()
                output_ok = controller.output_client.connect()

                if input_ok and output_ok:
                    controller.log_manager.debug("Modbus clients reconnected - monitoring for VERSION heartbeat...")
            except Exception as e:
                controller.log_manager.debug(f"Reconnection attempt failed: {e}")

        # Update LED based on comms health - only write if state doesn't match
        current_led = procon.get('LED_GREEN')

        if comms_healthy and current_led != True:
            controller.log_manager.debug(f"LED_GREEN is {current_led}, turning ON (comms healthy)")
            procon.set('LED_GREEN', True)
        elif not comms_healthy and current_led != False:
            controller.log_manager.debug(f"LED_GREEN is {current_led}, turning OFF (comms unhealthy)")
            procon.set('LED_GREEN', False)

class CommsAcknowledgeRule(Rule):
    """Acknowledge comms error when operator turns Auto_Select OFF (Manual mode)."""

    def __init__(self):
        super().__init__("Comms Acknowledge")

    def condition(self, procon, mem):
        return mem.mode() == 'ERROR_COMMS' and procon.get('Manual_Select')

    def action(self, controller, procon, mem):
        """Move to acknowledged state."""
        mem.set_mode('ERROR_COMMS_ACK')
        controller.log_manager.info("Comms failure ACKNOWLEDGED - turn auto_start switch back ON to reset")


class CommsResetRule(Rule):
    """Reset comms error when operator turns Auto_Select back ON and comms are healthy."""

    def __init__(self):
        super().__init__("Comms Reset")

    def condition(self, procon, mem):
        return mem.mode() == 'ERROR_COMMS_ACK' and procon.get('Auto_Select')

    def action(self, controller, procon, mem):
        """Clear error and return to READY if comms are healthy, or back to ERROR_COMMS if not."""
        comms_healthy = controller.log_manager.check_comms_health(timeout_seconds=5.0)

        if comms_healthy:
            controller.log_manager.info("Communications RESTORED and RESET - returning to READY")
            mem.set_mode('READY')
        else:
            controller.log_manager.warning("Cannot reset - VERSION heartbeat still not detected, returning to ERROR_COMMS")
            # Go back to ERROR_COMMS to continue reconnection attempts
            mem.set_mode('ERROR_COMMS')


class ReadyRule(Rule):
    """Set READY mode when all safety conditions are met."""

    def __init__(self):
        super().__init__("System Ready Check")

    def condition(self, procon, mem):
        """Check if all conditions for READY are met.

        Trip signals must be TRUE (OK) for 1+ seconds before allowing READY.
        """
        # Immediate checks
        immediate_ok = (
            procon.get('Auto_Select') and
            procon.get('E_Stop')
        )

        # Trip signals must be held TRUE (OK) for 1+ seconds
        trips_stable = (
            procon.get('M1_Trip') and
            procon.get('M2_Trip') and
            procon.get('DHLM_Trip_Signal')
        )

        safety_ok = immediate_ok and trips_stable

        # Only transition to READY from None, OFF, or ERROR_SAFETY states
        # Don't override MOVING states or other ERROR states (they have explicit reset logic)
        # ERROR_COMMS, ERROR_COMMS_ACK, ERROR_ESTOP require explicit operator reset
        current_mode = mem.mode()
        can_transition = (
            current_mode is None or
            current_mode == 'MANUAL' or
            current_mode == 'ERROR_SAFETY'
        )

        return safety_ok and can_transition

    def action(self, controller, procon, mem):
        """Set mode to READY."""
        mem.set_mode('READY')
        procon.set('MOTOR_2', False)
        procon.set('MOTOR_3', False)
        controller.log_manager.info("System is READY and Motors are OFF")


class ManualModeRule(Rule):
    """Set mode to MANUAL when manual mode is selected."""

    def __init__(self):
        super().__init__("Manual Mode")

    def condition(self, procon, mem):
        """Check if manual mode is selected.

        Note: ERROR_COMMS_ACK is excluded - it should only transition via CommsResetRule.
        """
        return (procon.get('Manual_Select') and
                mem.mode() != 'MANUAL' and
                mem.mode() != 'ERROR_COMMS_ACK')

    def action(self, controller, procon, mem):
        """Set mode to MANUAL and stop motors."""
        procon.set('MOTOR_2', False)
        procon.set('MOTOR_3', False)
        mem.set_mode('MANUAL')


class ClearReadyRule(Rule):
    """Clear READY state when conditions are no longer met."""

    def __init__(self):
        super().__init__("Clear Ready State")

    def condition(self, procon, mem):
        """Check if mode should be set to ERROR_SAFETY due to trips.

        Uses extended_hold() for trip signals to debounce momentary glitches.
        Trip signals must be FALSE for 1+ seconds before triggering error.
        """
        # Trip signals with 1-second debounce to filter out blips
        # Only trigger if they've been FALSE (tripped) for 1+ seconds
        trip_violations = (
            procon.extended_hold('M1_Trip', False, 1.0) or
            procon.extended_hold('M2_Trip', False, 1.0) or
            procon.extended_hold('DHLM_Trip_Signal', False, 1.0)
        )

        return trip_violations and mem.mode() != 'ERROR_SAFETY'

    def action(self, controller, procon, mem):
        """Set mode to ERROR_SAFETY and stop motors."""
        # Identify which specific safety conditions are violated
        violations = []

        # Get current data
        try:
            auto_select = procon.get('Auto_Select')
            m1_trip = procon.get('M1_Trip')
            m2_trip = procon.get('M2_Trip')
            dhlm_trip = procon.get('DHLM_Trip_Signal')
            e_stop = procon.get('E_Stop')
        except:
            # Fallback if procon.get fails
            auto_select = True
            m1_trip = True
            m2_trip = True
            dhlm_trip = True
            e_stop = True

        if not auto_select:
            violations.append("Auto_Select=OFF (not in auto mode)")
        if mem.mode() == 'ERROR_COMMS':
            violations.append("COMMS_FAILED (communications lost)")
        if mem.mode() == 'ERROR_ESTOP':
            violations.append("E_STOP_TRIGGERED (emergency stop active)")
        if not m1_trip:
            violations.append("M1_Trip=FALSE (Motor 1 tripped)")
        if not m2_trip:
            violations.append("M2_Trip=FALSE (Motor 2 tripped)")
        if not dhlm_trip:
            violations.append("DHLM_Trip_Signal=FALSE (DHLM tripped)")
        if not e_stop:
            violations.append("E_Stop=FALSE (emergency stop pressed)")

        # Set error state and stop motors
        mem.set_mode('ERROR_SAFETY')
        procon.set('MOTOR_2', False)
        procon.set('MOTOR_3', False)

        # Log specific violations
        if violations:
            violation_msg = ", ".join(violations)
            controller.log_manager.warning(f"Safety violated - mode set to ERROR_SAFETY: {violation_msg}")
        else:
            controller.log_manager.warning("Safety violated - mode set to ERROR_SAFETY (reason unknown)")

class C3ReadyTimerStart(Rule):
    """Start C3 timer when S1 is broken."""
    def __init__(self):
        super().__init__("Start Timer When S1 Is broken")

    def condition(self, procon, mem):
        """Check if timer should start."""
        return(
            not procon.get('S1') and
            mem.get('C3_Timer') is None and
            mem.mode() != 'ERROR_ESTOP'  # don't start timer in error mode
        )

    def action(self, controller, procon, mem):
        mem.set('C3_Timer', time.time())
        controller.log_manager.debug("C3_Timer - Started")

class C3ReadyTimerReset(Rule):
    """Reset C3 timer when S1 is made."""
    def __init__(self):
        super().__init__("Reset Timer When S1 Is made")

    def condition(self, procon, mem):
        """Check if timer should reset."""
        return(
            procon.get('S1') and
            mem.get('C3_Timer') is not None
        )

    def action(self, controller, procon, mem):
        mem.set('C3_Timer', None)
        controller.log_manager.debug("C3_Timer - Reset")

class CratePositionsSensorLedOn(Rule):
    """Turn on crate position LED when crates aren't positioned correctly."""
    def __init__(self):
        super().__init__("Crate Positioning On")

    def condition(self, procon, mem):
        """Check if crates are misaligned."""
        return(
            not procon.get('CPS_1') or
            not procon.get('CPS_2')
        )

    def action(self, controller, procon, mem):
        """Turn on red LED."""
        procon.set('LED_RED', True)

class CratePositionsSensorLedOff(Rule):
    """Turn off crate position LED when crates are positioned correctly."""
    def __init__(self):
        super().__init__("Crate Positioning Off")

    def condition(self, procon, mem):
        """Check if crates are aligned."""
        return(
            procon.get('CPS_1') and
            procon.get('CPS_2')
        )

    def action(self, controller, procon, mem):
        """Turn off red LED."""
        procon.set('LED_RED', False)

class InitiateMoveC3toC2(Rule):
    """Start C3→C2 move: single bin from C3 to C2 after 30s delay."""

    def __init__(self):
        super().__init__("Initiate Move C3→C2")

    def condition(self, procon, mem):
        """Check if C3→C2 move should start."""
        return (
            mem.mode() == 'READY' and
            procon.get('S2')  and # No bin on C2
            not procon.get('S1') # Bin present on C3
        )

    def action(self, controller, procon, mem):
        """Set mode to MOVING_C3_TO_C2 and schedule both motors to start after 30s."""
        mem.set_mode('MOVING_C3_TO_C2')

        # For C3_TO_C2, bin just arrived on C3, so always use full 30 second delay
        remaining_delay = 30.0
        log_msg = f"MOVING_C3_TO_C2 - Both motors will start in {remaining_delay:.1f}s"

        # Store when motors should start (PLC-style timer using timestamp)
        motors_start_time = time.time() + remaining_delay
        mem.set('C3toC2_StartTime', motors_start_time)
        from datetime import datetime
        start_time_str = datetime.fromtimestamp(motors_start_time).strftime('%H:%M:%S.%f')[:-3]
        current_time_str = datetime.fromtimestamp(time.time()).strftime('%H:%M:%S.%f')[:-3]
        controller.log_manager.debug(f"Set C3toC2_StartTime to {start_time_str}, current time: {current_time_str}")
        mem.set('C3toC2_Delay', remaining_delay)  # Store for logging

        controller.log_manager.info(log_msg)


class StartMovingC3toC2AfterDelay(Rule):
    """Start both motors after 30s delay for C3→C2 move."""

    def __init__(self):
        super().__init__("Start Moving C3→C2 After Delay")

    def condition(self, procon, mem):
        """Check if motors should start after delay."""
        start_time = mem.get('C3toC2_StartTime')
        current_time = time.time()
        mode = mem.mode()

        return (
            mode == 'MOVING_C3_TO_C2' and
            start_time is not None and
            current_time >= start_time
        )

    def action(self, controller, procon, mem):
        # Clear timers to avoid starting again
        mem.set('C3toC2_StartTime', None)

        # Start MOTOR_2 first
        procon.set('MOTOR_2', True)

        # Safety delay between motors
        time.sleep(2.0)

        # Start MOTOR_3 after delay
        controller.log_manager.info("Motor 3 started after 2 second delay")
        procon.set('MOTOR_3', True)

        # Log completion
        remaining_delay = mem.get('C3toC2_Delay')
        log_msg = f"Started MOVING_C3_TO_C2 - Motor 2 started, Motor 3 started after 2s safety delay (total delay {remaining_delay:.1f}s)"
        controller.log_manager.info(log_msg)
        mem.set('C3toC2_Delay', None)


class CompleteMoveC3toC2(Rule):
    """Complete C3→C2 move when bin reaches C2."""

    def __init__(self):
        super().__init__("Complete Move C3→C2")

    def condition(self, procon, mem):
        """Check if C3→C2 move is complete."""
        return (
            mem.mode() == 'MOVING_C3_TO_C2' and
            not procon.get('S2')  # Bin detected on C2
        )

    def action(self, controller, procon, mem):
        """Stop both motors and return to READY."""
        procon.set('MOTOR_2', False)
        procon.set('MOTOR_3', False)
        # Clear C3toC2 timer to prevent motors from starting after completion
        mem.set('C3toC2_StartTime', None)
        mem.set('C3toC2_Delay', None)
        controller.log_manager.info("Completed MOVING_C3_TO_C2 - both motors stopped")
        mem.set_mode('READY')


class InitiateMoveC2toPalm(Rule):
    """Start C2→PALM move: single bin from C2 to PALM."""

    def __init__(self):
        super().__init__("Initiate Move C2→PALM")

    def condition(self, procon, mem):
        """Check if C2→PALM move should start."""
        return (
            mem.mode() == 'READY' and
            procon.get('S1') and  # No bin on C3
            not procon.get('S2') and  # Bin present on C2
            procon.rising_edge('Klaar_Geweeg_Btn') and  # Button press detected (edge)
            procon.get('PALM_Run_Signal')  # PALM ready
        )

    def action(self, controller, procon, mem):
        """Start MOTOR_2 and set mode to MOVING_C2_TO_PALM."""
        if not mem.mode().startswith('ERROR_'):
            procon.set('MOTOR_2', True)
            mem.set_mode('MOVING_C2_TO_PALM')
            controller.log_manager.info_once("Started MOVING_C2_TO_PALM - MOTOR_2 running")


class CompleteMoveC2toPalm(Rule):
    """Complete C2→PALM move when bin leaves C2."""

    def __init__(self):
        super().__init__("Complete Move C2→PALM")

    def condition(self, procon, mem):
        """Check if C2→PALM move is complete."""
        return (
            mem.mode() == 'MOVING_C2_TO_PALM' and
            procon.get('S2')  # Bin left C2
        )

    def action(self, controller, procon, mem):
        """Stop MOTOR_2 and return to READY."""
        # Delayed stop for MOTOR_2 (1 second)
        def stop_motor_2():
            procon.set('MOTOR_2', False)
            controller.log_manager.info_once("MOTOR_2 stopped after 1s delay")
            mem.set_mode('READY')
            # Clear the log_once cache for next cycle
            controller.log_manager.clear_logged_once(message="Started MOVING_C2_TO_PALM - MOTOR_2 running")
            controller.log_manager.clear_logged_once(message="MOVING_C2_TO_PALM - MOTOR_2 will stop in 1 seconds.")

        Timer(1.0, stop_motor_2).start()
        controller.log_manager.info_once("MOVING_C2_TO_PALM - MOTOR_2 will stop in 1 seconds.")

class InitiateMoveBoth(Rule):
    """Start moving both bins simultaneously."""

    def __init__(self):
        super().__init__("Initiate Move Both")

    def condition(self, procon, mem):
        """Check if both bins move should start."""
        return (
            mem.mode() == 'READY' and
            not procon.get('S1') and  # Bin present on C3
            not procon.get('S2') and  # Bin present on C2
            procon.rising_edge('Klaar_Geweeg_Btn') and  # Button press detected (edge)
            procon.get('PALM_Run_Signal')  # PALM ready
        )

    def action(self, controller, procon, mem):
        """Start MOTOR_2 immediately, delay MOTOR_3 to ensure bin on C3 for 30s total."""
        mem.set_mode('MOVING_BOTH')

        # Start MOTOR_2 immediately
        procon.set('MOTOR_2', True)

        # Calculate how long bin has been on C3
        c3_timer_start = mem.get('C3_Timer')
        if c3_timer_start:
            elapsed = time.time() - c3_timer_start
            # Ensure bin is on C3 for 30 seconds total
            remaining_delay = max(0, 30.0 - elapsed)
            log_msg = f"MOVING_BOTH - Motor 2 started, Motor 3 will start in {remaining_delay:.1f}s (bin on C3 for {elapsed:.1f}s)"
        else:
            # Fallback if timer not found (shouldn't happen)
            elapsed = 0
            remaining_delay = 30.0
            controller.log_manager.warning("C3_Timer not found, using default 30s delay")
            log_msg = f"MOVING_BOTH - Motor 2 started, Motor 3 will start in {remaining_delay:.1f}s"


        # Store when Motor 3 should start (PLC-style timer using timestamp)
        motor3_start_time = time.time() + remaining_delay
        mem.set('Motor3_StartTime', motor3_start_time)
        from datetime import datetime
        start_time_str = datetime.fromtimestamp(motor3_start_time).strftime('%H:%M:%S.%f')[:-3]
        current_time_str = datetime.fromtimestamp(time.time()).strftime('%H:%M:%S.%f')[:-3]
        controller.log_manager.debug(f"Set Motor3_StartTime to {start_time_str}, current time: {current_time_str}")
        mem.set('Motor3_Delay', remaining_delay)  # Store for logging

        controller.log_manager.info_once(log_msg)

class StartMovingMotor3AfterDelay(Rule):
    """Start Motor 3 after delay."""

    def __init__(self):
        super().__init__("Start Moving Motor 3 After Delay")

    def condition(self, procon, mem):
        """Check if Motor 3 should start after delay."""
        motor3_time = mem.get('Motor3_StartTime')
        current_time = time.time()
        mode = mem.mode()

        return (
            mode == 'MOVING_BOTH' and
            motor3_time is not None and
            current_time >= motor3_time
        )

    def action(self, controller, procon, mem):
        mode = mem.mode()

        # Clear timers to avoid starting again.
        mem.set('Motor3_StartTime', None)

        # Safety delay before starting Motor 3
        time.sleep(2.0)

        # Start MOTOR_3
        controller.log_manager.info("Motor 3 started after 2 second delay")
        procon.set('MOTOR_3', True)

        # Calculate how long bin has been on C3
        remaining_delay = mem.get('Motor3_Delay')
        log_msg = f"Started {mode} - Motor 3 started after {remaining_delay:.1f}s"
        controller.log_manager.info(log_msg)
        mem.set('Motor3_Delay', None)  # Store for logging

class CompleteMoveBoth(Rule):
    """Complete moving both bins with delayed MOTOR_2 stop."""

    def __init__(self):
        super().__init__("Complete Move Both")

    def condition(self, procon, mem):
        """Check if both bins move is complete."""
        return (
            mem.mode() == 'MOVING_BOTH' and
            procon.get('S1') and      # C3 is empty (no bin)
            not procon.get('S2')      # C2 has bin (bin present)
        )

    def action(self, controller, procon, mem):
        """Stop MOTOR 2 and 3 immediately."""
        procon.set('MOTOR_3', False)
        procon.set('MOTOR_2', False)
        # Clear Motor3 timer to prevent it from starting after completion
        mem.set('Motor3_StartTime', None)
        mem.set('Motor3_Delay', None)
        controller.log_manager.info("Completed MOVING_BOTH - MOTOR_3 and MOTOR_2 stopped.")
        mem.set_mode('READY')


class EmergencyStopRule(Rule):
    """Emergency stop all motors when E_Stop is pressed and held."""

    def __init__(self):
        super().__init__("Emergency Stop")

    def condition(self, procon, mem):
        """Check if emergency stop button is pressed and held for 1 second.

        Uses extended_hold to debounce momentary glitches and require
        a sustained E-Stop signal before triggering emergency shutdown.
        """
        return procon.extended_hold('E_Stop', False, 1.0)

    def action(self, controller, procon, mem):
        if  mem.mode() != 'ERROR_ESTOP': # Avoid duplicate actions and errors.
            """Stop all motors and set mode to ERROR_ESTOP."""
            controller.emergency_stop_all_motors()
            # Clear all memory and set ERROR_ESTOP mode
            mem.clear()
            mem.set_mode('ERROR_ESTOP')
            controller.log_manager.critical("EMERGENCY STOP activated! Reset required to restart.")

class EmergencyStopResetRule(Rule):
    """Reset ERROR_ESTOP when operator cycles Auto_Select and E_Stop is released."""

    def __init__(self):
        super().__init__("Emergency Stop Reset")

    def condition(self, procon, mem):
        """Check if reset triggered (Auto_Select switched to manual) and E_Stop released."""
        return (
            mem.mode() == 'ERROR_ESTOP' and
            procon.get('E_Stop') and  # E_Stop must be released
            procon.get('Manual_Select')  # Detect switch to manual (reset position)
        )

    def action(self, controller, procon, mem):
        """Clear ERROR_ESTOP mode."""
        mem.set_mode(None)
        controller.log_manager.info("Emergency stop RESET")


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
    # =====  Communications Monitoring =====
    rule_engine.add_rule(CommsHealthCheckRule())       # Monitor comms health continuously
    rule_engine.add_rule(CommsAcknowledgeRule())       # Acknowledge comms failure (switch OFF)
    rule_engine.add_rule(CommsResetRule())             # Reset after acknowledgment (switch ON)

    # =====  System Ready State Management =====
    rule_engine.add_rule(ManualModeRule())             # Set mode='OFF' when manual selected
    rule_engine.add_rule(ReadyRule())                  # Set mode='READY' when conditions met
    rule_engine.add_rule(ClearReadyRule())             # Set mode='ERROR_SAFETY' when trips occur

    # =====  C3 Timer Rules=====
    rule_engine.add_rule(C3ReadyTimerStart())
    rule_engine.add_rule(C3ReadyTimerReset())

    # =====  Creat Possitioning Rules=====
    # C3→C2 operation (single bin from C3 to C2)
    rule_engine.add_rule(CratePositionsSensorLedOn())
    rule_engine.add_rule(CratePositionsSensorLedOff())

    # =====  State Machine Operations =====
    # C3→C2 operation (single bin from C3 to C2)
    rule_engine.add_rule(InitiateMoveC3toC2())         # Start C3→C2 move with 30s delay
    rule_engine.add_rule(StartMovingC3toC2AfterDelay()) # Start both motors after 30s delay
    rule_engine.add_rule(CompleteMoveC3toC2())         # Complete when S2 becomes true

    # C2→PALM operation (single bin from C2 to PALM)
    rule_engine.add_rule(InitiateMoveC2toPalm())       # Start C2→PALM move on button
    rule_engine.add_rule(CompleteMoveC2toPalm())       # Complete when S2 becomes false

    # Both bins operation (C3→C2 and C2→PALM simultaneously)
    rule_engine.add_rule(InitiateMoveBoth())           # Start both bins move on button
    rule_engine.add_rule(StartMovingMotor3AfterDelay())         # start moving motar 3 after delay
    rule_engine.add_rule(CompleteMoveBoth())           # Complete with 2s delay for MOTOR_2

    # =====  EMERGENCY OVERRIDES (ALWAYS EXECUTE LAST) =====
    # These rules execute last and can override all previous rules
    rule_engine.add_rule(EmergencyStopRule())          # E-Stop stops everything, sets OPERATION_MODE='ERROR'
    rule_engine.add_rule(EmergencyStopResetRule())     # Allow reset after emergency
