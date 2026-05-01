# SVV – Modellbasert prosjektstyring i planleggingsfasen

Webapplikasjon for å generere tverrprofiler og lengdeprofiler fra IFC-modeller (BIM) av veg, i henhold til Statens vegvesens håndbok **R700 – Tegningsgrunnlag**.

## Mål

Brukeren laster opp en IFC-fil av en vegmodell. Systemet:

1. Genererer en **2D-representasjon** av BIM-modellen.
2. Genererer **tverrprofiler hvert 10. meter** langs vegens senterlinje, formatert i tråd med håndbok R700. Intervallet skal på sikt være brukerstyrt fra opplastningsklienten.
3. Genererer et **lengdeprofil** av vegen.
4. Viser resultatet i en webapp der brukeren klikker langs senterlinjen og ser tilhørende tverrprofil.

Referanse: [Håndbok R700](https://www.trondelagfylke.no/contentassets/86d1228933954878b2a4c511884ecec6/handbok-r700.pdf) (også lagret i `docs/`).

## Arkitektur

```
[Bruker] → [Web frontend (ArcGIS JS API)]
              │
              │ Last opp IFC + spør på posisjon
              ▼
        [Backend API (FastAPI)]
              │
              ▼
      [IFC-prosessor (Python)]
        ├─ ifcopenshell      → parse IFC
        ├─ Shapely / NumPy   → geometri, snitt, beregninger
        ├─ ArcGIS API        → eksport til ArcGIS-formater
        └─ matplotlib        → render tverrprofil-bilder
```

### Komponenter

- **`src/ifc_processor/`** – Python-pakke som leser IFC, ekstraherer senterlinje, kutter tverrsnitt og genererer profiler.
- **`src/api/`** – FastAPI-tjeneste som tar imot IFC-opplastinger og leverer resultater til frontend.
- **`web/`** – Frontend basert på [ArcGIS Maps SDK for JavaScript](https://developers.arcgis.com/javascript/latest/) for kartvisning og brukerinteraksjon.
- **`docs/`** – Håndbok R700 og prosjektdokumentasjon.
- **`tests/`** – Tester for IFC-prosessoren.

## Kom i gang

### Forutsetninger

- Python 3.11+
- Node.js 20+ (for frontend)
- Anbefalt: virtuelt miljø (`venv` eller `conda`)

### Installasjon

```bash
# Klone repoet
git clone <repo-url>
cd "SVV - Modellbasert prosjektstyring i planleggingsfasen"

# Python
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt

# Frontend
cd web
npm install
```

### Kjøring (utvikling)

```bash
# Backend
uvicorn src.api.server:app --reload --port 8000

# Frontend (i et eget terminalvindu)
cd web
npm run dev
```

## Om ArcGIS-stacken

Prosjektet bruker **ArcGIS Maps SDK for JavaScript** i frontend og **ArcGIS API for Python** (pakken `arcgis`) for backend-integrasjon. `ArcPy` krever ArcGIS Pro + Windows-lisens og er valgfri – aktiver den i `requirements.txt` kun dersom du faktisk trenger Pro-spesifikke verktøy.

## Status

Tidlig prototype. Foreløpig fokus: IFC-parsing og generering av tverrprofiler.

## Lisens

Internt prosjekt – Geodata AS / Statens vegvesen.
