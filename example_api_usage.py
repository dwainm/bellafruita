"""Example usage of Procon with label-based access."""

from src.modbus import create_modbus_client, Procon

# Create mock clients for testing
input_client = create_modbus_client("172.20.231.25", mock=True)
output_client = create_modbus_client("172.20.231.49", mock=True)

# Connect
input_client.connect()
output_client.connect()

# Create Procon wrapper
procon = Procon(input_client, output_client)

print("=== Procon Usage Examples ===\n")

# Example 1: Read single values by label
print("1. Read single values:")
s1_value = procon.get('input', 's1')
print(f"   Sensor S1: {s1_value}")

version = procon.get('output', 'version')
print(f"   Version register: {version}")

# Example 2: Write values by label
print("\n2. Write values:")
success = procon.set('output', 'motor_1', True)
print(f"   Set MOTOR_1 to True: {success}")

success = procon.set('output', 'version', 99999)
print(f"   Set VERSION to 99999: {success}")

# Example 3: Read all coils from a device
print("\n3. Read all input coils:")
all_inputs = procon.get_all('input', 'coils')
for label, value in sorted(all_inputs.items())[:5]:  # Show first 5
    status = "ACTIVE" if value else "INACTIVE"
    print(f"   {label:15} = {status}")

# Example 4: Read all output registers
print("\n4. Read all output registers:")
all_registers = procon.get_all('output', 'registers')
for label, value in all_registers.items():
    print(f"   {label:15} = {value}")

# Example 5: Labels are case-insensitive
print("\n5. Case-insensitive labels:")
print(f"   'S1' = {procon.get('input', 'S1')}")
print(f"   's1' = {procon.get('input', 's1')}")
print(f"   'MOTOR_1' = {procon.get('output', 'MOTOR_1')}")
print(f"   'motor_1' = {procon.get('output', 'motor_1')}")

# Cleanup
input_client.close()
output_client.close()

print("\n✅ API works! Now you can use labels instead of addresses!")
