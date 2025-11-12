#!/bin/bash
# Bella Fruita - Start Headless Logs-Only Mode
cd "$(dirname "$0")"
source venv/bin/activate

# Validate Python syntax before starting
if ! python -m py_compile main.py config.py 2>/dev/null; then
  echo "ERROR: Python syntax errors detected in application files."
  echo "Please run './update.sh' to get the latest code."
  echo ""
  python -m py_compile main.py config.py
  exit 1
fi

echo "=========================================="
echo "Bella Fruita - Headless Mode (Logs Only)"
echo "=========================================="
echo ""
echo "Running without UI - logs will be printed to stdout"
echo "Press Ctrl+C to stop"
echo ""

# Start in logs-only mode
python main.py --view logs "$@"
