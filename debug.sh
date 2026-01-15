#!/bin/bash
# Start Bella Fruita with debug logging (real hardware)
cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting Bella Fruita in DEBUG mode..."
echo "  Dashboard: http://localhost:7681"
echo ""
echo "Press Ctrl+C to stop"
echo ""
python main.py --debug --view web
