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


# --- refresh_access_token ---

def test_refresh_returns_fresh_token_and_updates_session():
    """refresh_access_token henter nytt token og oppdaterer session."""
    from src.api.auth_routes import refresh_access_token
    from fastapi import HTTPException

    session = {
        "access_token": "old_token",
        "refresh_token": "ref_tok_123",
        "org_url": "https://testorg.arcgis.com",
    }
    token_mock = MagicMock(raise_for_status=MagicMock(),
                           json=MagicMock(return_value={"access_token": "new_token_456"}))

    with patch("src.api.auth_routes.httpx.post", return_value=token_mock) as mock_post:
        result = refresh_access_token(session)

    assert result == "new_token_456"
    assert session["access_token"] == "new_token_456"
    call_data = mock_post.call_args[1]["data"]
    assert call_data["refresh_token"] == "ref_tok_123"
    assert call_data["grant_type"] == "refresh_token"


def test_refresh_raises_401_when_no_refresh_token():
    """Manglende refresh_token i session → 401."""
    from src.api.auth_routes import refresh_access_token
    from fastapi import HTTPException

    session = {"access_token": "tok", "org_url": "https://testorg.arcgis.com"}

    with pytest.raises(HTTPException) as exc_info:
        refresh_access_token(session)
    assert exc_info.value.status_code == 401


def test_refresh_raises_401_when_agol_returns_error():
    """AGOL svarer med error-JSON → 401."""
    from src.api.auth_routes import refresh_access_token
    from fastapi import HTTPException

    session = {
        "access_token": "old",
        "refresh_token": "ref",
        "org_url": "https://testorg.arcgis.com",
    }
    token_mock = MagicMock(raise_for_status=MagicMock(),
                           json=MagicMock(return_value={"error": "invalid_grant"}))

    with patch("src.api.auth_routes.httpx.post", return_value=token_mock):
        with pytest.raises(HTTPException) as exc_info:
            refresh_access_token(session)
    assert exc_info.value.status_code == 401


def test_create_job_passes_refreshed_token_to_run_job():
    """POST /api/jobs skal bruke det fornyede tokenet, ikke det gamle fra session."""
    import io
    from fastapi.testclient import TestClient
    from unittest.mock import patch, MagicMock

    def _login(client):
        login_resp = client.get("/auth/login", follow_redirects=False)
        params = dict(p.split("=", 1) for p in
                      login_resp.headers["location"].split("?")[1].split("&"))
        state = params["state"]
        token_mock = MagicMock(raise_for_status=MagicMock(),
                               json=MagicMock(return_value={
                                   "access_token": "old_tok",
                                   "refresh_token": "ref_tok",
                               }))
        user_mock = MagicMock(raise_for_status=MagicMock(),
                              json=MagicMock(return_value={"username": "u", "fullName": "N"}))
        with patch("src.api.auth_routes.httpx.post", return_value=token_mock), \
             patch("src.api.auth_routes.httpx.get", return_value=user_mock):
            client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)

    from src.api.server import app
    client = TestClient(app)
    _login(client)

    with patch("src.api.job_runner.run_job") as mock_run_job, \
         patch("src.api.server.refresh_access_token", return_value="fresh_tok_789") as mock_refresh:
        client.post(
            "/api/jobs",
            data={"name": "S", "interval": "10"},
            files={"ifc_file": ("m.ifc", io.BytesIO(b"x")),
                   "cl_file": ("c.xml", io.BytesIO(b"<x/>"))},
        )

    mock_refresh.assert_called_once()
    _, kwargs = mock_run_job.call_args
    assert kwargs["access_token"] == "fresh_tok_789"
