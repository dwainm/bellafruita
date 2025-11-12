#!/bin/bash
# Bella Fruita - Start TUI Mode
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

# Run TUI in the terminal
python main.py --view tui "$@"
