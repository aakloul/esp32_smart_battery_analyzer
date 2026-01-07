# telemetry_repository.py
"""
Higher‑level service that the scanner can depend on.
It knows *what* to store, not *how* to store it.
"""

from datetime import datetime
from models import Device, Battery, Telemetry
from telemetry_db import TelemetryDB

from app_logger import logger


class TelemetryRepository:
    """
    Public API used by the scanner (or any other component) to persist data.
    """

    def __init__(self, db: TelemetryDB):
        self.db = db
        self.device_map: Dict[str, Device] = {}
        for device in db.list_devices():
            self.device_map[device.device_uuid] = device
        self.battery_map: Dict[str, Battery] = {}

    def get_battery_by_device_uuid(self, uuid: str) -> Battery:
        return self.battery_map.get(uuid)

    def update_battery_label(self, device_uuid, new_battery_label):
        battery = self.battery_map.get(device_uuid)
        battery.label = new_battery_label
        self.db.update_battery(battery)

    # ------------------------------------------------------------------
    # Public entry point – called by the scanner after a successful decode
    # ------------------------------------------------------------------
    def save_telemetry(
        self, decoded: dict, device_uuid: str | None = None
    ) -> Telemetry:
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

        # 2 Ensure the device row exists (INSERT OR IGNORE)
        device = self.device_map.get(device_uuid)
        if not device:
            device = Device(device_uuid=device_uuid, first_seen=now)
            device.device_id = self.db.insert_device(device)
            self.device_map[device_uuid] = device
            logger.info(
                f"inserted device {device.device_id} with uuid {device.device_uuid}"
            )

        # 2️⃣ Store a battery snapshot (optional – nice for separate charts)
        battery = self.battery_map.get(device_uuid)
        if not battery:
            battery = Battery(
                device_id=device.device_id,
                # voltage_mv=decoded["battery_mv"],
                # measured_at=now,
            )
            battery.battery_id = self.db.insert_battery(battery)
            self.battery_map[device_uuid] = battery
            logger.info(
                f"inserted battery {battery.battery_id} from device {device.device_id}"
            )
        battery_id = battery.battery_id

        # 3️⃣ Store the core telemetry record
        telemetry = Telemetry(
            battery_id=battery_id,
            voltage=decoded["battery_mv"],
            resistance=decoded["resistance"],
            capacity=decoded["capacity"],
            adv_count=decoded["adv_count"],
            uptime_s=decoded["time_since_power_on_s"],
            mode=decoded["mode"],
            discharge_current=decoded["discharge_current"],
            recorded_at=now,
        )
        self.db.insert_telemetry(telemetry)

        if telemetry.resistance > 0:
            battery.resistance = telemetry.resistance
            self.db.update_battery(battery)
        if telemetry.capacity > 0:
            battery.capacity = telemetry.capacity
            self.db.update_battery(battery)
        if telemetry.discharge_current > 0:
            battery.discharge_current = telemetry.discharge_current
            self.db.update_battery(battery)

        return telemetry
