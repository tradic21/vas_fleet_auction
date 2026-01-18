import numpy as np
import json
import time
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

LOG_FILE = Path("events.jsonl")

GRID_MAX = 10  

def load_events():
    if not LOG_FILE.exists():
        return []
    events = []
    with LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    events.sort(key=lambda e: e["ts"])
    return events


def main():
    events = load_events()
    if not events:
        print("No events.jsonl found or it's empty. Run the simulation first.")
        return

   
    vehicles = {}     
    current_task = {}  

    fig, ax = plt.subplots()
    ax.set_title("Fleet Auction Viewer")
    ax.set_xlim(-1, GRID_MAX + 1)
    ax.set_ylim(-1, GRID_MAX + 1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks(range(0, GRID_MAX + 1))
    ax.set_yticks(range(0, GRID_MAX + 1))
    ax.grid(True, linewidth=0.5)

    vehicle_scatter = ax.scatter([], [], s=80)  
    pickup_scatter = ax.scatter([], [], marker="s", s=80)   
    dropoff_scatter = ax.scatter([], [], marker="X", s=90)  
    text = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top")

    idx = {"i": 0}

    def redraw():
        xs, ys = [], []
        labels = []
        for jid, pos in vehicles.items():
            xs.append(pos[0]); ys.append(pos[1]); labels.append(jid)
        if xs:
            vehicle_scatter.set_offsets(np.column_stack([xs, ys]))
        else:
            vehicle_scatter.set_offsets(np.empty((0, 2)))


        active_pickups, active_dropoffs = [], []
        for tid, t in current_task.items():
            if t.get("done"):
                continue
            active_pickups.append(t["pickup"])
            active_dropoffs.append(t["dropoff"])
        pickup_scatter.set_offsets(np.array(active_pickups) if active_pickups else np.empty((0, 2)))
        dropoff_scatter.set_offsets(np.array(active_dropoffs) if active_dropoffs else np.empty((0, 2)))

    def step(frame):
        for _ in range(5):
            if idx["i"] >= len(events):
                break

            e = events[idx["i"]]
            idx["i"] += 1

            et = e["type"]

            if et == "ANNOUNCE":
                tid = e["task_id"]
                current_task[tid] = {
                    "pickup": e["pickup"],
                    "dropoff": e["dropoff"],
                    "winner": None,
                    "done": False
                }

            elif et == "AWARD":
                tid = e["task_id"]
                if tid in current_task:
                    current_task[tid]["winner"] = e["winner"]

            elif et == "START":
                vehicles[e["vehicle"]] = e["start_pos"]

            elif et == "FINISH":
                vehicles[e["vehicle"]] = e["pos"]
                
            elif et == "POS":
                vehicles[e["vehicle"]] = e["pos"]

            elif et == "DONE":
                tid = e["task_id"]
                if tid in current_task:
                    current_task[tid]["done"] = True

            
            text.set_text(f"events: {idx['i']}/{len(events)}")

        redraw()
        return vehicle_scatter, pickup_scatter, dropoff_scatter, text

    anim = FuncAnimation(fig, step, interval=100, blit=False, cache_frame_data=False)
    plt.show()


if __name__ == "__main__":
    main()
