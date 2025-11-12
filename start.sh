#!/bin/bash
# Bella Fruita - Smart Start Script
# Delegates to specific start scripts based on flags

cd "$(dirname "$0")"

# Default mode
MODE="web"

# Parse first argument to determine mode
case "$1" in
--web | web)
  MODE="web"
  shift # Remove mode flag
  ;;
--tui | tui)
  MODE="tui"
  shift
  ;;
--logs | logs)
  MODE="logs"
  shift
  ;;
--help | -h | help)
  echo "Bella Fruita - Start Script"
  echo ""
  echo "Usage:"
  echo "  ./start.sh [MODE] [OPTIONS]"
  echo ""
  echo "Modes:"
  echo "  tui   - Textual Terminal UI (default)"
  echo "  web   - Web Dashboard (browser-based) - port 7681"
  echo "  logs  - Headless logs-only mode"
  echo ""
  echo "Options:"
  echo "  --port PORT   - Custom port for Web server (default: 7681)"
  echo "  --mock        - Run with mock/simulated PLC data"
  echo ""
  echo "Examples:"
  echo "  ./start.sh              # Start TUI mode (default)"
  echo "  ./start.sh tui          # Start TUI mode explicitly"
  echo "  ./start.sh web          # Start web dashboard on port 7681"
  echo "  ./start.sh web --port 9000  # Web on custom port"
  echo "  ./start.sh logs         # Headless logs-only"
  echo "  ./start.sh tui --mock   # TUI with mock data"
  echo "  ./start.sh web --mock --port 8080  # Web with mock data on port 8080"
  echo ""
  exit 0
  ;;
esac

# Delegate to appropriate start script
case "$MODE" in
web)
  exec ./start-web.sh "$@"
  ;;
logs)
  exec ./start-logs.sh "$@"
  ;;
tui | *)
  exec ./start-tui.sh "$@"
  ;;
esac
