# src/api/auth_routes.py
"""OAuth2 Authorization Code flow mot ArcGIS Online."""
from __future__ import annotations

import os
import uuid

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from starlette.requests import Request

router = APIRouter()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@router.get("/login")
def auth_login(request: Request) -> RedirectResponse:
    state = str(uuid.uuid4())
    request.session["oauth_state"] = state
    org_url = _env("AGOL_ORG_URL", "https://www.arcgis.com")
    url = (
        f"{org_url}/sharing/rest/oauth2/authorize"
        f"?client_id={_env('AGOL_CLIENT_ID')}"
        f"&response_type=code"
        f"&redirect_uri={_env('AGOL_REDIRECT_URI', 'http://localhost:8000/auth/callback')}"
        f"&state={state}"
    )
    return RedirectResponse(url)


@router.get("/callback")
def auth_callback(request: Request, code: str, state: str) -> RedirectResponse:
    if state != request.session.get("oauth_state"):
        raise HTTPException(400, "Ugyldig state-parameter — mulig CSRF-angrep")

    org_url = _env("AGOL_ORG_URL", "https://www.arcgis.com")

    token_resp = httpx.post(
        f"{org_url}/sharing/rest/oauth2/token",
        data={
            "client_id": _env("AGOL_CLIENT_ID"),
            "client_secret": _env("AGOL_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": _env("AGOL_REDIRECT_URI", "http://localhost:8000/auth/callback"),
            "grant_type": "authorization_code",
        },
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    access_token = token_data["access_token"]

    self_resp = httpx.get(
        f"{org_url}/sharing/rest/community/self",
        params={"f": "json", "token": access_token},
    )
    self_resp.raise_for_status()
    user = self_resp.json()

    request.session.update({
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token"),
        "username": user.get("username", ""),
        "full_name": user.get("fullName", ""),
        "org_url": org_url,
    })
    return RedirectResponse("/")


@router.get("/me")
def auth_me(request: Request) -> dict:
    if "access_token" not in request.session:
        raise HTTPException(401, "Ikke innlogget")
    return {
        "username": request.session.get("username"),
        "full_name": request.session.get("full_name"),
        "org_url": request.session.get("org_url"),
    }


@router.post("/logout")
def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "ok"}
