#!/usr/bin/env python3
"""eddystone_scanner.py
Eddystone‑TLM scanner using bleak.
Listens for BLE advertisements, extracts any Eddystone‑TLM frames,
and prints a human‑readable summary per device.

Contains the :class:`EddystoneScanner` class that knows how to decode an
Eddystone‑TLM frame, extract it from a BLE advertisement and expose a
callback suitable for ``BleakScanner``.

Only the scanning / decoding logic lives here.  
After a successful tlm frame is decoded, 
it delegates to decoded tlm payload to the ``TelemetryController``.

Author: Adel Akloul – adapted for XIAO ESP33‑C3 chargers
"""
import struct
from datetime import datetime
from typing import Dict, Any

import asyncio
from bleak import BLEDevice, AdvertisementData

from hex_helper import HexHelper
from controller import TelemetryController

# ----------------------------------------------------------------------
# Constants (identical to the original script)
# ----------------------------------------------------------------------
EDDYSTONE_SERVICE_UUID = "0000feaa-0000-1000-8000-00805f9b34fb"
EDDYSTONE_UUID = b"\xAA\xFE"          # 0xFEAA in little‑endian order
TLM_FRAME_TYPE = 0x20                 # Fixed for TLM frames
TLM_PAYLOAD_LEN = 14                  # Bytes after the UUID
MAC_TRUNC_LEN = 4                     # Size of the truncated HMAC

class EddystoneScanner:
    """
    High‑level wrapper around Bleak that extracts and validates Eddystone‑TLM
    advertisements.

    Parameters
    ----------
    helper : HexHelper
        Instance providing ``verify_signature`` and optional hex utilities.

    device_name : str, optional
        Name of the beacon we are interested in.  Defaults to
        ``"ESP32 TLM Beacon"``.  The value is stored only for convenience –
        the scanner class can read it if needed.
    """

    def __init__(self, helper: HexHelper, controller: TelemetryController, device_name: str = "ESP32 TLM Beacon"):
        self.helper = helper
        self.controller = controller
        # Keep the last decoded payload per device to avoid spamming the console.
        self._last_seen: Dict[str, Dict[str, Any]] = {}
        self.device_name = device_name

    # ------------------------------------------------------------------
    # 1. Decode the raw 14‑byte TLM payload
    # ------------------------------------------------------------------
    @staticmethod
    def decode_tlm(payload: bytes) -> Dict[str, Any]:
        """
        Decode a 14‑byte TLM payload according to the Eddystone spec.

        Returns a dictionary with the fields used later in the UI.
        """
        if len(payload) != TLM_PAYLOAD_LEN:
            raise ValueError(
                f"TLM payload length mismatch: expected 14, got {len(payload)}"
            )

        (
            frame_type,
            version,
            batt_mv,
            temp_raw,
            adv_cnt,
            time_0_1s,
        ) = struct.unpack(">BBHhII", payload)

        return {
            "frame_type": frame_type,
            "version": version,
            "battery_mv": batt_mv,
            "resistance": temp_raw,
            "adv_count": adv_cnt,
            "time_since_power_on_s": time_0_1s / 1000.0,
        }

    # ------------------------------------------------------------------
    # 2. Parse a single advertisement, verify its HMAC and print a summary
    # ------------------------------------------------------------------
    def parse_advertisement(self, device_address: str, advertisement: AdvertisementData) -> None:
        """
        Look for Service Data containing the Eddystone UUID, verify the HMAC
        (if present) and, when successful, decode the TLM payload.

        The method prints a short, human‑readable summary only when the
        decoded data differs from the previous broadcast of the same device.
        """
        # `advertisement.service_data` is a dict: {uuid_bytes: bytes}
        for uuid, data in advertisement.service_data.items():
            # The UUID comes as a 16‑bit integer in little‑endian order
            # Convert to raw bytes for easy comparison.
            #uuid_bytes = uuid.encode('utf-8')[8:6]# to_bytes(2, byteorder="little")
            if uuid != EDDYSTONE_SERVICE_UUID:
                continue

            #print("data", len(data), self.helper.to_hex_string(data))
            #print("data", len(data), toHexString(data))

            # At this point `data` starts with the TLM payload (no UUID prefix)
            # Some implementations prepend the UUID again – handle both cases.

            # --------------------------------------------------------------
            # Determine whether the payload carries a MAC and/or a duplicated UUID
            # --------------------------------------------------------------
            if len(data) == TLM_PAYLOAD_LEN + MAC_TRUNC_LEN:
                # Last bytes are the truncated MAC
                mac = data[-MAC_TRUNC_LEN:]
                raw = data[:-MAC_TRUNC_LEN]

                #print("mac", len(mac), self.helper.to_hex_string(mac))
                #print("tlm", len(raw), self.helper.to_hex_string(raw))

                # Verify the HMAC before proceeding
                if not self.helper.verify_signature(raw, mac):
                    print("skip invalid mac")
                    continue

                # Strip possible duplicated UUID (some implementations prepend it)
                if len(raw) == TLM_PAYLOAD_LEN + 2 and raw[:2] == EDDYSTONE_UUID:
                    tlm_payload = raw[2:]          # drop duplicated UUID
                elif len(raw) == TLM_PAYLOAD_LEN:
                    tlm_payload = raw
                else:
                    print("Not a TLM payload (could be URL, UID, etc.)")
                    continue
            else:
                # No MAC – treat as non‑TLM data
                print("No MAC - treated as non-TLM payload")
                continue

            # --------------------------------------------------------------
            # Decode the payload and display it if anything changed
            # --------------------------------------------------------------
            try:
                decoded = self.decode_tlm(tlm_payload)
            except Exception as exc:
                print(f"[{device_address}] Failed to decode TLM: {exc}")
                continue

            previous = self._last_seen.get(device_address)
            if previous != decoded:
                self._last_seen[device_address] = decoded
                ts = datetime.now().strftime("%H:%M:%S")
                #print(f"\n[{ts}] Device {device_address}")
                #print(f"  Battery:\t{decoded['battery_mv']} mV")
                #print(f"  Resistance:\t{decoded['resistance']:.2f} Ω")
                #print(f"  Adv cnt:\t{decoded['adv_count']}")
                #print(f"  Uptime:\t{decoded['time_since_power_on_s']:.2f}s")

                # ----- Persist if different then previous -----------------------------
                # ---------- Hand over to the controller ----------
                self.controller.handle_telemetry(decoded, device_address)

            # We processed the relevant service data – stop iterating.
            break

    # ------------------------------------------------------------------
    # 3. Callback required by BleakScanner
    # ------------------------------------------------------------------
    def detection_callback(self, device: BLEDevice, advertisement_data: AdvertisementData) -> None:
        """
        This method is passed directly to ``BleakScanner``.  It filters
        devices by name (using the name stored in the helper) and forwards
        matching advertisements to :meth:`parse_advertisement`.
        """
        try:
            if device.name == self.device_name:
                #print(f"Device found: {device.name} - Address: {device.address}")
                self.parse_advertisement(device.address, advertisement_data)
        except asyncio.CancelledError:
            # Propagate cancellation so the outer event loop can shut down cleanly.
            raise
