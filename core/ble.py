import asyncio
import json
import logging as log
from typing import Dict, List, Optional

try:
    from bleak import BleakScanner, BleakClient
    from bleak.exc import BleakError
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

ANKER_SERVICE_UUID = "0000414d-0000-1000-8000-00805f9b34fb"
ANKER_CHAR_UUID = "00003344-0000-1000-8000-00805f9b34fb"
ANKER_ADV_SERVICE = "fb349b5f-8044-3380-7210-656b4d416e41"


async def _async_ble_scan(timeout: float = 4.0) -> List[Dict]:
    if not BLEAK_AVAILABLE:
        raise RuntimeError("Bleak library is not installed. Run 'pip install bleak'.")

    discovered = []
    scanner_results = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for device, adv in scanner_results.values():
        name = device.name or adv.local_name or ""
        service_uuids = [s.lower() for s in (adv.service_uuids or [])]
        is_anker = (
            "m5" in name.lower()
            or "anker" in name.lower()
            or ANKER_ADV_SERVICE.lower() in service_uuids
            or ANKER_SERVICE_UUID.lower() in service_uuids
        )
        if is_anker:
            discovered.append({
                "name": name or f"AnkerMake ({device.address})",
                "address": device.address,
                "rssi": adv.rssi,
                "services": adv.service_uuids or []
            })
    return discovered


def ble_scan(timeout: float = 4.0) -> List[Dict]:
    return asyncio.run(_async_ble_scan(timeout=timeout))


async def _async_ble_pair(address: str, timeout: float = 15.0) -> bool:
    if not BLEAK_AVAILABLE:
        raise RuntimeError("Bleak library is not installed.")

    log.info(f"Connecting to BLE device at {address}...")
    async with BleakClient(address, timeout=timeout) as client:
        log.info(f"Connected to {address}. Initiating pairing (please press printer button if prompted)...")
        try:
            res = await client.pair()
            log.info(f"Pairing result: {res}")
            return bool(res)
        except Exception as e:
            log.error(f"Pairing error: {e}")
            return False


def ble_pair(address: str, timeout: float = 15.0) -> bool:
    return asyncio.run(_async_ble_pair(address=address, timeout=timeout))


def format_wifi_provision_payload(ssid: str, password: str) -> bytes:
    """
    Constructs the Wi-Fi provisioning frame for AnkerMake M5/M5C.
    Standard payload formats:
    1. JSON command: {"commandType": 10001, "ssid": ..., "password": ...}
    2. Length-prefixed binary frame
    """
    payload = json.dumps({
        "commandType": 10001,
        "ssid": ssid,
        "password": password
    }).encode("utf-8")
    return payload


async def _async_ble_provision(address: str, ssid: str, password: str, timeout: float = 20.0) -> Dict:
    if not BLEAK_AVAILABLE:
        raise RuntimeError("Bleak library is not installed.")

    log.info(f"Connecting to {address} for Wi-Fi provisioning...")
    rx_frames = []

    def on_notify(sender, data):
        log.info(f"BLE RX: {data.hex()} | {data}")
        rx_frames.append(data)

    async with BleakClient(address, timeout=timeout) as client:
        log.info(f"Connected to {address}. Attempting pairing/bonding...")
        try:
            await client.pair()
        except Exception as e:
            log.warning(f"Pair step info: {e}")

        # Check services
        char = None
        for service in client.services:
            for c in service.characteristics:
                if c.uuid.lower() == ANKER_CHAR_UUID.lower() or "write" in c.properties:
                    char = c
                    break

        if not char:
            return {"success": False, "error": "AnkerMake provisioning characteristic not found"}

        try:
            if "notify" in char.properties:
                await client.start_notify(char.uuid, on_notify)
        except Exception as e:
            log.warning(f"Could not enable notifications: {e}")

        payload = format_wifi_provision_payload(ssid, password)
        log.info(f"Writing Wi-Fi payload ({len(payload)} bytes) for SSID: {ssid}")
        await client.write_gatt_char(char.uuid, payload, response=False)
        await asyncio.sleep(2.0)

        return {
            "success": True,
            "message": f"Wi-Fi credentials sent for SSID '{ssid}' to {address}",
            "responses": [f.hex() for f in rx_frames]
        }


def ble_provision(address: str, ssid: str, password: str, timeout: float = 20.0) -> Dict:
    return asyncio.run(_async_ble_provision(address=address, ssid=ssid, password=password, timeout=timeout))
