#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: telemetry_db.py
Author: Adel Akloul
Created: 2026‑01‑03
Description:
    Low‑level DAO (Data‑Access‑Object)
    A lightweight, type‑safe wrapper around an embedded SQLite database for
    storing battery telemetry data collected from devices. The module defines a 
    `TelemetryDB` class that implements full CRUD operations plus convenient 
    lookup and setter helpers over three dataclasses: Device, Battery, and Telemetry

    Key features:
        • Automatic schema creation (device, battery, telemetry tables)
        • Parameterised SQL statements (SQL‑injection safe)
        • Foreign‑key enforcement and cascade deletes
        • Helper methods such as:
            `get_device_by_mac`,
            `get_telemetry_by_battery_id`, 
            `set_mac_address_by_device_id`,
            `set_label_by_battery_id`, etc.
        • Pure‑standard‑library implementation (no external dependencies)
"""
import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional
import uuid
import time

from pathlib import Path

from models import Device, Battery, Telemetry

# ----------------------------------------------------------------------
# Core wrapper – only the new lookup methods are highlighted
# ----------------------------------------------------------------------
class TelemetryDB:
    """CRUD wrapper for device, battery and telemetry tables."""

    def __init__(self, db_path: str | Path = "telemetry.db"):
        self.conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    # --------------------------------------------------------------
    # Schema creation (same as before)
    # --------------------------------------------------------------
    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS device (
                device_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                device_uuid BLOB    NOT NULL,
                name        TEXT(256),
                mac_address BLOB,
                first_seen TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS battery (
                battery_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   INTEGER NOT NULL,
                label       TEXT(256),
                resistance  INTEGER DEFAULT 0,
                capacity    INTEGER DEFAULT 0,
                FOREIGN KEY(device_id) REFERENCES device(device_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS telemetry (
                voltage     INTEGER NOT NULL,
                resistance  INTEGER DEFAULT 0,
                capacity    INTEGER DEFAULT 0,
                adv_count   INTEGER NOT NULL,
                uptime_s    INTEGER NOT NULL,
                mode        INTEGER NOT NULL,
                battery_id  INTEGER NOT NULL,
                recorded_at TIMESTAMP NOT NULL,
                FOREIGN KEY(battery_id) REFERENCES battery(battery_id)
                    ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    # --------------------------------------------------------------
    # Helper: Row → dataclass
    # --------------------------------------------------------------
    @staticmethod
    def _row_to_dataclass(row: sqlite3.Row, cls):
        return cls(**{k: row[k] for k in row.keys()})

    # ==============================================================
    #                     DEVICE CRUD
    # ==============================================================

    def list_devices(self) -> Iterable[Device]:
        cur = self.conn.execute("SELECT * FROM device ORDER BY device_id;")
        for r in cur:
            yield self._row_to_dataclass(r, Device)

    def get_device(self, device_id: int) -> Optional[Device]:
        cur = self.conn.execute(
            "SELECT * FROM device WHERE device_id = ?;", (device_id,)
        )
        row = cur.fetchone()
        return self._row_to_dataclass(row, Device) if row else None

    def insert_device(self, dev: Device) -> int:
        cur = self.conn.cursor()
        sql = """
            INSERT INTO device (device_id, device_uuid, mac_address, name, first_seen)
            VALUES (?, ?, ?, ?, ?);
        """
        cur.execute(sql, (dev.device_id, dev.device_uuid, dev.mac_address, dev.name, dev.first_seen))
        self.conn.commit()
        return cur.lastrowid

    def update_device(self, dev: Device) -> None:
        sql = """
            UPDATE device
            SET device_uuid = ?, mac_address = ?, name = ?
            WHERE device_id = ?;
        """
        self.conn.execute(sql, (dev.device_uuid, dev.mac_address, dev.name, dev.device_id))
        self.conn.commit()

    def delete_device(self, device_id: int) -> None:
        self.conn.execute("DELETE FROM device WHERE device_id = ?;", (device_id,))
        self.conn.commit()

    # ==============================================================
    #                     BATTERY CRUD
    # ==============================================================

    def list_batteries(self) -> Iterable[Battery]:
        cur = self.conn.execute("SELECT * FROM battery ORDER BY battery_id;")
        for r in cur:
            yield self._row_to_dataclass(r, Battery)

    def get_battery(self, battery_id: int) -> Optional[Battery]:
        cur = self.conn.execute(
            "SELECT * FROM battery WHERE battery_id = ?;", (battery_id,)
        )
        row = cur.fetchone()
        return self._row_to_dataclass(row, Battery) if row else None

    def insert_battery(self, bat: Battery) -> int:
        cur = self.conn.cursor()
        sql = """
            INSERT INTO battery (battery_id, device_id)
            VALUES (?, ?);
        """
        cur.execute(sql, (bat.battery_id, bat.device_id))
        self.conn.commit()
        return cur.lastrowid

    def update_battery(self, bat: Battery) -> None:
        sql = """
            UPDATE battery
            SET device_id = ?, label = ?, capacity = ?, resistance = ?
            WHERE battery_id = ?;
        """
        self.conn.execute(sql, (bat.device_id, bat.label, bat.capacity, bat.resistance, bat.battery_id))
        self.conn.commit()

    def delete_battery(self, battery_id: int) -> None:
        self.conn.execute(
            "DELETE FROM battery WHERE battery_id = ?;", (battery_id,)
        )
        self.conn.commit()

    # ==============================================================
    #                     TELEMETRY CRUD
    # ==============================================================

    def list_telemetry(self) -> Iterable[Device]:
        cur = self.conn.execute("SELECT * FROM telemetry ORDER BY battery_id, uptime_s asc;")
        for r in cur:
            yield self._row_to_dataclass(r, Telemetry)

    def get_telemetry_by_battery_id(self, battery_id: int) -> Optional[Telemetry]:
        cur = self.conn.execute(
            "SELECT * FROM telemetry WHERE battery_id = ? ORDER BY uptime_s dec;",
            (battery_id,),
        )
        for r in cur:
            yield self._row_to_dataclass(r, Telemetry)

    def insert_telemetry(self, tel: Telemetry) -> int:
        cur = self.conn.cursor()
        sql = """
            INSERT INTO telemetry
                (voltage, resistance, capacity, adv_count, uptime_s, mode, recorded_at, battery_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        cur.execute(
            sql,
            (
                tel.voltage,
                tel.resistance,
                tel.capacity,
                tel.adv_count,
                tel.uptime_s,
                tel.mode,
                tel.recorded_at,
                tel.battery_id,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_telemetry_by_battery_id(self, battery_id: int) -> None:
        self.conn.execute(
            "DELETE FROM telemetry WHERE battery_id = ?;", (battery_id,)
        )
        self.conn.commit()


    # ------------------------------------------------------------------
    # NEW LOOKUP METHODS
    # ------------------------------------------------------------------

    def get_device_by_mac(self, mac: bytes) -> Optional[Device]:
        """
        Return the device whose MAC address matches ``mac`` (exact 6‑byte value).

        Parameters
        ----------
        mac : bytes
            Six‑byte MAC address (e.g. ``b'\\xAA\\xBB\\xCC\\xDD\\xEE\\xFF'``).

        Returns
        -------
        Device | None
            Matching device or ``None`` if not found.
        """
        cur = self.conn.execute(
            "SELECT * FROM device WHERE mac_address = ?;", (mac,)
        )
        row = cur.fetchone()
        return self._row_to_dataclass(row, Device) if row else None

    def get_telemetry_by_battery_id(self, battery_id: int) -> List[Telemetry]:
        """
        Retrieve **all** telemetry rows linked to a given ``battery_id``.

        Returns a list (empty if no rows match).  Using a list rather than a
        generator makes it straightforward for callers to inspect length,
        slice, etc.
        """
        cur = self.conn.execute(
            "SELECT * FROM telemetry WHERE battery_id = ? ORDER BY uptime_s;",
            (battery_id,),
        )
        return [self._row_to_dataclass(r, Telemetry) for r in cur]

    def get_battery_by_label(self, label: str) -> List[Battery]:
        """
        Find batteries whose ``label`` exactly equals the supplied string.
        SQLite’s default collation is case‑sensitive; adjust the query if you
        need case‑insensitive matching (e.g. ``WHERE LOWER(label)=LOWER(?)``).
        """
        cur = self.conn.execute(
            "SELECT * FROM battery WHERE label = ? ORDER BY battery_id;", (label,)
        )
        return [self._row_to_dataclass(r, Battery) for r in cur]

    # ------------------------------------------------------------------
    # Setter: change a device’s MAC address given its primary key
    # ------------------------------------------------------------------
    def set_mac_address_by_device_id(self, device_id: int, new_mac: bytes) -> int:
        """
        Update the ``mac_address`` column for the row whose ``device_id`` matches
        ``device_id``.

        Parameters
        ----------
        device_id : int
            Primary‑key of the device to modify.
        new_mac : bytes
            New 6‑byte MAC address (e.g. ``b'\\xAA\\xBB\\xCC\\xDD\\xEE\\xFF'``).

        Returns
        -------
        int
            Number of rows updated (0 if the id does not exist, 1 on success).
        """
        cur = self.conn.execute(
            """
            UPDATE device
            SET mac_address = ?
            WHERE device_id = ?;
            """,
            (new_mac, device_id),
        )
        self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Setter: change a battery’s label given its primary key
    # ------------------------------------------------------------------
    def set_label_by_battery_id(self, battery_id: int, new_label: str) -> int:
        """
        Update the ``label`` column for the battery identified by ``battery_id``.

        Parameters
        ----------
        battery_id : int
            Primary‑key of the battery to modify.
        new_label : str
            New label (up to 256 characters – SQLite will truncate if longer).

        Returns
        -------
        int
            Number of rows updated (0 if the id does not exist, 1 on success).
        """
        cur = self.conn.execute(
            """
            UPDATE battery
            SET label = ?
            WHERE battery_id = ?;
            """,
            (new_label, battery_id),
        )
        self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Clean shutdown
    # ------------------------------------------------------------------
    def close(self) -> None:
        self.conn.close()

if __name__ == "__main__":
    db = TelemetryDB()

        # ----- Device ----------------------------------------------------
    dev = Device(
        device_id=1,
        device_uuid=uuid.UUID("11111111-2222-3333-4444-555555555555").bytes,
        mac_address=bytes.fromhex("AA BB CC DD EE FF".replace(":", "").replace(" ", "")),
    )
    try:
        db.insert_device(dev)
    except sqlite3.IntegrityError as ie:
        pass

    # ----- Battery ---------------------------------------------------
    bat = Battery(battery_id=1, device_id=dev.device_id, label="Primary")
    try:
        db.insert_battery(bat)
    except sqlite3.IntegrityError as ie:
        pass

    # ----- Telemetry -------------------------------------------------
    tel = Telemetry(
        voltage=3700,
        resistance=120,
        adv_count=7,
        timestamp=int(time.time()),
        mode=0x02,
        battery_id=bat.battery_id,
    )
    try:
        db.insert_telemetry(tel)
    except sqlite3.IntegrityError as ie:
        pass

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


    # 1️⃣ Look up a device by its MAC address
    mac = bytes.fromhex('A1B2C3D4E5F6')
    device = db.get_device_by_mac(mac)
    print(device)                     # → Device(...) or None

    # 2️⃣ Get every telemetry record for battery #3
    telemetry_rows = db.get_telemetry_by_battery_id(3)
    for t in telemetry_rows:
        print(t)

    # 3️⃣ Find all batteries labelled "Main pack"
    batteries = db.get_battery_by_label("Main pack")
    for b in batteries:
        print(b)

    print('-' * 80)

    db = TelemetryDB()

    # Change the MAC address of device #5
    rows = db.set_mac_address_by_device_id(
        device_id=1,
        new_mac=bytes.fromhex('DE AD BE EF 00 01')
    )
    print(f"Device MAC updated: {rows} row(s) affected")

    # Rename battery #2
    rows = db.set_label_by_battery_id(battery_id=1, new_label="Backup Pack")
    print(f"Battery label updated: {rows} row(s) affected")

    print('-' * 80)

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

    db.close()
