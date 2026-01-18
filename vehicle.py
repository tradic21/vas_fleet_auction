# vehicle.py
import asyncio
import json
import os
import random
import time
from typing import Optional, Tuple, List, Dict, Any

import spade
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

from logger import log_event

try:
    from state_store import update_vehicle
except Exception:
    update_vehicle = None

ONTOLOGY = "dispatch_auction"


DISPATCHER_JID = os.getenv("DISPATCHER_JID", "dispatcher@localhost")


VIEWER_EVERY_N = int(os.getenv("VIEWER_EVERY_N", "4"))


ANIMATE_PICKUP_SEC = float(os.getenv("ANIMATE_PICKUP_SEC", "2.5"))


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    import math
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _queue_ids_from_agent(agent: "Vehicle") -> List[str]:
    try:
        items = list(agent.task_queue._queue)  
        out: List[str] = []
        for t in items:
            if isinstance(t, dict) and "task_id" in t:
                out.append(str(t.get("task_id")))
            else:
                out.append("?")
        return out
    except Exception:
        return []


def _viewer_update(agent: "Vehicle", task_id: str = "", busy: Optional[bool] = None) -> None:
    if update_vehicle is None:
        return
    try:
        q = _queue_ids_from_agent(agent)
        update_vehicle(
            str(agent.jid),
            agent.pos,
            busy=agent.busy if busy is None else busy,
            task_id=task_id,
            queue=q,
            queue_len=len(q),
        )
    except Exception:
        pass


async def animate_line(
    agent: "Vehicle",
    start_latlon: List[float],
    end_latlon: List[float],
    duration_sec: float,
    steps: int = 12,
    task_id: str = "",
) -> None:
    
    if steps < 2:
        steps = 2
    if duration_sec <= 0:
        agent.pos = [float(end_latlon[0]), float(end_latlon[1])]
        _viewer_update(agent, task_id=task_id, busy=True)
        return

    start_t = time.time()
    for i in range(steps):
        t = i / (steps - 1)
        lat = lerp(float(start_latlon[0]), float(end_latlon[0]), t)
        lon = lerp(float(start_latlon[1]), float(end_latlon[1]), t)

        agent.pos = [lat, lon]
        _viewer_update(agent, task_id=task_id, busy=True)

        target = start_t + duration_sec * t
        delay = target - time.time()
        if delay > 0:
            await asyncio.sleep(delay)


class Vehicle(Agent):
    def __init__(
        self,
        jid: str,
        password: str,
        start_pos, 
        capacity: int = 3,
        speed_mps: float = 8.0,  
        strategy: str = "nearest",
        seed: int = 1,
        traffic_range: Tuple[float, float] = (0.9, 1.6),
        service_range: Tuple[float, float] = (1.0, 3.0),
        lateness_weight: float = 5.0,
        queue_penalty_weight: float = 1.0,
    ):
        super().__init__(jid, password)

        self.pos = list(start_pos)
        self.capacity = int(capacity)
        self.speed_mps = float(speed_mps)
        self.strategy = str(strategy)

        base_seed = int(seed)
        salt = abs(hash(str(jid))) % 10_000
        self.seed = base_seed * 10_000 + salt
        self.rng = random.Random(self.seed)

        self.traffic_range = (float(traffic_range[0]), float(traffic_range[1]))
        self.service_range = (float(service_range[0]), float(service_range[1]))

        self.lateness_weight = float(lateness_weight)
        self.queue_penalty_weight = float(queue_penalty_weight)

        self.busy = False
        self.busy_until = 0.0
        self.task_queue: asyncio.Queue = asyncio.Queue()

    def active_load(self) -> int:
        return (1 if self.busy else 0) + self.task_queue.qsize()

    def expected_job_sec(self, distance_m: float) -> float:
        expected_traffic = (self.traffic_range[0] + self.traffic_range[1]) / 2.0
        expected_service = (self.service_range[0] + self.service_range[1]) / 2.0
        move_sec = (distance_m / max(0.001, self.speed_mps)) * expected_traffic
        return move_sec + expected_service

    def _make_bid_msg(self, to_jid: str, task_id: str, bid: Optional[float] = None, no_bid: bool = False) -> Message:
        reply = Message(to=to_jid)
        reply.set_metadata("ontology", ONTOLOGY)
        reply.set_metadata("intent", "bid")
        payload: Dict[str, Any] = {"task_id": task_id}
        if no_bid:
            payload["no_bid"] = True
        else:
            payload["bid"] = float(bid if bid is not None else 0.0)
        reply.body = json.dumps(payload)
        return reply

    class Listen(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=5)
            if not msg:
                return
            if msg.get_metadata("ontology") != ONTOLOGY:
                return

            intent = msg.get_metadata("intent")

            if intent == "announce_task":
                task = json.loads(msg.body)
                task_id = str(task.get("task_id", ""))
                if not task_id:
                    return

                deadline_ts = float(task.get("deadline_ts", time.time()))
                now = time.time()

                load_now = self.agent.active_load()
                if load_now >= self.agent.capacity:
                    print(f"[{self.agent.jid}] NO_BID for {task_id} (load={load_now}/{self.agent.capacity})")
                    log_event("NO_BID", task_id=task_id, vehicle=str(self.agent.jid))
                    reply = self.agent._make_bid_msg(str(msg.sender), task_id, no_bid=True)
                    await self.send(reply)  
                    return

                job_distance_m = float(task.get("distance_m", 0.0))

                pickup_latlon = task.get("pickup_latlon")
                dropoff_latlon = task.get("dropoff_latlon")

                approach_m = 0.0
                if isinstance(pickup_latlon, (list, tuple)) and len(pickup_latlon) == 2:
                    try:
                        approach_m = haversine_m(
                            float(self.agent.pos[0]), float(self.agent.pos[1]),
                            float(pickup_latlon[0]), float(pickup_latlon[1]),
                        )
                    except Exception:
                        approach_m = 0.0

                if (job_distance_m <= 0.0) and isinstance(pickup_latlon, (list, tuple)) and isinstance(dropoff_latlon, (list, tuple)):
                    if len(pickup_latlon) == 2 and len(dropoff_latlon) == 2:
                        try:
                            job_distance_m = haversine_m(
                                float(pickup_latlon[0]), float(pickup_latlon[1]),
                                float(dropoff_latlon[0]), float(dropoff_latlon[1]),
                            )
                        except Exception:
                            job_distance_m = 0.0

                total_trip_m = max(0.0, approach_m) + max(0.0, job_distance_m)

                noise = self.agent.rng.random()

                if self.agent.strategy == "nearest":
                    bid = total_trip_m + noise
                elif self.agent.strategy == "marginal":
                    available_at = max(now, float(self.agent.busy_until))
                    queued = int(self.agent.task_queue.qsize())

                    expected_one_job = self.agent.expected_job_sec(total_trip_m)
                    queue_wait = queued * expected_one_job

                    eta_finish = available_at + queue_wait + expected_one_job
                    lateness = max(0.0, eta_finish - deadline_ts)

                    bid = (
                        total_trip_m
                        + (self.agent.lateness_weight * lateness)
                        + (self.agent.queue_penalty_weight * queued)
                        + noise
                    )
                else:
                    bid = total_trip_m + noise

                print(
                    f"[{self.agent.jid}] ({self.agent.strategy}) Bid for {task_id}: {bid:.2f} "
                    f"(approach={approach_m:.0f}m, job={job_distance_m:.0f}m, load={load_now}/{self.agent.capacity})"
                )
                log_event("BID", task_id=task_id, vehicle=str(self.agent.jid), bid=bid)

                reply = self.agent._make_bid_msg(str(msg.sender), task_id, bid=bid, no_bid=False)
                await self.send(reply)  

            elif intent == "award":
                task = json.loads(msg.body)
                task_id = str(task.get("task_id", ""))

                await self.agent.task_queue.put(task)

                print(f"[{self.agent.jid}]  WON {task_id} -> queued (q={self.agent.task_queue.qsize()})")
                log_event("ASSIGNED", task_id=task_id, vehicle=str(self.agent.jid))

                _viewer_update(self.agent, task_id=task_id, busy=self.agent.busy)

            elif intent == "reject":
                data = json.loads(msg.body)
                print(f"[{self.agent.jid}]  Lost {data.get('task_id')}")

    class Worker(CyclicBehaviour):
        async def run(self):
            if self.agent.task_queue.empty():
                await asyncio.sleep(0.2)
                return
            if self.agent.busy:
                await asyncio.sleep(0.2)
                return

            task = await self.agent.task_queue.get()
            task_id = str(task.get("task_id", ""))
            deadline_ts = float(task.get("deadline_ts", time.time()))

            route = task.get("route_latlon") or []
            job_distance_m = float(task.get("distance_m", 0.0))  

            pickup_latlon = task.get("pickup_latlon")
            dropoff_latlon = task.get("dropoff_latlon")

            if (not route) and isinstance(pickup_latlon, (list, tuple)) and isinstance(dropoff_latlon, (list, tuple)):
                if len(pickup_latlon) == 2 and len(dropoff_latlon) == 2:
                    route = [[float(pickup_latlon[0]), float(pickup_latlon[1])],
                             [float(dropoff_latlon[0]), float(dropoff_latlon[1])]]
                    if job_distance_m <= 0:
                        job_distance_m = haversine_m(route[0][0], route[0][1], route[1][0], route[1][1])

            if not route or len(route) < 2:
                print(f"[{self.agent.jid}] WARNING: task {task_id} has no route -> finishing as NO_ROUTE.")
                finished_ts = time.time()
                log_event("FINISH", task_id=task_id, vehicle=str(self.agent.jid), status="NO_ROUTE")

                self.agent.busy = False
                self.agent.busy_until = 0.0
                _viewer_update(self.agent, task_id="", busy=False)

                update = Message(to=DISPATCHER_JID)
                update.set_metadata("ontology", ONTOLOGY)
                update.set_metadata("intent", "status_update")
                update.body = json.dumps(
                    {
                        "task_id": task_id,
                        "vehicle": str(self.agent.jid),
                        "finished_ts": finished_ts,
                        "deadline_ts": deadline_ts,
                        "distance": 0.0,
                        "delivered_latlon": [float(self.agent.pos[0]), float(self.agent.pos[1])],
                    }
                )
                await self.send(update)
                return

            traffic_factor = self.agent.rng.uniform(*self.agent.traffic_range)
            service_time = self.agent.rng.uniform(*self.agent.service_range)

            effective_speed = self.agent.speed_mps / max(0.0001, traffic_factor)

            pickup = [float(route[0][0]), float(route[0][1])]
            current = [float(self.agent.pos[0]), float(self.agent.pos[1])]
            approach_m = haversine_m(current[0], current[1], pickup[0], pickup[1])
            approach_time_sec = approach_m / max(0.001, effective_speed)

            job_move_time_sec = float(job_distance_m) / max(0.001, effective_speed)

            total_expected = approach_time_sec + job_move_time_sec + service_time

            self.agent.busy = True
            self.agent.busy_until = time.time() + total_expected
            _viewer_update(self.agent, task_id=task_id, busy=True)

            print(
                f"[{self.agent.jid}] Executing {task_id}: approach={approach_m:.0f}m, job={job_distance_m:.0f}m, "
                f"traffic={traffic_factor:.2f}, speed={effective_speed:.2f}m/s, service={service_time:.1f}s"
            )
            log_event("START", task_id=task_id, vehicle=str(self.agent.jid))

            anim_sec = 0.0
            if ANIMATE_PICKUP_SEC > 0:
                anim_sec = min(float(ANIMATE_PICKUP_SEC), float(approach_time_sec))

            if anim_sec > 0:
                await animate_line(
                    self.agent,
                    current,
                    pickup,
                    duration_sec=anim_sec,
                    steps=12,
                    task_id=task_id,
                )
            else:
                self.agent.pos = [pickup[0], pickup[1]]
                _viewer_update(self.agent, task_id=task_id, busy=True)

            remaining_approach = float(approach_time_sec) - float(anim_sec)
            if remaining_approach > 0:
                await asyncio.sleep(remaining_approach)

            self.agent.pos = [pickup[0], pickup[1]]
            _viewer_update(self.agent, task_id=task_id, busy=True)

            n = len(route)
            if n < 2:
                self.agent.pos = [float(route[-1][0]), float(route[-1][1])]
                _viewer_update(self.agent, task_id=task_id, busy=True)
            else:
                steps = min(30, n - 1)
                idxs = [int(i * (n - 1) / steps) for i in range(steps + 1)]
                idxs = sorted(set(idxs))

                start_ts = time.time()
                for i_idx, idx in enumerate(idxs):
                    target_ts = start_ts + (job_move_time_sec * (i_idx / max(1, len(idxs) - 1)))
                    delay = target_ts - time.time()
                    if delay > 0:
                        await asyncio.sleep(delay)

                    lat, lon = float(route[idx][0]), float(route[idx][1])
                    self.agent.pos = [lat, lon]
                    if (i_idx % max(1, VIEWER_EVERY_N)) == 0 or i_idx == len(idxs) - 1:
                        _viewer_update(self.agent, task_id=task_id, busy=True)

            await asyncio.sleep(service_time)

            finished_ts = time.time()
            lateness = max(0.0, finished_ts - deadline_ts)
            status = "ON_TIME" if lateness <= 0.0001 else f"LATE(+{lateness:.1f}s)"

            self.agent.busy = False
            self.agent.busy_until = 0.0

            print(f"[{self.agent.jid}] Finished {task_id}: {status}")
            log_event("FINISH", task_id=task_id, vehicle=str(self.agent.jid), status=status)

            _viewer_update(self.agent, task_id="", busy=False)

            update = Message(to=DISPATCHER_JID)
            update.set_metadata("ontology", ONTOLOGY)
            update.set_metadata("intent", "status_update")
            update.body = json.dumps(
                {
                    "task_id": task_id,
                    "vehicle": str(self.agent.jid),
                    "finished_ts": finished_ts,
                    "deadline_ts": deadline_ts,
                    "distance": float(max(0.0, approach_m) + max(0.0, job_distance_m)),
                    "delivered_latlon": [float(self.agent.pos[0]), float(self.agent.pos[1])],
                }
            )
            await self.send(update)

    async def setup(self):
        print(
            f"[{self.jid}] Started pos={self.pos} cap={self.capacity} "
            f"speed_mps={self.speed_mps} strategy={self.strategy} seed={self.seed}"
        )
        log_event("SPAWN", vehicle=str(self.jid), pos=self.pos)

        self.busy = False
        self.busy_until = 0.0
        _viewer_update(self, task_id="", busy=False)

        tpl = Template()
        tpl.set_metadata("ontology", ONTOLOGY)
        self.add_behaviour(self.Listen(), tpl)
        self.add_behaviour(self.Worker())


async def main(jid: str, start_pos: List[float], strategy: str, seed: int):
    a = Vehicle(jid, "lozinka123", start_pos=start_pos, strategy=strategy, seed=seed)
    await a.start()
    try:
        while a.is_alive():
            await asyncio.sleep(1)
    finally:
        await a.stop()


if __name__ == "__main__":
    import sys

    if len(sys.argv) not in (4, 5, 6):
        print("Usage: python3 vehicle.py <jid> <lat> <lon> [nearest|marginal] [seed]")
        raise SystemExit(1)

    jid = sys.argv[1]
    lat = float(sys.argv[2])
    lon = float(sys.argv[3])
    strategy = sys.argv[4] if len(sys.argv) >= 5 else "nearest"
    seed = int(sys.argv[5]) if len(sys.argv) == 6 else 1

    spade.run(main(jid, [lat, lon], strategy, seed))

