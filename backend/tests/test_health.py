from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_reports_ok_status():
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "ok"


def test_health_includes_app_metadata():
    response = client.get("/health")
    body = response.json()
    assert "app" in body
    assert "environment" in body
