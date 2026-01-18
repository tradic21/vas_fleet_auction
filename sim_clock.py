# sim_clock.py
import os
import time
import asyncio

FAST_MODE = os.getenv("FAST_MODE", "0") == "1"
TIME_ACCEL = float(os.getenv("TIME_ACCEL", "50"))

_T0_WALL = time.monotonic()
_T0_SIM  = time.time()  # da timestampi ostanu "normalni"

def sim_now() -> float:
    if not FAST_MODE:
        return time.time()
    return _T0_SIM + (time.monotonic() - _T0_WALL) * TIME_ACCEL

async def sim_sleep(sim_seconds: float):
    if sim_seconds <= 0:
        return
    if not FAST_MODE:
        await asyncio.sleep(sim_seconds)
    else:
        await asyncio.sleep(sim_seconds / max(1.0, TIME_ACCEL))

