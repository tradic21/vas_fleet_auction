# run_batch.py
import asyncio
import os
import contextlib
import json
import time
import spade

from dispatcher import Dispatcher
from vehicle import Vehicle

from scenarios import Scenario, SCENARIOS as SCENARIOS_DICT

SCENARIO_NAMES = ["low", "medium", "high"]
STRATEGIES = ["nearest", "marginal"]
SEEDS = [1, 2, 3] 

GRAPHML_PATH = os.path.join("data", "zadar_drive.graphml")

DISPATCHER_JID = os.getenv("DISPATCHER_JID", "dispatcher@localhost")

MAX_TASKS = 8
BID_WAIT_SEC = 0.5

WARMUP_SEC = 0.8
COOLDOWN_SEC = 0.8

POLL_SEC = 0.2

SCENARIO_OVERRIDES = {
    "low": (14, (320, 520)),
    "medium": (9,  (200, 360)),
    "high": (5,  (90,  180)),
}

OUT_BY_STRATEGY = {
    "nearest": "results_nearest.csv",
    "marginal": "results_marginal.csv",
}


VEHICLE_STARTS = {
    "vozilo1@localhost": [44.1156, 15.2278],  # Poluotok / centar
    "vozilo2@localhost": [44.1235, 15.2405],  # Voštarnica
    "vozilo3@localhost": [44.1320, 15.2160],  # Borik
    "vozilo4@localhost": [44.1080, 15.2625],  # Bili brig / istok
}


VEHICLE_SPEED_MPS = float(os.getenv("VEHICLE_SPEED_MPS", "18.0"))


STATE_PATH = os.getenv("STATE_PATH", os.path.join("map_viewer", "state.json"))


EVENTS_CSV = os.getenv("EVENTS_CSV", "events.csv")


def reset_outputs():
    for path in OUT_BY_STRATEGY.values():
        if os.path.exists(path):
            os.remove(path)
            print(f"[BATCH] Deleted old {path}")


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

        print(f"[BATCH] Reset viewer state: {STATE_PATH}")
    except Exception as e:
        print(f"[BATCH] Viewer state reset failed: {e}")


def reset_event_log():
    if os.getenv("RESET_EVENTS_CSV", "0") != "1":
        return
    try:
        if os.path.exists(EVENTS_CSV):
            os.remove(EVENTS_CSV)
            print(f"[BATCH] Deleted old {EVENTS_CSV}")
    except Exception as e:
        print(f"[BATCH] Event log reset failed: {e}")


@contextlib.contextmanager
def temporary_scenario_override(scenario: str):
    if scenario not in SCENARIO_OVERRIDES:
        yield
        return

    old = SCENARIOS_DICT.get(scenario)
    task_period, (slack_min, slack_max) = SCENARIO_OVERRIDES[scenario]

    SCENARIOS_DICT[scenario] = Scenario(
        name=scenario,
        task_period_sec=int(task_period),
        slack_min_sec=int(slack_min),
        slack_max_sec=int(slack_max),
    )

    try:
        yield
    finally:
        if old is not None:
            SCENARIOS_DICT[scenario] = old


async def stop_agents(dispatcher, vehicles):
    tasks = []
    if dispatcher is not None:
        tasks.append(dispatcher.stop())

    for v in vehicles or []:
        tasks.append(v.stop())

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    await asyncio.sleep(COOLDOWN_SEC)


def make_vehicles(strategy: str, seed: int):
    v1 = Vehicle(
        "vozilo1@localhost",
        "lozinka123",
        start_pos=VEHICLE_STARTS["vozilo1@localhost"],
        strategy=strategy,
        seed=seed,
        speed_mps=VEHICLE_SPEED_MPS,
    )
    v2 = Vehicle(
        "vozilo2@localhost",
        "lozinka123",
        start_pos=VEHICLE_STARTS["vozilo2@localhost"],
        strategy=strategy,
        seed=seed,
        speed_mps=VEHICLE_SPEED_MPS,
    )
    v3 = Vehicle(
        "vozilo3@localhost",
        "lozinka123",
        start_pos=VEHICLE_STARTS["vozilo3@localhost"],
        strategy=strategy,
        seed=seed,
        speed_mps=VEHICLE_SPEED_MPS,
    )
    v4 = Vehicle(
        "vozilo4@localhost",
        "lozinka123",
        start_pos=VEHICLE_STARTS["vozilo4@localhost"],
        strategy=strategy,
        seed=seed,
        speed_mps=VEHICLE_SPEED_MPS,
    )
    return [v1, v2, v3, v4]


async def run_one(scenario: str, strategy: str, seed: int, out_csv: str):
    vehicles_jids = list(VEHICLE_STARTS.keys())

    
    vehicles = make_vehicles(strategy=strategy, seed=seed)
    for v in vehicles:
        await v.start()

    await asyncio.sleep(WARMUP_SEC)

    dispatcher = None

    print("\n==============================")
    print(f"RUN: scenario={scenario} | strategy={strategy} | seed={seed}")
    print(f"graphml={GRAPHML_PATH}")
    print(f"max_tasks={MAX_TASKS} | bid_wait_sec={BID_WAIT_SEC} | csv={out_csv}")
    print(f"vehicle_speed_mps={VEHICLE_SPEED_MPS}")
    if scenario in SCENARIO_OVERRIDES:
        tp, dr = SCENARIO_OVERRIDES[scenario]
        print(f"override: task_period_sec={tp}, slack_range={dr}")
    print("==============================\n")

    try:
        with temporary_scenario_override(scenario):
            dispatcher = Dispatcher(
                DISPATCHER_JID,
                "lozinka123",
                vehicles_jids,
                scenario=scenario,
                seed=seed,
                bid_wait_sec=BID_WAIT_SEC,
                max_tasks=MAX_TASKS,
                auto_stop=True,
               
                graphml_path=GRAPHML_PATH,
                use_road_world=True,
               
                vehicle_starts=VEHICLE_STARTS,
            )
            await dispatcher.start()

            
            while dispatcher.is_alive():
                await asyncio.sleep(POLL_SEC)

    finally:
        if dispatcher is not None:
            try:
                dispatcher.export_csv(out_csv)
            except Exception as e:
                print(f"[BATCH] export_csv failed: {e}")

        await stop_agents(dispatcher, vehicles)


async def main():
    os.environ["DISPATCHER_JID"] = DISPATCHER_JID

   
    if not os.path.exists(GRAPHML_PATH):
        raise FileNotFoundError(f"Ne mogu naći graphml: {GRAPHML_PATH}")

    reset_outputs()
    reset_event_log()
    reset_viewer_state()

    for strategy in STRATEGIES:
        out_csv = OUT_BY_STRATEGY[strategy]
        for scenario in SCENARIO_NAMES:
            for seed in SEEDS:
                await run_one(scenario, strategy, seed, out_csv)

    print("\n Gotovo.")
    for strategy, out_csv in OUT_BY_STRATEGY.items():
        print(f"- {strategy}: {out_csv}")


if __name__ == "__main__":
    spade.run(main())

