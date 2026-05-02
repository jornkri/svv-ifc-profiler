# IFC-profiler backend — design

**Dato:** 2026-05-02
**Fokus:** Python-backend som parser IFC-vegmodell og produserer R700-konforme tverrprofiler som SVG

---

## Kontekst

Statens vegvesen bruker IFC-modeller (BIM) i planleggingsfasen. Systemet skal lese disse modellene og produsere tverrprofiler iht. håndbok R700 – Tegningsgrunnlag. Testmodell: `UEH-32-A-55075_05 Vei Kleverud_IFC.ifc` (IFC 2X3, 28 TIN-elementer, ETRS 1989 NTM Zone 11).

---

## Scope (MVP)

Backend-pipeline som:
1. Leser IFC-fil og klassifiserer TINer etter vegkomponent
2. Mottar senterlinje som ekstern input (GeoJSON, LandXML eller CSV)
3. Kutter tverrsnitt hvert 10 m langs senterlinjen
4. Produserer R700-konform SVG per stasjon
5. Eksporterer senterlinje som GeoJSON og metadata som JSON

**Ikke i scope for MVP:** FastAPI-endepunkter, ArcGIS JS-frontend, lengdeprofil, georeferering i selve pipelinen.

---

## Senterlinje-prioritering (hybrid)

```
1. IFC 4.3           → IfcAlignment direkte fra IFC-filen
2. IFC 2X3 (vanlig)  → brukerlevert fil: GeoJSON / LandXML / CSV
3. Ingen senterlinje → ArcPy (Windows pre-prosessering) eller Shapely medialakse
```

Primærscenario for testmodell: brukersupplert GeoJSON. ArcPy-steget kjøres separat på Windows og produserer senterlinje-GeoJSON som input til backend.

---

## Modulstruktur

```
src/ifc_processor/
  ifc_reader.py          – åpne IFC, lese TIN-geometri, klassifisere etter Layer-property
  centerline.py          – hybrid senterlinje-provider
  cross_section.py       – snittplan per stasjon, Shapely-skjæring mot TINer
  renderer.py            – R700-konform SVG
  pipeline.py            – orkestrerer hele kjøringen
  georef.py              – .prj-lesing og koordinattransform (ikke del av MVP-pipeline)
```

---

## TIN-klassifisering

Alle vegelementer er `IfcBuildingElementProxy` med eiendomssett `Attributter`. `Layer`-egenskapen identifiserer vegkomponent:

| Layer-prefix      | Vegkomponent        | R700-stil              |
|-------------------|---------------------|------------------------|
| `*Planum*`        | Vegdekke/underbygning | Solid, tykk linje    |
| `*Skjæring*`      | Skjæringsskråning   | Solid linje            |
| `*Fylling*`       | Fyllingsskråning    | Solid linje            |
| `*Grøfteskråning*`| Grøft               | Solid linje            |
| ukjent            | Terreng/annet       | Stiplet linje          |

Intern representasjon per TIN: `np.ndarray` med shape `(N, 3, 3)` (N triangler × 3 hjørnepunkter × XYZ).

---

## Pipeline-dataflyt

```
IFCReader
  → list[TINLayer]           (klassifiserte triangelnett)

CenterlineProvider
  → np.ndarray (M, 3)        (ordnet punktrekke X,Y,Z)

StationSampler
  → list[Station]            (posisjon + retningsvektor hvert 10 m)

CrossSectionCutter
  → list[CrossSection]       (tagged polylinjer per stasjon per lag)
    (numpy/trimesh for plan-triangel-skjæring i 3D → Shapely for 2D-sammenstilling)

R700Renderer
  → list[Path]               (SVG-filer)

pipeline.py
  → centerline.geojson
  → metadata.json
  → output/station_XXXXX.svg (én per stasjon)
```

---

## R700-krav til SVG-output (tverrprofil)

Per R700 håndbok, se også `~/.claude/skills/r700-tverrprofil/SKILL.md`:

- Rutenett-bakgrunn (graf-papir), 1:200 default
- Profilnummer over hvert profil
- Horisontal referanselinje med kotehøyde
- Solid linje for konstruert veggeometri (Planum, skjæringer, fyllinger)
- Stiplet linje for eksisterende terreng
- Ingen tegnforklaring per profil — kun én per ark
- Tittelfelt nede til høyre (rotert 90° for U-tegninger)

---

## Feilhåndtering

| Scenario | Håndtering |
|---|---|
| Ingen senterlinje funnet | Tydelig feilmelding med liste over godkjente inputformater |
| Snittplan gir tomt resultat | Logg advarsel for stasjonen, hopp over, fortsett |
| IFC mangler Layer-property | Fall tilbake til navn-basert klassifisering, logg uklassifiserte |
| Ukjent IFC-versjon | Prøv 4.3-strategi, fall tilbake til 2X3-strategi |

---

## Testing

- `tests/test_ifc_reader.py` — parse testfil, verifiser at 28 TINer leses og klassifiseres korrekt
- `tests/test_cross_section.py` — syntetisk TIN + kjent senterlinje → verifiser snittgeometri
- `tests/test_renderer.py` — verifiser at SVG inneholder påkrevde R700-elementer (rutenett, kotehøyde, profilnummer)
- `tests/test_pipeline.py` — ende-til-ende med testfil → verifiser at output-filer produseres

---

## Avhengigheter

```
ifcopenshell    – IFC-parsing
shapely         – 2D-geometri, medialakse, 2D-linje-sammenstilling
numpy           – koordinatberegninger, TIN-representasjon, 3D-snitting
trimesh         – plan-mesh-interseksjon (3D)
matplotlib      – SVG-rendering (allerede i requirements.txt, savefig svg)
```

Koordinatsystem: all intern geometri i IFC lokalt koordinatsystem. Georeferering (ETRS 1989 NTM Zone 11 via .prj) er et separat forhåndstrinn og berører ikke selve profil-geometrien.
