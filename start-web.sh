#!/bin/bash
# Bella Fruita - Start Web Dashboard Mode
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

# Default port (same as ttyd for consistency)
PORT=7681

# Parse command line arguments for port
REMAINING_ARGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
  --port)
    PORT="$2"
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

echo "=========================================="
echo "Bella Fruita - Web Dashboard"
echo "=========================================="
echo ""
echo "Starting web server on port $PORT..."
echo ""
echo "Access dashboard at:"
echo "  Local:   http://localhost:$PORT"
echo "  Network: http://$(hostname -I 2>/dev/null | awk '{print $1}' || hostname):$PORT"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start web server
python main.py --view web --port "$PORT" "$@"
