# BIM-kategorisering (3D + C-plan) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publiser IFC-BIM som én feature service med to fagmessig kategoriserte lag — `bim_3d` (multipatch) og `bim_plan` (polygon-fотavtrykk) — i stedet for Esris rå geometriklasser.

**Architecture:** Klassifisering i ren Python (ifcopenshell, testbar uten ArcGIS Pro) produserer `{GlobalId: ClassifiedElement}`. ArcPy slår sammen multipatch-FC-ene til ett 3D-lag, joiner kategori via IFC-GlobalId, og avleder et 2D-fотavtrykkslag. Begge lag bærer `kategori, fag_gruppe, ifc_klasse, navn`.

**Tech Stack:** Python 3, ifcopenshell, arcpy (Windows/ArcGIS Pro), pytest (`slow`-markør for sample-tester), arcgis (publisering).

**Spec:** `docs/superpowers/specs/2026-05-29-bim-kategorisering-c-plan.md`

---

## Filstruktur

| Fil | Ansvar |
|---|---|
| `src/ifc_processor/bim_classifier.py` | **Ny.** Ren klassifisering: `classify_from_fields()`, `classify_ifc()`, `ClassifiedElement`. Ingen arcpy. |
| `tests/test_bim_classifier.py` | **Ny.** Enhetstester (rene) + slow-test mot ekte sample. |
| `src/arcpy_processor/converter.py` | **Utvides.** `_resolve_kategori()`, `_find_guid_field()`, `merge_and_categorize()`. |
| `tests/test_bim_converter.py` | **Ny.** Pure-helper-tester + mocket arcpy-orkestrering. |
| `src/arcpy_processor/bim_to_agol.py` | **Endres.** Kall `classify_ifc` + `merge_and_categorize`, publiser den nye 2-lags-GDB-en. |
| `tests/test_bim_to_agol.py` | **Ny.** Mocket integrasjonstest av CLI-arbeidsflyten. |

---

## Task 1: `classify_from_fields()` — ren klassifiseringsregel

**Files:**
- Create: `src/ifc_processor/bim_classifier.py`
- Test: `tests/test_bim_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bim_classifier.py
import pytest
from src.ifc_processor.bim_classifier import classify_from_fields


@pytest.mark.parametrize("ifc_klasse,pt,ot,name,expected", [
    ("IfcKerb", None, None, "12200 | 3.07 | H.Tillegg 7", ("Kantstein", "Vegbane")),
    ("IfcDistributionChamberElement", "TRENCH", None, "12200 | 4.01 | H. Grøft 1", ("Grøft", "Drenering")),
    ("IfcCourse", "USERDEFINED", "TRAFFICLANE_SURFACE", "12200 | 1.01 | H. Kjørefelt 1", ("Kjørefelt", "Vegbane")),
    ("IfcCourse", "USERDEFINED", "ROADSHOULDER_SURFACE", "12200 | 2.01 | H. Skulder 1", ("Skulder", "Vegbane")),
    ("IfcCourse", "USERDEFINED", None, "12200 | Slitelag", ("Slitelag", "Vegoverbygning")),
    ("IfcCourse", "USERDEFINED", None, "12200 | Bindlag 1", ("Bindlag", "Vegoverbygning")),
    ("IfcCourse", "USERDEFINED", None, "12200 | Bærelag 2", ("Bærelag", "Vegoverbygning")),
    ("IfcCourse", "USERDEFINED", None, "12200 | -1.02 | V. breddeutvidelse", ("Kjørefelt", "Vegbane")),
    ("IfcPavement", "RIGID", None, "12200|RIGID", ("Slitelag", "Vegoverbygning")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | Forsterkningslag 1", ("Forsterkningslag", "Vegoverbygning")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | Filterlag", ("Filterlag", "Vegoverbygning")),
    ("IfcEarthworksFill", "USERDEFINED", "ROUNDING", "12200 | Avrunding | Solid", ("Avrunding", "Terreng")),
    ("IfcEarthworksFill", "SLOPEFILL", None, "12200 | 7.11 | H. Fylling 11", ("Fylling", "Terreng")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | -6.11 | V. Jordskj. 11", ("Skjæring", "Terreng")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | -5.11 | V. Fjellskj. 11", ("Skjæring", "Terreng")),
    ("IfcEarthworksCut", "USERDEFINED", None, "12200 | Constructionbed | InCutRock", ("Skjæring", "Terreng")),
    ("IfcEarthworksCut", "OVEREXCAVATION", None, "12200 | Dypsprenging | Solid", ("Skjæring", "Terreng")),
    ("IfcEarthworksFill", "EMBANKMENT", None, "12200 | Fyllingslag | Solid", ("Forsterket grunn", "Underbygning")),
    ("IfcReinforcedSoil", "REPLACED", None, "12200 | Fyllingslag | Solid", ("Forsterket grunn", "Underbygning")),
    ("IfcEarthworksFill", "SUBGRADEBED", None, "12200 | Constructionbed | OnTerrainSurfaceSoil", ("Planum", "Underbygning")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | SubgradeSurface Inside Pavement", ("Planum", "Underbygning")),
    ("IfcFooBar", None, None, "noe ukjent", ("Uklassifisert", "Annet")),
])
def test_classify_from_fields(ifc_klasse, pt, ot, name, expected):
    assert classify_from_fields(ifc_klasse, pt, ot, name) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bim_classifier.py -v`
Expected: FAIL med `ModuleNotFoundError: No module named 'src.ifc_processor.bim_classifier'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ifc_processor/bim_classifier.py
from __future__ import annotations

from dataclasses import dataclass

# IFC-produkter uten solid geometri — utelates fra både 3D- og plan-laget.
SKIP_CLASSES = {"IfcAnnotation", "IfcRoadPart", "IfcRoad", "IfcSite", "IfcGeomodel"}


@dataclass
class ClassifiedElement:
    global_id: str
    ifc_klasse: str
    navn: str
    kategori: str
    fag_gruppe: str


def classify_from_fields(ifc_klasse: str, predefined_type: str | None,
                         object_type: str | None, name: str | None) -> tuple[str, str]:
    """Returner (kategori, fag_gruppe) fra IFC-klasse + type-koder + navn.

    Baseres primært på PredefinedType/ObjectType (rene ASCII-koder). Navn-feltet
    har encoding-artefakter (æ/ø/å som mojibake), så nøkkelordmatch bruker
    ASCII-trygge delstrenger (f.eks. "relag" for Bærelag).
    """
    k = ifc_klasse or ""
    pt = (predefined_type or "").upper()
    ot = (object_type or "").upper()
    n = (name or "").lower()

    if k == "IfcKerb":
        return ("Kantstein", "Vegbane")
    if k == "IfcDistributionChamberElement" or pt == "TRENCH":
        return ("Grøft", "Drenering")
    if k == "IfcCourse":
        if ot == "TRAFFICLANE_SURFACE" or "breddeutvidelse" in n:
            return ("Kjørefelt", "Vegbane")
        if ot == "ROADSHOULDER_SURFACE":
            return ("Skulder", "Vegbane")
        if "slitelag" in n:
            return ("Slitelag", "Vegoverbygning")
        if "bindlag" in n:
            return ("Bindlag", "Vegoverbygning")
        if "relag" in n:  # Bærelag (æ kan være mojibake)
            return ("Bærelag", "Vegoverbygning")
        return ("Kjørefelt", "Vegbane")
    if k == "IfcPavement":
        return ("Slitelag", "Vegoverbygning")
    if k == "IfcReinforcedSoil":
        return ("Forsterket grunn", "Underbygning")
    if k in ("IfcEarthworksFill", "IfcEarthworksCut"):
        if "forsterkningslag" in n:
            return ("Forsterkningslag", "Vegoverbygning")
        if "filterlag" in n:
            return ("Filterlag", "Vegoverbygning")
        if "avrunding" in n:
            return ("Avrunding", "Terreng")
        if any(t in n for t in ("jordskj", "fjellskj", "incutsoil", "incutrock",
                                 "rockcutface", "dypsprenging")):
            return ("Skjæring", "Terreng")
        if "fyllingslag" in n:  # MÅ sjekkes før "fylling" (delstreng-kollisjon)
            return ("Forsterket grunn", "Underbygning")
        if pt in ("SLOPEFILL", "EMBANKMENT") or "fylling" in n:
            return ("Fylling", "Terreng")
        return ("Planum", "Underbygning")  # constructionbed / subgrade / øvrig
    return ("Uklassifisert", "Annet")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bim_classifier.py -v`
Expected: PASS (alle parametriserte tilfeller)

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/bim_classifier.py tests/test_bim_classifier.py
git commit -m "feat(bim): klassifiser IFC-element til fag-kategori (ren regel)"
```

---

## Task 2: `classify_ifc()` — les IFC, bygg GlobalId-oppslag

**Files:**
- Modify: `src/ifc_processor/bim_classifier.py`
- Test: `tests/test_bim_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bim_classifier.py — legg til øverst
from pathlib import Path
from src.ifc_processor.bim_classifier import classify_ifc, ClassifiedElement

SAMPLE = Path(__file__).parent.parent / "samples" / "m_f_veg_12200_Veg.ifc"


@pytest.mark.slow
def test_classify_ifc_against_sample():
    if not SAMPLE.exists():
        pytest.skip("12200 IFC-sample mangler")
    result = classify_ifc(SAMPLE)

    # Returnerer dict keyet på GlobalId med ClassifiedElement-verdier
    assert isinstance(result, dict)
    assert all(isinstance(v, ClassifiedElement) for v in result.values())

    kats = [ce.kategori for ce in result.values()]
    grupper = {ce.fag_gruppe for ce in result.values()}

    # Alle 92 grøfter (IfcDistributionChamberElement) skal være Grøft/Drenering
    grofter = [ce for ce in result.values() if ce.ifc_klasse == "IfcDistributionChamberElement"]
    assert len(grofter) == 92
    assert all(ce.kategori == "Grøft" and ce.fag_gruppe == "Drenering" for ce in grofter)

    # Forventede fag-grupper er representert
    assert {"Vegoverbygning", "Vegbane", "Underbygning", "Terreng", "Drenering"} <= grupper

    # Annotasjoner/struktur er utelatt
    assert not any(ce.ifc_klasse in {"IfcAnnotation", "IfcRoadPart", "IfcRoad", "IfcSite"}
                   for ce in result.values())

    # Ingenting med solid geometri skal ende som Uklassifisert
    assert kats.count("Uklassifisert") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bim_classifier.py::test_classify_ifc_against_sample -v -m slow`
Expected: FAIL med `ImportError: cannot import name 'classify_ifc'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ifc_processor/bim_classifier.py — legg til import øverst og funksjon nederst
import ifcopenshell


def classify_ifc(ifc_path) -> dict[str, ClassifiedElement]:
    """Les IFC-fil og returner {GlobalId: ClassifiedElement} for alle produkter
    med solid geometri (annotasjoner/struktur utelates)."""
    ifc = ifcopenshell.open(str(ifc_path))
    out: dict[str, ClassifiedElement] = {}
    for el in ifc.by_type("IfcProduct"):
        cls = el.is_a()
        if cls in SKIP_CLASSES:
            continue
        gid = el.GlobalId
        navn = getattr(el, "Name", None) or ""
        pt = getattr(el, "PredefinedType", None)
        pt = str(pt) if pt is not None else None
        ot = getattr(el, "ObjectType", None)
        kategori, fag_gruppe = classify_from_fields(cls, pt, ot, navn)
        out[gid] = ClassifiedElement(gid, cls, navn, kategori, fag_gruppe)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bim_classifier.py -v -m slow`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/bim_classifier.py tests/test_bim_classifier.py
git commit -m "feat(bim): classify_ifc bygger GlobalId-oppslag fra IFC"
```

---

## Task 3: `_resolve_kategori()` — ren oppslagshjelper i converter

**Files:**
- Modify: `src/arcpy_processor/converter.py`
- Test: `tests/test_bim_converter.py`

> **Merk:** `converter.py` importerer `arcpy` på modulnivå. For at pure-helper-testen
> skal kjøre uten ArcGIS Pro, mock `arcpy` i `sys.modules` *før* import (samme mønster
> som `tests/test_ifc_cl_to_agol.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bim_converter.py
from __future__ import annotations
import sys
from unittest.mock import MagicMock

# arcpy må stubbes før converter importeres (modulnivå-import)
sys.modules.setdefault("arcpy", MagicMock())
sys.modules.setdefault("arcpy.management", sys.modules["arcpy"].management)

from src.ifc_processor.bim_classifier import ClassifiedElement
from src.arcpy_processor.converter import _resolve_kategori


def test_resolve_kategori_found():
    cls = {"GUID1": ClassifiedElement("GUID1", "IfcKerb", "Kantstein 1", "Kantstein", "Vegbane")}
    assert _resolve_kategori("GUID1", cls) == ("Kantstein", "Vegbane", "IfcKerb", "Kantstein 1")


def test_resolve_kategori_missing():
    assert _resolve_kategori("UKJENT", {}) == ("Uklassifisert", "Annet", "", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bim_converter.py -v`
Expected: FAIL med `ImportError: cannot import name '_resolve_kategori'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/arcpy_processor/converter.py — legg til etter importene
from src.ifc_processor.bim_classifier import ClassifiedElement


def _resolve_kategori(global_id: str,
                      classification: dict[str, ClassifiedElement]) -> tuple[str, str, str, str]:
    """Returner (kategori, fag_gruppe, ifc_klasse, navn) for en GlobalId.
    Ukjent GlobalId → Uklassifisert (mister ingenting stille)."""
    ce = classification.get(global_id)
    if ce is None:
        return ("Uklassifisert", "Annet", "", "")
    return (ce.kategori, ce.fag_gruppe, ce.ifc_klasse, ce.navn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bim_converter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/converter.py tests/test_bim_converter.py
git commit -m "feat(bim): _resolve_kategori-oppslag i converter"
```

---

## Task 4: `_find_guid_field()` — finn IFC-GlobalId-feltet i GDB

**Files:**
- Modify: `src/arcpy_processor/converter.py`
- Test: `tests/test_bim_converter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bim_converter.py — legg til
from unittest.mock import patch
from src.arcpy_processor.converter import _find_guid_field


def _fields(*names):
    out = []
    for n in names:
        f = MagicMock()
        f.name = n
        out.append(f)
    return out


def test_find_guid_field_matches_globalid():
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_fields("OBJECTID", "GlobalId", "Name")):
        assert _find_guid_field("fc") == "GlobalId"


def test_find_guid_field_matches_ifcguid_case_insensitive():
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_fields("OBJECTID", "IFCGUID", "Name")):
        assert _find_guid_field("fc") == "IFCGUID"


def test_find_guid_field_none_when_absent():
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_fields("OBJECTID", "Name", "ObjectType")):
        assert _find_guid_field("fc") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bim_converter.py -k find_guid -v`
Expected: FAIL med `ImportError: cannot import name '_find_guid_field'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/arcpy_processor/converter.py — legg til
def _find_guid_field(fc_path: str) -> str | None:
    """Finn feltet som holder IFC-GlobalId i en feature class (case-insensitivt).
    Returner None hvis ingen kandidat finnes (→ trigger fallback i kaller)."""
    for f in arcpy.ListFields(fc_path):
        if "globalid" in f.name.lower() or "ifcguid" in f.name.lower():
            return f.name
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bim_converter.py -k find_guid -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/converter.py tests/test_bim_converter.py
git commit -m "feat(bim): _find_guid_field lokaliserer IFC-GlobalId-felt i GDB"
```

---

## Task 5: `merge_and_categorize()` — bygg 2-lags utdata-GDB

**Files:**
- Modify: `src/arcpy_processor/converter.py`
- Test: `tests/test_bim_converter.py`

Funksjonen lager en fersk utdata-GDB med nøyaktig to feature classes:
`bim_3d` (multipatch, merge av kilde-FC-ene) og `bim_plan` (polygon-fотavtrykk).
Kategori-feltene fylles via GlobalId-join; fотavtrykket grupperes på en stabil
`bim_id` (= OBJECTID) og får kategori-feltene via `JoinField`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bim_converter.py — legg til
import src.arcpy_processor.converter as conv


def test_merge_and_categorize_orchestration(monkeypatch):
    calls = {"merge": None, "footprint": None, "joinfield": None, "rows": []}

    arcpy = conv.arcpy
    arcpy.reset_mock()

    # CreateFileGDB / Exists
    arcpy.Exists.return_value = False

    # Merge registrerer kall
    def _merge(inputs, output):
        calls["merge"] = (list(inputs), output)
    arcpy.management.Merge.side_effect = _merge

    # ListFields → guid-felt finnes
    gf = MagicMock(); gf.name = "GlobalId"
    monkeypatch.setattr(conv, "_find_guid_field", lambda fc: "GlobalId")

    # UpdateCursor: én rad med GlobalId "G1"
    row = ["G1", None, None, None, None]
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return iter([row])
        def updateRow(self, r): calls["rows"].append(list(r))
    arcpy.da.UpdateCursor.return_value = _Cur()

    def _footprint(in_fc, out_fc, **kw):
        calls["footprint"] = (in_fc, out_fc, kw)
    arcpy.ddd.MultiPatchFootprint.side_effect = _footprint

    def _joinfield(*a, **kw):
        calls["joinfield"] = (a, kw)
    arcpy.management.JoinField.side_effect = _joinfield

    from src.ifc_processor.bim_classifier import ClassifiedElement
    classification = {"G1": ClassifiedElement("G1", "IfcKerb", "Kantstein 1", "Kantstein", "Vegbane")}

    gdb = conv.merge_and_categorize(
        ["/scratch/bim_temp.gdb/ds/Courses", "/scratch/bim_temp.gdb/ds/Kerbs"],
        classification,
        scratch="/scratch",
    )

    assert gdb.endswith("bim_out.gdb")
    # Begge kilde-FC-ene ble merget
    assert len(calls["merge"][0]) == 2
    # Kategori ble skrevet til raden (kategori, fag_gruppe, ifc_klasse, navn)
    assert calls["rows"][0][1:] == ["Kantstein", "Vegbane", "IfcKerb", "Kantstein 1"]
    # Fотavtrykk laget og kategori join-et tilbake
    assert calls["footprint"] is not None
    assert calls["joinfield"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bim_converter.py -k merge_and_categorize -v`
Expected: FAIL med `AttributeError: module ... has no attribute 'merge_and_categorize'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/arcpy_processor/converter.py — legg til
import os  # allerede importert øverst; ikke dupliser

_KAT_FIELDS = [("kategori", 60), ("fag_gruppe", 40), ("ifc_klasse", 60), ("navn", 200)]


def merge_and_categorize(
    fc_paths: list[str],
    classification: dict[str, ClassifiedElement],
    *,
    scratch: str | None = None,
    input_wkid: int | None = None,
    output_wkid: int = 25833,
) -> str:
    """Slå sammen multipatch-FC-er til ett 3D-lag, join kategori via GlobalId,
    og avled et 2D-fотavtrykkslag. Returner sti til utdata-GDB med to FC-er.

    Raises:
        ArcpyProcessorError: BIM_CONVERSION_FAILED ved geometrifeil, eller hvis
        GlobalId-felt mangler (join ikke mulig — se spec for fallback).
    """
    scratch = scratch or arcpy.env.scratchFolder
    out_gdb = os.path.join(scratch, "bim_out.gdb")
    if arcpy.Exists(out_gdb):
        arcpy.management.Delete(out_gdb)
    arcpy.management.CreateFileGDB(scratch, "bim_out.gdb")

    bim_3d = os.path.join(out_gdb, "bim_3d")
    bim_plan = os.path.join(out_gdb, "bim_plan")

    try:
        arcpy.management.Merge(fc_paths, bim_3d)

        guid_field = _find_guid_field(bim_3d)
        if guid_field is None:
            raise ArcpyProcessorError(
                BIM_CONVERSION_FAILED,
                "Fant ikke IFC-GlobalId-felt i GDB — kan ikke joine kategori. "
                "Inspiser feltene (arcpy.ListFields) og koble classify_from_fields "
                "mot ObjectType/Name som fallback (se spec).",
            )

        for fname, flen in _KAT_FIELDS:
            arcpy.management.AddField(bim_3d, fname, "TEXT", field_length=flen)
        arcpy.management.AddField(bim_3d, "bim_id", "LONG")
        arcpy.management.CalculateField(bim_3d, "bim_id", "!OBJECTID!", "PYTHON3")

        cursor_fields = [guid_field, "kategori", "fag_gruppe", "ifc_klasse", "navn"]
        with arcpy.da.UpdateCursor(bim_3d, cursor_fields) as cur:
            for r in cur:
                r[1], r[2], r[3], r[4] = _resolve_kategori(r[0], classification)
                cur.updateRow(r)

        # 2D-fотavtrykk, ett per kildeobjekt (gruppert på stabil bim_id)
        arcpy.ddd.MultiPatchFootprint(bim_3d, bim_plan, group_field="bim_id")
        arcpy.management.JoinField(
            bim_plan, "bim_id", bim_3d, "bim_id",
            ["kategori", "fag_gruppe", "ifc_klasse", "navn"],
        )

        if input_wkid and input_wkid != output_wkid:
            sr = arcpy.SpatialReference(output_wkid)
            for fc in (bim_3d, bim_plan):
                proj = fc + "_p"
                arcpy.management.Project(fc, proj, sr)
                arcpy.management.Delete(fc)
                arcpy.management.Rename(proj, fc)
    except ArcpyProcessorError:
        raise
    except Exception as exc:
        raise ArcpyProcessorError(
            BIM_CONVERSION_FAILED,
            f"Kategorisering/fотavtrykk feilet: {exc}",
        ) from exc

    return out_gdb
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bim_converter.py -v`
Expected: PASS (alle converter-tester)

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/converter.py tests/test_bim_converter.py
git commit -m "feat(bim): merge_and_categorize bygger 2-lags kategorisert GDB"
```

---

## Task 6: Koble inn i `bim_to_agol.main`

**Files:**
- Modify: `src/arcpy_processor/bim_to_agol.py`
- Test: `tests/test_bim_to_agol.py`

CLI-en skal etter `convert_bim` klassifisere IFC-en og bygge 2-lags-GDB-en før
publisering. Den gamle `_gdb_path_from_fcs`-stien erstattes av GDB-en fra
`merge_and_categorize`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bim_to_agol.py
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SAMPLE = Path(__file__).parent.parent / "samples" / "m_f_veg_12200_Veg.ifc"


def test_main_classifies_and_publishes_two_layers(monkeypatch):
    if not SAMPLE.exists():
        pytest.skip("12200 IFC-sample mangler")

    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "/tmp/scratch"
    monkeypatch.setitem(sys.modules, "arcpy", arcpy_mock)
    monkeypatch.setitem(sys.modules, "arcpy.management", arcpy_mock.management)
    monkeypatch.setitem(sys.modules, "arcpy.da", arcpy_mock.da)
    monkeypatch.setitem(sys.modules, "arcpy.ddd", arcpy_mock.ddd)
    monkeypatch.setitem(sys.modules, "arcpy.env", arcpy_mock.env)
    arcgis_mock = MagicMock()
    monkeypatch.setitem(sys.modules, "arcgis", arcgis_mock)
    monkeypatch.setitem(sys.modules, "arcgis.gis", arcgis_mock.gis)

    from src.arcpy_processor import bim_to_agol

    with patch.object(bim_to_agol, "connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.converter.convert_bim",
               return_value=["/s/bim_temp.gdb/ds/Courses"]) as m_conv, \
         patch("src.arcpy_processor.converter.merge_and_categorize",
               return_value="/s/bim_out.gdb") as m_cat, \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value={"status": "ok", "layer_count": 2}) as m_pub:
        with pytest.raises(SystemExit) as exc:
            bim_to_agol.main([
                "--ifc", str(SAMPLE), "--name", "svc", "--folder", "",
            ])
        assert exc.value.code == 0

    m_conv.assert_called_once()
    m_cat.assert_called_once()
    # publiserer GDB-en fra merge_and_categorize, ikke kilde-GDB
    assert m_pub.call_args.args[1] == "/s/bim_out.gdb"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bim_to_agol.py -v`
Expected: FAIL (CLI bruker fortsatt `_gdb_path_from_fcs`, kaller ikke `merge_and_categorize`)

- [ ] **Step 3: Write minimal implementation**

Erstatt i `src/arcpy_processor/bim_to_agol.py` blokken fra `from .converter import ...`
og ut publiseringskallet (linjene som i dag importerer converter, kjører
`convert_bim`/`delete_empty_fcs`/`_gdb_path_from_fcs` og kaller `upload_and_publish`):

```python
        from .auth import connect
        from .converter import convert_bim, merge_and_categorize
        from .publisher import check_name_available, upload_and_publish
        from src.ifc_processor.bim_classifier import classify_ifc

        gis = connect(token=args.token, org_url=args.org_url)
        check_name_available(gis, args.name, args.folder)

        stem = Path(args.ifc).stem
        dataset_name = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:50]
        if dataset_name and dataset_name[0].isdigit():
            dataset_name = "_" + dataset_name[:49]

        fc_paths = convert_bim(args.ifc, dataset_name,
                               input_wkid=args.input_wkid,
                               output_wkid=args.output_wkid)
        if not fc_paths:
            raise ArcpyProcessorError(
                NO_FEATURES,
                "BIMFileToGeodatabase produserte ingen feature classes. "
                "Sjekk at IFC-filen inneholder geometri.",
            )

        classification = classify_ifc(args.ifc)
        gdb_path = merge_and_categorize(
            fc_paths, classification,
            input_wkid=args.input_wkid, output_wkid=args.output_wkid,
        )

        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        print(json.dumps(result))
        sys.exit(0)
```

> `connect` må være importerbar som `bim_to_agol.connect` for testen. Hvis den i dag
> kun importeres inne i `main`, legg til `from .auth import connect` på modulnivå
> (toppen av fila), og behold den lokale importen om ønskelig.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bim_to_agol.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite (uten slow)**

Run: `python -m pytest -q`
Expected: PASS — ingen regresjon i eksisterende tester.

- [ ] **Step 6: Commit**

```bash
git add src/arcpy_processor/bim_to_agol.py tests/test_bim_to_agol.py
git commit -m "feat(bim): bim_to_agol klassifiserer og publiserer 2 kategoriserte lag"
```

---

## Task 7: Windows-verifisering (krever ArcGIS Pro)

**Files:** ingen kodeendring med mindre GlobalId-feltet mangler.

Dette steget kjøres på Windows med ArcGIS Pro-Python. Det verifiserer den ene
antagelsen planen hviler på: at `BIMFileToGeodatabase` legger igjen et GlobalId-felt.

- [ ] **Step 1: Inspiser felter i en konvertert GDB**

Kjør i ArcGIS Pro sitt Python-miljø (propy), eller via prosjektets venv hvis arcpy er der:

```python
import arcpy
arcpy.env.workspace = r"<scratch>\bim_temp.gdb\<dataset>"
for fc in arcpy.ListFeatureClasses():
    print(fc, "→", [f.name for f in arcpy.ListFields(fc)])
```

Bekreft at det finnes et felt med `GlobalId` eller `IfcGUID` i navnet.

- [ ] **Step 2: Kjør hele pipelinen mot 12200-sample**

Bruk den eksisterende dev-kommandoen / `dev.ps1`-oppskriften for BIM-publisering
(samme som dagens 3D-publisering, nå med ny kategorisering), f.eks.:

```powershell
python -m src.arcpy_processor.bim_to_agol --ifc "samples\m_f_veg_12200_Veg.ifc" --name "<testnavn>" --folder ""
```

Forventet JSON på stdout med `"layer_count": 2`.

- [ ] **Step 3: Verifiser i AGOL**

Åpne feature service-itemet. Bekreft to lag (`bim_3d`, `bim_plan`), og at
`kategori`-feltet inneholder verdier som Grøft, Bindlag, Bærelag, Fylling, Skjæring.

- [ ] **Step 4 (kun ved manglende GlobalId-felt): wire fallback**

Hvis Step 1 viste at GlobalId-felt mangler: utvid `merge_and_categorize` til å lese
`ObjectType` + `Name` (+ kilde-FC-navn som ifc_klasse-approksimasjon) og kalle
`classify_from_fields` direkte, i stedet for å feile. Legg til en mocket test for
denne grenen før implementering (TDD), og commit.

- [ ] **Step 5: Commit (kun hvis kode endret)**

```bash
git add -A
git commit -m "fix(bim): fallback-klassifisering når GlobalId-felt mangler"
```

---

## Self-review-notater

- **Spec-dekning:** klassifisering (T1–T2), 2-lags GDB med kategori-attributter
  (T5), GlobalId-join + risiko/fallback (T4, T5, T7), publisering (T6), testing
  mot ekte sample (T2) og mock (T3–T6). Web er eksplisitt utenfor scope.
- **Skjæring** er én kategori (jord+fjell slått sammen) — jf. oppdatert spec.
- **Type-konsistens:** `ClassifiedElement(global_id, ifc_klasse, navn, kategori,
  fag_gruppe)` brukt likt i T1, T3, T5; `_resolve_kategori` returnerer
  (kategori, fag_gruppe, ifc_klasse, navn) i samme rekkefølge som cursor-feltene.
