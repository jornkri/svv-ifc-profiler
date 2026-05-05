from src.arcpy_processor.errors import (
    ArcpyProcessorError, NAME_EXISTS,
    LANDXML_NOT_FOUND, LANDXML_PARSE_ERROR
)


def test_error_has_code_and_message():
    err = ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")
    assert err.code == NAME_EXISTS
    assert err.message == "Navn finnes allerede"


def test_error_to_dict():
    err = ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")
    d = err.to_dict()
    assert d == {"status": "error", "code": "NAME_EXISTS", "message": "Navn finnes allerede"}


def test_error_is_exception_subclass():
    err = ArcpyProcessorError("CODE", "melding")
    assert isinstance(err, Exception)


def test_all_error_codes_exist():
    from src.arcpy_processor.errors import (
        IFC_NOT_FOUND, ARCPY_UNAVAILABLE, AUTH_FAILED,
        NAME_EXISTS, BIM_CONVERSION_FAILED, NO_FEATURES, PUBLISH_FAILED,
    )
    codes = [IFC_NOT_FOUND, ARCPY_UNAVAILABLE, AUTH_FAILED,
             NAME_EXISTS, BIM_CONVERSION_FAILED, NO_FEATURES, PUBLISH_FAILED]
    assert len(codes) == 7
    assert all(isinstance(c, str) for c in codes)


def test_landxml_error_codes_exist():
    assert LANDXML_NOT_FOUND == "LANDXML_NOT_FOUND"
    assert LANDXML_PARSE_ERROR == "LANDXML_PARSE_ERROR"


def test_landxml_error_to_dict():
    err = ArcpyProcessorError(LANDXML_PARSE_ERROR, "EPSG mangler")
    assert err.to_dict() == {
        "status": "error",
        "code": "LANDXML_PARSE_ERROR",
        "message": "EPSG mangler",
    }


def test_connect_with_token():
    """connect(token=...) passes token= keyword to GIS(), not username/password."""
    import sys
    from unittest.mock import MagicMock, patch

    gis_mock = MagicMock()
    GIS_mock = MagicMock(return_value=gis_mock)

    with patch.dict(sys.modules, {"arcgis.gis": MagicMock(GIS=GIS_mock)}):
        import importlib
        import src.arcpy_processor.auth as auth_module
        importlib.reload(auth_module)
        auth_module.connect(token="mytoken", org_url="https://test.maps.arcgis.com")

    GIS_mock.assert_called_once_with("https://test.maps.arcgis.com", token="mytoken")


def test_connect_without_token_uses_env_credentials():
    """connect() with no args calls GIS(url, username, password) from env."""
    import sys
    import importlib
    import pytest
    from unittest.mock import MagicMock, patch

    GIS_mock = MagicMock(return_value=MagicMock())

    with patch.dict(sys.modules, {"arcgis.gis": MagicMock(GIS=GIS_mock)}), \
         patch.dict("os.environ", {
             "AGOL_USERNAME": "testuser",
             "AGOL_PASSWORD": "testpass",
             "AGOL_ORG_URL": "https://myorg.maps.arcgis.com",
         }):
        import src.arcpy_processor.auth as auth_module
        importlib.reload(auth_module)
        auth_module.connect()

    GIS_mock.assert_called_once_with(
        "https://myorg.maps.arcgis.com", "testuser", "testpass"
    )


def test_connect_raises_when_credentials_missing():
    """connect() with no token and no env credentials raises AUTH_FAILED."""
    import sys
    import importlib
    import pytest
    from unittest.mock import MagicMock, patch
    from src.arcpy_processor.errors import ArcpyProcessorError, AUTH_FAILED

    GIS_mock = MagicMock(return_value=MagicMock())

    with patch.dict(sys.modules, {"arcgis.gis": MagicMock(GIS=GIS_mock)}), \
         patch.dict("os.environ", {}, clear=True):
        import src.arcpy_processor.auth as auth_module
        importlib.reload(auth_module)
        with pytest.raises(ArcpyProcessorError) as exc_info:
            auth_module.connect()

    assert exc_info.value.code == AUTH_FAILED
