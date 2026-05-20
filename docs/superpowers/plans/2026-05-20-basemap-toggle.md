# Basemap Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a popup basemap picker to the map with four Geodata basemaps; Kanvas Mørk auto-activates in dark mode.

**Architecture:** All changes are in `web/profilutforsker.html` (the single-file app). A module-level `BASEMAPS` array drives both the picker UI and `setBasemap(id)`. ArcGIS classes needed by `setBasemap` are stored on `window` inside the `try` block where they are imported, so module-level functions can reach them.

**Tech Stack:** ArcGIS JS 5 (`@arcgis/core` via `$arcgis.import`), vanilla JS ES module, inline CSS.

---

## Task 1: Add CSS for basemap picker

**Files:**
- Modify: `web/profilutforsker.html:292`

- [ ] **Step 1: Add picker CSS after `.map-tool.active` rule**

Find this line (≈292):
```css
.map-tool.active { background: var(--svv-navy-900); color: #fff; border-color: transparent; }
```

Insert immediately after it:
```css

.basemap-picker {
  position: absolute; top: 0; right: calc(100% + 8px);
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,.12); padding: 4px; min-width: 148px; z-index: 20;
}
.basemap-picker.hidden { display: none; }
.basemap-option {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 4px; cursor: pointer;
  font-size: 12px; color: var(--ink); user-select: none;
}
.basemap-option:hover { background: var(--paper); }
.basemap-option.active { font-weight: 600; }
.basemap-option .bm-check { margin-left: auto; font-size: 11px; color: var(--svv-green-500); opacity: 0; }
.basemap-option.active .bm-check { opacity: 1; }
.basemap-swatch {
  width: 16px; height: 16px; border-radius: 3px;
  border: 1px solid rgba(0,0,0,.15); flex-shrink: 0;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/profilutforsker.html
git commit -m "style: add basemap picker CSS"
```

---

## Task 2: Add basemap button + picker HTML

**Files:**
- Modify: `web/profilutforsker.html:750–757`

The picker `div` starts empty; JS populates it in Task 4. The group needs `overflow: visible` (overrides the class default of `overflow: hidden`) so the absolutely-positioned picker can escape the box.

- [ ] **Step 1: Add new map-tool-group after the sidebar toggle group**

Find this block (≈750–757):
```html
      <div class="map-tool-group">
        <button class="map-tool" onclick="toggleSidebar()" title="Vis/skjul lag">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1" y="1" width="12" height="12" rx="2" stroke="currentColor" stroke-width="1.2"/>
            <path d="M5 1v12" stroke="currentColor" stroke-width="1.2"/>
          </svg>
        </button>
      </div>
```

Replace with:
```html
      <div class="map-tool-group">
        <button class="map-tool" onclick="toggleSidebar()" title="Vis/skjul lag">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1" y="1" width="12" height="12" rx="2" stroke="currentColor" stroke-width="1.2"/>
            <path d="M5 1v12" stroke="currentColor" stroke-width="1.2"/>
          </svg>
        </button>
      </div>
      <div class="map-tool-group" id="grp-basemap" style="position:relative;overflow:visible">
        <button class="map-tool" id="btn-basemap" onclick="toggleBasemapPicker()" title="Bytt bakgrunnskart">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1" y="1" width="12" height="5.5" rx="1.2" stroke="currentColor" stroke-width="1.2"/>
            <rect x="1" y="7.5" width="12" height="5.5" rx="1.2" stroke="currentColor" stroke-width="1.2"/>
          </svg>
        </button>
        <div id="basemap-picker" class="basemap-picker hidden"></div>
      </div>
```

- [ ] **Step 2: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: add basemap picker button and popup container to map tools"
```

---

## Task 3: Replace GEODATA_KANVAS constant with BASEMAPS array + add state

**Files:**
- Modify: `web/profilutforsker.html:957` (constant), `web/profilutforsker.html:975` (state block)

- [ ] **Step 1: Replace the old constant with the BASEMAPS array**

Find (≈957):
```js
const GEODATA_KANVAS = 'https://vector.services.geodataonline.no/arcgis/rest/services/GeocacheVector/GeocacheKanvas/VectorTileServer';
```

Replace with:
```js
const BASEMAPS = [
  { id: 'kanvas', label: 'Kanvas',    type: 'vtl',  swatch: '#e8e4d8',
    url: 'https://vector.services.geodataonline.no/arcgis/rest/services/GeocacheVector/GeocacheKanvas/VectorTileServer' },
  { id: 'graa',   label: 'Gråtone',  type: 'vtl',  swatch: '#c8c8c8',
    url: 'https://vector.services.geodataonline.no/arcgis/rest/services/GeocacheVector/GeocacheGraatoneTerreng/VectorTileServer' },
  { id: 'bilder', label: 'Bilder',   type: 'tile', swatch: '#2a3a2a',
    url: 'https://services.geodataonline.no/arcgis/rest/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer' },
  { id: 'mork',   label: 'Mørk',     type: 'vtl',  swatch: '#1a2630',
    url: 'https://vector.services.geodataonline.no/arcgis/rest/services/GeocacheVector/GeocacheKanvasMork/VectorTileServer' },
];
```

- [ ] **Step 2: Add basemap state variables**

Find (≈975):
```js
let darkMode = false;
```

Replace with:
```js
let darkMode = false;
let activeBasemapId = 'kanvas';
let lightBasemapId  = 'kanvas';
```

- [ ] **Step 3: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: add BASEMAPS config array and basemap state variables"
```

---

## Task 4: Add TileLayer to ArcGIS imports and expose classes on window

**Files:**
- Modify: `web/profilutforsker.html:1399–1412`

`TileLayer` is needed for the "Bilder" MapServer endpoint. The three ArcGIS classes are stored on `window` so module-level functions defined outside the `try` block can use them.

- [ ] **Step 1: Extend the $arcgis.import call and expose classes**

Find (≈1399–1412):
```js
  const [Map, MapView, VectorTileLayer, FeatureLayer, Basemap, esriId, GraphicsLayer, Graphic] =
    await $arcgis.import([
      '@arcgis/core/Map.js',
      '@arcgis/core/views/MapView.js',
      '@arcgis/core/layers/VectorTileLayer.js',
      '@arcgis/core/layers/FeatureLayer.js',
      '@arcgis/core/Basemap.js',
      '@arcgis/core/identity/IdentityManager.js',
      '@arcgis/core/layers/GraphicsLayer.js',
      '@arcgis/core/Graphic.js',
    ]);

  window._esriId = esriId;
  window._FeatureLayer = FeatureLayer;
```

Replace with:
```js
  const [Map, MapView, VectorTileLayer, TileLayer, FeatureLayer, Basemap, esriId, GraphicsLayer, Graphic] =
    await $arcgis.import([
      '@arcgis/core/Map.js',
      '@arcgis/core/views/MapView.js',
      '@arcgis/core/layers/VectorTileLayer.js',
      '@arcgis/core/layers/TileLayer.js',
      '@arcgis/core/layers/FeatureLayer.js',
      '@arcgis/core/Basemap.js',
      '@arcgis/core/identity/IdentityManager.js',
      '@arcgis/core/layers/GraphicsLayer.js',
      '@arcgis/core/Graphic.js',
    ]);

  window._esriId = esriId;
  window._FeatureLayer = FeatureLayer;
  window._VectorTileLayer = VectorTileLayer;
  window._TileLayer = TileLayer;
  window._Basemap = Basemap;
```

- [ ] **Step 2: Update initial basemap creation to use BASEMAPS array URL**

Find (≈1414–1417):
```js
  const basemap = new Basemap({
    baseLayers: [new VectorTileLayer({ url: GEODATA_KANVAS })],
    title: 'Geodata Kanvas',
  });
```

Replace with:
```js
  const kanvasCfg = BASEMAPS.find(b => b.id === 'kanvas');
  const basemap = new Basemap({
    baseLayers: [new VectorTileLayer({ url: kanvasCfg.url })],
    title: kanvasCfg.label,
  });
```

- [ ] **Step 3: Call buildBasemapPicker() inside view.when()**

Find (≈1428–1431):
```js
  view.when(async () => {
    await initAuth();
    loadJobs();
  });
```

Replace with:
```js
  view.when(async () => {
    buildBasemapPicker();
    await initAuth();
    loadJobs();
  });
```

- [ ] **Step 4: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: add TileLayer import, expose ArcGIS classes on window, call buildBasemapPicker"
```

---

## Task 5: Add setBasemap, buildBasemapPicker, toggleBasemapPicker functions

**Files:**
- Modify: `web/profilutforsker.html:983` (after the THEME section comment, before toggleTheme)

Add three functions. `setBasemap` reads ArcGIS classes from `window` (set in Task 4). `buildBasemapPicker` creates the picker DOM once. `toggleBasemapPicker` opens/closes the popup and manages the outside-click listener.

- [ ] **Step 1: Insert the three functions before the THEME section**

Find (≈983–987):
```js
// ── THEME ──────────────────────────────────────────────────────────────
function toggleTheme() {
  darkMode = !darkMode;
  document.documentElement.dataset.theme = darkMode ? 'dark' : '';
}
```

Replace with:
```js
// ── BASEMAP ────────────────────────────────────────────────────────────
function setBasemap(id) {
  const cfg = BASEMAPS.find(b => b.id === id);
  if (!cfg || !window._map) return;
  const layer = cfg.type === 'tile'
    ? new window._TileLayer({ url: cfg.url })
    : new window._VectorTileLayer({ url: cfg.url });
  window._map.basemap = new window._Basemap({ baseLayers: [layer], title: cfg.label });
  activeBasemapId = id;
  if (id !== 'mork') lightBasemapId = id;
  document.querySelectorAll('.basemap-option').forEach(el => {
    el.classList.toggle('active', el.dataset.id === id);
  });
}

function buildBasemapPicker() {
  const picker = document.getElementById('basemap-picker');
  if (!picker) return;
  picker.innerHTML = BASEMAPS.map(b => `
    <div class="basemap-option${b.id === activeBasemapId ? ' active' : ''}" data-id="${b.id}"
         onclick="setBasemap('${b.id}');toggleBasemapPicker()">
      <span class="basemap-swatch" style="background:${b.swatch}"></span>
      <span>${b.label}</span>
      <span class="bm-check">✓</span>
    </div>`).join('');
}

let _pickerDismiss = null;
function toggleBasemapPicker() {
  const picker = document.getElementById('basemap-picker');
  const btn    = document.getElementById('btn-basemap');
  if (!picker) return;
  const opening = picker.classList.contains('hidden');
  picker.classList.toggle('hidden', !opening);
  btn.classList.toggle('active', opening);
  if (_pickerDismiss) { document.removeEventListener('mousedown', _pickerDismiss); _pickerDismiss = null; }
  if (opening) {
    _pickerDismiss = (e) => {
      if (!picker.contains(e.target) && e.target !== btn) {
        picker.classList.add('hidden');
        btn.classList.remove('active');
        document.removeEventListener('mousedown', _pickerDismiss);
        _pickerDismiss = null;
      }
    };
    document.addEventListener('mousedown', _pickerDismiss);
  }
}

// ── THEME ──────────────────────────────────────────────────────────────
function toggleTheme() {
  darkMode = !darkMode;
  document.documentElement.dataset.theme = darkMode ? 'dark' : '';
}
```

- [ ] **Step 2: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: add setBasemap, buildBasemapPicker, toggleBasemapPicker functions"
```

---

## Task 6: Wire toggleTheme to auto-switch basemap

**Files:**
- Modify: `web/profilutforsker.html` — `toggleTheme` function (just updated in Task 5)

- [ ] **Step 1: Extend toggleTheme with basemap auto-switch**

Find (the function just written in Task 5):
```js
function toggleTheme() {
  darkMode = !darkMode;
  document.documentElement.dataset.theme = darkMode ? 'dark' : '';
}
```

Replace with:
```js
function toggleTheme() {
  darkMode = !darkMode;
  document.documentElement.dataset.theme = darkMode ? 'dark' : '';
  setBasemap(darkMode ? 'mork' : lightBasemapId);
}
```

- [ ] **Step 2: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: auto-switch to Kanvas Mørk on dark mode toggle"
```

---

## Task 7: Expose new functions on window

**Files:**
- Modify: `web/profilutforsker.html:2486–2490`

- [ ] **Step 1: Add toggleBasemapPicker and setBasemap to window.assign**

Find (≈2486–2490):
```js
Object.assign(window, {
  toggleTheme, toggleLp, openCs, closeCs, toggleCsMax,
  toggleLayer, toggleSidebar, mapZoom, mapHome,
  nav, drawLp, svgZoomBtn, resetCsZoom, toggleMeasure, clearMeasure, copyMeasure,
});
```

Replace with:
```js
Object.assign(window, {
  toggleTheme, toggleLp, openCs, closeCs, toggleCsMax,
  toggleLayer, toggleSidebar, mapZoom, mapHome,
  nav, drawLp, svgZoomBtn, resetCsZoom, toggleMeasure, clearMeasure, copyMeasure,
  toggleBasemapPicker, setBasemap,
});
```

- [ ] **Step 2: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: expose toggleBasemapPicker and setBasemap on window"
```

---

## Task 8: Manual browser verification

- [ ] **Step 1: Start dev server**

```bash
cd path/to/svv-ifc-profiler
python -m http.server 3000   # or whatever dev server is used
```

- [ ] **Step 2: Open the app and verify picker appears**

Open `http://localhost:3000/web/profilutforsker.html` (or the actual dev URL).
Expected: A new stacked-layers button appears below the sidebar toggle in the map tools panel.

- [ ] **Step 3: Verify picker opens and closes**

Click the basemap button. Expected: A popup appears to the left with four rows (Kanvas, Gråtone, Bilder, Mørk) each with a color swatch and a checkmark on the active row. Click outside — popup closes. Click button again — opens again.

- [ ] **Step 4: Verify Gråtone and Mørk switch**

Click "Gråtone". Expected: Map basemap switches to the gray terrain style, popup closes, button no longer shows `.active` ring. Open picker again — Gråtone row has checkmark.

Click "Mørk". Expected: Dark basemap appears.

- [ ] **Step 5: Verify Bilder (satellite) switches**

Click "Bilder". Expected: Satellite imagery appears on the map (raster tiles from GeocacheBilder MapServer).

- [ ] **Step 6: Verify dark mode auto-switch**

Switch to Kanvas first. Click the light/dark toggle (top-right toolbar). Expected: Theme goes dark AND the basemap switches to Kanvas Mørk automatically. Open the picker — Mørk row is active.

Click the toggle again. Expected: Theme goes light AND basemap returns to Kanvas.

- [ ] **Step 7: Verify light basemap memory**

Switch to Gråtone. Toggle dark mode on → basemap becomes Mørk. Toggle dark mode off → basemap returns to Gråtone (not Kanvas).

- [ ] **Step 8: Final commit if all checks pass**

All features verified — implementation complete.
