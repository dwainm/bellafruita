#!/bin/bash
# Update IP addresses and configuration for Bella Fruita
# Run this after installation to change Modbus PLC IP addresses

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Bella Fruita - Update IP Configuration${NC}"
echo "========================================"
echo ""

if [ ! -f "config.py" ]; then
    echo "Error: config.py not found!"
    exit 1
fi

# Read current values
CURRENT_INPUT_IP=$(grep -oP '^\s*input_ip:\s*str\s*=\s*"\K[0-9.]+' config.py 2>/dev/null || echo "192.168.1.10")
CURRENT_OUTPUT_IP=$(grep -oP '^\s*output_ip:\s*str\s*=\s*"\K[0-9.]+' config.py 2>/dev/null || echo "192.168.1.11")
CURRENT_USE_MOCK=$(grep -oP '^\s*use_mock:\s*bool\s*=\s*\K(True|False)' config.py 2>/dev/null || echo "False")

echo "Current configuration:"
echo "  Input PLC IP:  $CURRENT_INPUT_IP"
echo "  Output PLC IP: $CURRENT_OUTPUT_IP"
echo "  Mock Mode:     $CURRENT_USE_MOCK"
echo ""

# Get new values
read -p "Input PLC IP address [$CURRENT_INPUT_IP]: " INPUT_IP
INPUT_IP=${INPUT_IP:-$CURRENT_INPUT_IP}

read -p "Output PLC IP address [$CURRENT_OUTPUT_IP]: " OUTPUT_IP
OUTPUT_IP=${OUTPUT_IP:-$CURRENT_OUTPUT_IP}

read -p "Use mock mode? (y/n) [$([ "$CURRENT_USE_MOCK" == "True" ] && echo "y" || echo "n")]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    USE_MOCK="True"
elif [[ $REPLY =~ ^[Nn]$ ]]; then
    USE_MOCK="False"
else
    USE_MOCK=$CURRENT_USE_MOCK
fi

# Backup config
cp config.py config.py.backup
echo "Backed up config to config.py.backup"

# Update config
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s/\(^[[:space:]]*\)input_ip: str = \"[^\"]*\"\(.*\)$/\1input_ip: str = \"$INPUT_IP\"\2/" config.py
    sed -i '' "s/\(^[[:space:]]*\)output_ip: str = \"[^\"]*\"\(.*\)$/\1output_ip: str = \"$OUTPUT_IP\"\2/" config.py
    sed -i '' "s/\(^[[:space:]]*\)use_mock: bool = .*/\1use_mock: bool = $USE_MOCK/" config.py
else
    # Linux
    sed -i "s/\(^[[:space:]]*\)input_ip: str = \"[^\"]*\"\(.*\)$/\1input_ip: str = \"$INPUT_IP\"\2/" config.py
    sed -i "s/\(^[[:space:]]*\)output_ip: str = \"[^\"]*\"\(.*\)$/\1output_ip: str = \"$OUTPUT_IP\"\2/" config.py
    sed -i "s/\(^[[:space:]]*\)use_mock: bool = .*/\1use_mock: bool = $USE_MOCK/" config.py
fi

# Verify changes were applied
VERIFY_INPUT=$(grep -oP '^\s*input_ip:\s*str\s*=\s*"\K[^"]+' config.py 2>/dev/null || echo "")
VERIFY_OUTPUT=$(grep -oP '^\s*output_ip:\s*str\s*=\s*"\K[^"]+' config.py 2>/dev/null || echo "")
VERIFY_MOCK=$(grep -oP '^\s*use_mock:\s*bool\s*=\s*\K(True|False)' config.py 2>/dev/null || echo "")

echo ""
if [ "$VERIFY_INPUT" == "$INPUT_IP" ] && [ "$VERIFY_OUTPUT" == "$OUTPUT_IP" ] && [ "$VERIFY_MOCK" == "$USE_MOCK" ]; then
    echo -e "${GREEN}Configuration updated!${NC}"
    echo "  Input PLC IP:  $INPUT_IP"
    echo "  Output PLC IP: $OUTPUT_IP"
    echo "  Mock Mode:     $USE_MOCK"
else
    echo -e "${YELLOW}Warning: Could not verify all changes were applied${NC}"
    echo "Current values in config.py:"
    echo "  Input PLC IP:  $VERIFY_INPUT"
    echo "  Output PLC IP: $VERIFY_OUTPUT"
    echo "  Mock Mode:     $VERIFY_MOCK"
    echo ""
    echo "Expected values:"
    echo "  Input PLC IP:  $INPUT_IP"
    echo "  Output PLC IP: $OUTPUT_IP"
    echo "  Mock Mode:     $USE_MOCK"
    echo ""
    echo "Please verify config.py manually. Backup available at: config.py.backup"
fi
echo ""
echo "Restart the system for changes to take effect:"
echo "  systemctl --user restart bellafruita  # If running as service"
echo "  ./start.sh                              # If running manually"
