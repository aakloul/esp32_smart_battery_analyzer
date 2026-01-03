# curses_view.py
"""
Curses‑based view that displays the latest telemetry for every device in a
tabular grid.  The view owns the curses window, redraws the whole table
whenever a row changes and never blocks the event loop – it only updates
the screen when instructed by the controller.
"""

import curses
from typing import Dict, Any, List


class CursesView:
    """
    Minimal curses UI.  The controller calls ``update_row`` with a dict that
    contains the columns defined in ``HEADER`` (except the first column,
    which is the device MAC address itself).
    """

    HEADER = ["device_uuid", "battery_id", "voltage (mV)",
              "adv_count", "uptime_s", "mode"]

    def __init__(self, stdscr: curses.window) -> None:
        """
        ``stdscr`` is the window object supplied by ``curses.wrapper``.
        All drawing happens inside this window.
        """
        self.stdscr = stdscr
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._init_curses()

    # ------------------------------------------------------------------
    # Curses initialisation (colors, etc.)
    # ------------------------------------------------------------------
    def _init_curses(self) -> None:
        curses.curs_set(0)                     # hide cursor
        self.stdscr.nodelay(True)             # non‑blocking getch()
        curses.start_color()
        curses.use_default_colors()
        # Define a simple colour pair for the header (white on blue)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        self.header_attr = curses.color_pair(1) | curses.A_BOLD

    # ------------------------------------------------------------------
    # Public API – called by the controller
    # ------------------------------------------------------------------
    def update_row(self, device_uuid: str, data: Dict[str, Any]) -> None:
        """
        Store (or replace) the row for *device_uuid* and repaint the screen.
        """
        self._rows[device_uuid] = data
        self._render()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def _render(self) -> None:
        """
        Clear the window and draw the full table.  The method is fast enough
        for the modest amount of data we expect (a handful of beacons).
        """
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()

        # Compute column widths – give each column a minimum width.
        col_widths = [max(len(h), 12) for h in self.HEADER]

        # Header line
        x = 0
        for idx, (title, w) in enumerate(zip(self.HEADER, col_widths)):
            txt = title.ljust(w)
            self.stdscr.addstr(0, x, txt, self.header_attr)
            x += w + 1                     # +1 for a space between cols

        # Horizontal separator
        self.stdscr.hline(1, 0, curses.ACS_HLINE, max_x)

        # Body – one line per device, sorted by MAC for deterministic order
        for row_idx, mac in enumerate(sorted(self._rows.keys()), start=2):
            if row_idx >= max_y:           # prevent overflow on very small terminals
                break
            row = self._rows[mac]
            cells = [
                mac.ljust(col_widths[0]),
                str(row.get("battery_id", "")).ljust(col_widths[1]),
                str(row.get("voltage", "")).ljust(col_widths[2]),
                str(row.get("adv_count", "")).ljust(col_widths[3]),
                f"{row.get('uptime_s', 0):.1f}".ljust(col_widths[4]),
                str(row.get("mode", "")).ljust(col_widths[5]),
            ]
            x = 0
            for cell, w in zip(cells, col_widths):
                self.stdscr.addstr(row_idx, x, cell)
                x += w + 1

        # Footer / instruction line
        footer = "Press Ctrl‑C to quit"
        self.stdscr.addstr(max_y - 1, 0, footer, curses.A_DIM)

        self.stdscr.refresh()
