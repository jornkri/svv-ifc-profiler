# ArcPy BIM-til-ArcGIS-Online — implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standalone Python-modul (`src/arcpy_processor/`) som konverterer en IFC-fil til georefererte multipatch-features og publiserer dem som 3D Object Layer til ArcGIS Online.

**Architecture:** ArcPy konverterer IFC → midlertidig fil-GDB (scratchFolder) → tøm features slettes → GDB zippes og lastes opp til AGOL via `arcgis`-pakken → publiseres som hosted feature service (multipatch = 3D Object Layer). CLI-inngangspunkt printer JSON til stdout/stderr.

**Tech Stack:** Python 3.11, ArcPy (ArcGIS Pro 3.x), arcgis Python API, python-dotenv, pytest + unittest.mock

---

## Filstruktur

```
src/arcpy_processor/
  __init__.py          ← eksporter public API
  errors.py            ← ArcpyProcessorError + feilkoder
  auth.py              ← les .env, returner autentisert GIS-instans
  converter.py         ← BIMFileToGeodatabase, slett tomme, reproject
  publisher.py         ← sjekk navn, zip GDB, upload, publish til AGOL
  bim_to_agol.py       ← CLI-orkestrator + JSON-output

tests/
  test_arcpy_auth.py          ← mock arcgis.GIS
  test_arcpy_publisher.py     ← mock GIS.content.search + add + publish
  test_arcpy_cli.py           ← test argparse + JSON stdout/stderr
```

`.env.example` — oppdateres med `AGOL_*`-variabler.

---

## Felles datakontraktar

```python
# Returverdi fra run_pipeline() i bim_to_agol.py ved suksess:
{
  "status": "ok",
  "url": str,            # FeatureServer-URL
  "item_id": str,
  "item_url": str,
  "feature_count": int,
  "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
  "published_at": str    # ISO 8601
}

# Returverdi ved feil (til stderr):
{
  "status": "error",
  "code": str,           # se errors.py
  "message": str
}
```

---

## Oppgave 1: Felles feil-typer og modulstruktur

**Filer:**
- Opprett: `src/arcpy_processor/__init__.py`
- Opprett: `src/arcpy_processor/errors.py`

- [ ] **Steg 1.1: Opprett `errors.py`**

```python
# src/arcpy_processor/errors.py
from __future__ import annotations


class ArcpyProcessorError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"status": "error", "code": self.code, "message": self.message}


# Feilkoder
IFC_NOT_FOUND       = "IFC_NOT_FOUND"
ARCPY_UNAVAILABLE   = "ARCPY_UNAVAILABLE"
AUTH_FAILED         = "AUTH_FAILED"
NAME_EXISTS         = "NAME_EXISTS"
BIM_CONVERSION_FAILED = "BIM_CONVERSION_FAILED"
NO_FEATURES         = "NO_FEATURES"
PUBLISH_FAILED      = "PUBLISH_FAILED"
```

- [ ] **Steg 1.2: Opprett `__init__.py`**

```python
# src/arcpy_processor/__init__.py
from .errors import ArcpyProcessorError

__all__ = ["ArcpyProcessorError"]
```

- [ ] **Steg 1.3: Skriv test**

```python
# tests/test_arcpy_auth.py  (vi starter filen her, bygger på den i oppgave 2)
from src.arcpy_processor.errors import ArcpyProcessorError, NAME_EXISTS


def test_error_has_code_and_message():
    err = ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")
    assert err.code == NAME_EXISTS
    assert err.message == "Navn finnes allerede"


def test_error_to_dict():
    err = ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")
    d = err.to_dict()
    assert d == {"status": "error", "code": "NAME_EXISTS", "message": "Navn finnes allerede"}
```

- [ ] **Steg 1.4: Kjør test**

```bash
python -m pytest tests/test_arcpy_auth.py -v
```
Forventet: 2 PASS

- [ ] **Steg 1.5: Commit**

```bash
git add src/arcpy_processor/ tests/test_arcpy_auth.py
git commit -m "feat: add arcpy_processor module skeleton and error types"
```

---

## Oppgave 2: auth.py — ArcGIS Online-autentisering

**Filer:**
- Opprett: `src/arcpy_processor/auth.py`
- Endre: `tests/test_arcpy_auth.py`

- [ ] **Steg 2.1: Skriv feilviklende tester**

Legg til i `tests/test_arcpy_auth.py`:

```python
import os
from unittest.mock import patch, MagicMock
import pytest
from src.arcpy_processor.errors import ArcpyProcessorError, AUTH_FAILED


def test_connect_uses_username_password(monkeypatch):
    monkeypatch.setenv("AGOL_USERNAME", "testuser")
    monkeypatch.setenv("AGOL_PASSWORD", "testpass")
    monkeypatch.setenv("AGOL_ORG_URL", "https://www.arcgis.com")

    mock_gis = MagicMock()
    with patch("src.arcpy_processor.auth.GIS", return_value=mock_gis) as mock_cls:
        from src.arcpy_processor.auth import connect
        gis = connect()
        mock_cls.assert_called_once_with(
            "https://www.arcgis.com", "testuser", "testpass"
        )
        assert gis is mock_gis


def test_connect_raises_auth_failed_on_exception(monkeypatch):
    monkeypatch.setenv("AGOL_USERNAME", "bad")
    monkeypatch.setenv("AGOL_PASSWORD", "bad")
    monkeypatch.setenv("AGOL_ORG_URL", "https://www.arcgis.com")

    with patch("src.arcpy_processor.auth.GIS", side_effect=Exception("Invalid credentials")):
        from src.arcpy_processor import auth
        import importlib; importlib.reload(auth)
        with pytest.raises(ArcpyProcessorError) as exc_info:
            auth.connect()
        assert exc_info.value.code == AUTH_FAILED


def test_connect_raises_when_env_missing(monkeypatch):
    monkeypatch.delenv("AGOL_USERNAME", raising=False)
    monkeypatch.delenv("AGOL_PASSWORD", raising=False)

    from src.arcpy_processor import auth
    import importlib; importlib.reload(auth)
    with pytest.raises(ArcpyProcessorError) as exc_info:
        auth.connect()
    assert exc_info.value.code == AUTH_FAILED
```

- [ ] **Steg 2.2: Kjør tester for å bekrefte at de feiler**

```bash
python -m pytest tests/test_arcpy_auth.py -v
```
Forventet: `ImportError` (auth.py finnes ikke)

- [ ] **Steg 2.3: Implementer `auth.py`**

```python
# src/arcpy_processor/auth.py
from __future__ import annotations

import os

from arcgis.gis import GIS

from .errors import ArcpyProcessorError, AUTH_FAILED


def connect() -> GIS:
    """Returner autentisert GIS-instans fra .env-variabler.

    Leser AGOL_USERNAME, AGOL_PASSWORD og AGOL_ORG_URL.
    Feiler med AUTH_FAILED hvis variabler mangler eller login feiler.
    """
    username = os.getenv("AGOL_USERNAME")
    password = os.getenv("AGOL_PASSWORD")
    org_url = os.getenv("AGOL_ORG_URL", "https://www.arcgis.com")

    if not username or not password:
        raise ArcpyProcessorError(
            AUTH_FAILED,
            "AGOL_USERNAME og AGOL_PASSWORD må settes i .env-filen.",
        )

    try:
        return GIS(org_url, username, password)
    except Exception as exc:
        raise ArcpyProcessorError(
            AUTH_FAILED,
            f"Kunne ikke logge inn på ArcGIS Online ({org_url}): {exc}",
        ) from exc
```

- [ ] **Steg 2.4: Kjør tester**

```bash
python -m pytest tests/test_arcpy_auth.py -v
```
Forventet: alle 5 tester PASS

- [ ] **Steg 2.5: Commit**

```bash
git add src/arcpy_processor/auth.py tests/test_arcpy_auth.py
git commit -m "feat: add AGOL authentication via .env credentials"
```

---

## Oppgave 3: converter.py — BIM-konvertering, sletting og reproject

**Filer:**
- Opprett: `src/arcpy_processor/converter.py`
- Opprett: `tests/test_arcpy_converter.py`

ArcPy er ikke pip-installerbar, så alle tester mocker `arcpy`. De kjøres kun der ArcPy er tilgjengelig.

- [ ] **Steg 3.1: Skriv feilviklende tester**

```python
# tests/test_arcpy_converter.py
from __future__ import annotations
import sys
from unittest.mock import patch, MagicMock, call
import pytest

# Simuler at arcpy ikke er installert i test-miljøet
arcpy_mock = MagicMock()
sys.modules.setdefault("arcpy", arcpy_mock)
sys.modules.setdefault("arcpy.conversion", arcpy_mock.conversion)
sys.modules.setdefault("arcpy.management", arcpy_mock.management)
sys.modules.setdefault("arcpy.env", arcpy_mock.env)

from src.arcpy_processor.errors import ArcpyProcessorError, BIM_CONVERSION_FAILED, NO_FEATURES


def test_convert_bim_calls_bimfile_to_geodatabase():
    arcpy_mock.env.scratchFolder = "C:/scratch"
    arcpy_mock.management.CreateFileGDB.return_value = None
    arcpy_mock.conversion.BIMFileToGeodatabase.return_value = None
    arcpy_mock.env.workspace = ""
    arcpy_mock.ListFeatureClasses.return_value = ["Planum", "Skjaering"]
    arcpy_mock.SpatialReference.return_value = MagicMock()

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    fcs = converter.convert_bim("test.ifc", "test_dataset", wkid=25833)
    arcpy_mock.conversion.BIMFileToGeodatabase.assert_called_once()
    assert len(fcs) == 2


def test_delete_empty_fcs_removes_zero_count():
    arcpy_mock.management.GetCount.side_effect = lambda fc: [0] if fc == "Empty" else [5]
    arcpy_mock.management.Delete.return_value = None

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    remaining = converter.delete_empty_fcs(["Planum", "Empty"], "C:/scratch/bim.gdb/ds")
    assert remaining == ["Planum"]
    arcpy_mock.management.Delete.assert_called_once()


def test_delete_empty_fcs_raises_no_features_when_all_empty():
    arcpy_mock.management.GetCount.return_value = [0]
    arcpy_mock.management.Delete.return_value = None

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    with pytest.raises(ArcpyProcessorError) as exc_info:
        converter.delete_empty_fcs(["A", "B"], "C:/scratch/bim.gdb/ds")
    assert exc_info.value.code == NO_FEATURES


def test_convert_bim_raises_on_arcpy_error():
    arcpy_mock.management.CreateFileGDB.return_value = None
    arcpy_mock.conversion.BIMFileToGeodatabase.side_effect = Exception("Ugyldig IFC")

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    with pytest.raises(ArcpyProcessorError) as exc_info:
        converter.convert_bim("bad.ifc", "ds", wkid=25833)
    assert exc_info.value.code == BIM_CONVERSION_FAILED
```

- [ ] **Steg 3.2: Kjør tester for å bekrefte at de feiler**

```bash
python -m pytest tests/test_arcpy_converter.py -v
```
Forventet: `ImportError` (converter.py finnes ikke)

- [ ] **Steg 3.3: Implementer `converter.py`**

```python
# src/arcpy_processor/converter.py
from __future__ import annotations

import os
import logging
from pathlib import Path

import arcpy

from .errors import ArcpyProcessorError, BIM_CONVERSION_FAILED, NO_FEATURES

logger = logging.getLogger(__name__)


def convert_bim(ifc_path: str, dataset_name: str, wkid: int = 25833) -> list[str]:
    """Konverter IFC-fil til feature classes i scratchGDB.

    Returns:
        Liste med fulle stier til feature classes i scratchGDB.

    Raises:
        ArcpyProcessorError: BIM_CONVERSION_FAILED hvis konvertering feiler.
    """
    scratch = arcpy.env.scratchFolder
    gdb_name = "bim_temp.gdb"
    gdb_path = os.path.join(scratch, gdb_name)

    try:
        arcpy.management.CreateFileGDB(scratch, gdb_name)
        sr = arcpy.SpatialReference(wkid)
        arcpy.conversion.BIMFileToGeodatabase(
            str(ifc_path), gdb_path, dataset_name, spatial_reference=sr
        )
    except Exception as exc:
        raise ArcpyProcessorError(
            BIM_CONVERSION_FAILED,
            f"BIMFileToGeodatabase feilet for '{ifc_path}': {exc}",
        ) from exc

    dataset_path = os.path.join(gdb_path, dataset_name)
    arcpy.env.workspace = dataset_path
    fcs = arcpy.ListFeatureClasses() or []
    logger.info("BIMFileToGeodatabase produserte %d feature classes", len(fcs))
    return [os.path.join(dataset_path, fc) for fc in fcs]


def delete_empty_fcs(fc_paths: list[str], dataset_path: str) -> list[str]:
    """Slett feature classes uten features. Returner gjenstående.

    Raises:
        ArcpyProcessorError: NO_FEATURES hvis alle er tomme.
    """
    remaining = []
    for fc_path in fc_paths:
        count = int(arcpy.management.GetCount(fc_path)[0])
        if count == 0:
            arcpy.management.Delete(fc_path)
            logger.debug("Slettet tom FC: %s", fc_path)
        else:
            remaining.append(fc_path)
            logger.debug("Beholder FC med %d features: %s", count, fc_path)

    if not remaining:
        raise ArcpyProcessorError(
            NO_FEATURES,
            "Alle feature classes var tomme etter konvertering. "
            "Sjekk at IFC-filen inneholder geometri.",
        )
    return remaining
```

- [ ] **Steg 3.4: Kjør tester**

```bash
python -m pytest tests/test_arcpy_converter.py -v
```
Forventet: alle 4 tester PASS

- [ ] **Steg 3.5: Commit**

```bash
git add src/arcpy_processor/converter.py tests/test_arcpy_converter.py
git commit -m "feat: add BIM converter with empty-feature cleanup"
```

---

## Oppgave 4: publisher.py — navnesjekk, zip, upload og publish

**Filer:**
- Opprett: `src/arcpy_processor/publisher.py`
- Opprett: `tests/test_arcpy_publisher.py`

- [ ] **Steg 4.1: Skriv feilviklende tester**

```python
# tests/test_arcpy_publisher.py
from __future__ import annotations
import json
from unittest.mock import MagicMock, patch
import pytest
from src.arcpy_processor.errors import ArcpyProcessorError, NAME_EXISTS, PUBLISH_FAILED


def _make_gis(existing_titles: list[str] = []) -> MagicMock:
    gis = MagicMock()
    items = [MagicMock(title=t) for t in existing_titles]
    gis.content.search.return_value = items
    return gis


def test_check_name_raises_name_exists():
    gis = _make_gis(existing_titles=["Vei_Kleverud"])
    from src.arcpy_processor.publisher import check_name_available
    with pytest.raises(ArcpyProcessorError) as exc_info:
        check_name_available(gis, "Vei_Kleverud", "SVV")
    assert exc_info.value.code == NAME_EXISTS


def test_check_name_passes_when_free():
    gis = _make_gis(existing_titles=["AnnetNavn"])
    from src.arcpy_processor.publisher import check_name_available
    check_name_available(gis, "Vei_Kleverud", "SVV")  # skal ikke kaste


def test_publish_returns_metadata():
    gis = _make_gis()
    mock_item = MagicMock()
    mock_item.id = "abc123"
    mock_item.homepage = "https://www.arcgis.com/home/item.html?id=abc123"
    mock_fs = MagicMock()
    mock_fs.url = "https://services.arcgis.com/xxx/FeatureServer"
    mock_fs.layers = [MagicMock(), MagicMock()]
    mock_item.publish.return_value = mock_fs
    gis.content.add.return_value = mock_item

    with patch("src.arcpy_processor.publisher.shutil.make_archive", return_value="/tmp/bim.zip"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"):
        from src.arcpy_processor import publisher
        import importlib; importlib.reload(publisher)

        result = publisher.upload_and_publish(
            gis=gis,
            gdb_path="/scratch/bim_temp.gdb",
            name="Vei_Kleverud",
            folder="SVV",
        )

    assert result["status"] == "ok"
    assert result["item_id"] == "abc123"
    assert "url" in result
    assert result["feature_count"] == 2


def test_publish_raises_publish_failed_on_error():
    gis = _make_gis()
    gis.content.add.side_effect = Exception("Upload feilet")

    with patch("src.arcpy_processor.publisher.shutil.make_archive", return_value="/tmp/bim.zip"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"):
        from src.arcpy_processor import publisher
        import importlib; importlib.reload(publisher)

        with pytest.raises(ArcpyProcessorError) as exc_info:
            publisher.upload_and_publish(gis, "/scratch/bim_temp.gdb", "Vei_Kleverud", "SVV")
        assert exc_info.value.code == PUBLISH_FAILED
```

- [ ] **Steg 4.2: Kjør tester for å bekrefte at de feiler**

```bash
python -m pytest tests/test_arcpy_publisher.py -v
```
Forventet: `ImportError` (publisher.py finnes ikke)

- [ ] **Steg 4.3: Implementer `publisher.py`**

```python
# src/arcpy_processor/publisher.py
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone

from arcgis.gis import GIS

from .errors import ArcpyProcessorError, NAME_EXISTS, PUBLISH_FAILED

logger = logging.getLogger(__name__)


def check_name_available(gis: GIS, name: str, folder: str) -> None:
    """Feiler med NAME_EXISTS hvis et item med samme tittel finnes i folder."""
    existing = gis.content.search(
        query=f'title:"{name}" AND type:"Feature Service"',
        max_items=10,
    )
    if any(item.title == name for item in existing):
        raise ArcpyProcessorError(
            NAME_EXISTS,
            f"En tjeneste med navn '{name}' finnes allerede i folder '{folder}'. "
            "Velg et annet navn eller slett den eksisterende tjenesten.",
        )


def upload_and_publish(gis: GIS, gdb_path: str, name: str, folder: str) -> dict:
    """Zip GDB, last opp til AGOL og publiser som hosted feature service.

    Returns:
        Dict med status, url, item_id, item_url, feature_count,
        spatial_reference og published_at.

    Raises:
        ArcpyProcessorError: PUBLISH_FAILED hvis noe feiler.
    """
    scratch_dir = os.path.dirname(gdb_path)
    zip_base = os.path.join(scratch_dir, f"{name}_upload")
    zip_path = zip_base + ".zip"

    try:
        shutil.make_archive(zip_base, "zip", scratch_dir, os.path.basename(gdb_path))
        logger.info("Zippet GDB til %s (%.1f MB)", zip_path, os.path.getsize(zip_path) / 1e6)

        item_props = {
            "type": "File Geodatabase",
            "title": name,
            "tags": "IFC,BIM,SVV,tverrprofil",
            "snippet": f"BIM-data konvertert fra IFC: {name}",
        }
        item = gis.content.add(item_props, data=zip_path, folder=folder)
        logger.info("Lastet opp GDB som item %s", item.id)

        fs_item = item.publish()
        logger.info("Publisert feature service: %s", fs_item.url)

        feature_count = len(getattr(fs_item, "layers", []))

        return {
            "status": "ok",
            "url": fs_item.url,
            "item_id": item.id,
            "item_url": item.homepage,
            "feature_count": feature_count,
            "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    except ArcpyProcessorError:
        raise
    except Exception as exc:
        raise ArcpyProcessorError(
            PUBLISH_FAILED,
            f"Publisering til ArcGIS Online feilet: {exc}",
        ) from exc
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
            logger.debug("Slettet midlertidig zip: %s", zip_path)
```

- [ ] **Steg 4.4: Kjør tester**

```bash
python -m pytest tests/test_arcpy_publisher.py -v
```
Forventet: alle 4 tester PASS

- [ ] **Steg 4.5: Commit**

```bash
git add src/arcpy_processor/publisher.py tests/test_arcpy_publisher.py
git commit -m "feat: add AGOL publisher with name check, upload and publish"
```

---

## Oppgave 5: bim_to_agol.py — CLI-orkestrator og JSON-output

**Filer:**
- Opprett: `src/arcpy_processor/bim_to_agol.py`
- Opprett: `tests/test_arcpy_cli.py`
- Endre: `src/arcpy_processor/__init__.py`

- [ ] **Steg 5.1: Skriv feilviklende tester**

```python
# tests/test_arcpy_cli.py
from __future__ import annotations
import json
import sys
from unittest.mock import patch, MagicMock
import pytest


def test_cli_prints_json_on_success(capsys):
    mock_gis = MagicMock()
    success_meta = {
        "status": "ok",
        "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc123",
        "item_url": "https://www.arcgis.com/home/item.html?id=abc123",
        "feature_count": 14,
        "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.bim_to_agol.connect", return_value=mock_gis), \
         patch("src.arcpy_processor.bim_to_agol.check_name_available"), \
         patch("src.arcpy_processor.bim_to_agol.convert_bim", return_value=["fc1", "fc2"]), \
         patch("src.arcpy_processor.bim_to_agol.delete_empty_fcs", return_value=["fc1", "fc2"]), \
         patch("src.arcpy_processor.bim_to_agol._gdb_path_from_fcs", return_value="/scratch/bim_temp.gdb"), \
         patch("src.arcpy_processor.bim_to_agol.upload_and_publish", return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor import bim_to_agol
        import importlib; importlib.reload(bim_to_agol)

        with pytest.raises(SystemExit) as exc_info:
            bim_to_agol.main(["--ifc", "test.ifc", "--name", "TestLag", "--folder", "SVV"])
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "ok"
    assert result["item_id"] == "abc123"


def test_cli_exits_1_and_prints_error_json_on_failure(capsys):
    from src.arcpy_processor.errors import ArcpyProcessorError, NAME_EXISTS

    with patch("src.arcpy_processor.bim_to_agol.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.bim_to_agol.check_name_available",
               side_effect=ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor import bim_to_agol
        import importlib; importlib.reload(bim_to_agol)

        with pytest.raises(SystemExit) as exc_info:
            bim_to_agol.main(["--ifc", "test.ifc", "--name", "TestLag", "--folder", "SVV"])
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["status"] == "error"
    assert error["code"] == NAME_EXISTS


def test_cli_exits_1_when_ifc_not_found(capsys):
    from src.arcpy_processor import bim_to_agol
    import importlib; importlib.reload(bim_to_agol)

    with pytest.raises(SystemExit) as exc_info:
        bim_to_agol.main(["--ifc", "finnes_ikke.ifc", "--name", "X", "--folder", "Y"])
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["code"] == "IFC_NOT_FOUND"
```

- [ ] **Steg 5.2: Kjør tester for å bekrefte at de feiler**

```bash
python -m pytest tests/test_arcpy_cli.py -v
```
Forventet: `ImportError` (bim_to_agol.py finnes ikke)

- [ ] **Steg 5.3: Implementer `bim_to_agol.py`**

```python
# src/arcpy_processor/bim_to_agol.py
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .auth import connect
from .converter import convert_bim, delete_empty_fcs
from .errors import ArcpyProcessorError, IFC_NOT_FOUND, ARCPY_UNAVAILABLE
from .publisher import check_name_available, upload_and_publish

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _gdb_path_from_fcs(fc_paths: list[str]) -> str:
    """Utled GDB-sti fra første FC-sti."""
    # fc_path = /scratch/bim_temp.gdb/dataset/FC
    parts = Path(fc_paths[0]).parts
    gdb_idx = next(i for i, p in enumerate(parts) if p.endswith(".gdb"))
    return str(Path(*parts[:gdb_idx + 1]))


def _check_arcpy() -> None:
    try:
        import arcpy  # noqa: F401
    except ImportError as exc:
        raise ArcpyProcessorError(
            ARCPY_UNAVAILABLE,
            "ArcPy er ikke tilgjengelig. Kjør scriptet fra ArcGIS Pro sitt Python-miljø.",
        ) from exc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Konverter IFC-fil til 3D Object Layer i ArcGIS Online"
    )
    parser.add_argument("--ifc", required=True, help="Sti til .ifc-fil")
    parser.add_argument("--name", required=True, help="Tjenestenavn i ArcGIS Online")
    parser.add_argument("--folder", required=True, help="Folder i ArcGIS Online")
    args = parser.parse_args(argv)

    def _fail(err: ArcpyProcessorError) -> None:
        print(json.dumps(err.to_dict()), file=sys.stderr)
        sys.exit(1)

    # Valider IFC-fil
    if not Path(args.ifc).exists():
        _fail(ArcpyProcessorError(IFC_NOT_FOUND, f"IFC-filen ble ikke funnet: {args.ifc}"))

    try:
        _check_arcpy()
        gis = connect()
        check_name_available(gis, args.name, args.folder)

        dataset_name = Path(args.ifc).stem.replace(" ", "_")[:50]
        fc_paths = convert_bim(args.ifc, dataset_name, wkid=25833)
        fc_paths = delete_empty_fcs(fc_paths, os.path.dirname(fc_paths[0]))
        gdb_path = _gdb_path_from_fcs(fc_paths)

        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
```

- [ ] **Steg 5.4: Oppdater `__init__.py`**

```python
# src/arcpy_processor/__init__.py
from .errors import ArcpyProcessorError
from .bim_to_agol import main as run_bim_to_agol

__all__ = ["ArcpyProcessorError", "run_bim_to_agol"]
```

- [ ] **Steg 5.5: Kjør tester**

```bash
python -m pytest tests/test_arcpy_cli.py -v
```
Forventet: alle 3 tester PASS

- [ ] **Steg 5.6: Kjør alle tester**

```bash
python -m pytest tests/ -v
```
Forventet: alle 39 + nye tester PASS

- [ ] **Steg 5.7: Commit**

```bash
git add src/arcpy_processor/bim_to_agol.py src/arcpy_processor/__init__.py tests/test_arcpy_cli.py
git commit -m "feat: add CLI orchestrator with JSON stdout/stderr output"
```

---

## Oppgave 6: Oppdater .env.example

**Filer:**
- Endre: `.env.example`

- [ ] **Steg 6.1: Oppdater `.env.example`**

```
# Kopier til .env og fyll inn lokale verdier (ikke commit .env)

# ArcGIS Online-innlogging (for arcpy_processor)
AGOL_USERNAME=
AGOL_PASSWORD=
AGOL_ORG_URL=https://www.arcgis.com

# ArcGIS API (for frontend/backend)
ARCGIS_API_KEY=
ARCGIS_PORTAL_URL=https://www.arcgis.com

# Backend
UPLOAD_MAX_MB=500
```

- [ ] **Steg 6.2: Commit**

```bash
git add .env.example
git commit -m "chore: add AGOL auth variables to .env.example"
```

---

## Sjekkliste: spec-dekning

| Spec-krav | Oppgave |
|---|---|
| BIMFileToGeodatabase med memory/scratch workspace | Oppgave 3 |
| Slett tomme multipatcher | Oppgave 3 |
| Reproject til WKID 25833 | Oppgave 3 (parameter til BIMFileToGeodatabase) |
| OAuth2 / credentials fra .env | Oppgave 2 |
| Sjekk at tjenestenavn ikke finnes | Oppgave 4 |
| Publiser som 3D Object Layer (hosted feature service) | Oppgave 4 |
| JSON til stdout ved suksess | Oppgave 5 |
| JSON til stderr + exit 1 ved feil | Oppgave 5 |
| Alle feilkoder fra spec | Oppgave 1 + 2 + 3 + 4 + 5 |
| CLI med --ifc, --name, --folder | Oppgave 5 |
| Brukernavn/folder som parameter | Oppgave 5 |
| Ingen lokal lagring (scratchFolder) | Oppgave 3 |
| .env.example oppdatert | Oppgave 6 |
