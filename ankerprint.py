#!/usr/bin/env python3
import os
import sys
import json
import uuid
import time
import random
import logging
from pathlib import Path

# Auto-detect local venv on Linux, WSL, and Windows
if sys.prefix == sys.base_prefix:
    _repo = Path(__file__).resolve().parent
    _candidates = [
        _repo / "venv" / "bin" / "python",
        _repo / "venv" / "Scripts" / "python.exe",
        _repo / ".venv" / "bin" / "python",
        _repo / ".venv" / "Scripts" / "python.exe",
    ]
    for _vpy in _candidates:
        if _vpy.exists() and os.access(_vpy, os.X_OK):
            os.execv(str(_vpy), [str(_vpy)] + sys.argv)
            break

import click
from rich import print as rprint
from tqdm import tqdm

from core import config
from core import ble
from core.ppppapi import AnkerPPPPApi, FileUploadInfo, PPPP_LAN_PORT, PPPPState, PPPPError
from core.pppp_packets import Duid, PktLanSearch, PktPunchPkt, FileTransfer, P2PCmdType
from core.util import patch_gcode_time, split_chunks

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("ankerprint")


def _send_xzyh_with_retry(api, data, cmd, reply_timeout=3.0, chan=0, retries=2):
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return api.send_xzyh(data, cmd=cmd, timeout=reply_timeout)
        except TimeoutError as exc:
            is_drw_timeout = "PPPP DRW ACK" in str(exc)
            if not is_drw_timeout or attempt >= attempts:
                raise
            log.warning(f"Retrying handshake send after transport timeout (attempt {attempt + 1}/{attempts})")
            api.reset_chan_tx(chan=chan)


def _pppp_send_file_handshake(api, fui, reply_timeout=3.0):
    file_uuid = (fui.machine_id or "").strip()
    if not file_uuid or file_uuid == "-":
        file_uuid = uuid.uuid4().hex.upper()
        fui.machine_id = file_uuid

    payload = {
        "uuid": file_uuid,
        "device": "ankerprint",
        "flag": 0,
        "random": random.getrandbits(64),
        "timeout": 40,
        "total_timeout": 120,
    }

    log.debug("Requesting file transfer handshake...")
    _send_xzyh_with_retry(
        api, json.dumps(payload).encode(), cmd=P2PCmdType.P2P_SEND_FILE, reply_timeout=reply_timeout, chan=0
    )

    try:
        reply = api.recv_xzyh(chan=0, timeout=reply_timeout)
    except TimeoutError:
        reply = None

    if not reply:
        log.debug("No P2P_SEND_FILE reply; falling back to legacy handshake")
        api.send_xzyh(file_uuid[:16].encode(), cmd=P2PCmdType.P2P_SEND_FILE, timeout=reply_timeout)
        return

    if reply.data:
        code = int.from_bytes(reply.data[:4], "little", signed=False)
        if code != 0:
            log.debug(f"P2P_SEND_FILE reply error 0x{code:08x}; falling back to legacy handshake")
            api.send_xzyh(file_uuid[:16].encode(), cmd=P2PCmdType.P2P_SEND_FILE, timeout=reply_timeout)


def _retry_file_transfer_data(api, chunk, pos, reply_timeout=15.0, retries=2):
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return api.aabb_request(chunk, frametype=FileTransfer.DATA, pos=pos, timeout=reply_timeout)
        except TimeoutError as exc:
            is_drw_timeout = "PPPP DRW ACK" in str(exc)
            if not is_drw_timeout or attempt >= attempts:
                raise
            log.warning(f"Retrying file transfer chunk at pos {pos} after transport timeout (attempt {attempt + 1}/{attempts})")
            api.reset_chan_tx(chan=1)


def _get_target_printer(ctx):
    printers = config.load_printers()
    p_idx = ctx.obj.get("printer_index", 0)
    
    if not printers:
        rprint("[yellow]No printers in cache. Running quick scan...[/yellow]")
        cmd_scan()
        printers = config.load_printers()
        
    if not printers:
        rprint("[bold red]Error: No printers available on local network.[/bold red]")
        sys.exit(1)
        
    if p_idx < 0 or p_idx >= len(printers):
        rprint(f"[bold red]Error: Printer index {p_idx} out of range (available: 0..{len(printers)-1})[/bold red]")
        sys.exit(1)
        
    return printers[p_idx]


def stream_gcode_to_printer(ip, duid, gcode_bytes, filename="job.gcode", no_act=False, desc="Streaming G-code"):
    file_uuid = uuid.uuid4().hex.upper()
    fui = FileUploadInfo.from_data(gcode_bytes, filename, user_name="ankerprint", user_id="-", machine_id=file_uuid)
    
    api = AnkerPPPPApi.open_lan(Duid.from_string(duid), host=ip)
    api.connect_lan_search()
    api.start()
    
    deadline = time.monotonic() + 10.0
    connected = False
    while time.monotonic() < deadline:
        if api.state == PPPPState.Connected:
            connected = True
            break
        time.sleep(0.05)
        
    if not connected:
        rprint(f"[bold red]Error: Could not connect to printer at {ip}:32108.[/bold red]")
        api.stop()
        sys.exit(1)
        
    try:
        rprint("[*] Handshaking with printer file subsystem...")
        _pppp_send_file_handshake(api, fui, reply_timeout=3.0)
        
        rprint("[*] Sending file metadata...")
        api.aabb_request(bytes(fui), frametype=FileTransfer.BEGIN, timeout=15.0)
        
        chunks = split_chunks(gcode_bytes, 1024 * 32)
        pos = 0
        total = len(gcode_bytes)
        
        show_bar = total > 1024
        with tqdm(unit="b", total=total, unit_scale=True, unit_divisor=1024, desc=desc, disable=not show_bar) as bar:
            for chunk in chunks:
                _retry_file_transfer_data(api, chunk, pos, reply_timeout=15.0)
                pos += len(chunk)
                if show_bar:
                    bar.update(len(chunk))
                
        if no_act:
            try:
                api.aabb_request(b"", frametype=FileTransfer.ABORT, timeout=5.0)
            except Exception:
                pass
            rprint("[green]Upload complete (dry run, transfer closed without executing).[/green]")
        else:
            api.aabb_request(b"", frametype=FileTransfer.END, timeout=15.0)
            rprint("[bold green]Success: Command sent to printer.[/bold green]")
    finally:
        api.stop()


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("--printer", "-p", type=int, default=0, help="Printer index (default: 0)")
@click.pass_context
def cli(ctx, printer):
    """AnkerPrint - Lean, zero-server CLI for AnkerMake M5 / M5C printers."""
    ctx.ensure_object(dict)
    ctx.obj["printer_index"] = printer


@cli.command("scan", help="Scan local network for online AnkerMake printers")
def cmd_scan():
    rprint("[bold blue]Scanning local network for AnkerMake printers...[/bold blue]")
    api = AnkerPPPPApi.open_broadcast()
    api.state = PPPPState.Connected
    
    discovered = []
    seen = set()
    deadline = time.monotonic() + 1.5
    
    try:
        api.send(PktLanSearch())
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                resp = api.recv(timeout=remaining)
            except TimeoutError:
                break
            if not isinstance(resp, PktPunchPkt):
                continue
            
            duid_str = str(resp.duid)
            ip_str = str(api.addr[0])
            if (duid_str, ip_str) in seen:
                continue
            seen.add((duid_str, ip_str))
            discovered.append({"name": f"AnkerMake ({duid_str[:10]})", "duid": duid_str, "ip": ip_str})
    finally:
        api.stop()
        
    if not discovered:
        rprint("[bold red]No printers responded. Check if printer is on the same Wi-Fi subnet.[/bold red]")
        return
        
    config.save_printers(discovered)
    rprint(f"[bold green]Found {len(discovered)} online printer(s):[/bold green]")
    for i, p in enumerate(discovered):
        rprint(f"  [{i}] [cyan]{p['duid']}[/cyan] at [green]{p['ip']}[/green]")
    rprint("[dim]Saved printer list to ~/.config/ankerprint/printers.json[/dim]")


@cli.command("print", help="Upload G-code file and start printing (PrusaSlicer ready)")
@click.argument("file", type=click.File("rb"), metavar="<file.gcode>")
@click.option("--no-act", "-n", is_flag=True, help="Upload only without starting print")
@click.pass_context
def cmd_print(ctx, file, no_act):
    target = _get_target_printer(ctx)
    rprint(f"[bold blue]Targeting Printer [{ctx.obj['printer_index']}]: {target['duid']} at {target['ip']}[/bold blue]")
    raw_data = file.read()
    patched_data = patch_gcode_time(raw_data)
    stream_gcode_to_printer(
        target["ip"], target["duid"], patched_data,
        filename=Path(file.name).name, no_act=no_act, desc="Streaming G-code"
    )


@cli.command("gcode", help="Send G-code command(s) directly to printer (e.g. G28, G29, auto-level)")
@click.argument("commands", nargs=-1)
@click.option("--home", is_flag=True, help="Shortcut to home all axes (G28)")
@click.option("--home-xy", is_flag=True, help="Shortcut to home X and Y axes (G28 X Y)")
@click.option("--home-z", is_flag=True, help="Shortcut to home Z axis (G28 Z)")
@click.option("--level", is_flag=True, help="Shortcut to run auto bed leveling (G29)")
@click.option("--motors-off", is_flag=True, help="Shortcut to disable stepper motors (M84)")
@click.option("--no-act", "-n", is_flag=True, help="Dry run: upload command without executing")
@click.pass_context
def cmd_gcode(ctx, commands, home, home_xy, home_z, level, motors_off, no_act):
    cmd_list = []
    
    # Process shortcut flags
    if home:
        cmd_list.append("G28")
    if home_xy:
        cmd_list.append("G28 X Y")
    if home_z:
        cmd_list.append("G28 Z")
    if level:
        cmd_list.append("G29")
    if motors_off:
        cmd_list.append("M84")
        
    # Process positional arguments or stdin
    if commands:
        if len(commands) == 1 and commands[0] == "-":
            stdin_text = sys.stdin.read()
            for line in stdin_text.splitlines():
                line = line.strip()
                if line and not line.startswith(";"):
                    cmd_list.append(line)
        else:
            for c in commands:
                for line in c.splitlines():
                    line = line.strip()
                    if line:
                        cmd_list.append(line)
                        
    if not cmd_list:
        rprint("[bold yellow]No G-code command provided. Specify commands or options like --home, --level.[/bold yellow]")
        rprint("Examples:")
        rprint("  ankerprint gcode --home")
        rprint("  ankerprint gcode --level")
        rprint('  ankerprint gcode "G28" "G1 Z10 F1000"')
        rprint('  ankerprint gcode "M104 S200" "M140 S60"')
        return
        
    target = _get_target_printer(ctx)
    rprint(f"[bold blue]Targeting Printer [{ctx.obj['printer_index']}]: {target['duid']} at {target['ip']}[/bold blue]")
    rprint(f"[cyan]Executing G-code:[/cyan] {', '.join(cmd_list)}")
    
    # Construct minimal standalone G-code buffer
    buffer_lines = [
        "; generated by ankerprint gcode",
        "; estimated printing time = 10s",
        ";TIME:10",
        "G21 ; millimeter units",
        "G90 ; absolute coordinates",
    ]
    buffer_lines.extend(cmd_list)
    gcode_bytes = ("\n".join(buffer_lines) + "\n").encode("utf-8")
    
    stream_gcode_to_printer(
        target["ip"], target["duid"], gcode_bytes,
        filename="direct_cmd.gcode", no_act=no_act, desc="Sending G-code"
    )


@cli.group("ble", help="Bluetooth Low Energy (BLE) Wi-Fi tools")
def grp_ble():
    pass

@grp_ble.command("scan", help="Scan for nearby AnkerMake BLE devices")
@click.option("--timeout", "-t", default=4.0, type=float, help="Scan timeout in seconds")
def cmd_ble_scan(timeout):
    devices = ble.ble_scan(timeout=timeout)
    if not devices:
        rprint("[yellow]No AnkerMake BLE devices found nearby.[/yellow]")
        return
    rprint(f"[bold green]Found {len(devices)} device(s):[/bold green]")
    for d in devices:
        rprint(f"  • [cyan]{d['name']}[/cyan] (MAC: [green]{d['address']}[/green], RSSI: {d['rssi']} dBm)")

@grp_ble.command("pair", help="Initiate BLE pairing with printer")
@click.argument("address", required=True)
@click.option("--timeout", "-t", default=15.0, type=float, help="Pairing timeout in seconds")
def cmd_ble_pair(address, timeout):
    rprint(f"Connecting to {address} (press printer button if requested)...")
    ok = ble.ble_pair(address, timeout=timeout)
    if ok:
        rprint(f"[bold green]Successfully paired with {address}[/bold green]")
    else:
        rprint(f"[bold red]Pairing with {address} failed.[/bold red]")

@grp_ble.command("provision", help="Send Wi-Fi credentials to printer via BLE")
@click.argument("address", required=True)
@click.option("--ssid", "-s", required=True, prompt="Wi-Fi SSID", help="Wi-Fi network name (SSID)")
@click.option("--password", "-p", required=True, prompt="Wi-Fi Password", hide_input=True, help="Wi-Fi password")
@click.option("--timeout", "-t", default=20.0, type=float, help="Provisioning timeout in seconds")
def cmd_ble_provision(address, ssid, password, timeout):
    rprint(f"Sending Wi-Fi credentials for '{ssid}' to {address}...")
    res = ble.ble_provision(address, ssid, password, timeout=timeout)
    if res.get("success"):
        rprint(f"[bold green]Success: {res.get('message')}[/bold green]")
    else:
        rprint(f"[bold red]Provisioning failed: {res.get('error')}[/bold red]")

if __name__ == "__main__":
    cli()
