import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# -------------------------------------------------
# 1️⃣  CONFIGURATION
# -------------------------------------------------
DB_PATH      = "./telemetry.db"
BATTERY_ID   = 1                                 # change if needed
ROW_LIMIT    = 100000                               # increase for more data

# -------------------------------------------------
# 2️⃣  LOAD DATA FROM SQLITE
# -------------------------------------------------
conn = sqlite3.connect(DB_PATH)

query = f"""
SELECT
    CAST(voltage AS REAL) / 1000    AS voltage_f,
    CAST(t.resistance AS REAL)      AS resistance_f,
    CAST(t.capacity AS REAL) / 10   AS capacity_f,
    adv_count,
    uptime_s,
    mode,
    t.battery_id,
    recorded_at,
    b.label
FROM telemetry t LEFT JOIN battery b
ON b.battery_id = t.battery_id
WHERE b.battery_id = ?
AND voltage > 0
ORDER BY recorded_at ASC
LIMIT ?
"""

df = pd.read_sql_query(query, conn, params=(BATTERY_ID, ROW_LIMIT))
conn.close()

# -------------------------------------------------
# 3️⃣  PRE‑PROCESSING
# -------------------------------------------------
# Convert the timestamp string to a datetime object (optional, useful for hover‑tooltips)
df["recorded_at"] = pd.to_datetime(df["recorded_at"])

# Ensure numeric columns really are numbers (SQLite returns ints, but pandas can coerce)
numeric_cols = ["voltage_f", "resistance_f", "capacity_f", "adv_count", "uptime_s"]
df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

# Drop any rows that somehow ended up with NaNs in the columns we care about
df.dropna(subset=["voltage_f", "capacity_f", "uptime_s"], inplace=True)

# -------------------------------------------------
# 4️⃣  PLOT
# -------------------------------------------------
sns.set_style("whitegrid")
plt.figure(figsize=(12, 6))

# Primary axis – voltage
ax_volt = plt.gca()
sns.lineplot(
    data=df,
    x="uptime_s",
    y="voltage_f",
    ax=ax_volt,
    label="Voltage (V)",
    color="#1f77b4",          # classic blue
    linewidth=2,
)

ax_volt.set_xlabel("Uptime (seconds)")
ax_volt.set_ylabel("Voltage (V)", color="#1f77b4")
ax_volt.tick_params(axis='y', labelcolor="#1f77b4")

# Secondary axis – capacity
ax_cap = ax_volt.twinx()
sns.lineplot(
    data=df,
    x="uptime_s",
    y="capacity_f",
    ax=ax_cap,
    label="Capacity (maH)",
    color="#ff7f0e",          # orange
    linewidth=2,
    linestyle="--",
)

ax_cap.set_ylabel("Capacity (maH)", color="#ff7f0e")
ax_cap.tick_params(axis='y', labelcolor="#ff7f0e")

# Optional: add a legend that combines both lines
lines, labels = ax_volt.get_legend_handles_labels()
lines2, labels2 = ax_cap.get_legend_handles_labels()
plt.legend(lines + lines2, labels + labels2, loc="upper left")

plt.title(f"Battery {BATTERY_ID}: Voltage & Capacity vs. Uptime")
plt.tight_layout()
plt.show()
