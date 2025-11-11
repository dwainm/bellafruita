#!/bin/bash
# Bella Fruita Control System - Installer/Updater
# Usage:
#   Interactive: bash <(curl -sSL https://raw.githubusercontent.com/dwainm/bellafruita/master/install.sh)
#   Non-interactive:
#     INPUT_IP=192.168.1.10 OUTPUT_IP=192.168.1.11 bash <(curl -sSL https://...)
#     SKIP_CONFIG=true bash <(curl -sSL https://...)  # Skip config prompts

set -e # Exit on error

# Configuration
REPO_URL="https://github.com/dwainm/bellafruita"
INSTALL_DIR="$HOME/packlinefeeder"
PYTHON_MIN_VERSION="3.9"

# Check for non-interactive mode (env vars set)
if [ -n "$INPUT_IP" ] || [ -n "$OUTPUT_IP" ]; then
  NON_INTERACTIVE=true
  print_info "Running in non-interactive mode (env vars detected)"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
  print_error "Please do not run this script as root or with sudo"
  exit 1
fi

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  OS="linux"
  print_info "Detected Linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
  OS="macos"
  print_info "Detected macOS"
else
  print_error "Unsupported OS: $OSTYPE"
  exit 1
fi

# Check if this is an update or fresh install
if [ -d "$INSTALL_DIR/.git" ]; then
  MODE="update"
  print_info "Existing installation found - updating..."
else
  MODE="install"
  print_info "Fresh installation..."
fi

# Check Python version
print_info "Checking Python version..."
if command -v python3 &>/dev/null; then
  PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
  PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
  PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

  if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    print_error "Python 3.9+ required, found $PYTHON_VERSION"
    exit 1
  fi
  print_success "Python $PYTHON_VERSION found"
else
  print_error "Python 3 not found. Please install Python 3.9+"
  exit 1
fi

# Check git
if ! command -v git &>/dev/null; then
  print_error "git not found. Please install git first"
  if [ "$OS" == "linux" ]; then
    print_info "Install with: sudo apt-get install git"
  else
    print_info "Install with: brew install git"
  fi
  exit 1
fi

# Check/Install ttyd for remote terminal viewing
print_info "Checking ttyd for remote terminal access..."
if ! command -v ttyd &>/dev/null; then
  print_warning "ttyd not found - attempting to install for remote UI access..."

  if [ "$OS" == "linux" ]; then
    # Build ttyd from source on Linux
    print_info "Building ttyd from source..."

    # Install build dependencies
    if command -v apt-get &>/dev/null; then
      print_info "Installing build dependencies..."
      if sudo -n true 2>/dev/null; then
        # Passwordless sudo
        sudo apt-get update >/dev/null 2>&1
        sudo apt-get install -y build-essential cmake git libjson-c-dev libwebsockets-dev >/dev/null 2>&1
      else
        # Need password
        print_info "Installing dependencies (you may be prompted for your password)..."
        sudo apt-get update
        sudo apt-get install -y build-essential cmake git libjson-c-dev libwebsockets-dev
      fi
    else
      print_error "apt-get not found. Cannot install build dependencies."
      print_info "Install manually: https://github.com/tsl0922/ttyd"
      return
    fi

    # Clone and build ttyd
    TTYD_BUILD_DIR="/tmp/ttyd-build-$$"
    print_info "Cloning ttyd repository..."
    if git clone --depth 1 https://github.com/tsl0922/ttyd.git "$TTYD_BUILD_DIR" >/dev/null 2>&1; then
      cd "$TTYD_BUILD_DIR"
      mkdir build
      cd build

      print_info "Compiling ttyd (this may take a few minutes)..."
      if cmake .. >/dev/null 2>&1 && make >/dev/null 2>&1; then
        print_info "Installing ttyd..."
        if sudo -n true 2>/dev/null; then
          sudo make install >/dev/null 2>&1
        else
          sudo make install
        fi

        # Clean up build directory
        cd /
        rm -rf "$TTYD_BUILD_DIR"

        print_success "ttyd built and installed successfully"
      else
        print_error "Failed to compile ttyd"
        cd /
        rm -rf "$TTYD_BUILD_DIR"
        print_info "Install manually: https://github.com/tsl0922/ttyd"
      fi
    else
      print_error "Failed to clone ttyd repository"
      print_info "Install manually: https://github.com/tsl0922/ttyd"
    fi
  elif [ "$OS" == "macos" ]; then
    # Try to install via Homebrew on macOS
    if command -v brew &>/dev/null; then
      print_info "Installing ttyd via Homebrew..."
      if brew install ttyd 2>&1 | tee /tmp/ttyd_install.log; then
        print_success "ttyd installation initiated"
      else
        print_error "Failed to install ttyd via Homebrew"
        cat /tmp/ttyd_install.log
        print_info "Install manually: brew install ttyd"
      fi
      rm -f /tmp/ttyd_install.log
    else
      print_warning "Homebrew not found. Install ttyd manually"
      print_info "Install Homebrew: https://brew.sh"
      print_info "Then run: brew install ttyd"
    fi
  fi

  # Check if installation succeeded
  if command -v ttyd &>/dev/null; then
    print_success "ttyd installed successfully"
  else
    print_warning "ttyd not installed - remote viewing will not be available"
    print_info "The application will still work, but only locally on this machine"
  fi
else
  print_success "ttyd already installed"
fi

# Save existing config BEFORE any git operations
SAVED_SITE_NAME=""
SAVED_INPUT_IP=""
SAVED_OUTPUT_IP=""

if [ "$MODE" == "update" ] && [ -f "$INSTALL_DIR/config.py" ]; then
  cd "$INSTALL_DIR"
  print_info "Reading existing configuration..."

  # Extract values using Python (works with dataclass format)
  SAVED_INPUT_IP=$(python3 -c "import sys; sys.path.insert(0, '.'); import config; print(config.ModbusConfig().input_ip)" 2>/dev/null || echo "")
  SAVED_OUTPUT_IP=$(python3 -c "import sys; sys.path.insert(0, '.'); import config; print(config.ModbusConfig().output_ip)" 2>/dev/null || echo "")
  SAVED_SITE_NAME=$(python3 -c "import sys; sys.path.insert(0, '.'); import config; print(config.AppConfig.site_name)" 2>/dev/null || echo "Bella Fruita")

  if [ -n "$SAVED_INPUT_IP" ] && [ -n "$SAVED_OUTPUT_IP" ]; then
    print_success "Saved config: Site='$SAVED_SITE_NAME', Input=$SAVED_INPUT_IP, Output=$SAVED_OUTPUT_IP"
  else
    print_warning "Could not read existing config"
  fi
fi

# Install/Update
if [ "$MODE" == "update" ]; then
  print_info "Pulling latest changes from GitHub..."
  cd "$INSTALL_DIR"

  # Check if there are local changes
  if ! git diff-index --quiet HEAD --; then
    print_warning "Local changes detected. Stashing them..."
    git stash save "Auto-stash before update $(date '+%Y-%m-%d %H:%M:%S')"
  fi

  # Pull latest from default branch
  git pull --force
  print_success "Code updated to latest version"

else
  print_info "Cloning repository from GitHub..."

  # Remove directory if it exists but isn't a git repo
  if [ -d "$INSTALL_DIR" ]; then
    print_warning "Removing existing non-git directory..."
    rm -rf "$INSTALL_DIR"
  fi

  # Clone repository (uses default branch)
  git clone $REPO_URL "$INSTALL_DIR"
  cd "$INSTALL_DIR"
  print_success "Repository cloned"
fi

# Setup virtual environment
print_info "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
  python3 -m venv venv
  print_success "Virtual environment created"
else
  print_info "Virtual environment already exists"
fi

# Activate venv and install dependencies
print_info "Installing Python dependencies..."
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip >/dev/null 2>&1

# Install requirements
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
  print_success "Dependencies installed"
else
  print_warning "No requirements.txt found"
fi

# Configure Modbus IPs
echo ""
print_info "Configuration Setup"
echo "================================================"

# Use saved config values (from before git pull) or defaults
CURRENT_SITE_NAME=${SAVED_SITE_NAME:-"Bella Fruita"}
CURRENT_INPUT_IP=${SAVED_INPUT_IP:-"192.168.1.10"}
CURRENT_OUTPUT_IP=${SAVED_OUTPUT_IP:-"192.168.1.11"}

# During updates, ask if user wants to keep existing config
PRESERVE_CONFIG=false
if [ "$MODE" == "update" ] && [ -n "$SAVED_INPUT_IP" ]; then
  print_info "Current configuration:"
  echo "  Site Name:     $CURRENT_SITE_NAME"
  echo "  Input PLC IP:  $CURRENT_INPUT_IP"
  echo "  Output PLC IP: $CURRENT_OUTPUT_IP"
  echo ""

  if [ "$NON_INTERACTIVE" != "true" ]; then
    read -p "Keep these settings? (y/n) [y]: " -n 1 -r </dev/tty
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
      PRESERVE_CONFIG=true
      print_info "Keeping existing configuration"
    else
      PRESERVE_CONFIG=false
    fi
  else
    # Non-interactive mode - always preserve during updates
    PRESERVE_CONFIG=true
    print_info "Keeping existing configuration (non-interactive mode)"
  fi
fi

if [ "$SKIP_CONFIG" != "true" ]; then
  # Use env vars if set (non-interactive mode), otherwise prompt
  if [ "$NON_INTERACTIVE" == "true" ] || [ "$PRESERVE_CONFIG" == "true" ]; then
    # Non-interactive mode OR user chose to preserve config
    if [ "$PRESERVE_CONFIG" == "true" ]; then
      print_info "Applying existing configuration"
    else
      print_info "Using configuration from environment variables"
    fi
    SITE_NAME=${SITE_NAME:-${CURRENT_SITE_NAME}}
    INPUT_IP=${INPUT_IP:-${CURRENT_INPUT_IP}}
    OUTPUT_IP=${OUTPUT_IP:-${CURRENT_OUTPUT_IP}}
  else
    echo ""
    print_info "Please enter your site/installation details"
    echo "(Press Enter to use default values)"
    echo ""

    # Site Name
    read -p "Site/Installation Name [${CURRENT_SITE_NAME:-Bella Fruita}]: " SITE_NAME </dev/tty
    SITE_NAME=${SITE_NAME:-${CURRENT_SITE_NAME:-Bella Fruita}}

    # Input PLC IP
    read -p "Input PLC IP address [${CURRENT_INPUT_IP:-192.168.1.10}]: " INPUT_IP </dev/tty
    INPUT_IP=${INPUT_IP:-${CURRENT_INPUT_IP:-192.168.1.10}}

    # Output PLC IP
    read -p "Output PLC IP address [${CURRENT_OUTPUT_IP:-192.168.1.11}]: " OUTPUT_IP </dev/tty
    OUTPUT_IP=${OUTPUT_IP:-${CURRENT_OUTPUT_IP:-192.168.1.11}}
  fi

  # Backup existing config
  if [ -f "config.py" ]; then
    cp config.py config.py.backup
    print_info "Backed up existing config to config.py.backup"
  fi

  # Update config.py using awk (more portable and reliable)
  if [ -f "config.py" ]; then
    # Update site_name - replace first non-commented occurrence
    awk -v new_name="$SITE_NAME" '
      !done && /^[[:space:]]*site_name: str = "/ {
        if ($0 !~ /^[[:space:]]*#/) {
          sub(/site_name: str = "[^"]*"/, "site_name: str = \"" new_name "\"")
          done=1
        }
      }
      {print}
    ' config.py > config.py.tmp && mv config.py.tmp config.py

    # Update input_ip - replace first non-commented occurrence
    awk -v new_ip="$INPUT_IP" '
      !done && /^[[:space:]]*input_ip: str = "/ {
        if ($0 !~ /^[[:space:]]*#/) {
          sub(/input_ip: str = "[^"]*"/, "input_ip: str = \"" new_ip "\"")
          done=1
        }
      }
      {print}
    ' config.py > config.py.tmp && mv config.py.tmp config.py

    # Update output_ip - replace first non-commented occurrence
    awk -v new_ip="$OUTPUT_IP" '
      !done && /^[[:space:]]*output_ip: str = "/ {
        if ($0 !~ /^[[:space:]]*#/) {
          sub(/output_ip: str = "[^"]*"/, "output_ip: str = \"" new_ip "\"")
          done=1
        }
      }
      {print}
    ' config.py > config.py.tmp && mv config.py.tmp config.py

    # Verify changes were applied successfully (using Python for reliable parsing)
    VERIFY_SITE=$(python3 -c "import sys; sys.path.insert(0, '.'); import config; print(config.AppConfig.site_name)" 2>/dev/null || echo "")
    VERIFY_INPUT=$(python3 -c "import sys; sys.path.insert(0, '.'); import config; print(config.ModbusConfig().input_ip)" 2>/dev/null || echo "")
    VERIFY_OUTPUT=$(python3 -c "import sys; sys.path.insert(0, '.'); import config; print(config.ModbusConfig().output_ip)" 2>/dev/null || echo "")

    if [ "$VERIFY_SITE" == "$SITE_NAME" ] && [ "$VERIFY_INPUT" == "$INPUT_IP" ] && [ "$VERIFY_OUTPUT" == "$OUTPUT_IP" ]; then
      print_success "Configuration updated:"
      echo "  Site Name:     $SITE_NAME"
      echo "  Input PLC IP:  $INPUT_IP"
      echo "  Output PLC IP: $OUTPUT_IP"
    else
      print_error "Failed to update config.py automatically"
      print_warning "Please edit config.py manually and update:"
      echo "  site_name: str = \"$SITE_NAME\""
      echo "  input_ip: str = \"$INPUT_IP\""
      echo "  output_ip: str = \"$OUTPUT_IP\""

      if [ -f "config.py.backup" ]; then
        print_info "Original config backed up to: config.py.backup"
      fi

      # Restore backup if update failed
      if [ -f "config.py.backup" ]; then
        cp config.py.backup config.py
        print_info "Restored config.py from backup"
      fi
    fi
  else
    print_warning "config.py not found - please configure manually"
  fi
fi

echo ""

# Setup auto-start on boot
echo ""
if [ "$OS" == "linux" ]; then
  read -p "Would you like to auto-start on login with Terminal window? (y/n) " -n 1 -r </dev/tty
  echo

  if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Desktop autostart - opens terminal with TUI
    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"

    # Detect available terminal emulator and use start.sh
    TERMINAL_CMD=""
    if command -v lxterminal &>/dev/null; then
      # Raspberry Pi OS / LXDE default
      TERMINAL_CMD="lxterminal --command=\"bash -c 'cd $INSTALL_DIR && ./start.sh; exec bash'\""
      print_info "Detected: lxterminal (Raspberry Pi OS)"
    elif command -v x-terminal-emulator &>/dev/null; then
      # Debian default alternative
      TERMINAL_CMD="x-terminal-emulator -e bash -c 'cd $INSTALL_DIR && ./start.sh; exec bash'"
      print_info "Detected: x-terminal-emulator"
    elif command -v gnome-terminal &>/dev/null; then
      # GNOME
      TERMINAL_CMD="gnome-terminal -- bash -c 'cd $INSTALL_DIR && ./start.sh; exec bash'"
      print_info "Detected: gnome-terminal"
    elif command -v xfce4-terminal &>/dev/null; then
      # XFCE
      TERMINAL_CMD="xfce4-terminal -e \"bash -c 'cd $INSTALL_DIR && ./start.sh; exec bash'\""
      print_info "Detected: xfce4-terminal"
    elif command -v mate-terminal &>/dev/null; then
      # MATE
      TERMINAL_CMD="mate-terminal -e \"bash -c 'cd $INSTALL_DIR && ./start.sh; exec bash'\""
      print_info "Detected: mate-terminal"
    else
      print_error "No supported terminal emulator found"
      print_warning "Please install lxterminal: sudo apt-get install lxterminal"
      TERMINAL_CMD="lxterminal --command=\"bash -c 'cd $INSTALL_DIR && ./start.sh; exec bash'\""
    fi

    print_info "Autostart will use start.sh (includes ttyd remote viewing)"

    AUTOSTART_FILE="$AUTOSTART_DIR/packlinefeeder.desktop"
    cat >"$AUTOSTART_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Bella Fruita Control System
Comment=Apple sorting machine control system
Exec=$TERMINAL_CMD
Terminal=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

    print_success "Desktop autostart installed"
    print_info "A terminal window will open on login showing the TUI"
    print_info "To disable: rm ~/.config/autostart/packlinefeeder.desktop"
  else
    print_info "No auto-start configured"
  fi
elif [ "$OS" == "macos" ]; then
  read -p "Would you like to auto-start on login with Terminal window? (y/n) " -n 1 -r </dev/tty
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    PLIST_FILE="$HOME/Library/LaunchAgents/com.bellafruita.app.plist"
    mkdir -p "$HOME/Library/LaunchAgents"

    # Create a launcher script that opens Terminal
    LAUNCHER_SCRIPT="$INSTALL_DIR/launch_terminal.sh"
    cat >"$LAUNCHER_SCRIPT" <<'EOF'
#!/bin/bash
# Launch Bella Fruita in a new Terminal window
osascript <<'APPLESCRIPT'
tell application "Terminal"
    do script "cd ~/bellafruita && source venv/bin/activate && python main.py"
    activate
end tell
APPLESCRIPT
EOF
    chmod +x "$LAUNCHER_SCRIPT"

    # Create LaunchAgent plist
    cat >"$PLIST_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bellafruita.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>$LAUNCHER_SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF

    # Load the LaunchAgent
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    launchctl load "$PLIST_FILE"

    print_success "LaunchAgent installed - will auto-start on login"
    print_info "The TUI will open in a Terminal window on login"
    print_info "To disable: launchctl unload ~/Library/LaunchAgents/com.bellafruita.app.plist"
    print_info "To test now: launchctl start com.bellafruita.app"
  fi
fi

# Create convenience scripts
print_info "Creating convenience scripts..."

# Create start script with ttyd support
cat >"$INSTALL_DIR/start.sh" <<'EOF'
#!/bin/bash
# Bella Fruita - Start Script with Remote Viewing Support
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

# Configuration
TTYD_PORT=7681  # Port for remote web-based terminal viewing
PID_FILE="$HOME/.bellafruita_ttyd.pid"

# Function to cleanup on exit
cleanup() {
    if [ -f "$PID_FILE" ]; then
        TTYD_PID=$(cat "$PID_FILE")
        if ps -p $TTYD_PID > /dev/null 2>&1; then
            echo "Stopping ttyd (PID: $TTYD_PID)..."
            kill $TTYD_PID 2>/dev/null
        fi
        rm -f "$PID_FILE"
    fi
}

# Register cleanup on exit
trap cleanup EXIT INT TERM

# Check if ttyd is available
if command -v ttyd &> /dev/null; then
    # Check if port is already in use
    if lsof -Pi :$TTYD_PORT -sTCP:LISTEN -t >/dev/null 2>&1 || nc -z localhost $TTYD_PORT 2>/dev/null; then
        echo "Warning: Port $TTYD_PORT already in use. Remote viewing may not be available."
    else
        # Start ttyd in background to share terminal over HTTP
        # -W: Enable write access (allows keyboard input from remote viewers)
        # -p: Port to listen on
        # -t: Set terminal type
        # bash -c: Command to run (launches the python app)
        echo "Starting remote terminal viewer on port $TTYD_PORT..."
        echo "Access the TUI remotely at: http://$(hostname -I 2>/dev/null | awk '{print $1}' || hostname):$TTYD_PORT"
        echo "Or from this machine: http://localhost:$TTYD_PORT"
        echo ""

        ttyd -W -p $TTYD_PORT -t fontSize=14 -t theme='{"background": "#1e1e1e"}' bash -c "cd $(pwd) && source venv/bin/activate && unset DEBUG && python main.py $*; echo 'Application exited. Press any key to close...'; read -n 1" &
        TTYD_PID=$!
        echo $TTYD_PID > "$PID_FILE"

        # Give ttyd a moment to start
        sleep 1

        # Check if ttyd is still running
        if ps -p $TTYD_PID > /dev/null 2>&1; then
            echo "Remote viewer started successfully (PID: $TTYD_PID)"
            echo ""

            # Wait for ttyd process to finish
            wait $TTYD_PID
        else
            echo "Warning: ttyd failed to start"
            rm -f "$PID_FILE"
            echo "Falling back to local mode only..."
            echo ""
            unset DEBUG
            python main.py "$@"
        fi
    fi
else
    # ttyd not available, run normally
    echo "ttyd not installed - running in local mode only"
    echo "To enable remote viewing, install ttyd: sudo apt-get install ttyd (Linux) or brew install ttyd (macOS)"
    echo ""
    unset DEBUG
    python main.py "$@"
fi
EOF
chmod +x "$INSTALL_DIR/start.sh"

# Create update script (updates code only, preserves config)
cat >"$INSTALL_DIR/update.sh" <<'EOF'
#!/bin/bash
# Update Bella Fruita code from GitHub
# Configuration (IP addresses) will be preserved
echo "Updating Bella Fruita from GitHub..."
bash <(curl -sSL https://raw.githubusercontent.com/dwainm/bellafruita/master/install.sh)
EOF
chmod +x "$INSTALL_DIR/update.sh"

# The update_ip.sh script should already exist from git, but make it executable
if [ -f "$INSTALL_DIR/update_ip.sh" ]; then
  chmod +x "$INSTALL_DIR/update_ip.sh"
fi

print_success "Scripts created"

# Summary
echo ""
echo "================================================"
if [ "$MODE" == "install" ]; then
  print_success "Installation complete!"
else
  print_success "Update complete!"
fi
echo "================================================"
echo ""
print_info "Installation directory: $INSTALL_DIR"
echo ""
print_info "To start the system:"
echo "  cd $INSTALL_DIR"
echo "  ./start.sh"
echo ""
print_info "To update code from GitHub:"
echo "  cd $INSTALL_DIR"
echo "  ./update.sh"
echo ""
print_info "To change IP addresses:"
echo "  cd $INSTALL_DIR"
echo "  ./update_ip.sh"
echo ""
if [ "$OS" == "linux" ]; then
  if [ -f "$HOME/.config/autostart/packlinefeeder.desktop" ]; then
    print_info "Desktop autostart enabled:"
    echo "  Terminal window will open on login"
    echo "  To disable: rm ~/.config/autostart/packlinefeeder.desktop"
    echo ""
  fi
elif [ "$OS" == "macos" ] && [ -f "$HOME/Library/LaunchAgents/com.bellafruita.app.plist" ]; then
  print_info "LaunchAgent commands:"
  echo "  launchctl start com.bellafruita.app    # Start now"
  echo "  launchctl stop com.bellafruita.app     # Stop"
  echo "  launchctl unload ~/Library/LaunchAgents/com.bellafruita.app.plist  # Disable auto-start"
  echo "  launchctl load ~/Library/LaunchAgents/com.bellafruita.app.plist    # Enable auto-start"
  echo ""
fi
print_info "Configuration file: $INSTALL_DIR/config.py"
echo ""
