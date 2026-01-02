#!/usr/bin/env python3
"""
Eddystone‑TLM scanner using bleak.
Listens for BLE advertisements, extracts any Eddystone‑TLM frames,
and prints a human‑readable summary per device.

Author: Adel Akloul – adapted for XIAO ESP32‑C3 chargers
"""
import asyncio
from bleak import BleakScanner, BLEDevice, AdvertisementData
import struct
import sys
from datetime import datetime
from typing import Dict
import hmac
import hashlib

# ----------------------------------------------------------------------
EDDYSTONE_SERVICE_UUID = "0000feaa-0000-1000-8000-00805f9b34fb"
EDDYSTONE_UUID = b'\xAA\xFE'        # 0xFEAA in little‑endian order (as transmitted)
TLM_FRAME_TYPE = 0x20               # Fixed for TLM
TLM_PAYLOAD_LEN = 14                # Bytes after the UUID
MAC_TRUNC_LEN = 4                   # Truncated payload HMAC size

# Store the last seen data per MAC so we can avoid flooding the console
last_seen: Dict[str, dict] = {}

#SECRET_KEY = bytes.fromhex(
#    "123456789ABCDEF01122334455667788"
#)  # <-- replace with the same secret used on the ESP32

SECRET_KEY = "secretKey"

def toHexString(_byteArray):
    return ":".join("{:02x}".format(int(c)) for c in _byteArray)

def printHex(_byteArray):
    print(toHexString(_byteArray))

def verify_signature(tlm: bytes, mac: bytes) -> bool:
    """Re‑compute HMAC‑SHA256 over the TLM payload and compare the truncated MAC."""
    full_hmac = hmac.new(SECRET_KEY.encode(), tlm, hashlib.sha256).digest()
    #print("calculated_hmac = ", toHexString(full_hmac))
    #print("truncated_hmac = ", toHexString(full_hmac[:MAC_TRUNC_LEN]))
    return full_hmac[:MAC_TRUNC_LEN] == mac

def decode_tlm(payload: bytes) -> dict:
    """
    Decode the 14‑byte TLM payload into a dictionary.
    Payload must be exactly 14 bytes.
    """
    if len(payload) != TLM_PAYLOAD_LEN:
        raise ValueError(f"TLM payload length mismatch: expected 14, got {len(payload)}")

    # Unpack according to the spec (big‑endian)
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


def parse_advertisement(device_address, advertisement) -> None:
    """
    Look for Service Data with the Eddystone UUID and try to decode a TLM frame.
    """
    # `advertisement.service_data` is a dict: {uuid_bytes: bytes}
    for uuid, data in advertisement.service_data.items():
        # The UUID comes as a 16‑bit integer in little‑endian order.
        # Convert to raw bytes for easy comparison.
        #uuid_bytes = uuid.encode('utf-8')[8:6]# to_bytes(2, byteorder="little")

        if uuid != EDDYSTONE_SERVICE_UUID:
            continue

        # At this point `data` starts with the TLM payload (no UUID prefix)
        # Some implementations prepend the UUID again – handle both cases.
        if len(data) > TLM_PAYLOAD_LEN + 2:
            hmac = data[-MAC_TRUNC_LEN:]
            data = data[:-MAC_TRUNC_LEN]          # strip duplicated UUID
            #printHex("hmac = ", hmac)
            if not verify_signature(data, hmac):
                print("skip invalid mac")
                continue
            if len(data) == TLM_PAYLOAD_LEN + 2 and data[:2] == EDDYSTONE_UUID:
                tlm_payload = data[2:]          # strip duplicated UUID
            elif len(data) == TLM_PAYLOAD_LEN:
                tlm_payload = data
            else:
                # Not a TLM payload (could be URL, UID, etc.)
                print("Not a TLM payload (could be URL, UID, etc.)")
                continue
        else:
            # Not a TLM payload (could be URL, UID, etc.)
            print("Not a TLM payload (could be URL, UID, etc.)")
            continue


        try:
            decoded = decode_tlm(tlm_payload)
        except Exception as e:
            print(f"[{device_address}] Failed to decode TLM: {e}")
            continue

        # Only print if something changed (avoid spamming)
        prev = last_seen.get(device_address)
        if prev != decoded:
            last_seen[device_address] = decoded
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{ts}] Device {device_address}")
            print(f"  Battery:\t{decoded['battery_mv']} mV")
            print(f"  Resistance:\t{decoded['resistance']:.2f} ohms")
            print(f"  Adv cnt:\t{decoded['adv_count']}")
            print(f"  Uptime:\t{decoded['time_since_power_on_s']:.1f}s")
        # No need to keep scanning this service data entry
        break


# Define your callback function
# It must accept two arguments: device and advertisement_data
def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
    try:
        #j = {'name':device.name, 'address':device.address, 'details':device.details, 'advertisement_data':advertisement_data}
        #print(j)
        if device.name == "ESP32 TLM Beacon":
            #print(f"Device found: {device.name} - Address: {device.address}")
            parse_advertisement(device.address, advertisement_data)
            # Check if the device is advertising the Eddystone Service UUID
            #    # You can add logic here to process the data or stop scanning
    except asyncio.CancelledError:
        print("Gracefully shutting down")


async def main():
    # Pass the callback directly to the constructor
    async with BleakScanner(detection_callback) as scanner:
        # The scanner runs as long as it is within the 'async with' block.
        # You need an event or another mechanism to keep the program running
        # if you want to scan continuously for a period.
        print("Scanning started, waiting for devices...")
        try:
            while True:
                await asyncio.sleep(5.0)   # keep the event loop alive
        except KeyboardInterrupt:
            pass
        finally:
            await asyncio.sleep(1.0) # Scan for 5 seconds

    print("Scanning stopped.")
    # After the 'async with' block, the scanner is stopped automatically.

# To run the async function
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Gracefully shutted down")
