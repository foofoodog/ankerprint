import binascii
import crcmod
import struct
import re
import logging as log

def enhex(s):
    return binascii.b2a_hex(s).decode()

def unhex(s):
    return binascii.a2b_hex(s)

def b64e(s):
    return binascii.b2a_base64(s).decode().strip()

def b64d(s):
    return binascii.a2b_base64(s)

def ppcs_crc16(data):
    crc16 = crcmod.mkCrcFun(0x11021, rev=False, initCrc=0x0000, xorOut=0x0000)
    return struct.pack("<H", crc16(data))

def split_chunks(data, chunksize):
    data = data[:]
    res = []
    while data:
        res.append(data[:chunksize])
        data = data[chunksize:]
    return res

_TIME_PATTERN = re.compile(r";\s*estimated printing time[^=]*=\s*(.*)", re.IGNORECASE)
_TIME_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}

def _parse_time_seconds(time_str):
    total = 0
    for value, unit in re.findall(r"(\d+)\s*([dhms])", time_str, re.IGNORECASE):
        total += int(value) * _TIME_UNITS[unit.lower()]
    return total or None

def patch_gcode_time(data: bytes) -> bytes:
    """Insert ;TIME:<seconds> before the first G28 if not already present."""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return data

    lines = text.splitlines(keepends=True)
    g28_index = None
    seconds = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.upper().startswith(";TIME:"):
            return data
        if g28_index is None and stripped.upper().startswith("G28"):
            g28_index = i
        m = _TIME_PATTERN.search(line)
        if m and seconds is None:
            seconds = _parse_time_seconds(m.group(1))
        if g28_index is not None and seconds is not None:
            break

    if g28_index is None or seconds is None:
        return data

    lines.insert(g28_index, f";TIME:{seconds}\n")
    return "".join(lines).encode("utf-8")
