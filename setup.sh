#!/usr/bin/env bash
# Fast launcher for AnkerPrint: sets up venv if needed, scans LAN, and shows help.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment in ./venv..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

echo "========================================================="
echo "  AnkerPrint - Lean LAN & BLE CLI for AnkerMake M5 / M5C"
echo "========================================================="
./ankerprint.py scan || true
echo ""
./ankerprint.py --help
