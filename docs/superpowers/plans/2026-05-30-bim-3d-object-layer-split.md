# Plan: Skill ut BIM3D til eget feature layer for 3D Object Layer-publisering

**Dato:** 2026-05-30
**Gren:** worktree-bim-kategorisering
**Status:** Under arbeid

## Bakgrunn / rotårsak

Dagens `merge_and_categorize` legger `bim_3d` (multipatch) **og** `bim_plan`
(2D-polygon) i én GDB som publiseres som **én** hosted feature service med to lag.

ArcGIS Online tillater bare å publisere et **3D Object Layer** fra et hosted
feature layer der **alle lagene har samme geometritype** (alle multipatch eller
alle punkt). Den blandede geometrien (multipatch + polygon) blokkerer derfor
3D-publisering. Kilde: <https://doc.arcgis.com/en/arcgis-online/manage-data/publish-scenes.htm>.

## Teknisk begrensning (verifisert)

- Installert `arcgis` er **2.4.2** (ArcGIS Pro-miljøet).
- `Item.publish()` lager scene-tjenester **kun fra scene-pakker (.slpk/.spk)** —
  ikke fra et hosted feature layer. (Verifisert mot pakkekilden.)
- AGOL-knappen «Publish 3D object layer» kaller en REST `publish`-operasjon hvis
  eksakte `publishParameters`-form for multipatch→sceneService **ikke er offentlig
  dokumentert**. Kan ikke testes live i denne sesjonen (ingen token).

→ Selve scene-publiseringen gjøres **best-effort med myk degradering**, på samme
måte som resten av pipelinen (`done_with_warnings`, best-effort opprydding).

## Mål

1. `bim_3d` publiseres som et **eget multipatch-only** hosted feature layer
   (den «associated feature layer» som et 3D Object Layer kan bygges på).
2. Best-effort: publiser et 3D Object Scene Layer fra det feature-laget.
   Feiler det → returner feature-layer-URL + tydelig neste-steg (ett-klikks
   manuell publisering i AGOL).
3. `bim_plan` publiseres som et **eget** 2D feature layer.
4. Bakoverkompatibelt: `result["url"]` = scene-URL hvis publisert, ellers
   3D-feature-layer-URL (så `state.bim_url` nedstrøms fortsatt funker).

## Endringer per komponent

### `src/arcpy_processor/converter.py`
- `merge_and_categorize(...)` returnerer **tuple** `(gdb_3d, gdb_plan)`.
  - `gdb_3d` (`bim_3d.gdb`): kun multipatch-FC `bim_3d` med kategori-felt.
  - `gdb_plan` (`bim_plan.gdb`): kun 2D-FC `bim_plan` (fотavtrykk + kategori-join).

### `src/arcpy_processor/publisher.py`
- Ny `publish_3d_object_layer(gis, feature_service_item, name, folder)`:
  best-effort REST `publish` mot brukerens content-endepunkt. Returnerer
  scene-URL ved suksess, `None` ved feil (logger advarsel + neste-steg).
- `upload_and_publish` er uendret (gjenbrukes av `tverrprofil_to_agol`).

### `src/arcpy_processor/bim_to_agol.py`
- Sjekk navn for `{name}` og `{name}_plan`.
- Publiser `gdb_3d` som `{name}` → 3D-feature-layer (associated).
- Best-effort scene-publisering → scene-URL/None.
- Publiser `gdb_plan` som `{name}_plan` → 2D-feature-layer.
- Resultat: `url`, `bim_3d_url`, `bim_scene_url`, `bim_plan_url`, `layer_count`, …

### Nedstrøms (lett)
- `job_runner.JobState`: nye `bim_plan_url`, `bim_scene_url`.
- `server.py` get_job/list_jobs: ta med de nye feltene.
- `web/src/job.js`: vis plan-lenke + scene-lenke når satt.

## Testing
- Oppdater `test_bim_converter.py` til 2-GDB-retur.
- Oppdater `test_bim_to_agol.py` til 2-tjeneste-flyt + scene-best-effort.
- Ny test for `publish_3d_object_layer` (suksess + myk degradering).
- Hele suiten grønn (mock-basert; ingen live AGOL).

## Gjenstår etter denne planen (krever live AGOL)
- Verifisere at REST-payloaden for scene-publisering faktisk treffer; ev.
  justere `publishParameters` etter første live-kjøring.
