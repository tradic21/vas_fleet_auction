# run_all.py
import os

os.environ["ANIMATE_PICKUP_SEC"] = "999"   
os.environ["VIEWER_EVERY_N"] = "1"         


os.environ["DISPATCHER_JID"] = os.getenv("DISPATCHER_JID", "dispatcher@localhost")

import asyncio
import json
import time
import spade

from dispatcher import Dispatcher
from vehicle import Vehicle


STRATEGY = "nearest"
SCENARIO = "low"
SEED = 1

MAX_TASKS = 4
TASK_PERIOD_SEC = 18
BID_WAIT_SEC = 2.0

GRAPHML_PATH = "data/zadar_drive.graphml"
USE_ROAD_WORLD = True


VEHICLE_SPEED_MPS = 10.0


TRAFFIC_RANGE = (1.0, 1.4)
SERVICE_RANGE = (0.05, 0.15)


STATE_PATH = os.getenv("STATE_PATH", os.path.join("map_viewer", "state.json"))


WARMUP_SEC = 1.0
COOLDOWN_SEC = 0.8
POLL_SEC = 0.25


DISPATCHER_JID = os.getenv("DISPATCHER_JID", "dispatcher@localhost")
DISPATCHER_PWD = os.getenv("DISPATCHER_PWD", "lozinka123")


def reset_viewer_state():
    try:
        parent = os.path.dirname(STATE_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)

        state = {
            "updated_ts": time.time(),
            "task": None,
            "vehicles": [],
            "deliveries": [],
            "assigned": [],
        }
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        print(f"[run_all] Reset viewer state: {STATE_PATH}")
    except Exception as e:
        print(f"[run_all] Viewer state reset failed: {e}")


async def stop_all(dispatcher, vehicles):
    tasks = []
    if dispatcher is not None:
        tasks.append(dispatcher.stop())
    for v in vehicles or []:
        tasks.append(v.stop())
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(COOLDOWN_SEC)


async def main():
    os.environ["DISPATCHER_JID"] = DISPATCHER_JID

    
    reset_viewer_state()

    vehicles_jids = [
        "vozilo1@localhost",
        "vozilo2@localhost",
        "vozilo3@localhost",
        "vozilo4@localhost",
    ]

   
    v_seeds = {
        "vozilo1@localhost": SEED + 101,
        "vozilo2@localhost": SEED + 102,
        "vozilo3@localhost": SEED + 103,
        "vozilo4@localhost": SEED + 104,
    }

    
    starts = {
        "vozilo1@localhost": [44.1156, 15.2278],  # Poluotok / centar
        "vozilo2@localhost": [44.1235, 15.2405],  # Voštarnica
        "vozilo3@localhost": [44.1320, 15.2160],  # Borik
        "vozilo4@localhost": [44.1080, 15.2625],  # Bili brig / istok
    }

    
    vehicles = []
    for jid in vehicles_jids:
        vehicles.append(
            Vehicle(
                jid,
                "lozinka123",
                start_pos=starts[jid],
                capacity=3,
                speed_mps=VEHICLE_SPEED_MPS,
                strategy=STRATEGY,
                seed=v_seeds[jid],
                traffic_range=TRAFFIC_RANGE,
                service_range=SERVICE_RANGE,
            )
        )

    dispatcher = Dispatcher(
        DISPATCHER_JID,
        DISPATCHER_PWD,
        vehicles_jids,
        scenario=SCENARIO,
        seed=SEED,
        bid_wait_sec=BID_WAIT_SEC,
        max_tasks=MAX_TASKS,
        auto_stop=True,
        task_period_sec=TASK_PERIOD_SEC,
        graphml_path=GRAPHML_PATH,
        use_road_world=USE_ROAD_WORLD,
        
        vehicle_starts=starts,
    )

    out_csv = f"results_{STRATEGY}_{SCENARIO}_seed{SEED}_{len(vehicles_jids)}veh.csv"

    try:
        for v in vehicles:
            await v.start()

      
        await asyncio.sleep(WARMUP_SEC)

        
        await dispatcher.start()

        print("\nAll agents started.\n")
        print(f"vehicles={len(vehicles_jids)} | strategy={STRATEGY} | scenario={SCENARIO} | seed={SEED}")
        print(f"task_period_sec={TASK_PERIOD_SEC} | bid_wait_sec={BID_WAIT_SEC} | max_tasks={MAX_TASKS}")
        print(f"vehicle_speed_mps={VEHICLE_SPEED_MPS} | traffic={TRAFFIC_RANGE} | service={SERVICE_RANGE}")
        print(f"graphml={GRAPHML_PATH}")
        print(f"viewer_state={STATE_PATH}\n")

        
        while dispatcher.is_alive():
            await asyncio.sleep(POLL_SEC)

    finally:
        if dispatcher is not None:
            try:
                dispatcher.export_csv(out_csv)
                print(f"[run_all] Exported: {out_csv}")
            except Exception as e:
                print(f"[run_all] export_csv failed: {e}")

        await stop_all(dispatcher, vehicles)


if __name__ == "__main__":
    spade.run(main())

