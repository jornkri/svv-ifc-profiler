# Experience Builder — Profilutforsker (hyllevare)

**Dato:** 2026-05-20
**Status:** Godkjent

## Sammendrag

Lager en ArcGIS Experience Builder-app som repliserer kjerneopplevelsen i den custom-bygde `profilutforsker.html`, utelukkende med innebygde XB-widgets. SVG-tverrprofiler lagres som attachments på AGOL-feature layeret og URL-en skrives tilbake som attributtfelt slik at Embedded Content-widgeten kan vise dem uten avhengighet av lokal backend.

Lengdeprofil-canvas og interaktiv hover/måleverktøy er **utenfor scope** — disse krever custom widgets og hører ikke hjemme i en hyllevare-XB-app.

---

## Seksjon 1 — Overordnet arkitektur

```
publish_to_agol()          (eksisterende — uendret)
        │
        ▼
upload_svg_attachments()   (ny)
  ├─ for hvert stasjon-feature (OID):
  │    POST /FeatureServer/{layerId}/{oid}/addAttachment  → attachment_id
  │    svg_url = f"{service_url}/{layer_id}/{oid}/attachments/{att_id}"
  └─ applyEdits: skriv svg_url tilbake på alle features (batch)
        │
        ▼
create_or_update_experience()  (ny)
  ├─ søk etter eksisterende XB-item (tittel/tag)
  ├─ WebExperience(gis).create() eller hent eksisterende
  ├─ sett datasources → centerline_item + sections_item
  ├─ last opp config.json-mal med widget-oppsett (item-ID-er erstattet)
  └─ publiser
```

XB-appen er selvbetjent på AGOL etter publisering — ingen lokal FastAPI-backend kreves.

---

## Seksjon 2 — XB-app layout og widgets

Tre-sone-layout (ligner custom-appen):

| Sone | Widget | Funksjon |
|------|--------|----------|
| Venstre sidebar (280 px) | **List widget** | Stasjonsliste sortert på `station_m`. Klikk velger stasjon. |
| Sentrum | **Map widget** | Senterlinje (LineString) + stasjonspunkter (Point). Klikk velger stasjon. |
| Høyre panel (460 px) | **Feature Info widget** + **Embedded Content widget** | Metadata øverst, SVG-tverrprofil under |

Interaksjon: klikk på stasjon i kart **eller** i liste → begge høyre-panel-widgets oppdateres via XB datasource linking (ingen egendefinert JS).

### Map widget
- Lag 1: Centerline feature layer — linje med SVV-blå farge
- Lag 2: Sections feature layer — punkt, symbolisert med stasjonsnummer-label
- Popup aktivert med Arcade-formatert innhold (se seksjon 3)
- Basemap: Geodata Kanvas (tile layer) som standard

### List widget
- Datakilde: Sections feature layer
- Sortering: `station_m` ASC
- Visning per rad: `profil_nr` (stor) + `station_m` formatert som `km X.XXX` (liten)
- Filterfelt øverst for stasjonssøk

### Feature Info widget
- Viser følgende felt for valgt stasjon:
  - `profil_nr` — Profilnummer
  - `station_m` — Stasjonering (m)
  - `elevation` — Kotehøyde (m.o.h.)
  - `segment_classes` — Tverrprofilklasser

### Embedded Content widget
- URL-kilde: `$feature.svg_url` (attributtfelt)
- Høyde: 300 px, bredde: 100%
- Fallback-tekst hvis `svg_url` er tom: "Tverrprofil ikke tilgjengelig"

---

## Seksjon 3 — Arcade-uttrykk

### Popup-tittel på stasjonspunkter
```arcade
"Profil " + Text($feature.profil_nr) + "  ·  " +
Text(Round($feature.station_m, 0)) + " m  ·  " +
Text(Round($feature.elevation, 1)) + " m.o.h."
```

### Formatert km-visning i Feature Info
```arcade
"km " + Text(Round($feature.station_m / 1000, 3), "0.000")
```

### SVG-URL for Embedded Content
```arcade
$feature.svg_url
```
Python skriver ferdig URL under publisering; ingen token-konstruksjon nødvendig i Arcade.

---

## Seksjon 4 — Python API-arbeidsflyt (nye funksjoner)

### `upload_svg_attachments(sections_layer, output_dir)`

```
Input:  sections_layer (FeatureLayer), output_dir (Path med SVG-filer)
For hvert feature i layeret:
  1. Finn SVG-fil matching svg_filename-attributtet
  2. POST attachment via sections_layer.attachments.add(oid, svg_path)
  3. Hent attachment_id fra respons
  4. Bygg url = f"{service_url}/{oid}/attachments/{attachment_id}"
  5. Samle {oid: url} i dict
Batch-oppdater svg_url-felt via sections_layer.edit_features(updates=[...])
```

### `create_or_update_experience(gis, name, centerline_item, sections_item)`

```
Input:  gis (GIS), name (str), item-referanser
1. Søk: gis.content.search(f'title:"{name}" type:"Web Experience"')
2. Hvis ikke funnet: WebExperience(gis).create(title=name, tags=[...])
3. Last inn config.json-mal fra templates/xb_config_template.json
4. Erstatt plassholdere:
     __CENTERLINE_ITEM_ID__  → centerline_item.id
     __SECTIONS_ITEM_ID__    → sections_item.id
     __SERVICE_URL__         → sections_item.url
5. Sett datasources via experience.datasources = [...]
6. Last opp config: experience._draft = config_dict
   # NB: _draft er en udokumentert intern egenskap i ArcGIS Python API 2.x.
   # Alternativ: last opp config.json direkte via item.update(data=json_str)
7. Publiser: experience.publish()
Output: experience item URL
```

### `templates/xb_config_template.json`

Plassering: `templates/xb_config_template.json` i prosjektets rotmappe.

**Manuelt prerequisites-steg** (gjøres én gang av utvikler, ikke av Python):
1. Bygg XB-appen i browser-editoren (AGOL Experience Builder)
2. Last ned config.json fra XB-editoren (Share → Download)
3. Erstatt item-ID-er og service-URL-er med plassholdere:
   - Alle forekomster av centerline-item-ID → `__CENTERLINE_ITEM_ID__`
   - Alle forekomster av sections-item-ID → `__SECTIONS_ITEM_ID__`
   - Service base-URL → `__SERVICE_URL__`
4. Lagre som `templates/xb_config_template.json` og commit

---

## Seksjon 5 — Filer som endres / opprettes

| Fil | Endring |
|-----|---------|
| `src/arcpy_processor/publisher.py` | Legg til `upload_svg_attachments()` og `create_or_update_experience()` |
| `templates/xb_config_template.json` | Ny — XB config-mal (lages manuelt i browser, deretter parameteriseres) |
| `src/api/job_runner.py` | Kall `upload_svg_attachments()` og `create_or_update_experience()` etter vellykket publisering |
| `src/api/server.py` | Evt. nytt endepunkt `GET /api/jobs/{id}/xb_url` for å returnere XB-app-URL |

---

## Utenfor scope

- Lengdeprofil-canvas
- Hover-avlesning og punkt-til-punkt måleverktøy
- Dark mode i XB-appen
- Basemap-velger i XB (kan konfigureres manuelt i XB-editoren)
- Opplasting av normalprofil-SVG
