# tests/test_api_auth.py
from __future__ import annotations
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("AGOL_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("AGOL_CLIENT_SECRET", "test_secret")
    monkeypatch.setenv("AGOL_REDIRECT_URI", "http://localhost:8000/auth/callback")
    monkeypatch.setenv("AGOL_ORG_URL", "https://testkommune.maps.arcgis.com")


@pytest.fixture
def client():
    from src.api.auth_routes import router
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")
    app.include_router(router, prefix="/auth")
    return TestClient(app)


def test_login_redirects_to_agol(client):
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "testkommune.maps.arcgis.com" in resp.headers["location"]
    assert "client_id=test_client_id" in resp.headers["location"]
    assert "state=" in resp.headers["location"]


def test_me_returns_401_when_not_logged_in(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_callback_rejects_invalid_state(client):
    resp = client.get("/auth/callback?code=abc&state=bad-state-no-session")
    assert resp.status_code == 400


def test_callback_sets_session(client):
    """Full flow: login -> set state -> callback with valid state -> /me returns user."""
    # Login to establish state in session
    login_resp = client.get("/auth/login", follow_redirects=False)
    location = login_resp.headers["location"]
    params = dict(p.split("=", 1) for p in location.split("?")[1].split("&"))
    state = params["state"]

    token_mock = MagicMock()
    token_mock.raise_for_status = MagicMock()
    token_mock.json.return_value = {"access_token": "tok123", "refresh_token": "ref456"}

    user_mock = MagicMock()
    user_mock.raise_for_status = MagicMock()
    user_mock.json.return_value = {"username": "testuser", "fullName": "Test Bruker"}

    with patch("src.api.auth_routes.httpx.post", return_value=token_mock), \
         patch("src.api.auth_routes.httpx.get", return_value=user_mock):
        cb_resp = client.get(f"/auth/callback?code=xyz&state={state}",
                             follow_redirects=False)
    assert cb_resp.status_code in (302, 307)

    me_resp = client.get("/auth/me")
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["username"] == "testuser"
    assert data["full_name"] == "Test Bruker"


def test_logout_clears_session(client):
    """After logout, /auth/me returns 401."""
    # Login
    login_resp = client.get("/auth/login", follow_redirects=False)
    state = dict(p.split("=", 1) for p in
                 login_resp.headers["location"].split("?")[1].split("&"))["state"]
    token_mock = MagicMock(raise_for_status=MagicMock(),
                           json=MagicMock(return_value={"access_token": "t", "refresh_token": "r"}))
    user_mock = MagicMock(raise_for_status=MagicMock(),
                          json=MagicMock(return_value={"username": "u", "fullName": "N"}))
    with patch("src.api.auth_routes.httpx.post", return_value=token_mock), \
         patch("src.api.auth_routes.httpx.get", return_value=user_mock):
        client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)

    assert client.get("/auth/me").status_code == 200
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401
