"""Smoke-tester: sjekk at modulene kan importeres og at API-en svarer."""

from fastapi.testclient import TestClient


def test_imports():
    from src.ifc_processor import (
        extract_centerline,
        generate_cross_sections,
        generate_longitudinal_profile,
    )
    assert callable(extract_centerline)
    assert callable(generate_cross_sections)
    assert callable(generate_longitudinal_profile)


def test_health_endpoint():
    from src.api.server import app

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
