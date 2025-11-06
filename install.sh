#!/bin/bash
# Bella Fruita Control System - Installer/Updater
# Usage:
#   Interactive: bash <(curl -sSL https://raw.githubusercontent.com/dwainm/bellafruita/master/install.sh)
#   Non-interactive:
#     INPUT_IP=192.168.1.10 OUTPUT_IP=192.168.1.11 bash <(curl -sSL https://...)
#     SKIP_CONFIG=true bash <(curl -sSL https://...)  # Skip config prompts

set -e  # Exit on error

# Configuration
REPO_URL="https://github.com/dwainm/bellafruita"
INSTALL_DIR="$HOME/bellafruita"
PYTHON_MIN_VERSION="3.9"

# Check for non-interactive mode (env vars set)
if [ -n "$INPUT_IP" ] || [ -n "$OUTPUT_IP" ] || [ -n "$USE_MOCK" ]; then
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
if command -v python3 &> /dev/null; then
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
if ! command -v git &> /dev/null; then
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
if ! command -v ttyd &> /dev/null; then
    print_warning "ttyd not found - installing for remote UI access..."

    if [ "$OS" == "linux" ]; then
        # Try to install ttyd on Linux
        if command -v apt-get &> /dev/null; then
            # Debian/Ubuntu/Raspberry Pi OS
            print_info "Installing ttyd via apt..."
            if sudo -n true 2>/dev/null; then
                sudo apt-get update > /dev/null 2>&1
                sudo apt-get install -y ttyd > /dev/null 2>&1 || {
                    print_warning "Could not auto-install ttyd. Install manually: sudo apt-get install ttyd"
                }
            else
                print_warning "Needs sudo to install ttyd. Run: sudo apt-get install ttyd"
            fi
        else
            print_warning "Please install ttyd manually for remote viewing"
            print_info "Visit: https://github.com/tsl0922/ttyd"
        fi
    elif [ "$OS" == "macos" ]; then
        # Try to install via Homebrew on macOS
        if command -v brew &> /dev/null; then
            print_info "Installing ttyd via Homebrew..."
            brew install ttyd > /dev/null 2>&1 || {
                print_warning "Could not auto-install ttyd. Install manually: brew install ttyd"
            }
        else
            print_warning "Homebrew not found. Install ttyd manually: brew install ttyd"
        fi
    fi

    # Check if installation succeeded
    if command -v ttyd &> /dev/null; then
        print_success "ttyd installed successfully"
    else
        print_warning "ttyd not installed - remote viewing will not be available"
    fi
else
    print_success "ttyd already installed"
fi

# Install/Update
if [ "$MODE" == "update" ]; then
    print_info "Pulling latest changes from GitHub..."

    # Check if there are local changes
    cd "$INSTALL_DIR"
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
pip install --upgrade pip > /dev/null 2>&1

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

# Check if config.py exists and try to read current settings
CURRENT_INPUT_IP=""
CURRENT_OUTPUT_IP=""
CURRENT_USE_MOCK=""

if [ -f "config.py" ]; then
    # Try to read current config (if file is valid Python)
    if python3 -m py_compile config.py 2>/dev/null; then
        CURRENT_INPUT_IP=$(grep -oP "input_ip:\s*['\"]?\K[0-9.]+" config.py 2>/dev/null || echo "")
        CURRENT_OUTPUT_IP=$(grep -oP "output_ip:\s*['\"]?\K[0-9.]+" config.py 2>/dev/null || echo "")
        CURRENT_USE_MOCK=$(grep -oP "use_mock:\s*\K(True|False)" config.py 2>/dev/null || echo "")
    else
        print_warning "Existing config.py has syntax errors - will be replaced with template"
    fi

    if [ "$MODE" == "update" ] && [ -n "$CURRENT_INPUT_IP" ]; then
        # During updates with valid config, ask if user wants to keep or change settings
        print_info "Current configuration detected:"
        echo "  Input PLC IP:  $CURRENT_INPUT_IP"
        echo "  Output PLC IP: $CURRENT_OUTPUT_IP"
        echo "  Mock Mode:     $CURRENT_USE_MOCK"
        echo ""

        if [ "$NON_INTERACTIVE" != "true" ]; then
            read -p "Keep these settings? (y/n) [y]: " -n 1 -r < /dev/tty
            echo
            if [[ $REPLY =~ ^[Nn]$ ]]; then
                # User wants to change settings - don't preserve
                PRESERVE_CONFIG=false
            else
                # User wants to keep settings
                PRESERVE_CONFIG=true
                print_info "Keeping existing configuration"
            fi
        else
            # Non-interactive mode - always preserve during updates
            PRESERVE_CONFIG=true
            print_info "Keeping existing configuration (non-interactive mode)"
        fi
    else
        PRESERVE_CONFIG=false
    fi
fi

# Set defaults if no valid config was found
CURRENT_INPUT_IP=${CURRENT_INPUT_IP:-"192.168.1.10"}
CURRENT_OUTPUT_IP=${CURRENT_OUTPUT_IP:-"192.168.1.11"}
CURRENT_USE_MOCK=${CURRENT_USE_MOCK:-"False"}

if [ "$SKIP_CONFIG" != "true" ]; then
    # Use env vars if set (non-interactive mode), otherwise prompt
    if [ "$NON_INTERACTIVE" == "true" ] || [ "$PRESERVE_CONFIG" == "true" ]; then
        # Non-interactive mode OR user chose to preserve config
        if [ "$PRESERVE_CONFIG" == "true" ]; then
            print_info "Applying existing configuration"
        else
            print_info "Using configuration from environment variables"
        fi
        INPUT_IP=${INPUT_IP:-${CURRENT_INPUT_IP}}
        OUTPUT_IP=${OUTPUT_IP:-${CURRENT_OUTPUT_IP}}
        USE_MOCK=${USE_MOCK:-${CURRENT_USE_MOCK}}
    else
        echo ""
        print_info "Please enter your Modbus PLC IP addresses"
        echo "(Press Enter to use default values)"
        echo ""

        # Input PLC IP
        read -p "Input PLC IP address [${CURRENT_INPUT_IP:-192.168.1.10}]: " INPUT_IP < /dev/tty
        INPUT_IP=${INPUT_IP:-${CURRENT_INPUT_IP:-192.168.1.10}}

        # Output PLC IP
        read -p "Output PLC IP address [${CURRENT_OUTPUT_IP:-192.168.1.11}]: " OUTPUT_IP < /dev/tty
        OUTPUT_IP=${OUTPUT_IP:-${CURRENT_OUTPUT_IP:-192.168.1.11}}

        # Mock mode
        echo ""
        read -p "Use mock mode for testing? (y/n) [n]: " -n 1 -r < /dev/tty
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            USE_MOCK="True"
        else
            USE_MOCK="False"
        fi
    fi

    # Backup existing config
    if [ -f "config.py" ]; then
        cp config.py config.py.backup
        print_info "Backed up existing config to config.py.backup"
    fi

    # Update config.py with sed
    if [ -f "config.py" ]; then
        # Update input_ip
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS sed syntax
            sed -i '' "s/input_ip: \"[^\"]*\"/input_ip: \"$INPUT_IP\"/" config.py
            sed -i '' "s/output_ip: \"[^\"]*\"/output_ip: \"$OUTPUT_IP\"/" config.py
            sed -i '' "s/use_mock: .*/use_mock: $USE_MOCK/" config.py
        else
            # Linux sed syntax
            sed -i "s/input_ip: \"[^\"]*\"/input_ip: \"$INPUT_IP\"/" config.py
            sed -i "s/output_ip: \"[^\"]*\"/output_ip: \"$OUTPUT_IP\"/" config.py
            sed -i "s/use_mock: .*/use_mock: $USE_MOCK/" config.py
        fi

        print_success "Configuration updated:"
        echo "  Input PLC IP:  $INPUT_IP"
        echo "  Output PLC IP: $OUTPUT_IP"
        echo "  Mock Mode:     $USE_MOCK"
    else
        print_warning "config.py not found - please configure manually"
    fi
fi

echo ""

# Setup auto-start on boot
echo ""
if [ "$OS" == "linux" ]; then
    echo "Linux auto-start options:"
    echo "  1) Terminal window (shows TUI on login)"
    echo "  2) Background service (headless, logs to journalctl)"
    echo "  3) No auto-start"
    read -p "Choose option [1/2/3]: " -n 1 -r < /dev/tty
    echo

    if [[ $REPLY == "1" ]]; then
        # Desktop autostart - opens terminal with TUI
        AUTOSTART_DIR="$HOME/.config/autostart"
        mkdir -p "$AUTOSTART_DIR"

        # Detect available terminal emulator
        TERMINAL_CMD=""
        if command -v lxterminal &> /dev/null; then
            # Raspberry Pi OS / LXDE default
            TERMINAL_CMD="lxterminal --command=\"bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python main.py; exec bash'\""
            print_info "Detected: lxterminal (Raspberry Pi OS)"
        elif command -v x-terminal-emulator &> /dev/null; then
            # Debian default alternative
            TERMINAL_CMD="x-terminal-emulator -e bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python main.py; exec bash'"
            print_info "Detected: x-terminal-emulator"
        elif command -v gnome-terminal &> /dev/null; then
            # GNOME
            TERMINAL_CMD="gnome-terminal -- bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python main.py; exec bash'"
            print_info "Detected: gnome-terminal"
        elif command -v xfce4-terminal &> /dev/null; then
            # XFCE
            TERMINAL_CMD="xfce4-terminal -e \"bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python main.py; exec bash'\""
            print_info "Detected: xfce4-terminal"
        elif command -v mate-terminal &> /dev/null; then
            # MATE
            TERMINAL_CMD="mate-terminal -e \"bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python main.py; exec bash'\""
            print_info "Detected: mate-terminal"
        else
            print_error "No supported terminal emulator found"
            print_warning "Please install lxterminal: sudo apt-get install lxterminal"
            TERMINAL_CMD="lxterminal --command=\"bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python main.py; exec bash'\""
        fi

        AUTOSTART_FILE="$AUTOSTART_DIR/bellafruita.desktop"
        cat > "$AUTOSTART_FILE" << EOF
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
        print_info "To disable: rm ~/.config/autostart/bellafruita.desktop"

    elif [[ $REPLY == "2" ]]; then
        # Systemd service - background
        SERVICE_FILE="$HOME/.config/systemd/user/bellafruita.service"
        mkdir -p "$HOME/.config/systemd/user"

        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Bella Fruita Control System
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

        systemctl --user daemon-reload
        systemctl --user enable bellafruita.service
        print_success "Systemd service installed and enabled"
        print_info "Start with: systemctl --user start bellafruita"
        print_info "View logs with: journalctl --user -u bellafruita -f"
    else
        print_info "No auto-start configured"
    fi
elif [ "$OS" == "macos" ]; then
    read -p "Would you like to auto-start on login with Terminal window? (y/n) " -n 1 -r < /dev/tty
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        PLIST_FILE="$HOME/Library/LaunchAgents/com.bellafruita.app.plist"
        mkdir -p "$HOME/Library/LaunchAgents"

        # Create a launcher script that opens Terminal
        LAUNCHER_SCRIPT="$INSTALL_DIR/launch_terminal.sh"
        cat > "$LAUNCHER_SCRIPT" << 'EOF'
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
        cat > "$PLIST_FILE" << EOF
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
cat > "$INSTALL_DIR/start.sh" << 'EOF'
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

        ttyd -p $TTYD_PORT -t fontSize=14 -t theme='{"background": "#1e1e1e"}' bash -c "cd $(pwd) && source venv/bin/activate && python main.py $*; echo 'Application exited. Press any key to close...'; read -n 1" &
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
            python main.py "$@"
        fi
    fi
else
    # ttyd not available, run normally
    echo "ttyd not installed - running in local mode only"
    echo "To enable remote viewing, install ttyd: sudo apt-get install ttyd (Linux) or brew install ttyd (macOS)"
    echo ""
    python main.py "$@"
fi
EOF
chmod +x "$INSTALL_DIR/start.sh"

# Create update script (updates code only, preserves config)
cat > "$INSTALL_DIR/update.sh" << 'EOF'
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
    if [ -f "$HOME/.config/autostart/bellafruita.desktop" ]; then
        print_info "Desktop autostart enabled:"
        echo "  Terminal window will open on login"
        echo "  To disable: rm ~/.config/autostart/bellafruita.desktop"
        echo ""
    elif [ -f "$HOME/.config/systemd/user/bellafruita.service" ]; then
        print_info "Systemd service commands:"
        echo "  systemctl --user start bellafruita"
        echo "  systemctl --user stop bellafruita"
        echo "  systemctl --user status bellafruita"
        echo "  journalctl --user -u bellafruita -f"
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
