# Tverrprofil-pipeline med landing page og AGOL OAuth2 — designspesifikasjon

**Dato:** 2026-05-04
**Scope:** Landing page for IFC + LandXML upload, OAuth2-innlogging mot ArcGIS Online, bakgrunnsjobb som genererer tverrprofiler og publiserer senterlinje + tverrprofil-punkter til brukerens AGOL-konto.

---

## Mål

En web-applikasjon der brukeren:
1. Logger inn med sin egen ArcGIS Online-konto (OAuth2 Authorization Code flow)
2. Laster opp IFC-fil + LandXML-senterlinjefil
3. Oppgir tverrprofilintervall (m) og tjenestenavn
4. Starter en bakgrunnsjobb og følger fremdrift med live statusmeldinger
5. Får to ferdig-publiserte feature services i sin AGOL-konto

---

## Arkitektur

```
Browser (Vite + ArcGIS JS SDK)
  Landing page:  wizard steg 1→2→3 + "Kjør"-knapp
  Jobstatus:     polling hvert 2s + fremdriftslinje + AGOL-lenker

FastAPI (src/api/)
  /auth/*        OAuth2 Authorization Code flow (server-side session)
  /api/jobs      Opprett + poll jobb

BackgroundTask (FastAPI BackgroundTasks)
  Steg 1: ifc_processor.run_pipeline()      → SVG-er + stasjoner
  Steg 2: landxml_to_agol subprocess        → senterlinje FeatureServer
  Steg 3: tverrprofil_to_agol subprocess    → punkter + SVG-vedlegg FeatureServer

ArcPy subprocesses (src/arcpy_processor/)
  Mottar --token <access_token> i stedet for å lese fra .env
```

---

## Komponenter

### 1. `src/api/auth_routes.py` — NY

FastAPI-router for OAuth2-flyten.

**Endepunkter:**

| Metode | Sti | Beskrivelse |
|--------|-----|-------------|
| `GET` | `/auth/login` | Generer OAuth2 state-parameter, lagre i session, redirect til AGOL authorize-URL |
| `GET` | `/auth/callback` | Valider state, bytt code mot access_token + refresh_token via AGOL token-endpoint, lagre i server-session |
| `GET` | `/auth/me` | Returner `{username, full_name, org_url}` for innlogget bruker (fra session) |
| `POST` | `/auth/logout` | Slett server-session |

**OAuth2-parametre (fra .env):**
```
AGOL_CLIENT_ID=<app-klient-ID fra AGOL Developer Console>
AGOL_CLIENT_SECRET=<app-klient-secret>
AGOL_REDIRECT_URI=http://localhost:8000/auth/callback
AGOL_ORG_URL=https://testkommune.maps.arcgis.com
```

**Session-lagring:** `starlette.middleware.sessions.SessionMiddleware` med `SECRET_KEY` fra .env. Session inneholder: `access_token`, `refresh_token`, `username`, `org_url`.

**State-validering:** UUID4 genereres ved `/auth/login`, lagres i session, valideres i `/auth/callback` — forhindrer CSRF.

---

### 2. `src/api/server.py` — UTVIDE

Eksisterende FastAPI-app utvides med:
- `app.include_router(auth_router, prefix="/auth")`
- `SessionMiddleware` registreres
- `POST /api/jobs` — ny rute (se under)
- `GET /api/jobs/{id}` — utvide eksisterende (tilsvarende stub finnes)

**`POST /api/jobs`** — multipart form:
```
ifc_file:   UploadFile   (.ifc)
xml_file:   UploadFile   (.xml LandXML)
name:       str          tjenestenavn i AGOL
interval:   float        tverrprofilintervall i meter (default: 10.0)
```
Krever innlogget bruker (sjekk session). Returnerer `{job_id, status: "queued"}`. Starter `BackgroundTask(run_job, job_id, ...)`.

**`GET /api/jobs/{id}`** returnerer:
```json
{
  "status": "running",
  "progress_pct": 45,
  "message": "Kutter tverrprofiler… (stasjon 230 av 510 m)",
  "centerline_url": null,
  "sections_url": null,
  "error": null
}
```
`status` ∈ `"queued" | "running" | "done" | "failed"`.

---

### 3. `src/api/job_runner.py` — NY

Bakgrunnsjobb-orkestrator. Funksjon `run_job(job_id, ifc_path, xml_path, name, interval, access_token, org_url)`.

**Jobbsteg og statusmeldinger:**

| Steg | `progress_pct` | `message` |
|------|---------------|-----------|
| Start | 0 | "Starter pipeline…" |
| IFC lest | 10 | "IFC lest — {n} overflatelag" |
| Senterlinje lastet | 15 | "Senterlinje lastet — {length:.0f} m" |
| Tverrprofiler generert | 50 | "Genererte {n} tverrprofiler" |
| Senterlinje publisert | 70 | "Senterlinje publisert til AGOL" |
| Tverrprofiler publisert | 100 | "Ferdig — {n} profiler publisert" |

Jobbstatus lagres i minne (dict `_jobs: dict[str, JobState]`). Ingen database nødvendig for MVP.

**Subprosess-kall:**
```python
# Steg 2: senterlinje
subprocess.run([
    sys.executable, "-m", "src.arcpy_processor.landxml_to_agol",
    "--xml", str(xml_path),
    "--name", f"{name}_senterlinje",
    "--folder", "",
    "--token", access_token,
    "--org-url", org_url,
], check=True, capture_output=True)

# Steg 3: tverrprofiler
subprocess.run([
    sys.executable, "-m", "src.arcpy_processor.tverrprofil_to_agol",
    "--stations-json", str(stations_json_path),
    "--svgs-dir", str(svgs_dir),
    "--name", f"{name}_tverrprofiler",
    "--folder", "",
    "--token", access_token,
    "--org-url", org_url,
], check=True, capture_output=True)
```

---

### 4. `src/arcpy_processor/auth.py` — UTVIDE

`connect()` utvides til å akseptere valgfri token:

```python
def connect(token: str | None = None, org_url: str | None = None) -> GIS:
    if token:
        return GIS(org_url or os.getenv("AGOL_ORG_URL"), token=token)
    # eksisterende username/password fallback fra .env
    ...
```

---

### 5. `src/arcpy_processor/landxml_to_agol.py` — UTVIDE

CLI-argumenter utvides med:
```
--token     OAuth2 access_token (valgfri; overstyrer .env credentials)
--org-url   AGOL org-URL (valgfri; overstyrer AGOL_ORG_URL i .env)
```

`connect()` kalles med `token=args.token, org_url=args.org_url` hvis oppgitt.

---

### 6. `src/arcpy_processor/tverrprofil_to_agol.py` — NY

CLI-orkestrator for å publisere tverrprofil-punkter med SVG-vedlegg.

**CLI-argumenter:**
```
--stations-json  Sti til JSON-fil med stasjonsdata (fra run_pipeline)
--svgs-dir       Katalog med SVG-filer navngitt {stasjon_m:.2f}.svg
--name           Tjenestenavn i AGOL
--folder         Mappe i AGOL (default: "")
--token          OAuth2 access_token
--org-url        AGOL org-URL
```

**Stasjons-JSON-format** (produseres av `run_pipeline`):
```json
[
  {"station_m": 10.0, "profil_nr": "0010.00", "x": 86105.2, "y": 1283560.1, "z": 130.5},
  ...
]
```

**Arbeidsflyt:**
1. Les stasjons-JSON
2. Opprett scratchGDB + PointZ feature class `{dataset_name}_tverrprofiler`
   - Felt: `stasjon_m DOUBLE`, `profil_nr TEXT 20`, SHAPE PointZ EPSG:25833
3. Populer med `InsertCursor`
4. Aktiver attachments: `arcpy.management.EnableAttachments(fc_path)`
5. For hvert punkt: `arcpy.management.AddAttachment(fc_path, oid, svg_path)`
6. `upload_and_publish(gis, gdb_path, name, folder)` → feature service
7. Print JSON til stdout (samme format som `landxml_to_agol.py` + `feature_count`)

---

### 7. `src/ifc_processor/pipeline.py` — UTVIDE

`run_pipeline()` utvides til å skrive `stations.json` til output-katalogen:

```python
# Eksisterende retur-dict utvides med:
{
  "svgs": [...],
  "stations_json": "output/stations.json",   # NY
  "centerline": "output/centerline.geojson",
  "metadata": "output/metadata.json"
}
```

`stations.json` inneholder liste med `{station_m, profil_nr, x, y, z}` for hver generert seksjon.

---

## Frontend

### Filer

Eksisterende frontend bruker vanilla JavaScript (ingen Vue/React) med ArcGIS Maps SDK og Vite. Nye filer følger samme mønster:

```
web/
  index.html          ← ERSTATT: ny landing page (wizard)
  job.html            ← NY: jobstatus-side
  src/
    main.js           ← ERSTATT: wizard-logikk + auth
    job.js            ← NY: polling + fremdriftslinje
```

### Landing Page — Wizard

**Steg 1: Logg inn**
- "Logg inn med ArcGIS Online"-knapp → `GET /auth/login`
- Etter callback: vis innlogget bruker (navn + org), aktiver steg 2

**Steg 2: Last opp filer**
- IFC-filvelger (.ifc, maks 500 MB)
- LandXML-filvelger (.xml)
- Begge kreves for å gå til steg 3

**Steg 3: Innstillinger + kjør**
- Tverrprofilintervall (m): tallinnput, default 10, min 1, maks 100
- Tjenestenavn i AGOL: tekstfelt (pre-utfylt fra IFC-filnavn, sanitert)
- "Kjør pipeline"-knapp → `POST /api/jobs` (multipart) → naviger til `/jobs/{id}`

### Jobstatus-side

- Henter `GET /api/jobs/{id}` hvert 2. sekund
- Fremdriftslinje (0–100 %)
- Statuslogg: liste med gjennomførte + pågående steg
- Ved `status: "done"`: vis to lenker — senterlinje i AGOL + tverrprofiler i AGOL
- Ved `status: "failed"`: vis feilmelding fra `error`-feltet

---

## AGOL-output

```
Brukerens AGOL-konto
├── {navn}_senterlinje     ← PolylineZ Feature Service
│     1 rad: name, feat_length, SHAPE (3D linje, EPSG:25833)
│
└── {navn}_tverrprofiler   ← PointZ Feature Service (attachments aktivert)
      N rader — én per stasjon:
        stasjon_m   DOUBLE
        profil_nr   TEXT 20
        SHAPE       PointZ (EPSG:25833)
      + SVG-vedlegg per punkt
```

---

## Feilhåndtering

- `POST /api/jobs`: returnerer 401 hvis ikke innlogget, 400 ved ugyldig input
- Subprosesser: `stderr` fanges og lagres som `job.error` ved ikke-null exit code
- Token-utløp: ved `401` fra AGOL under jobb → `status: "failed"`, melding "AGOL-token utløpt, logg inn på nytt"
- Filstørrelsesgrense: 500 MB (konfigurerbar via `UPLOAD_MAX_MB` i .env)

---

## Teststrategi

- `tests/test_api_auth.py` — OAuth2-flyt mockes (ingen ekte AGOL-kall): state-generering, callback-validering, session-håndtering
- `tests/test_api_jobs.py` — `POST /api/jobs` og `GET /api/jobs/{id}` med mockede subprosesser
- `tests/test_tverrprofil_to_agol.py` — mock arcpy + arcgis, verifiser punktgeometri og attachment-kall
- `tests/test_pipeline_stations_json.py` — verifiser at `run_pipeline` skriver korrekt `stations.json`
- Frontend: manuell røyktest (ingen Jest/Playwright i MVP)

---

## Utenfor scope

- Refresh token-rotasjon (token-utløp etter én jobb er akseptabelt i MVP)
- Multi-bruker job-køen (én jobb om gangen er tilstrekkelig)
- HTTPS i produksjon (lokal utvikling med HTTP)
- E-postvarsling ved ferdig jobb
- Slette/gjenbruke eksisterende AGOL-tjenester
