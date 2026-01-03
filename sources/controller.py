# controller.py
"""
Same controller as before – it only needs the view to expose an
``update_row(mac, dict)`` method, which both the old ASCII view and the
new curses view implement.
"""

from typing import Dict, Any

from telemetry_repository import TelemetryRepository
from curses_view import CursesView   # <-- import the curses version


class TelemetryController:
    def __init__(self, repo: TelemetryRepository, view: CursesView):
        self.repo = repo
        self.view = view

    def handle_telemetry(self, decoded: Dict[str, Any], device_uuid: str) -> None:
        # Persist the data
        # ``device_name`` is optional – we forward the helper's default

        telemetry = self.repo.save_telemetry(
            decoded=decoded,
            device_uuid=device_uuid,
        )

        #battery = self.repo.get_battery_by_device_uuid(device_uuid)

        # Build the row the view expects
        view_row: Dict[str, Any] = {
            "battery_id": telemetry.battery_id,
            "voltage": decoded["battery_mv"],
            "adv_count": decoded["adv_count"],
            "uptime_s": decoded["time_since_power_on_s"],
            "mode": "NORMAL",
        }
        self.view.update_row(device_uuid, view_row)
