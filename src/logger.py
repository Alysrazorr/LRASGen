"""
Simple progress logger — timestamped, auto-flushed.
"""

import sys
from datetime import datetime


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def info(msg):
    print(f"[{_ts()}] {msg}", flush=True)


def step(step_name, current, total, extra=""):
    pct = current / total * 100 if total else 0
    bar = "#" * int(pct / 5) + "-" * (20 - int(pct / 5))
    print(f"[{_ts()}] [{bar}] {step_name} {current}/{total} {extra}", flush=True)


def warn(msg):
    print(f"[{_ts()}] WARN  {msg}", flush=True)


def error(msg):
    print(f"[{_ts()}] ERROR {msg}", flush=True)
