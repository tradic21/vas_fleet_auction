# dispatcher.py
import asyncio
import csv
import json
import random
import time
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Any

import spade
from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

from logger import log_event

try:
    from state_store import update_task, update_award, clear_task, add_delivery
except Exception:
    update_task = None
    update_award = None
    clear_task = None
    add_delivery = None

try:
    from scenarios import SCENARIOS
except Exception:
    SCENARIOS = {}

from world import RoadWorld

ONTOLOGY = "dispatch_auction"


@dataclass
class Stats:
    tasks_announced: int = 0
    tasks_awarded: int = 0
    tasks_completed: int = 0

    tasks_on_time: int = 0
    tasks_late: int = 0
    total_lateness_sec: float = 0.0        
    total_lateness_all_sec: float = 0.0    
    total_distance: float = 0.0            

    total_assignment_time_sec: float = 0.0
    assignment_samples: int = 0

    messages_sent: int = 0
    messages_received: int = 0


class Dispatcher(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        vehicles: List[str],
        task_period_sec: int = 10,
        deadline_range_sec=(40, 90),
        scenario: str = "custom",
        seed: int = 1,
        bid_wait_sec: float = 2.0,
        max_tasks: Optional[int] = None,
        auto_stop: bool = True,
        
        graphml_path: str = "zadar.graphml",
        use_road_world: bool = True,
        
        vehicle_starts: Optional[Dict[str, List[float]]] = None,
        
        max_route_resample: int = 30,
    ):
        super().__init__(jid, password)
        self.vehicles = vehicles

        self.scenario = scenario
        self.seed = int(seed)
        self.bid_wait_sec = float(bid_wait_sec)

        self.max_tasks = max_tasks
        self.auto_stop = bool(auto_stop)

        self.rng = random.Random(self.seed)

        
        self.scenario_conf = None
        if SCENARIOS and scenario in SCENARIOS:
            conf = SCENARIOS[scenario]
            self.scenario_conf = conf
            task_period_sec = int(getattr(conf, "task_period_sec", task_period_sec))
            slack_min = int(getattr(conf, "slack_min_sec", deadline_range_sec[0]))
            slack_max = int(getattr(conf, "slack_max_sec", deadline_range_sec[1]))
            deadline_range_sec = (slack_min, slack_max)

        self.task_period_sec = int(task_period_sec)
        self.deadline_range_sec = (int(deadline_range_sec[0]), int(deadline_range_sec[1]))

      
        self.current_task: Dict[str, Any] = {}
        self.bids: Dict[str, float] = {}          
        self.no_bids: Set[str] = set()            
        self.auction_open_ts: Optional[float] = None
        self.awarded_task_id: Optional[str] = None
        self.task_announce_ts: Dict[str, float] = {}

        
        self.completed_task_ids: Set[str] = set()

        self.stats = Stats()
        self.run_id = int(time.time())

        self._stopping = False

        
        self.use_road_world = bool(use_road_world)
        self.world = RoadWorld(graphml_path=graphml_path, seed=self.seed) if self.use_road_world else None
        self.max_route_resample = int(max_route_resample)

        
        self.vehicle_starts = vehicle_starts or {
            "vozilo1@localhost": [44.1156, 15.2278],  # Poluotok / centar
            "vozilo2@localhost": [44.1235, 15.2405],  # Voštarnica
            "vozilo3@localhost": [44.1320, 15.2160],  # Borik
            "vozilo4@localhost": [44.1080, 15.2625],  # Bili brig / istok
        }

    def _count_sent(self, msg: Message) -> Message:
        self.stats.messages_sent += 1
        return msg

    def pending(self) -> int:
        return self.stats.tasks_awarded - self.stats.tasks_completed

    def _safe_update_task(self, task: Dict[str, Any]):
        if update_task is None:
            return
        try:
            update_task(task)
        except Exception as e:
            print(f"[DISPATCH] Viewer update_task failed: {e}")

    def _safe_update_award(self, task_id: str, winner: str):
        if update_award is None:
            return
        try:
            update_award(task_id, winner)
        except Exception:
            pass

    def _safe_clear_task(self):
        if clear_task is None:
            return
        try:
            clear_task()
        except Exception:
            pass

    

    class AnnounceTask(PeriodicBehaviour):
        async def run(self):
            if self.agent.max_tasks is not None and self.agent.stats.tasks_announced >= self.agent.max_tasks:
                return

            
            cur_id = self.agent.current_task.get("task_id")
            if cur_id and self.agent.awarded_task_id != cur_id:
                return

            now = time.time()
            task_id = f"T{int(now)}-{self.agent.rng.randint(100, 999)}"

            
            if self.agent.scenario_conf and hasattr(self.agent.scenario_conf, "sample_deadline_slack"):
                deadline_sec = int(self.agent.scenario_conf.sample_deadline_slack(self.agent.rng))
            else:
                deadline_sec = int(self.agent.rng.randint(*self.agent.deadline_range_sec))

           
            if self.agent.use_road_world and self.agent.world is not None:
                task = None

                
                for _ in range(max(1, self.agent.max_route_resample)):
                    pu, dv = self.agent.world.sample_task_nodes()

                    distance_m = float(self.agent.world.dist_m(pu, dv))
                    if not math.isfinite(distance_m) or distance_m <= 0.0:
                        continue

                    route_latlon = self.agent.world.path_latlon(pu, dv)
                    if not isinstance(route_latlon, list) or len(route_latlon) < 2:
                        continue

                    pickup_latlon = self.agent.world.node_latlon(pu)   
                    dropoff_latlon = self.agent.world.node_latlon(dv)

                    
                    task = {
                        "task_id": task_id,
                        "release_ts": now,
                        "deadline_ts": now + deadline_sec,
                       
                        "pickup_node": pu,
                        "dropoff_node": dv,
                        "pickup_latlon": [float(pickup_latlon[0]), float(pickup_latlon[1])],
                        "dropoff_latlon": [float(dropoff_latlon[0]), float(dropoff_latlon[1])],
                        "route_latlon": route_latlon,     
                        "distance_m": float(distance_m),   
                        
                        "size": 1,
                        "winner": None,
                    }
                    break

                if task is None:
                    print("[DISPATCH] WARNING: Could not sample valid ROAD route (no-path/inf). Skipping announce.")
                    log_event("ROUTE_FAIL", task_id=task_id)
                    return

            else:
                pickup = [self.agent.rng.randint(0, 10), self.agent.rng.randint(0, 10)]
                dropoff = [self.agent.rng.randint(0, 10), self.agent.rng.randint(0, 10)]
                task = {
                    "task_id": task_id,
                    "pickup": pickup,
                    "dropoff": dropoff,
                    "size": 1,
                    "release_ts": now,
                    "deadline_ts": now + deadline_sec,
                    "winner": None,
                }

            
            self.agent.current_task = task
            self.agent.bids = {}
            self.agent.no_bids = set()
            self.agent.auction_open_ts = now
            self.agent.awarded_task_id = None

            self.agent.stats.tasks_announced += 1
            self.agent.task_announce_ts[task_id] = now

           
            if "pickup_latlon" in task:
                print(
                    f"\n[DISPATCH] Announce {task_id} | ROAD dist={task['distance_m']:.0f}m | deadline in {deadline_sec}s"
                )
                log_event(
                    "ANNOUNCE",
                    task_id=task_id,
                    pickup=task["pickup_latlon"],
                    dropoff=task["dropoff_latlon"],
                    deadline_ts=task["deadline_ts"],
                )
            else:
                print(
                    f"\n[DISPATCH] Announce {task_id} | pickup={task['pickup']} dropoff={task['dropoff']} | deadline in {deadline_sec}s"
                )
                log_event(
                    "ANNOUNCE",
                    task_id=task_id,
                    pickup=task["pickup"],
                    dropoff=task["dropoff"],
                    deadline_ts=task["deadline_ts"],
                )

            
            self.agent._safe_update_task(task)

          
            for vjid in self.agent.vehicles:
                msg = Message(to=vjid)
                msg.set_metadata("ontology", ONTOLOGY)
                msg.set_metadata("intent", "announce_task")
                msg.body = json.dumps(task)
                await self.send(self.agent._count_sent(msg))

    class Inbox(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=0.5)

            if msg:
                self.agent.stats.messages_received += 1
                if msg.get_metadata("ontology") != ONTOLOGY:
                    return

                intent = msg.get_metadata("intent")

                if intent == "bid":
                    try:
                        data = json.loads(msg.body)
                    except Exception:
                        return

                    current_id = self.agent.current_task.get("task_id")
                    if not current_id or data.get("task_id") != current_id:
                        return

                    sender_bare = str(msg.sender).split("/")[0]

                    if bool(data.get("no_bid")):
                        self.agent.no_bids.add(sender_bare)
                        print(f"[DISPATCH] Got NO_BID from {sender_bare}")
                        log_event("NO_BID", task_id=current_id, vehicle=sender_bare)
                        return

                    try:
                        bid_value = float(data["bid"])
                    except Exception:
                        self.agent.no_bids.add(sender_bare)
                        log_event("NO_BID", task_id=current_id, vehicle=sender_bare)
                        return

                    if not math.isfinite(bid_value):
                        self.agent.no_bids.add(sender_bare)
                        print(f"[DISPATCH] Got invalid bid (non-finite) from {sender_bare} -> NO_BID")
                        log_event("NO_BID", task_id=current_id, vehicle=sender_bare)
                        return

                    self.agent.bids[sender_bare] = bid_value
                    print(f"[DISPATCH] Got bid {bid_value:.2f} from {sender_bare}")
                    log_event("BID", task_id=current_id, vehicle=sender_bare, bid=bid_value)

                elif intent == "status_update":
                    try:
                        data = json.loads(msg.body)
                    except Exception:
                        return

                    task_id = str(data.get("task_id", ""))
                    if not task_id:
                        return

                    
                    if task_id in self.agent.completed_task_ids:
                        return
                    self.agent.completed_task_ids.add(task_id)

                    vehicle = str(data.get("vehicle", ""))
                    finished_ts = float(data.get("finished_ts", time.time()))
                    deadline_ts = float(data.get("deadline_ts", finished_ts))

                   
                    distance = float(data.get("distance", 0.0))
                    lateness = max(0.0, finished_ts - deadline_ts)

                    self.agent.stats.tasks_completed += 1
                    self.agent.stats.total_distance += distance
                    self.agent.stats.total_lateness_all_sec += lateness

                    if lateness <= 0.0001:
                        self.agent.stats.tasks_on_time += 1
                        status = "ON_TIME"
                    else:
                        self.agent.stats.tasks_late += 1
                        self.agent.stats.total_lateness_sec += lateness
                        status = f"LATE(+{lateness:.1f}s)"

                    print(f"[DISPATCH] DONE {task_id} by {vehicle} | {status} | dist={distance:.0f}")
                    log_event(
                        "DONE",
                        task_id=task_id,
                        vehicle=vehicle,
                        finished_ts=finished_ts,
                        deadline_ts=deadline_ts,
                        distance=distance,
                    )

                    
                    if add_delivery is not None:
                        deliv = data.get("delivered_latlon")
                        if isinstance(deliv, list) and len(deliv) == 2:
                            try:
                                add_delivery(
                                    task_id=task_id,
                                    vehicle=vehicle,
                                    lat=float(deliv[0]),
                                    lon=float(deliv[1]),
                                    finished_ts=finished_ts,
                                    deadline_ts=deadline_ts,
                                    distance=distance,
                                )
                            except Exception:
                                pass

                    
                    self.agent._safe_clear_task()

            await self._maybe_award()
            await self._maybe_autostop()

        async def _maybe_award(self):
            task = self.agent.current_task
            task_id = task.get("task_id")
            if not task_id:
                return
            if self.agent.awarded_task_id == task_id:
                return

            
            all_responded = (len(self.agent.bids) + len(self.agent.no_bids)) >= len(self.agent.vehicles)

            timed_out = False
            if self.agent.auction_open_ts is not None:
                timed_out = (time.time() - self.agent.auction_open_ts) >= self.agent.bid_wait_sec

            if not (all_responded or timed_out):
                return

            
            if not self.agent.bids:
                print(f"[DISPATCH] No valid bids for {task_id} -> dropping task")
                log_event("NO_BIDS", task_id=task_id)
                self.agent.awarded_task_id = task_id
                self.agent._safe_clear_task()
                return

            winner = min(self.agent.bids, key=self.agent.bids.get)
            win_bid = self.agent.bids[winner]

            print(f"[DISPATCH] AWARD {task_id} -> {winner} (bid={win_bid:.2f})")

            self.agent.stats.tasks_awarded += 1
            announce_ts = self.agent.task_announce_ts.get(task_id)
            if announce_ts is not None:
                assign_time = time.time() - announce_ts
                self.agent.stats.total_assignment_time_sec += assign_time
                self.agent.stats.assignment_samples += 1

            
            try:
                self.agent.current_task["winner"] = winner
            except Exception:
                pass

          
            self.agent._safe_update_award(task_id, winner)

            log_event("AWARD", task_id=task_id, winner=winner, bid=win_bid)

            award_msg = Message(to=winner)
            award_msg.set_metadata("ontology", ONTOLOGY)
            award_msg.set_metadata("intent", "award")
            award_msg.body = json.dumps(task)
            await self.send(self.agent._count_sent(award_msg))

            for vjid in self.agent.vehicles:
                if vjid == winner:
                    continue
                rej = Message(to=vjid)
                rej.set_metadata("ontology", ONTOLOGY)
                rej.set_metadata("intent", "reject")
                rej.body = json.dumps({"task_id": task_id, "winner": winner, "bid": win_bid})
                await self.send(self.agent._count_sent(rej))

            self.agent.awarded_task_id = task_id

        async def _maybe_autostop(self):
            if not self.agent.auto_stop:
                return
            if self.agent._stopping:
                return
            if self.agent.max_tasks is None:
                return

           
            cur_id = self.agent.current_task.get("task_id")
            if cur_id and self.agent.awarded_task_id != cur_id:
                return

            if self.agent.stats.tasks_announced >= self.agent.max_tasks and self.agent.pending() <= 0:
                self.agent._stopping = True
                print("[DISPATCH] Auto-stop: max_tasks reached and no pending tasks.")
                await self.agent.stop()

    async def setup(self):
        print(f"[DISPATCH] Started as {self.jid} (scenario={self.scenario}, seed={self.seed})")
        if self.max_tasks is not None:
            print(f"[DISPATCH] max_tasks={self.max_tasks} | auto_stop={self.auto_stop}")
        if self.use_road_world:
            print("[DISPATCH] Mode=ROAD (OSMnx graphml)")

        self.add_behaviour(self.AnnounceTask(period=self.task_period_sec))

        tpl = Template()
        tpl.set_metadata("ontology", ONTOLOGY)
        self.add_behaviour(self.Inbox(), tpl)

    def export_csv(self, filename: str):
        s = self.stats
        on_time_pct = (s.tasks_on_time / s.tasks_completed * 100.0) if s.tasks_completed else 0.0
        late_pct = (s.tasks_late / s.tasks_completed * 100.0) if s.tasks_completed else 0.0

        avg_lateness = (s.total_lateness_sec / s.tasks_late) if s.tasks_late else 0.0
        avg_lateness_all = (s.total_lateness_all_sec / s.tasks_completed) if s.tasks_completed else 0.0

        pending = s.tasks_awarded - s.tasks_completed
        avg_assignment_time = (s.total_assignment_time_sec / s.assignment_samples) if s.assignment_samples else 0.0
        messages_per_task = ((s.messages_sent + s.messages_received) / s.tasks_announced) if s.tasks_announced else 0.0

        row = {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "seed": self.seed,
            "vehicles": len(self.vehicles),
            "task_period_sec": self.task_period_sec,
            "deadline_min_sec": int(self.deadline_range_sec[0]),
            "deadline_max_sec": int(self.deadline_range_sec[1]),
            "bid_wait_sec": round(self.bid_wait_sec, 2),
            "max_tasks": self.max_tasks if self.max_tasks is not None else "",
            "tasks_announced": s.tasks_announced,
            "tasks_awarded": s.tasks_awarded,
            "tasks_completed": s.tasks_completed,
            "pending": pending,
            "on_time_pct": round(on_time_pct, 2),
            "late_pct": round(late_pct, 2),
            "avg_lateness_sec": round(avg_lateness, 2),
            "avg_lateness_all_sec": round(avg_lateness_all, 2),
            "avg_assignment_time_sec": round(avg_assignment_time, 2),
            "messages_sent": s.messages_sent,
            "messages_received": s.messages_received,
            "messages_per_task": round(messages_per_task, 2),
            "total_distance": round(s.total_distance, 2),
        }

        write_header = False
        try:
            with open(filename, "r", newline=""):
                pass
        except FileNotFoundError:
            write_header = True

        with open(filename, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                w.writeheader()
            w.writerow(row)

        print(f"\n[DISPATCH] Exported results to {filename}")
        print(f"[DISPATCH] Summary: {row}")



async def main():
    vehicles = ["vozilo1@localhost", "vozilo2@localhost", "vozilo3@localhost", "vozilo4@localhost"]
    a = Dispatcher(
        "dispatcher@localhost",
        "lozinka123",
        vehicles,
        scenario="medium",
        seed=1,
        bid_wait_sec=1.0,
        max_tasks=10,
        auto_stop=True,
        graphml_path="zadar.graphml",
        use_road_world=True,
        
        max_route_resample=30,
    )
    await a.start()
    print("[DISPATCH] Running... Ctrl+C za prekid (ili auto_stop)")
    try:
        while a.is_alive():
            await asyncio.sleep(1)
    finally:
        a.export_csv("results.csv")
        await a.stop()


if __name__ == "__main__":
    spade.run(main())

