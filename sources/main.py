#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py
Minimal executable that launches the asynchronous BLE scanner to capture 
eddystone_tlm beacons. Developer must adjust ``SECRET_KEY`` (or load it from a config file)
to match the key used on the ESP32 sketch.
It also uses the TelemetryDB wrapper defined in telemetry_db.py.
"""

from eddystone_tlm_scanner import EddystoneScanner
from hex_helper import HexHelper


# ----------------------------------------------------------------------
# Import the public symbols from telemetry_db.py
# ----------------------------------------------------------------------
import asyncio
from bleak import BleakScanner


# ----------------------------------------------------------------------
# Import the public symbols from telemetry_db.py
# ----------------------------------------------------------------------
# Assuming telemetry_db.py lives in the same directory as this script.
# If it is in a package/sub‑folder, adjust the import path accordingly
# (e.g. `from mypackage.telemetry_db import TelemetryDB, Device, Battery, Telemetry`).
from telemetry_db import TelemetryDB, Device, Battery, Telemetry
import sqlite3

# ----------------------------------------------------------------------
# Optional: a tiny helper to generate a UUID and a MAC address
# ----------------------------------------------------------------------
import uuid
import time
import os

def random_mac() -> bytes:
    """Return a random 6‑byte MAC address (for demo purposes)."""
    return os.urandom(6)

# ----------------------------------------------------------------------
# Configuration – change only if your deployment uses a different key
# ----------------------------------------------------------------------
SECRET_KEY = "secretKey"          # <-- replace with the real secret if needed

def build_scanner() -> EddystoneScanner:
    """
    Create the helper and scanner objects and return the ready‑to‑use
    :class:`EddystoneScanner` instance.
    """
    hexHelper = HexHelper(secret_key=SECRET_KEY)
    return EddystoneScanner(hexHelper, device_name="ESP32 TLM Beacon")


async def main() -> None:
    scanner = build_scanner()

    # ``BleakScanner`` expects a callable with the signature
    # (device: BLEDevice, advertisement_data: AdvertisementData)
    async with BleakScanner(scanner.detection_callback) as ble_scanner:
        print("Scanning started, waiting for devices…")
        try:
            while True:
                await asyncio.sleep(5)   # keep the event loop alive
        except KeyboardInterrupt:
            print("\nInterrupted by user – stopping scan…")
        finally:
            # Give Bleak a moment to tidy up before exiting
            await asyncio.sleep(1)

    print("Scanning stopped.")


def test_database() -> None:
    # Create / open the SQLite file (it will be created if missing)
    db = TelemetryDB("my_telemetry.db")

    # --------------------------------------------------------------
    # Insert a device, a battery and a telemetry record
    # --------------------------------------------------------------
    dev = Device(
        device_id=1,
        device_uuid=uuid.uuid4().bytes,   # 16‑byte UUID
        mac_address=random_mac(),
    )
    try:
        db.insert_device(dev)
    except sqlite3.IntegrityError as ie:
        pass

    bat = Battery(battery_id=1, device_id=dev.device_id, label="Main pack")
    try:
        db.insert_battery(bat)
    except sqlite3.IntegrityError as ie:
        pass

    tel = Telemetry(
        voltage=3750,
        resistance=110,
        advCnt=13,
        timestamp=int(time.time()),
        mode=0x01,
        battery_id=bat.battery_id,
    )
    try:
        db.insert_telemetry(tel)
    except sqlite3.IntegrityError as ie:
        pass

    # --------------------------------------------------------------
    # Demonstrate a couple of the lookup helpers
    # --------------------------------------------------------------
    # 1️⃣ Find the device we just inserted by its MAC address
    fetched_dev = db.get_device_by_mac(dev.mac_address)
    print("\nFetched by MAC →", fetched_dev)

    # 2️⃣ Pull all telemetry rows for battery #1
    telemetry_rows = db.get_telemetry_by_battery_id(battery_id=1)
    print("\nTelemetry for battery 1:")
    for row in telemetry_rows:
        print(row)

    # --------------------------------------------------------------
    # Demonstrate a setter helper
    # --------------------------------------------------------------
    new_mac = random_mac()
    updated = db.set_mac_address_by_device_id(device_id=1, new_mac=new_mac)
    print(f"\nUpdated MAC address – rows affected: {updated}")

    # Verify the change
    print("Device after MAC update:", db.get_device(1))

    print("-"*80)

    # Show what we stored
    print("\nDevices:")
    for d in db.list_devices():
        print(d)

    print("\nBatteries:")
    for b in db.list_batteries():
        print(b)

    print("\nTelemetry rows:")
    for t in db.list_telemetry():
        print(t)

    # Clean shutdown
    db.close()

# ----------------------------------------------------------------------
# 3️⃣  Main entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    test_database()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Graceful shutdown path if the user hits Ctrl‑C during the outer run()
        print("\nProgram terminated by user.")








