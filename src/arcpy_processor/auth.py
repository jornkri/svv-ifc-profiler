# src/arcpy_processor/auth.py
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .errors import ArcpyProcessorError, AUTH_FAILED

if TYPE_CHECKING:
    from arcgis.gis import GIS


def connect(token: str | None = None, org_url: str | None = None) -> GIS:
    """Returner autentisert GIS-instans.

    Args:
        token:   OAuth2 access_token fra brukerens innlogging. Overstyrer .env-credentials.
        org_url: AGOL org-URL. Overstyrer AGOL_ORG_URL i .env.
    """
    from arcgis.gis import GIS

    url = org_url or os.getenv("AGOL_ORG_URL", "https://www.arcgis.com")

    if token:
        try:
            return GIS(url, token=token)
        except Exception as exc:
            raise ArcpyProcessorError(
                AUTH_FAILED,
                f"Kunne ikke koble til ArcGIS Online med token ({url}): {exc}",
            ) from exc

    username = os.getenv("AGOL_USERNAME")
    password = os.getenv("AGOL_PASSWORD")

    if not (username and username.strip()) or not (password and password.strip()):
        raise ArcpyProcessorError(
            AUTH_FAILED,
            "AGOL_USERNAME og AGOL_PASSWORD må settes i .env-filen.",
        )

    try:
        return GIS(url, username, password)
    except Exception as exc:
        raise ArcpyProcessorError(
            AUTH_FAILED,
            f"Kunne ikke logge inn på ArcGIS Online ({url}): {exc}",
        ) from exc
