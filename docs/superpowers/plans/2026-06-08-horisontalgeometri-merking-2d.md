# Horisontalgeometri-merking (R / A) i 2D-kartet — Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vise R700-kurvaturmerking (`R=<verdi>` på sirkelbuer, `A=<verdi>` på klotoider, `R=∞` på rette strekk) oppå senterlinja i 2D-kartet i profilutforskeren, rotert langs vegen, med av/på-knapp.

**Architecture:** Rent frontend i `web/profilutforsker.html`. Et nytt `GraphicsLayer` (`geomLabelLayer`) fylles med ett `TextSymbol`-`Graphic` per geometrisegment. Posisjon og rotasjon interpoleres fra det allerede innlastede `stations`-arrayet (har `stasjon_m`, `x`, `y` i EPSG:25833). Geometridataene leses fra `horCurves` (`horizontal_alignment.json`, allerede hentet). Ingen backend-/AGOL-endring.

**Tech Stack:** ArcGIS JS API v5 (GraphicsLayer, Graphic, TextSymbol), vanilla JS i én monolittisk HTML-fil.

---

## Testtilnærming (les først)

Prosjektet har **ingen JS-testrigg** — `tests/` inneholder kun pytest for Python-backend, og frontend er historisk verifisert live (jf. tidligere 3D-scene-arbeid). Denne planen følger TDD i ånden:

- **Ren logikk** (tekst, vinkel, plassering) er trukket ut i rene funksjoner og verifiseres automatisk med et frittstående Node-snutt (ingen rammeverk, ingen avhengigheter) før de kobles inn i kartet.
- **Kart-integrasjonen** verifiseres manuelt i nettleseren mot en live-jobb med kurvet senterlinje, med eksplisitte forventede observasjoner.

Dette er et bevisst avvik fra automatiserte browser-tester, begrunnet i fravær av rigg og i kodebasens etablerte praksis.

## Fildekomponering

Alt skjer i `web/profilutforsker.html`. Endringene er gruppert slik:

| Område | Hva | Omtrentlig sted |
|--------|-----|-----------------|
| Globale variabler | `geomLabelLayer`, `layerVis.geom` | linje 1299–1300, 1330 |
| Rene hjelpefunksjoner | `geomLabelText`, `geomLabelAngle`, `geomLabelPlacement` | ny blokk nær linje 2111 |
| Bygging av merker | `buildGeomLabels()` | ny funksjon nær linje 2111 |
| Lag-opprettelse | `new GraphicsLayer(...)` + `map.add` | linje 2185–2188 |
| loadJob-integrasjon | rydd + bygg + reorder + kall | linje 2362–2365, 2467–2470, 2507 |
| Av/på i UI | ny lag-rad + `toggleLayer`-gren | linje 833, 3781–3798 |

`horCurves`-skjema (verifisert mot `pipeline.py:448-467`): `{ kind: "line"|"curve"|"spiral", sta_start, sta_end, radius?, A?, dir? }`.

---

### Task 1: Rene hjelpefunksjoner (tekst, vinkel, plassering)

**Files:**
- Modify: `web/profilutforsker.html` (ny blokk nær linje 2111, etter `drawCrossSectionOnMap`-funksjonen som slutter der)

- [ ] **Step 1: Skriv hjelpefunksjonene**

Sett inn følgende blokk rett etter linje 2111 (etter den avsluttende `}` for funksjonen som tegner tverrsnitt på kartet):

```javascript
// ── HORISONTALGEOMETRI-MERKING (R/A) ───────────────────────────────────
// Ren tekst for et horisontalsegment. Returnerer null hvis data mangler.
function geomLabelText(hc) {
  if (hc.kind === 'line') return 'R=∞';
  if (hc.kind === 'curve') return hc.radius ? 'R=' + Math.round(hc.radius) : null;
  if (hc.kind === 'spiral') return hc.A ? 'A=' + Math.round(hc.A) : null;
  return null;
}

// TextSymbol.angle (grader) for en tangentvektor i kartkoordinater (y opp).
// Normaliseres til [-90, 90] så teksten aldri står opp-ned.
function geomLabelAngle(dx, dy) {
  let a = Math.atan2(-dy, dx) * 180 / Math.PI; // klokkeretning fra øst i skjermrom
  if (a > 90) a -= 180;
  if (a < -90) a += 180;
  return a;
}

// Posisjon + rotasjon for en gitt stasjon, interpolert mellom stasjonspunkter.
// Returnerer { x, y, angle } i EPSG:25833, eller null hvis stasjonen er utenfor.
function geomLabelPlacement(stations, sta) {
  if (!stations || stations.length < 2) return null;
  if (sta < stations[0].stasjon_m || sta > stations[stations.length - 1].stasjon_m) return null;
  let i = 0;
  while (i < stations.length - 1 && stations[i + 1].stasjon_m < sta) i++;
  const a = stations[i], b = stations[i + 1] || stations[i];
  const span = (b.stasjon_m - a.stasjon_m) || 1;
  const t = Math.min(1, Math.max(0, (sta - a.stasjon_m) / span));
  return {
    x: a.x + (b.x - a.x) * t,
    y: a.y + (b.y - a.y) * t,
    angle: geomLabelAngle(b.x - a.x, b.y - a.y),
  };
}
```

- [ ] **Step 2: Verifiser den rene logikken med Node**

Lag en midlertidig fil `scratch-geomlabel.mjs` i prosjektroten med en kopi av de tre funksjonene over etterfulgt av assertions:

```javascript
// (lim inn de tre funksjonene geomLabelText, geomLabelAngle, geomLabelPlacement her)
import assert from 'node:assert';

// Tekst
assert.equal(geomLabelText({ kind: 'line' }), 'R=∞');
assert.equal(geomLabelText({ kind: 'curve', radius: 349.7 }), 'R=350');
assert.equal(geomLabelText({ kind: 'spiral', A: 200.4 }), 'A=200');
assert.equal(geomLabelText({ kind: 'curve' }), null);
assert.equal(geomLabelText({ kind: 'spiral' }), null);

// Vinkel: øst → 0, nord (y opp) → -90, og alltid innenfor [-90, 90]
assert.equal(geomLabelAngle(1, 0), 0);
assert.equal(geomLabelAngle(0, 1), -90);
assert.equal(geomLabelAngle(-1, 0), 0);     // vest normaliseres til 0 (ikke 180)
assert.ok(geomLabelAngle(-1, -1) >= -90 && geomLabelAngle(-1, -1) <= 90);

// Plassering: interpolerer midt mellom to stasjoner og gir tangent østover
const st = [
  { stasjon_m: 0, x: 0, y: 0 },
  { stasjon_m: 10, x: 10, y: 0 },
  { stasjon_m: 20, x: 20, y: 0 },
];
const p = geomLabelPlacement(st, 5);
assert.equal(p.x, 5);
assert.equal(p.y, 0);
assert.equal(p.angle, 0);
assert.equal(geomLabelPlacement(st, 25), null);     // utenfor
assert.equal(geomLabelPlacement(st, -5), null);     // utenfor

console.log('OK');
```

- [ ] **Step 3: Kjør verifiseringen**

Run: `node scratch-geomlabel.mjs`
Expected: skriver `OK` og avslutter med kode 0. Hvis en assertion feiler, rett funksjonen i HTML-fila (og i scratch-kopien) til den passerer.

- [ ] **Step 4: Slett scratch-fila**

Run: `Remove-Item scratch-geomlabel.mjs`
Expected: fila er borte (skal ikke committes).

- [ ] **Step 5: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(2d): rene hjelpefunksjoner for kurvaturmerking (R/A)"
```

---

### Task 2: Opprett geomLabelLayer og bygg merkene

**Files:**
- Modify: `web/profilutforsker.html` — globale variabler (1299–1300, 1330), lag-opprettelse (2185–2188), `buildGeomLabels` (nær 2111), loadJob (2362–2365, 2467–2470, 2507)

- [ ] **Step 1: Legg til globale variabler**

Ved linje 1299–1300 står i dag:

```javascript
let hoverLayer = null;
let selectedLayer = null;
```

Legg til en linje under:

```javascript
let geomLabelLayer = null;
```

Ved linje 1330 står i dag:

```javascript
let layerVis = { centerline: true, stations: true, bim: true };
```

Endre til (geom av som standard):

```javascript
let layerVis = { centerline: true, stations: true, bim: true, geom: false };
```

- [ ] **Step 2: Legg til `buildGeomLabels()`**

Sett inn rett etter `geomLabelPlacement` fra Task 1 (samme blokk):

```javascript
const GEOM_MIN_SEG_M = 3; // hopp over svært korte segmenter for å unngå overlapp

// Fyller geomLabelLayer med ett TextSymbol per horisontalsegment.
function buildGeomLabels() {
  if (!geomLabelLayer || !window._Graphic) return;
  geomLabelLayer.removeAll();
  if (!stations || stations.length < 2) return;
  for (const hc of horCurves) {
    if ((hc.sta_end - hc.sta_start) < GEOM_MIN_SEG_M) continue;
    const text = geomLabelText(hc);
    if (!text) continue;
    const place = geomLabelPlacement(stations, (hc.sta_start + hc.sta_end) / 2);
    if (!place) continue;
    geomLabelLayer.add(new window._Graphic({
      geometry: { type: 'point', x: place.x, y: place.y, spatialReference: { wkid: 25833 } },
      symbol: {
        type: 'text',
        text,
        angle: place.angle,
        color: [20, 20, 20],
        haloColor: [255, 255, 255, 230],
        haloSize: 1.6,
        font: { size: 11, family: 'ui-monospace, SFMono-Regular, monospace', weight: 'bold' },
        yoffset: 5,
      },
    }));
  }
}
```

- [ ] **Step 3: Opprett laget ved oppstart**

Ved linje 2185–2188 står i dag:

```javascript
  hoverLayer = new GraphicsLayer({ listMode: 'hide' });
  selectedLayer = new GraphicsLayer({ listMode: 'hide' });
  map.add(hoverLayer);
  map.add(selectedLayer);
```

Endre til:

```javascript
  hoverLayer = new GraphicsLayer({ listMode: 'hide' });
  selectedLayer = new GraphicsLayer({ listMode: 'hide' });
  geomLabelLayer = new GraphicsLayer({ listMode: 'hide', visible: false, minScale: 5000 });
  map.add(hoverLayer);
  map.add(selectedLayer);
  map.add(geomLabelLayer);
```

- [ ] **Step 4: Rydd laget ved jobbytte**

Ved linje 2362–2365 står i dag:

```javascript
  if (clLayer && window._map) window._map.remove(clLayer);
  if (stLayer && window._map) window._map.remove(stLayer);
  for (const l of bimLayers) { if (window._map) window._map.remove(l); }
  clLayer = null; stLayer = null; bimLayers = [];
```

Legg til en linje under:

```javascript
  if (geomLabelLayer) geomLabelLayer.removeAll();
```

- [ ] **Step 5: Hold laget øverst og bygg merkene**

Ved linje 2467–2470 står i dag:

```javascript
  map.addMany([clLayer, stLayer]);
  // Keep graphics layers above feature layers
  map.reorder(selectedLayer, map.layers.length - 1);
  map.reorder(hoverLayer, map.layers.length - 1);
```

Legg til en reorder-linje under:

```javascript
  if (geomLabelLayer) map.reorder(geomLabelLayer, map.layers.length - 1);
```

Ved linje 2507 (rett etter `try/catch`-blokken som setter `horCurves`, dvs. etter `horCurves = [];` i catch og før kommentaren `// Update UI`) legg til:

```javascript
    buildGeomLabels();
```

- [ ] **Step 6: Verifiser at sida lastes uten JS-feil**

Run: åpne profilutforskeren (se Task 4 for hvordan den serveres) og åpne nettleserkonsollen.
Expected: ingen `ReferenceError`/`TypeError` ved innlasting av en jobb. Merkene vises ennå ikke (laget er `visible:false`) — det er forventet; full visuell verifisering skjer i Task 4 etter at av/på-knappen finnes.

- [ ] **Step 7: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(2d): bygg kurvaturmerke-lag (geomLabelLayer) fra horCurves"
```

---

### Task 3: Av/på-knapp i laglista

**Files:**
- Modify: `web/profilutforsker.html` — lag-rad-HTML (linje 833), `toggleLayer` (3781–3798)

- [ ] **Step 1: Legg til lag-raden i UI**

Ved linje 833 slutter `row-stations`-raden med `</div>`. Sett inn følgende rad rett etter den (fortsatt inne i `<div class="sb-group">` for «Prosjekterte»), før `</div>` som lukker gruppa på linje 834:

```html
          <div class="layer-row muted" id="row-geom" onclick="toggleLayer('geom')">
            <button class="layer-toggle" id="tog-geom"></button>
            <div class="layer-swatch" style="width:18px;height:12px;border-radius:2px;background:var(--paper-2);border:0.5px solid var(--line-2);display:flex;align-items:center;justify-content:center;font-size:7px;font-weight:700;color:var(--ink);flex:0 0 18px">R/A</div>
            <span class="layer-name">Kurvaturmerking (R/A)</span>
          </div>
```

- [ ] **Step 2: Håndter `geom` i `toggleLayer`**

Ved linje 3789–3797 står i dag:

```javascript
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

Endre til (ny `geom`-gren før `else`):

```javascript
  if (name === 'bim') {
    bimLayers.forEach(l => { l.visible = layerVis[name]; });
    if (sceneLayer3d) sceneLayer3d.visible = layerVis[name];
  } else if (name === 'geom') {
    if (geomLabelLayer) geomLabelLayer.visible = layerVis[name];
  } else {
    const layer = name === 'centerline' ? clLayer : stLayer;
    if (layer) layer.visible = layerVis[name];
    const layer3d = name === 'centerline' ? cl3d : st3d;
    if (layer3d) layer3d.visible = layerVis[name];
  }
```

- [ ] **Step 3: Verifiser knappens av/på-tilstand i nettleseren**

Run: last en jobb, klikk på «Kurvaturmerking (R/A)»-raden.
Expected: knappen får hake/`on`-stil og rad-stilen går fra `muted` til `active` ved første klikk, og tilbake ved neste klikk (samme oppførsel som de andre lag-radene). `console.log(layerVis.geom)` veksler true/false.

- [ ] **Step 4: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(2d): av/på-knapp for kurvaturmerking i laglista"
```

---

### Task 4: Live verifisering i nettleseren og finjustering

**Files:**
- Modify (kun ved behov): `web/profilutforsker.html` (`minScale`, `GEOM_MIN_SEG_M`, eller fortegn i `geomLabelAngle`)

- [ ] **Step 1: Start appen og åpne en jobb med kurvet senterlinje**

Bruk prosjektets vanlige måte å kjøre profilutforskeren på (FastAPI-serveren under `src/api/` server `web/`-mappa; alternativt åpne den publiserte GitHub Pages-utgaven). Velg en jobb der senterlinja har kurver og overgangskurver.

- [ ] **Step 2: Slå på kurvaturmerkingen og kontrollér visningen**

Klikk «Kurvaturmerking (R/A)» og zoom inn nærmere enn ~1:5000.
Expected:
- `R=<verdi>` står på sirkelbuene, `A=<verdi>` på klotoidene, og `R=∞` på de rette strekkene.
- Verdiene stemmer med rubrikkene i lengdeprofilen (åpne lengdeprofilen og sammenlign R/A for samme stasjonsområde).
- Teksten følger vegens retning og står aldri opp-ned.

- [ ] **Step 3: Juster rotasjon hvis nødvendig**

Hvis teksten står vinkelrett på vegen eller speilvendt: bytt fortegn i `geomLabelAngle` (`Math.atan2(-dy, dx)` ↔ `Math.atan2(dy, dx)`) og verifiser på nytt i nettleseren. Oppdater Node-asserten i Task 1 tilsvarende hvis fortegnet endres.

- [ ] **Step 4: Kontrollér zoom- og av/på-oppførsel**

Expected:
- Zoom ut forbi ~1:5000 → merkene forsvinner (pga. `minScale`). Juster `minScale` hvis terskelen føles feil mot ekte data.
- Slå laget av → alle merker forsvinner. Slå på igjen → de kommer tilbake.
- Bytt til en annen jobb → gamle merker forsvinner, nye bygges.

- [ ] **Step 5: Kontrollér ingen regresjon**

Expected: senterlinje, tverrprofilpunkter med «PR»-labels, BIM-lag og 2D↔3D-synk fungerer som før.

- [ ] **Step 6: Commit eventuelle finjusteringer**

```powershell
git add web/profilutforsker.html
git commit -m "fix(2d): finjuster kurvaturmerking (rotasjon/minScale/terskel)"
```

(Hopp over om ingen justering var nødvendig.)

---

## Self-review (utført under skriving)

- **Spec-dekning:** §1 labeltekst → Task 1 `geomLabelText` + Task 4 verifisering. §2 plassering/rotasjon → Task 1 `geomLabelPlacement`/`geomLabelAngle`. §3 rendering + av/på → Task 2 (lag) + Task 3 (knapp). §4 zoom → Task 2 `minScale` + Task 4 finjustering. §5 grensetilfeller → `GEOM_MIN_SEG_M`, null-retur i tekst/plassering, tom-array-vakter i `buildGeomLabels`.
- **Placeholders:** ingen TBD/TODO; alle kodesteg har komplett kode.
- **Typekonsistens:** `geomLabelLayer`, `buildGeomLabels`, `layerVis.geom`, `geomLabelText/Angle/Placement`, `GEOM_MIN_SEG_M` brukt konsistent på tvers av taskene. `horCurves`-felter (`kind`, `sta_start`, `sta_end`, `radius`, `A`) verifisert mot `pipeline.py`.
- **Avvik fra strikt TDD:** dokumentert i «Testtilnærming» — ingen JS-rigg finnes; ren logikk Node-verifiseres, integrasjon nettleser-verifiseres.
