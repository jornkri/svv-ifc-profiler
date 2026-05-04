# src/arcpy_processor/auth.py
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .errors import ArcpyProcessorError, AUTH_FAILED

if TYPE_CHECKING:
    from arcgis.gis import GIS


def connect() -> GIS:
    """Returner autentisert GIS-instans fra .env-variabler."""
    from arcgis.gis import GIS

    username = os.getenv("AGOL_USERNAME")
    password = os.getenv("AGOL_PASSWORD")
    org_url = os.getenv("AGOL_ORG_URL", "https://www.arcgis.com")

    if not (username and username.strip()) or not (password and password.strip()):
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
