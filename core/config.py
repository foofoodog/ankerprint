import json
import os
from pathlib import Path

def get_config_dir() -> Path:
    base = os.getenv("XDG_CONFIG_HOME")
    if base:
        d = Path(base) / "ankerprint"
    else:
        d = Path.home() / ".config" / "ankerprint"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_printers_file() -> Path:
    return get_config_dir() / "printers.json"

def load_printers():
    pf = get_printers_file()
    if pf.exists():
        try:
            with open(pf, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Fallback to existing ankerctl default.json if present
    for old_path in [
        Path.home() / ".config" / "ankerctl" / "default.json",
        Path.home() / "AppData" / "Local" / "ankerctl" / "ankerctl" / "default.json",
    ]:
        if old_path.exists():
            try:
                with open(old_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    printers = []
                    for p in data.get("printers", []):
                        printers.append({
                            "name": p.get("name", "AnkerMake"),
                            "duid": p.get("p2p_duid") or p.get("sn", ""),
                            "sn": p.get("sn", ""),
                            "ip": p.get("ip_addr", ""),
                            "model": p.get("model", "M5C")
                        })
                    if printers:
                        save_printers(printers)
                        return printers
            except Exception:
                pass
    return []

def save_printers(printers):
    pf = get_printers_file()
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(printers, f, indent=2)
