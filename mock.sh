#!/bin/bash
# Start Bella Fruita in mock mode with web UI
cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting Bella Fruita in MOCK mode (debug enabled)..."
echo "  Main dashboard: http://localhost:7681"
echo "  Mock controls:  http://localhost:7682"
echo ""
echo "Press Ctrl+C to stop"
echo ""
python main.py --mock --debug --view web
