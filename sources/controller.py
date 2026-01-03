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

class TelemetryController:
    def __init__(self, repo: TelemetryRepository, view: CursesView):
        self.repo = repo
        self.view = view

    def handle_telemetry(self, decoded: Dict[str, Any], device_uuid: str) -> None:

        # Persist the data
        telemetry = self.repo.save_telemetry(
            decoded=decoded,
            device_uuid=device_uuid,
        )

        # Build the row the view expects
        view_row: Dict[str, Any] = {
            "battery_id": telemetry.battery_id,
            "voltage": decoded["battery_mv"],
            "adv_count": decoded["adv_count"],
            "uptime_s": decoded["time_since_power_on_s"],
            "mode": "NORMAL",
        }
        self.view.update_row(device_uuid, view_row)

        # log the record
        logger.info(
            "Telemetry received from %s – V=%dmV, adv=%d, uptime=%.1fs",
            device_uuid,
            decoded["battery_mv"],
            decoded["adv_count"],
            decoded["time_since_power_on_s"],
        )
