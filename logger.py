# logger.py
import csv
import os
import time
from typing import Any, Dict

LOG_PATH = "events.csv"


def _ensure_header(path: str, fieldnames) -> None:
    if os.path.exists(path):
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()


def log_event(event: str, **data: Any) -> None:
    row: Dict[str, Any] = {"ts": time.time(), "event": str(event)}
    row.update(data)

    
    base_fields = [
        "ts", "event",
        "task_id", "vehicle", "winner",
        "bid", "status",
        "release_ts", "deadline_ts", "finished_ts",
        "pickup", "dropoff",
        "distance",
    ]

    
    all_fields = list(base_fields)
    for k in row.keys():
        if k not in all_fields:
            all_fields.append(k)

    _ensure_header(LOG_PATH, all_fields)


    try:
        with open(LOG_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
        fieldnames = header if header else all_fields
    except Exception:
        fieldnames = all_fields

    safe_row = {k: row.get(k, "") for k in fieldnames}

    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writerow(safe_row)

