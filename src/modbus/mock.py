"""Mock Modbus client for testing without hardware."""

from typing import Any
from dataclasses import dataclass

from .interface import ModbusInterface
from .mapping import MODBUS_MAP


@dataclass
class MockResponse:
    """Mock response object matching PyModbus response format."""
    bits: list[bool] = None
    registers: list[int] = None
    address: int = 0
    value: Any = None

    def __post_init__(self):
        if self.bits is None:
            self.bits = []
        if self.registers is None:
            self.registers = []


class MockModbusClient(ModbusInterface):

    """Mock Modbus client for testing control logic without hardware."""
    def __init__(self, host: str = "mock", port: int = 502):

        """Initialize mock Modbus client.
        Args:
            host: Placeholder host (not used in mock)
            port: Placeholder port (not used in mock)
        """
        self.host = host
        self.port = port
        self._connected = False

        # Build input coil definitions from MODBUS_MAP (address 0-15, stored as 1-indexed internally)
        self.inputs = {}
        for address, info in MODBUS_MAP['INPUT']['coils'].items():
            # Convert 0-indexed address to 1-indexed for inputs dict
            self.inputs[address + 1] = {
                'label': info['label'],
                'description': info['description'],
                'state': False
            }

        # In-memory storage for mock data
        self._coils: dict[int, bool] = {}
        self._discrete_inputs: dict[int, bool] = {}
        self._holding_registers: dict[int, int] = {0: 12345}  # Default version number
        self._input_registers: dict[int, int] = {}

    def connect(self) -> bool:
        """Simulate connection to Modbus device.

        Returns:
            bool: Always True for mock
        """
        self._connected = True
        return True

    def close(self) -> None:
        """Simulate closing connection."""
        self._connected = False

    def is_connected(self) -> bool:
        """Check if mock client is 'connected'.

        Returns:
            bool: Connection status
        """
        return self._connected

    def read_coils(self, address: int, count: int = 1, device_id: int = 1) -> MockResponse:
        """Read coil status from mock memory.

        Args:
            address: Starting coil address (0-indexed in Modbus)
            count: Number of coils to read
            device_id: Modbus device/slave ID (ignored in mock)

        Returns:
            MockResponse with .bits attribute containing bool values
        """
        bits = []
        for i in range(count):
            addr = address + i
            # Convert 0-indexed address to 1-indexed for inputs dict
            input_idx = addr + 1
            if input_idx in self.inputs:
                bits.append(self.inputs[input_idx]['state'])
            else:
                bits.append(self._coils.get(addr, False))
        return MockResponse(bits=bits, address=address)

    def write_coil(self, address: int, value: bool, device_id: int = 1) -> MockResponse:
        """Write single coil to mock memory.

        Args:
            address: Coil address
            value: Boolean value to write
            device_id: Modbus device/slave ID (ignored in mock)

        Returns:
            MockResponse
        """
        self._coils[address] = value
        return MockResponse(address=address, value=value)

    def read_holding_registers(self, address: int, count: int = 1, device_id: int = 1) -> MockResponse:
        """Read holding registers from mock memory.

        Args:
            address: Starting register address
            count: Number of registers to read
            device_id: Modbus device/slave ID (ignored in mock)

        Returns:
            MockResponse with .registers attribute containing int values
        """
        registers = [self._holding_registers.get(address + i, 0) for i in range(count)]
        return MockResponse(registers=registers, address=address)

    def read_input_registers(self, address: int, count: int = 1, device_id: int = 1) -> MockResponse:
        """Read input registers from mock memory.

        Args:
            address: Starting register address
            count: Number of registers to read
            device_id: Modbus device/slave ID (ignored in mock)

        Returns:
            MockResponse with .registers attribute containing int values
        """
        registers = [self._input_registers.get(address + i, 0) for i in range(count)]
        return MockResponse(registers=registers, address=address)

    def write_register(self, address: int, value: int, device_id: int = 1) -> MockResponse:
        """Write single register to mock memory.

        Args:
            address: Register address
            value: Integer value to write
            device_id: Modbus device/slave ID (ignored in mock)

        Returns:
            MockResponse
        """
        self._holding_registers[address] = value
        return MockResponse(address=address, value=value)

    # Helper methods for testing

    def set_input_state(self, input_number: int, value: bool) -> None:
        """Helper: Set input state by input number (1-16).

        Args:
            input_number: Input number (1-16)
            value: Boolean value
        """
        if input_number in self.inputs:
            self.inputs[input_number]['state'] = value
            # Also update coils storage (0-indexed)
            self._coils[input_number - 1] = value

    def get_input_info(self, input_number: int) -> dict:
        """Get input information.

        Args:
            input_number: Input number (1-16)

        Returns:
            dict: Input info with label, description, state
        """
        return self.inputs.get(input_number, {})

    def set_coil(self, address: int, value: bool) -> None:
        """Helper: Manually set a coil value for testing.

        Args:
            address: Coil address (0-indexed)
            value: Boolean value
        """
        self._coils[address] = value
        # If this corresponds to an input, update that too
        input_idx = address + 1
        if input_idx in self.inputs:
            self.inputs[input_idx]['state'] = value

    def set_register(self, address: int, value: int) -> None:
        """Helper: Manually set a holding register value for testing.

        Args:
            address: Register address
            value: Integer value
        """
        self._holding_registers[address] = value

    def set_input_register(self, address: int, value: int) -> None:
        """Helper: Manually set an input register value for testing.

        Args:
            address: Register address
            value: Integer value
        """
        self._input_registers[address] = value

    def reset(self) -> None:
        """Helper: Clear all mock data."""
        self._coils.clear()
        self._discrete_inputs.clear()
        self._holding_registers.clear()
        self._input_registers.clear()
