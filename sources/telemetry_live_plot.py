#!/usr/bin/env python4
"""
Live telemetry plot – refactored as a reusable class.

Features
--------
* Reads new rows from a SQLite telemetry table on‑the‑fly.
* Shows voltage (left y‑axis) and capacity (right y‑axis) on a **shared vertical scale**.
* Aligns capacity 0 with the smallest voltage (rounded down to one decimal place).
* Displays the current maximum voltage and capacity as small tags on the top of each axis.
* Fully configurable – you can create several instances for different battery IDs.

Author:  (your name / Lumo)
"""

from pathlib import Path
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FuncFormatter


class TelemetryLivePlot:
    """
    Encapsulates the live‑updating telemetry plot.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.
    battery_id : int
        Which battery to visualise.
    interval_ms : int, optional
        Refresh interval for the animation (default 2000 ms).
    max_points : int, optional
        Maximum number of points to keep in memory (oldest points are discarded).
    """

    def __init__(self, db_path: str, battery_id: int,
                 interval_ms: int = 2000, max_points: int = 2000):
        # ------------------------------------------------------------------
        # 1️⃣  Store configuration
        # ------------------------------------------------------------------
        self.db_path = db_path
        self.battery_id = battery_id
        self.interval_ms = interval_ms
        self.max_points = max_points

        # ------------------------------------------------------------------
        # 2️⃣  Initialise runtime state
        # ------------------------------------------------------------------
        self.conn = sqlite3.connect(self.db_path,
                                    detect_types=sqlite3.PARSE_DECLTYPES)

        self.data_df, self.last_timestamp = self._fetch_new_rows(None)
        self._fetch_battery_details()

        # Scaling helpers that will be recomputed on every frame
        self.scale_factor = 1.0
        self.voltage_floor = 0.0

        # ------------------------------------------------------------------
        # 3️⃣  Build the Matplotlib figure once
        # ------------------------------------------------------------------
        sns.set_style("whitegrid")
        self.fig, self.ax_volt = plt.subplots(figsize=(12, 6))

        annotation_text = (
            f"Label: {self.label} (id={self.battery_id})\n"
            f"Capacity: {self.capacity} mAh\n"
            f"Discharge cur: {self.discharge_current} mA\n"
            f"Int Resistance: {self.resistance} mΩ"
        )

        # (0.02, 0.5) are *axes‑fraction* coordinates:
        #   x ≈ 2 % from the left border,
        #   y = 50 % vertically (center).
        self.ax_volt.text(
            0.02, 0.5, annotation_text,
            transform=self.ax_volt.transAxes,   # use axes‑fraction coordinates
            ha="left", va="center",           # left‑aligned, vertically centered
            fontsize=9,
            color="#555555",                  # a neutral gray that doesn’t clash
            bbox=dict(facecolor="white", edgecolor="#dddddd", pad=3)
        )


        # ---- primary (voltage) axis ---------------------------------------
        self.line_volt, = self.ax_volt.plot([], [], color="#1f77b4",
                                            linewidth=2, label="Voltage (V)")
        self.ax_volt.set_xlabel("Uptime (seconds)")
        self.ax_volt.set_ylabel("Voltage (V)", color="#1f77b4")
        self.ax_volt.tick_params(axis='y', labelcolor="#1f77b4")

        # tag that will show the current maximum voltage
        self.voltage_max_tag = self.ax_volt.text(
            0.98, 0.98, "",
            transform=self.ax_volt.transAxes,
            ha="right", va="top",
            fontsize=9,
            color="#1f77b4",
            backgroundcolor="w",
            bbox=dict(facecolor="white", edgecolor="#1f77b4", pad=1.5)
        )

        # ---- secondary (capacity) axis ------------------------------------
        self.ax_cap = self.ax_volt.twinx()
        self.line_cap, = self.ax_cap.plot([], [], color="#ff7f0e",
                                          linewidth=2, linestyle="--",
                                          label="Capacity (mAh)")
        self.ax_cap.set_ylabel("Capacity (mAh)", color="#ff7f0e")
        self.ax_cap.tick_params(axis='y', labelcolor="#ff7f0e")

        # tag that will show the current maximum capacity
        self.capacity_max_tag = self.ax_cap.text(
            0.98, 0.98, "",
            transform=self.ax_cap.transAxes,
            ha="right", va="top",
            fontsize=9,
            color="#ff7f0e",
            backgroundcolor="w",
            bbox=dict(facecolor="white", edgecolor="#ff7f0e", pad=1.5)
        )

        # combined legend
        handles = [self.line_volt, self.line_cap]
        labels = [h.get_label() for h in handles]
        self.ax_volt.legend(handles, labels, loc="upper center")

        self.fig.suptitle(f"Live Battery {self.battery_id}: "
                          "Voltage & Capacity vs. Uptime")
        self.fig.tight_layout()

    # ----------------------------------------------------------------------
    # 4️⃣  PRIVATE HELPERS
    # ----------------------------------------------------------------------
    def _fetch_battery_details(self):
        """Return a DataFrame with rows newer than ``last_ts`` and the newest timestamp."""
        sql = """
        SELECT
            label,
            capacity,
            resistance,
            discharge_current
        FROM battery
        WHERE battery_id = 1
        """
        df = pd.read_sql_query(sql, self.conn) #, params=(self.battery_id))
        if not df.empty:
            self.label = df.loc[0]['label']
            self.capacity = df.loc[0]['capacity']
            self.resistance = df.loc[0]['resistance']
            self.discharge_current = df.loc[0]['discharge_current']
            #print(self.label, self.capacity, self.resistance, self.discharge_current)

    def _fetch_new_rows(self, last_ts):
        """Return a DataFrame with rows newer than ``last_ts`` and the newest timestamp."""
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
        df = pd.read_sql_query(sql, self.conn,
                               params=(self.battery_id, ts_str, ts_str))
        if df.empty:
            return df, last_ts
        df["recorded_at"] = pd.to_datetime(df["recorded_at"])
        newest_ts = df["recorded_at"].iloc[-1]
        return df, newest_ts

    @staticmethod
    def _capacity_formatter_factory(voltage_floor, scale_factor):
        """Factory that builds a FuncFormatter converting plotted y → real capacity."""
        def fmt(x, pos):
            cap = (x - voltage_floor) / scale_factor
            return f"{cap:.0f}"
        return FuncFormatter(fmt)

    # ----------------------------------------------------------------------
    # 5️⃣  ANIMATION CALLBACK (called by FuncAnimation)
    # ----------------------------------------------------------------------
    def _animate(self, frame_idx):
        # ---- 1️⃣ fetch any new rows ---------------------------------------
        new_df, self.last_timestamp = self._fetch_new_rows(self.last_timestamp)

        if not new_df.empty:
            self.data_df = pd.concat([self.data_df, new_df],
                                     ignore_index=True)

            # keep only the newest N points if the user asked for it
            if len(self.data_df) > self.max_points:
                self.data_df = self.data_df.iloc[-self.max_points:].reset_index(drop=True)

        # ---- 2️⃣ recompute scaling / axis limits --------------------------
        if not self.data_df.empty:
            # a) floor = smallest voltage rounded **down** to one decimal place
            v_min_raw = self.data_df["voltage_f"].min()
            self.voltage_floor = round(v_min_raw - 0.1, 1)   # e.g. 3.13 → 3.1

            # b) top of the plot = largest voltage observed
            v_max = self.data_df["voltage_f"].max()

            # c) capacity extremes (we only need the max for the tag)
            c_max = self.data_df["capacity_f"].max()

            # d) scale factor that maps capacity → voltage space
            #    capacity = 0 → y = voltage_floor
            #    capacity = c_max → y = v_max
            self.scale_factor = (v_max - self.voltage_floor) / c_max if c_max != 0 else 1.0
        else:
            # safe defaults for an empty dataset
            self.voltage_floor = 0.0
            v_max = 1.0
            self.scale_factor = 1.0
            c_max = 1.0

        # ---- 3️⃣ update the plotted lines ---------------------------------
        self.line_volt.set_data(self.data_df["uptime_s"],
                                self.data_df["voltage_f"])
        self.line_cap.set_data(
            self.data_df["uptime_s"],
            self.data_df["capacity_f"] * self.scale_factor + self.voltage_floor
        )

        # ---- 4️⃣ keep axes limits identical -------------------------------
        if not self.data_df.empty:
            self.ax_volt.set_xlim(self.data_df["uptime_s"].min(),
                                  self.data_df["uptime_s"].max())
        self.ax_volt.set_ylim(self.voltage_floor, round(v_max, 1))
        self.ax_cap.set_ylim(self.voltage_floor, round(v_max, 1))

        # ---- 5️⃣ update the “max‑value” tags ------------------------------
        self.voltage_max_tag.set_text(f"max ≈ {v_max:.2f} V")
        self.capacity_max_tag.set_text(f"max ≈ {c_max:.0f} mAh")

        # ---- 6️⃣ refresh the right‑hand axis tick formatter ---------------
        self.ax_cap.yaxis.set_major_formatter(
            self._capacity_formatter_factory(self.voltage_floor,
                                             self.scale_factor)
        )

        # Return the artists that changed – required by FuncAnimation
        return (self.line_volt,
                self.line_cap,
                self.voltage_max_tag,
                self.capacity_max_tag)

    # ----------------------------------------------------------------------
    # 6️⃣  PUBLIC METHOD – start the animation
    # ----------------------------------------------------------------------
    def run(self):
        """Start the live plot and block until the window is closed."""
        anim = FuncAnimation(self.fig,
                             func=self._animate,
                             interval=self.interval_ms,
                             blit=False)
        plt.show()
        # When the window is closed we tidy up the DB connection
        self.conn.close()


# ----------------------------------------------------------------------
# 7️⃣  Example usage (can be placed in a separate script)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    BATTERY_ID = 1
    home_dir = Path.home()
    #DB_PATH=Path(home_dir,"battery_profiles/master.db")
    DB_PATH=Path("./telemetry.db")

    plot1 = TelemetryLivePlot(db_path=DB_PATH,
                              battery_id=BATTERY_ID,
                              interval_ms=2000,
                              max_points=2000)
    plot1.run()

    # to plot a second battery in the same process:
    # plot2 = TelemetryLivePlot("./telemetry.db", battery_id=2)
    # plot2.run()
