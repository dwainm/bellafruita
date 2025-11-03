"""Factory for creating Modbus client instances."""

from .interface import ModbusInterface
from .mock import MockModbusClient

# Try to import real client, but don't fail if pymodbus not installed
try:
    from .client import ModbusClient
    HAS_PYMODBUS = True
except ImportError:
    HAS_PYMODBUS = False


def create_modbus_client(
    host: str,
    port: int = 502,
    mock: bool = False,
    timeout: float = 3.0,
    retries: int = 3
) -> ModbusInterface:
    """Create a Modbus client instance.

    Factory function that creates either a real or mock Modbus client
    based on configuration. This allows easy switching between hardware
    and testing modes.

    Args:
        host: IP address or hostname of Modbus device
        port: Modbus TCP port (default: 502)
        mock: If True, return MockModbusClient for testing (default: False)
        timeout: Connection timeout in seconds (real client only)
        retries: Number of retry attempts (real client only)

    Returns:
        ModbusInterface: Either ModbusClient or MockModbusClient instance

    Example:
        # For production with real hardware
        client = create_modbus_client("192.168.1.100")

        # For testing without hardware
        client = create_modbus_client("192.168.1.100", mock=True)

        # Both use the same interface
        client.connect()
        result = client.read_coils(0, count=8)
        client.close()
    """
    if mock:
        return MockModbusClient(host=host, port=port)
    else:
        if not HAS_PYMODBUS:
            raise ImportError(
                "pymodbus is required for real Modbus client. "
                "Install it with: pip install pymodbus\n"
                "Or use mock=True for testing without hardware."
            )
        return ModbusClient(
            host=host,
            port=port,
            timeout=timeout,
            retries=retries
        )
