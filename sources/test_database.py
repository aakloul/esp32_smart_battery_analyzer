#!/usr/bin/env python4
# -*- coding: utf-8 -*-
"""main.py
Minimal executable that launches the asynchronous BLE scanner to capture 
eddystone_tlm beacons. Developer must adjust ``SECRET_KEY`` (or load it from a config file)
to match the key used on the ESP32 sketch.
It also uses the TelemetryDB wrapper defined in telemetry_db.py.
"""

import uuid
import time
import os

import sqlite3

from telemetry_db import TelemetryDB

def random_mac() -> bytes:
    """Return a random 6‑byte MAC address (for demo purposes)."""
    return os.urandom(6)


def test_database() -> None:
    # ----------------------------------------------------------------------
    # Import the public symbols from telemetry_db.py
    # ----------------------------------------------------------------------
    # Assuming telemetry_db.py lives in the same directory as this script.
    # If it is in a package/sub‑folder, adjust the import path accordingly
    # (e.g. `from mypackage.telemetry_db import TelemetryDB, Device, Battery, Telemetry`).
    from telemetry_db import TelemetryDB, Device, Battery, Telemetry

    # Create / open the SQLite file (it will be created if missing)
    db = TelemetryDB("my_telemetry.db")

    # --------------------------------------------------------------
    # Insert a device, a battery and a telemetry record
    # --------------------------------------------------------------
    dev = Device(
        device_uuid=uuid.uuid4().bytes,   # 16‑byte UUID
        mac_address=random_mac(),
    )
    try:
        dev.device_id = db.insert_device(dev)
        print("device_id", dev.device_id)
    except sqlite3.IntegrityError as ie:
        pass

    bat = Battery(device_id=dev.device_id, label="Main pack")
    try:
        bat.battery_id = db.insert_battery(bat)
        print("battery_id", bat.battery_id)
    except sqlite3.IntegrityError as ie:
        pass

    tel = Telemetry(
        voltage=3750,
        resistance=110,
        adv_count=13,
        uptime_s=int(time.time()),
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
