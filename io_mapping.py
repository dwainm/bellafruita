"""Modbus register and coil mappings for Bella Fruita system.

This is the single source of truth for all Modbus addresses, labels, and descriptions.
When hardware purposes change, only update this file.
"""

MODBUS_MAP = {
    'INPUT': {
        'coils': {
            0: {'label': 'S1', 'description': 'Sensor Conveyor 1'},
            1: {'label': 'S2', 'description': 'Sensor Conveyor 2'},
            2: {'label': 'CS1', 'description': 'Crate Height Sensor 1'},
            3: {'label': 'CS2', 'description': 'Crate Height Sensor 2'},
            4: {'label': 'CS3', 'description': 'Crate Height Sensor 3'},
            5: {'label': 'M1_Trip', 'description': 'Conveyor 1 Motor Drive Trip'},
            6: {'label': 'M2_Trip', 'description': 'Conveyor 2 Motor Drive Trip'},
            7: {'label': 'E_Stop', 'description': 'Emergency Stop Button'},
            8: {'label': 'Manual_Select', 'description': 'Selector Switch Manual'},
            9: {'label': 'Auto_Select', 'description': 'Selector Switch Auto'},
            10: {'label': 'Klaar_Geweeg_Btn', 'description': 'Klaar Geweeg Button (Ready Weighed)'},
            11: {'label': 'CPS_1', 'description': 'Crate position sensor 1'},
            12: {'label': 'CPS_2', 'description': 'Crate position sensor 2'},
            13: {'label': 'Reset_Btn', 'description': 'System Reset Button'},
            14: {'label': 'PALM_Run_Signal', 'description': 'PALM Chemtrack Run Signal'},
            15: {'label': 'DHLM_Trip_Signal', 'description': 'DHLM Chemtrack Trip Signal'},
        },
        'registers': {
            # Input module holding registers (if any)
        }
    },
    'OUTPUT': {
        'coils': {
            0: {'label': 'LED_GREEN', 'description': 'Comms indicator light.'},
            1: {'label': 'MOTOR_2', 'description': 'Conveyor 2 Motor'},
            2: {'label': 'MOTOR_3', 'description': 'Conveyor 3 Motor'},
            3: {'label': 'LED_RED', 'description': 'Create position indicator light.'},
        },
        'registers': {
            0: {'label': 'VERSION', 'description': 'Firmware Version Number'},
        }
    }
}


def get_address(device: str, label: str, reg_type: str = None):
    """Get Modbus address for a given device and label.

    Args:
        device: 'INPUT' or 'OUTPUT'
        label: Label like 'S1', 'MOTOR_1', 'VERSION' (case-insensitive)
        reg_type: 'coils' or 'registers' (optional, will search both if not specified)

    Returns:
        tuple: (address, reg_type) or (None, None) if not found

    Example:
        >>> get_address('INPUT', 's1')
        (0, 'coils')
        >>> get_address('OUTPUT', 'version')
        (0, 'registers')
    """
    device = device.upper()
    label = label.upper()

    if device not in MODBUS_MAP:
        return None, None

    # Search in specified type only
    if reg_type:
        for addr, info in MODBUS_MAP[device][reg_type].items():
            if info['label'].upper() == label:
                return addr, reg_type
        return None, None

    # Search in both coils and registers
    for rtype in ['coils', 'registers']:
        for addr, info in MODBUS_MAP[device].get(rtype, {}).items():
            if info['label'].upper() == label:
                return addr, rtype

    return None, None


def get_info(device: str, address: int, reg_type: str):
    """Get label and description for a given address.

    Args:
        device: 'INPUT' or 'OUTPUT'
        address: Modbus address
        reg_type: 'coils' or 'registers'

    Returns:
        dict: {'label': str, 'description': str} or None if not found
    """
    device = device.upper()

    if device not in MODBUS_MAP:
        return None

    return MODBUS_MAP[device].get(reg_type, {}).get(address)


def get_all_labels(device: str, reg_type: str):
    """Get all labels for a device and type.

    Args:
        device: 'INPUT' or 'OUTPUT'
        reg_type: 'coils' or 'registers'

    Returns:
        list: List of (address, label, description) tuples
    """
    device = device.upper()

    if device not in MODBUS_MAP:
        return []

    result = []
    for addr, info in MODBUS_MAP[device].get(reg_type, {}).items():
        result.append((addr, info['label'], info['description']))

    return sorted(result, key=lambda x: x[0])  # Sort by address
