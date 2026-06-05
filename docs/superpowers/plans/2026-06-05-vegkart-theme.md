# Vegkart-tema for profilutforskeren — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `web/profilutforsker.html` til SVV Vegkarts look and feel (skifer/oransje-palett, Mulish, 2px hjørner, flytende lag-kort) uten å fjerne funksjonalitet.

**Architecture:** Én HTML-fil. Fargebyttet skjer nesten utelukkende via CSS-variabelblokkene (`:root` + `html[data-theme="dark"]`) — variabelNAVNENE beholdes (f.eks. `--svv-navy-900` får skiferverdi) så selektorer ikke må endres. Deretter komponentvise CSS-justeringer (radier, skygger, layout), én HTML-omstrukturering (sidebar → flytende lag-kort) og en håndfull hardkodede farger/fonter i JS.

**Tech Stack:** Vanilla HTML/CSS/JS, ArcGIS Maps SDK for JavaScript 5.0, Google Fonts (Mulish + JetBrains Mono). Ingen byggesteg — fila serveres som den er.

**Spec:** `docs/superpowers/specs/2026-06-05-vegkart-theme-design.md` (godkjent).

**Testing:** Ren frontend — manuell visuell verifisering (Task 8). Ingen pytest berøres. Kjør lokalt med:

```powershell
python -m http.server 8000 --directory web
```

og åpne `http://localhost:8000/profilutforsker.html`.

**Viktige fakta for utfører (null kontekst antatt):**
- Fila er ~3811 linjer. Linjenumre under er fra utgangspunktet og forskyves etter hvert som du redigerer — bruk selektor-/funksjonsnavn som anker, linjenummer som hint.
- Senterlinja i kartet tegnes **stiplet svart** (kommentar «Stiplet svart senterlinje» ved linje 2327). Legend-swatchen på linje 887 bruker i dag `var(--accent)` — den skal pinnes til `var(--ink)`, IKKE bli oransje.
- R700-fargene (`--road-gray`, `--road-yellow`, `--road-existing`), signal-rosa `#e0228e` og all ArcGIS-renderer-symbologi (kartdata) skal IKKE endres.
- `#e8c94a` (gul «løs» måleannotasjon) beholdes.
- Det finnes INGEN `localStorage`-bruk i fila fra før. Tema-valget persisteres ikke i dag, og det skal vi IKKE legge til (utenfor scope). Kun lag-kortets kollaps-tilstand persisteres (Task 3).
- To pre-eksisterende CSS-bugs fikses underveis: `var(--svv-green-500)` (linje 336, udefinert) og `var(--ink-1)` (linje 365, udefinert).

---

### Task 1: Mulish + nye designtokens

**Files:**
- Modify: `web/profilutforsker.html` (linje 9 font-link, linje 12–54 `:root`, linje 56–71 dark-blokk)

- [ ] **Step 1: Bytt Google Fonts-lenken (linje 9)**

Erstatt:

```html
  <link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

med:

```html
  <link href="https://fonts.googleapis.com/css2?family=Mulish:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Erstatt hele `:root`-blokken (linje 12–54)**

Dagens blokk starter med `:root {` og slutter med `color-scheme: light;\n}`. Erstatt hele blokken med:

```css
:root {
  /* Skifer (Vegkart) erstatter navy — variabelnavn beholdt for å unngå selector-endringer */
  --svv-navy-900: #444f55;
  --svv-navy-800: #353e43;
  --svv-navy-700: #5b676e;
  --svv-navy-50:  #ececec;

  --paper:        #f5f5f5;
  --paper-2:      #ececec;
  --ink:          #444f55;
  --ink-2:        #535d63;
  --ink-3:        #697277;
  --ink-4:        #858d90;
  --line:         #dadada;
  --line-2:       #e8e8e8;
  --line-strong:  #858d90;
  --card:         #ffffff;

  --accent:       #ff9600;
  --accent-ink:   #8a5200;
  --accent-soft:  #fff5e6;
  --accent-line:  #ffd9a3;

  --ok:           #158925;
  --ok-bg:        #e8f3e9;
  --err:          #b63434;
  --err-bg:       #fedfe1;
  --info:         #077197;
  --info-bg:      #e6f1f5;

  --signal-pink:  #e0228e;
  --warn:         #e27500;
  --warn-bg:      #fff5e6;

  --map-bg:       #e9e9e9;

  --road-gray:    #BBBCBC;
  --road-yellow:  #FFE080;
  --road-existing:#9aac98;

  --shadow:       0 2px 2px rgba(0,0,0,.3);

  --r-sm: 2px;
  --r:    2px;
  --r-lg: 4px;
  --topbar-h: 44px;
  --sidebar-w: 280px;
  --layer-card-w: 300px;
  --drawer-right-w: 460px;
  --drawer-bottom-h: 480px;

  --font-sans: "Mulish", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

  color-scheme: light;
}
```

Merk: `--sidebar-w` beholdes midlertidig (sidebar-CSS-en bruker den frem til Task 3). `--layer-card-w` brukes først i Task 3.

- [ ] **Step 3: Erstatt hele dark-blokken (linje 56–71)**

Dagens blokk starter med `html[data-theme="dark"] {` og slutter med `color-scheme: dark;\n}`. Erstatt hele blokken med:

```css
html[data-theme="dark"] {
  --svv-navy-900: #231f20;
  --svv-navy-800: #2c3438;
  --svv-navy-700: #4a555c;
  --svv-navy-50:  #3f484e;
  --paper:        #231f20;
  --paper-2:      #2c3438;
  --ink:          #ececec;
  --ink-2:        #c6cdd1;
  --ink-3:        #9aa4a9;
  --ink-4:        #7d878c;
  --line:         #4a555c;
  --line-2:       #3f484e;
  --line-strong:  #697277;
  --card:         #353e43;
  --accent-ink:   #ffc069;
  --accent-soft:  #4a3a1d;
  --accent-line:  #6e5328;
  --ok:           #5fc26d;
  --ok-bg:        #1d3322;
  --err:          #ff9a9a;
  --err-bg:       #432527;
  --info:         #6cc4e0;
  --info-bg:      #1c333d;
  --warn:         #ffb45c;
  --warn-bg:      #3d2d15;
  --map-bg:       #1a1d1f;
  color-scheme: dark;
}
```

(`--accent` overstyres ikke i dark — oransje `#ff9600` gjelder begge temaer, per spec.)

- [ ] **Step 4: Fiks de to udefinerte variablene**

Linje 336 — erstatt:

```css
.basemap-option .bm-check { margin-left: auto; font-size: 11px; color: var(--svv-green-500); opacity: 0; }
```

med:

```css
.basemap-option .bm-check { margin-left: auto; font-size: 11px; color: var(--accent); opacity: 0; }
```

Linje 365 — erstatt:

```css
.legend-toggle:hover { background: var(--line-2); color: var(--ink-1); }
```

med:

```css
.legend-toggle:hover { background: var(--line-2); color: var(--ink); }
```

- [ ] **Step 5: Pin legendens senterlinje-swatch til blekkfargen**

Senterlinja i kartet er stiplet svart; swatchen må ikke bli oransje når `--accent` skifter. Linje 887 — erstatt:

```html
        <span class="sw line" style="color:var(--accent)"></span>
```

med:

```html
        <span class="sw line" style="color:var(--ink)"></span>
```

- [ ] **Step 6: Verifiser**

Søk i fila: `Inter Tight` skal nå KUN finnes i JS-strenger (linje ~1871, ~1929, ~1939, ~1954 — de tas i Task 7). `--svv-green-500` og `--ink-1` skal gi null treff. Åpne appen i nettleser: alt skal være skifer/grått/oransje (litt rotete radier/layout er forventet — det kommer i Task 2–6).

- [ ] **Step 7: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(tema): Vegkart-designtokens + Mulish erstatter navy/grønn/Inter Tight"
```

---

### Task 2: Topbar — 44px og Vegkart-kontroller

**Files:**
- Modify: `web/profilutforsker.html` (CSS ~linje 84–175 + `.viewmode-seg` ~linje 270–281)

`--topbar-h` ble 44px i Task 1; her justeres kontrollene. Bakgrunnen (`var(--svv-navy-900)`) er allerede skifer via tokens.

- [ ] **Step 1: brand-mark — 2px hjørner**

I `.brand-mark`-regelen (linje ~95–100), endre kun:

```css
  width: 26px; height: 26px; border-radius: 4px;
```

til:

```css
  width: 26px; height: 26px; border-radius: var(--r-sm);
```

- [ ] **Step 2: project-pick, project-chip, top-search, top-btn — 2px hjørner**

Fire punkt-endringer:

I `.project-pick` (linje ~106): `padding: 5px 10px; border-radius: 6px;` → `padding: 5px 10px; border-radius: var(--r);`

I `.project-chip` (linje ~121): `background: rgba(255,255,255,.10); padding: 2px 6px; border-radius: 3px;` → `background: rgba(255,255,255,.10); padding: 2px 6px; border-radius: var(--r-sm);`

I `.top-search` (linje ~129): `border-radius: 6px; padding: 6px 10px;` → `border-radius: var(--r); padding: 6px 10px;`

I `.top-btn` (linje ~143): `height: 30px; padding: 0 11px; border-radius: 6px;` → `height: 30px; padding: 0 11px; border-radius: var(--r);`

- [ ] **Step 3: 2D/3D-veksleren som pille-toggle**

Erstatt hele `.viewmode-seg`-blokken (linje ~271–281, tre regler):

```css
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

med:

```css
.viewmode-seg {
  display: inline-flex; align-items: center;
  background: rgba(255,255,255,.12); border-radius: 999px; padding: 2px;
}
.viewmode-seg button {
  height: 26px; padding: 0 14px; border: 0; border-radius: 999px;
  background: transparent; color: rgba(255,255,255,.7);
  font: inherit; font-size: 12px; font-weight: 600; cursor: pointer;
  transition: background .15s, color .15s;
}
.viewmode-seg button.active { background: var(--accent); color: #fff; }
```

- [ ] **Step 4: Oransje fokusring (global)**

Spec-en krever oransje fokusring på interaktive elementer. Rett etter `.viewmode-seg button.active`-regelen, legg til:

```css
button:focus-visible, select:focus-visible, input:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 1px;
}
```

(`:focus-visible` trigges kun ved tastaturnavigasjon — museklikk får ingen ring.)

- [ ] **Step 5: Verifiser i nettleser**

Topbaren er 44px, skifergrå (lys modus), kontroller med 2px hjørner; 2D/3D-veksleren er en pille med oransje aktiv side. Tema-toggle (måneknappen) fungerer fortsatt. Tab gjennom topbaren: oransje fokusring.

- [ ] **Step 6: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(tema): slank topbar 44px med Vegkart-kontroller og pille-veksler"
```

---

### Task 3: Sidebar → flytende lag-kort

**Files:**
- Modify: `web/profilutforsker.html` — CSS `/* ── SIDEBAR ── */` (linje ~186–249), markup `<aside class="sidebar">` (linje ~765–794), map-tool-knappen `toggleSidebar()` (linje ~849-ish, tittel «Vis/skjul lag»), JS `toggleSidebar` (linje ~3732–3734) og window-eksport (linje ~3800–3807), `:root` (`--sidebar-w` fjernes)

- [ ] **Step 1: Erstatt sidebar-CSS med lag-kort-CSS**

Erstatt HELE seksjonen fra `/* ── SIDEBAR ── */` (linje 186) til og med `.layer-count { ... }`-regelen (linje 249) med:

```css
/* ── FLYTENDE LAG-KORT ── */
.layer-card {
  position: absolute; top: 14px; left: 14px; z-index: 6;
  width: var(--layer-card-w);
  max-height: calc(100% - 28px);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.lc-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 12px;
  cursor: pointer; user-select: none;
  flex-shrink: 0;
}
.lc-head h2 {
  margin: 0; font-size: 13px; font-weight: 700;
  display: flex; align-items: center; gap: 8px; white-space: nowrap;
}
.lc-head .pill {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em;
  padding: 2px 6px; border-radius: var(--r-sm);
  background: var(--ok-bg); color: var(--ok);
  text-transform: uppercase; flex-shrink: 0;
}
.lc-toggle {
  display: flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; padding: 0;
  border: none; background: transparent; border-radius: var(--r-sm); cursor: pointer;
  color: var(--ink-3); flex-shrink: 0;
  transition: background .15s, color .15s;
}
.lc-head:hover .lc-toggle { background: var(--paper-2); color: var(--ink); }
.lc-toggle svg { transition: transform .22s cubic-bezier(.2,.7,.2,1); }
.layer-card.collapsed .lc-body { display: none; }
.layer-card.collapsed .lc-toggle svg { transform: rotate(180deg); }
.lc-body { overflow-y: auto; border-top: 1px solid var(--line-2); }
.lc-sub { margin: 0; padding: 8px 12px 2px; font-size: 11px; color: var(--ink-3); }

.sb-group { padding: 8px 0; border-bottom: 1px solid var(--line-2); }
.sb-group:last-child { border-bottom: 0; }
.sb-grp-title {
  padding: 0 12px 5px;
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.09em;
  color: var(--ink-4); text-transform: uppercase;
}
.layer-row {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 12px; cursor: default;
  transition: background .1s;
}
.layer-row:hover { background: var(--paper-2); }
.layer-row.active { background: transparent; }
.layer-toggle {
  width: 28px; height: 16px; border-radius: 8px;
  border: 0; flex: 0 0 28px;
  background: var(--ink-4); cursor: pointer;
  position: relative; font-size: 0; color: transparent;
  transition: background .15s;
}
.layer-toggle::after {
  content: ""; position: absolute; top: 2px; left: 2px;
  width: 12px; height: 12px; border-radius: 50%;
  background: #fff;
  transition: left .15s;
}
.layer-toggle.on { background: var(--accent); }
.layer-toggle.on::after { left: 14px; }
.layer-swatch {
  flex: 0 0 auto;
  border: 1px solid rgba(0,0,0,.1);
}
.layer-name { flex: 1; font-size: 12px; color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.layer-row.muted .layer-name { color: var(--ink-4); }
.layer-count {
  font-family: var(--font-mono); font-size: 10px; color: var(--ink-4);
  background: var(--paper-2); padding: 1px 5px; border-radius: var(--r-sm); flex-shrink: 0;
}
```

Merk: pille-togglen (`.layer-toggle`) erstatter checkbox-stilen; `✓`-tegnet i markupen skjules av `font-size: 0`. Den gamle `html[data-theme="dark"] .layer-row.active`-overstyringen (linje 230) skal IKKE gjenskapes — den fjernes som del av denne erstatningen.

- [ ] **Step 2: Erstatt sidebar-markupen med lag-kort-markup**

Erstatt hele `<aside class="sidebar" id="sidebar"> ... </aside>` (linje ~765–794) med (alle id-er beholdes — JS bruker `sb-pill`, `sb-sub`, `row-*`, `tog-*`, `cnt-*`, `grp-bim`):

```html
    <aside class="layer-card" id="layer-card">
      <div class="lc-head" onclick="toggleLayerCard()">
        <h2>Lag <span class="pill" id="sb-pill" style="display:none">Live</span></h2>
        <button class="lc-toggle" id="lc-toggle" title="Minimer lagpanel" aria-label="Minimer lagpanel" aria-expanded="true">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
            <path d="M2 4l3.5 3.5L9 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
      <div class="lc-body" id="lc-body">
        <p class="lc-sub" id="sb-sub">Velg et prosjekt for å se lag</p>
        <div class="sb-group">
          <div class="sb-grp-title">Prosjekterte</div>
          <div class="layer-row active" id="row-centerline" onclick="toggleLayer('centerline')">
            <button class="layer-toggle on" id="tog-centerline">✓</button>
            <div class="layer-swatch" style="width:18px;height:3px;border-radius:0;background:#000;border:0;margin:5px 0"></div>
            <span class="layer-name">Senterlinje</span>
            <span class="layer-count" id="cnt-centerline" style="display:none">—</span>
          </div>
          <div class="layer-row active" id="row-stations" onclick="toggleLayer('stations')">
            <button class="layer-toggle on" id="tog-stations">✓</button>
            <div class="layer-swatch" style="width:9px;height:9px;border-radius:50%;border:1.5px solid var(--svv-navy-900);background:transparent;flex:0 0 9px;margin:0 4.5px"></div>
            <span class="layer-name">Tverrprofilpunkter</span>
            <span class="layer-count" id="cnt-stations" style="display:none">—</span>
          </div>
        </div>
        <div class="sb-group" id="grp-bim" style="display:none">
          <div class="sb-grp-title">BIM-modell</div>
          <div class="layer-row active" id="row-bim" onclick="toggleLayer('bim')">
            <button class="layer-toggle on" id="tog-bim">✓</button>
            <div class="layer-swatch" style="width:14px;height:10px;border-radius:2px;background:#646468;border:0.5px solid #3c3c46;flex:0 0 14px;margin:0 2px"></div>
            <span class="layer-name">Vegmodell (2D)</span>
            <span class="layer-count" id="cnt-bim" style="display:none">—</span>
          </div>
        </div>
      </div>
    </aside>
```

`<aside>` blir stående der den står i dag (første barn av `<div class="stage">`, før `<div class="map-area">`) — den posisjoneres nå absolutt oppå kartet.

- [ ] **Step 3: Erstatt `toggleSidebar()` med `toggleLayerCard()` i JS**

Erstatt funksjonen (linje ~3732–3734):

```js
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('collapsed');
}
```

med:

```js
function toggleLayerCard() {
  const card = document.getElementById('layer-card');
  const collapsed = card.classList.toggle('collapsed');
  document.getElementById('lc-toggle').setAttribute('aria-expanded', String(!collapsed));
  try { localStorage.setItem('pf.layerCardCollapsed', collapsed ? '1' : '0'); } catch { /* private mode o.l. */ }
}
```

- [ ] **Step 4: Gjenopprett kollaps-tilstand ved lasting**

Rett FØR `Object.assign(window, { ... })`-blokken (linje ~3800), legg til:

```js
// Gjenopprett lag-kortets kollaps-tilstand fra forrige økt
try {
  if (localStorage.getItem('pf.layerCardCollapsed') === '1') {
    document.getElementById('layer-card').classList.add('collapsed');
    document.getElementById('lc-toggle').setAttribute('aria-expanded', 'false');
  }
} catch { /* private mode o.l. */ }
```

- [ ] **Step 5: Oppdater window-eksporten**

I `Object.assign(window, { ... })` (linje ~3800–3807), erstatt `toggleSidebar,` med `toggleLayerCard,`.

- [ ] **Step 6: Pek map-tool-knappen på den nye funksjonen**

Map-tool-knappen med `title="Vis/skjul lag"` (i `.map-tools`-markupen, linje ~849) har `onclick="toggleSidebar()"`. Endre til `onclick="toggleLayerCard()"`.

- [ ] **Step 7: Fjern `--sidebar-w` fra `:root`**

Slett linja `  --sidebar-w: 280px;` fra `:root`. Verifiser at `--sidebar-w` og ordet `sidebar` nå gir null treff i fila (verken CSS, markup eller JS).

- [ ] **Step 8: Verifiser i nettleser**

Kartet fyller hele bredden under topbaren. Hvitt lag-kort oppe til venstre med «Lag»-header. Chevron kollapser/ekspanderer; tilstanden overlever reload (localStorage). Lag-radene har oransje/grå pille-toggles som fortsatt slår lag av/på (klikk en rad og se at laget forsvinner i kartet). Map-tool-knappen «Vis/skjul lag» kollapser kortet.

- [ ] **Step 9: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(tema): sidebar erstattet med flytende kollapsbart lag-kort (localStorage)"
```

---

### Task 4: Kartverktøy, map-info, legend og basemap-velger

**Files:**
- Modify: `web/profilutforsker.html` (CSS ~linje 283–394 + `.esri-attribution` ~linje 670–674)

- [ ] **Step 1: Flytt map-info ned til venstre + nye hjørner/skygge**

`.map-info` (linje ~283–289) — lag-kortet okkuperer nå øvre venstre hjørne. Erstatt regelen:

```css
.map-info {
  position: absolute; top: 14px; left: 14px; z-index: 6;
  background: var(--card); border: 1px solid var(--line);
  border-radius: 6px; padding: 7px 12px;
  font-size: 11.5px; display: flex; align-items: center; gap: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
```

med:

```css
.map-info {
  position: absolute; bottom: 14px; left: 14px; z-index: 6;
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--r); padding: 7px 12px;
  font-size: 11.5px; display: flex; align-items: center; gap: 12px;
  box-shadow: var(--shadow);
}
```

(Speiler legenden nede til høyre. At bunn-draweren dekker den når den er åpen, er samme aksepterte oppførsel som legenden har i dag.)

- [ ] **Step 2: kbd — 2px hjørner**

I `kbd`-regelen (linje ~296–300): `border-radius: 3px; padding: 1px 4px;` → `border-radius: var(--r-sm); padding: 1px 4px;`

- [ ] **Step 3: map-tools — 40×40 verktøy-rail**

Tre endringer:

I `.map-tools` (linje ~302): `display: flex; flex-direction: column; gap: 7px;` → `display: flex; flex-direction: column; gap: 8px;`

Erstatt `.map-tool-group` (linje ~309–312):

```css
.map-tool-group {
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); overflow: hidden;
}
```

med:

```css
.map-tool-group {
  background: var(--card); border: 1px solid var(--line); border-radius: var(--r);
  box-shadow: var(--shadow); overflow: hidden;
}
```

I `.map-tool` (linje ~313–318): `width: 34px; height: 34px;` → `width: 40px; height: 40px;` og `font-size: 13px;` → `font-size: 14px;`

(`.map-tool.active` beholdes som den er — `var(--svv-navy-900)` er nå skifer = «mørk flate, aktiv» per spec.)

- [ ] **Step 4: basemap-picker — 2px hjørner og kort-skygge**

I `.basemap-picker` (linje ~323): `border-radius: 6px;` → `border-radius: var(--r);` og `box-shadow: 0 4px 12px rgba(0,0,0,.12);` → `box-shadow: var(--shadow);`

I `.basemap-option` (linje ~329): `padding: 6px 8px; border-radius: 4px;` → `padding: 6px 8px; border-radius: var(--r-sm);`

I `.basemap-swatch` (linje ~338): `border-radius: 3px;` → `border-radius: var(--r-sm);`

- [ ] **Step 5: legend — 2px hjørner og kort-skygge**

I `.map-legend` (linje ~343): `border-radius: 6px;` → `border-radius: var(--r);` og `box-shadow: 0 1px 3px rgba(0,0,0,.06);` → `box-shadow: var(--shadow);`

I `.legend-toggle` (linje ~358): `border-radius: 4px;` → `border-radius: var(--r-sm);`

- [ ] **Step 6: map-tooltip — 2px hjørner**

I `.map-tooltip` (linje ~380): `padding: 6px 9px; border-radius: 4px;` → `padding: 6px 9px; border-radius: var(--r);` (bakgrunnen `var(--svv-navy-900)` er allerede skifer via tokens).

- [ ] **Step 7: esri-attribution — bort fra beige**

Erstatt (linje ~670-ish):

```css
.esri-attribution { background: rgba(244,243,238,.85) !important; border-radius: 4px 0 0 0 !important; }
```

med:

```css
.esri-attribution { background: rgba(255,255,255,.85) !important; border-radius: var(--r) 0 0 0 !important; }
```

(Dark-varianten `rgba(12,18,24,.85)` rett under beholdes.)

- [ ] **Step 8: Verifiser i nettleser**

Verktøyknappene er 40×40 i hvit vertikal rail med skygge. Koordinat-/stasjonsinfo ligger nede til venstre. Legend og basemap-velger har 2px hjørner. Tooltip på stasjonspunkt er skifergrå.

- [ ] **Step 9: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(tema): kartverktøy 40px-rail, map-info nede til venstre, legend/picker i Vegkart-stil"
```

---

### Task 5: Drawere — kort som skyves inn

**Files:**
- Modify: `web/profilutforsker.html` (CSS `.drawer-right` ~linje 407+, `.drawer-bottom` ~linje 582+)

- [ ] **Step 1: drawer-right — tydeligere skygge mot kartet**

I `.drawer-right`-regelen (linje ~407–415): `box-shadow: -4px 0 14px rgba(0,0,0,.06);` → `box-shadow: -2px 0 8px rgba(0,0,0,.25);` (border-left `var(--line)` er allerede `#dadada` via tokens).

- [ ] **Step 2: svg-zoom-knapper og nav-knapper — token-hjørner**

I `.nav-btn`-regelen (nederst i drawer-right-seksjonen, ~linje 520-ish): `border-radius: 4px;` → `border-radius: var(--r);`

(`.svg-zoom-btn` bruker allerede `var(--r-sm)` — ingen endring.)

- [ ] **Step 3: drawer-bottom — skygge + flat handle**

I `.drawer-bottom`-regelen (linje ~582–590): `box-shadow: 0 -4px 14px rgba(0,0,0,.06);` → `box-shadow: 0 -2px 8px rgba(0,0,0,.25);`

I `.drawer-handle`-regelen (linje ~600-ish): `background: linear-gradient(to bottom, var(--card), var(--paper));` → `background: var(--card);`

- [ ] **Step 4: btn-mini — token-hjørner**

I `.btn-mini`-regelen (linje ~620-ish): `border-radius: 4px;` → `border-radius: var(--r);`

(`.btn-mini.active` med `var(--svv-navy-900)` beholdes — skifer aktiv-flate.)

- [ ] **Step 5: xp-zoom-HUD — token-hjørner**

I `.xp-zoom-hud`-regelen: `border-radius: 6px;` → `border-radius: var(--r);`
I `.xp-zoom-btn`-regelen: `border-radius: 4px;` → `border-radius: var(--r-sm);`

(Begge ligger i drawer-bottom-seksjonen, ~linje 640–668.)

- [ ] **Step 6: Verifiser i nettleser**

Velg et prosjekt og klikk en stasjon: høyre-drawer (tverrprofil) og bunn-drawer (lengdeprofil) leses som hvite kort med kant + skygge mot kartet. Målemodus-panelet i tverrprofilen er nå oransje-tintet (via `--accent-soft`/`--accent-line` fra Task 1).

- [ ] **Step 7: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(tema): drawere som hvite kort med kant og skygge mot kartet"
```

---

### Task 6: Snap-preview — solid kort uten glassmorphism

**Files:**
- Modify: `web/profilutforsker.html` (CSS `.snap-preview-card` ~linje 535–580, `spgrid`-pattern i markup ~linje 935)

- [ ] **Step 1: Erstatt glass-kortet med solid kort**

Erstatt `.snap-preview-card`-regelen (linje ~539-ish):

```css
.snap-preview-card {
  width: 204px;
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 9px 10px 8px;
  box-shadow: 0 4px 14px rgba(8,20,36,.10), 0 1px 3px rgba(8,20,36,.06);
  transform: translateY(-50%);
}
```

med:

```css
.snap-preview-card {
  width: 204px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  padding: 9px 10px 8px;
  box-shadow: var(--shadow);
  transform: translateY(-50%);
}
```

- [ ] **Step 2: Slett dark-overstyringen for kortet**

Slett regelen (linje ~552):

```css
html[data-theme="dark"] .snap-preview-card { background: rgba(18,28,37,0.95); }
```

(`var(--card)` dekker nå begge temaer. Dark-overstyringen for `.snap-preview-svg-el` lenger ned beholdes hvis den finnes — den bruker tokens.)

- [ ] **Step 3: Rutenett-streken fra navy- til skifer-avledet**

I snap-preview-markupen (linje ~935), i `<pattern id="spgrid" ...>`, erstatt `stroke="rgba(11,58,99,0.07)"` med `stroke="rgba(68,79,85,0.08)"`.

- [ ] **Step 4: Verifiser i nettleser**

Hold musa nær senterlinja (med valgt prosjekt): forhåndsvisningskortet er solid hvitt (solid mørkt i dark mode) uten blur.

- [ ] **Step 5: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(tema): snap-preview som solid kort uten glassmorphism"
```

---

### Task 7: Hardkodede farger og fonter i JS

**Files:**
- Modify: `web/profilutforsker.html` (JS: linje ~1871, ~1918–1962, ~2045–2053, ~3155–3160)

- [ ] **Step 1: SVG-fontstrenger Inter Tight → Mulish (4 steder)**

Erstatt alle forekomster av:

```js
'font-family': 'Inter Tight, system-ui, sans-serif',
```

med:

```js
'font-family': 'Mulish, system-ui, sans-serif',
```

(Linje ~1871, ~1929, ~1939, ~1954 — bruk replace-all.)

- [ ] **Step 2: Måleannotasjoner — varseloransje `#e27500` erstatter `#c25a1f` (6 steder)**

I måleannotasjonskoden (linje ~1922–1955) erstattes alle seks `#c25a1f`-forekomstene — eksakt mønster `#c25a1f` → `#e27500`:

- Linje ~1924: `fill: A.loose ? '#e8c94a' : '#c25a1f'` → `fill: A.loose ? '#e8c94a' : '#e27500'` (`#e8c94a` beholdes!)
- Linje ~1928: tekst-`fill: '#c25a1f'` → `fill: '#e27500'`
- Linje ~1934: som ~1924
- Linje ~1938: som ~1928
- Linje ~1944: `stroke: '#c25a1f'` → `stroke: '#e27500'`
- Linje ~1952: rect-`fill: '#c25a1f'` → `fill: '#e27500'`

Enklest: replace-all `#c25a1f` → `#e27500` (verifiser etterpå at `#c25a1f` gir null treff i hele fila).

- [ ] **Step 3: Hover-pille på kartet — skifer i stedet for mørkegrønn**

I `makePillUrl(text)` (linje ~2045–2053), erstatt `fill="#1B5E20"` med `fill="#444f55"` (matcher map-tooltipens skiferflate; pillen er et hover-element, ikke semantisk grønt).

- [ ] **Step 4: Lengdeprofilens aksefarger følger nye teksttokens**

I `drawLp` (linje ~3155–3160), erstatt:

```js
const ink = isDark ? 'rgba(232,237,242,' : 'rgba(14,26,38,';
```

med:

```js
const ink = isDark ? 'rgba(236,236,236,' : 'rgba(68,79,85,';
```

(`const CC = '#e0228e';` rett ved skal IKKE endres — signal-rosa er fredet.)

- [ ] **Step 5: Verifiser**

Søk i fila: `Inter Tight`, `#c25a1f`, `#1B5E20` og `rgba(14,26,38,` skal alle gi null treff. I nettleser: åpne lengdeprofilen — aksetekst er skifergrå (lys) / lysgrå (mørk); mål noe i tverrprofilen — målelinjer/etiketter er varseloransje; hover over senterlinja — «PR …»-pillen er skifergrå.

- [ ] **Step 6: Commit**

```powershell
git add web/profilutforsker.html
git commit -m "feat(tema): JS-farger og SVG-fonter på Vegkart-palett (Mulish, varseloransje, skifer-pille)"
```

---

### Task 8: Manuell visuell verifisering

**Files:** ingen endringer forventet (kun fikser hvis noe avdekkes).

- [ ] **Step 1: Start lokal server**

```powershell
python -m http.server 8000 --directory web
```

Åpne `http://localhost:8000/profilutforsker.html` og logg inn/velg et prosjekt med BIM-data.

- [ ] **Step 2: Gå gjennom sjekklista fra spec-en**

- [ ] Lys modus: topbar skifer, kort hvite, oransje interaksjon, 2px hjørner
- [ ] Mørk modus (måneknapp): bakgrunn `#231f20`, kort `#353e43`, oransje fortsatt synlig, ingen «glemt» beige/navy-flate
- [ ] 2D ↔ 3D i begge temaer (3D arver tokens; R700-fargene i scenen uendret)
- [ ] Drawere: åpne/lukk tverrprofil (høyre) og lengdeprofil (bunn) i begge temaer; maksimer tverrprofil
- [ ] Lag-kort: kollaps/ekspander via chevron OG via map-tool-knappen; reload bevarer tilstand; pille-toggles slår lag av/på i kartet
- [ ] Lag-kort med BIM-gruppe synlig: intern scroll fungerer ved lav vindushøyde
- [ ] Snap-preview, legend (inkl. R700-rader uendret), map-info (nede til venstre), basemap-velger
- [ ] Målemodus i tverrprofil: oransje-tintet panel, varseloransje annotasjoner
- [ ] ArcGIS-flater (attribution, popup, zoom-widgets) skjærer ikke mot paletten
- [ ] SVG-tverrprofil i dark mode: invert-filteret ser fortsatt riktig ut

- [ ] **Step 3: Fiks eventuelle avvik og commit**

Småfikser commites som `fix(tema): <hva>`. Når alt er grønt:

```powershell
git log --oneline -8
```

Forventet: 6–7 `feat(tema)`-commits (+ ev. fikser) over `7d3a400`.
