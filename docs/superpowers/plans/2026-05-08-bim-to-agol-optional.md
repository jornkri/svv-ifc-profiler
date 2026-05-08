# Valgfri BIM-publisering til AGOL — Implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Legg til en valgfri checkbox i web-veiviseren som lar brukeren publisere BIM-data (IFC) som et 3D GIS-lag i ArcGIS Online som en ekstra fase i den eksisterende pipeline-jobben.

**Architecture:** En ny `publish_bim: bool`-parameter traverserer hele stacken fra HTML-checkbox → FormData → FastAPI → job_runner. `bim_to_agol.py` utvides med `--token`/`--org-url` slik den matcher de andre ArcPy-CLI-ene. Feiler BIM-fasen, settes jobben til `done_with_warnings` og tverrprofil-/senterlinje-resultater vises likevel.

**Tech Stack:** Python (FastAPI, dataclasses), vanilla JavaScript, HTML/CSS

---

## Filkart

| Fil | Endring |
|-----|---------|
| `src/arcpy_processor/bim_to_agol.py` | Legg til `--token` og `--org-url` CLI-argumenter |
| `src/api/job_runner.py` | Legg til `publish_bim`, `bim_url`, `done_with_warnings` |
| `src/api/server.py` | Legg til `publish_bim` i skjema og `bim_url` i respons |
| `web/index.html` | Legg til checkbox i steg 3 |
| `web/src/main.js` | Les checkbox, send med FormData |
| `web/job.html` | Legg til CSS-klasse og BIM-lenke |
| `web/src/job.js` | Håndter `bim_url` og `done_with_warnings` |
| `tests/test_arcpy_cli.py` | Legg til test for `--token`/`--org-url` i bim_to_agol |
| `tests/test_api_jobs.py` | Legg til tester for publish_bim-flyt |

---

## Task 1: Legg til --token og --org-url i bim_to_agol.py

**Files:**
- Modify: `src/arcpy_processor/bim_to_agol.py`
- Test: `tests/test_arcpy_cli.py`

- [ ] **Step 1: Skriv den feilende testen**

Legg til følgende test nederst i `tests/test_arcpy_cli.py`:

```python
def test_cli_passes_token_and_org_url_to_connect(capsys):
    mock_gis = MagicMock()
    success_meta = {"status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer"}

    with patch("src.arcpy_processor.auth.connect", return_value=mock_gis) as mock_connect, \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.converter.convert_bim", return_value=["fc1"]), \
         patch("src.arcpy_processor.converter.delete_empty_fcs", return_value=["fc1"]), \
         patch("src.arcpy_processor.bim_to_agol._gdb_path_from_fcs",
               return_value="/scratch/bim_temp.gdb"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.bim_to_agol import main

        with pytest.raises(SystemExit) as exc_info:
            main([
                "--ifc", "test.ifc", "--name", "TestLag", "--folder", "SVV",
                "--token", "mytoken123",
                "--org-url", "https://myorg.maps.arcgis.com",
            ])
        assert exc_info.value.code == 0

    mock_connect.assert_called_once_with(
        token="mytoken123",
        org_url="https://myorg.maps.arcgis.com",
    )
```

- [ ] **Step 2: Kjør testen og verifiser at den feiler**

```
pytest tests/test_arcpy_cli.py::test_cli_passes_token_and_org_url_to_connect -v
```

Forventet: FAIL — `connect()` kalles uten argumenter.

- [ ] **Step 3: Implementer endringen i bim_to_agol.py**

I `src/arcpy_processor/bim_to_agol.py`, i `main()`-funksjonen, finn `parser.add_argument`-blokken og legg til to nye argumenter:

```python
    parser.add_argument("--ifc", required=True, help="Sti til .ifc-fil")
    parser.add_argument("--name", required=True, help="Tjenestenavn i ArcGIS Online")
    parser.add_argument("--folder", required=True, help="Folder i ArcGIS Online")
    parser.add_argument("--token", default=None, help="AGOL OAuth2-token")
    parser.add_argument("--org-url", default=None, dest="org_url",
                        help="ArcGIS Online organisasjons-URL")
```

Finn deretter linjen `gis = connect()` og endre til:

```python
        gis = connect(token=args.token, org_url=args.org_url)
```

- [ ] **Step 4: Kjør alle arcpy-cli-tester og verifiser at alle passerer**

```
pytest tests/test_arcpy_cli.py -v
```

Forventet: alle 5 tester PASS.

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/bim_to_agol.py tests/test_arcpy_cli.py
git commit -m "feat: add --token and --org-url args to bim_to_agol CLI"
```

---

## Task 2: Utvid job_runner med publish_bim, bim_url og done_with_warnings

**Files:**
- Modify: `src/api/job_runner.py`
- Test: `tests/test_api_jobs.py`

- [ ] **Step 1: Skriv feilende test — publish_bim=True, BIM lykkes**

Legg til følgende test i `tests/test_api_jobs.py` etter `test_run_job_sets_failed_on_subprocess_error`:

```python
def test_run_job_with_publish_bim_success(tmp_path):
    """publish_bim=True kjører tre subprocesser og setter bim_url."""
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"; fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"; fake_xml.write_text("")
    output_dir = tmp_path / "output"; output_dir.mkdir()
    meta = {"stations": [{"station": 0.0}, {"station": 10.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl/FeatureServer"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp/FeatureServer"})
    bim_stdout = json.dumps({"status": "ok", "url": "https://agol/bim/FeatureServer"})

    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)
    mock_proc_bim = MagicMock(stdout=bim_stdout, returncode=0)

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp, mock_proc_bim]), \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 25833)):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            xml_path=fake_xml,
            name="TestBIM",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
            publish_bim=True,
        )

    state = get_job(job_id)
    assert state.status == "done"
    assert state.bim_url == "https://agol/bim/FeatureServer"
    assert state.centerline_url == "https://agol/cl/FeatureServer"
    assert state.sections_url == "https://agol/tp/FeatureServer"
```

- [ ] **Step 2: Skriv feilende test — publish_bim=True, BIM feiler → done_with_warnings**

Legg til rett etter forrige test:

```python
def test_run_job_with_publish_bim_bim_fails_gives_done_with_warnings(tmp_path):
    """Når BIM-subprocess feiler settes done_with_warnings; senterlinje og tverrprofiler er ok."""
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"; fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"; fake_xml.write_text("")
    output_dir = tmp_path / "output"; output_dir.mkdir()
    meta = {"stations": [{"station": 0.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp"})

    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)
    bim_error = subprocess.CalledProcessError(1, "cmd", stderr="BIM-konvertering feilet")

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp, bim_error]), \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 25833)):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            xml_path=fake_xml,
            name="TestBIMFail",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
            publish_bim=True,
        )

    state = get_job(job_id)
    assert state.status == "done_with_warnings"
    assert state.bim_url is None
    assert state.centerline_url == "https://agol/cl"
    assert state.sections_url == "https://agol/tp"
    assert "BIM-konvertering feilet" in state.error
```

- [ ] **Step 3: Kjør de to nye testene og verifiser at begge feiler**

```
pytest tests/test_api_jobs.py::test_run_job_with_publish_bim_success tests/test_api_jobs.py::test_run_job_with_publish_bim_bim_fails_gives_done_with_warnings -v
```

Forventet: begge FAIL.

- [ ] **Step 4: Implementer endringene i job_runner.py**

Erstatt hele innholdet i `src/api/job_runner.py` med:

```python
# src/api/job_runner.py
"""Bakgrunnsjobb-orkestrator for IFC → AGOL pipeline."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

try:
    from src.ifc_processor.pipeline import run_pipeline  # noqa: F401
except Exception:  # pragma: no cover
    run_pipeline = None  # type: ignore[assignment]

try:
    from src.arcpy_processor.landxml_parser import parse_landxml  # noqa: F401
except Exception:  # pragma: no cover
    parse_landxml = None  # type: ignore[assignment]

JobStatus = Literal["queued", "running", "done", "done_with_warnings", "failed"]


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "queued"
    progress_pct: int = 0
    message: str = "Venter…"
    centerline_url: str | None = None
    sections_url: str | None = None
    bim_url: str | None = None
    error: str | None = None


_jobs: dict[str, JobState] = {}


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobState(job_id=job_id, message="Starter pipeline…")
    return job_id


def get_job(job_id: str) -> JobState | None:
    return _jobs.get(job_id)


def _update(state: JobState, pct: int, msg: str) -> None:
    state.progress_pct = pct
    state.message = msg
    logger.info("[%s] %d%% %s", state.job_id, pct, msg)


def run_job(
    job_id: str,
    ifc_path: Path,
    xml_path: Path,
    name: str,
    interval: float,
    access_token: str,
    org_url: str,
    output_dir: Path,
    publish_bim: bool = False,
) -> None:
    """Kjør full pipeline i bakgrunnen. Oppdaterer jobbstatus underveis."""
    state = _jobs[job_id]
    state.status = "running"

    try:
        _update(state, 0, "Starter pipeline…")
        _update(state, 5, "Kjører IFC-prosessering…")

        pipeline_result = run_pipeline(
            ifc_path=ifc_path,
            centerline_path=xml_path,
            output_dir=output_dir,
            interval_m=interval,
        )

        meta = json.loads(Path(pipeline_result["metadata"]).read_text())
        n_sections = len(meta["stations"])
        _update(state, 50, f"Genererte {n_sections} tverrprofiler")

        _, source_epsg = parse_landxml(xml_path)

        _update(state, 55, "Publiserer senterlinje til AGOL…")
        cl_proc = subprocess.run(
            [
                sys.executable, "-m", "src.arcpy_processor.landxml_to_agol",
                "--xml", str(xml_path),
                "--name", f"{name}_senterlinje",
                "--folder", "",
                "--token", access_token,
                "--org-url", org_url,
            ],
            check=True, capture_output=True, text=True,
        )
        cl_result = json.loads(cl_proc.stdout)
        state.centerline_url = cl_result.get("url")
        logger.info("[%s] senterlinje stdout: %s", job_id, cl_proc.stdout.strip())
        logger.info("[%s] senterlinje stderr: %s", job_id, cl_proc.stderr.strip())
        _update(state, 70, "Senterlinje publisert til AGOL")

        _update(state, 75, "Publiserer tverrprofiler til AGOL…")
        tp_proc = subprocess.run(
            [
                sys.executable, "-m", "src.arcpy_processor.tverrprofil_to_agol",
                "--stations-json", pipeline_result["stations_json"],
                "--svgs-dir", str(output_dir),
                "--name", f"{name}_tverrprofiler",
                "--folder", "",
                "--source-epsg", str(source_epsg),
                "--token", access_token,
                "--org-url", org_url,
            ],
            check=True, capture_output=True, text=True,
        )
        tp_result = json.loads(tp_proc.stdout)
        state.sections_url = tp_result.get("url")
        logger.info("[%s] tverrprofil stdout: %s", job_id, tp_proc.stdout.strip())
        logger.info("[%s] tverrprofil stderr: %s", job_id, tp_proc.stderr.strip())

        if publish_bim:
            _update(state, 80, "Publiserer BIM som 3D GIS-lag…")
            try:
                bim_proc = subprocess.run(
                    [
                        sys.executable, "-m", "src.arcpy_processor.bim_to_agol",
                        "--ifc", str(ifc_path),
                        "--name", f"{name}_bim",
                        "--folder", "",
                        "--token", access_token,
                        "--org-url", org_url,
                    ],
                    check=True, capture_output=True, text=True,
                )
                bim_result = json.loads(bim_proc.stdout)
                state.bim_url = bim_result.get("url")
                logger.info("[%s] BIM stdout: %s", job_id, bim_proc.stdout.strip())
                _update(state, 100, f"Ferdig — {n_sections} profiler + BIM-lag publisert")
                state.status = "done"
            except subprocess.CalledProcessError as exc:
                logger.warning("[%s] BIM-publisering feilet: %s", job_id, exc.stderr)
                state.error = exc.stderr or f"BIM-subprocess feilet med kode {exc.returncode}"
                _update(state, 100, f"Ferdig — {n_sections} profiler publisert (BIM feilet)")
                state.status = "done_with_warnings"
        else:
            _update(state, 100, f"Ferdig — {n_sections} profiler publisert")
            state.status = "done"

    except subprocess.CalledProcessError as exc:
        state.status = "failed"
        state.error = exc.stderr or f"Subprocess feilet med kode {exc.returncode}"
        logger.error("[%s] Subprocess feilet: %s", job_id, state.error)
    except Exception as exc:
        state.status = "failed"
        state.error = str(exc)
        logger.error("[%s] Jobb feilet: %s", job_id, exc, exc_info=True)
```

- [ ] **Step 5: Kjør alle job_runner-tester og verifiser at alle passerer**

```
pytest tests/test_api_jobs.py -v -k "not client and not health and not post_jobs and not get_job"
```

Forventet: alle `run_job`- og `create_job`-tester PASS.

- [ ] **Step 6: Commit**

```bash
git add src/api/job_runner.py tests/test_api_jobs.py
git commit -m "feat: add publish_bim phase and done_with_warnings status to job_runner"
```

---

## Task 3: Legg til publish_bim i server.py og bim_url i respons

**Files:**
- Modify: `src/api/server.py`
- Test: `tests/test_api_jobs.py`

- [ ] **Step 1: Skriv feilende test — publish_bim sendes til run_job**

Legg til i `tests/test_api_jobs.py`:

```python
def test_post_jobs_passes_publish_bim_true_to_run_job(client):
    """publish_bim=true i skjemaet skal sendes videre til run_job."""
    _login(client)
    with patch("src.api.job_runner.run_job") as mock_run_job:
        client.post(
            "/api/jobs",
            data={"name": "S", "interval": "10", "publish_bim": "true"},
            files={"ifc_file": ("m.ifc", io.BytesIO(b"x")),
                   "xml_file": ("c.xml", io.BytesIO(b"<x/>"))},
        )
    mock_run_job.assert_called_once()
    _, kwargs = mock_run_job.call_args
    assert kwargs.get("publish_bim") is True


def test_get_job_status_includes_bim_url(client):
    """GET /api/jobs/{id} skal inneholde bim_url-feltet."""
    _login(client)
    with patch("src.api.job_runner.run_job"):
        create_resp = client.post(
            "/api/jobs",
            data={"name": "S", "interval": "10"},
            files={"ifc_file": ("m.ifc", io.BytesIO(b"x")),
                   "xml_file": ("c.xml", io.BytesIO(b"<x/>"))},
        )
    job_id = create_resp.json()["job_id"]
    status_resp = client.get(f"/api/jobs/{job_id}")
    assert "bim_url" in status_resp.json()
```

- [ ] **Step 2: Kjør de to nye testene og verifiser at de feiler**

```
pytest tests/test_api_jobs.py::test_post_jobs_passes_publish_bim_true_to_run_job tests/test_api_jobs.py::test_get_job_status_includes_bim_url -v
```

Forventet: begge FAIL.

- [ ] **Step 3: Implementer endringene i server.py**

I `src/api/server.py`, finn `async def create_job(...)` og legg til `publish_bim`-parameter og oppdater `background_tasks.add_task`:

```python
@app.post("/api/jobs")
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    ifc_file: UploadFile = File(...),
    xml_file: UploadFile = File(...),
    name: str = Form(...),
    interval: float = Form(10.0),
    publish_bim: bool = Form(False),
) -> dict:
    """Motta IFC + LandXML, start pipeline-jobb i bakgrunnen."""
    if "access_token" not in request.session:
        raise HTTPException(401, "Ikke innlogget — bruk /auth/login")
    if not ifc_file.filename or not ifc_file.filename.lower().endswith(".ifc"):
        raise HTTPException(400, "ifc_file må være en .ifc-fil")
    if not xml_file.filename or not xml_file.filename.lower().endswith(".xml"):
        raise HTTPException(400, "xml_file må være en .xml LandXML-fil")
    if not (1 <= interval <= 100):
        raise HTTPException(400, "interval må være mellom 1 og 100 meter")

    job_id = job_runner.create_job()
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir()

    ifc_path = job_dir / "model.ifc"
    xml_path = job_dir / "centerline.xml"

    with ifc_path.open("wb") as f:
        while chunk := await ifc_file.read(1024 * 1024):
            f.write(chunk)
    with xml_path.open("wb") as f:
        while chunk := await xml_file.read(1024 * 1024):
            f.write(chunk)

    background_tasks.add_task(
        job_runner.run_job,
        job_id=job_id,
        ifc_path=ifc_path,
        xml_path=xml_path,
        name=name,
        interval=interval,
        access_token=request.session["access_token"],
        org_url=request.session.get("org_url", "https://www.arcgis.com"),
        output_dir=job_dir / "output",
        publish_bim=publish_bim,
    )

    return {"job_id": job_id, "status": "queued"}
```

Finn deretter `def get_job(...)` og legg til `bim_url` i return-dict:

```python
@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    state = job_runner.get_job(job_id)
    if state is None:
        raise HTTPException(404, "Jobb ikke funnet")
    return {
        "status": state.status,
        "progress_pct": state.progress_pct,
        "message": state.message,
        "centerline_url": state.centerline_url,
        "sections_url": state.sections_url,
        "bim_url": state.bim_url,
        "error": state.error,
    }
```

- [ ] **Step 4: Kjør alle server- og job_runner-tester**

```
pytest tests/test_api_jobs.py -v
```

Forventet: alle tester PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py tests/test_api_jobs.py
git commit -m "feat: add publish_bim form field and bim_url to job API"
```

---

## Task 4: Frontend — checkbox, BIM-lenke og done_with_warnings

**Files:**
- Modify: `web/index.html`
- Modify: `web/src/main.js`
- Modify: `web/job.html`
- Modify: `web/src/job.js`

- [ ] **Step 1: Legg til checkbox i web/index.html**

Finn steg-3-kortet i `web/index.html`. Etter `<span class="error-msg" id="form-error"></span>` og før `<button ...>Kjør pipeline</button>`, legg til:

```html
      <div style="margin-top:0.75rem">
        <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.85rem;color:#555;cursor:pointer">
          <input type="checkbox" id="publish-bim" />
          Publiser BIM-data som 3D GIS-lag
          <span style="color:#999;font-size:0.8rem">(kan ta tid)</span>
        </label>
      </div>
```

Resulterende blokk:

```html
    <!-- Step 3: Settings + Run -->
    <div class="card disabled" id="step3">
      <h2>Innstillinger</h2>
      <div class="row">
        <div>
          <label for="interval">Tverrprofilintervall (m)</label>
          <input type="number" id="interval" value="10" min="1" max="100" step="1" />
        </div>
        <div>
          <label for="service-name">Tjenestenavn i AGOL</label>
          <input type="text" id="service-name" placeholder="Rv4_Roa_profiler" maxlength="60" />
        </div>
      </div>
      <span class="error-msg" id="form-error"></span>
      <div style="margin-top:0.75rem">
        <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.85rem;color:#555;cursor:pointer">
          <input type="checkbox" id="publish-bim" />
          Publiser BIM-data som 3D GIS-lag
          <span style="color:#999;font-size:0.8rem">(kan ta tid)</span>
        </label>
      </div>
      <button class="btn btn-success" id="run-btn" style="margin-top:1rem" disabled>
        Kjør pipeline
      </button>
    </div>
```

- [ ] **Step 2: Oppdater web/src/main.js**

Øverst i filen, der andre DOM-referanser deklareres, legg til:

```javascript
const publishBimCheckbox = document.getElementById("publish-bim");
```

I `runBtn.addEventListener("click", ...)`, finn blokken der `fd.append`-kall gjøres og legg til:

```javascript
  fd.append("ifc_file", ifcFile.files[0]);
  fd.append("xml_file", xmlFile.files[0]);
  fd.append("name", name);
  fd.append("interval", String(interval));
  fd.append("publish_bim", publishBimCheckbox.checked ? "true" : "false");
```

- [ ] **Step 3: Legg til CSS-klasse og BIM-lenke i web/job.html**

I `<style>`-blokken, legg til ny CSS-klasse etter `.status-failed`:

```css
    .status-done_with_warnings { background: #fff8e1; color: #e65100; }
```

I `#result-links`-div, legg til BIM-lenken etter `link-sections`:

```html
      <a href="#" class="result-link" id="link-bim" target="_blank">
        <span>BIM-lag (3D Object Layer)</span>
      </a>
```

- [ ] **Step 4: Oppdater web/src/job.js**

Legg til DOM-referanse øverst, etter `linkSections`:

```javascript
const linkBim = document.getElementById("link-bim");
```

Erstatt hele `updateUI`-funksjonen:

```javascript
function updateUI(data) {
  jobTitle.textContent = jobId.slice(0, 8) + "…";

  statusBadge.textContent = {
    queued: "Venter",
    running: "Kjører",
    done: "Ferdig",
    done_with_warnings: "Ferdig",
    failed: "Feilet",
  }[data.status] ?? data.status;
  statusBadge.className = `status-badge status-${data.status}`;

  progressBar.style.width = `${data.progress_pct}%`;
  if (data.status === "done" || data.status === "done_with_warnings") {
    progressBar.classList.add("done");
  }
  if (data.status === "failed") progressBar.classList.add("failed");

  currentMessage.textContent = data.message || "";

  if (data.message && data.message !== prevMessage) {
    if (prevMessage) addLogEntry(prevMessage);
    prevMessage = data.message;
  }

  if (data.status === "done" || data.status === "done_with_warnings") {
    resultLinks.style.display = "block";
    if (data.centerline_url) {
      linkCenterline.href = data.centerline_url;
    } else {
      linkCenterline.style.display = "none";
    }
    if (data.sections_url) {
      linkSections.href = data.sections_url;
    } else {
      linkSections.style.display = "none";
    }
    if (data.bim_url) {
      linkBim.href = data.bim_url;
    } else {
      linkBim.style.display = "none";
    }
  }

  if (data.status === "done_with_warnings") {
    errorBox.style.display = "block";
    errorBox.style.background = "#fff8e1";
    errorBox.style.borderColor = "#ffcc02";
    errorBox.style.color = "#e65100";
    errorBox.textContent = `BIM-publisering feilet: ${data.error || "Ukjent feil"}`;
  }

  if (data.status === "failed") {
    errorBox.style.display = "block";
    errorBox.textContent = `Feil: ${data.error || "Ukjent feil"}`;
  }
}
```

Erstatt `clearInterval`-sjekken med:

```javascript
    if (data.status === "done" || data.status === "done_with_warnings" || data.status === "failed") {
      clearInterval(pollHandle);
    }
```

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/src/main.js web/job.html web/src/job.js
git commit -m "feat: add optional BIM publish checkbox and result link to frontend"
```

---

## Task 5: Full testsuite og røyktest

- [ ] **Step 1: Kjør hele testsuiten**

```
pytest -v
```

Forventet: alle tester PASS. Antall tester skal ha økt med 4 nye (1 i test_arcpy_cli.py, 3 i test_api_jobs.py).

- [ ] **Step 2: Start utviklingsserver og verifiser visuelt**

```bash
uvicorn src.api.server:app --reload
```

Åpne `http://localhost:5173` i nettleser (forutsetter at Vite-dev-server kjører). Verifiser:
- Checkbox vises i steg 3
- Checkbox er ikke avkrysset som standard
- Å krysse av og sende inn jobben fungerer (kan testes med mock uten AGOL-tilkobling)

- [ ] **Step 3: Commit (om nødvendig)**

Kun hvis det ble gjort manuelle justeringer under røyktest.
