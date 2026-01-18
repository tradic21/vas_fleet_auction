# vas_fleet_auction

Projekt simulira raspodjelu zadataka dostave u gradu Zadru pomoću aukcijskog pristupa: dispatcher objavljuje zadatke, a vozila šalju ponude (bid). Uspoređuju se dvije strategije određivanja bida: **nearest** i **marginal**.

## Struktura projekta
- dispatcher.py – objavljuje zadatke, prikuplja bidove i dodjeljuje zadatke vozilima
- vehicle.py – vozila računaju bid (nearest/marginal) i izvršavaju rute
- run_batch.py – batch pokretanje više scenarija/seedova i spremanje rezultata u CSV
- scenarios.py – definicija scenarija (low/medium/high)
- world.py – RoadWorld rad s cestovnim grafom (shortest path, distance, sampling)
- data/zadar_drive.graphml – cestovni graf Zadra (OSMnx GraphML)
- state_store.py – spremanje stanja u map_viewer/state.json za viewer
- map_viewer/ – web prikaz (Leaflet) vozila, ruta i isporuka
- logger.py – zapis događaja u events.csv

## Preduvjeti
- Python 3.10+ (ili verzija koju koristiš u projektu)
- Paketi: spade, osmnx, networkx, pandas, matplotlib

## Instalacija
1) Kreiraj virtualno okruženje:
   python3 -m venv .venv

2) Aktiviraj okruženje:
   source .venv/bin/activate

3) Instaliraj ovisnosti:
   pip install spade osmnx networkx pandas matplotlib

## Pokretanje batch eksperimenata
1) Aktiviraj virtualno okruženje:
   source .venv/bin/activate

2) Pokreni batch:
   python run_batch.py

Izlazne datoteke (primjer):
- results_nearest.csv
- results_marginal.csv

Parametri batch izvođenja (npr. MAX_TASKS, SEEDS, override scenarija) nalaze se u run_batch.py.

## Viewer (karta)
Viewer čita map_viewer/state.json i prikazuje:
- pozicije vozila + status (FREE/BUSY)
- trenutni task (pickup/dropoff) i rutu
- markere završenih dostava (deliveries)

Pokretanje lokalnog servera:
1) Uđi u mapu viewera:
   cd map_viewer

2) Pokreni server:
   python3 -m http.server 8000

3) Otvori u pregledniku:
   http://localhost:8000

## Strategije (nearest vs marginal)
- nearest: bid se temelji primarno na ukupnoj udaljenosti (approach + job) + mali slučajni šum.
- marginal: bid uključuje udaljenost + penalizaciju za očekivano kašnjenje (ovisno o deadline-u) + penalizaciju za trenutno opterećenje (queue) + šum.

Zbog toga marginal često bolje rasporedi zadatke kad su rokovi tijesni i vozila neravnomjerno opterećena.

## Metrike u rezultatima
- on_time_pct – postotak zadataka završenih na vrijeme
- late_pct – postotak zadataka koji kasne
- avg_lateness_sec – prosječno kašnjenje među zakašnjelim zadacima
- avg_lateness_all_sec – prosječno kašnjenje uključujući i zadatke na vrijeme (0 za on-time)
- avg_assignment_time_sec – prosječno vrijeme dodjele zadatka (aukcije)
- total_distance – ukupno prijeđena udaljenost (m)

## Licenca
Projekt je objavljen pod licencom GPL-3.0 (vidi LICENSE).

## Poveznica na kod
https://github.com/tradic21/vas_fleet_auction
