# curses_view.py
"""
Curses‑based view that displays the latest telemetry for every device in a
tabular grid.  The view owns the curses window, redraws the whole table
whenever a row changes and never blocks the event loop – it only updates
the screen when instructed by the controller.
"""

import curses
from typing import Dict, Any, List
from app_logger import log_buffer   # shared in‑memory log deque


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
        self.mode: str = "table"          # start in telemetry table view
        self.log_scroll: int = 0          # index of the first visible log line
        self._needs_redraw = True         # force first draw
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
        self._needs_redraw = True          # mark that UI must refresh
        #self._render()


    def run(self) -> None:
        """Enter a tight loop that polls keys and redraws only when needed."""
        while True:
            self._handle_key()            # non‑blocking, cheap
            if self._needs_redraw:
                self._render()
                self._needs_redraw = False
            curses.napms(10)               # 10 ms pause → ~100 fps max, low CPU

    # ------------------------------------------------------------------
    # Key handling – called each loop iteration
    # ------------------------------------------------------------------
    def _handle_key(self) -> None:
        """
        Non‑blocking poll for a key press.
        * `l` → switch to log view
        * `t` → switch back to table view
        * Arrow keys/PageUp/PageDown → scroll log view
        """
        try:
            ch = self.stdscr.getch()
        except Exception:
            ch = -1

        if ch == -1:
            return  # no key pressed

        if ch in (ord('l'), ord('L')):
            self.mode = "log"
            self.log_scroll = 0          # reset scroll when entering log view
        elif ch in (ord('t'), ord('T')):
            self.mode = "table"
        elif self.mode == "log":
            # Scrolling only works in log mode
            max_y, _ = self.stdscr.getmaxyx()
            visible_lines = max_y - 2      # leave room for footer
            if ch in (curses.KEY_DOWN, ord('j')):
                if self.log_scroll < max(0, len(log_buffer) - visible_lines):
                    self.log_scroll += 1
            elif ch in (curses.KEY_UP, ord('k')):
                if self.log_scroll > 0:
                    self.log_scroll -= 1
            elif ch in (curses.KEY_NPAGE, ):   # Page Down
                self.log_scroll = min(
                    self.log_scroll + visible_lines,
                    max(0, len(log_buffer) - visible_lines),
                )
            elif ch in (curses.KEY_PPAGE, ):   # Page Up
                self.log_scroll = max(self.log_scroll - visible_lines, 0)

        # Force a redraw after any key that changes the UI
        self._render()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def _render(self) -> None:
        """
        Clear the window and draw the full table or logs. Fast enough method
        for the modest amount of data we expect (a handful of beacons).
        """
        self.stdscr.erase()
        if self.mode == "table":
            self._draw_table()
        else:
            self._draw_log()
        self._draw_footer()
        self.stdscr.refresh()
        # After rendering we also poll for a key so the UI feels responsive.
        self._handle_key()

    # ------------------------------------------------------------------
    # Table view (unchanged except for being a private helper)
    # ------------------------------------------------------------------
    def _draw_table(self) -> None:
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
            if row_idx >= max_y - 1:           # prevent overflow on very small terminals
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


    # ------------------------------------------------------------------
    # Log view – scrollable list of the most recent log lines
    # ------------------------------------------------------------------
    def _draw_log(self) -> None:
        max_y, max_x = self.stdscr.getmaxyx()
        visible_lines = max_y - 2               # reserve last line for footer

        # Grab a slice of the deque based on the current scroll offset.
        # `list(log_buffer)` converts the deque to a list for slicing.
        logs = list(log_buffer)
        start = self.log_scroll
        end = start + visible_lines
        for idx, line in enumerate(logs[start:end], start=0):
            # Truncate line if it exceeds screen width
            if len(line) > max_x:
                line = line[: max_x - 1]
            self.stdscr.addstr(idx, 0, line)

        # If there are fewer lines than the screen height, fill the rest
        for filler in range(len(logs[start:end]), visible_lines):
            self.stdscr.move(filler, 0)
            self.stdscr.clrtoeol()


    # ------------------------------------------------------------------
    # Footer – shows current mode and hint for toggling
    # ------------------------------------------------------------------
    def _draw_footer(self) -> None:
        max_y, max_x = self.stdscr.getmaxyx()
        mode_msg = f"[{'TABLE' if self.mode == 'table' else 'LOG'} MODE] "
        hint = "Press 'l' for logs, 't' for table, Ctrl‑C to quit"
        footer = (mode_msg + hint)[: max_x - 1]   # truncate if needed
        self.stdscr.addstr(max_y - 1, 0, footer, curses.A_REVERSE)

