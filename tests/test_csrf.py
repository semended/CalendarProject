"""Тесты CSRF-защиты с включённым CSRF_ENFORCE.

CSRF выключен по умолчанию (см. app/config.py) для обратной совместимости
с существующими тестами и ранними демо-средами; здесь — отдельный набор
с явным `monkeypatch` флага. Перезагружаем модули, чтобы middleware подхватил
новое значение.
"""
import importlib
import re

import pytest


@pytest.fixture
def csrf_client(monkeypatch):
    monkeypatch.setenv("CSRF_ENFORCE", "1")
    # Перезагружаем config + csrf + main, чтобы CSRF_ENFORCE подхватился
    # на уровне модуля и middleware взял значение True.
    import app.config
    import app.csrf
    import app.main as app_main

    importlib.reload(app.config)
    importlib.reload(app.csrf)
    importlib.reload(app_main)

    from fastapi.testclient import TestClient

    yield TestClient(app_main.app)

    # После теста вернуть на off, чтобы дальнейшие тесты не пострадали.
    monkeypatch.delenv("CSRF_ENFORCE", raising=False)
    importlib.reload(app.config)
    importlib.reload(app.csrf)
    importlib.reload(app_main)


def _csrf_token_from_get(client, path="/") -> str:
    r = client.get(path)
    assert r.status_code == 200, r.text
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
    assert m, "csrf_token hidden input not found in form"
    return m.group(1)


def test_post_without_csrf_token_blocked(csrf_client):
    r = csrf_client.post(
        "/registration",
        data={"email": "noscrf@example.com", "name": "X", "surname": "Y", "password": "pw123456"},
        follow_redirects=False,
    )
    assert r.status_code == 403, r.text


def test_post_with_csrf_token_allowed(csrf_client):
    token = _csrf_token_from_get(csrf_client, "/registration")
    r = csrf_client.post(
        "/registration",
        data={
            "email": "withcsrf@example.com",
            "name": "X", "surname": "Y", "password": "pw123456",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def test_post_with_wrong_csrf_token_blocked(csrf_client):
    _csrf_token_from_get(csrf_client, "/")
    r = csrf_client.post(
        "/registration",
        data={
            "email": "wrong@example.com",
            "name": "X", "surname": "Y", "password": "pw123456",
            "csrf_token": "this-is-not-the-real-token",
        },
        follow_redirects=False,
    )
    assert r.status_code == 403, r.text


def test_api_jwt_request_does_not_require_csrf(csrf_client):
    """JWT-эндпоинт под /api/v1 без cookie вообще — CSRF не должен мешать."""
    # Сначала зарегаемся через CSRF-форму, чтобы получить юзера в БД.
    token = _csrf_token_from_get(csrf_client, "/registration")
    r = csrf_client.post(
        "/registration",
        data={
            "email": "jwtuser@example.com",
            "name": "X", "surname": "Y", "password": "pw123456",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    # Получаем JWT (POST на /api/v1/auth/token — это form-data, /api/v1/* пропускается)
    r = csrf_client.post(
        "/api/v1/auth/token",
        data={"username": "jwtuser@example.com", "password": "pw123456"},
    )
    assert r.status_code == 200, r.text
    jwt = r.json()["access_token"]

    # Делаем JWT-запрос на mutating-эндпоинт — куки тоже идут (TestClient их хранит),
    # но Authorization: Bearer должен освободить от CSRF.
    r = csrf_client.post(
        "/api/v1/tasks",
        json={"name": "JWT-таска", "description": "", "color": "#aaaaaa"},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 201, r.text


def test_api_json_under_v1_does_not_require_csrf(csrf_client):
    """POST /api/v1/auth/login принимает JSON под cookie — CSRF не нужен,
    т.к. /api/v1/* пропускается middleware'ом по path-prefix."""
    # сидим юзера через CSRF-флоу
    token = _csrf_token_from_get(csrf_client, "/registration")
    r = csrf_client.post(
        "/registration",
        data={
            "email": "jsonu@example.com",
            "name": "X", "surname": "Y", "password": "pw123456",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Логаут чтобы куки очистились
    csrf_client.post("/api/v1/auth/logout")
    # POST JSON на /api/v1/auth/login — CSRF не должен ругаться
    r = csrf_client.post(
        "/api/v1/auth/login",
        json={"email": "jsonu@example.com", "password": "pw123456"},
    )
    assert r.status_code == 200, r.text
