# telemetry_repository.py
"""
Higher‑level service that the scanner can depend on.
It knows *what* to store, not *how* to store it.
"""

from datetime import datetime
from models import Device, Battery, Telemetry
from telemetry_db import TelemetryDB


class TelemetryRepository:
    """
    Public API used by the scanner (or any other component) to persist data.
    """

    def __init__(self, db: TelemetryDB):
        self.db = db
        self.battery_map: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public entry point – called by the scanner after a successful decode
    # ------------------------------------------------------------------
    def save_telemetry(self, decoded: dict, device_uuid: str | None = None) -> None:
        """
        Persist a decoded TLM payload.

        Parameters
        ----------
        mac : str
            MAC address of the beacon (used as primary‑key for Device).
        decoded : dict
            Result of ``EddystoneScanner.decode_tlm`` – must contain the keys
            ``battery_mv``, ``resistance``, ``adv_count`` and
            ``time_since_power_on_s``.
        device_name : str | None
            Optional friendly name; stored only the first time we see the device.
        """
        now = datetime.utcnow()

        # 1️⃣ Ensure the device row exists (INSERT OR IGNORE)
        device = Device(device_uuid=device_uuid, first_seen=now)
        self.db.insert_device(device)
        print(f"inserted device {device.device_id} with uuid {device.device_uuid}")

        # 2️⃣ Store a battery snapshot (optional – nice for separate charts)
        battery_id = battery_map.get(device.device_id)
        if not battery_id:
            battery = Battery(
                device_id=device.device_id,
                #voltage_mv=decoded["battery_mv"],
                #measured_at=now,
            )
            self.db.insert_battery(battery)
            battery_id = battery.battery_id
            print(f"inserted battery {battery_id} from device {device.device_id}")
            battery_map[device.device_id] = battery.battery_id

        # 3️⃣ Store the core telemetry record
        telemetry = Telemetry(
            battery_id=battery_id,
            voltage=decoded["battery_mv"],
            resistance=decoded["resistance"],
            adv_count=decoded["adv_count"],
            uptime_s=decoded["time_since_power_on_s"],
            #recorded_at=now,
        )
        self.db.insert_telemetry(telemetry)
