"""Machine Memory - Internal state for the control system.

Provides a clean API for accessing machine operation mode and other internal state.
"""


class MachineMemory:
    """Machine memory for storing internal control state.

    This separates internal machine state (like operation mode) from physical I/O.

    Example:
        >>> mem = MachineMemory()
        >>> mem.mode()
        None
        >>> mem.set_mode('READY')
        >>> mem.mode()
        'READY'
        >>> mem.set('C3_ReadyTimer', 1234567890.5)
        >>> mem.get('C3_ReadyTimer')
        1234567890.5
    """

    def __init__(self):
        """Initialize empty machine memory."""
        self._state = {}

    def mode(self):
        """Get current operation mode.

        Returns:
            str or None: Current operation mode, or None if not set
        """
        return self._state.get('_MODE')

    def set_mode(self, mode):
        """Set operation mode.

        Args:
            mode: Operation mode string (e.g., 'READY', 'ERROR_COMMS', 'MOVING_C3_TO_C2')
        """
        self._state['_MODE'] = mode

    def get(self, key, default=None):
        """Get arbitrary memory value.

        Args:
            key: Memory key
            default: Default value if key not found

        Returns:
            Value associated with key, or default if not found
        """
        return self._state.get(key, default)

    def set(self, key, value):
        """Set arbitrary memory value.

        Args:
            key: Memory key
            value: Value to store
        """
        self._state[key] = value

    def clear(self):
        """Clear all memory state."""
        self._state.clear()

    def pop(self, key, default=None):
        """Remove and return a memory value.

        Args:
            key: Memory key
            default: Default value if key not found

        Returns:
            Value that was removed, or default if not found
        """
        return self._state.pop(key, default)
