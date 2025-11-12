#!/bin/bash
# Bella Fruita - Start TUI Mode with Remote Viewing Support
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

# Default port for ttyd
TTYD_PORT=7681

# Parse command line arguments for port
REMAINING_ARGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
  --port)
    TTYD_PORT="$2"
    shift 2
    ;;
  *)
    # Collect remaining arguments
    REMAINING_ARGS+=("$1")
    shift
    ;;
  esac
done

# Restore remaining args for passing to main.py
set -- "${REMAINING_ARGS[@]}"

PID_FILE="$HOME/.bellafruita_ttyd_${TTYD_PORT}.pid"

# Function to cleanup on exit
cleanup() {
  if [ -f "$PID_FILE" ]; then
    TTYD_PID=$(cat "$PID_FILE")
    if ps -p $TTYD_PID >/dev/null 2>&1; then
      echo "Stopping ttyd (PID: $TTYD_PID)..."
      kill $TTYD_PID 2>/dev/null
    fi
    rm -f "$PID_FILE"
  fi
}

# Register cleanup on exit
trap cleanup EXIT INT TERM

# Check if ttyd is available
if command -v ttyd &>/dev/null; then
  # Check if port is already in use
  if lsof -Pi :$TTYD_PORT -sTCP:LISTEN -t >/dev/null 2>&1 || nc -z localhost $TTYD_PORT 2>/dev/null; then
    echo "Warning: Port $TTYD_PORT already in use. Remote viewing may not be available."
  else
    # Start ttyd in background to share terminal over HTTP
    echo "Starting remote terminal viewer on port $TTYD_PORT..."
    echo "Access the TUI remotely at: http://$(hostname -I 2>/dev/null | awk '{print $1}' || hostname):$TTYD_PORT"
    echo "Or from this machine: http://localhost:$TTYD_PORT"
    echo ""

    ttyd -W -p $TTYD_PORT -t fontSize=14 -t theme='{"background": "#1e1e1e"}' bash -c "cd $(pwd) && source venv/bin/activate && python main.py --view tui $*; echo 'Application exited. Press any key to close...'; read -n 1" &
    TTYD_PID=$!
    echo $TTYD_PID >"$PID_FILE"

    # Give ttyd a moment to start
    sleep 1

    # Check if ttyd is still running
    if ps -p $TTYD_PID >/dev/null 2>&1; then
      echo "Remote viewer started successfully (PID: $TTYD_PID)"
      echo ""

      # Wait for ttyd process to finish
      wait $TTYD_PID
    else
      echo "Warning: ttyd failed to start"
      rm -f "$PID_FILE"
      echo "Falling back to local mode only..."
      echo ""
      python main.py --view tui "$@"
    fi
  fi
else
  # ttyd not available, run normally
  echo "ttyd not installed - running in local mode only"
  echo "To enable remote viewing, install ttyd: sudo apt-get install ttyd (Linux) or brew install ttyd (macOS)"
  echo ""
  python main.py --view tui "$@"
fi
