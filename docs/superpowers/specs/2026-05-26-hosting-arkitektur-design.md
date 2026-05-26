# Hosting-arkitektur: SVV IFC Profiler

**Dato:** 2026-05-26  
**Status:** Referanse — ikke implementert ennå

## Sammendrag

Appen skal hostes online slik at den ikke er avhengig av at utviklers maskin kjører. Den valgte arkitekturen er en **split Linux API + Windows Worker** med Azure som primær plattform. Alternativ med FME Flow Hosted er også vurdert og dokumentert.

---

## Kontekst og begrensninger

### arcpy-avhengigheten
Kodebasen har to klart adskilte lag:

- **`src/ifc_processor/`** — ren Python (ifcopenshell, shapely, trimesh). Kjører på Linux uten lisenskrav.
- **`src/arcpy_processor/`** — bruker `arcgis` Python API (pip-installerbar) + `arcpy` for tre operasjoner:
  - `landxml_to_agol.py` — oppretter File GDB og publiserer senterlinje til AGOL
  - `tverrprofil_to_agol.py` — oppretter File GDB og publiserer tverrprofilpunkter til AGOL
  - `bim_to_agol.py` — konverterer IFC til 3D Object Layer (C-plan, R700). **Krever ArcGIS Pro.**

arcpy krever Windows + ArcGIS Pro-lisens og kan ikke containeriseres på Linux.

### Bruksmønster
Burst-preget: rolig mesteparten av tiden, av og til mange jobber (f.eks. ved prosjektleveranser). Windows-ressurser bør bare være aktive ved faktisk behov.

---

## Valgt arkitektur: Split Linux API + Windows Worker (Alternativ B)

```
  Bruker (nettleser)
        │ HTTPS
  ┌─────▼──────────────────────────────────┐
  │  Frontend — Azure Static Web Apps       │  Gratis tier, Vite-bygg
  └─────┬──────────────────────────────────┘
        │ HTTPS/REST
  ┌─────▼──────────────────────────────────┐
  │  API — Azure Container Apps (Linux)     │
  │  FastAPI · AGOL OAuth · job-status      │
  │  ifc_processor (IFC-parsing, SVG-gen)   │
  │                                         │
  │  POST /api/jobs → Blob + Service Bus    │
  │  GET  /api/jobs/{id} → leser fra Blob   │
  └─────┬──────────────────────┬────────────┘
        │                      │
        ▼                      ▼
  Azure Blob Storage    Azure Service Bus
  jobs/{job_id}/        Jobbkø: { job_id,
   model.ifc             access_token,
   centerline.xml        org_url, flags }
   output/                     │
    *.svg                      │ trigger
    metadata.json        ┌─────▼──────────────────────────────┐
    job_state.json       │  Windows Worker — Azure VM           │
    agol_urls.json       │  Windows Server 2022 + ArcGIS Pro   │
        ▲                │                                      │
        └────────────────│  1. Last ned fra Blob                │
                         │  2. landxml_to_agol → AGOL           │
                         │  3. tverrprofil_to_agol → AGOL       │
                         │  4. bim_to_agol (hvis flagget)       │
                         │  5. Skriv resultater til Blob        │
                         │                                      │
                         │  Auto-start ved jobb i kø            │
                         │  Auto-stop etter ~15 min tomgang     │
                         └──────────────────┬───────────────────┘
                                            ▼
                                     ArcGIS Online
                                  Feature Layers, XB-app
```

### Azure-tjenester og kostnader

| Tjeneste | Formål | Estimert kostnad |
|---|---|---|
| Azure Static Web Apps | Frontend (Vite-bygg) | Gratis |
| Azure Container Apps | FastAPI API + ifc_processor | ~0 kr idle (scale-to-zero) |
| Azure VM (Standard_D2s_v3) | Windows Worker med ArcGIS Pro | ~kr 3–5/time VM er på |
| Azure Blob Storage | Delt fillagring (erstatter `uploads/`) | ~kr 5–20/mnd |
| Azure Service Bus | Jobbkø API → Worker | ~kr 5/mnd |
| Azure Key Vault | Hemmeligheter (SECRET_KEY, AGOL creds) | ~kr 5/mnd |

**Estimert totalkostnad ved burst-bruk (ca. 10 timer Windows VM per måned): ~kr 60–100/mnd.**

### Nøkkeländringer i koden

Eksisterende forretningslogikk endres **ikke**. Endringene er i infrastrukturlaget:

1. **`src/api/storage.py`** (ny) — abstraksjon over Azure Blob som erstatter direkte `Path`-operasjoner på `uploads/`. Faller tilbake til lokal disk i dev-modus.

2. **`src/api/job_runner.py`** (endret) — Fase 1 (ifc_processor) beholdes på API-siden. Fase 2 (arcpy-subprocess-kallene) erstattes med én Service Bus-melding.

3. **`src/arcpy_processor/worker.py`** (ny) — liten Python-prosess som kjører på Windows VM, lytter på Service Bus, laster ned fra Blob, kaller eksisterende `arcpy_processor`-moduler som subprosesser (identisk med dagens `job_runner`-logikk).

4. **`server.py`** — SVG-serving bytter fra `FileResponse` til Blob-URL-er (eller proxy via API).

Alt i `src/ifc_processor/` og `src/arcpy_processor/` forblir uendret.

---

## Alternativ: FME Flow Hosted (ikke valgt, men vurdert)

FME Flow Hosted (fme.safe.com/platform) ble vurdert som alternativ til Windows Worker.

**Kritisk begrensning:** FME Flow Hosted kjører på Linux (Ubuntu) og støtter **ikke** arcpy. Safe Software bekrefter dette eksplisitt: *"FME Flow Hosted does not support the Python interpreters included with ArcGIS products."*

### Hva FME Flow Hosted faktisk kan gjøre

FME har innebygde transformere for XML, GeoJSON og ArcGIS Online Feature Services. To av tre arcpy-steg kan potensielt erstattes med FME-workspaces uten arcpy:

| Steg | FME Flow Hosted | Kommentar |
|---|---|---|
| `landxml_to_agol` | Kan erstattes | XML Reader → AGOL Feature Service Writer |
| `tverrprofil_to_agol` | Kan erstattes | GeoJSON Reader → AGOL Feature Service Writer |
| `bim_to_agol` (C-plan) | **Kan ikke erstattes** | Krever ArcGIS Pro-verktøy for 3D Object Layer |

### FME Remote Engine (hybrid)

FME Flow Hosted støtter Remote Engines: en Windows-maskin kobles til som engine for arcpy-avhengige jobber. Dette er konseptuelt likt den valgte arkitekturen, men bruker FME som orkestrator i stedet for Service Bus + worker.py. Krever fortsatt Windows-maskin.

### Hvorfor ikke valgt nå

- Krever bygging av FME-workspaces for å erstatte eksisterende Python-kode
- BIM/C-plan-steget trenger uansett arcpy
- Legger til FME som avhengighet i arkitekturen
- Den valgte løsningen (Windows VM) er enklere og bevarer all eksisterende kode

**FME Flow Hosted er et godt alternativ dersom BIM/C-plan-steget på et tidspunkt kan droppes fra den hostede løsningen** (f.eks. holdes som et lokalt steg i ArcGIS Pro).

---

## Forutsetninger for implementering

- Azure-abonnement tilgjengelig (Geodata)
- ArcGIS Pro Named User-lisens tilgjengelig for en service-konto (brukes på Windows VM)
- AGOL OAuth-app registrert med riktig redirect URI for hosted domene
- FME Flow-abonnement (om FME-alternativet velges senere)
