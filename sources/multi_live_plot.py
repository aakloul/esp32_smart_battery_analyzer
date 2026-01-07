#!/usr/bin/env python3
"""
Live telemetry visualiser that can display *multiple* batteries in the same
Matplotlib window.  The per‑battery logic lives in the private class
_OneBatteryPlot; the public wrapper MultiBatteryLivePlot handles layout
and the shared animation loop.
"""

import math
from pathlib import Path
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.animation import FuncAnimation
from matplotlib.ticker import FuncFormatter


# ----------------------------------------------------------------------
# 1️⃣  INTERNAL CLASS – one battery, but receives pre‑created Axes
# ----------------------------------------------------------------------
class _OneBatteryPlot:
    """Handles fetching, scaling and drawing for a single battery."""

    def __init__(
        self,
        conn,
        battery_id,
        ax_volt,
        ax_cap,
        max_points=2000,
        v_min=2.7,
        v_max=4.2,
        u_min=0,
        u_max=15000,
        c_max=2500,
    ):
        self.conn = conn
        self.battery_id = battery_id
        self.ax_volt = ax_volt  # left‑hand y‑axis
        self.ax_cap = ax_cap  # right‑hand y‑axis (twin)
        self.max_points = max_points
        self.v_min = v_min
        self.v_max = v_max
        self.u_min = u_min
        self.u_max = u_max
        self.c_max = c_max

        # runtime state
        self.data_df, self.last_timestamp = self._fetch_new_rows(None)
        self._fetch_battery_details()

        self.scale_factor = 1.0
        self.voltage_floor = 0.0

        sns.set_style("whitegrid")
        # self.fig, self.ax_volt = plt.subplots(figsize=(12, 6))

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
            0.02,
            0.15,
            annotation_text,
            transform=self.ax_volt.transAxes,  # use axes‑fraction coordinates
            ha="left",
            va="center",  # left‑aligned, vertically centered
            fontsize=9,
            color="#555555",  # a neutral gray that doesn’t clash
            bbox=dict(facecolor="white", edgecolor="#dddddd", pad=4),
        )

        # ----- line objects -------------------------------------------------
        (self.line_volt,) = self.ax_volt.plot(
            [], [], color="#1f77b4", linewidth=2, label="Voltage (V)"
        )
        self.ax_volt.set_xlabel("Uptime (s)")
        self.ax_volt.set_ylabel("Voltage (V)", color="#1f77b4")
        self.ax_volt.tick_params(axis="y", labelcolor="#1f77b4")

        (self.line_cap,) = self.ax_cap.plot(
            [], [], color="#ff8f0e", linewidth=2, linestyle="--", label="Capacity (mAh)"
        )
        self.ax_cap.set_ylabel("Capacity (mAh)", color="#ff7f0e")
        self.ax_cap.tick_params(axis="y", labelcolor="#ff7f0e")

        # ----- max‑value tags ------------------------------------------------
        self.voltage_max_tag = self.ax_volt.text(
            0.98,
            0.98,
            "",
            transform=self.ax_volt.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color="#1f77b4",
            backgroundcolor="w",
            bbox=dict(facecolor="white", edgecolor="#1f77b4", pad=1.5),
        )
        self.capacity_max_tag = self.ax_cap.text(
            0.98,
            0.98,
            "",
            transform=self.ax_cap.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color="#ff7f0e",
            backgroundcolor="w",
            bbox=dict(facecolor="white", edgecolor="#ff7f0e", pad=1.5),
        )

        # legend (combined for the two lines)
        handles = [self.line_volt, self.line_cap]
        labels = [h.get_label() for h in handles]
        self.ax_volt.legend(handles, labels, loc="upper center")

        # title for this subplot
        self.ax_volt.set_title(f"Battery {self.battery_id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_battery_details(self):
        """Return a DataFrame with rows newer than ``last_ts`` and the newest timestamp."""
        sql = """
        SELECT
            label,
            CAST(capacity AS REAL) / 10 AS capacity_f,
            resistance,
            discharge_current
        FROM battery
        WHERE battery_id = ?
        """
        df = pd.read_sql_query(sql, self.conn, params=(self.battery_id,))
        if not df.empty:
            self.label = df.loc[0]["label"]
            self.capacity = df.loc[0]["capacity_f"]
            self.resistance = df.loc[0]["resistance"]
            self.discharge_current = df.loc[0]["discharge_current"]

    def _fetch_new_rows(self, last_ts):
        """Return a DataFrame with rows newer than ``last_ts`` and the newest timestamp."""
        sql = """
        WITH start_uptime_s AS (
            SELECT min(uptime_s) AS start_uptime_s
            FROM telemetry
            WHERE battery_id = ?
                AND capacity > 0
        )
        SELECT
            CAST(t.voltage    AS REAL) / 1000    AS voltage_f,
            CAST(t.resistance AS REAL)           AS resistance_f,
            CAST(t.capacity   AS REAL) / 10     AS capacity_f,
            t.adv_count,
            t.uptime_s - (SELECT start_uptime_s FROM start_uptime_s) AS uptime_s,
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
        ts_str = None if last_ts is None else last_ts.isoformat(sep=" ")
        df = pd.read_sql_query(
            sql, self.conn, params=(self.battery_id, self.battery_id, ts_str, ts_str)
        )
        if df.empty:
            return df, last_ts
        df["recorded_at"] = pd.to_datetime(df["recorded_at"])
        newest_ts = df["recorded_at"].iloc[-1]
        return df, newest_ts

    @staticmethod
    def _capacity_formatter_factory(voltage_floor, scale_factor):
        def fmt(x, pos):
            cap = (x - voltage_floor) / scale_factor
            return f"{cap:.0f}"

        return FuncFormatter(fmt)

    # ------------------------------------------------------------------
    # Public animation step – returns the artists that changed
    # ------------------------------------------------------------------
    def animate(self, _frame_idx):
        # 1️⃣ fetch new rows
        new_df, self.last_timestamp = self._fetch_new_rows(self.last_timestamp)

        if not new_df.empty:
            self.data_df = pd.concat([self.data_df, new_df], ignore_index=True)
            if len(self.data_df) > self.max_points:
                self.data_df = self.data_df.iloc[-self.max_points :].reset_index(
                    drop=True
                )

        # 2️⃣ recompute scaling
        if not self.data_df.empty:
            # v_min_raw = self.data_df["voltage_f"].min()
            v_min_raw = self.v_min
            self.voltage_floor = round(v_min_raw - 0.1, 1)  # e.g. 3.13 → 3.1
            # v_max = self.data_df["voltage_f"].max()
            # c_max = self.data_df["capacity_f"].max()
            v_max = self.v_max
            c_max = self.c_max
            self.scale_factor = (
                (v_max - self.voltage_floor) / c_max if c_max != 0 else 1.0
            )
        else:
            self.voltage_floor = 0.0
            v_max = 1.0
            self.scale_factor = 1.0
            c_max = 1.0

        # 3️⃣ update lines
        self.line_volt.set_data(self.data_df["uptime_s"], self.data_df["voltage_f"])
        self.line_cap.set_data(
            self.data_df["uptime_s"],
            self.data_df["capacity_f"] * self.scale_factor + self.voltage_floor,
        )

        # 4️⃣ axes limits
        # if not self.data_df.empty:
        #    self.ax_volt.set_xlim(self.data_df["uptime_s"].min(),
        #                          self.data_df["uptime_s"].max())
        # self.ax_volt.set_ylim(self.voltage_floor, round(v_max, 1))
        # self.ax_cap.set_ylim(self.voltage_floor, round(v_max, 1))

        # 5️⃣ max‑value tags
        self.voltage_max_tag.set_text(f"max ≈ {self.data_df['voltage_f'].max():.2f} V")
        self.capacity_max_tag.set_text(f"max ≈ {self.capacity:.0f} mAh")

        # 6️⃣ tick formatter for capacity axis
        self.ax_cap.yaxis.set_major_formatter(
            self._capacity_formatter_factory(self.voltage_floor, self.scale_factor)
        )

        self.ax_volt.set_xlim(self.u_min, self.u_max)
        self.ax_volt.set_ylim(self.v_min, self.v_max)
        self.ax_cap.set_xlim(self.u_min, self.u_max)
        self.ax_cap.set_ylim(self.v_min, self.v_max)

        # self.ax_volt.set_xlim(0, 13000)
        # self.ax_volt.set_ylim(2.7, 4.2)
        # self.ax_cap.set_ylim(self.v_min, self.v_max)

        # Return the artists that changed (Matplotlib expects an iterable)
        return (
            self.line_volt,
            self.line_cap,
            self.voltage_max_tag,
            self.capacity_max_tag,
        )


# ----------------------------------------------------------------------
# 2️⃣  PUBLIC WRAPPER – handles any number of batteries
# ----------------------------------------------------------------------
class MultiBatteryLivePlot:
    """
    Visualise one or more batteries in a single Matplotlib window.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.
    battery_ids : list[int]
        List of battery identifiers you want to monitor.
    interval_ms : int, optional
        Refresh interval for the animation (default 2000 ms).
    max_points : int, optional
        Maximum points per subplot (default 2000).
    """

    def __init__(self, db_path, battery_ids, interval_ms=2000, max_points=2000):
        if not battery_ids:
            raise ValueError("At least one battery_id must be supplied")

        self.db_path = db_path
        self.battery_ids = battery_ids
        self.interval_ms = interval_ms
        self.max_points = max_points

        # 1️⃣ Determine a tidy grid layout
        n = len(battery_ids)
        self.cols = math.ceil(math.sqrt(n))
        self.rows = math.ceil(n / self.cols)

        # 2️⃣ Create the figure and a matrix of Axes
        sns.set_style("whitegrid")
        self.fig, self.ax_matrix = plt.subplots(
            self.rows, self.cols, figsize=(self.cols * 6, self.rows * 4), squeeze=False
        )
        self.fig.suptitle("Live Telemetry – Multiple Batteries", fontsize=16)

        # 3️⃣ Open a single SQLite connection (shared by all sub‑plots)
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)

        self._fetch_voltage_limits()

        # 4️⃣ Build a list of per‑battery plot objects
        self.sub_plots = []
        for idx, bat_id in enumerate(battery_ids):
            r = idx // self.cols
            c = idx % self.cols
            ax_volt = self.ax_matrix[r][c]  # left y‑axis
            # ax_volt.set_aspect('equal', adjustable='box')
            ax_volt.set_ylim(self.v_min, self.v_max)
            ax_cap = ax_volt.twinx()  # right y‑axis (twin)
            ax_volt.set_xlim(self.u_min, self.u_max)
            plot = _OneBatteryPlot(
                conn=self.conn,
                battery_id=bat_id,
                ax_volt=ax_volt,
                ax_cap=ax_cap,
                max_points=self.max_points,
                v_min=self.v_min,
                v_max=self.v_max,
                u_min=self.u_min,
                u_max=self.u_max,
                c_max=self.c_max,
            )
            self.sub_plots.append(plot)

        # 5️⃣ Hide any unused sub‑plots (when rows*cols > n)
        # --------------------------------------------------------------
        total_axes = self.rows * self.cols
        for empty_idx in range(len(battery_ids), total_axes):
            r = empty_idx // self.cols
            c = empty_idx % self.cols
            self.ax_matrix[r][c].axis("off")

        # --------------------------------------------------------------
        # 6️⃣ Tight‑layout – keep room for the suptitle
        # --------------------------------------------------------------
        self.fig.tight_layout(rect=[0, 0, 1, 0.95])

    def _fetch_voltage_limits(self):
        """Return a DataFrame with rows newer than ``last_ts`` and the newest timestamp."""
        placeholders = ", ".join("?" for _ in self.battery_ids)
        sql = f"""
        WITH start_uptime_s AS (
            SELECT battery_id, min(uptime_s) AS start_uptime_s 
            FROM telemetry 
            WHERE battery_id  in ({placeholders})
                AND capacity > 0
        )
        SELECT
            min(CAST(voltage    AS REAL) / 1000)    AS min_voltage_f,
            max(CAST(voltage    AS REAL) / 1000)    AS max_voltage_f,
            max(capacity / 10),
            min(uptime_s - start_uptime_s),
            max(uptime_s - start_uptime_s)
        FROM telemetry t LEFT JOIN start_uptime_s s ON t.battery_id = s.battery_id 
        WHERE t.battery_id in ({placeholders})
          AND voltage > 0
        """
        ids = []
        ids.extend(self.battery_ids)
        ids.extend(self.battery_ids)
        df = pd.read_sql_query(sql, self.conn, params=(ids))
        if not df.empty:
            self.v_min = df.iloc[0, 0]
            self.v_max = df.iloc[0, 1]
            self.c_max = df.iloc[0, 2]
            self.u_min = df.iloc[0, 3]
            self.u_max = df.iloc[0, 4]
            print(self.v_min, self.v_max, self.c_max, self.u_min, self.u_max)

    # ------------------------------------------------------------------
    # Internal animation driver – calls every sub‑plot's animate()
    # ------------------------------------------------------------------
    def _animate_all(self, frame_idx):
        artists = []
        for sp in self.sub_plots:
            artists.extend(sp.animate(frame_idx))
        return artists

    # ------------------------------------------------------------------
    # Public entry point – keep a reference to the animation object
    # ------------------------------------------------------------------
    def run(self):
        """Start the live animation; blocks until the window is closed."""
        self._anim = FuncAnimation(
            self.fig, func=self._animate_all, interval=self.interval_ms, blit=False
        )
        plt.show()
        self.conn.close()


# ----------------------------------------------------------------------
# 3️⃣  Example usage (run this file directly)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    home_dir = Path.home()
    DB_PATH = Path("telemetry.db")
    DB_PATH = Path(home_dir, "battery_profiles/master.db")
    # Example: visualise three batteries side‑by‑side
    batteries_to_show = [1, 2, 3, 4, 5, 6]  # replace with the IDs you need
    live = MultiBatteryLivePlot(
        db_path=DB_PATH,
        battery_ids=batteries_to_show,
        interval_ms=2000,
        max_points=100000,
    )
    live.run()
