"""Modbus communication interfaces for Bella Fruita apple sorting system."""

from .interface import ModbusInterface
from .mock import MockModbusClient
from .factory import create_modbus_client
from .mapping import MODBUS_MAP, get_address, get_info, get_all_labels
from .api import Procon

# Conditionally import real client only if pymodbus is available
try:
    from .client import ModbusClient
    __all__ = [
        "ModbusInterface",
        "ModbusClient",
        "MockModbusClient",
        "create_modbus_client",
        "Procon",
        "MODBUS_MAP",
        "get_address",
        "get_info",
        "get_all_labels",
    ]
except ImportError:
    # pymodbus not installed, only mock client available
    __all__ = [
        "ModbusInterface",
        "MockModbusClient",
        "create_modbus_client",
        "Procon",
        "MODBUS_MAP",
        "get_address",
        "get_info",
        "get_all_labels",
    ]
