# Måleverktøy i tverrprofil-viewer — implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Legg til hover-koordinatavlesning og punkt-til-punkt måling (med snap til SVG-geometri) i tverrprofil-draweren i `profilutforsker.html`.

**Architecture:** SVG-ene injiseres inline i DOM-en (i stedet for å lastes som `<img>`), slik at `getPointAtLength()` kan brukes for snap. Matplotlib-tagger tagges med `set_gid('cs:CLASS')` i renderer, noe som skaper `<g id="cs:CLASS">` i SVG-utdataet. Pan/zoom-logikken bevares uendret.

**Tech Stack:** Vanilla JS (ES2022 modules), matplotlib SVG output, Python/matplotlib `set_gid()`, pytest for Python-tester

---

## Filer som endres

| Fil | Endring |
|-----|---------|
| `src/ifc_processor/renderer.py` | Legg til `set_gid('cs:CLASS')` på alle data-`Line2D`-objekter |
| `tests/test_renderer.py` | Test at SVG inneholder `id="cs:terreng"` o.l. |
| `web/profilutforsker.html` | Alle JS- og HTML-endringer (5 oppgaver) |

---

## Task 1: renderer.py — Tag data-paths med gid

**Files:**
- Modify: `src/ifc_processor/renderer.py`
- Test: `tests/test_renderer.py`

Matplotlib's `Line2D.set_gid('cs:CLASS')` skaper `<g id="cs:CLASS"><path .../></g>` i SVG-utdataet. JS-siden konverterer dette til `data-cs="CLASS"` på path-elementene.

- [ ] **Steg 1: Skriv feiltesten**

Legg til i `tests/test_renderer.py`:

```python
def test_svg_contains_data_cs_gids():
    """SVG-en skal inneholde gid-tagger for kjørefelt og terreng."""
    cs = CrossSection(
        station=50.0,
        elevation=100.0,
        segments={
            "planum": [((-4.5, 0.0), (4.5, 0.0))],
            "terreng": [((-10.0, -2.0), (10.0, -2.0))],
            "skjaering": [((4.5, 0.0), (8.0, -3.0))],
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text()
        assert 'id="cs:kjørefelt"' in content
        assert 'id="cs:terreng"' in content
        assert 'id="cs:skjaering"' in content
```

- [ ] **Steg 2: Kjør testen og bekreft at den feiler**

```bash
python -m pytest tests/test_renderer.py::test_svg_contains_data_cs_gids -v
```

Forventet: FAIL — `AssertionError`

- [ ] **Steg 3: Implementer gid-tagging i renderer.py**

I `render_cross_section_svg()` — finn disse fire stedene og gjør endringene:

**3a. Pavement-envelope** (rundt linje 518):
```python
    if pavement_segs:
        envelope = _upper_envelope_chain(pavement_segs)
        if len(envelope) >= 2:
            lines = ax.plot(
                [p[0] for p in envelope],
                [p[1] for p in envelope],
                color="black", linewidth=2.0, linestyle="-", zorder=5,
            )
            lines[0].set_gid('cs:kjørefelt')
```

**3b. Andre segmenter** (rundt linje 533) — erstatt `ax.plot(us, vs, **style)` med:
```python
            lines = ax.plot(us, vs, **style)
            lines[0].set_gid(f'cs:{road_class}')
```

**3c. `_draw_terrain_chain()`** — endre signaturen og legg til gid-sett:
```python
def _draw_terrain_chain(ax, chain: list[tuple[float, float]], gid: str | None = None) -> None:
    ...
    lines = ax.plot(us, vs, color="black", linewidth=0.8, linestyle="-", zorder=2)
    if gid:
        lines[0].set_gid(gid)
```

Kall-stedet (rundt linje 538):
```python
            if road_class == "terreng":
                _draw_terrain_chain(ax, chain, gid='cs:terreng')
```

**3d. Named layer chains** — finn `_draw_named_layer_chains()` (rundt linje 306) og hent return-verdien fra `ax.plot()`:

Finn alle `ax.plot(...)` kall i `_draw_named_layer_chains` og legg til `set_gid('cs:named')` på `lines[0]`. Det er typisk ett kall per kjede. Finn eksakt kode:

```bash
grep -n "ax.plot" src/ifc_processor/renderer.py
```

For hvert plot-kall inne i `_draw_named_layer_chains`:
```python
lines = ax.plot(xs, ys, ...)
lines[0].set_gid('cs:named')
```

- [ ] **Steg 4: Kjør testen og bekreft at den passerer**

```bash
python -m pytest tests/test_renderer.py::test_svg_contains_data_cs_gids -v
```

Forventet: PASS

- [ ] **Steg 5: Kjør alle renderer-tester**

```bash
python -m pytest tests/test_renderer.py -v
```

Forventet: alle bestående tester fortsatt PASS

- [ ] **Steg 6: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "feat: tag SVG data-paths with set_gid for CS measurement snap"
```

---

## Task 2: profilutforsker.html — Inline SVG host + koordinatmapping

**Files:**
- Modify: `web/profilutforsker.html`

Erstatt `<img id="cs-img">` med `<div id="cs-svg-host">`. Oppdater CSS, `applyTransform()`, `resetCsZoom()`, `loadSvg()`, og pan/zoom-hendelseshåndterere. Bygg koordinatmapping fra matplotlib-tikkene i DOM-en.

- [ ] **Steg 1: Erstatt `<img>` med `<div>` i HTML**

Finn (rundt linje 826):
```html
        <img id="cs-img" alt="Tverrprofil">
```
Erstatt med:
```html
        <div id="cs-svg-host"></div>
```

- [ ] **Steg 2: Oppdater CSS for SVG-host**

Finn (rundt linje 389):
```css
#cs-img {
  position: absolute; top: 0; left: 0;
  max-width: none; display: none;
  transform-origin: 0 0; user-select: none; pointer-events: none;
  background: var(--card);
}
```
Erstatt med:
```css
#cs-svg-host {
  position: absolute; top: 0; left: 0;
  width: 100%; height: 100%;
}
#cs-svg-host > svg {
  position: absolute; top: 0; left: 0;
  transform-origin: 0 0; user-select: none;
  display: block; background: var(--card);
  overflow: visible;
}
html[data-theme="dark"] #cs-svg-host > svg {
  filter: invert(0.88) hue-rotate(180deg);
}
```

- [ ] **Steg 3: Oppdater `applyTransform()`**

Finn (rundt linje 1716):
```javascript
function applyTransform() {
  document.getElementById('cs-img').style.transform =
    `translate(${svgPanX}px,${svgPanY}px) scale(${svgScale})`;
}
```
Erstatt med:
```javascript
function applyTransform() {
  const svgEl = document.querySelector('#cs-svg-host > svg');
  if (svgEl) svgEl.style.transform = `translate(${svgPanX}px,${svgPanY}px) scale(${svgScale})`;
}
```

- [ ] **Steg 4: Oppdater `resetCsZoom()`**

Finn (rundt linje 1721):
```javascript
function resetCsZoom() {
  const area = document.querySelector('.dr-svg-area');
  const img = document.getElementById('cs-img');
  const cw = area.clientWidth, ch = area.clientHeight;
  const iw = img.naturalWidth || 1058, ih = img.naturalHeight || 751;
  svgScale = Math.min(cw / iw, ch / ih) * 0.95;
  svgPanX = (cw - iw * svgScale) / 2;
  svgPanY = (ch - ih * svgScale) / 2;
  applyTransform();
}
```
Erstatt med:
```javascript
function resetCsZoom() {
  const area = document.querySelector('.dr-svg-area');
  const svgEl = document.querySelector('#cs-svg-host > svg');
  const cw = area.clientWidth, ch = area.clientHeight;
  const vb = svgEl ? svgEl.viewBox.baseVal : null;
  const iw = (vb && vb.width) || 1058;
  const ih = (vb && vb.height) || 751;
  svgScale = Math.min(cw / iw, ch / ih) * 0.95;
  svgPanX = (cw - iw * svgScale) / 2;
  svgPanY = (ch - ih * svgScale) / 2;
  applyTransform();
}
```

- [ ] **Steg 5: Oppdater pan/zoom-hendelseshåndterere**

Finn (rundt linje 1745):
```javascript
svgArea.addEventListener('wheel', (e) => {
  if (document.getElementById('cs-img').style.display === 'none') return;
```
Erstatt `document.getElementById('cs-img').style.display === 'none'` med `!document.querySelector('#cs-svg-host > svg')`.

Finn (rundt linje 1758):
```javascript
svgArea.addEventListener('pointerdown', (e) => {
  if (document.getElementById('cs-img').style.display === 'none' || e.button !== 0) return;
```
Samme erstatning der.

- [ ] **Steg 6: Legg til hjelpefunksjoner for koordinatmapping rett etter `parseSvgXTicks()`**

Finn slutten av `parseSvgXTicks()` (rundt linje 1013) og legg til disse funksjonene etterpå:

```javascript
function _findCommentIn(el) {
  for (const n of el.childNodes) {
    if (n.nodeType === 8) return n;
    const found = _findCommentIn(n);
    if (found) return found;
  }
  return null;
}

function buildCoordMap(svgEl, stationElevation) {
  const xTickEls = [...svgEl.querySelectorAll('[id^="xtick_"]')];
  const yTickEls = [...svgEl.querySelectorAll('[id^="ytick_"]')];
  if (xTickEls.length < 2 || yTickEls.length < 2) return null;

  const parseTick = (els, attr) => els.map(g => {
    const tspan = g.querySelector('tspan');
    const comment = _findCommentIn(g);
    if (!tspan || !comment) return null;
    const svgPos = parseFloat(tspan.getAttribute(attr));
    const realVal = parseFloat(comment.textContent.trim().replace(/−/g, '-'));
    return (isNaN(svgPos) || isNaN(realVal)) ? null : {svgPos, realVal};
  }).filter(Boolean);

  const xTicks = parseTick(xTickEls, 'x').sort((a, b) => a.svgPos - b.svgPos);
  // y-ticks: realVal is relative v; convert to absolute z using stationElevation
  const yTicksRaw = parseTick(yTickEls, 'y').sort((a, b) => a.svgPos - b.svgPos);
  const yTicks = yTicksRaw.map(t => ({svgPos: t.svgPos, realVal: t.realVal + stationElevation}));

  if (xTicks.length < 2 || yTicks.length < 2) return null;

  const x0 = xTicks[0], x1 = xTicks[xTicks.length - 1];
  const y0 = yTicks[0], y1 = yTicks[yTicks.length - 1];

  return {
    svgToReal(svgX, svgY) {
      const x_m = x0.realVal + (svgX - x0.svgPos) / (x1.svgPos - x0.svgPos) * (x1.realVal - x0.realVal);
      const z_m = y0.realVal + (svgY - y0.svgPos) / (y1.svgPos - y0.svgPos) * (y1.realVal - y0.realVal);
      return {x_m, z_m};
    },
    realToSvg(x_m, z_m) {
      const svgX = x0.svgPos + (x_m - x0.realVal) / (x1.realVal - x0.realVal) * (x1.svgPos - x0.svgPos);
      const svgY = y0.svgPos + (z_m - y0.realVal) / (y1.realVal - y0.realVal) * (y1.svgPos - y0.svgPos);
      return {svgX, svgY};
    },
  };
}

function tagDataCsElements(svgEl) {
  svgEl.querySelectorAll('[id^="cs:"]').forEach(g => {
    const cls = g.id.slice(3);
    g.querySelectorAll('path').forEach(p => { p.dataset.cs = cls; });
  });
}
```

- [ ] **Steg 7: Legg til state-variabel for koordinatmap etter de andre state-variablene**

Finn (rundt linje 936):
```javascript
let svgDragging = false, svgDragStartX = 0, svgDragStartY = 0;
```
Legg til på neste linje:
```javascript
let currentCoordMap = null;
```

- [ ] **Steg 8: Erstatt `loadSvg()` med inline SVG-versjon**

Finn `async function loadSvg(stasjon_m) {` (rundt linje 1653) og erstatt hele funksjonen:

```javascript
async function loadSvg(stasjon_m) {
  const host = document.getElementById('cs-svg-host');
  const loading = document.getElementById('cs-loading');
  const ph = document.getElementById('cs-placeholder');
  const zoomCtrl = document.getElementById('svg-zoom-ctrl');

  ph.style.display = 'none';
  host.innerHTML = '';
  currentCoordMap = null;
  zoomCtrl.classList.remove('visible');
  loading.style.display = 'flex';

  const formatted = stasjon_m.toFixed(1).padStart(7, '0');
  const url = API + '/api/jobs/' + currentJobId + '/svg/tverrprofil_' + formatted + '.svg';

  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('not found');
    const svgText = await resp.text();

    const parser = new DOMParser();
    const svgDoc = parser.parseFromString(svgText, 'image/svg+xml');
    const svgEl = svgDoc.documentElement;
    svgEl.removeAttribute('width');
    svgEl.removeAttribute('height');
    svgEl.style.transformOrigin = '0 0';

    tagDataCsElements(svgEl);

    const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    overlay.id = 'cs-overlay';
    svgEl.appendChild(overlay);

    host.appendChild(svgEl);

    loading.style.display = 'none';
    zoomCtrl.classList.add('visible');

    // Build coord map after SVG is in DOM (comment nodes accessible)
    const stIdx = stations.findIndex(s => Math.abs(s.stasjon_m - stasjon_m) < 0.01);
    const elev = stIdx >= 0 ? stations[stIdx].z : 0;
    currentCoordMap = buildCoordMap(svgEl, elev);

    resetCsZoom();
    return parseSvgXTicks(svgText);
  } catch (_) {
    loading.style.display = 'none';
    ph.textContent = 'SVG ikke funnet for stasjon ' + stasjon_m.toFixed(1);
    ph.style.display = 'flex';
    return null;
  }
}
```

- [ ] **Steg 9: Manuell test — åpne viewer og verifiser at SVG vises korrekt**

Start backend:
```powershell
python -m uvicorn src.api.server:app --reload --port 8000
```

Åpne `http://localhost:8000/profilutforsker.html`, velg et prosjekt, klikk på en stasjon.

Forventet: Tverrprofil vises, pan/zoom fungerer som før. Åpne DevTools og verifiser at `document.querySelector('#cs-svg-host > svg')` finnes, og at det finnes elementer med `data-cs="terreng"` o.l.

- [ ] **Steg 10: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: inject tverrprofil SVG inline for coordinate access"
```

---

## Task 3: profilutforsker.html — Snap-funksjon + hover-avlesning

**Files:**
- Modify: `web/profilutforsker.html`

- [ ] **Steg 1: Legg til snap-hjelpefunksjoner etter `buildCoordMap()`**

```javascript
function nearestPointOnPath(pathEl, x, y) {
  const total = pathEl.getTotalLength();
  if (total < 1) return pathEl.getPointAtLength(0);
  let lo = 0, hi = total;
  for (let i = 0; i < 24; i++) {
    const m1 = lo + (hi - lo) / 3;
    const m2 = hi - (hi - lo) / 3;
    const d1 = Math.hypot(...[pathEl.getPointAtLength(m1)].map(p => [p.x - x, p.y - y]).flat());
    const d2 = Math.hypot(...[pathEl.getPointAtLength(m2)].map(p => [p.x - x, p.y - y]).flat());
    if (d1 < d2) hi = m2; else lo = m1;
  }
  return pathEl.getPointAtLength((lo + hi) / 2);
}

function snapToPath(svgEl, svgX, svgY, thresholdPx) {
  let bestDist = Infinity, bestPt = null, bestCls = null;
  svgEl.querySelectorAll('path[data-cs]').forEach(el => {
    try {
      const pt = nearestPointOnPath(el, svgX, svgY);
      const d = Math.hypot(pt.x - svgX, pt.y - svgY);
      if (d < bestDist) { bestDist = d; bestPt = pt; bestCls = el.dataset.cs; }
    } catch (_) {}
  });
  if (bestDist > thresholdPx || !bestPt) return null;
  return {x: bestPt.x, y: bestPt.y, cls: bestCls};
}
```

- [ ] **Steg 2: Legg til `renderHoverOverlay()` og `clearHoverOverlay()`**

```javascript
const CS_NS = 'http://www.w3.org/2000/svg';

function svgEl() { return document.querySelector('#cs-svg-host > svg'); }
function overlayEl() { return document.getElementById('cs-overlay'); }

function clearHoverOverlay() {
  if (!overlayEl()) return;
  overlayEl().querySelectorAll('.hover-el').forEach(e => e.remove());
}

function renderHoverOverlay(snap, coordMap) {
  const svg = svgEl();
  const ov = overlayEl();
  if (!svg || !ov) return;
  clearHoverOverlay();
  if (!snap || !coordMap) return;

  const {x_m, z_m} = coordMap.svgToReal(snap.x, snap.y);
  const vb = svg.viewBox.baseVal;

  const mkEl = (tag, attrs, cls) => {
    const el = document.createElementNS(CS_NS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    el.classList.add('hover-el');
    if (cls) el.classList.add(cls);
    ov.appendChild(el);
    return el;
  };

  // Crosshair lines
  mkEl('line', {x1: snap.x, y1: vb.y, x2: snap.x, y2: vb.y + vb.height,
    stroke: '#e0228e', 'stroke-width': 0.5, 'stroke-dasharray': '4 3', opacity: 0.7});
  mkEl('line', {x1: vb.x, y1: snap.y, x2: vb.x + vb.width, y2: snap.y,
    stroke: '#e0228e', 'stroke-width': 0.5, 'stroke-dasharray': '4 3', opacity: 0.7});

  // Snap dot
  mkEl('circle', {cx: snap.x, cy: snap.y, r: 3.5,
    fill: '#e0228e', stroke: 'white', 'stroke-width': 1});

  // Compute % fall to CL (z-difference / |x| from CL → %)
  const {z_m: z_cl} = coordMap.svgToReal(coordMap.realToSvg(0, 0).svgX, snap.y);
  const fall_pct = x_m !== 0 ? ((z_m - z_cl) / Math.abs(x_m) * 100) : 0;

  // Tooltip box — flip left if near right edge
  const tipW = 130, tipH = 54, pad = 6;
  const tipX = (snap.x + tipW / (vb.width / 100) < vb.x + vb.width * 0.8)
    ? snap.x + pad : snap.x - tipW - pad;
  const tipY = snap.y - tipH - pad;

  mkEl('rect', {x: tipX, y: tipY, width: tipW, height: tipH, rx: 3,
    fill: '#e0228e', opacity: 0.92});

  const lines = [
    `x = ${x_m >= 0 ? '+' : ''}${x_m.toFixed(2)} m fra CL`,
    `z = ${z_m.toFixed(2)} m.o.h.`,
    `fall = ${fall_pct.toFixed(1)} %`,
    snap.cls ? snap.cls.replace('cs:', '') : '',
  ].filter(Boolean);

  lines.forEach((txt, i) => {
    const t = mkEl('text', {
      x: tipX + 6, y: tipY + 13 + i * 13,
      'font-size': 10, fill: 'white',
      'font-family': 'Inter Tight, system-ui, sans-serif',
      'font-weight': i === 0 ? '600' : '400',
    });
    t.textContent = txt;
  });
}
```

- [ ] **Steg 3: Legg til `pointermove`-handler på `svgArea` for hover**

Finn `svgArea.addEventListener('pointerup', ...)` (rundt linje 1775) og legg til etter den:

```javascript
svgArea.addEventListener('pointermove', (e) => {
  if (svgDragging || measureMode !== 'idle') return;
  const svg = svgEl();
  if (!svg || !currentCoordMap) return;
  const rect = svgArea.getBoundingClientRect();
  const screenX = e.clientX - rect.left;
  const screenY = e.clientY - rect.top;
  const svgX = (screenX - svgPanX) / svgScale;
  const svgY = (screenY - svgPanY) / svgScale;
  const snap = snapToPath(svg, svgX, svgY, 20 / svgScale);
  renderHoverOverlay(snap || {x: svgX, y: svgY, cls: null}, currentCoordMap);
});

svgArea.addEventListener('pointerleave', () => {
  clearHoverOverlay();
  if (measureMode === 'idle') svgDragging = false;
  svgArea.classList.remove('panning');
});
```

Merk: `svgArea` har allerede en `pointerleave`-handler fra pan/zoom. Fjern den gamle og erstatt med den over (den gamle håndterte bare panning-cursor).

- [ ] **Steg 4: Manuell test — hover-avlesning**

Åpne viewer, last en stasjon. Beveg musa over tegningen.

Forventet:
- Rosa crosshair og tooltip vises
- Tooltip viser `x = ±N.NN m fra CL`, `z = NNN.NN m.o.h.`, `fall = N.N %`
- Tooltip forsvinner når musa forlater SVG-area
- Pan/zoom fungerer fortsatt

- [ ] **Steg 5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: hover coordinate readout with snap to SVG geometry"
```

---

## Task 4: profilutforsker.html — Måle-tilstandsmaskin, overlay og resultpanel

**Files:**
- Modify: `web/profilutforsker.html`

- [ ] **Steg 1: Legg til måle-state-variablar etter `currentCoordMap`**

```javascript
let measureMode = 'idle'; // 'idle' | 'wait_a' | 'wait_b' | 'result'
let measurement = null;   // {a: {svgX, svgY, x_m, z_m} | null, b: ...}
```

- [ ] **Steg 2: Legg til målingsknapp i HTML (`.svg-zoom-ctrl`)**

Finn (rundt linje 827):
```html
        <div class="svg-zoom-ctrl" id="svg-zoom-ctrl">
          <button class="svg-zoom-btn" onclick="svgZoomBtn(1.25)" title="Zoom inn">+</button>
          <button class="svg-zoom-btn" onclick="svgZoomBtn(0.8)" title="Zoom ut">−</button>
          <button class="svg-zoom-btn" onclick="resetCsZoom()" ...>
```

Legg til som siste knapp i gruppen (etter reset-knappen):
```html
          <button class="svg-zoom-btn" id="btn-measure" onclick="toggleMeasure()" title="Avstandsmåling">
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
              <line x1="1" y1="10" x2="10" y2="1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              <line x1="1" y1="8" x2="3" y2="10" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
              <line x1="8" y1="1" x2="10" y2="3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
            </svg>
          </button>
```

- [ ] **Steg 3: Legg til CSS for aktiv måleknapp og målepanel**

Etter `.svg-zoom-btn:hover { ... }` (rundt linje 408):
```css
#btn-measure.is-on { background: var(--accent); color: white; border-color: var(--accent); }
#measure-panel {
  display: none; border-top: 1px solid var(--accent-line);
  padding: 10px 14px; background: var(--accent-soft); font-size: 11.5px;
}
#measure-panel.visible { display: block; }
.measure-lbl { font-size: 9.5px; font-weight: 700; letter-spacing: .08em;
  color: var(--accent-ink); text-transform: uppercase; margin-bottom: 6px; }
.measure-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 12px; color: var(--ink-3); }
.measure-grid .val { font-family: var(--font-mono); color: var(--ink); font-weight: 600; }
.measure-actions { display: flex; gap: 6px; margin-top: 8px; padding-top: 8px;
  border-top: 1px solid var(--accent-line); }
```

- [ ] **Steg 4: Legg til `#measure-panel` HTML i `.dr-body`**

Finn `.dr-body`-seksjonen (rundt linje 838) og legg til etter `</dl>`:
```html
        <div id="measure-panel">
          <div class="measure-lbl">Måleresultat</div>
          <div class="measure-grid">
            <span>Horisontal avstand</span><span class="val" id="mv-dx">—</span>
            <span>Høydeforskjell (ΔZ)</span><span class="val" id="mv-dz">—</span>
            <span>% fall</span><span class="val" id="mv-fall">—</span>
            <span>Skrå avstand</span><span class="val" id="mv-3d">—</span>
          </div>
          <div class="measure-actions">
            <button class="btn-mini" onclick="clearMeasure()">Nullstill</button>
            <button class="btn-mini" onclick="copyMeasure()">Kopier</button>
          </div>
        </div>
```

- [ ] **Steg 5: Implementer måle-funksjonene**

Legg til etter `renderHoverOverlay()`:

```javascript
function toggleMeasure() {
  if (measureMode !== 'idle') {
    clearMeasure();
  } else {
    measureMode = 'wait_a';
    document.getElementById('btn-measure').classList.add('is-on');
    document.getElementById('cs-meta-line').textContent = 'Klikk punkt 1 i tegningen';
    svgArea.style.cursor = 'crosshair';
  }
}

function clearMeasure() {
  measureMode = 'idle';
  measurement = null;
  document.getElementById('btn-measure').classList.remove('is-on');
  document.getElementById('measure-panel').classList.remove('visible');
  svgArea.style.cursor = '';
  clearMeasureOverlay();
  // Restore meta line
  if (currentIdx >= 0 && stations[currentIdx]) {
    const s = stations[currentIdx];
    document.getElementById('cs-meta-line').textContent =
      (s.stasjon_m / 1000).toFixed(3) + ' km · ' + s.z.toFixed(1) + ' m.o.h.';
  }
}

function clearMeasureOverlay() {
  if (!overlayEl()) return;
  overlayEl().querySelectorAll('.measure-el').forEach(e => e.remove());
}

function renderMeasureOverlay() {
  clearMeasureOverlay();
  const svg = svgEl(), ov = overlayEl();
  if (!svg || !ov || !measurement) return;

  const mkEl = (tag, attrs) => {
    const el = document.createElementNS(CS_NS, tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    el.classList.add('measure-el');
    ov.appendChild(el);
    return el;
  };

  const A = measurement.a, B = measurement.b;

  if (A) {
    mkEl('circle', {cx: A.svgX, cy: A.svgY, r: 4,
      fill: A.loose ? '#e8c94a' : '#c25a1f', stroke: 'white', 'stroke-width': 1.2});
    const t = mkEl('text', {x: A.svgX + 5, y: A.svgY - 5,
      'font-size': 9, fill: A.loose ? '#c25a1f' : '#c25a1f',
      'font-family': 'Inter Tight, system-ui, sans-serif', 'font-weight': '700'});
    t.textContent = '1';
  }

  if (B) {
    mkEl('circle', {cx: B.svgX, cy: B.svgY, r: 4,
      fill: B.loose ? '#e8c94a' : '#c25a1f', stroke: 'white', 'stroke-width': 1.2});
    const t = mkEl('text', {x: B.svgX + 5, y: B.svgY - 5,
      'font-size': 9, fill: '#c25a1f',
      'font-family': 'Inter Tight, system-ui, sans-serif', 'font-weight': '700'});
    t.textContent = '2';
  }

  if (A && B) {
    mkEl('line', {x1: A.svgX, y1: A.svgY, x2: B.svgX, y2: B.svgY,
      stroke: '#c25a1f', 'stroke-width': 1, 'stroke-dasharray': '6 3'});

    const mx = (A.svgX + B.svgX) / 2, my = (A.svgY + B.svgY) / 2;
    const dx = Math.abs(B.x_m - A.x_m);
    const dz = B.z_m - A.z_m;
    const fall = dx > 0.001 ? (dz / dx * 100) : 0;
    const d3 = Math.hypot(dx, dz);

    const lbl = dx.toFixed(2) + ' m';
    const lW = lbl.length * 6 + 14;
    mkEl('rect', {x: mx - lW / 2, y: my - 10, width: lW, height: 14,
      rx: 3, fill: '#c25a1f'});
    const t = mkEl('text', {x: mx, y: my - 0.5,
      'font-size': 9, fill: 'white', 'text-anchor': 'middle',
      'font-family': 'Inter Tight, system-ui, sans-serif', 'font-weight': '700'});
    t.textContent = lbl;

    // Update result panel
    document.getElementById('mv-dx').textContent = dx.toFixed(2) + ' m';
    document.getElementById('mv-dz').textContent = (dz >= 0 ? '+' : '') + dz.toFixed(2) + ' m';
    document.getElementById('mv-fall').textContent = fall.toFixed(1) + ' %';
    document.getElementById('mv-3d').textContent = d3.toFixed(2) + ' m';
    document.getElementById('measure-panel').classList.add('visible');
  }
}

function copyMeasure() {
  if (!measurement || !measurement.a || !measurement.b) return;
  const A = measurement.a, B = measurement.b;
  const dx = Math.abs(B.x_m - A.x_m);
  const dz = B.z_m - A.z_m;
  const fall = dx > 0.001 ? (dz / dx * 100) : 0;
  const row = [dx.toFixed(3), dz.toFixed(3), fall.toFixed(2), Math.hypot(dx, dz).toFixed(3)].join('\t');
  navigator.clipboard.writeText(row).catch(() => {});
}
```

- [ ] **Steg 6: Legg til klikk-handler for måling på `svgArea`**

Finn `svgArea.addEventListener('pointerdown', ...)` (rundt linje 1757). Legg til en klikk-handler ETTER pointerdown/move/up:

```javascript
svgArea.addEventListener('click', (e) => {
  if (measureMode === 'idle' || svgDragging) return;
  if (e.target.closest('.svg-zoom-ctrl')) return;
  const svg = svgEl();
  if (!svg || !currentCoordMap) return;

  const rect = svgArea.getBoundingClientRect();
  const svgX = (e.clientX - rect.left - svgPanX) / svgScale;
  const svgY = (e.clientY - rect.top - svgPanY) / svgScale;
  const snap = snapToPath(svg, svgX, svgY, 40 / svgScale);

  if (!snap) {
    document.getElementById('cs-meta-line').textContent = 'Ingen geometri her — prøv nærmere en linje';
    setTimeout(() => {
      if (measureMode !== 'idle' && currentIdx >= 0) {
        document.getElementById('cs-meta-line').textContent =
          measureMode === 'wait_a' ? 'Klikk punkt 1 i tegningen' : 'Klikk punkt 2 i tegningen';
      }
    }, 1500);
    return;
  }

  const real = currentCoordMap.svgToReal(snap.x, snap.y);
  const pt = {svgX: snap.x, svgY: snap.y, x_m: real.x_m, z_m: real.z_m, loose: false};

  if (measureMode === 'wait_a') {
    measurement = {a: pt, b: null};
    measureMode = 'wait_b';
    document.getElementById('cs-meta-line').textContent = 'Klikk punkt 2 i tegningen';
    renderMeasureOverlay();
  } else if (measureMode === 'wait_b') {
    measurement.b = pt;
    measureMode = 'result';
    svgArea.style.cursor = '';
    document.getElementById('btn-measure').classList.remove('is-on');
    document.getElementById('cs-meta-line').textContent = 'Måleresultat vist under';
    renderMeasureOverlay();
  }
});
```

- [ ] **Steg 7: Legg til Escape-tast handling**

Finn `window.addEventListener('keydown', ...)` (rundt linje 1199) og legg til i toppen av funksjonen:

```javascript
  if (e.key === 'Escape') {
    if (measureMode !== 'idle') { clearMeasure(); return; }
  }
```

- [ ] **Steg 8: Eksponer `toggleMeasure`, `clearMeasure`, `copyMeasure` i globalscope-listen**

Finn (rundt linje 2065):
```javascript
  nav, drawLp, svgZoomBtn, resetCsZoom,
```
Legg til:
```javascript
  nav, drawLp, svgZoomBtn, resetCsZoom, toggleMeasure, clearMeasure, copyMeasure,
```

- [ ] **Steg 9: Manuell test — måling**

Start viewer, klikk en stasjon, klikk måleknappen (linjal-ikon).

Forventet:
- Cursor endres til crosshair, header viser "Klikk punkt 1 i tegningen"
- Klikk på vegkant: oransje prikk med "1" vises
- Klikk på andre vegkant: "2" vises, stiplet linje mellom dem, dimensjonslabel
- Resultpanel vises med horisontal avstand, ΔZ, % fall, skrå avstand
- Escape nullstiller

- [ ] **Steg 10: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: point-to-point measurement tool with SVG overlay and result panel"
```

---

## Task 5: profilutforsker.html — Persistens av måling ved stasjonsskift

**Files:**
- Modify: `web/profilutforsker.html`

Målingen skal "følge med" til neste stasjon ved å re-snappe de lagrede real-world-koordinatene mot den nye SVG-geometrien.

- [ ] **Steg 1: Legg til `remeasureAfterLoad()` etter `renderMeasureOverlay()`**

```javascript
function remeasureAfterLoad() {
  if (!measurement || !currentCoordMap) return;
  const svg = svgEl();
  if (!svg) return;

  ['a', 'b'].forEach(key => {
    const pt = measurement[key];
    if (!pt) return;
    const {svgX, svgY} = currentCoordMap.realToSvg(pt.x_m, pt.z_m);
    const snap = snapToPath(svg, svgX, svgY, 999);
    if (snap) {
      const real = currentCoordMap.svgToReal(snap.x, snap.y);
      const dist = Math.hypot(real.x_m - pt.x_m, real.z_m - pt.z_m);
      measurement[key] = {svgX: snap.x, svgY: snap.y, x_m: real.x_m, z_m: real.z_m, loose: dist > 2};
    } else {
      measurement[key] = {...pt, svgX, svgY, loose: true};
    }
  });

  if (measureMode === 'result') renderMeasureOverlay();
}
```

- [ ] **Steg 2: Kall `remeasureAfterLoad()` i `loadSvg()` etter at SVG og coordMap er klare**

Finn i `loadSvg()` der `resetCsZoom()` kalles og legg til etter:

```javascript
    resetCsZoom();
    remeasureAfterLoad();
    return parseSvgXTicks(svgText);
```

- [ ] **Steg 3: Tilbakestill SVG coords ved `clearMeasure()` (valgfri robusthet)**

`clearMeasure()` sletter allerede `measurement = null`, så dette er allerede håndtert.

- [ ] **Steg 4: Manuell test — persistens**

Start viewer. Klikk to punkter og se resultpanelet. Bruk piltaster eller nav-knapper for å gå til neste profil.

Forventet:
- Prikk 1 og prikk 2 vises på den nye profilen (re-snappet til nærmeste geometri)
- Resultpanelet oppdateres med nye målverdier
- Hvis et punkt er langt fra geometri (> 2 m): gul prikk + ingen resultpanel
- Escape fjerner fortsatt målingen

- [ ] **Steg 5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: persist measurement across station navigation with re-snap"
```

---

## Selvgjennomgang (spec vs. plan)

| Spec-krav | Dekket i |
|-----------|----------|
| Hover-avlesning: x fra CL, z, % fall | Task 3 |
| Snap til linjer (hover) | Task 3 |
| Snap til linjer (klikk) | Task 4 |
| Punkt-til-punkt: ΔX, ΔZ, % fall, skrå avstand | Task 4 |
| Resultpanel med Nullstill/Kopier | Task 4 |
| Persistens ved navigasjon, re-snap | Task 5 |
| Løs prikk ved > 2 m avvik | Task 5 |
| Inline SVG (erstatter img) | Task 2 |
| data-cs tagging i renderer.py | Task 1 |
| Dark mode filter | Task 2 (CSS) |
| Escape-tast nullstiller | Task 4 |
| Fallback for SVG uten data-cs | Task 1 (gid) + Task 2 (tagDataCsElements) |
