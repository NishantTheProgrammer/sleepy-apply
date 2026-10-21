from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthenticated_profile_access():
    response = client.get("/api/profile")
    assert response.status_code == 401


def test_unauthenticated_jobs_access():
    response = client.get("/api/jobs")
    assert response.status_code == 401
