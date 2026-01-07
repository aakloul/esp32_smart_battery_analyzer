#!/usr/bin/env python4
"""
Overlay several battery profiles on a single canvas.

Features
--------
* Any number of battery IDs can be supplied (list[int]).
* Each battery gets its own colour (automatically chosen from a Matplotlib
  palette) and appears in the legend.
* The plot uses the same “voltage‑floor / capacity‑zero” alignment you
  already like.
* Optional static annotation (discharge current / internal resistance) can
  be toggled per‑battery.
* The figure is saved to PNG (optional) and displayed with plt.show().
"""

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import FuncFormatter
from itertools import cycle
import argparse
import sys


# ----------------------------------------------------------------------
# Helper – fetch data for a single battery (identical to the earlier version)
# ----------------------------------------------------------------------
def fetch_battery_data(conn, battery_id):
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
    ORDER BY t.recorded_at ASC
    """
    df = pd.read_sql_query(sql, conn, params=(battery_id, battery_id))
    if df.empty:
        return df
    df["recorded_at"] = pd.to_datetime(df["recorded_at"])
    return df


# ----------------------------------------------------------------------
# Core class – draws all batteries on one canvas
# ----------------------------------------------------------------------
class OverlayBatteryPlot:
    """
    Parameters
    ----------
    db_path : str
        Path to the SQLite database.
    battery_ids : list[int]
        IDs of the batteries you want to compare.
    annotate : bool, optional
        If True, add the static “Discharge cur / Int Resistance” text
        (same for every battery). Default: False.
    """

    def __init__(self, db_path, battery_ids, annotate=False):
        self.db_path = db_path
        self.battery_ids = battery_ids
        self.annotate = annotate

        # Open a single connection that will be reused for all queries
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)

        # Load data for every battery up‑front (fast enough for a few dozen)
        self.data = {}
        for bid in self.battery_ids:
            df = fetch_battery_data(self.conn, bid)
            if df.empty:
                print(f"[warning] No data found for battery_id={bid}", file=sys.stderr)
            self.data[bid] = df

        # Prepare a colour cycle – Seaborn’s default palette is pleasant
        self.colour_cycle = cycle(sns.color_palette("tab10"))

    # ------------------------------------------------------------------
    # Private formatter – converts the *scaled* capacity back to its real value
    # ------------------------------------------------------------------
    # @staticmethod
    # def _capacity_formatter_factory(voltage_floor, scale_factor):
    #    def fmt(x, pos):
    #        cap = (x - voltage_floor) / scale_factor
    #        return f"{cap:.0f}"
    #    return FuncFormatter(fmt)

    # ------------------------------------------------------------------
    # Public method – build and show (or save) the figure
    # ------------------------------------------------------------------
    def draw(self, save_path=None):
        # --------------------------------------------------------------
        # 1️⃣  Create the figure & the two axes (shared y‑scale)
        # --------------------------------------------------------------
        sns.set_style("whitegrid")
        fig, ax_volt = plt.subplots(figsize=(12, 6))
        # ax_cap = ax_volt.twinx()          # right‑hand y‑axis for capacity

        # --------------------------------------------------------------
        # 2️⃣  Iterate over batteries, plot each with its own colour
        # --------------------------------------------------------------
        legend_entries = []  # (handle, label) tuples for the final legend

        for bid in self.battery_ids:
            df = self.data[bid]
            if df.empty:
                continue

            # ---- 2a – compute the shared vertical mapping for THIS battery
            v_min_raw = df["voltage_f"].min()
            voltage_floor = round(v_min_raw - 0.1, 1)  # e.g. 3.13 → 3.1
            v_max = df["voltage_f"].max()
            # c_max = df["capacity_f"].max()
            # scale_factor = (v_max - voltage_floor) / c_max if c_max != 0 else 1.0

            # ---- 2b – pick a colour for this battery
            col = next(self.colour_cycle)

            # ---- 2c – plot voltage (left axis)
            (h_volt,) = ax_volt.plot(
                df["uptime_s"],
                df["voltage_f"],
                color=col,
                linewidth=2,
                label=f"B{bid} V",
            )
            # ---- 2d – plot capacity (right axis) – apply the same scaling
            # h_cap, = ax_cap.plot(df["uptime_s"],
            #                     df["capacity_f"] * scale_factor + voltage_floor,
            #                     color=col, linewidth=2, linestyle="--",
            #                     label=f"B{bid} C")
            # Store handles for the legend (we only need one per battery)
            legend_entries.append((h_volt, f"Battery {bid}"))

            # ---- 2e – optional static annotation (same for every battery)
            if self.annotate:
                annotation = "Discharge cur: 525mA\n" "Int Resistance: 129 mΩ"
                ax_volt.text(
                    0.02,
                    0.5,
                    annotation,
                    transform=ax_volt.transAxes,
                    ha="left",
                    va="center",
                    fontsize=9,
                    color="#555555",
                    bbox=dict(facecolor="white", edgecolor="#dddddd", pad=3),
                )

        # --------------------------------------------------------------
        # 3️⃣  Axis limits – make the x‑ and y‑ranges *square* (1:1 data units)
        # --------------------------------------------------------------
        # Gather global minima / maxima across all batteries
        all_uptime = pd.concat(
            [df["uptime_s"] for df in self.data.values() if not df.empty]
        )
        all_voltage = pd.concat(
            [df["voltage_f"] for df in self.data.values() if not df.empty]
        )

        if not all_uptime.empty:
            #    x_min, x_max = all_uptime.min(), all_uptime.max()
            #    y_min, y_max = all_voltage.min(), all_voltage.max()

            #    # Expand to a square data window (same technique as in the live plot)
            #    x_span = x_max - x_min
            #    y_span = y_max - y_min
            #    max_span = max(x_span, y_span)

            #    x_center = (x_max + x_min) / 2.0
            #    y_center = (y_max + y_min) / 2.0

            ax_volt.set_xlim(-250, 12000)
            ax_volt.set_ylim(2.7, 4.2)
            # ax_cap.set_ylim(y_center - max_span/2.0,
            #                 y_center + max_span/2.0)

        # --------------------------------------------------------------
        # 4️⃣  Capacity axis formatter (undo the scaling)
        # --------------------------------------------------------------
        # Use the *global* floor & scale that correspond to the overall limits
        # (they are the same numbers we just used for the y‑lims)
        # global_floor = y_center - max_span/2.0
        # global_scale = max_span / (all_voltage.max() - all_voltage.min()
        #                           if (all_voltage.max() - all_voltage.min()) != 0 else 1)

        # ax_cap.yaxis.set_major_formatter(
        #    self._capacity_formatter_factory(global_floor, global_scale)
        # )

        # --------------------------------------------------------------
        # 5️⃣  Labels, title, legend
        # --------------------------------------------------------------
        ax_volt.set_xlabel("Uptime (seconds)")
        ax_volt.set_ylabel("Voltage (V)", color="#1f77b4")
        ax_volt.tick_params(axis="y", labelcolor="#1f77b4")
        # ax_cap.set_ylabel("Capacity (mAh)", color="#ff7f0e")
        # ax_cap.tick_params(axis='y', labelcolor="#ff7f0e")

        # Build a combined legend from the stored handles
        handles, labels = zip(*legend_entries) if legend_entries else ([], [])
        ax_volt.legend(handles, labels, loc="lower left", title="Batteries")

        plt.title("Overlay Comparison of Battery Profiles")
        plt.tight_layout()

        # --------------------------------------------------------------
        # 6️⃣  Show / save
        # --------------------------------------------------------------
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            print(f"Figure saved to {save_path}")
        plt.show()

        # Clean up the DB connection
        self.conn.close()


# ----------------------------------------------------------------------
# Command‑line interface (optional – handy for quick testing)
# ----------------------------------------------------------------------
def _parse_args():
    parser = argparse.ArgumentParser(
        description="Overlay multiple battery telemetry profiles on a single canvas."
    )
    parser.add_argument(
        "-d",
        "--db",
        required=True,
        help="Path to the SQLite database (e.g. ./telemetry.db)",
    )
    parser.add_argument(
        "-b",
        "--batteries",
        nargs="+",
        type=int,
        required=True,
        help="Space‑separated list of battery IDs to plot, e.g. -b 1 2 5",
    )
    parser.add_argument(
        "-a",
        "--annotate",
        action="store_true",
        help="Add the static discharge‑current / internal‑resistance annotation",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Optional path to save the figure (PNG). If omitted, only display.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    overlay = OverlayBatteryPlot(
        db_path=args.db, battery_ids=args.batteries, annotate=args.annotate
    )
    overlay.draw(save_path=args.output)
