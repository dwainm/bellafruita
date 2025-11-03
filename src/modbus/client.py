"""Real PyModbus client implementation."""

from typing import Any
from pymodbus.client import ModbusTcpClient

from .interface import ModbusInterface


class ModbusClient(ModbusInterface):
    """Wrapper around PyModbus ModbusTcpClient for Procon terminals."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 3.0,
        retries: int = 3
    ):
        """Initialize Modbus TCP client.

        Args:
            host: IP address or hostname of Procon Modbus terminal
            port: Modbus TCP port (default: 502)
            timeout: Connection timeout in seconds
            retries: Number of retry attempts
        """
        self.host = host
        self.port = port
        self._client = ModbusTcpClient(
            host=host,
            port=port,
            timeout=timeout,
            retries=retries
        )

    def connect(self) -> bool:
        """Establish connection to Modbus device.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            return self._client.connect()
        except Exception:
            # Network error during connection attempt
            return False

    def close(self) -> None:
        """Close connection to Modbus device."""
        try:
            self._client.close()
        except Exception:
            # Ignore errors during close - connection may already be broken
            pass

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            bool: True if connected, False otherwise
        """
        return self._client.connected

    def read_coils(self, address: int, count: int = 1, device_id: int = 1) -> Any:
        """Read coil status from Modbus device.

        Args:
            address: Starting coil address
            count: Number of coils to read
            device_id: Modbus device/slave ID

        Returns:
            Response object with .bits attribute containing bool values, or None on error
        """
        try:
            return self._client.read_coils(address, count=count, device_id=device_id)
        except Exception:
            # Network disconnection, timeout, or other communication error
            return None

    def write_coil(self, address: int, value: bool, device_id: int = 1) -> Any:
        """Write single coil to Modbus device.

        Args:
            address: Coil address
            value: Boolean value to write
            device_id: Modbus device/slave ID

        Returns:
            Response object, or None on error
        """
        try:
            return self._client.write_coil(address, value, device_id=device_id)
        except Exception:
            # Network disconnection, timeout, or other communication error
            return None

    def read_holding_registers(self, address: int, count: int = 1, device_id: int = 1) -> Any:
        """Read holding registers from Modbus device.

        Args:
            address: Starting register address
            count: Number of registers to read
            device_id: Modbus device/slave ID

        Returns:
            Response object with .registers attribute containing int values, or None on error
        """
        try:
            return self._client.read_holding_registers(address, count=count, device_id=device_id)
        except Exception:
            # Network disconnection, timeout, or other communication error
            return None

    def read_input_registers(self, address: int, count: int = 1, device_id: int = 1) -> Any:
        """Read input registers from Modbus device.

        Args:
            address: Starting register address
            count: Number of registers to read
            device_id: Modbus device/slave ID

        Returns:
            Response object with .registers attribute containing int values, or None on error
        """
        try:
            return self._client.read_input_registers(address, count=count, device_id=device_id)
        except Exception:
            # Network disconnection, timeout, or other communication error
            return None

    def write_register(self, address: int, value: int, device_id: int = 1) -> Any:
        """Write single register to Modbus device.

        Args:
            address: Register address
            value: Integer value to write
            device_id: Modbus device/slave ID

        Returns:
            Response object, or None on error
        """
        try:
            return self._client.write_register(address, value, device_id=device_id)
        except Exception:
            # Network disconnection, timeout, or other communication error
            return None
