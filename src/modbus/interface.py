"""Abstract interface for Modbus communication."""

from abc import ABC, abstractmethod
from typing import Any


class ModbusInterface(ABC):
    """Abstract base class for Modbus client implementations."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to Modbus device.

        Returns:
            bool: True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close connection to Modbus device."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            bool: True if connected, False otherwise
        """
        pass

    @abstractmethod
    def read_coils(self, address: int, count: int = 1, device_id: int = 1) -> Any:
        """Read coil status from Modbus device.

        Args:
            address: Starting coil address
            count: Number of coils to read
            device_id: Modbus device/slave ID

        Returns:
            Response object with .bits attribute containing bool values
        """
        pass

    @abstractmethod
    def write_coil(self, address: int, value: bool, device_id: int = 1) -> Any:
        """Write single coil to Modbus device.

        Args:
            address: Coil address
            value: Boolean value to write
            device_id: Modbus device/slave ID

        Returns:
            Response object
        """
        pass

    @abstractmethod
    def read_holding_registers(self, address: int, count: int = 1, device_id: int = 1) -> Any:
        """Read holding registers from Modbus device.

        Args:
            address: Starting register address
            count: Number of registers to read
            device_id: Modbus device/slave ID

        Returns:
            Response object with .registers attribute containing int values
        """
        pass

    @abstractmethod
    def read_input_registers(self, address: int, count: int = 1, device_id: int = 1) -> Any:
        """Read input registers from Modbus device.

        Args:
            address: Starting register address
            count: Number of registers to read
            device_id: Modbus device/slave ID

        Returns:
            Response object with .registers attribute containing int values
        """
        pass

    @abstractmethod
    def write_register(self, address: int, value: int, device_id: int = 1) -> Any:
        """Write single register to Modbus device.

        Args:
            address: Register address
            value: Integer value to write
            device_id: Modbus device/slave ID

        Returns:
            Response object
        """
        pass
