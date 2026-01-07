# controller.py
"""
Same controller as before – it only needs the view to expose an
``update_row(mac, dict)`` method, which both the old ASCII view and the
new curses view implement.
"""

from typing import Dict, Any

from telemetry_repository import TelemetryRepository
from curses_view import CursesView

from app_logger import logger

from enum import Enum


class SmartChargerMode(Enum):
    Charge = 0
    Discharge = 1
    Analysis = 2
    IResistance = 3


class TelemetryController:
    def __init__(self, repo: TelemetryRepository, view: CursesView):
        self.repo = repo
        self.view = view
        # controller register to be notified by view
        # when battery_label is changed
        self.view.on_battery_label_change = self.handle_battery_label_change

    def handle_battery_label_change(self, device_uuid, new_battery_label) -> None:
        self.repo.update_battery_label(device_uuid, new_battery_label)
        self.view._needs_redraw = True

    def handle_telemetry(self, decoded: Dict[str, Any], device_uuid: str) -> None:

        # Persist the data
        telemetry = self.repo.save_telemetry(
            decoded=decoded,
            device_uuid=device_uuid,
        )
        battery_label = str(telemetry.battery_id)
        capacity = 0
        resistance = 0
        battery = self.repo.get_battery_by_device_uuid(device_uuid)
        if battery:
            if battery.label:
                battery_label = battery.label
            if battery.resistance:
                resistance = battery.resistance
            if battery.capacity:
                capacity = battery.capacity

        # Build the row the view expects
        view_row: Dict[str, Any] = {
            "battery_label": battery_label,
            "battery_id": battery.battery_id,
            "capacity": capacity,
            "resistance": resistance,
            "voltage": decoded["battery_mv"],
            "discharge_current": decoded["discharge_current"],
            "adv_count": decoded["adv_count"],
            "uptime_s": decoded["time_since_power_on_s"],
            "mode": SmartChargerMode(decoded["mode"]).name,
        }
        self.view.update_row(device_uuid, view_row)

        # log the record
        logger.info(
            "from %s – V=%dmV, C=%.fmAh, cur=%d, adv=%d, up=%.1fs",
            device_uuid[:12],
            decoded["battery_mv"],
            decoded["capacity"] / 10.0,
            decoded["discharge_current"] / 10.0,
            decoded["adv_count"],
            decoded["time_since_power_on_s"],
        )
