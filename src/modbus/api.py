"""High-level API for Procon Modbus operations using labels instead of addresses."""

import time
from typing import Any, Union, Optional
from io_mapping import get_address, get_info
from .interface import ModbusInterface


class Procon:
    """High-level wrapper for Procon Modbus operations.

    Allows reading/writing using device names and labels instead of raw addresses.

    Example:
        >>> procon = Procon(input_client, output_client)
        >>> procon.get('input', 's1')  # Read sensor 1
        True
        >>> procon.set('output', 'motor_1', True)  # Turn on motor 1
        >>> procon.get('output', 'version')  # Read version register
        12345
    """

    def __init__(self, input_client: ModbusInterface, output_client: ModbusInterface,
                 input_slave_id: int = 1, output_slave_id: int = 1, log_manager=None):
        """Initialize Procon.

        Args:
            input_client: ModbusInterface for input module
            output_client: ModbusInterface for output module
            input_slave_id: Slave ID for input module
            output_slave_id: Slave ID for output module
            log_manager: LogManager instance for edge detection (optional)
        """
        self.clients = {
            'INPUT': input_client,
            'OUTPUT': output_client
        }
        self.slave_ids = {
            'INPUT': input_slave_id,
            'OUTPUT': output_slave_id
        }
        self.log_manager = log_manager
        self.default_edge_window_ms = 500.0

    def get(self, device_or_label: str, label: str = None) -> Union[bool, int, None]:
        """Read value by device and label, or by label only.

        Can be called in two ways:
        1. get(device, label) - Read from specific device
        2. get(label) - Search INPUT then OUTPUT automatically

        Args:
            device_or_label: Device ('input'/'output') or label if called with 1 arg
            label: Label if called with 2 args (optional)

        Returns:
            bool for coils, int for registers, None if not found or error

        Example:
            >>> procon.get('input', 's1')     # Old API still works
            True
            >>> procon.get('S1')               # New unified API
            True
            >>> procon.get('VERSION')          # Works for any label
            12345
        """
        # New API: single argument means unified search
        if label is None:
            label = device_or_label
            # Try INPUT first (most signals are inputs)
            value = self._get_from_device('INPUT', label)
            if value is not None:
                return value
            # Try OUTPUT
            return self._get_from_device('OUTPUT', label)

        # Old API: two arguments means device + label
        device = device_or_label
        return self._get_from_device(device, label)

    def _get_from_device(self, device: str, label: str) -> Union[bool, int, None]:
        """Internal method to read from a specific device.

        Args:
            device: 'input' or 'output' (case-insensitive)
            label: Label like 's1', 'motor_1', 'version' (case-insensitive)

        Returns:
            bool for coils, int for registers, None if not found or error
        """
        device = device.upper()

        # Get address and type from mapping
        address, reg_type = get_address(device, label)

        if address is None:
            return None

        client = self.clients.get(device)
        slave_id = self.slave_ids.get(device)

        if not client:
            return None

        try:
            if reg_type == 'coils':
                # Read single coil
                result = client.read_coils(address, count=1, device_id=slave_id)
                if hasattr(result, 'bits') and result.bits:
                    return result.bits[0]
                return None

            elif reg_type == 'registers':
                # Read single register
                result = client.read_holding_registers(address, count=1, device_id=slave_id)
                if hasattr(result, 'registers') and result.registers:
                    return result.registers[0]
                return None

        except Exception:
            return None

    def set(self, device_or_label: str, label_or_value: Union[str, bool, int], value: Union[bool, int] = None) -> bool:
        """Write value by device and label, or by label only.

        Can be called in two ways:
        1. set(device, label, value) - Write to specific device
        2. set(label, value) - Search OUTPUT then INPUT automatically

        Args:
            device_or_label: Device ('input'/'output') or label if called with 2 args
            label_or_value: Label if 3 args, or value if 2 args
            value: Value if called with 3 args (optional)

        Returns:
            bool: True if successful, False otherwise

        Example:
            >>> procon.set('output', 'motor_1', True)  # Old API still works
            True
            >>> procon.set('MOTOR_2', True)             # New unified API
            True
        """
        # New API: two arguments means unified search
        if value is None:
            label = device_or_label
            value = label_or_value
            # Try OUTPUT first (most writes are to outputs)
            if self._set_to_device('OUTPUT', label, value):
                return True
            # Try INPUT
            return self._set_to_device('INPUT', label, value)

        # Old API: three arguments means device + label + value
        device = device_or_label
        label = label_or_value
        return self._set_to_device(device, label, value)

    def _set_to_device(self, device: str, label: str, value: Union[bool, int]) -> bool:
        """Internal method to write to a specific device.

        Args:
            device: 'input' or 'output' (case-insensitive)
            label: Label like 'motor_1', 'version' (case-insensitive)
            value: Boolean for coils, integer for registers

        Returns:
            bool: True if successful, False otherwise
        """
        device = device.upper()

        # Get address and type from mapping
        address, reg_type = get_address(device, label)

        if address is None:
            return False

        client = self.clients.get(device)
        slave_id = self.slave_ids.get(device)

        if not client:
            return False

        try:
            if reg_type == 'coils':
                # Write single coil
                if not isinstance(value, bool):
                    return False
                result = client.write_coil(address, value, device_id=slave_id)
                # Check if write was successful (result should not be None)
                return result is not None

            elif reg_type == 'registers':
                # Write single register
                if not isinstance(value, int):
                    return False
                result = client.write_register(address, value, device_id=slave_id)
                # Check if write was successful (result should not be None)
                return result is not None

        except Exception:
            return False

    def get_all(self, device: str, reg_type: str) -> dict:
        """Read all values of a specific type from a device.

        Args:
            device: 'input' or 'output' (case-insensitive)
            reg_type: 'coils' or 'registers'

        Returns:
            dict: {label: value} mapping

        Example:
            >>> api.get_all('input', 'coils')
            {'S1': True, 'S2': False, 'CS1': True, ...}
        """
        device = device.upper()
        reg_type = reg_type.lower()

        client = self.clients.get(device)
        slave_id = self.slave_ids.get(device)

        if not client:
            return {}

        result = {}

        # Get all defined addresses for this device/type
        from io_mapping import get_all_labels
        labels = get_all_labels(device, reg_type)

        if not labels:
            return {}

        # Find min and max addresses to read in one go
        addresses = [addr for addr, _, _ in labels]
        min_addr = min(addresses)
        max_addr = max(addresses)
        count = max_addr - min_addr + 1

        try:
            if reg_type == 'coils':
                read_result = client.read_coils(min_addr, count=count, device_id=slave_id)
                if hasattr(read_result, 'bits'):
                    for addr, label, _ in labels:
                        idx = addr - min_addr
                        if idx < len(read_result.bits):
                            result[label] = read_result.bits[idx]

            elif reg_type == 'registers':
                read_result = client.read_holding_registers(min_addr, count=count, device_id=slave_id)
                if hasattr(read_result, 'registers'):
                    for addr, label, _ in labels:
                        idx = addr - min_addr
                        if idx < len(read_result.registers):
                            result[label] = read_result.registers[idx]
                else:
                    # Connection failed - explicitly set registers to 0
                    for addr, label, _ in labels:
                        result[label] = 0

        except Exception:
            # On exception, explicitly set all registers to 0 for clarity
            if reg_type == 'registers':
                for addr, label, _ in labels:
                    result[label] = 0

        return result

    def rising_edge(self, label: str, window_ms: Optional[float] = None) -> bool:
        """Detect rising edge (False->True transition) within time window.

        Args:
            label: Signal label to check (e.g., 'Klaar_Geweeg_Btn', 'S1')
            window_ms: Time window in milliseconds (uses default if not specified)

        Returns:
            True if signal transitioned from False to True within the window
        """
        if not self.log_manager:
            return False

        window = window_ms if window_ms is not None else self.default_edge_window_ms
        return self._detect_edge(label, 'rising', window)

    def falling_edge(self, label: str, window_ms: Optional[float] = None) -> bool:
        """Detect falling edge (True->False transition) within time window.

        Args:
            label: Signal label to check (e.g., 'S2', 'Auto_Select')
            window_ms: Time window in milliseconds (uses default if not specified)

        Returns:
            True if signal transitioned from True to False within the window
        """
        if not self.log_manager:
            return False

        window = window_ms if window_ms is not None else self.default_edge_window_ms
        return self._detect_edge(label, 'falling', window)

    def extended_hold(self, label: str, value: bool, hold_seconds: float = 1.0) -> bool:
        """Check if signal has been held at a specific value for a duration.

        This is useful for debouncing signals that might have brief glitches.

        Args:
            label: Signal label to check (e.g., 'M1_Trip', 'E_Stop')
            value: The value to check for (True or False)
            hold_seconds: How long the signal must be held (in seconds)

        Returns:
            True if signal has been continuously at 'value' for 'hold_seconds'

        Example:
            # Check if M1_Trip has been FALSE (tripped) for 1+ seconds
            if procon.extended_hold('M1_Trip', False, 1.0):
                # Genuine trip condition - take action
        """
        if not self.log_manager:
            return False

        logs = self.log_manager.input_logs

        if len(logs) < 2:
            return False

        # Calculate time window
        current_time = time.time()
        cutoff_time = current_time - hold_seconds

        # Collect all values within the hold window
        values_in_window = []
        for entry in reversed(logs):
            if entry.timestamp < cutoff_time:
                break
            values_in_window.append((entry.timestamp, entry.data.get(label)))

        # Need enough history to cover the hold period
        if not values_in_window:
            return False

        # Check if we have data covering the entire hold period
        oldest_timestamp = values_in_window[-1][0]
        if oldest_timestamp > cutoff_time:
            # Not enough history - can't confirm hold
            return False

        # Check that ALL values in the window match the desired value
        for timestamp, signal_value in values_in_window:
            if signal_value != value:
                return False  # Found a different value - not held continuously

        return True  # All values match - signal has been held

    def _detect_edge(self, label: str, edge_type: str, window_ms: float) -> bool:
        """Internal method to detect edges in log history.

        Args:
            label: Signal label
            edge_type: 'rising' or 'falling'
            window_ms: Time window in milliseconds

        Returns:
            True if edge detected within window
        """
        logs = self.log_manager.input_logs

        if len(logs) < 2:
            return False

        # Calculate time window
        current_time = time.time()
        window_seconds = window_ms / 1000.0
        cutoff_time = current_time - window_seconds

        # Collect values within the time window (iterate backwards from newest)
        values_in_window = []
        for entry in reversed(logs):
            if entry.timestamp < cutoff_time:
                break
            values_in_window.append((entry.timestamp, entry.data.get(label)))

        if len(values_in_window) < 2:
            return False

        # Reverse to get chronological order (oldest first)
        values_in_window.reverse()

        # Look for the specified edge transition
        for i in range(len(values_in_window) - 1):
            current_val = values_in_window[i][1]
            next_val = values_in_window[i + 1][1]

            if edge_type == 'rising':
                if current_val == False and next_val == True:
                    return True
            elif edge_type == 'falling':
                if current_val == True and next_val == False:
                    return True

        return False
