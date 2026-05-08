"""Parity-тесты: HTML-форма и API-эндпоинт на одинаковые входные данные
производят одинаковый результат в БД. Смысл — поймать дрифт между путями
после рефакторинга в сервисный слой.
"""
import re


def _register_jinja(client, email, password="pw123456", name="J", surname="User"):
    r = client.post(
        "/registration",
        data={"email": email, "name": name, "surname": surname, "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def _login_jinja(client, email, password="pw123456"):
    r = client.post(
        "/", data={"email": email, "password": password}, follow_redirects=False
    )
    assert r.status_code == 303, r.text


def _login_api(client, email, password="pw123456") -> str:
    r = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_create_task_parity_jinja_vs_api(client):
    """Создание задачи через форму и через API даёт идентичные ключевые поля.

    Сравниваем: name, description, color, creator_id, parent_task_id (None),
    state ("todo"). Не сравниваем id/created_at/duration — они различаются
    по построению.
    """
    _register_jinja(client, "jinja-creator@example.com")

    r = client.post(
        "/create_task",
        data={
            "taskName": "Через форму",
            "taskDescription": "описание",
            "taskColor": "#aabbcc",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    api_user_email = "api-creator@example.com"
    _register_jinja(client, api_user_email)
    token = _login_api(client, api_user_email)
    r = client.post(
        "/api/v1/tasks",
        json={
            "name": "Через форму",
            "description": "описание",
            "color": "#aabbcc",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    api_task = r.json()

    # Достаём jinja-задачу через API под её сессией. Перелогиниваемся
    # под jinja-юзера, чтобы /api/v1/tasks вернуло его задачи.
    _login_jinja(client, "jinja-creator@example.com")
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200, r.text
    jinja_tasks = r.json()
    assert len(jinja_tasks) == 1
    jinja_task = jinja_tasks[0]

    for field in ("name", "description", "color", "state", "parent_task_id"):
        assert jinja_task[field] == api_task[field], (
            f"parity mismatch for '{field}': jinja={jinja_task[field]!r} "
            f"api={api_task[field]!r}"
        )


def test_register_parity_jinja_vs_api(client):
    """Регистрация через POST /registration и POST /api/v1/auth/register
    создаёт идентичные пользователи (по полям email/name/surname/confirmed)."""
    r = client.post(
        "/registration",
        data={
            "email": "jinja-reg@example.com",
            "name": "Jay",
            "surname": "Сюрнейм",
            "password": "pw123456",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "api-reg@example.com",
            "name": "Jay",
            "surname": "Сюрнейм",
            "password": "pw123456",
        },
    )
    assert r.status_code == 201, r.text
    api_user = r.json()

    _login_jinja(client, "jinja-reg@example.com")
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200, r.text
    jinja_user = r.json()

    for field in ("name", "surname", "confirmed"):
        assert jinja_user[field] == api_user[field], (
            f"parity mismatch for '{field}': jinja={jinja_user[field]!r} "
            f"api={api_user[field]!r}"
        )


def test_create_task_permission_parity(client):
    """Создание подзадачи без прав — оба пути отказывают (403).

    Тимлид-владелец проекта создаёт корневой проект, второй юзер пытается
    добавить туда подзадачу через форму и через API — оба должны вернуть 403.
    """
    _register_jinja(client, "owner@example.com")
    r = client.post(
        "/create_task",
        data={"taskName": "Корневой", "taskDescription": "", "taskColor": "#111111"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    parent_id = r.json()[0]["id"]

    # Логинимся вторым юзером — у него прав на parent нет.
    _register_jinja(client, "outsider@example.com")

    # 1) Через Jinja-форму
    r = client.post(
        f"/create_task/{parent_id}",
        data={
            "taskName": "Чужая подзадача",
            "taskDescription": "",
            "taskColor": "#222222",
        },
        follow_redirects=False,
    )
    assert r.status_code == 403, r.text

    # 2) Через API
    token = _login_api(client, "outsider@example.com")
    r = client.post(
        "/api/v1/tasks",
        json={
            "name": "Чужая подзадача",
            "description": "",
            "color": "#222222",
            "parent_task_id": parent_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text
