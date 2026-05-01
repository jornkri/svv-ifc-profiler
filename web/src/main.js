// SVV IFC Profiler - frontend entrypoint
// Bruker ArcGIS Maps SDK for JavaScript som kartrammeverk.

import Map from "@arcgis/core/Map.js";
import MapView from "@arcgis/core/views/MapView.js";
import GraphicsLayer from "@arcgis/core/layers/GraphicsLayer.js";
import Graphic from "@arcgis/core/Graphic.js";

const API_BASE = "http://localhost:8000";

// --- Kart -------------------------------------------------------------------
const centerlineLayer = new GraphicsLayer({ id: "centerline" });

const map = new Map({
  basemap: "topo-vector",
  layers: [centerlineLayer],
});

const view = new MapView({
  container: "map",
  map,
  // Norge - default extent. Justeres når senterlinje lastes.
  center: [10.75, 59.91],
  zoom: 6,
});

// --- State ------------------------------------------------------------------
let currentJobId = null;

// --- Opplasting -------------------------------------------------------------
const uploadInput = document.getElementById("upload");
const statusEl = document.getElementById("status");
const stationLabel = document.getElementById("station-label");
const profileImg = document.getElementById("profile-img");

uploadInput.addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;

  statusEl.textContent = `Laster opp ${file.name}…`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const resp = await fetch(`${API_BASE}/api/upload`, {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) throw new Error(`Opplasting feilet: ${resp.status}`);
    const data = await resp.json();
    currentJobId = data.job_id;
    statusEl.textContent = `Jobb ${currentJobId} opprettet. Behandler…`;

    await loadCenterline(currentJobId);
  } catch (err) {
    console.error(err);
    statusEl.textContent = `Feil: ${err.message}`;
  }
});

// --- Senterlinje ------------------------------------------------------------
async function loadCenterline(jobId) {
  // TODO: backend må returnere senterlinje som GeoJSON.
  const resp = await fetch(`${API_BASE}/api/jobs/${jobId}/centerline`);
  if (!resp.ok) {
    statusEl.textContent = "Kunne ikke laste senterlinje (ikke implementert ennå).";
    return;
  }
  const geojson = await resp.json();
  // TODO: konverter GeoJSON-LineString til ArcGIS Polyline og legg til som Graphic.
  console.log("Senterlinje mottatt:", geojson);
}

// --- Klikk på senterlinje ---------------------------------------------------
view.on("click", async (event) => {
  if (!currentJobId) return;

  const hit = await view.hitTest(event, { include: [centerlineLayer] });
  if (!hit.results.length) return;

  // TODO: regn ut nærmeste stasjon (m) på senterlinjen for klikkpunktet.
  const station = 0;
  stationLabel.textContent = `Stasjon: ${station.toFixed(1)} m`;
  profileImg.src = `${API_BASE}/api/jobs/${currentJobId}/section?station=${station}`;
});
