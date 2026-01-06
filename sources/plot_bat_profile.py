import sqlite3
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FuncFormatter

home_dir = Path.home()

# ----------------------------------------------------------------------
# 1️⃣  USER SETTINGS
# ----------------------------------------------------------------------

# This returns a Path object pointing at the home folder
DB_PATH      = "./telemetry.db"
DB_PATH      = Path(home_dir,"battery_profiles/master.db")
BATTERY_ID   = 3
INTERVAL_MS  = 2000          # refresh every 2 seconds
MAX_POINTS   = 2000          # keep only the newest N points (optional)

# ----------------------------------------------------------------------
# 2️⃣  FETCH ONLY NEW ROWS
# ----------------------------------------------------------------------
def fetch_new_rows(conn, last_ts):
    sql = """
    SELECT
        CAST(t.voltage    AS REAL) / 1000    AS voltage_f,
        CAST(t.resistance AS REAL)           AS resistance_f,
        CAST(t.capacity   AS REAL) / 10     AS capacity_f,
        t.adv_count,
        t.uptime_s,
        t.mode,
        t.battery_id,
        t.recorded_at,
        b.label
    FROM telemetry t
    LEFT JOIN battery b ON b.battery_id = t.battery_id
    WHERE b.battery_id = ?
      AND t.voltage > 0
      AND (? IS NULL OR t.recorded_at > ?)
    ORDER BY t.recorded_at ASC
    """
    ts_str = None if last_ts is None else last_ts.isoformat(sep=' ')
    df = pd.read_sql_query(sql, conn, params=(BATTERY_ID, ts_str, ts_str))
    if df.empty:
        return df, last_ts
    df["recorded_at"] = pd.to_datetime(df["recorded_at"])
    newest_ts = df["recorded_at"].iloc[-1]
    return df, newest_ts


# ----------------------------------------------------------------------
# 3️⃣  INITIAL CONNECTION & Snapshot
# ----------------------------------------------------------------------
conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
data_df, last_timestamp = fetch_new_rows(conn, None)   # may be empty initially

# ----------------------------------------------------------------------
# 4️⃣  SET UP FIGURE – one shared scale, two axis‑labels, two “max” tags
# ----------------------------------------------------------------------
sns.set_style("whitegrid")
fig, ax_volt = plt.subplots(figsize=(12, 6))

# ----- primary (voltage) axis ------------------------------------------------
line_volt, = ax_volt.plot([], [], color="#1f77b4", linewidth=2,
                          label="Voltage (V)")
ax_volt.set_xlabel("Uptime (seconds)")
ax_volt.set_ylabel("Voltage (V)", color="#1f77b4")
ax_volt.tick_params(axis='y', labelcolor="#1f77b4")

# placeholder for the *maximum voltage* label (will be updated later)
voltage_max_tag = ax_volt.text(
    0.98, 0.98, "",               # x‑, y‑position in axis‑fraction coordinates
    transform=ax_volt.transAxes,   # relative to the axis box
    ha="right", va="top",         # anchor at the top‑right corner
    fontsize=9,
    color="#1f77b4",
    backgroundcolor="w",
    bbox=dict(facecolor="white", edgecolor="#1f77b4", pad=1.5)
)

# ----- secondary (capacity) axis --------------------------------------------
ax_cap = ax_volt.twinx()
line_cap, = ax_cap.plot([], [], color="#ff7f0e", linewidth=2,
                        linestyle="--", label="Capacity (mAh)")
ax_cap.set_ylabel("Capacity (mAh)", color="#ff7f0e")
ax_cap.tick_params(axis='y', labelcolor="#ff7f0e")

# placeholder for the *maximum capacity* label
capacity_max_tag = ax_cap.text(
    0.98, 0.98, "",
    transform=ax_cap.transAxes,
    ha="right", va="top",
    fontsize=9,
    color="#ff7f0e",
    backgroundcolor="w",
    bbox=dict(facecolor="white", edgecolor="#ff7f0e", pad=1.5)
)

# combined legend (both lines)
handles = [line_volt, line_cap]
labels  = [h.get_label() for h in handles]
ax_volt.legend(handles, labels, loc="upper center")

plt.title(f"Live Battery {BATTERY_ID}: Voltage & Capacity vs. Uptime")
plt.tight_layout()

# ----------------------------------------------------------------------
# 5️⃣  ANIMATION CALLBACK
# ----------------------------------------------------------------------
def animate(frame_idx):
    global data_df, last_timestamp, scale_factor, voltage_floor

    # ----- 1️⃣ fetch any new rows ---------------------------------------------
    new_df, last_timestamp = fetch_new_rows(conn, last_timestamp)

    if not new_df.empty:
        data_df = pd.concat([data_df, new_df], ignore_index=True)

        # optional: keep only the newest N points
        if len(data_df) > MAX_POINTS:
            data_df = data_df.iloc[-MAX_POINTS:].reset_index(drop=True)

    # ----- 2️⃣ compute shared y‑range (floor, ceiling, scale) ------------------
    if not data_df.empty:
        # a) floor = smallest voltage rounded down to 1 decimal place
        v_min_raw   = data_df["voltage_f"].min()
        voltage_floor = round(v_min_raw-0.1, 1)          # e.g. 3.13 → 3.1

        # b) top of the plot = largest voltage observed
        v_max = data_df["voltage_f"].max()

        # c) capacity extremes
        c_max = data_df["capacity_f"].max()
        c_min = data_df["capacity_f"].min()   # usually 0, but we keep it generic

        # d) scale factor that maps capacity → voltage space
        #    capacity = 0  → y = voltage_floor
        #    capacity = c_max → y = v_max
        scale_factor = (v_max - voltage_floor) / c_max if c_max != 0 else 1.0
    else:
        # no data yet – safe defaults
        voltage_floor = 0.0
        v_max         = 1.0
        scale_factor  = 1.0
        c_max         = 1.0

    # ----- 3️⃣ update plotted lines -------------------------------------------
    line_volt.set_data(data_df["uptime_s"], data_df["voltage_f"])
    line_cap.set_data(
        data_df["uptime_s"],
        data_df["capacity_f"] * scale_factor + voltage_floor
    )

    # ----- 4️⃣ keep axes limits identical -------------------------------------
    ax_volt.set_xlim(data_df["uptime_s"].min(),
                     data_df["uptime_s"].max())
    ax_volt.set_ylim(voltage_floor, round(v_max,1))
    ax_cap.set_ylim(voltage_floor, round(v_max,1))   # keep them identical

    # ----- 5️⃣ update the *max‑value* tags ------------------------------------
    voltage_max_tag.set_text(f"max ≈ {v_max:.2f} V")
    # capacity label must undo the shift & scaling so the number shown is the real capacity
    capacity_max_tag.set_text(f"max ≈ {c_max:.0f} mAh")

    # ----- 6️⃣ refresh the right‑hand axis tick formatter (unchanged) ---------
    def capacity_formatter(x, pos):
        cap = (x - voltage_floor) / scale_factor
        return f"{cap:.0f}"
    ax_cap.yaxis.set_major_formatter(FuncFormatter(capacity_formatter))

    # return the artists that changed (required by FuncAnimation)
    return line_volt, line_cap, voltage_max_tag, capacity_max_tag



# ----------------------------------------------------------------------
# 6️⃣  START THE LIVE ANIMATION
# ----------------------------------------------------------------------
anim = FuncAnimation(fig,
                     func=animate,
                     interval=INTERVAL_MS,
                     blit=False)

plt.show()
conn.close()
