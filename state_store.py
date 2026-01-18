# state_store.py
import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


STATE_PATH = os.getenv("STATE_PATH", os.path.join("map_viewer", "state.json"))

_LOCK = threading.Lock()


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _read_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_state_atomic(state: Dict[str, Any]) -> None:
    _ensure_parent_dir(STATE_PATH)

    d = os.path.dirname(STATE_PATH) or "."
    fd, tmp_path = tempfile.mkstemp(prefix="state_", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_PATH)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _init_defaults(state: Dict[str, Any]) -> Dict[str, Any]:

    state.setdefault("updated_ts", time.time())
    state.setdefault("task", None)              
    state.setdefault("vehicles", [])            
    state.setdefault("vehicles_by_jid", {})     
    state.setdefault("deliveries", [])        
    return state


def _coerce_pos(pos: Any) -> List[float]:

    try:
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            return [float(pos[0]), float(pos[1])]
    except Exception:
        pass
    return [0.0, 0.0]


def _vehicles_list_and_map(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:

    vehicles_list: List[Dict[str, Any]] = []
    vehicles_map: Dict[str, Dict[str, Any]] = {}

    v = state.get("vehicles")
    if isinstance(v, list):
        for item in v:
            if isinstance(item, dict) and item.get("jid"):
                jid = str(item.get("jid"))
                vehicles_list.append(item)
                vehicles_map[jid] = item
    elif isinstance(v, dict):
        
        for jid, item in v.items():
            if isinstance(item, dict):
                item.setdefault("jid", str(jid))
                vehicles_list.append(item)
                vehicles_map[str(jid)] = item

    
    vbj = state.get("vehicles_by_jid")
    if isinstance(vbj, dict):
        for jid, item in vbj.items():
            if isinstance(item, dict):
                if str(jid) not in vehicles_map:
                    vehicles_list.append(item)
                vehicles_map[str(jid)] = item

    return vehicles_list, vehicles_map


def _task_add_alias_fields(task: Dict[str, Any]) -> Dict[str, Any]:

    try:
        if "pickup" not in task and isinstance(task.get("pickup_latlon"), (list, tuple)) and len(task["pickup_latlon"]) == 2:
            task["pickup"] = [float(task["pickup_latlon"][0]), float(task["pickup_latlon"][1])]
        if "dropoff" not in task and isinstance(task.get("dropoff_latlon"), (list, tuple)) and len(task["dropoff_latlon"]) == 2:
            task["dropoff"] = [float(task["dropoff_latlon"][0]), float(task["dropoff_latlon"][1])]

        if "route" not in task and isinstance(task.get("route_latlon"), list):
            task["route"] = task["route_latlon"]

        
        if "distance" not in task and "distance_m" in task:
            try:
                task["distance"] = float(task["distance_m"])
            except Exception:
                pass
    except Exception:
        pass
    return task




def update_task(task: Dict[str, Any]) -> None:
   
    if not isinstance(task, dict):
        return
    with _LOCK:
        state = _init_defaults(_read_state())
        task2 = dict(task)
        task2 = _task_add_alias_fields(task2)
        state["task"] = task2
        state["updated_ts"] = time.time()
        _write_state_atomic(state)


def update_award(task_id: str, winner: str) -> None:
    
    with _LOCK:
        state = _init_defaults(_read_state())
        task = state.get("task")
        if isinstance(task, dict) and str(task.get("task_id")) == str(task_id):
            task["winner"] = str(winner)
            task = _task_add_alias_fields(task)
            state["task"] = task
            state["updated_ts"] = time.time()
            _write_state_atomic(state)


def clear_task() -> None:
    
    with _LOCK:
        state = _init_defaults(_read_state())
        state["task"] = None
        state["updated_ts"] = time.time()
        _write_state_atomic(state)


def update_vehicle(
    jid: str,
    pos: List[float],
    busy: bool = False,
    task_id: str = "",
    queue: Optional[List[str]] = None,
    queue_len: Optional[int] = None,
) -> None:

    jid = str(jid)
    pos2 = _coerce_pos(pos)
    q = list(queue) if isinstance(queue, list) else []
    qlen = int(queue_len) if queue_len is not None else len(q)

    vehicle_obj: Dict[str, Any] = {
        "jid": jid,
        "pos": pos2,                
        "lat": float(pos2[0]),        
        "lon": float(pos2[1]),       
        "busy": bool(busy),
        "task_id": str(task_id or ""),
        "queue": q,
        "queue_len": qlen,
        "updated_ts": time.time(),
    }

    with _LOCK:
        state = _init_defaults(_read_state())
        vehicles_list, vehicles_map = _vehicles_list_and_map(state)

        
        vehicles_map[jid] = vehicle_obj

        
        replaced = False
        for i, item in enumerate(vehicles_list):
            if isinstance(item, dict) and str(item.get("jid")) == jid:
                vehicles_list[i] = vehicle_obj
                replaced = True
                break
        if not replaced:
            vehicles_list.append(vehicle_obj)

        state["vehicles"] = vehicles_list
        state["vehicles_by_jid"] = vehicles_map
        state["updated_ts"] = time.time()
        _write_state_atomic(state)


def add_delivery(
    task_id: str,
    vehicle: str,
    lat: float,
    lon: float,
    finished_ts: float,
    deadline_ts: float,
    distance: float,
) -> None:

    lateness = max(0.0, float(finished_ts) - float(deadline_ts))
    on_time = lateness <= 1e-4

    delivery_obj: Dict[str, Any] = {
        "task_id": str(task_id),
        "vehicle": str(vehicle),
        "lat": float(lat),
        "lon": float(lon),
        "pos": [float(lat), float(lon)],         
        "finished_ts": float(finished_ts),
        "deadline_ts": float(deadline_ts),
        "lateness_sec": float(lateness),
        "on_time": bool(on_time),
        "distance_m": float(distance),
    }

    with _LOCK:
        state = _init_defaults(_read_state())
        deliveries = state.get("deliveries", [])
        if not isinstance(deliveries, list):
            deliveries = []

        deliveries.append(delivery_obj)

        max_keep = int(os.getenv("MAX_DELIVERIES_KEEP", "500"))
        if max_keep > 0 and len(deliveries) > max_keep:
            deliveries = deliveries[-max_keep:]

        state["deliveries"] = deliveries
        state["updated_ts"] = time.time()
        _write_state_atomic(state)

