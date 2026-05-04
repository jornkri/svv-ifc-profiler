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
IFC_NOT_FOUND         = "IFC_NOT_FOUND"
ARCPY_UNAVAILABLE     = "ARCPY_UNAVAILABLE"
AUTH_FAILED           = "AUTH_FAILED"
NAME_EXISTS           = "NAME_EXISTS"
BIM_CONVERSION_FAILED = "BIM_CONVERSION_FAILED"
NO_FEATURES           = "NO_FEATURES"
PUBLISH_FAILED        = "PUBLISH_FAILED"
LANDXML_NOT_FOUND     = "LANDXML_NOT_FOUND"
LANDXML_PARSE_ERROR   = "LANDXML_PARSE_ERROR"
