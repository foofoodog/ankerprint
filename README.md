# AnkerPrint

**AnkerPrint** is a lean, zero-server CLI tool and slicer integration for **AnkerMake M5 and M5C** 3D printers.

Unlike bloated suites that run background web daemons, RTSP video relays, Docker containers, or cloud proxies, AnkerPrint strips away everything non-essential:

- **Zero Background Daemons & Zero Servers**: No Flask, no Mosquitto MQTT, no RTSP/OpenCV/FFmpeg video, no Docker. Runs only when invoked.
- **Bluetooth Low Energy (BLE) Provisioning**: Scan for unconfigured or factory-reset M5/M5C printers, pair, and configure Wi-Fi credentials directly over Bluetooth.
- **Instant LAN Discovery**: Broadcasts UDP search packets on port `32108` and saves discovered printers automatically.
- **Direct LAN G-code Streaming**: Direct binary PPPP file upload and print initiation over local UDP.
- **Automatic Time Patching**: Injects standard `;TIME:<seconds>` metadata into G-code for accurate on-printer countdown display.
- **Slicer Ready**: Native post-processing script integration for **PrusaSlicer**, **OrcaSlicer**, and headless CLI print pipelines.
- **Cross-Platform**: Supports native Linux, WSL (with automatic Windows-to-WSL path translation), and Windows.

---

## Quickstart

### 1. Installation

```bash
git clone https://github.com/foofoodog/ankerprint.git
cd ankerprint

# Quick launcher (automatically creates venv and installs dependencies):
./setup.sh
```

Or manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Discover Printers on Local Network

```bash
./ankerprint.py scan
```
Output:
```text
Scanning local network for AnkerMake printers...
Found 2 online printer(s):
  [0] USPRAKM-030549-UZSES at 192.168.4.79
  [1] USPRAKM-015689-GMMPU at 192.168.4.29
Saved printer list to ~/.config/ankerprint/printers.json
```

---

## Usage

### Direct Printing

Stream a G-code file directly over LAN UDP to the printer and start the job:

```bash
# Print to default printer (index 0)
./ankerprint.py print model.gcode

# Print to specific printer index
./ankerprint.py -p 1 print model.gcode

# Dry run: Upload to printer storage without starting print
./ankerprint.py print -n model.gcode
```

### Direct G-code Commands

Send arbitrary G-code commands or common operations directly to the printer over LAN UDP without opening a slicer or web UI:

```bash
# Home all axes (G28)
./ankerprint.py gcode --home

# Run auto bed leveling (G29)
./ankerprint.py gcode --level

# Home specific axes or disable steppers
./ankerprint.py gcode --home-xy
./ankerprint.py gcode --home-z
./ankerprint.py gcode --motors-off

# Send custom G-code command sequences
./ankerprint.py gcode "G28" "G1 Z25 F1000"
./ankerprint.py gcode "M104 S210" "M140 S60"

# Target specific printer by index
./ankerprint.py -p 1 gcode --home

# Dry run: Verify transfer without executing commands
./ankerprint.py gcode --home -n

# Pipe G-code from standard input
echo "G28" | ./ankerprint.py gcode -
```

### Bluetooth Low Energy (BLE) Wi-Fi Provisioning

Configure a new or factory-reset printer without the mobile app:

```bash
# 1. Scan for nearby AnkerMake BLE advertisements
./ankerprint.py ble scan

# 2. Pair with the printer (press printer button if requested)
./ankerprint.py ble pair <BLE_MAC_ADDRESS>

# 3. Send Wi-Fi credentials to join local network
./ankerprint.py ble provision <BLE_MAC_ADDRESS> --ssid "MyWiFi" --password "secret"
```

---

## PrusaSlicer & OrcaSlicer Integration

### Linux / macOS / WSL GUI Setup
In PrusaSlicer or OrcaSlicer:
1. Go to **Print Settings** -> **Output options**.
2. In the **Post-processing scripts** box, add the absolute path:
   ```text
   /path/to/ankerprint/scripts/prusa_print.sh
   ```
   *(For targeting a secondary printer, pass the index: `/path/to/ankerprint/scripts/prusa_print.sh 1`)*
3. Exporting G-code or clicking Send will now automatically upload and start the print!

### Windows Native GUI Setup
In PrusaSlicer on Windows:
1. Go to **Print Settings** -> **Output options** -> **Post-processing scripts**.
2. Add:
   ```text
   "C:\path\to\ankerprint\scripts\prusa_print.cmd"
   ```
   The `.cmd` wrapper automatically detects whether to run native Windows Python or route through WSL using `wslpath`.

### Headless CLI Slicer Automation
To slice and print entirely from the terminal:
```bash
prusa-slicer --export-gcode model.stl -o model.gcode
./scripts/prusa_print.sh model.gcode
```

---

## Hardware Control Note (No Cloud/Server Needed)
Because AnkerPrint does not run a daemon or cloud relay, in-flight pause and cancellation are handled directly on the hardware:
- **M5C**: Single button press = **Pause / Resume**; 3-second hold = **Cancel Print**.
- **M5**: Use the built-in touchscreen display to pause, resume, or abort.

---

## Running Tests

AnkerPrint includes a unit test suite covering CLI commands, flags, G-code generation, and network mock workflows:

```bash
# Run tests with pytest
./venv/bin/pytest

# Or with python's built-in unittest runner
./venv/bin/python -m unittest discover tests
```

---

## Platform Compatibility and Caveats

AnkerPrint runs across Linux, native Windows, and Windows Subsystem for Linux (WSL). Because the core tool relies on standard UDP sockets and lightweight Python libraries, behavior is nearly identical across platforms, with a few environment-specific details:

### WSL2 Subnet Isolation on Scan
- By default, WSL2 uses NAT virtual networking. UDP broadcast packets (`255.255.255.255:32108`) sent from inside WSL2 cannot reach physical Wi-Fi devices on your local subnet unless WSL2 is configured with mirrored networking.
- If `scan` does not discover printers inside WSL2, add `networkingMode=mirrored` under `[wsl2]` in `C:\Users\<User>\.wslconfig`, or run `scan` once from native Windows PowerShell / CMD to populate `printers.json`. Direct printing and G-code streaming work normally once the printer IP is cached.

### Bluetooth (BLE) in Virtualized Environments
- BLE features (`ankerprint ble scan / pair / provision`) use the `bleak` library, which communicates directly with host Bluetooth adapters (via WinRT on Windows and BlueZ on Linux).
- Virtual machines and default WSL2 environments do not have direct access to host Bluetooth adapters without USB passthrough (such as `usbipd-win`). For initial BLE provisioning, run AnkerPrint on native Windows or native Linux.

### Windows Firewall Configuration
- When running AnkerPrint for the first time on Windows, Windows Defender Firewall may prompt for network permissions when Python binds to an ephemeral UDP port.
- Allow access on Private networks so printer UDP responses on port 32108 can reach the CLI.

### Native Windows Setup
- On Linux and WSL, `./setup.sh` automatically initializes the virtual environment.
- On native Windows, set up the virtual environment manually:
  ```powershell
  python -m venv venv
  .\venv\Scripts\pip install -r requirements.txt
  python ankerprint.py scan
  ```

---

## License
GNU General Public License v3.0 (GPL-3.0). See [LICENSE](LICENSE) for details.
