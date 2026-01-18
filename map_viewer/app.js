// map_viewer/app.js

// Centar Zadra (otprilike)
const ZADAR_CENTER = [44.11972, 15.24222];

const map = L.map("map").setView(ZADAR_CENTER, 13);

// OSM tiles
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const statusEl = document.getElementById("status");

const vehicleMarkers = new Map();
let pickupMarker = null;
let dropoffMarker = null;

function upsertMarker(key, lat, lon, label) {
  const existing = vehicleMarkers.get(key);
  if (existing) {
    existing.setLatLng([lat, lon]);
    existing.setPopupContent(label);
    return existing;
  }
  const m = L.marker([lat, lon]).addTo(map);
  m.bindPopup(label);
  vehicleMarkers.set(key, m);
  return m;
}

function setTaskMarkers(task) {
  if (!task) {
    if (pickupMarker) { map.removeLayer(pickupMarker); pickupMarker = null; }
    if (dropoffMarker) { map.removeLayer(dropoffMarker); dropoffMarker = null; }
    return;
  }

  const p = task.pickup;
  const d = task.dropoff;

  if (!pickupMarker) {
    pickupMarker = L.circleMarker([p.lat, p.lon], { radius: 7 }).addTo(map);
  }
  pickupMarker.setLatLng([p.lat, p.lon]).bindPopup(`PICKUP ${task.task_id}`);

  if (!dropoffMarker) {
    dropoffMarker = L.circleMarker([d.lat, d.lon], { radius: 7 }).addTo(map);
  }
  dropoffMarker.setLatLng([d.lat, d.lon]).bindPopup(`DROPOFF ${task.task_id}`);
}

async function tick() {
  try {
    // cache-bust
    const res = await fetch(`state.json?t=${Date.now()}`);
    if (!res.ok) throw new Error("state.json not found");
    const data = await res.json();

    const vehicles = data.vehicles || {};
    const keys = Object.keys(vehicles);

    statusEl.textContent = `vozila: ${keys.length} | last update: ${new Date((data.ts || 0) * 1000).toLocaleTimeString()}`;

    // update vozila
    for (const [jid, v] of Object.entries(vehicles)) {
      const label = `${jid}<br>x=${v.x?.toFixed?.(1) ?? v.x}, y=${v.y?.toFixed?.(1) ?? v.y}<br>${v.busy ? "BUSY" : "FREE"}`;
      upsertMarker(jid, v.lat, v.lon, label);
    }

    // task markers
    setTaskMarkers(data.task);

  } catch (e) {
    statusEl.textContent = "Čekam state.json...";
  } finally {
    setTimeout(tick, 300); // refresh rate
  }
}

tick();

