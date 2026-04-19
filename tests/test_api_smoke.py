"""Smoke-тесты API слоя. Не трогают БД на запись — проверяют только маршрутизацию и auth-гейты."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_openapi_exposes_api_v1():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/tasks" in paths
    assert "/api/v1/users/me" in paths


def test_docs_page_reachable():
    r = client.get("/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_api_tasks_list_requires_auth():
    r = client.get("/api/v1/tasks")
    assert r.status_code == 401
    assert r.json() == {"detail": "Не авторизован"}


def test_api_users_me_requires_auth():
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401


def test_api_auth_me_requires_auth():
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_api_login_with_bad_creds():
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "wrong"},
    )
    assert r.status_code == 401
    assert "Неверный" in r.json()["detail"]


def test_api_login_validates_email_format():
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "x"},
    )
    assert r.status_code == 422


def test_api_logout_requires_auth():
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 401


def test_jinja_start_page_still_renders():
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
