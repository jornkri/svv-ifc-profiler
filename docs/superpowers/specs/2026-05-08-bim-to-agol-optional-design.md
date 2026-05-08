# Design: Valgfri BIM-publisering som 3D GIS-lag

**Dato:** 2026-05-08  
**Status:** Godkjent

## Oversikt

Legger til en valgfri fase i den eksisterende pipeline-flyten som publiserer BIM-data (IFC) som et 3D Object Layer i ArcGIS Online, via det eksisterende `bim_to_agol.py`-scriptet. Aktiveres med en enkel checkbox i frontend.

## Scope

- Valgfritt tillegg til eksisterende jobb — ingen ny jobb-type eller ny UI-flyt
- BIM-laget navngis automatisk som `{name}_bim`
- Feiler BIM-steget stoppes ikke jobben — senterlinje og tverrprofiler er allerede publisert

## Endringer per komponent

### `src/arcpy_processor/bim_to_agol.py`

Legg til `--token` og `--org-url` som CLI-argumenter, identisk med mønsteret i `landxml_to_agol.py` og `tverrprofil_to_agol.py`. `connect()` kalles med disse verdiene i stedet for å lese fra miljøvariabler.

### `src/api/job_runner.py`

- `JobState` får nytt felt: `bim_url: str | None = None`
- Ny jobbstatus: `done_with_warnings` — brukes når BIM-fasen feiler men resten er OK
- `run_job()` får ny parameter: `publish_bim: bool`
- Fremdriftsfordeling når `publish_bim=True`:
  - 0–50 %: IFC-prosessering
  - 50–70 %: senterlinje til AGOL
  - 70–80 %: tverrprofiler til AGOL
  - 80–100 %: BIM til AGOL
- Fremdriftsfordeling når `publish_bim=False` (uendret):
  - 0–50 %: IFC-prosessering
  - 50–75 %: senterlinje til AGOL
  - 75–100 %: tverrprofiler til AGOL
- Hvis `publish_bim=True` og BIM-subprocess feiler: logg advarsel, sett `state.status = "done_with_warnings"`, sett `state.error` til feilmeldingen, men ikke kast exception

### `src/api/server.py`

- `POST /api/jobs` får nytt skjemafelt: `publish_bim: bool = Form(False)`
- Feltet sendes videre til `job_runner.run_job()`
- `GET /api/jobs/{id}` inkluderer `bim_url` i responsen

### `web/index.html`

- Nytt checkbox-element med `id="publish-bim"` og tilhørende label under intervallinputen i steg 3

### `web/src/main.js`

- Les `document.getElementById("publish-bim")` som `publishBimCheckbox`
- `fd.append("publish_bim", publishBimCheckbox.checked ? "true" : "false")` sendes med skjemaet

### `web/src/job.js`

- Viser tredje resultlenke «Åpne BIM-lag i AGOL» hvis `bim_url` er satt i jobbstatus
- Ved `done_with_warnings`: vis resultater som normalt, men vis en synlig advarsel om at BIM-publisering feilet, med feilmeldingen fra `state.error`

## Dataflytt

```
POST /api/jobs (publish_bim=true)
    ↓
job_runner.run_job(publish_bim=True)
    ↓
[fase 1] run_pipeline()          → stations.json + SVGer
[fase 2] landxml_to_agol CLI     → centerline_url
[fase 3] tverrprofil_to_agol CLI → sections_url
[fase 4] bim_to_agol CLI         → bim_url  (eller done_with_warnings ved feil)
    ↓
GET /api/jobs/{id}
→ { status, centerline_url, sections_url, bim_url }
```

## Feilhåndtering

| Scenario | Resultat |
|---|---|
| BIM-subprocess feiler | `done_with_warnings`, `bim_url=null`, `error` inneholder feilmelding |
| BIM-subprocess lykkes | `done`, `bim_url` satt |
| `publish_bim=false` | Uendret fra nåværende flyt |

## Testing

- Eksisterende tester skal fortsatt passere uten endring
- Ny enhetstest for `run_job` med `publish_bim=True` der BIM-subprocess lykkes
- Ny enhetstest for `run_job` med `publish_bim=True` der BIM-subprocess feiler → verifiser `done_with_warnings`
- Ny test for `POST /api/jobs` med `publish_bim` i skjemaet
- Ny test for `bim_to_agol.main()` med `--token` / `--org-url`
