#!/usr/bin/env python3
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
import curses
from bleak import BleakScanner

import sqlite3
from pathlib import Path

from hex_helper import HexHelper
from telemetry_db import TelemetryDB
from telemetry_repository import TelemetryRepository

import threading
from curses_view import CursesView
from controller import TelemetryController

from eddystone_tlm_scanner import EddystoneScanner

# ----------------------------------------------------------------------
# Configuration – change only if your deployment uses a different key
# ----------------------------------------------------------------------
SECRET_KEY = "secretKey"          # <-- replace with the real secret if needed
DB_FILE = Path("telemetry.db")    # SQLite file location

def build_components(stdscr: curses.window) -> EddystoneScanner:
    """
    Build the whole stack and return a ready‑to‑use scanner instance.
    """
    # 1️⃣ Helper (holds secret & device name)
    helper = HexHelper(secret_key=SECRET_KEY)

    # 2️⃣  Persistence LAyer
    # Low‑level DB object
    db = TelemetryDB(db_path=DB_FILE)
    # Repository façade
    repo = TelemetryRepository(db)

    # 3️⃣ UI layer (curses)
    view = CursesView(stdscr)

    # 4️⃣  Controller – glues repo + view
    controller = TelemetryController(repo, view) 

    # 5️⃣  Scanner wired with both helper & repository
    return EddystoneScanner(helper, controller, device_name="ESP32 TLM Beacon")


async def scan(stdscr: curses.window) -> None:
    """
    Async part of the program – runs the Bleak scanner.
    """
    scanner = build_components(stdscr)

    # Start the UI loop in a *background* coroutine so we can still run asyncio.
    # We'll run the UI loop in a separate thread because curses blocks.
    ui_thread = threading.Thread(target=scanner.controller.view.run, daemon=True)
    ui_thread.start()

    # ``BleakScanner`` expects a callable with the signature
    # (device: BLEDevice, advertisement_data: AdvertisementData)
    async with BleakScanner(scanner.detection_callback) as ble_scanner:
        # Show a short banner at the top while we wait for first beacon
        max_y, _ = stdscr.getmaxyx()
        stdscr.addstr(max_y - 2, 0, "[TABLE MODE] Scanning started – press Ctrl‑C to quit – 'l' for logs")
        stdscr.refresh()

        try:
            while True:
                await asyncio.sleep(0.02)   # keep the event loop alive
        except KeyboardInterrupt:
            print("\nInterrupted by user – stopping scan…")
        finally:
            # Give Bleak a moment to tidy up before exiting
            await asyncio.sleep(1)

    print("Scanning stopped.")

def main(stdscr: curses.window) -> None:
    try:
        asyncio.run(scan(stdscr))
    except KeyboardInterrupt:
        # Graceful shutdown path if the user hits Ctrl‑C during the outer run()
        print("\nProgram terminated by user.")



# ----------------------------------------------------------------------
# 3️⃣  Main entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # ``curses.wrapper`` takes care of terminal init / teardown.
    curses.wrapper(main)

