#!/usr/bin/env bash
# PrusaSlicer Post-Processing & CLI Automation Script
# Compatible with native Linux, WSL (Windows Subsystem for Linux), and macOS.
#
# Usage:
#   In CLI automation:   ./scripts/prusa_print.sh [printer_index] /path/to/job.gcode
#   In PrusaSlicer GUI:  Add this script path to Print Settings -> Output options -> Post-processing scripts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PRINTER_INDEX=0

if [ "$#" -ge 2 ]; then
    PRINTER_INDEX="$1"
    GCODE_FILE="$2"
else
    GCODE_FILE="$1"
fi

if [ -z "$GCODE_FILE" ]; then
    echo "Usage: prusa_print.sh [printer_index] <file.gcode>" >&2
    exit 1
fi

# Convert Windows paths (e.g. C:\... or containing backslashes) when running under WSL
if [[ "$GCODE_FILE" =~ ^[A-Za-z]: || "$GCODE_FILE" == *\\* ]]; then
    if command -v wslpath >/dev/null 2>&1; then
        GCODE_FILE="$(wslpath -u "$GCODE_FILE")"
    fi
fi

if [ ! -f "$GCODE_FILE" ]; then
    echo "Error: G-code file not found: $GCODE_FILE" >&2
    exit 1
fi

echo "========================================================="
echo "  AnkerMake LAN Direct Print (Target: Printer $PRINTER_INDEX)"
echo "  File: $GCODE_FILE"
echo "========================================================="

# Execute via ankerprint (which automatically uses the virtual environment)
if [ -f "$REPO_DIR/ankerprint.py" ]; then
    "$REPO_DIR/ankerprint.py" -p "$PRINTER_INDEX" print "$GCODE_FILE"
elif [ -f "$REPO_DIR/ankerctl.py" ]; then
    "$REPO_DIR/ankerctl.py" -p "$PRINTER_INDEX" print "$GCODE_FILE"
else
    echo "Error: ankerprint.py not found in $REPO_DIR" >&2
    exit 1
fi
