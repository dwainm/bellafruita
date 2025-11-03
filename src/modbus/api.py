"""High-level API for Procon Modbus operations using labels instead of addresses."""

from typing import Any, Union
from .mapping import get_address, get_info
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
                 input_slave_id: int = 1, output_slave_id: int = 1):
        """Initialize Procon.

        Args:
            input_client: ModbusInterface for input module
            output_client: ModbusInterface for output module
            input_slave_id: Slave ID for input module
            output_slave_id: Slave ID for output module
        """
        self.clients = {
            'INPUT': input_client,
            'OUTPUT': output_client
        }
        self.slave_ids = {
            'INPUT': input_slave_id,
            'OUTPUT': output_slave_id
        }

    def get(self, device: str, label: str) -> Union[bool, int, None]:
        """Read value by device and label.

        Args:
            device: 'input' or 'output' (case-insensitive)
            label: Label like 's1', 'motor_1', 'version' (case-insensitive)

        Returns:
            bool for coils, int for registers, None if not found or error

        Example:
            >>> procon.get('input', 's1')
            True
            >>> procon.get('output', 'version')
            12345
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

    def set(self, device: str, label: str, value: Union[bool, int]) -> bool:
        """Write value by device and label.

        Args:
            device: 'input' or 'output' (case-insensitive)
            label: Label like 'motor_1', 'version' (case-insensitive)
            value: Boolean for coils, integer for registers

        Returns:
            bool: True if successful, False otherwise

        Example:
            >>> procon.set('output', 'motor_1', True)
            True
            >>> procon.set('output', 'version', 12345)
            True
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
        from .mapping import get_all_labels
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

        except Exception:
            pass

        return result
