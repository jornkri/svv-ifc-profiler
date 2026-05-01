# Arkitektur

## Dataflyt

```
   ┌─────────┐   IFC-fil   ┌────────────┐   GeoJSON      ┌──────────────┐
   │ Bruker  │ ──────────▶ │  FastAPI   │ ─────────────▶ │ ArcGIS JS    │
   │ (web)   │             │  /upload   │   senterlinje  │ kart         │
   └─────────┘             └─────┬──────┘                └───────┬──────┘
                                 │                               │ klikk
                                 ▼                               ▼
                       ┌──────────────────┐         ┌──────────────────────┐
                       │ ifc_processor    │         │ /section?station=...  │
                       │ ─ centerline     │         │  → PNG av tverrprofil │
                       │ ─ cross_section  │ ─────── │     iht. R700         │
                       │ ─ longitudinal   │         └──────────────────────┘
                       │ ─ renderer       │
                       └──────────────────┘
```

## Tekniske valg

### IFC-parsing: ifcopenshell
Open source, godt vedlikeholdt, støtter både IFC 2x3, IFC 4 og IFC 4.3 (Road).
For IFC 4.3-modeller bruker vi `IfcAlignment` direkte til senterlinje. For eldre
modeller må senterlinje rekonstrueres geometrisk.

### Geometri: Shapely + trimesh + NumPy
- `shapely` for 2D-operasjoner (skjæring, buffring, projeksjon).
- `trimesh` for 3D mesh-operasjoner (mesh-mesh slicing).
- `numpy` for koordinatberegninger og transformer.

### GIS-eksport: ArcGIS API for Python (`arcgis`)
Brukes for å publisere senterlinje + profilmetadata som feature layers, hvis vi
trenger ArcGIS Online/Enterprise-integrasjon. For ren visning i nettleseren via
ArcGIS Maps SDK for JavaScript kan vi nøye oss med GeoJSON levert via FastAPI.

### Hvorfor ikke ArcPy?
ArcPy er låst til ArcGIS Pro + Windows + lisens, og er ikke pip-installerbar.
Det gjør CI/CD og kollegaers oppsett vanskelig. Vi bruker ArcPy kun hvis et
spesifikt verktøy fra Pro mangler ekvivalent ellers — og da som valgfri
avhengighet.

### Backend: FastAPI
- Enkel async-håndtering av filopplasting.
- Automatisk OpenAPI-dokumentasjon.
- Lett å deploye lokalt og i container senere.

### Frontend: ArcGIS Maps SDK for JavaScript + Vite
- Vite gir rask hot reload under utvikling.
- `@arcgis/core` som ES-modul gir bedre tree-shaking enn AMD-varianten.

## Åpne spørsmål

1. **Hvor mye av R700 må visualiseres bokstavelig?** Linjetyper, fargekoder og
   tittelfelt bør rekkes ut av første prototype, men full ramme + målestokkboks
   kan komme senere.
2. **Klassifisering av elementer i tverrsnittet:** R700 skiller mellom
   vegoverflate, skulder, grøft, fylling, skjæring osv. Hvor mye av dette ligger
   som metadata i typiske SVV IFC-leveranser? Må undersøkes med en testmodell.
3. **Ytelse:** Store IFC-modeller (>500 MB) krever bakgrunnskø (Celery/RQ/Arq)
   og fremgangsindikator i UI.
4. **Koordinatsystem:** SVV bruker EUREF89/UTM 32–35. Verifiser at IFC-modellens
   `IfcGeometricRepresentationContext.CoordinateOperation` finnes og er korrekt,
   ellers må georeferering konfigureres manuelt.
