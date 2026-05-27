# Lengdeprofil med R700-rubrikk — Design Spec

**Dato:** 2026-05-27  
**Status:** Godkjent

## Bakgrunn

SVV-møte 2026-05-27: Statens vegvesen ønsker at lengdeprofilet skal vise et informasjonsbånd (rubrikk) under selve profilplottet i tråd med håndbok R700. Båndet skal inkludere profilnummer, horisontalkurvatur, tverrfall, profilhøyde og terrenghøyde. Skalaen skal være 1:5 (50 m celler horisontalt, 10 m celler vertikalt) som default.

## Scope

### I scope
- Legg til `gradient_pct`, `cross_fall_l`, `cross_fall_r` i `stations.json` og AGOL-skjema
- Tegn R700-rubrikk (5 rader) under profilgrafen i `drawLp()` Canvas-renderer
- Implement 1:5-skala som default (toggle til auto-fit)
- Utvid bunndrawer til 480px

### Ut av scope
- Horisontalkurvatur fra LandXML (vent på Quadri-fileksempel)
- Breddeutvidelse
- Backend SVG-forbedringer

## Arkitektur

```
pipeline.py          → beregner gradient_pct, cross_fall_l/r
tverrprofil_to_agol.py → skriver til AGOL FeatureClass (3 nye DOUBLE-felt)
profilutforsker.html → leser fra AGOL (outFields), tegner rubrikk i Canvas
```

## Komponent-design

### 1. Backend: `src/ifc_processor/pipeline.py`

Legg til i `station_rows`-dictionaryen per stasjon:

```python
"gradient_pct": float  # longitudinalt fall i %, NaN for siste stasjon
"cross_fall_l": float  # venstre tverrfall (%), NaN hvis ukjent
"cross_fall_r": float  # høyre tverrfall (%), NaN hvis ukjent
```

Gradient-beregning:
```python
gradient_pct = (z[i+1] - z[i]) / (station[i+1] - station[i]) * 100
# Siste stasjon: float("nan")
```

`cross_fall_l`/`cross_fall_r`: hentes fra `ns.left_cross_fall_pct` og `ns.right_cross_fall_pct` allerede beregnet i `compute_normal_section(cs)`. Eksisterer allerede i `lp_cross_falls`-listen — bare eksponer i `station_rows`.

Backward compatibility: eksisterende kode leser ikke disse feltene, ingen breaking change.

### 2. Backend: `src/arcpy_processor/tverrprofil_to_agol.py`

Legg til 3 DOUBLE-felt i `_create_station_fc()`:
```python
arcpy.management.AddField(fc_path, "gradient_pct", "DOUBLE")
arcpy.management.AddField(fc_path, "cross_fall_l", "DOUBLE")
arcpy.management.AddField(fc_path, "cross_fall_r", "DOUBLE")
```

Oppdater `InsertCursor`-feltlisten og `insertRow`-kallet tilsvarende.

Nullable-håndtering: `None` for NaN-verdier (AGOL lagrer `null` i DOUBLE).

### 3. Frontend: `web/profilutforsker.html`

#### 3a. CSS

```css
--drawer-bottom-h: 480px;  /* var fra 340px */
```

#### 3b. AGOL-query (outFields)

Legg til de 3 nye feltene i `outFields`-listen:
```javascript
outFields: ['OBJECTID', 'stasjon_m', 'profil_nr', 'z_moh', 'z_terreng',
            'gradient_pct', 'cross_fall_l', 'cross_fall_r'],
```

Oppdater stations-array-mapping:
```javascript
gradient_pct: f.attributes.gradient_pct ?? null,
cross_fall_l: f.attributes.cross_fall_l ?? null,
cross_fall_r: f.attributes.cross_fall_r ?? null,
```

#### 3c. `drawLp()` — canvas-layout

Konstanter (legg til øverst i funksjonen):
```javascript
const RUBRIC_ROW_H = 26;    // px per rad
const N_RUBRIC_ROWS = 5;
const RUBRIC_H = N_RUBRIC_ROWS * RUBRIC_ROW_H;  // 130px
const PAD = { t: 10, r: 18, b: 20, l: 70 };     // l økt fra 50→70 for rad-etiketter
const profH = H - PAD.t - RUBRIC_H - PAD.b;     // profilgraf-høyde
const rubricY0 = PAD.t + profH;                  // y-start for rubrikk-seksjonen
```

Rad-definisjon (bottom-to-top, rad 0 = bunn):
```javascript
const ROWS = [
  { label: 'Terrenghøyde', key: 'terrain' },
  { label: 'Profilhøyde',  key: 'design'  },
  { label: 'Tverrfall',    key: 'crossfall'},
  { label: 'Hor.kurv.',    key: 'curvature'},
  { label: 'Profil nr.',   key: 'profnr'  },
];
```

**1:5-skala:**

Legg til tilstandsvariabel:
```javascript
let lpScaleMode = '1:5';  // '1:5' eller 'fit'
```

I `drawLp()` — Y-range-beregning:
```javascript
if (lpScaleMode === '1:5') {
  const elRange = (stMax - stMin) / 5;
  const elCenter = (Math.min(...elevs) + Math.max(...elevs)) / 2;
  elMin = elCenter - elRange / 2;
  elMax = elCenter + elRange / 2;
} else {
  elMin = Math.min(...allElevs) - 2;
  elMax = Math.max(...allElevs) + 2;
}
```

Grid X: 50 m-intervaller (alltid, uavhengig av skala-modus).  
Grid Y: 10 m-intervaller (alltid).

"Tilpass"-knapp endres til å toggle mellom `'1:5'` og `'fit'`:
```javascript
function toggleLpScale() {
  lpScaleMode = lpScaleMode === '1:5' ? 'fit' : '1:5';
  drawLp();
}
```

HTML: endre `onclick="drawLp()"` til `onclick="toggleLpScale()"`. Knapp-tekst oppdateres dynamisk: viser `"Tilpass"` når modus er `'1:5'` (klikk bytter til auto-fit), viser `"1:5 skala"` når modus er `'fit'` (klikk bytter tilbake til 1:5).

**Rubrikk-tegning** (ny blokk etter profilgraf):

Skillelinje mellom profil og rubrikk:
```javascript
ctx.strokeStyle = axisColor; ctx.lineWidth = 1;
ctx.beginPath();
ctx.moveTo(PAD.l, rubricY0); ctx.lineTo(W - PAD.r, rubricY0);
ctx.stroke();
```

For hver rad `i` (0 = bunn, 4 = topp):
```javascript
const rowY = rubricY0 + (N_RUBRIC_ROWS - 1 - i) * RUBRIC_ROW_H;
const rowMidY = rowY + RUBRIC_ROW_H / 2;
// Rad-separatlinje
ctx.beginPath(); ctx.moveTo(PAD.l, rowY + RUBRIC_ROW_H);
ctx.lineTo(W - PAD.r, rowY + RUBRIC_ROW_H); ctx.stroke();
// Rad-etikett
ctx.fillText(ROWS[i].label, PAD.l - 6, rowMidY + 3.5);
```

Rad-innhold per type:
- **Profil nr.** — tall ved 100m-intervaller:
  ```javascript
  ctx.fillText(st.toFixed(0), xOf(st), rowMidY + 3.5);
  ```
- **Profilhøyde** — tall (z_moh) ved 100m-intervaller
- **Terrenghøyde** — tall (z_terreng) ved 100m-intervaller; grå `"(ikke tilgjengelig)"` hvis alle null
- **Tverrfall** — step-diagram venstre og høyre ± (%):
  - Midtlinje horisontalt
  - Enkel steg-kurve for L og R; farge: grønn/rød for pos/neg
  - `null`-verdier vises som grå `"(tverrfalldata mangler)"`
- **Hor. kurvatur** — grå tekst `"(kurvatur fra LandXML — kommer)"` sentrert i raden

**Cursor-linje i rubrikk:**

Forleng eksisterende cursor `axvline` til å gå fra `PAD.t` ned til `H - PAD.b` (dekker nå både profil og rubrikk allerede — men sjekk at `lineTo(x, H - PAD.b)` faktisk er justert).

#### 3d. `updateLpRight()` — toolbar-oppdatering

Legg til vising av gradient ved valgt stasjon:
```javascript
const grad = s.gradient_pct;
document.getElementById('lp-gradient-lbl').textContent =
  grad != null ? (grad >= 0 ? '+' : '') + grad.toFixed(1) + ' %' : '—';
```

Legg til HTML-elementet i `.lp-toolbar`:
```html
<div class="pipe"></div>
<div class="grp">
  <span class="lbl">Fall</span>
  <span class="val" id="lp-gradient-lbl">— %</span>
</div>
```

## Bakoverkompatibilitet

Eksisterende AGOL-lag (fra tidligere jobber) har ikke `gradient_pct`, `cross_fall_l`, `cross_fall_r`. Frontend tolker disse som `null` og viser placeholder-tekst i rubrikk-radene. Ingen breaking change.

## Test-scenarioer

1. Ny jobb prosesseres → AGOL-lag har alle 8 felt → rubrikk viser reelle tverrfall- og høydetall
2. Gammel jobb lastes → rubrikk viser "—" / placeholder-tekst for manglende felt
3. Vei uten terrengdata → terrenghøyde-rad viser "(ikke tilgjengelig)" i grått
4. 1:5-knapp klikkes → vertikal rekkevidde endres, grid-linjer ved 10m-intervaller vises
5. Cursor flyttes → kolonne i rubrikk-rader oppdateres simultant med cursor i profil

## Avhengigheter og åpne spørsmål

- **LandXML horisontalkurvatur**: Vent på konkret Quadri-eksportfil fra SVV. Når data er tilgjengelig: legg til `curve_radius` og `curve_dir` i AGOL-skjema og rubrikk-rad.
- **Breddeutvidelse**: Ikke i scope. Legg til som separat oppgave etter LandXML-analyse.
- **AGOL-lag for eksisterende jobber**: Ingen migrasjon av historiske lag — de vises med placeholders.
