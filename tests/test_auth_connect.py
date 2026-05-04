"""Tests for GIS auth module. Run in isolation via: pytest tests/test_auth_connect.py -v"""

import pytest
from unittest.mock import MagicMock, patch
from src.arcpy_processor.errors import ArcpyProcessorError


def test_connect_uses_username_password(monkeypatch):
    """Test that connect() passes env vars to GIS() constructor."""
    monkeypatch.setenv("AGOL_USERNAME", "testuser")
    monkeypatch.setenv("AGOL_PASSWORD", "testpass")
    monkeypatch.setenv("AGOL_ORG_URL", "https://www.arcgis.com")

    # Mock at the module level before importing connect()
    import sys
    from unittest.mock import MagicMock

    mock_gis_class = MagicMock()
    mock_gis_instance = MagicMock()
    mock_gis_class.return_value = mock_gis_instance

    # Create a mock arcgis module
    sys.modules["arcgis"] = MagicMock()
    sys.modules["arcgis.gis"] = MagicMock()
    sys.modules["arcgis.gis"].GIS = mock_gis_class

    from src.arcpy_processor.auth import connect
    gis = connect()

    mock_gis_class.assert_called_once_with(
        "https://www.arcgis.com", "testuser", "testpass"
    )
    assert gis is mock_gis_instance

    # Clean up
    del sys.modules["arcgis.gis"]
    del sys.modules["arcgis"]


def test_connect_raises_auth_failed_on_exception(monkeypatch):
    """Test that connect() raises ArcpyProcessorError on GIS() exception."""
    monkeypatch.setenv("AGOL_USERNAME", "bad")
    monkeypatch.setenv("AGOL_PASSWORD", "bad")
    monkeypatch.setenv("AGOL_ORG_URL", "https://www.arcgis.com")

    import sys
    from unittest.mock import MagicMock

    mock_gis_class = MagicMock(side_effect=Exception("Invalid credentials"))

    sys.modules["arcgis"] = MagicMock()
    sys.modules["arcgis.gis"] = MagicMock()
    sys.modules["arcgis.gis"].GIS = mock_gis_class

    from src.arcpy_processor.auth import connect

    with pytest.raises(ArcpyProcessorError) as exc_info:
        connect()
    assert exc_info.value.code == "AUTH_FAILED"

    del sys.modules["arcgis.gis"]
    del sys.modules["arcgis"]


def test_connect_raises_when_env_missing(monkeypatch):
    """Test that connect() raises ArcpyProcessorError when env vars missing."""
    monkeypatch.delenv("AGOL_USERNAME", raising=False)
    monkeypatch.delenv("AGOL_PASSWORD", raising=False)

    import sys
    from unittest.mock import MagicMock

    # Mock arcgis to avoid ArcPy crashes when module state is dirty
    if "arcgis.gis" not in sys.modules:
        sys.modules["arcgis"] = MagicMock()
        sys.modules["arcgis.gis"] = MagicMock()

    from src.arcpy_processor.auth import connect
    with pytest.raises(ArcpyProcessorError) as exc_info:
        connect()
    assert exc_info.value.code == "AUTH_FAILED"

    if "arcgis.gis" in sys.modules:
        del sys.modules["arcgis.gis"]
    if "arcgis" in sys.modules:
        del sys.modules["arcgis"]


def test_connect_uses_default_org_url(monkeypatch):
    """Test that connect() uses default ArcGIS.com URL when AGOL_ORG_URL not set."""
    monkeypatch.setenv("AGOL_USERNAME", "user")
    monkeypatch.setenv("AGOL_PASSWORD", "pass")
    monkeypatch.delenv("AGOL_ORG_URL", raising=False)

    import sys
    mock_gis_instance = MagicMock()
    mock_gis_class = MagicMock(return_value=mock_gis_instance)

    # Patch arcgis.gis.GIS before importing connect
    sys.modules["arcgis"] = MagicMock()
    sys.modules["arcgis.gis"] = MagicMock()
    sys.modules["arcgis.gis"].GIS = mock_gis_class

    from src.arcpy_processor.auth import connect
    result = connect()

    mock_gis_class.assert_called_once_with("https://www.arcgis.com", "user", "pass")
    assert result is mock_gis_instance

    # Clean up
    del sys.modules["arcgis.gis"]
    del sys.modules["arcgis"]
