#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [ ! -d "venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
fi

echo "[*] Installing dependencies & PyInstaller..."
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install pyinstaller

echo "[*] Compiling standalone executable..."
./venv/bin/pyinstaller --clean -y \
    --onefile \
    --name ankerprint \
    --collect-all bleak \
    --collect-all Cryptodome \
    --collect-all tinyec \
    ankerprint.py

echo "[*] Build complete: dist/ankerprint"
