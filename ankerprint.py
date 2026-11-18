#!/usr/bin/env python3
import os
import sys
import uuid
import time
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
from core.pppp_packets import Duid, PktLanSearch, PktPunchPkt, FileTransfer
from core.util import patch_gcode_time, split_chunks

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("ankerprint")


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
    printers = config.load_printers()
    p_idx = ctx.obj["printer_index"]
    
    if not printers:
        rprint("[yellow]No printers in cache. Running quick scan...[/yellow]")
        ctx.invoke(cmd_scan)
        printers = config.load_printers()
        
    if not printers:
        rprint("[bold red]Error: No printers available to print.[/bold red]")
        sys.exit(1)
        
    if p_idx < 0 or p_idx >= len(printers):
        rprint(f"[bold red]Error: Printer index {p_idx} out of range (available: 0..{len(printers)-1})[/bold red]")
        sys.exit(1)
        
    target = printers[p_idx]
    ip = target["ip"]
    duid = target["duid"]
    
    rprint(f"[bold blue]Targeting Printer [{p_idx}]: {duid} at {ip}[/bold blue]")
    raw_data = file.read()
    patched_data = patch_gcode_time(raw_data)
    
    file_uuid = uuid.uuid4().hex.upper()
    fui = FileUploadInfo.from_data(patched_data, Path(file.name).name, user_name="ankerprint", user_id="-", machine_id=file_uuid)
    
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
        rprint("[*] Handshaking and sending file metadata...")
        api.aabb_request(bytes(fui), frametype=FileTransfer.BEGIN, timeout=15.0)
        
        chunks = split_chunks(patched_data, 1024 * 32)
        pos = 0
        total = len(patched_data)
        
        with tqdm(unit="b", total=total, unit_scale=True, unit_divisor=1024, desc="Streaming G-code") as bar:
            for chunk in chunks:
                api.aabb_request(chunk, frametype=FileTransfer.DATA, timeout=15.0)
                pos += len(chunk)
                bar.update(len(chunk))
                
        if no_act:
            rprint("[green]Upload complete (dry run, print not started).[/green]")
        else:
            rprint("[bold green]File upload complete! Starting print...[/bold green]")
            api.aabb_request(b"", frametype=FileTransfer.END, timeout=15.0)
            rprint("[bold green]Success: Print started.[/bold green]")
    finally:
        api.stop()


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
