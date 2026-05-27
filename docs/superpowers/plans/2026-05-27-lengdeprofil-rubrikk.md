# Lengdeprofil R700-rubrikk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Legg til R700-rubrikk med 5 informasjonsrader under lengdeprofilet i Profilutforsker, implementer 1:5-skala som default, og eksporter tverrfall/gradient til AGOL.

**Architecture:** Pipeline beregner `gradient_pct`, `cross_fall_l`, `cross_fall_r` per stasjon og eksporterer dem til AGOL via ArcPy. Profilutforsker henter de nye feltene fra AGOL FeatureLayer og tegner dem i en 5-rads Canvas-rubrikk under profilgrafen. Skalaen er 1:5 (50m/10m grid-celler) som default med toggle til auto-fit.

**Tech Stack:** Python 3.11 (pipeline.py, tverrprofil_to_agol.py), ArcPy, HTML5 Canvas (profilutforsker.html), ArcGIS JS 4.30

---

## File Map

| Fil | Endring |
|-----|---------|
| `src/ifc_processor/pipeline.py` | Legg til `gradient_pct`, `cross_fall_l`, `cross_fall_r` i `station_rows` |
| `src/arcpy_processor/tverrprofil_to_agol.py` | Legg til 3 DOUBLE-felt i feature class-skjema + InsertCursor |
| `web/profilutforsker.html` | CSS, HTML toolbar, state var, AGOL query, reskriv `drawLp()`, `selectStation()` |
| `tests/test_pipeline_stations_json.py` | Test at nye felt eksisterer i output |
| `tests/test_tverrprofil_to_agol.py` | Test at nye felt legges til feature class |

---

## Task 1: pipeline.py — legg til gradient_pct og tverrfall i stations.json

**Files:**
- Modify: `src/ifc_processor/pipeline.py:304-311`
- Test: `tests/test_pipeline_stations_json.py`

- [ ] **Step 1.1: Skriv en feiltestende test**

Åpne `tests/test_pipeline_stations_json.py`. Legg til denne testen **etter** `test_stations_json_keys_with_mocks`:

```python
def test_stations_json_rubric_fields(tmp_path):
    """gradient_pct, cross_fall_l, cross_fall_r skal finnes i stations.json."""
    from src.ifc_processor.normal_section import NormalSection
    fake_cs = CrossSection(station=0.0, elevation=100.0, segments={})
    fake_ns = NormalSection(
        left_carriageway_width=float("nan"),
        right_carriageway_width=float("nan"),
        left_shoulder_width=float("nan"),
        right_shoulder_width=float("nan"),
        left_cross_fall_pct=3.5,
        right_cross_fall_pct=-3.5,
        left_slope_ratio=float("nan"),
        right_slope_ratio=float("nan"),
        section_type="ukjent",
    )
    cl_path = _cl_geojson(tmp_path)
    fake_ifc = tmp_path / "fake.ifc"
    fake_ifc.write_text("")

    with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
         patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
         patch("src.ifc_processor.pipeline.compute_normal_section", return_value=fake_ns), \
         patch("src.ifc_processor.pipeline.render_cross_section_svg"), \
         patch("src.ifc_processor.pipeline.render_normal_section_svg"):
        result = run_pipeline(
            ifc_path=fake_ifc,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )

    stations = json.loads(Path(result["stations_json"]).read_text())
    assert len(stations) >= 2, "Trenger minst 2 stasjoner for å teste gradient"
    row0 = stations[0]
    for key in ("gradient_pct", "cross_fall_l", "cross_fall_r"):
        assert key in row0, f"Mangler felt: {key}"
    # gradient_pct på siste stasjon skal være None (ingen neste punkt)
    last_row = stations[-1]
    assert last_row["gradient_pct"] is None
    # cross_fall fra NormalSection mock
    assert row0["cross_fall_l"] == pytest.approx(3.5)
    assert row0["cross_fall_r"] == pytest.approx(-3.5)
```

- [ ] **Step 1.2: Kjør testen — verifiser at den feiler**

```
pytest tests/test_pipeline_stations_json.py::test_stations_json_rubric_fields -v
```

Forventet: `FAILED` med `KeyError: 'gradient_pct'` eller `AssertionError`.

- [ ] **Step 1.3: Implementer endringen i pipeline.py**

I `src/ifc_processor/pipeline.py`, finn blokken som bygger `station_rows` (rundt linje 303–320). Den ser slik ut:

```python
        z_moh = _z_from_profile(s.distance)
        station_rows.append({
            "station_m": round(s.distance, 3),
            "profil_nr": f"{s.distance:07.2f}",
            "x": round(float(s.position[0]), 3),
            "y": round(float(s.position[1]), 3),
            "z": round(z_moh if z_moh is not None else float(s.position[2]), 3),
            "z_terreng": round(terrain_z_ifc, 3) if terrain_z_ifc is not None else None,
        })
```

Erstatt den med:

```python
        z_moh = _z_from_profile(s.distance)
        _cf_l = ns.left_cross_fall_pct if ns is not None and not (isinstance(ns.left_cross_fall_pct, float) and ns.left_cross_fall_pct != ns.left_cross_fall_pct) else None
        _cf_r = ns.right_cross_fall_pct if ns is not None and not (isinstance(ns.right_cross_fall_pct, float) and ns.right_cross_fall_pct != ns.right_cross_fall_pct) else None
        station_rows.append({
            "station_m": round(s.distance, 3),
            "profil_nr": f"{s.distance:07.2f}",
            "x": round(float(s.position[0]), 3),
            "y": round(float(s.position[1]), 3),
            "z": round(z_moh if z_moh is not None else float(s.position[2]), 3),
            "z_terreng": round(terrain_z_ifc, 3) if terrain_z_ifc is not None else None,
            "gradient_pct": None,   # fylles ut i neste pass nedenfor
            "cross_fall_l": round(_cf_l, 3) if _cf_l is not None else None,
            "cross_fall_r": round(_cf_r, 3) if _cf_r is not None else None,
        })
```

Finn så der `stations_json_path.write_text(...)` kalles (rundt linje 326). Legg til gradient-beregningspasset **rett før** `stations_json_path.write_text`:

```python
    # Gradient-beregning: (z[i+1] - z[i]) / (station[i+1] - station[i]) * 100
    for i in range(len(station_rows) - 1):
        dz = station_rows[i + 1]["z"] - station_rows[i]["z"]
        ds = station_rows[i + 1]["station_m"] - station_rows[i]["station_m"]
        station_rows[i]["gradient_pct"] = round(dz / ds * 100, 2) if ds > 1e-6 else None
    # Siste stasjon har ingen neste — beholder None

    stations_json_path = output_dir / "stations.json"
    stations_json_path.write_text(json.dumps(station_rows, indent=2))
```

- [ ] **Step 1.4: Kjør testen — verifiser at den passerer**

```
pytest tests/test_pipeline_stations_json.py::test_stations_json_rubric_fields -v
```

Forventet: `PASSED`

- [ ] **Step 1.5: Kjør eksisterende tester — verifiser ingen regresjon**

```
pytest tests/test_pipeline_stations_json.py -v
```

Forventet: alle tester `PASSED`

- [ ] **Step 1.6: Commit**

```bash
git add src/ifc_processor/pipeline.py tests/test_pipeline_stations_json.py
git commit -m "feat: add gradient_pct, cross_fall_l/r to stations.json output"
```

---

## Task 2: tverrprofil_to_agol.py — legg til 3 felt i AGOL feature class

**Files:**
- Modify: `src/arcpy_processor/tverrprofil_to_agol.py:61-80`
- Test: `tests/test_tverrprofil_to_agol.py`

- [ ] **Step 2.1: Skriv feiltestende test**

Åpne `tests/test_tverrprofil_to_agol.py`. Finn `_stations_json`-hjelperfunksjonen rundt linje 26. Legg til en ny testfunksjon etter de eksisterende:

```python
def test_create_point_fc_adds_rubric_fields(tmp_path):
    """create_point_fc skal kalle AddField for gradient_pct, cross_fall_l, cross_fall_r."""
    import sys
    from unittest.mock import call
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.management.AddField.reset_mock()

    stations = [
        {"station_m": 0.0, "profil_nr": "0000.00", "x": 10.0, "y": 20.0, "z": 100.0,
         "gradient_pct": 1.5, "cross_fall_l": 3.5, "cross_fall_r": -3.5},
        {"station_m": 50.0, "profil_nr": "0050.00", "x": 60.0, "y": 20.0, "z": 100.75,
         "gradient_pct": None, "cross_fall_l": None, "cross_fall_r": None},
    ]

    with patch("src.arcpy_processor.tverrprofil_to_agol.Transformer") as mock_tf:
        mock_tf.from_crs.return_value.transform.side_effect = lambda x, y: (x, y)
        from src.arcpy_processor.tverrprofil_to_agol import create_point_fc
        create_point_fc(stations, str(tmp_path), "test")

    added_fields = [c.args[1] for c in arcpy_mock.management.AddField.call_args_list]
    assert "gradient_pct" in added_fields, "gradient_pct-felt mangler"
    assert "cross_fall_l" in added_fields, "cross_fall_l-felt mangler"
    assert "cross_fall_r" in added_fields, "cross_fall_r-felt mangler"
```

- [ ] **Step 2.2: Kjør testen — verifiser at den feiler**

```
pytest tests/test_tverrprofil_to_agol.py::test_create_point_fc_adds_rubric_fields -v
```

Forventet: `FAILED` — `gradient_pct` mangler i `added_fields`.

- [ ] **Step 2.3: Implementer skjema-endringen i tverrprofil_to_agol.py**

Åpne `src/arcpy_processor/tverrprofil_to_agol.py`. Finn disse linjene (rundt linje 61–80):

```python
    arcpy.management.AddField(fc_path, "stasjon_m", "DOUBLE")
    arcpy.management.AddField(fc_path, "profil_nr", "TEXT", field_length=20)
    arcpy.management.AddField(fc_path, "z_moh", "DOUBLE")
    arcpy.management.AddField(fc_path, "z_terreng", "DOUBLE")
    arcpy.management.AddField(fc_path, "svg_url", "TEXT", field_length=512)

    transformer = (
        ...
    )

    with arcpy.da.InsertCursor(fc_path, ["stasjon_m", "profil_nr", "z_moh", "z_terreng", "SHAPE@"]) as cur:
        for row in stations:
            x, y = row["x"], row["y"]
            if transformer is not None:
                x, y = transformer.transform(x, y)
            pt = arcpy.Point(x, y, row["z"])
            geom = arcpy.PointGeometry(pt, sr)
            cur.insertRow((row["station_m"], row["profil_nr"], row["z"], row.get("z_terreng"), geom))
```

Erstatt de to delene med:

```python
    arcpy.management.AddField(fc_path, "stasjon_m", "DOUBLE")
    arcpy.management.AddField(fc_path, "profil_nr", "TEXT", field_length=20)
    arcpy.management.AddField(fc_path, "z_moh", "DOUBLE")
    arcpy.management.AddField(fc_path, "z_terreng", "DOUBLE")
    arcpy.management.AddField(fc_path, "gradient_pct", "DOUBLE")
    arcpy.management.AddField(fc_path, "cross_fall_l", "DOUBLE")
    arcpy.management.AddField(fc_path, "cross_fall_r", "DOUBLE")
    arcpy.management.AddField(fc_path, "svg_url", "TEXT", field_length=512)
```

Og InsertCursor-blokken:

```python
    with arcpy.da.InsertCursor(
        fc_path,
        ["stasjon_m", "profil_nr", "z_moh", "z_terreng",
         "gradient_pct", "cross_fall_l", "cross_fall_r", "SHAPE@"],
    ) as cur:
        for row in stations:
            x, y = row["x"], row["y"]
            if transformer is not None:
                x, y = transformer.transform(x, y)
            pt = arcpy.Point(x, y, row["z"])
            geom = arcpy.PointGeometry(pt, sr)
            _nan_to_none = lambda v: None if v is None or (isinstance(v, float) and v != v) else v
            cur.insertRow((
                row["station_m"],
                row["profil_nr"],
                row["z"],
                row.get("z_terreng"),
                _nan_to_none(row.get("gradient_pct")),
                _nan_to_none(row.get("cross_fall_l")),
                _nan_to_none(row.get("cross_fall_r")),
                geom,
            ))
```

- [ ] **Step 2.4: Kjør testen — verifiser at den passerer**

```
pytest tests/test_tverrprofil_to_agol.py::test_create_point_fc_adds_rubric_fields -v
```

Forventet: `PASSED`

- [ ] **Step 2.5: Kjør alle tverrprofil_to_agol-tester**

```
pytest tests/test_tverrprofil_to_agol.py -v
```

Forventet: alle `PASSED`

- [ ] **Step 2.6: Commit**

```bash
git add src/arcpy_processor/tverrprofil_to_agol.py tests/test_tverrprofil_to_agol.py
git commit -m "feat: add gradient_pct, cross_fall_l/r fields to AGOL station feature class"
```

---

## Task 3: profilutforsker.html — CSS, HTML-struktur, state-variabel og AGOL-spørring

**Files:**
- Modify: `web/profilutforsker.html` (linje 48, 956–973, 1007, 1792, 1799–1807)

Ingen automatiserte tester for frontend — verifiseres visuelt i neste oppgave.

- [ ] **Step 3.1: Øk drawer-høyde (linje 48)**

Finn:
```css
  --drawer-bottom-h: 340px;
```

Erstatt med:
```css
  --drawer-bottom-h: 480px;
```

- [ ] **Step 3.2: Endre "Tilpass"-knapp-HTML (linje 956–959)**

Finn:
```html
          <button class="btn-mini" onclick="drawLp()">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1 1h8v8H1z" stroke="currentColor" stroke-width="1.2"/><path d="M3 3h4v4H3z" stroke="currentColor" stroke-width="1"/></svg>
            Tilpass
          </button>
```

Erstatt med:
```html
          <button class="btn-mini" id="btn-lp-scale" onclick="toggleLpScale()">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1 1h8v8H1z" stroke="currentColor" stroke-width="1.2"/><path d="M3 3h4v4H3z" stroke="currentColor" stroke-width="1"/></svg>
            Tilpass
          </button>
```

- [ ] **Step 3.3: Legg til gradient-felt i lp-toolbar (linje 973, etter lp-terreng-grp)**

Finn:
```html
        <div class="grp" id="lp-terreng-grp" style="display:none"><span class="lbl">Terreng</span><span class="val" id="lp-terreng-lbl">— m</span></div>
      </div>
```

Erstatt med:
```html
        <div class="grp" id="lp-terreng-grp" style="display:none"><span class="lbl">Terreng</span><span class="val" id="lp-terreng-lbl">— m</span></div>
        <div class="pipe" id="lp-gradient-pipe" style="display:none"></div>
        <div class="grp" id="lp-gradient-grp" style="display:none"><span class="lbl">Fall</span><span class="val" id="lp-gradient-lbl">— %</span></div>
      </div>
```

- [ ] **Step 3.4: Legg til lpScaleMode-tilstandsvariabel (linje 1007)**

Finn:
```javascript
let lpOpen = false;
```

Erstatt med:
```javascript
let lpOpen = false;
let lpScaleMode = '1:5';  // '1:5' | 'fit'
```

- [ ] **Step 3.5: Utvid AGOL outFields (linje 1792)**

Finn:
```javascript
      outFields: ['OBJECTID', 'stasjon_m', 'profil_nr', 'z_moh', 'z_terreng'],
```

Erstatt med:
```javascript
      outFields: ['OBJECTID', 'stasjon_m', 'profil_nr', 'z_moh', 'z_terreng',
                  'gradient_pct', 'cross_fall_l', 'cross_fall_r'],
```

- [ ] **Step 3.6: Utvid stations-array-mapping (linje 1799–1807)**

Finn:
```javascript
    stations = fset.features.map(f => ({
      oid: f.attributes.OBJECTID,
      stasjon_m: f.attributes.stasjon_m,
      profil_nr: f.attributes.profil_nr || '',
      z: f.attributes.z_moh ?? (f.geometry?.z ?? 0),
      z_terreng: f.attributes.z_terreng ?? null,
      x: f.geometry?.x ?? 0,
      y: f.geometry?.y ?? 0,
    }));
```

Erstatt med:
```javascript
    stations = fset.features.map(f => ({
      oid: f.attributes.OBJECTID,
      stasjon_m: f.attributes.stasjon_m,
      profil_nr: f.attributes.profil_nr || '',
      z: f.attributes.z_moh ?? (f.geometry?.z ?? 0),
      z_terreng: f.attributes.z_terreng ?? null,
      gradient_pct: f.attributes.gradient_pct ?? null,
      cross_fall_l: f.attributes.cross_fall_l ?? null,
      cross_fall_r: f.attributes.cross_fall_r ?? null,
      x: f.geometry?.x ?? 0,
      y: f.geometry?.y ?? 0,
    }));
```

- [ ] **Step 3.7: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: expand lp drawer, add rubric state vars and AGOL fields"
```

---

## Task 4: profilutforsker.html — reskriv drawLp() med 1:5-skala og rubrikk

**Files:**
- Modify: `web/profilutforsker.html:2358-2537` (hele `drawLp()`-funksjonen)

Ingen automatiserte tester — verifiseres visuelt ved å kjøre dev-serveren.

- [ ] **Step 4.1: Erstatt hele drawLp()-funksjonen**

Finn funksjonen som starter på linje 2358:
```javascript
function drawLp() {
  if (!stations.length) return;
  ...
```

og slutter etter `};` på linje 2537 (onclick-handleren). Erstatt **hele funksjonen** med:

```javascript
function drawLp() {
  if (!stations.length) return;
  const area = document.querySelector('.lp-area');
  const cnv = document.getElementById('lp-canvas');
  const W = area.clientWidth, H = area.clientHeight;
  if (!W || !H) return;
  cnv.width = W; cnv.height = H;
  const ctx = cnv.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  const isDark = document.documentElement.dataset.theme === 'dark';
  const gridColor   = isDark ? 'rgba(255,255,255,.04)' : 'rgba(6,41,72,.05)';
  const axisColor   = isDark ? 'rgba(255,255,255,.15)' : 'rgba(6,41,72,.15)';
  const labelColor  = isDark ? '#6a7682' : '#8a96a2';
  const lineColor   = '#1f8a4a';
  const fillColor   = isDark ? 'rgba(31,138,74,.08)' : 'rgba(31,138,74,.1)';
  const terrengColor = isDark ? '#9b7a2e' : '#8b5e1a';
  const cursorColor = '#e0228e';

  // Rubric layout constants
  const RUBRIC_ROW_H = 26;
  const N_RUBRIC_ROWS = 5;
  const RUBRIC_H = N_RUBRIC_ROWS * RUBRIC_ROW_H;
  const PAD = { t: 10, r: 18, b: 20, l: 70 };
  const iW = W - PAD.l - PAD.r;
  const profH = H - PAD.t - RUBRIC_H - PAD.b;
  const iH = profH;
  const rubricY0 = PAD.t + profH;

  const stMin = stations[0].stasjon_m;
  const stMax = stations[stations.length - 1].stasjon_m;
  const elevs = stations.map(s => s.z);
  const terrengElevs = stations.map(s => s.z_terreng).filter(z => z != null);
  const hasTerreng = terrengElevs.length > 0;
  const allElevs = [...elevs, ...terrengElevs];

  // 1:5 scale or auto-fit
  let elMin, elMax;
  if (lpScaleMode === '1:5') {
    const elRange  = (stMax - stMin) / 5;
    const elCenter = (Math.min(...elevs) + Math.max(...elevs)) / 2;
    elMin = elCenter - elRange / 2;
    elMax = elCenter + elRange / 2;
  } else {
    elMin = Math.min(...allElevs) - 2;
    elMax = Math.max(...allElevs) + 2;
  }

  const xOf = st => PAD.l + ((st - stMin) / (stMax - stMin)) * iW;
  const yOf = el => PAD.t + iH - ((el - elMin) / (elMax - elMin)) * iH;

  // Grid Y — 10m fixed (R700 1:5)
  ctx.strokeStyle = gridColor; ctx.lineWidth = 1;
  ctx.fillStyle = labelColor;
  ctx.font = '10px "JetBrains Mono", monospace'; ctx.textAlign = 'right';
  for (let el = Math.ceil(elMin / 10) * 10; el <= elMax; el += 10) {
    const y = yOf(el);
    if (y < PAD.t - 1 || y > PAD.t + iH + 1) continue;
    ctx.beginPath(); ctx.moveTo(PAD.l, y); ctx.lineTo(W - PAD.r, y); ctx.stroke();
    ctx.fillText(el.toFixed(0), PAD.l - 5, y + 3.5);
  }

  // Grid X — 50m fixed (R700 1:5)
  ctx.textAlign = 'center';
  for (let st = Math.ceil(stMin / 50) * 50; st <= stMax; st += 50) {
    const x = xOf(st);
    ctx.beginPath(); ctx.moveTo(x, PAD.t); ctx.lineTo(x, rubricY0); ctx.stroke();
    // x-axis label below rubric
    ctx.fillText(st.toFixed(0), x, H - PAD.b + 14);
  }

  // Axes (profile area only)
  ctx.strokeStyle = axisColor; ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(PAD.l, PAD.t);
  ctx.lineTo(PAD.l, rubricY0);
  ctx.lineTo(W - PAD.r, rubricY0);
  ctx.stroke();

  // Y axis label
  ctx.save();
  ctx.translate(13, PAD.t + iH / 2); ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = labelColor; ctx.font = '10px "Inter Tight", sans-serif';
  ctx.textAlign = 'center'; ctx.fillText('H.o.h. (m)', 0, 0);
  ctx.restore();

  // Terrain line (dashed, below design)
  if (hasTerreng) {
    ctx.save(); ctx.setLineDash([6, 4]);
    ctx.strokeStyle = terrengColor; ctx.lineWidth = 1.0;
    ctx.beginPath();
    let started = false;
    for (const s of stations) {
      if (s.z_terreng == null) { started = false; continue; }
      const x = xOf(s.stasjon_m), y = yOf(s.z_terreng);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke(); ctx.restore();
  }

  // Fill under design profile
  ctx.beginPath();
  ctx.moveTo(xOf(stMin), rubricY0);
  for (const s of stations) ctx.lineTo(xOf(s.stasjon_m), yOf(s.z));
  ctx.lineTo(xOf(stMax), rubricY0);
  ctx.closePath();
  ctx.fillStyle = fillColor; ctx.fill();

  // Design profile line (solid heavy — R700)
  ctx.beginPath(); ctx.strokeStyle = lineColor; ctx.lineWidth = 2.0;
  stations.forEach((s, i) => {
    if (i === 0) ctx.moveTo(xOf(s.stasjon_m), yOf(s.z));
    else ctx.lineTo(xOf(s.stasjon_m), yOf(s.z));
  });
  ctx.stroke();

  // Profile height labels at 100m
  ctx.fillStyle = lineColor;
  ctx.font = 'bold 9px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
  for (let st = Math.ceil(stMin / 100) * 100; st <= stMax; st += 100) {
    const s = stations.reduce((a, b) =>
      Math.abs(b.stasjon_m - st) < Math.abs(a.stasjon_m - st) ? b : a);
    const x = xOf(s.stasjon_m), y = yOf(s.z);
    if (y > PAD.t + 5) ctx.fillText(s.z.toFixed(1), x, y - 5);
  }

  // Terrain height labels at 100m
  if (hasTerreng) {
    ctx.fillStyle = terrengColor;
    ctx.font = '8px "JetBrains Mono", monospace'; ctx.textAlign = 'center';
    for (let st = Math.ceil(stMin / 100) * 100; st <= stMax; st += 100) {
      const s = stations.reduce((a, b) =>
        Math.abs(b.stasjon_m - st) < Math.abs(a.stasjon_m - st) ? b : a);
      if (s.z_terreng == null) continue;
      const x = xOf(s.stasjon_m), y = yOf(s.z_terreng);
      if (y > PAD.t + 5) ctx.fillText(s.z_terreng.toFixed(1), x, y + 12);
    }
  }

  // Legend (upper right)
  const legX = W - PAD.r - 4, legY = PAD.t + 10;
  ctx.font = '9px "Inter Tight", sans-serif'; ctx.textAlign = 'right';
  ctx.strokeStyle = lineColor; ctx.lineWidth = 2.0; ctx.setLineDash([]);
  ctx.beginPath(); ctx.moveTo(legX - 28, legY); ctx.lineTo(legX - 8, legY); ctx.stroke();
  ctx.fillStyle = lineColor; ctx.fillText('Prosjektert profil', legX - 32, legY + 3.5);
  if (hasTerreng) {
    ctx.strokeStyle = terrengColor; ctx.lineWidth = 1.0; ctx.setLineDash([6, 4]);
    ctx.beginPath(); ctx.moveTo(legX - 28, legY + 14); ctx.lineTo(legX - 8, legY + 14); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = terrengColor; ctx.fillText('Eksisterende terreng', legX - 32, legY + 17.5);
  }
  ctx.setLineDash([]);

  // Station ticks (pink dots at rubric boundary)
  ctx.strokeStyle = 'rgba(224,34,142,.25)'; ctx.lineWidth = 1;
  for (const s of stations) {
    const x = xOf(s.stasjon_m);
    ctx.beginPath(); ctx.moveTo(x, rubricY0 - 1); ctx.lineTo(x, rubricY0 + 3); ctx.stroke();
  }

  // ── RUBRIC ──────────────────────────────────────────────────────────
  const ROWS = [
    { label: 'Terrenghøyde', key: 'terrain'   },
    { label: 'Profilhøyde',  key: 'design'    },
    { label: 'Tverrfall',    key: 'crossfall' },
    { label: 'Hor.kurv.',    key: 'curvature' },
    { label: 'Profil nr.',   key: 'profnr'    },
  ];

  // Left border of rubric block
  ctx.strokeStyle = axisColor; ctx.lineWidth = 0.7;
  ctx.beginPath();
  ctx.moveTo(PAD.l, rubricY0); ctx.lineTo(PAD.l, H - PAD.b);
  ctx.stroke();

  ctx.font = '8.5px "Inter Tight", sans-serif';

  for (let i = 0; i < N_RUBRIC_ROWS; i++) {
    const rowY    = rubricY0 + (N_RUBRIC_ROWS - 1 - i) * RUBRIC_ROW_H;
    const rowMidY = rowY + RUBRIC_ROW_H / 2;
    const rowBotY = rowY + RUBRIC_ROW_H;

    // Row separator
    ctx.strokeStyle = axisColor; ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(PAD.l, rowBotY); ctx.lineTo(W - PAD.r, rowBotY); ctx.stroke();

    // Row label
    ctx.fillStyle = labelColor; ctx.textAlign = 'right';
    ctx.fillText(ROWS[i].label, PAD.l - 4, rowMidY + 3);

    const key = ROWS[i].key;

    if (key === 'profnr') {
      // 100m vertical dividers + profile numbers
      for (let st = Math.ceil(stMin / 100) * 100; st <= stMax; st += 100) {
        const x = xOf(st);
        ctx.strokeStyle = axisColor; ctx.lineWidth = 0.3;
        ctx.beginPath(); ctx.moveTo(x, rubricY0); ctx.lineTo(x, H - PAD.b); ctx.stroke();
        ctx.fillStyle = isDark ? '#e0e6ec' : '#1a2a36';
        ctx.textAlign = 'center';
        ctx.font = 'bold 8.5px "JetBrains Mono", monospace';
        ctx.fillText(st.toFixed(0), x, rowMidY + 3);
        ctx.font = '8.5px "Inter Tight", sans-serif';
      }

    } else if (key === 'design') {
      ctx.textAlign = 'center';
      ctx.font = '8px "JetBrains Mono", monospace';
      ctx.fillStyle = lineColor;
      for (let st = Math.ceil(stMin / 100) * 100; st <= stMax; st += 100) {
        const s = stations.reduce((a, b) =>
          Math.abs(b.stasjon_m - st) < Math.abs(a.stasjon_m - st) ? b : a);
        ctx.fillText(s.z.toFixed(1), xOf(st), rowMidY + 3);
      }
      ctx.font = '8.5px "Inter Tight", sans-serif';

    } else if (key === 'terrain') {
      const hasT = stations.some(s => s.z_terreng != null);
      if (hasT) {
        ctx.textAlign = 'center'; ctx.font = '8px "JetBrains Mono", monospace';
        ctx.fillStyle = terrengColor;
        for (let st = Math.ceil(stMin / 100) * 100; st <= stMax; st += 100) {
          const s = stations.reduce((a, b) =>
            Math.abs(b.stasjon_m - st) < Math.abs(a.stasjon_m - st) ? b : a);
          if (s.z_terreng != null) ctx.fillText(s.z_terreng.toFixed(1), xOf(st), rowMidY + 3);
        }
        ctx.font = '8.5px "Inter Tight", sans-serif';
      } else {
        ctx.fillStyle = labelColor; ctx.textAlign = 'center';
        ctx.font = 'italic 8px "Inter Tight", sans-serif';
        ctx.fillText('(ikke tilgjengelig)', (PAD.l + W - PAD.r) / 2, rowMidY + 3);
        ctx.font = '8.5px "Inter Tight", sans-serif';
      }

    } else if (key === 'crossfall') {
      const hasL = stations.some(s => s.cross_fall_l != null);
      const hasR = stations.some(s => s.cross_fall_r != null);
      if (hasL || hasR) {
        const midY = rowMidY;
        const maxCf = Math.max(...stations.map(s =>
          Math.max(Math.abs(s.cross_fall_l ?? 0), Math.abs(s.cross_fall_r ?? 0))), 2);
        const cfScale = (RUBRIC_ROW_H * 0.35) / maxCf;
        // Horizontal center reference line
        ctx.strokeStyle = axisColor; ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(PAD.l, midY); ctx.lineTo(W - PAD.r, midY); ctx.stroke();
        // Left CF (green)
        if (hasL) {
          ctx.save(); ctx.strokeStyle = lineColor; ctx.lineWidth = 1.2;
          ctx.beginPath(); let moved = false;
          for (const s of stations) {
            if (s.cross_fall_l == null) { moved = false; continue; }
            const x = xOf(s.stasjon_m), y = midY - s.cross_fall_l * cfScale;
            if (!moved) { ctx.moveTo(x, y); moved = true; } else ctx.lineTo(x, y);
          }
          ctx.stroke(); ctx.restore();
        }
        // Right CF (amber)
        if (hasR) {
          ctx.save(); ctx.strokeStyle = terrengColor; ctx.lineWidth = 1.2;
          ctx.beginPath(); let moved = false;
          for (const s of stations) {
            if (s.cross_fall_r == null) { moved = false; continue; }
            const x = xOf(s.stasjon_m), y = midY - s.cross_fall_r * cfScale;
            if (!moved) { ctx.moveTo(x, y); moved = true; } else ctx.lineTo(x, y);
          }
          ctx.stroke(); ctx.restore();
        }
      } else {
        ctx.fillStyle = labelColor; ctx.textAlign = 'center';
        ctx.font = 'italic 8px "Inter Tight", sans-serif';
        ctx.fillText('(tverrfalldata mangler)', (PAD.l + W - PAD.r) / 2, rowMidY + 3);
        ctx.font = '8.5px "Inter Tight", sans-serif';
      }

    } else if (key === 'curvature') {
      ctx.fillStyle = labelColor; ctx.textAlign = 'center';
      ctx.font = 'italic 8px "Inter Tight", sans-serif';
      ctx.fillText('(kurvatur fra LandXML — kommer)', (PAD.l + W - PAD.r) / 2, rowMidY + 3);
      ctx.font = '8.5px "Inter Tight", sans-serif';
    }
  }

  // Cursor — full height from profile top through rubric
  if (currentIdx >= 0 && currentIdx < stations.length) {
    const s = stations[currentIdx];
    const x = xOf(s.stasjon_m), y = yOf(s.z);
    ctx.strokeStyle = cursorColor; ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, PAD.t); ctx.lineTo(x, H - PAD.b); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = cursorColor;
    ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(224,34,142,.2)';
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill();
    if (s.z_terreng != null) {
      const yt = yOf(s.z_terreng);
      ctx.fillStyle = terrengColor;
      ctx.beginPath(); ctx.arc(x, yt, 3.5, 0, Math.PI * 2); ctx.fill();
    }
  }

  // Click handler
  cnv.onclick = e => {
    const rect = cnv.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    let best = 0, bestD = Infinity;
    for (let i = 0; i < stations.length; i++) {
      const d = Math.abs(xOf(stations[i].stasjon_m) - mx);
      if (d < bestD) { bestD = d; best = i; }
    }
    selectStation(best);
  };
}
```

- [ ] **Step 4.2: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: rewrite drawLp() with 1:5 scale and R700 rubric rows"
```

---

## Task 5: profilutforsker.html — scale toggle og gradient i toolbar

**Files:**
- Modify: `web/profilutforsker.html` (etter `toggleLp()`-funksjonen og `selectStation()`-funksjonen)

- [ ] **Step 5.1: Legg til toggleLpScale()-funksjon**

Finn `toggleLp()`-funksjonen (rundt linje 2348):
```javascript
function toggleLp() {
  lpOpen = !lpOpen;
  ...
}
```

Legg til `toggleLpScale` rett **etter** `toggleLp`:

```javascript
function toggleLpScale() {
  lpScaleMode = lpScaleMode === '1:5' ? 'fit' : '1:5';
  const btn = document.getElementById('btn-lp-scale');
  if (btn) btn.lastChild.textContent = lpScaleMode === '1:5' ? ' Tilpass' : ' 1:5 skala';
  if (lpOpen) drawLp();
}
```

- [ ] **Step 5.2: Oppdater selectStation() med gradient-visning**

Finn i `selectStation()`-funksjonen (rundt linje 1980–1984):
```javascript
  document.getElementById('lp-terreng-pipe').style.display = hasTerreng ? '' : 'none';
  document.getElementById('lp-terreng-grp').style.display = hasTerreng ? '' : 'none';
  if (hasTerreng) document.getElementById('lp-terreng-lbl').textContent = s.z_terreng.toFixed(1) + ' m';
```

Erstatt med:
```javascript
  document.getElementById('lp-terreng-pipe').style.display = hasTerreng ? '' : 'none';
  document.getElementById('lp-terreng-grp').style.display = hasTerreng ? '' : 'none';
  if (hasTerreng) document.getElementById('lp-terreng-lbl').textContent = s.z_terreng.toFixed(1) + ' m';
  const hasGrad = s.gradient_pct != null;
  document.getElementById('lp-gradient-pipe').style.display = hasGrad ? '' : 'none';
  document.getElementById('lp-gradient-grp').style.display = hasGrad ? '' : 'none';
  if (hasGrad) document.getElementById('lp-gradient-lbl').textContent =
    (s.gradient_pct >= 0 ? '+' : '') + s.gradient_pct.toFixed(1) + ' %';
```

- [ ] **Step 5.3: Legg til toggleLpScale i window-eksporten**

Finn (rundt linje 2583):
```javascript
  toggleTheme, toggleLp, openCs, closeCs, toggleCsMax,
```

Erstatt med:
```javascript
  toggleTheme, toggleLp, toggleLpScale, openCs, closeCs, toggleCsMax,
```

- [ ] **Step 5.4: Kjør dev-serveren og verifiser visuelt**

```bash
cd web && python -m http.server 3000
```

Åpne `http://localhost:3000/profilutforsker.html` i nettleseren.

Sjekkliste:
- [ ] Drawer åpner seg (480px høyde — høyere enn før)
- [ ] Rubrikk-blokk vises under profilgrafen med 5 rader
- [ ] Rad-etiketter (`Profil nr.`, `Hor.kurv.`, `Tverrfall`, `Profilhøyde`, `Terrenghøyde`) vises til venstre
- [ ] Grid bruker 50m-intervaller horisontalt, 10m vertikalt
- [ ] `Tilpass`-knapp endrer seg til `1:5 skala` og tilbake
- [ ] Cursor-linje strekker seg gjennom rubrikken
- [ ] (Med faktiske data) Profilhøyde-rad viser tall ved 100m-intervaller

Merk: For å teste med faktiske AGOL-data må en jobb kjøres med ny pipeline-kode. Med eldre jobber vises placeholders i tverrfall-raden.

- [ ] **Step 5.5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: add scale toggle, gradient toolbar display, expose toggleLpScale"
```

---

## Spec Coverage Check

| Krav fra spec | Implementert i |
|---|---|
| `gradient_pct` i stations.json | Task 1 |
| `cross_fall_l`/`cross_fall_r` i stations.json | Task 1 |
| 3 nye DOUBLE-felt i AGOL feature class | Task 2 |
| CSS `--drawer-bottom-h: 480px` | Task 3 |
| AGOL outFields utvidet | Task 3 |
| `lpScaleMode`-tilstand | Task 3 |
| `toggleLpScale()`-funksjon | Task 5 |
| `drawLp()` med 1:5-skala (50m/10m grid) | Task 4 |
| Rubrikk 5 rader | Task 4 |
| Rad: Profil nr. (hvert 100m) | Task 4 |
| Rad: Profilhøyde (hvert 100m) | Task 4 |
| Rad: Terrenghøyde (hvert 100m, placeholder hvis mangler) | Task 4 |
| Rad: Tverrfall (step-diagram) | Task 4 |
| Rad: Hor. kurvatur (placeholder) | Task 4 |
| Cursor gjennom rubrikk | Task 4 |
| Gradient i toolbar ved stasjonsvalg | Task 5 |
| Bakoverkompatibilitet (null-verdier → placeholder-tekst) | Task 4 (hasT/hasL/hasR-sjekker) |
