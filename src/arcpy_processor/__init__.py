# src/arcpy_processor/__init__.py
from .errors import (
    ArcpyProcessorError,
    IFC_NOT_FOUND,
    ARCPY_UNAVAILABLE,
    AUTH_FAILED,
    NAME_EXISTS,
    BIM_CONVERSION_FAILED,
    NO_FEATURES,
    PUBLISH_FAILED,
)

__all__ = [
    "ArcpyProcessorError",
    "IFC_NOT_FOUND",
    "ARCPY_UNAVAILABLE",
    "AUTH_FAILED",
    "NAME_EXISTS",
    "BIM_CONVERSION_FAILED",
    "NO_FEATURES",
    "PUBLISH_FAILED",
]
