# app_logger.py
"""
A small wrapper around the standard library `logging` module.
All parts of the program import `logger` from here, so we have a single
source of truth for log configuration.
"""

import logging
from collections import deque
from typing import Deque, List

# ----------------------------------------------------------------------
# 1️⃣ Configure the root logger once
# ----------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

logger = logging.getLogger("EddystoneLogger")   # use a dedicated namespace
logger.setLevel(logging.INFO)          # choose the level you need
logger.propagate = False               # prevent propagation to the root logger

# ----------------------------------------------------------------------
# 2️⃣ In‑memory handler – stores the last N log records for the UI
# ----------------------------------------------------------------------
MAX_LOG_RECORDS = 200   # keep the most recent 200 lines (adjust as you like)

class MemoryHandler(logging.Handler):
    """
    Simple handler that keeps the newest N formatted log strings in a
    thread‑safe deque.  The UI can read `handler.buffer` at any time.
    """
    def __init__(self, capacity: int = MAX_LOG_RECORDS):
        super().__init__()
        self.capacity = capacity
        self.buffer: Deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.buffer.append(msg)

formatter = logging.Formatter(LOG_FORMAT)

# Create the handler, attach it to our logger, and expose it for the UI.
memory_handler = MemoryHandler()
memory_handler.setFormatter(formatter)
logger.addHandler(memory_handler)

# Write to file instead of stdout
file_handler = logging.FileHandler("eddystone.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)      # capture everything
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)   

# Export the buffer so the view can read it without importing the whole logger.
log_buffer = memory_handler.buffer

def log_debug(msg: str, *args, **kwargs) -> None:
    """Shortcut for `logger.debug(msg, *args, **kwargs)`."""
    logger.debug(msg, *args, **kwargs)
