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
