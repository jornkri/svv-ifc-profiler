# 3D-scene i Profilutforsker — Implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Legge til en 3D-scene (`SceneView`) av den publiserte vegmodellen i `web/profilutforsker.html`, med en 2D/3D-veksler i topbaren og full synk mot valgt stasjon.

**Architecture:** To separate ArcGIS-views (`MapView` + ny `SceneView`), hvert med eget `Map`, stablet i `#map-container` og vekslet med vis/skjul. 3D-scenen lazy-initialiseres første gang den åpnes, bygges programmatisk (ground = GeocacheTerreng ImageServer, basemap = GeocacheBilder, vegmodell = `SceneLayer` fra `bim_scene_url`), og synkroniseres mot eksisterende felles tilstand (`stations` / `currentIdx` / `selectStation`).

**Tech Stack:** ArcGIS Maps SDK for JavaScript 5.0 (ESM via `$arcgis.import`), vanilla JS i én HTML-fil, FastAPI-backend (uendret).

---

## Spesielle merknader for denne planen

- **Ingen frontend-testrigg finnes.** Filen er én HTML-fil som kjøres i nettleser. Derfor brukes **manuell verifisering** (kjør appen, observer) i stedet for automattester. Dette er bevisst valgt i spec-en — ikke legg til en testrigg.
- **Slik kjører du appen for verifisering** (samme i alle tasks):
  1. Backend må kjøre på `http://localhost:8000` (egen prosess, utenfor scope her).
  2. Frontend: `npm --prefix web run dev` → åpne URL-en Vite skriver ut (typisk `http://localhost:5173/profilutforsker.html`).
  3. Logg inn (AGOL OAuth via «Logg inn»-lenken) og velg et publisert prosjekt som har 3D-lag.
- **Alle endringer skjer i `web/profilutforsker.html`.** Ingen andre filer.
- En `FeatureLayer`/`SceneLayer`-instans kan kun tilhøre ÉN `Map`. 3D trenger derfor **egne instanser** av senterlinje/stasjoner (ikke gjenbruk `clLayer`/`stLayer`).

---

## Filstruktur

Kun én fil endres: `web/profilutforsker.html`. Logiske seksjoner som berøres:

- **CSS** (`<style>`, ca. linje 11–658): containere for to views + segmentert veksler-knapp + 3D-meldingsboks.
- **HTML topbar** (ca. linje 693–725): `[2D][3D]`-veksler.
- **HTML map-area** (ca. linje 763–765): del `#map-container` i `#map-2d` + `#map-3d` + `#scene-msg`.
- **JS globals** (ca. linje 1057–1088): nye 3D-variabler.
- **JS map-init** (ca. linje 1555–1686): utvid `$arcgis.import`, bind `MapView` til `#map-2d`, eksponer SDK-klasser på `window`.
- **JS `loadJob` / `loadBimLayers`** (ca. linje 1755–2063): bygg/rydd 3D-jobblag.
- **JS `selectStation`** (ca. linje 2066–2204): fly 3D-kamera + 3D-markør.
- **JS kontroller** (`toggleLayer`, `mapZoom`, `mapHome`, ca. linje 3131–3159): gjør mode-bevisste.
- **JS `Object.assign(window, …)`** (ca. linje 3212): eksponer `setViewMode`.

---

## Task 1: Containere for to views + 2D/3D-veksler (skjelett)

Mål: Del kartflaten i to containere, bind 2D-kartet til `#map-2d`, og legg inn en `[2D][3D]`-knapp som veksler synlighet. 3D-containeren er foreløpig tom.

**Files:**
- Modify: `web/profilutforsker.html` (CSS, topbar-HTML, map-area-HTML, JS map-init, JS window-eksport)

- [ ] **Step 1: Legg til CSS for view-containere og veksler-knapp**

Finn `#map-container { position: absolute; inset: 0; }` (ca. linje 252) og erstatt med:

```css
#map-container { position: absolute; inset: 0; }
#map-2d, #map-3d { position: absolute; inset: 0; }
#map-3d { display: none; }
#map-container.is-3d #map-2d { display: none; }
#map-container.is-3d #map-3d { display: block; }

/* 3D-melding (mangler scene-lag) */
.scene-msg {
  position: absolute; inset: 0; z-index: 4;
  display: none; align-items: center; justify-content: center;
  flex-direction: column; gap: 8px; pointer-events: none;
  text-align: center; padding: 24px;
}
.scene-msg.visible { display: flex; }
.scene-msg .ic { font-size: 40px; opacity: .2; }
.scene-msg .t { font-size: 15px; font-weight: 600; color: var(--ink-3); opacity: .8; }
.scene-msg .s { font-size: 12px; color: var(--ink-3); opacity: .55; max-width: 280px; }

/* Segmentert 2D/3D-veksler i topbaren */
.viewmode-seg {
  display: inline-flex; align-items: center;
  background: rgba(255,255,255,.06); border-radius: 6px; padding: 2px;
}
.viewmode-seg button {
  height: 26px; padding: 0 12px; border: 0; border-radius: 4px;
  background: transparent; color: rgba(255,255,255,.7);
  font: inherit; font-size: 12px; font-weight: 600; cursor: pointer;
  transition: background .15s, color .15s;
}
.viewmode-seg button.active { background: var(--accent); color: #fff; }
```

- [ ] **Step 2: Legg til veksler-knappen i topbaren**

Finn `<button class="top-btn" id="btn-lp" onclick="toggleLp()" ...>` (ca. linje 699). Sett inn rett FØR den, etterfulgt av en skille-divider:

```html
    <div class="viewmode-seg" id="viewmode-seg">
      <button id="vm-2d" class="active" onclick="setViewMode('2d')">2D</button>
      <button id="vm-3d" onclick="setViewMode('3d')">3D</button>
    </div>
    <div class="top-divider"></div>
```

- [ ] **Step 3: Del `#map-container` i to containere + meldingsboks**

Finn `<div id="map-container"></div>` (ca. linje 764) og erstatt med:

```html
    <div id="map-container">
      <div id="map-2d"></div>
      <div id="map-3d"></div>
      <div class="scene-msg" id="scene-msg">
        <div class="ic">🧊</div>
        <div class="t">Ingen 3D-modell for dette prosjektet</div>
        <div class="s">Prosjektet mangler publisert 3D-lag. Kjør opplastning på nytt for å publisere 3D til AGOL.</div>
      </div>
    </div>
```

- [ ] **Step 4: Bind 2D `MapView` til `#map-2d`**

Finn (ca. linje 1584) `container: document.getElementById('map-container'),` inne i `new MapView({…})` og endre til:

```js
    container: document.getElementById('map-2d'),
```

- [ ] **Step 5: Legg til `viewMode`-global og `setViewMode`-funksjon**

Finn globalt-deklarasjons-blokken og legg til ved siden av `let csOpen = false;` (ca. linje 1075):

```js
let viewMode = '2d';        // '2d' | '3d'
let view3d = null;          // SceneView
let map3d = null;           // Map for 3D
let scene3dReady = false;   // lazy-init flagg
```

Legg så til denne funksjonen rett over `// ── BASEMAP ──` (ca. linje 1090):

```js
// ── VIEW MODE (2D/3D) ──────────────────────────────────────────────────
function setViewMode(mode) {
  if (mode === viewMode) return;
  viewMode = mode;
  document.getElementById('map-container').classList.toggle('is-3d', mode === '3d');
  document.getElementById('vm-2d').classList.toggle('active', mode === '2d');
  document.getElementById('vm-3d').classList.toggle('active', mode === '3d');
  // initScene() og synk legges til i senere tasks.
}
```

- [ ] **Step 6: Eksponer `setViewMode` på window**

Finn `Object.assign(window, {` (ca. linje 3212) og legg `setViewMode` i objektet, f.eks. på linjen med `toggleBasemapPicker, setBasemap,`:

```js
  toggleBasemapPicker, setBasemap, setViewMode,
```

- [ ] **Step 7: Manuell verifisering**

Kjør appen (se «Slik kjører du appen» øverst). Forventet:
- Appen laster i 2D nøyaktig som før; velg et prosjekt → senterlinje/stasjoner vises.
- `[2D][3D]`-knappen vises i topbaren; 2D er aktiv (grønn).
- Klikk **3D** → 2D-kartet skjules, flaten blir tom (grå `--map-bg`), knappen 3D blir grønn. Klikk **2D** → 2D-kartet kommer tilbake uendret.
- Ingen feil i konsollen.

- [ ] **Step 8: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): 2D/3D-veksler og view-containere (skjelett)"
```

---

## Task 2: Lazy-initialisering av 3D-scenen (terreng + bakgrunn)

Mål: Første gang man trykker 3D bygges en `SceneView` med GeocacheTerreng som ground og GeocacheBilder som bakgrunn. Ingen jobblag ennå.

**Files:**
- Modify: `web/profilutforsker.html` (JS map-init import + window-eksport, `setViewMode`, ny `initScene`)

- [ ] **Step 1: Utvid `$arcgis.import` med 3D-klasser**

Finn import-blokken (ca. linje 1556–1567). Erstatt hele `const [...] = await $arcgis.import([...]);` med:

```js
  const [Map, MapView, SceneView, VectorTileLayer, TileLayer, FeatureLayer,
         SceneLayer, ElevationLayer, Ground, Basemap, esriId, GraphicsLayer, Graphic] =
    await $arcgis.import([
      '@arcgis/core/Map.js',
      '@arcgis/core/views/MapView.js',
      '@arcgis/core/views/SceneView.js',
      '@arcgis/core/layers/VectorTileLayer.js',
      '@arcgis/core/layers/TileLayer.js',
      '@arcgis/core/layers/FeatureLayer.js',
      '@arcgis/core/layers/SceneLayer.js',
      '@arcgis/core/layers/ElevationLayer.js',
      '@arcgis/core/Ground.js',
      '@arcgis/core/Basemap.js',
      '@arcgis/core/identity/IdentityManager.js',
      '@arcgis/core/layers/GraphicsLayer.js',
      '@arcgis/core/Graphic.js',
    ]);
```

- [ ] **Step 2: Eksponer 3D-klassene på window**

Finn (ca. linje 1569–1573) blokken som setter `window._esriId = esriId;` osv., og legg til etter `window._Basemap = Basemap;`:

```js
  window._SceneView = SceneView;
  window._SceneLayer = SceneLayer;
  window._ElevationLayer = ElevationLayer;
  window._Ground = Ground;
  window._Map = Map;
  window._GraphicsLayer = GraphicsLayer;
```

- [ ] **Step 3: Legg til scene-URL-konstanter**

Finn `const BASEMAPS = [` (ca. linje 1045) og legg til rett FØR den:

```js
const SCENE_BASEMAP_URL = 'https://services.geodataonline.no/arcgis/rest/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer';
const SCENE_TERRAIN_URL  = 'https://services.geodataonline.no/arcgis/rest/services/Geocache_UTM33_EUREF89/GeocacheTerreng/ImageServer';
```

- [ ] **Step 4: Skriv `initScene()`**

Legg til rett under `setViewMode` (i VIEW MODE-seksjonen fra Task 1):

```js
async function initScene() {
  if (scene3dReady) return;
  scene3dReady = true;  // sett tidlig så vi ikke dobbelt-initialiserer ved raske klikk

  const Map = window._Map, SceneView = window._SceneView;
  const TileLayer = window._TileLayer, ElevationLayer = window._ElevationLayer, Ground = window._Ground;

  const ground = new Ground({ layers: [new ElevationLayer({ url: SCENE_TERRAIN_URL })] });
  const basemap = new window._Basemap({
    baseLayers: [new TileLayer({ url: SCENE_BASEMAP_URL })],
    title: 'Bilder',
  });

  map3d = new Map({ basemap, ground });

  view3d = new SceneView({
    container: document.getElementById('map-3d'),
    map: map3d,
    center: [10.75, 59.9],
    zoom: 5,
    qualityProfile: 'high',
    ui: { components: ['attribution'] },
  });

  window._view3d = view3d;
  window._map3d = map3d;

  // 3D-jobblag lastes i Task 3 hvis et prosjekt allerede er valgt.
  if (typeof loadScene3dLayers === 'function' && currentJobId) {
    loadScene3dLayers().catch(e => console.warn('3D-lag:', e));
  }
}
```

- [ ] **Step 5: Kall `initScene()` fra `setViewMode`**

I `setViewMode`, erstatt kommentarlinjen `// initScene() og synk legges til i senere tasks.` med:

```js
  if (mode === '3d') initScene();
```

- [ ] **Step 6: Manuell verifisering**

Kjør appen. Forventet:
- Klikk **3D** (uten prosjekt valgt går også an): scenen bygges, du ser en 3D-globe/terreng med satellittbilder (GeocacheBilder) og høyderelieff (GeocacheTerreng).
- Du kan rotere/tilte (høyre-dra) og zoome i 3D.
- Veksle 2D/3D flere ganger: ingen ny init, ingen feil i konsollen (sjekk at `initScene` ikke kjøres på nytt).

- [ ] **Step 7: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): lazy-init 3D SceneView med terreng og bakgrunnsbilder"
```

---

## Task 3: Last jobbens lag inn i 3D-scenen (vegmodell + senterlinje + stasjoner)

Mål: Når et prosjekt er valgt og 3D-scenen finnes, vis vegmodellen (`SceneLayer` fra `bim_scene_url`, fallback `bim_url`), pluss senterlinje og stasjonspunkter drapert på terrenget. Rydd ved jobbytte.

**Files:**
- Modify: `web/profilutforsker.html` (nye globals, ny `loadScene3dLayers`/`clearScene3dJobLayers`, hekt på `loadJob`)

- [ ] **Step 1: Legg til globals for 3D-jobblag**

Ved siden av `let bimLayers = [];` (ca. linje 1060) legg til:

```js
let cl3d = null;            // senterlinje i 3D
let st3d = null;            // stasjonspunkter i 3D
let sceneLayer3d = null;    // vegmodell (SceneLayer eller FeatureLayer-fallback)
let selected3dLayer = null; // GraphicsLayer for valgt/markør i 3D
```

- [ ] **Step 2: Lagre jobbens URL-er på en global så 3D kan laste dem ved lazy-init**

I `loadJob(jobId, centerlineUrl, sectionsUrl, bimUrl = '')`, finn `currentJobId = jobId;` (ca. linje 1756) og legg til rett under:

```js
  window._jobUrls = { centerlineUrl, sectionsUrl, bimUrl };
```

Vi trenger også 3D-scene-URL-en. Finn i `loadJobs()` der options bygges (ca. linje 1733–1740) og legg til etter `opt.dataset.bimUrl = ...;`:

```js
      opt.dataset.bimSceneUrl = j.bim_scene_url || '';
```

Finn change-handleren `document.getElementById('job-select').addEventListener('change', …)` (ca. linje 1747) og utvid kallet:

```js
document.getElementById('job-select').addEventListener('change', async e => {
  const sel = e.target;
  const jobId = sel.value;
  if (!jobId) return;
  const opt = sel.options[sel.selectedIndex];
  window._jobSceneUrl = opt.dataset.bimSceneUrl || '';
  await loadJob(jobId, opt.dataset.centerlineUrl, opt.dataset.sectionsUrl, opt.dataset.bimUrl || '');
});
```

- [ ] **Step 3: Skriv `clearScene3dJobLayers()` og `loadScene3dLayers()`**

Legg til rett under `loadBimLayers` (etter ca. linje 2063):

```js
// ── 3D-SCENE: JOBBLAG ──────────────────────────────────────────────────
function clearScene3dJobLayers() {
  if (!map3d) return;
  for (const l of [sceneLayer3d, cl3d, st3d, selected3dLayer]) {
    if (l) map3d.remove(l);
  }
  sceneLayer3d = null; cl3d = null; st3d = null; selected3dLayer = null;
}

async function loadScene3dLayers() {
  if (!scene3dReady || !map3d) return;
  clearScene3dJobLayers();

  const urls = window._jobUrls || {};
  const sceneUrl = window._jobSceneUrl || '';
  const FeatureLayer = window._FeatureLayer;
  const SceneLayer   = window._SceneLayer;
  const GraphicsLayer = window._GraphicsLayer;

  const msg = document.getElementById('scene-msg');
  msg.classList.remove('visible');

  // 1) Vegmodell: SceneLayer fra bim_scene_url, ellers FeatureLayer-fallback fra bim_url.
  if (sceneUrl) {
    sceneLayer3d = new SceneLayer({ url: sceneUrl, title: 'Vegmodell (3D)' });
    map3d.add(sceneLayer3d);
  } else if (urls.bimUrl) {
    sceneLayer3d = new FeatureLayer({
      url: urls.bimUrl + '/0',
      title: 'Vegmodell (3D)',
      elevationInfo: { mode: 'absolute-height' },
    });
    map3d.add(sceneLayer3d);
  } else {
    msg.classList.add('visible');  // ingen 3D-modell tilgjengelig
  }

  // 2) Senterlinje (drapert).
  if (urls.centerlineUrl) {
    cl3d = new FeatureLayer({
      url: urls.centerlineUrl + '/0',
      elevationInfo: { mode: 'on-the-ground' },
      renderer: {
        type: 'simple',
        symbol: {
          type: 'line-3d',
          symbolLayers: [{ type: 'line', size: 3, material: { color: [27, 94, 32] } }],
        },
      },
    });
    map3d.add(cl3d);
  }

  // 3) Stasjonspunkter (drapert).
  if (urls.sectionsUrl) {
    st3d = new FeatureLayer({
      url: urls.sectionsUrl + '/0',
      outFields: ['*'],
      elevationInfo: { mode: 'on-the-ground' },
      renderer: {
        type: 'simple',
        symbol: {
          type: 'point-3d',
          symbolLayers: [{
            type: 'object', resource: { primitive: 'sphere' },
            width: 4, height: 4, depth: 4, material: { color: [255, 255, 255, 0.9] },
          }],
        },
      },
    });
    map3d.add(st3d);
  }

  // 4) Eget graphics-lag for valgt-markør (legges øverst).
  selected3dLayer = new GraphicsLayer({ listMode: 'hide', elevationInfo: { mode: 'on-the-ground' } });
  map3d.add(selected3dLayer);
}
```

- [ ] **Step 4: Last 3D-jobblag når et prosjekt lastes (hvis scenen finnes)**

I `loadJob`, finn linjen som starter BIM-lasting (ca. linje 1928):

```js
    // Load BIM layer in background — non-blocking
    if (bimUrl) loadBimLayers(bimUrl).catch(e => console.warn('BIM-lag:', e));
```

Legg til rett under:

```js
    // Last 3D-scenelag hvis scenen allerede er initialisert (ellers gjør initScene det).
    if (scene3dReady) loadScene3dLayers().catch(e => console.warn('3D-lag:', e));
```

- [ ] **Step 5: Rydd 3D-jobblag ved jobbytte**

I `loadJob`, finn opprydningsblokken (ca. linje 1762–1765):

```js
  for (const l of bimLayers) { if (window._map) window._map.remove(l); }
  clLayer = null; stLayer = null; bimLayers = [];
```

Legg til rett under:

```js
  clearScene3dJobLayers();
```

- [ ] **Step 6: Manuell verifisering**

Kjør appen. Forventet:
- Velg et prosjekt med 3D-lag → klikk **3D**: du ser vegmodellen (3D Object Scene Layer) liggende på terrenget, med senterlinje (grønn) og stasjonspunkter (hvite kuler) langs vegen.
- Bytt til et annet prosjekt mens du står i 3D → gammel modell forsvinner, ny lastes.
- Velg et prosjekt UTEN `bim_scene_url` men med `bim_url` → fallback-feature-laget vises. (Test fallback-meldingen i Task 6.)
- Ingen feil i konsollen.

- [ ] **Step 7: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): last vegmodell, senterlinje og stasjoner i 3D-scenen"
```

---

## Task 4: Full synk — fly 3D-kamera + markør ved stasjonsvalg

Mål: Når en stasjon velges (klikk i 2D, piltaster, søk, lengdeprofil), skal 3D-kameraet fly til valgt tverrprofil og markere punktet — også hvis valget skjedde mens man var i 2D (brukes ved neste veksling til 3D).

**Files:**
- Modify: `web/profilutforsker.html` (ny `fly3dToStation`/`mark3dStation`, hekt på `selectStation`, kall ved 2D→3D-veksling)

- [ ] **Step 1: Skriv kamera- og markørhjelpere**

Legg til rett under `loadScene3dLayers` (fra Task 3):

```js
// Beregn enhets-tangent langs senterlinja ved stasjon idx (samme logikk som 2D-tverrsnittslinja).
function clTangent(idx) {
  let dx, dy;
  if (idx > 0 && idx < stations.length - 1) {
    dx = stations[idx + 1].x - stations[idx - 1].x;
    dy = stations[idx + 1].y - stations[idx - 1].y;
  } else if (idx < stations.length - 1) {
    dx = stations[idx + 1].x - stations[idx].x;
    dy = stations[idx + 1].y - stations[idx].y;
  } else {
    dx = stations[idx].x - stations[idx - 1].x;
    dy = stations[idx].y - stations[idx - 1].y;
  }
  const len = Math.hypot(dx, dy) || 1;
  return { tx: dx / len, ty: dy / len };
}

function mark3dStation(s) {
  if (!selected3dLayer || !window._Graphic) return;
  selected3dLayer.removeAll();
  selected3dLayer.add(new window._Graphic({
    geometry: { type: 'point', x: s.x, y: s.y, spatialReference: { wkid: 25833 } },
    symbol: {
      type: 'point-3d',
      symbolLayers: [{
        type: 'object', resource: { primitive: 'sphere' },
        width: 8, height: 8, depth: 8, material: { color: [224, 34, 142] },
      }],
    },
  }));
}

// Fly kameraet til en stasjon: stå ~120 m bak/over langs senterlinja, tilt ned mot profilen.
function fly3dToStation(idx) {
  if (!view3d || !stations[idx]) return;
  const s = stations[idx];
  const { tx, ty } = clTangent(idx);
  const BACK = 120, UP = 70;  // meter
  view3d.goTo({
    position: { x: s.x - tx * BACK, y: s.y - ty * BACK, z: (s.z || 0) + UP,
                spatialReference: { wkid: 25833 } },
    heading: (Math.atan2(tx, ty) * 180 / Math.PI + 360) % 360,
    tilt: 65,
  }, { duration: 700, easing: 'ease-in-out' }).catch(() => {});
}
```

- [ ] **Step 2: Hekt synk på `selectStation`**

I `selectStation(idx)`, finn slutten av funksjonen — `goTo`-blokken for 2D som avsluttes med `.catch(() => {});` og `}` (ca. linje 2202–2204). Legg til rett FØR den avsluttende `}` på `selectStation`:

```js
  // 3D-synk: marker punktet alltid; fly kameraet kun når 3D er aktivt.
  if (scene3dReady) {
    mark3dStation(s);
    if (viewMode === '3d') fly3dToStation(idx);
  }
```

- [ ] **Step 3: Fly til valgt stasjon ved 2D→3D-veksling**

I `setViewMode`, etter `if (mode === '3d') initScene();`, legg til:

```js
  if (mode === '3d' && scene3dReady && currentIdx >= 0) {
    fly3dToStation(currentIdx);
    mark3dStation(stations[currentIdx]);
  }
```

- [ ] **Step 4: Manuell verifisering**

Kjør appen. Forventet:
- Velg prosjekt, gå til 3D, klikk et stasjonspunkt-område via piltaster i 2D først: Velg en stasjon i 2D (klikk), bytt til 3D → kameraet står bak/over valgt profil, og en magenta kule markerer stasjonen.
- I 3D: trykk piltast ←/→ → kameraet flyr til nabostasjon, markøren flytter seg.
- Stasjonssøk (skriv tall + Enter) i 3D → kameraet flyr dit.
- Ingen feil i konsollen.

- [ ] **Step 5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): synk 3D-kamera og markør mot valgt stasjon"
```

---

## Task 5: Klikk i 3D åpner tverrprofil + behold utsnitt ved veksling

Mål: Klikk på et stasjonspunkt i 3D skal åpne tverrprofilen (samme som i 2D). Veksling 2D↔3D skal beholde omtrentlig kartutsnitt når ingen stasjon er valgt.

**Files:**
- Modify: `web/profilutforsker.html` (`view3d.on('click')` i `initScene`, viewpoint-synk i `setViewMode`)

- [ ] **Step 1: Legg til klikk-håndtering i 3D**

I `initScene`, rett før den avsluttende `}` (etter blokken som ev. kaller `loadScene3dLayers`), legg til:

```js
  view3d.on('click', async (event) => {
    if (!st3d) return;
    const resp = await view3d.hitTest(event, { include: [st3d] });
    if (resp.results.length > 0) {
      const g = resp.results[0].graphic;
      const oid = g.attributes && g.attributes.OBJECTID;
      const idx = stations.findIndex(s => s.oid === oid);
      if (idx >= 0) selectStation(idx);
    }
  });
```

- [ ] **Step 2: Behold utsnitt ved veksling (kun når ingen stasjon er valgt)**

I `setViewMode`, etter `if (mode === '3d') initScene();` men FØR fly-til-stasjon-blokken fra Task 4, legg til:

```js
  // Synk omtrentlig utsnitt mellom 2D og 3D når ingen stasjon styrer kameraet.
  if (mode === '3d' && scene3dReady && currentIdx < 0 && view && view3d && view.center) {
    view3d.goTo({ center: [view.center.longitude, view.center.latitude], zoom: view.zoom },
                { duration: 0 }).catch(() => {});
  } else if (mode === '2d' && view && view3d && view3d.center) {
    view.goTo({ center: [view3d.center.longitude, view3d.center.latitude] },
              { duration: 0 }).catch(() => {});
  }
```

- [ ] **Step 3: Manuell verifisering**

Kjør appen. Forventet:
- I 3D: klikk på et stasjonspunkt (hvit kule) → tverrprofil-drawer åpner med riktig profil, markøren blir magenta, kameraet flyr dit.
- Uten valgt stasjon: panorer 2D-kartet til et område, bytt til 3D → 3D viser omtrent samme område (ikke hele Norge).
- Ingen feil i konsollen.

- [ ] **Step 4: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): klikk i 3D åpner tverrprofil + utsnitt-synk ved veksling"
```

---

## Task 6: Mode-bevisste kontroller, lag-synlighet og fallback-melding

Mål: Knappene «zoom», «hjem» og lag-toggles skal virke i 3D. Fallback-meldingen skal kun vises i 3D-modus. Rydd opp småting.

**Files:**
- Modify: `web/profilutforsker.html` (`mapZoom`, `mapHome`, `toggleLayer`)

- [ ] **Step 1: Gjør `mapZoom` og `mapHome` mode-bevisste**

Finn `mapZoom` og `mapHome` (ca. linje 3152–3159) og erstatt begge med:

```js
function mapZoom(delta) {
  const v = (viewMode === '3d' && view3d) ? view3d : view;
  if (v) v.zoom += delta;
}
function mapHome() {
  if (viewMode === '3d' && view3d && st3d && st3d.fullExtent) {
    view3d.goTo({ target: st3d.fullExtent.expand(1.5) }, { duration: 500 }).catch(() => {});
  } else if (stLayer && stLayer.fullExtent) {
    view.goTo({ target: stLayer.fullExtent.expand(1.5) }, { duration: 500 });
  }
}
```

- [ ] **Step 2: La lag-toggles styre 3D-lagene også**

Finn `toggleLayer` (ca. linje 3131) og erstatt `if (name === 'bim') { … } else { … }`-blokken (ca. linje 3139–3144) med:

```js
  if (name === 'bim') {
    bimLayers.forEach(l => { l.visible = layerVis[name]; });
    if (sceneLayer3d) sceneLayer3d.visible = layerVis[name];
  } else {
    const layer = name === 'centerline' ? clLayer : stLayer;
    if (layer) layer.visible = layerVis[name];
    const layer3d = name === 'centerline' ? cl3d : st3d;
    if (layer3d) layer3d.visible = layerVis[name];
  }
```

- [ ] **Step 3: Vis fallback-melding kun i 3D-modus**

I `setViewMode`, helt til slutt i funksjonen (før avsluttende `}`), legg til:

```js
  // Fallback-melding (mangler 3D-modell) skal kun vises når 3D er fremme.
  const msg = document.getElementById('scene-msg');
  if (mode === '2d') msg.classList.remove('visible');
  else if (scene3dReady && !sceneLayer3d && currentJobId) msg.classList.add('visible');
```

- [ ] **Step 4: Manuell verifisering**

Kjør appen. Forventet:
- I 3D: zoom-knappene (+/–) zoomer 3D-kameraet; «hjem»-knappen rammer hele vegmodellen.
- Slå av/på «Vegmodell», «Senterlinje», «Tverrprofilpunkter» i sidepanelet → tilsvarende 3D-lag skjules/vises.
- Velg et prosjekt uten 3D-modell → i 3D vises «Ingen 3D-modell for dette prosjektet»; i 2D vises den ikke.
- 2D fungerer fortsatt uendret.
- Ingen feil i konsollen.

- [ ] **Step 5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): mode-bevisste kontroller, 3D lag-synlighet og fallback-melding"
```

---

## Sluttverifisering (etter alle tasks)

Kjør hele flyten én gang:
1. Velg prosjekt med 3D → 2D viser kart + lag som før.
2. Klikk 3D → vegmodell på terreng, bilder i bakgrunn, senterlinje + punkter.
3. Naviger med piltaster, søk, lengdeprofil → kamera følger, markør flytter seg.
4. Klikk punkt i 3D → tverrprofil åpner.
5. Slå lag av/på, zoom, hjem → virker i begge moduser.
6. Bytt prosjekt → gamle 3D-lag forsvinner, nye lastes.
7. Prosjekt uten 3D → fallback-melding i 3D, 2D upåvirket.

Bruk gjerne `superpowers:verify`-skillet for en strukturert manuell gjennomgang i nettleser.
