from src.arcpy_processor.errors import ArcpyProcessorError, NAME_EXISTS


def test_error_has_code_and_message():
    err = ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")
    assert err.code == NAME_EXISTS
    assert err.message == "Navn finnes allerede"


def test_error_to_dict():
    err = ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")
    d = err.to_dict()
    assert d == {"status": "error", "code": "NAME_EXISTS", "message": "Navn finnes allerede"}
