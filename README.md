# esp32_smart_battery_analyzer

== Bluetooth Fleet of SmartCharger and Battery Profile Analyzer ==

- This device is designed for testing Lithium Battery, It has four mode of operation: 1. Charge Mode, 2. Discharge Mode, 3. Analyze Mode, 4. IR Test Mode
- The device send altered BLE (Bluetooth Low Energy) Eddystone_TLM Beacons that are captured by the terminal in a form of a python script
- The terminal switches to curses mode, showing a header row, a separator line, and one line per discovered SmartCharger device. 
- As soon as a new telemetry packet is captured, it is stored in a database and the corresponding row is refreshed instantly


## References: 
| Link | |
| - | - |
| [Instructables](https://www.instructables.com/DIY-Smart-Multipurpose-Battery-Tester/) | detailed instructions and schematics |
| [Youtube](https://youtu.be/QN8AuUfg2y8?si=btL3awTXZG-g8NH7) | |
| [PCBWay](https://www.pcbway.com/project/shareproject/DIY_Smart_Multipurpose_Battery_Tester_aaf0922e.html) | PCB production |
| [Seed Studio](https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/) | Getting Started with ESP32-C3 |
| [Nimble on ESP32-C](https://wiki.seeedstudio.com/XIAO_ESP32C3_Bluetooth_Usage/) | Bluetooth with ESP32-C3 |
| [Nimble-Arduino](https://github.com/h2zero/NimBLE-Arduino/blob/master/examples/BLE_EddystoneTLM_Beacon/BLE_EddystoneTLM_Beacon.ino) | Nimble Eddystone-TLM Beacons |
| [HMAC](https://www.dfrobot.com/blog-921.html?srsltid=AfmBOootriPzmv8BGEABjtGPIYKFY8ldHPTuY8WLx7NJhZGtg5EIOsAH) | HMAC implementation for esp32 chip |

## Installation

Recommended to install a virtualenv of your choice

```
pip install -r requirements.txt
python main.py
```

plot all the battery charge / discharge profile:
```
python overlay_battery_plot.py --db ~/battery_profiles/master.db --batteries 2 3 4 5 6
python telemetry_live_plot.py
python multi_live_plot.py
```

## Documentatiomn

| Directory | description |
| - | - |
| datasheet_schematics | datasheets and schematics in pdf |
| gerber | gerber files from PCBway for production |
| stl | contains stl files for 3D printing the pcb housing and buttons |
| bom | bill of materials |
| sources | arduino and python code |

Project Directory:

```
sources/
│
├─ main.py                  # entry point (bootstrap)
├─ app_logger.py            # write logs
├─ controller.py            # MVC controller (model ↔ view)
├─ curses_view.py           # MVC view: curses based UI implementation
├─ eddystone_scanner.py     # BLE scanner – passing telemetry to controller handler
├─ hex_helper.py            # HMAC, hex utils and bytes manipulation
├─ models.py                # Device / Battery / Telemetry dataclasses
├─ telemetry_db.py          # Low‑level SQLite wrapper acting as DAO
├─ telemetry_repository.py  # Repository façade 
├─ archive_sqlite.py        # merge multiple sqlite database into a master.db
├─ multi_live_plot.py       # Live plot multiple battery profiles side by side
├─ overlay_battery_plot.py  # Live plot multiple battery profiles on same chart 
├─ telemetry_live_plot.py   # Live plot a single battery profile during Smart Charger Operations
└─ timing_decorator.py      # debug timing information
```


## Architecture Principles and Notes

| Layer	| Responsibility	| Example class |
| - | - | - |
| Presentation / Runtime |	Starts the async loop, passes the callback to Bleak	| main.py |
| Domain / Business Logic |	Decodes BLE packets, decides what to store	| EddystoneScanner |
| Application Service	| Coordinates persistence, hides DB details	| TelemetryRepository |
| Infrastructure / Persistence |	Raw SQLite commands, schema creation	| TelemetryDB |
| Utility	| Hex formatting & HMAC verification	| HexHelper |

The codebase **testable, maintainable, and future‑proof with clear separation**: 
- The scanner never touches SQL; 
- the repository never knows about BLE.
- The UI lives in its own module and the whole application follows a very lightweight MVC pattern (Model = dataclasses + SQLite, View = curses based terminal table, Controller = glue that updates the model and tells the view to redraw).

**Lightweight**: All modules import only the Python standard library plus bleak (already required for BLE). No extra third‑party UI frameworks are needed, keeping the package lightweight and easy to install.

**Requires minimum hardware specifications**, all the UI is ASCII based to allow the capture to run on a headless device (e.g raspberry pi)

**Responsiveness** of the UI and scanning with asyncio and threading

## Development

###Contributions are welcome

Make sure you use proper python linter and code formatter (e.g black, flake)

### Profiling the UI loop

Any change, especially in the UI must be trsted for responsivemess. Recommend to use Python’s built‑in cProfile that works even with curses:

```python -m cProfile -o profile.pstats main.py```

After you quit the program, inspect the hot spots:

```python
python - <<'PY'
import pstats, sys
p = pstats.Stats('profile.pstats')
p.strip_dirs().sort_stats('cumtime').print_stats(20)
PY
```
Look for functions that consume a lot of cumulative time (_draw_table, _draw_log, parse_advertisement, etc.). Those are the places to optimise.
