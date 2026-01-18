# world.py
import os
import random
import math
from typing import Any, Dict, List, Tuple, Optional

import networkx as nx


try:
    import osmnx as ox
except Exception:
    ox = None


class RoadWorld:

    def __init__(self, graphml_path: str, seed: int = 1, max_sample_tries: int = 80):
        if ox is None:
            raise ImportError("osmnx nije instaliran. Instaliraj: pip install osmnx")

        if not os.path.exists(graphml_path):
            raise FileNotFoundError(f"Ne mogu naći graphml: {graphml_path}")

        self.graphml_path = graphml_path
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.max_sample_tries = int(max_sample_tries)

        
        self.G = ox.load_graphml(graphml_path)

        
        self._normalize_node_ids_to_int_if_possible()

        
        self._coerce_node_xy_to_float()

       
        self._coerce_edge_length_to_float()

     
        self.nodes: List[Any] = list(self.G.nodes)

        if not self.nodes:
            raise RuntimeError("Graf nema čvorova (nodes=0).")


        try:
            self.G_undirected = ox.utils_graph.get_undirected(self.G)  
        except Exception:
            self.G_undirected = self.G.to_undirected()



    def _normalize_node_ids_to_int_if_possible(self) -> None:

        nodes = list(self.G.nodes)
        if not nodes:
            return

        
        sample = nodes[: min(200, len(nodes))]
        if not all(isinstance(n, str) for n in sample):
            return

        def _is_int_str(s: str) -> bool:
            s2 = s.strip()
            return s2.isdigit() or (s2.startswith("-") and s2[1:].isdigit())

        if not all(_is_int_str(str(n)) for n in sample):
            return

        mapping: Dict[Any, Any] = {}
        try:
            for n in nodes:
                mapping[n] = int(str(n).strip())
        except Exception:
            return

       
        self.G = nx.relabel_nodes(self.G, mapping, copy=False)

    def _coerce_node_xy_to_float(self) -> None:
  
        for n, data in self.G.nodes(data=True):
            if "x" in data and data["x"] is not None:
                try:
                    data["x"] = float(data["x"])
                except Exception:
                    pass
            if "y" in data and data["y"] is not None:
                try:
                    data["y"] = float(data["y"])
                except Exception:
                    pass

    def _coerce_edge_length_to_float(self) -> None:

        for u, v, k, data in self.G.edges(keys=True, data=True):
            val = data.get("length", None)

            
            if val is not None:
                try:
                    data["length"] = float(val)
                    continue
                except Exception:
                    pass

            
            try:
                lat1, lon1 = self.node_latlon(u)
                lat2, lon2 = self.node_latlon(v)
                data["length"] = float(self._haversine_m(lat1, lon1, lat2, lon2))
            except Exception:
                data["length"] = 0.0

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371000.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dlat = p2 - p1
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return 2 * R * math.asin(min(1.0, math.sqrt(a)))

   

    def node_latlon(self, n: Any) -> Tuple[float, float]:
        d = self.G.nodes[n]
        return float(d["y"]), float(d["x"])

    def nearest_node(self, lat: float, lon: float) -> Any:
        return ox.distance.nearest_nodes(self.G, X=float(lon), Y=float(lat))



    def dist_m(self, u: Any, v: Any, fallback_undirected: bool = True) -> float:

        try:
            d = nx.shortest_path_length(self.G, u, v, weight="length")
            return float(d)
        except Exception:
            if not fallback_undirected:
                return float("inf")
        try:
            d = nx.shortest_path_length(self.G_undirected, u, v, weight="length")
            return float(d)
        except Exception:
            return float("inf")

    def path_nodes(self, u: Any, v: Any, fallback_undirected: bool = True) -> List[Any]:
        try:
            return list(nx.shortest_path(self.G, u, v, weight="length"))
        except Exception:
            if not fallback_undirected:
                return []
        try:
            return list(nx.shortest_path(self.G_undirected, u, v, weight="length"))
        except Exception:
            return []

    def path_latlon(self, u: Any, v: Any) -> List[List[float]]:
        nodes = self.path_nodes(u, v, fallback_undirected=True)
        if not nodes:
            lat1, lon1 = self.node_latlon(u)
            lat2, lon2 = self.node_latlon(v)
            return [[lat1, lon1], [lat2, lon2]]

        out: List[List[float]] = []
        for n in nodes:
            lat, lon = self.node_latlon(n)
            out.append([lat, lon])
        return out



    def sample_task_nodes(self) -> Tuple[Any, Any]:
        if not self.nodes:
            raise RuntimeError("Graf nema čvorova.")

        for _ in range(self.max_sample_tries):
            pu = self.rng.choice(self.nodes)
            dv = self.rng.choice(self.nodes)
            if dv == pu:
                continue
            d = self.dist_m(pu, dv, fallback_undirected=False)
            if math.isfinite(d) and d > 0:
                return pu, dv

        
        for _ in range(self.max_sample_tries):
            pu = self.rng.choice(self.nodes)
            dv = self.rng.choice(self.nodes)
            if dv == pu:
                continue
            d = self.dist_m(pu, dv, fallback_undirected=True)
            if math.isfinite(d) and d > 0:
                return pu, dv

        raise RuntimeError("Ne mogu naći valjan (pickup, dropoff) par s rutom u grafu.")

