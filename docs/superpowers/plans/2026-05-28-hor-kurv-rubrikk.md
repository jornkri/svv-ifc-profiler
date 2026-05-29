# Hor.kurv.-rubrikk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tegne en R700-konform Hor.kurv.-rad i lengdeprofilets rubrikkblokk basert på reell horisontal kurvatur (Line/Curve/Spiral) parsed ut fra opplastet LandXML.

**Architecture:** Backend-utvidelse av `landxml_parser.py` ekstraherer `<Alignment>/<CoordGeom>`-segmenter (Line, Curve, Spiral) som strukturerte dicter. `job_runner.py` skriver dette til `horizontal_alignment.json` i job-output. En ny FastAPI-endpoint serverer JSON-filen til frontend. `drawLp()` i `profilutforsker.html` henter dataene og tegner ribbon-diagrammet (lang-stiplet senterlinje + utslag for buer + diagonal for klotoider + KP-streker), portet fra `explorer-profiles.jsx`-prototypen.

**Tech Stack:** Python 3.11 (landxml_parser.py, job_runner.py, server.py), FastAPI, vanilla JS / SVG (profilutforsker.html)

---

## File Map

| Fil | Endring |
|-----|---------|
| `src/arcpy_processor/landxml_parser.py` | Ny funksjon `parse_horizontal_alignment(path)` |
| `tests/test_landxml_parser.py` | Tester for ny funksjon |
| `src/api/job_runner.py` | Skriv `horizontal_alignment.json` til output-dir |
| `tests/test_api_jobs.py` | Test at endpoint serverer JSON |
| `src/api/server.py` | Ny endpoint `/api/jobs/{job_id}/horizontal-alignment` |
| `web/profilutforsker.html` | Hent JSON i `loadJob()`, tegn ribbon i `drawLp()` |

---

## Task 1: landxml_parser.py — `parse_horizontal_alignment()` extraherer Line/Curve/Spiral

**Files:**
- Modify: `src/arcpy_processor/landxml_parser.py` (legg til ny funksjon på slutten)
- Test: `tests/test_landxml_parser.py`

Bakgrunn: `<Alignment>/<CoordGeom>` (Quadri/Novapoint-format) inneholder rekkefølge av:
- `<Line dir="..." staStart="..." length="...">` — rett strekning
- `<Curve radius="..." rot="cw|ccw" staStart="..." length="...">` — sirkulær bue
- `<Spiral length="..." radiusStart="..." radiusEnd="..." spiType="clothoid" rot="cw|ccw" staStart="...">` — klotoide

Resultat: liste med segment-dicter i station-rekkefølge:
```python
{"kind": "line",  "sta_start": 12.77, "sta_end": 57.54}
{"kind": "curve", "sta_start": 57.54, "sta_end": 86.57, "radius": 25.0, "dir": +1}
{"kind": "spiral","sta_start": 86.57, "sta_end": 92.48, "A": 79.06, "dir": -1}
```
Konvensjon for `dir`: `+1 = ccw (venstrekurve)`, `-1 = cw (høyrekurve)` — matcher LandXML `rot`-attributtet. For klotoider beregnes `A = sqrt(L * R)` der `R` er ikke-uendelig endepunkt (`radiusStart` eller `radiusEnd`).

Hvis ingen `<Alignment>` finnes (f.eks. PlanFeature-bare filer som FV229), returner tom liste.

- [ ] **Step 1.1: Skriv en feilende test for Curve + Line ekstraksjon**

I `tests/test_landxml_parser.py`, legg til **etter** eksisterende tester:

```python
from src.arcpy_processor.landxml_parser import parse_horizontal_alignment


SAMPLE_ALIGNMENT = Path(__file__).parent.parent / "samples" / "m_f_veg_70400_aligment.xml"


def test_parses_curve_line_segments_from_alignment():
    """parse_horizontal_alignment skal lese ut Curve+Line-segmenter fra Quadri-format."""
    segments = parse_horizontal_alignment(SAMPLE_ALIGNMENT)
    # Sample har: Curve, Line, Curve, Line, Curve, Line = 6 segmenter
    assert len(segments) == 6

    # Første Curve: radius=50, rot=cw (høyrekurve), staStart=0
    s0 = segments[0]
    assert s0["kind"] == "curve"
    assert s0["sta_start"] == pytest.approx(0.0)
    assert s0["sta_end"] == pytest.approx(12.768460)
    assert s0["radius"] == pytest.approx(50.0)
    assert s0["dir"] == -1  # cw = høyre

    # Andre segment: Line
    s1 = segments[1]
    assert s1["kind"] == "line"
    assert s1["sta_start"] == pytest.approx(12.768460)
    assert s1["sta_end"] == pytest.approx(57.540816)
    assert "radius" not in s1

    # Tredje: Curve venstre (rot=ccw → dir=+1)
    s2 = segments[2]
    assert s2["kind"] == "curve"
    assert s2["radius"] == pytest.approx(25.0)
    assert s2["dir"] == +1


def test_returns_empty_for_planfeature_only_file():
    """FV229_Senterlinje.xml har bare PlanFeatures, ingen Alignment — skal returnere []."""
    segments = parse_horizontal_alignment(SAMPLE)
    assert segments == []
```

- [ ] **Step 1.2: Kjør testen — verifiser at den feiler**

```
pytest tests/test_landxml_parser.py::test_parses_curve_line_segments_from_alignment -v
```

Forventet: `FAILED` med `ImportError: cannot import name 'parse_horizontal_alignment'`.

- [ ] **Step 1.3: Implementer `parse_horizontal_alignment()`**

I `src/arcpy_processor/landxml_parser.py`, legg til på slutten av filen:

```python
def parse_horizontal_alignment(path: Path) -> list[dict]:
    """Ekstraherer horisontal kurvatur-segmenter fra <Alignment>/<CoordGeom>.

    Returnerer ordnet liste med segment-dicter i station-rekkefølge.
    Segment-keys:
        kind:      'line' | 'curve' | 'spiral'
        sta_start: float (stasjon ved segmentstart, meter)
        sta_end:   float (stasjon ved segmentslutt, meter)
        radius:    float (kun for 'curve')
        A:         float (kun for 'spiral' — klotoide-parameter sqrt(L*R))
        dir:       +1 (ccw/venstre) | -1 (cw/høyre) (kun for 'curve'/'spiral')

    Hvis filen ikke har <Alignment>-elementer returneres tom liste.

    Args:
        path: Sti til LandXML-fil.

    Raises:
        ArcpyProcessorError: LANDXML_PARSE_ERROR ved ugyldig XML.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR, f"Ugyldig XML i '{Path(path).name}': {exc}"
        ) from exc

    root = tree.getroot()
    ns_uri = root.tag.split("}")[0][1:] if root.tag.startswith("{") else ""
    ns = {"lx": ns_uri} if ns_uri else {}

    def find_all(parent: ET.Element, tag: str) -> list[ET.Element]:
        return (parent.findall(f".//lx:{tag}", ns) if ns_uri
                else parent.findall(f".//{tag}"))

    def find_one(parent: ET.Element, tag: str) -> ET.Element | None:
        return (parent.find(f"lx:{tag}", ns) if ns_uri
                else parent.find(tag))

    segments: list[dict] = []
    for al in find_all(root, "Alignment"):
        geom_el = find_one(al, "CoordGeom")
        if geom_el is None:
            continue
        for seg in list(geom_el):
            tag = seg.tag.split("}")[-1] if "}" in seg.tag else seg.tag
            sta_start_str = seg.get("staStart")
            length_str = seg.get("length")
            if sta_start_str is None or length_str is None:
                continue
            sta_start = float(sta_start_str)
            sta_end = sta_start + float(length_str)

            if tag == "Line":
                segments.append({
                    "kind": "line",
                    "sta_start": sta_start,
                    "sta_end": sta_end,
                })
            elif tag == "Curve":
                radius_str = seg.get("radius")
                if radius_str is None:
                    continue
                rot = seg.get("rot", "ccw")
                segments.append({
                    "kind": "curve",
                    "sta_start": sta_start,
                    "sta_end": sta_end,
                    "radius": float(radius_str),
                    "dir": +1 if rot == "ccw" else -1,
                })
            elif tag == "Spiral":
                rs_str = seg.get("radiusStart")
                re_str = seg.get("radiusEnd")
                rot = seg.get("rot", "ccw")
                L = float(length_str)
                # Endelig (ikke-uendelig) radius bestemmer A
                rs = float(rs_str) if rs_str and rs_str.lower() != "inf" else None
                re = float(re_str) if re_str and re_str.lower() != "inf" else None
                R = rs if rs is not None else re
                if R is None or R <= 0:
                    continue
                segments.append({
                    "kind": "spiral",
                    "sta_start": sta_start,
                    "sta_end": sta_end,
                    "A": math.sqrt(L * R),
                    "dir": +1 if rot == "ccw" else -1,
                })

    return segments
```

- [ ] **Step 1.4: Kjør testen — verifiser at den passerer**

```
pytest tests/test_landxml_parser.py::test_parses_curve_line_segments_from_alignment -v
pytest tests/test_landxml_parser.py::test_returns_empty_for_planfeature_only_file -v
```

Forventet: begge `PASSED`.

- [ ] **Step 1.5: Kjør alle landxml_parser-tester — verifiser ingen regresjon**

```
pytest tests/test_landxml_parser.py -v
```

Forventet: alle `PASSED`.

- [ ] **Step 1.6: Commit**

```bash
git add src/arcpy_processor/landxml_parser.py tests/test_landxml_parser.py
git commit -m "feat: extract horizontal alignment segments (line/curve/spiral) from LandXML"
```

---

## Task 2: job_runner.py — skriv `horizontal_alignment.json` til output-dir

**Files:**
- Modify: `src/api/job_runner.py:149` (etter eksisterende `parse_landxml(xml_path)`-kall)
- Test: `tests/test_api_jobs.py`

Pipelinen kjører IFC-prosessering først (linje 135–147) og kaller `parse_landxml` for å hente EPSG (linje 149). Vi legger til ekstraksjon og persistering av horisontal alignment **rett etter** EPSG-kallet, før AGOL-publisering starter.

- [ ] **Step 2.1: Skriv en feilende test**

I `tests/test_api_jobs.py`, finn en passende plassering for ny test. Legg til:

```python
def test_horizontal_alignment_json_written(monkeypatch, tmp_path):
    """job_runner skal skrive horizontal_alignment.json til output-dir basert på LandXML."""
    from src.api import job_runner
    from src.arcpy_processor.landxml_parser import parse_horizontal_alignment

    # Bruk ekte sample-fil med Alignment-blokk
    xml_src = Path(__file__).parent.parent / "samples" / "m_f_veg_70400_aligment.xml"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Direkte test av hjelpefunksjonen vi skal lage:
    job_runner._write_horizontal_alignment_json(xml_src, output_dir)

    out_file = output_dir / "horizontal_alignment.json"
    assert out_file.exists(), "horizontal_alignment.json ble ikke skrevet"
    data = json.loads(out_file.read_text())
    assert len(data) == 6
    assert data[0]["kind"] == "curve"
    assert data[0]["radius"] == pytest.approx(50.0)
```

Pass på at `json` og `pytest` er importert øverst i testfilen.

- [ ] **Step 2.2: Kjør testen — verifiser at den feiler**

```
pytest tests/test_api_jobs.py::test_horizontal_alignment_json_written -v
```

Forventet: `FAILED` med `AttributeError: module ... has no attribute '_write_horizontal_alignment_json'`.

- [ ] **Step 2.3: Legg til `_write_horizontal_alignment_json()` i job_runner.py**

I `src/api/job_runner.py`, finn imports øverst (rundt linje 24):

```python
    from src.arcpy_processor.landxml_parser import parse_landxml  # noqa: F401
```

Erstatt med:

```python
    from src.arcpy_processor.landxml_parser import parse_landxml, parse_horizontal_alignment  # noqa: F401
```

Og i fallback-blokken (rundt linje 26):

```python
    parse_landxml = None  # type: ignore[assignment]
```

Erstatt med:

```python
    parse_landxml = None  # type: ignore[assignment]
    parse_horizontal_alignment = None  # type: ignore[assignment]
```

Legg til hjelpefunksjon **nær toppen av filen** (etter imports og før første publike funksjon):

```python
def _write_horizontal_alignment_json(xml_path: Path, output_dir: Path) -> None:
    """Skriv horizontal_alignment.json hvis LandXML har Alignment-blokk.

    Stille no-op hvis parse_horizontal_alignment ikke er tilgjengelig (testmiljø
    uten arcpy) eller hvis filen ikke inneholder Alignment-elementer.
    """
    if parse_horizontal_alignment is None:
        return
    segments = parse_horizontal_alignment(Path(xml_path))
    if not segments:
        return
    out = Path(output_dir) / "horizontal_alignment.json"
    out.write_text(json.dumps(segments, indent=2), encoding="utf-8")
```

- [ ] **Step 2.4: Kall hjelpefunksjonen i `run_job()`**

Finn linje 149:

```python
        _, source_epsg = parse_landxml(xml_path)
```

Erstatt med:

```python
        _, source_epsg = parse_landxml(xml_path)
        _write_horizontal_alignment_json(xml_path, output_dir)
```

- [ ] **Step 2.5: Kjør testen — verifiser at den passerer**

```
pytest tests/test_api_jobs.py::test_horizontal_alignment_json_written -v
```

Forventet: `PASSED`.

- [ ] **Step 2.6: Kjør alle api-tester — verifiser ingen regresjon**

```
pytest tests/test_api_jobs.py -v
```

Forventet: alle `PASSED`.

- [ ] **Step 2.7: Commit**

```bash
git add src/api/job_runner.py tests/test_api_jobs.py
git commit -m "feat: write horizontal_alignment.json to job output dir during pipeline"
```

---

## Task 3: server.py — ny endpoint `/api/jobs/{job_id}/horizontal-alignment`

**Files:**
- Modify: `src/api/server.py` (legg til ny endpoint nær `get_svg`-endpointen rundt linje 326)
- Test: `tests/test_api_jobs.py`

Endpointen serverer JSON-filen som ble skrevet i Task 2. Returnerer `[]` hvis fil ikke finnes (slik at frontenden kan rendre placeholder uten å feile).

- [ ] **Step 3.1: Skriv en feilende test**

I `tests/test_api_jobs.py`, legg til:

```python
def test_get_horizontal_alignment_returns_segments(client, tmp_uploads):
    """Endpoint /api/jobs/{job_id}/horizontal-alignment skal returnere segmenter."""
    job_dir = tmp_uploads / "job-xyz"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True)
    segments = [
        {"kind": "curve", "sta_start": 0.0, "sta_end": 12.77, "radius": 50.0, "dir": -1},
        {"kind": "line",  "sta_start": 12.77, "sta_end": 57.54},
    ]
    (output_dir / "horizontal_alignment.json").write_text(json.dumps(segments))

    r = client.get("/api/jobs/job-xyz/horizontal-alignment")
    assert r.status_code == 200
    assert r.json() == segments


def test_get_horizontal_alignment_returns_empty_list_when_missing(client, tmp_uploads):
    """Hvis filen mangler skal endpoint returnere [] (ikke 404)."""
    job_dir = tmp_uploads / "job-empty"
    (job_dir / "output").mkdir(parents=True)

    r = client.get("/api/jobs/job-empty/horizontal-alignment")
    assert r.status_code == 200
    assert r.json() == []
```

Test-fikstur `tmp_uploads` og `client` finnes allerede i denne filen — bruk dem som eksisterende tester gjør.

- [ ] **Step 3.2: Kjør testene — verifiser at de feiler**

```
pytest tests/test_api_jobs.py::test_get_horizontal_alignment_returns_segments -v
pytest tests/test_api_jobs.py::test_get_horizontal_alignment_returns_empty_list_when_missing -v
```

Forventet: begge `FAILED` med 404.

- [ ] **Step 3.3: Implementer endpointen**

I `src/api/server.py`, finn `get_svg`-endpointen rundt linje 326:

```python
@app.get("/api/jobs/{job_id}/svg/{filename:path}")
def get_svg(job_id: str, filename: str) -> FileResponse:
```

Legg til **rett før** den (eller hvor som helst i rekkefølgen av `/api/jobs/{job_id}/...`-endpointer):

```python
@app.get("/api/jobs/{job_id}/horizontal-alignment")
def get_horizontal_alignment(job_id: str) -> list[dict]:
    """Returner horisontale kurvatur-segmenter for jobben (tom liste hvis mangler)."""
    path = UPLOAD_DIR / job_id / "output" / "horizontal_alignment.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
```

Sjekk at `json` allerede er importert øverst i filen — det skal den være.

- [ ] **Step 3.4: Kjør testene — verifiser at de passerer**

```
pytest tests/test_api_jobs.py::test_get_horizontal_alignment_returns_segments -v
pytest tests/test_api_jobs.py::test_get_horizontal_alignment_returns_empty_list_when_missing -v
```

Forventet: begge `PASSED`.

- [ ] **Step 3.5: Commit**

```bash
git add src/api/server.py tests/test_api_jobs.py
git commit -m "feat: add /api/jobs/{job_id}/horizontal-alignment endpoint"
```

---

## Task 4: profilutforsker.html — hent horCurves i `loadJob()`

**Files:**
- Modify: `web/profilutforsker.html` (global state, `loadJob()`)

- [ ] **Step 4.1: Legg til global `horCurves`-variabel**

Finn linje 1007 (`let lpOpen = false;`-blokken med tilstandsvariabler):

```javascript
let lpOpen = false;
let lpScaleMode = '1:5';  // '1:5' | 'fit'
```

Legg til **rett etter**:

```javascript
let horCurves = [];  // [{kind, sta_start, sta_end, radius?, A?, dir?}, ...]
```

- [ ] **Step 4.2: Tøm horCurves når ny jobb lastes**

I `loadJob()` (rundt linje 1718), finn linjen:

```javascript
  stations = [];
  currentIdx = -1;
```

Erstatt med:

```javascript
  stations = [];
  horCurves = [];
  currentIdx = -1;
```

- [ ] **Step 4.3: Fetch horCurves etter at stations er lastet**

Søk i `loadJob()` (linje 1718–) for hvor stations-arrayet bygges via `fset.features.map(...)` (rundt linje 1799). **Rett etter** denne blokken (etter `stations = fset.features.map(...);`-uttrykket), legg til:

```javascript
  // Last horisontal kurvatur fra API (tom liste hvis ikke tilgjengelig)
  try {
    const hcRes = await fetch(API + '/api/jobs/' + jobId + '/horizontal-alignment',
                              { credentials: 'include' });
    horCurves = hcRes.ok ? await hcRes.json() : [];
  } catch (err) {
    console.warn('horizontal-alignment fetch:', err);
    horCurves = [];
  }
```

Funksjonen `loadJob()` er allerede `async`, så `await` er trygt her.

- [ ] **Step 4.4: Verifiser at filen er gyldig JS**

Åpne filen i nettleseren via dev-serveren (Task 6 dekker dette grundig). Inntil videre — kjør en syntaks-sjekk:

```
node --check web/profilutforsker.html 2>&1 | head -5
```

`node --check` aksepterer ikke HTML, men den skal i det minste ikke kræsje på inline `<script>` — skip dette steget hvis det ikke er praktisk og verifiser i Task 6 i stedet.

- [ ] **Step 4.5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: fetch horizontal alignment data when loading a job"
```

---

## Task 5: profilutforsker.html — rendre Hor.kurv.-rad i `drawLp()`

**Files:**
- Modify: `web/profilutforsker.html:2596-2598` (eksisterende horkurv-placeholder)

Portering av prototypens algoritme fra `explorer-profiles.jsx:446–540` til vanilla JS som genererer SVG-tekst direkte (samme stil som resten av `drawLp()`).

Algoritmen:
1. Tegn lang-stiplet senterlinje gjennom hele rad-bredden.
2. For hvert segment i `horCurves` (filtrert til segmenter som faller innenfor station-range):
   - **Curve**: heltrukken horisontal linje med utslag fra senter — `dir>0` (venstre) = over senterlinjen, `dir<0` (høyre) = under. Tegn `R=<radius>`-label med hvit maskeboks. Tegn vertikale KP-streker (to segmenter med liten luft) ved start og slutt.
   - **Spiral**: diagonal linje fra senterlinjen til nabosegmentets nivå (curve over/under, eller senter for line). Tegn `A=<A>`-label. Tegn KP-streker.
   - **Line**: ingen tilleggsgrafikk — bare senterlinjen synes.

- [ ] **Step 5.1: Erstatt horkurv-blokken**

Finn dette i `drawLp()` (rundt linje 2596–2598):

```javascript
    } else if (r.key === 'horkurv') {
      $(`<line x1="0" y1="${mid.toFixed(1)}" x2="${innerW}" y2="${mid.toFixed(1)}" stroke="${ink}0.18)" stroke-width="0.8" stroke-dasharray="14,5"/>`);
      $(`<text x="${(innerW/2).toFixed(1)}" y="${(mid+3.5).toFixed(1)}" text-anchor="middle" font-size="8" fill="${ink}0.28)" font-family="var(--font-sans)" font-style="italic">kurvaturdata fra LandXML</text>`);

    } else if (r.key === 'breddeutv') {
```

Erstatt med:

```javascript
    } else if (r.key === 'horkurv') {
      const yC    = mid;
      const yTop  = y0 + 3;
      const yBot  = y0 + rh - 3;
      const offset = (yBot - yC) * 0.85;
      const segFs = Math.max(8.5, baseRowH * 0.62);
      const stepX = innerW / Math.max(1, (stMax - stMin) / 10);

      // Lang-stiplet senterlinje (~3 stipler per 50 m)
      const dash = Math.max(8, stepX * 1.3);
      const gap  = Math.max(3, stepX * 0.4);
      $(`<line x1="0" y1="${yC.toFixed(1)}" x2="${innerW}" y2="${yC.toFixed(1)}" stroke="${ink}1)" stroke-width="0.9" stroke-dasharray="${dash.toFixed(1)},${gap.toFixed(1)}"/>`);

      // Filtrer segmenter til synlig station-range
      const visible = horCurves.filter(hc => hc.sta_end > stMin && hc.sta_start < stMax);

      visible.forEach((hc, i) => {
        const xL = xOf(Math.max(hc.sta_start, stMin));
        const xR = xOf(Math.min(hc.sta_end, stMax));
        const midX = (xL + xR) / 2;
        const prev = visible[i - 1];
        const next = visible[i + 1];

        if (hc.kind === 'curve') {
          const yArc = yC - hc.dir * offset;
          $(`<line x1="${xL.toFixed(1)}" x2="${xR.toFixed(1)}" y1="${yArc.toFixed(1)}" y2="${yArc.toFixed(1)}" stroke="${ink}1)" stroke-width="1.4"/>`);
          if ((xR - xL) > 22) {
            const labelY = hc.dir > 0 ? yArc + segFs + 1 : yArc - 3;
            $(`<rect x="${(midX - segFs * 1.9).toFixed(1)}" y="${(labelY - segFs).toFixed(1)}" width="${(segFs * 3.8).toFixed(1)}" height="${(segFs + 2).toFixed(1)}" fill="var(--card)"/>`);
            $(`<text x="${midX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" font-size="${segFs.toFixed(1)}" fill="${ink}1)" font-family="var(--font-mono)" font-weight="500">R=${Math.round(hc.radius)}</text>`);
          }
        } else if (hc.kind === 'spiral') {
          let yA = yC, yB = yC;
          if (prev && prev.kind === 'curve') yA = yC - prev.dir * offset;
          if (next && next.kind === 'curve') yB = yC - next.dir * offset;
          $(`<line x1="${xL.toFixed(1)}" x2="${xR.toFixed(1)}" y1="${yA.toFixed(1)}" y2="${yB.toFixed(1)}" stroke="${ink}1)" stroke-width="1.4"/>`);
          if ((xR - xL) > 20) {
            const yMidSeg = (yA + yB) / 2;
            const above = yMidSeg < yC;
            const labelY = above ? yMidSeg - 3 : yMidSeg + segFs + 1;
            $(`<rect x="${(midX - segFs * 1.8).toFixed(1)}" y="${(labelY - segFs).toFixed(1)}" width="${(segFs * 3.6).toFixed(1)}" height="${(segFs + 2).toFixed(1)}" fill="var(--card)"/>`);
            $(`<text x="${midX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" font-size="${segFs.toFixed(1)}" fill="${ink}1)" font-family="var(--font-mono)" font-weight="500">A=${Math.round(hc.A)}</text>`);
          }
        }
        // KP-streker ved start og slutt (curve + spiral)
        if (hc.kind === 'curve' || hc.kind === 'spiral') {
          [xL, xR].forEach(x => {
            const yMidGap = (yTop + yBot) / 2;
            const g = 3;
            $(`<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${yTop.toFixed(1)}" y2="${(yMidGap - g).toFixed(1)}" stroke="${ink}1)" stroke-width="0.7"/>`);
            $(`<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${(yMidGap + g).toFixed(1)}" y2="${yBot.toFixed(1)}" stroke="${ink}1)" stroke-width="0.7"/>`);
          });
        }
      });

      // Hvis ingen segmenter (eller alle utenfor): vis placeholder-tekst
      if (visible.length === 0) {
        $(`<text x="${(innerW/2).toFixed(1)}" y="${(mid+3.5).toFixed(1)}" text-anchor="middle" font-size="8" fill="${ink}0.28)" font-family="var(--font-sans)" font-style="italic">kurvaturdata mangler</text>`);
      }

    } else if (r.key === 'breddeutv') {
```

Merk: `stMin`, `stMax`, `xOf`, `mid`, `y0`, `rh`, `innerW`, `baseRowH`, `ink` er alle lokale variabler i `drawLp()` som allerede er definert før denne blokken — du trenger ikke å definere dem på nytt.

- [ ] **Step 5.2: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat: render Hor.kurv. row from LandXML alignment data"
```

---

## Task 6: Visuell verifikasjon

**Files:** Ingen — ren E2E-sjekk i nettleser.

- [ ] **Step 6.1: Start dev-server og kjør pipeline med Alignment-data**

Bruk `dev.ps1` (eller tilsvarende startskript) for å starte API + frontend. Last opp en LandXML-fil som inneholder `<Alignment>/<CoordGeom>` (Quadri/Novapoint-eksportert). `samples/m_f_veg_70400_aligment.xml` er en kjent god kandidat for utvikling, men for fullstendig flyt trenger du IFC + LandXML matchet.

- [ ] **Step 6.2: Sjekkliste for visuell verifikasjon**

Åpne profilutforsker, velg jobben, åpne lengdeprofil-skuffen.

Sjekk:
- [ ] Hor.kurv.-raden viser en lang-stiplet horisontal linje gjennom hele bredden (~3 stipler pr 50 m).
- [ ] Buer vises som heltrukken horisontal linje med utslag — venstrekurve over senter, høyrekurve under senter.
- [ ] Hver bue har `R=<radius>`-label sentrert over/under linjen med hvit maskeboks.
- [ ] Klotoider (spiraler) vises som diagonal linje mellom senterlinjen og bueens nivå.
- [ ] Hver klotoide har `A=<A>`-label.
- [ ] Vertikale KP-streker (to korte segmenter med liten luft) markerer start/slutt av hver bue og klotoide.
- [ ] Rette strekninger viser bare senterlinjen (ingen tilleggsgrafikk).
- [ ] Hvis LandXML-filen ikke har Alignment-blokk: raden viser italic "kurvaturdata mangler" og ingen kræsj.
- [ ] Mørk modus: alle linjer/labels lesbare.

- [ ] **Step 6.3: Hvis sjekklisten avdekker problemer**

Diagnostiser via DevTools:
- `console.log(horCurves)` — verifiser at data er hentet og har riktig struktur.
- Inspect SVG-elementene — verifiser at `<line>` og `<text>` faktisk rendres med riktige koordinater.

Vanlige fallgruver:
- Stasjonene i `horCurves` (fra LandXML) kan starte på 0, mens `stations` (fra AGOL/IFC-pipeline) kan ha en offset. Verifiser at `stMin`/`stMax` matcher LandXML-alignmentens `staStart`.
- Hvis `dir`-konvensjonen ser snudd ut (venstrekurver under, høyre over), juster fortegnet i Task 1's `parse_horizontal_alignment` (LandXML `rot="cw"` = høyrekurve sett i kjøreretning).

---

## Spec Coverage Check

| Krav | Implementert i |
|------|----------------|
| Parse Line/Curve/Spiral fra Alignment | Task 1 |
| Robust fallback for PlanFeature-only filer | Task 1 |
| Skriv horizontal_alignment.json | Task 2 |
| API-endpoint for å lese data | Task 3 |
| Frontend henter data ved jobb-valg | Task 4 |
| Lang-stiplet senterlinje | Task 5 |
| Utslag for curve med R-label | Task 5 |
| Diagonal for spiral med A-label | Task 5 |
| KP/KKP-streker | Task 5 |
| Placeholder hvis ingen data | Task 5 |
| Visuell verifikasjon | Task 6 |
