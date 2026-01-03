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

import asyncio
from bleak import BleakScanner

import sqlite3
from pathlib import Path

from hex_helper import HexHelper
from telemetry_db import TelemetryDB
from telemetry_repository import TelemetryRepository
from eddystone_tlm_scanner import EddystoneScanner

# ----------------------------------------------------------------------
# Configuration – change only if your deployment uses a different key
# ----------------------------------------------------------------------
SECRET_KEY = "secretKey"          # <-- replace with the real secret if needed
DB_FILE = Path("telemetry.db")    # SQLite file location

def build_scanner() -> EddystoneScanner:
    """
    Build the whole stack and return a ready‑to‑use scanner instance.
    """
    # 1️⃣ Helper (holds secret & device name)
    helper = HexHelper(secret_key=SECRET_KEY)

    # 2️⃣ Low‑level DB object
    db = TelemetryDB(db_path=DB_FILE)

    # 3️⃣ Repository façade
    repo = TelemetryRepository(db)

    # 4️⃣ Scanner wired with both helper & repository
    return EddystoneScanner(helper, repo, device_name="ESP32 TLM Beacon")


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


# ----------------------------------------------------------------------
# 3️⃣  Main entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Graceful shutdown path if the user hits Ctrl‑C during the outer run()
        print("\nProgram terminated by user.")

