# Bella Fruita - Apple Sorting Machine Control System

Industrial PLC control system for automated apple sorting operations with real-time TUI monitoring.

## Overview

Bella Fruita controls conveyor feeders for an apple sorting machine using PLC ladder logic implemented in Python. The system communicates with Modbus PLC terminals to manage bin movement, safety interlocks, and operator interfaces with a live terminal-based UI.

## Features

- ✅ **PLC Ladder Logic** - Rule-based control system matching industrial PLC behavior
- ✅ **Real-time TUI** - Live monitoring via Textual terminal interface
- ✅ **Remote Web Access** - View and control TUI from any browser on port 7681
- ✅ **Modbus Communication** - Integration with industrial PLC hardware
- ✅ **Safety Interlocks** - Emergency stop, trip signals, and safety checks
- ✅ **Persistent Logging** - System events survive crashes and restarts
- ✅ **Auto-start on Boot** - Runs on login with visible terminal (Raspberry Pi & desktop Linux)
- ✅ **One-command Install/Update** - GitHub-based deployment

## Quick Install

### Interactive Mode (Recommended)
```bash
bash <(curl -sSL https://raw.githubusercontent.com/dwainm/bellafruita/master/install.sh)
```

The installer will ask you for:
- Site/Installation name (displayed in TUI)
- Input PLC IP address
- Output PLC IP address
- Auto-start preference (terminal window or background service)

### Non-Interactive Mode (Automated Deployment)
```bash
INPUT_IP=192.168.1.10 OUTPUT_IP=192.168.1.11 \
  bash <(curl -sSL https://raw.githubusercontent.com/dwainm/bellafruita/master/install.sh)
```

Or skip configuration entirely:
```bash
SKIP_CONFIG=true bash <(curl -sSL https://raw.githubusercontent.com/dwainm/bellafruita/master/install.sh)
```

**What gets installed:**
1. ✅ Checks Python 3.9+ and git
2. ✅ Clones repository to `~/bellafruita`
3. ✅ Creates Python virtual environment
4. ✅ Installs all dependencies
5. ✅ Configures Modbus IP addresses
6. ✅ Creates helper scripts (`start.sh`, `update.sh`, `update_ip.sh`)
7. ✅ (Optional) Sets up auto-start on boot

**Raspberry Pi OS:** Automatically detects and uses `lxterminal` for display.

## Running

### Manual Start
```bash
cd ~/bellafruita
./start.sh
```

The system automatically enables **remote viewing** of the TUI via web browser:
- **Local access**: http://localhost:7681
- **Remote access**: http://YOUR_RASPBERRY_PI_IP:7681

This allows you to monitor the system from any device with a web browser (phone, tablet, laptop) without SSH. The remote view is read/write enabled, so you can interact with the TUI remotely.

### Auto-Start on Boot (Configured during installation)

#### Linux - Option 1: Terminal Window (Recommended for operator stations)
Opens a terminal window on login with the TUI visible.

**Supported on:**
- Raspberry Pi OS (uses lxterminal)
- Ubuntu (uses gnome-terminal)
- Debian (uses x-terminal-emulator)
- XFCE, MATE, and other desktop environments

```bash
# Installed to: ~/.config/autostart/bellafruita.desktop

# To disable auto-start
rm ~/.config/autostart/bellafruita.desktop
```

The installer automatically detects which terminal emulator you have installed.

#### Linux - Option 2: Background Service (For headless servers)
```bash
systemctl --user start bellafruita    # Start now
systemctl --user stop bellafruita     # Stop
systemctl --user status bellafruita   # Check status
journalctl --user -u bellafruita -f   # View logs
```

#### macOS (LaunchAgent)
Opens a Terminal window on login:
```bash
launchctl start com.bellafruita.app   # Start now
launchctl stop com.bellafruita.app    # Stop

# Disable auto-start
launchctl unload ~/Library/LaunchAgents/com.bellafruita.app.plist

# Re-enable auto-start
launchctl load ~/Library/LaunchAgents/com.bellafruita.app.plist
```

## Updating

### Update Code (Preserves your IP configuration)
```bash
cd ~/bellafruita
./update.sh
```

### Change PLC IP Addresses
```bash
cd ~/bellafruita
./update_ip.sh
```

## System Requirements

- **OS**: Raspberry Pi OS, Ubuntu, Debian, macOS
- **Python**: 3.9 or higher
- **Hardware**: Raspberry Pi 3B+ or better (Pi 4 recommended)
- **Network**: Ethernet connection to Modbus PLCs
- **Display**: 1280x720 or higher for TUI

## Architecture

### Control Logic
- `rules.py` - PLC ladder logic rules (safety, sequencing, modes)
- `io_mapping.py` - Modbus address mapping for I/O
- `src/rule_engine.py` - Rule evaluation engine
- `src/mem.py` - Machine state memory

### Communication
- `src/modbus/` - Modbus TCP client and API
- Supports both real hardware and mock mode for testing

### User Interface
- `src/tui.py` - Textual-based terminal UI
- Real-time display of I/O, mode, logs, and active rules

### State Management
- Persistent event logs in `logs/system_events.jsonl`
- Automatic log rotation (keeps 2 files)
- State machine for operational modes

## Configuration

Edit `~/bellafruita/config.py`:

```python
site_name: "Bella Fruita"    # Site name displayed in TUI
modbus:
  input_ip: "192.168.1.10"   # Input PLC IP
  output_ip: "192.168.1.11"  # Output PLC IP

use_mock: False  # Set True for testing without hardware
```

Or use the configuration utility:
```bash
cd ~/bellafruita
./update_ip.sh
```

## Operational Modes

- **READY** - System ready for operation
- **MOVING_C3_TO_C2** - Moving bin from conveyor 3 to 2
- **MOVING_C2_TO_PALM** - Moving bin from conveyor 2 to PALM
- **MOVING_BOTH** - Moving both bins simultaneously
- **ERROR_COMMS** - Communications failure (requires reset)
- **ERROR_ESTOP** - Emergency stop active
- **ERROR_SAFETY** - Safety violation (trip signals)

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design

## Troubleshooting

### Can't Access Remote Web UI
```bash
# Find your Raspberry Pi's IP address
hostname -I

# Check if ttyd is running
ps aux | grep ttyd

# Check if port 7681 is open
nc -zv localhost 7681

# Install ttyd if missing
sudo apt-get install ttyd  # Raspberry Pi/Debian/Ubuntu
brew install ttyd          # macOS

# Allow port through firewall (if enabled)
sudo ufw allow 7681/tcp
```

**Note**: Remote viewing requires `ttyd` to be installed. The installer attempts to install it automatically.

### Can't Connect to PLC
```bash
ping 192.168.1.10  # Test network
nc -zv 192.168.1.10 502  # Test Modbus port
```

### Terminal Won't Open on Boot (Raspberry Pi)
```bash
which lxterminal  # Check if installed
sudo apt-get install lxterminal  # Install if needed
```

### Python Too Old
```bash
python3 --version  # Check version (need 3.9+)
# Upgrade Raspberry Pi OS to Bullseye or newer
```

### View Logs
```bash
cd ~/bellafruita
tail -f logs/system_events.jsonl
```

System logs are saved to:
- `~/bellafruita/logs/system_events.jsonl` (current)
- `~/bellafruita/logs/system_events.jsonl.old` (previous rotation)

Logs persist across restarts and crashes.

## Development

### Mock Mode (Test Without Hardware)
```bash
cd ~/bellafruita
python main.py --mock
```

### Manual Installation
```bash
git clone https://github.com/YOUR_USERNAME/bellafruita.git
cd bellafruita
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Technology Stack

- **Python 3.9+** - Core application
- **PyModbus** - Modbus TCP communication
- **Textual** - Terminal UI framework
- **Procon Modbus Terminals** - Industrial PLC hardware

## Uninstall

```bash
# Stop service (if running)
systemctl --user stop bellafruita  # Linux
launchctl stop com.bellafruita.app  # macOS

# Disable auto-start
rm ~/.config/autostart/bellafruita.desktop  # Linux
launchctl unload ~/Library/LaunchAgents/com.bellafruita.app.plist  # macOS

# Remove installation
rm -rf ~/bellafruita
```

## Support

- **GitHub Issues**: https://github.com/YOUR_USERNAME/bellafruita/issues
- **Installation Help**: See INSTALL.md

## License

Industrial use project
