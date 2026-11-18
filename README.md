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

## License
GNU General Public License v3.0 (GPL-3.0). See [LICENSE](LICENSE) for details.
