# Linked cursor tverrprofil → kart/3D — implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Når brukeren beveger cursoren i tverrprofil-tegningen, vises tilsvarende posisjon som en markør som glir langs snittlinjen i 2D-kartet og som en kule på kotehøyde i 3D-scenen.

**Architecture:** Ren frontend-endring i `web/profilutforsker.html`. En «snittakse» `{x0, y0, px, py}` lagres ved stasjonsvalg; hover-flyten i tverrprofilet (som allerede gir `x_m`/`z_m` via `coordMap.svgToReal`) mater en rAF-throttlet oppdatering av én gjenbrukbar `Graphic` i et dedikert `GraphicsLayer` per visning (2D og 3D). Spec: `docs/superpowers/specs/2026-06-12-linked-cursor-tverrprofil-kart-design.md`.

**Tech Stack:** ArcGIS Maps SDK for JavaScript (allerede lastet i siden), vanilla JS i én HTML-fil. Ingen backend-endringer, ingen automatiske tester (manuell visuell verifisering — etablert mønster i prosjektet).

**Viktig kontekst for utfører:**
- Alt skjer i `web/profilutforsker.html` (~3900 linjer, alt inline). Linjenumre under er ca. — søk på de oppgitte kodeutdragene.
- `stations[idx]` har `.x/.y` (EPSG:25833) og `.z` (kote). `clTangent(idx)` (definert nær «Enhets-tangent langs senterlinja») gir enhets-tangent `{tx, ty}`; normalen er `(ty, -tx)` — samme u-akse som backend (`cross_section._project_to_2d`) og `drawCrossSectionLine()`. (Planen sa opprinnelig `(-ty, tx)`; det var speilvendt og ble rettet i debadf9/66354ba.)
- `MAGENTA = [224, 34, 142]` er definert globalt.
- Eksisterende `hoverLayer` (2D) og `selected3dLayer` (3D) kan IKKE brukes til markøren — begge tømmes med `removeAll()` av annen kode (kart-hover/`selectStation` hhv. `mark3dStation`).
- 3D er lazy-init: `csCursor3dLayer` finnes først etter at brukeren har åpnet 3D én gang. Alle 3D-oppdateringer må derfor være guarded.

---

### Task 1: Tilstand og markørfunksjoner

**Files:**
- Modify: `web/profilutforsker.html` (to steder: globale `let`-deklarasjoner ~linje 1357, og rett etter `clTangent()` ~linje 1611)

- [ ] **Step 1: Legg til globale tilstandsvariabler**

Finn linjen:

```js
let currentCoordMap = null;
```

og legg til rett under:

```js
// Linked cursor: tverrprofil-hover → markør i kart/3D
let csMapAxis = null;        // {x0, y0, px, py} — snittakse i kartet for valgt stasjon
let csCursorLayer = null;    // GraphicsLayer (2D) for cursor-markøren
let csCursor3dLayer = null;  // GraphicsLayer (3D) for cursor-markøren
let csCursorGfx2d = null;    // gjenbrukbar Graphic i 2D
let csCursorGfx3d = null;    // gjenbrukbar Graphic i 3D
let _csCursorRaf = 0;        // rAF-handle (throttling)
let _csCursorPending = null; // {x_m, z_m} som venter på neste frame
```

- [ ] **Step 2: Legg til markørfunksjonene**

Finn slutten av `clTangent(idx)` (funksjonen som slutter med `return { tx: dx / len, ty: dy / len };` og `}`), og legg til rett etter den:

```js
// ── LINKED CURSOR: tverrprofil-hover → markør i kart/3D ────────────────
// Snittaksen for valgt stasjon: stasjonspunkt + enhetsnormal på senterlinja.
function setCsMapAxis(idx) {
  const s = stations[idx];
  if (!s) { csMapAxis = null; return; }
  const { tx, ty } = clTangent(idx);
  csMapAxis = { x0: s.x, y0: s.y, px: ty, py: -tx };  // u-akse, rettet i debadf9
}

// Flytt (eller opprett) cursor-markøren. rAF-throttlet: raske pointermove-
// events gir maks én ArcGIS-geometrioppdatering per frame.
function updateCsMapMarker(x_m, z_m) {
  if (!csMapAxis) return;
  _csCursorPending = { x_m, z_m };
  if (_csCursorRaf) return;
  _csCursorRaf = requestAnimationFrame(() => {
    _csCursorRaf = 0;
    const p = _csCursorPending;
    if (!p || !csMapAxis) return;
    const x = csMapAxis.x0 + csMapAxis.px * p.x_m;
    const y = csMapAxis.y0 + csMapAxis.py * p.x_m;
    const SR = { wkid: 25833 };
    if (csCursorLayer && window._Graphic) {
      if (!csCursorGfx2d) {
        csCursorGfx2d = new window._Graphic({
          geometry: { type: 'point', x, y, spatialReference: SR },
          symbol: {
            type: 'simple-marker', color: MAGENTA, size: 9,
            outline: { color: [255, 255, 255], width: 1.5 },
          },
        });
        csCursorLayer.add(csCursorGfx2d);
      } else {
        csCursorGfx2d.geometry = { type: 'point', x, y, spatialReference: SR };
      }
    }
    if (csCursor3dLayer && window._Graphic) {
      if (!csCursorGfx3d) {
        csCursorGfx3d = new window._Graphic({
          geometry: { type: 'point', x, y, z: p.z_m, spatialReference: SR },
          symbol: { type: 'point-3d', symbolLayers: [{
            type: 'object', resource: { primitive: 'sphere' },
            width: 1, depth: 1, height: 1, material: { color: MAGENTA },
          }] },
        });
        csCursor3dLayer.add(csCursorGfx3d);
      } else {
        csCursorGfx3d.geometry = { type: 'point', x, y, z: p.z_m, spatialReference: SR };
      }
    }
  });
}

// Skjul markøren (pointerleave, lukking av tegning, jobbytte).
function hideCsMapMarker() {
  _csCursorPending = null;
  if (_csCursorRaf) { cancelAnimationFrame(_csCursorRaf); _csCursorRaf = 0; }
  if (csCursorGfx2d && csCursorLayer) { csCursorLayer.remove(csCursorGfx2d); csCursorGfx2d = null; }
  if (csCursorGfx3d && csCursor3dLayer) { csCursor3dLayer.remove(csCursorGfx3d); csCursorGfx3d = null; }
}
```

- [ ] **Step 3: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): tilstand og markørfunksjoner for linked cursor"
```

---

### Task 2: Dedikerte GraphicsLayers (2D + 3D)

**Files:**
- Modify: `web/profilutforsker.html` (kartinit ~linje 2307, reorder ~linje 2597 og ~linje 2824, scene-init ~linje 1508)

- [ ] **Step 1: Opprett 2D-laget i kartinit**

Finn (i `initMap`-området der grafikklagene lages):

```js
  hoverLayer = new GraphicsLayer({ listMode: 'hide' });
```

Konteksten rundt er `hoverLayer`, `selectedLayer` og `geomLabelLayer` som lages og legges til med `map.add(...)`. Etter linjen `map.add(hoverLayer);` legg til:

```js
  csCursorLayer = new GraphicsLayer({ listMode: 'hide' });
  map.add(csCursorLayer);
```

- [ ] **Step 2: Hold laget øverst — reorder-sted 1**

Finn:

```js
  map.reorder(selectedLayer, map.layers.length - 1);
  map.reorder(hoverLayer, map.layers.length - 1);
  if (geomLabelLayer) map.reorder(geomLabelLayer, map.layers.length - 1);
```

og legg til etter `geomLabelLayer`-linjen:

```js
  if (csCursorLayer) map.reorder(csCursorLayer, map.layers.length - 1);
```

- [ ] **Step 3: Hold laget øverst — reorder-sted 2 (BIM-lag-innsetting)**

Finn:

```js
  if (selectedLayer) map.reorder(selectedLayer, map.layers.length - 1);
  if (hoverLayer)   map.reorder(hoverLayer,   map.layers.length - 1);
```

og legg til etter:

```js
  if (csCursorLayer) map.reorder(csCursorLayer, map.layers.length - 1);
```

- [ ] **Step 4: Opprett 3D-laget i `initScene`**

Finn:

```js
  selected3dLayer = new window._GraphicsLayer({
    listMode: 'hide', elevationInfo: { mode: 'absolute-height' },
  });
  map3d.add(selected3dLayer);
```

og legg til rett etter:

```js
  // Eget lag for linked-cursor-markøren (tømmes ikke av mark3dStation).
  csCursor3dLayer = new window._GraphicsLayer({
    listMode: 'hide', elevationInfo: { mode: 'absolute-height' },
  });
  map3d.add(csCursor3dLayer);
```

- [ ] **Step 5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): dedikerte grafikklag for linked cursor (2D+3D)"
```

---

### Task 3: Hooks i hover-flyt, stasjonsvalg og opprydding

**Files:**
- Modify: `web/profilutforsker.html` (`selectStation` ~linje 2846, `renderHoverOverlay` ~linje 1949, `pointerleave`-handler ~linje 3167, `closeCs` ~linje 3230, jobbytte-opprydding ~linje 2483)

- [ ] **Step 1: Sett snittaksen ved stasjonsvalg**

I `selectStation(idx)`, finn:

```js
  currentIdx = idx;
  if (hoverLayer) hoverLayer.removeAll();
  const s = stations[idx];
```

og endre til:

```js
  currentIdx = idx;
  if (hoverLayer) hoverLayer.removeAll();
  const s = stations[idx];
  setCsMapAxis(idx);
```

- [ ] **Step 2: Oppdater markøren fra hover-overlayet**

I `renderHoverOverlay(snap, coordMap)`, finn:

```js
  clearHoverOverlay();
  if (!snap || !coordMap) return;

  const {x_m, z_m} = coordMap.svgToReal(snap.x, snap.y);
```

og endre til:

```js
  clearHoverOverlay();
  if (!snap || !coordMap) { hideCsMapMarker(); return; }

  const {x_m, z_m} = coordMap.svgToReal(snap.x, snap.y);
  updateCsMapMarker(x_m, z_m);
```

**Merk:** `hideCsMapMarker()` skal IKKE inn i `clearHoverOverlay()` — den kalles øverst i `renderHoverOverlay` på hver pointermove, og ville revet og gjenskapt markør-grafikken hver frame.

- [ ] **Step 3: Skjul markøren når cursoren forlater SVG-området**

Finn:

```js
svgArea.addEventListener('pointerleave', () => {
  clearHoverOverlay();
```

og endre til:

```js
svgArea.addEventListener('pointerleave', () => {
  clearHoverOverlay();
  hideCsMapMarker();
```

- [ ] **Step 4: Skjul markøren når tegningen lukkes**

I `closeCs()`, finn:

```js
function closeCs() {
  csOpen = false;
```

og endre til:

```js
function closeCs() {
  csOpen = false;
  hideCsMapMarker();
```

(`csMapAxis` beholdes — hover skal virke igjen ved gjenåpning av samme stasjon.)

- [ ] **Step 5: Rydd ved jobbytte**

I jobbytte-koden, finn:

```js
  stations = [];
  horCurves = [];
  currentIdx = -1;
```

og endre til:

```js
  stations = [];
  horCurves = [];
  currentIdx = -1;
  csMapAxis = null;
  hideCsMapMarker();
```

- [ ] **Step 6: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(profilutforsker): linked cursor tverrprofil → kart/3D"
```

---

### Task 4: Manuell verifisering i kjørende app

**Files:** ingen endringer (verifisering)

- [ ] **Step 1: Start backend**

```bash
uvicorn src.api.server:app --reload --port 8000
```

(kjør i bakgrunnen fra repo-rot)

- [ ] **Step 2: Åpne appen**

Frontend åpnes slik brukeren pleier (statisk `web/profilutforsker.html`; ved behov `python -m http.server 8080 -d web` og åpne `http://localhost:8080/profilutforsker.html`). Bruk agent-browser-skillen. **NB:** AGOL-OAuth-innlogging kan kreve brukerens hjelp — si fra og vent i så fall.

- [ ] **Step 3: Verifiser 2D**

1. Velg en jobb og klikk på en stasjon → tverrprofil åpnes, magenta snittlinje vises i kartet.
2. Beveg cursoren langs terreng/vegkant i tverrprofilet.
   - Forventet: en liten magenta sirkel med hvit ring glir langs snittlinjen i kartet, på samme side av senterlinja som cursoren (negativ `x_m` = venstre).
   - Forventet: hover-tooltipen i tegningen og markøren i kartet er konsistente.
3. Flytt cursoren ut av SVG-området → markøren i kartet forsvinner.
4. Ta skjermbilde som dokumentasjon.

- [ ] **Step 4: Verifiser 3D**

1. Bytt til 3D-visning, hover i tverrprofilet igjen.
   - Forventet: magenta kule (~1 m) følger på kotehøyde langs snittet.
2. Bytt stasjon (piltast/knapp) → hover på ny stasjon gir markør langs NY snittlinje (3D-stolpen på valgt stasjon skal fortsatt fungere som før).
3. Ta skjermbilde.

- [ ] **Step 5: Verifiser opprydding**

1. Lukk tverrprofil-skuffen → markør borte. Åpne igjen, hover → markør tilbake.
2. Aktiver målemodus, klikk to punkter → måling fungerer som før, hover-markøren i kartet oppfører seg som ellers.
3. Bytt jobb → ingen etterlatt markør, ingen feil i konsollen.

- [ ] **Step 6: Rapporter**

Oppsummer funn med skjermbilder. Avvik fra forventet oppførsel → tilbake til relevant task, IKKE hopp videre.
