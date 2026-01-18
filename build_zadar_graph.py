# build_zadar_graph.py
import os
import osmnx as ox

PLACE = "Zadar, Croatia"
OUT_DIR = "data"
OUT_PATH = os.path.join(OUT_DIR, "zadar_drive.graphml")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    
    G = ox.graph_from_place(PLACE, network_type="drive", simplify=True)

    
    ox.save_graphml(G, OUT_PATH)
    print(f"Saved: {OUT_PATH}")

if __name__ == "__main__":
    main()
