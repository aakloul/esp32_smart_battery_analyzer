# models.py
"""
Dataclasses that map 1‑to‑1 to the SQLite tables.
They are deliberately tiny – only the fields required for the demo.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------
@dataclass
class Device:
    device_uuid: bytes                      # 16‑byte UUID (binary)
    mac_address: Optional[bytes] = None     # 6‑byte MAC (binary)
    device_id: int = field(default=None)    # 1‑byte PK
    name: Optional[str] = None  # Human readable name, if known
    first_seen: datetime = datetime.utcnow()


@dataclass
class Battery:
    """Battery snapshot – useful if you ever want a history per device."""
    device_id: int                          # FK → device.device_id
    battery_id: int = field(default=None)   # 1‑byte PK
    label: Optional[str] = None             # up to 256 chars
    capacity: int = 0                       # real measured capacity in mah 
    resistance: int = 0                     # 2‑byte


@dataclass
class Telemetry:
    """Core TLM record – one row per successful decode."""
    voltage: int = 0                # 2‑byte
    resistance: int = 0             # 2‑byte
    capacity: int = 0               # 2‑byte
    adv_count: int = 0              # 4‑byte
    uptime_s: int = 0               # 4‑byte Unix epoch
    mode: int = 0                   # 1‑byte
    recorded_at: datetime = datetime.utcnow
    battery_id: int = 0             # FK → battery.battery_id

