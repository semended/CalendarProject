"""Финишная пачка для добивания coverage до 70% — verify-email, глубокие
подзадачи в Ганте, Jinja-формы ролей."""
from datetime import datetime, timedelta

from app.tokens import make_verify_token


def _register(client, email="f@example.com", password="pw123456"):
    r = client.post(
        "/registration",
        data={"email": email, "name": "F", "surname": "C", "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303


# ---------- verify-email ----------

def test_verify_email_valid_token(client):
    _register(client)
    token = make_verify_token("f@example.com")
    r = client.get(f"/verify-email/{token}")
    assert r.status_code == 200
    assert "подтверждена" in r.text.lower()


def test_verify_email_invalid_token(client):
    r = client.get("/verify-email/notatoken")
    assert r.status_code == 400


def test_verify_email_user_gone(client):
    """Токен валиден, но юзера в БД больше нет — 404."""
    token = make_verify_token("ghost@example.com")
    r = client.get(f"/verify-email/{token}")
    assert r.status_code == 404


# ---------- Gantt with depth-2 hierarchy + overdue/done ----------

def test_overview_with_deep_subtasks_and_statuses(client):
    """Показывает дерево с глубиной 2, разными цветами и статусами done/overdue."""
    _register(client)
    deadline = (datetime.now() + timedelta(days=30)).isoformat(timespec="minutes")
    r = client.post(
        "/create_task",
        data={
            "taskName": "Корень", "taskDescription": "", "taskColor": "#0ea5e9",
            "taskDeadline": deadline,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    pid = client.get("/api/v1/tasks").json()[0]["id"]

    # подзадачи разными цветами
    sub1 = client.post(
        "/api/v1/tasks",
        json={"name": "Sub-1", "description": "", "color": "#10b981",
              "parent_task_id": pid,
              "ended_at": (datetime.now() + timedelta(days=14)).isoformat()},
    ).json()
    client.post(
        "/api/v1/tasks",
        json={"name": "Sub-1.1", "description": "", "color": "#10b981",
              "parent_task_id": sub1["id"],
              "ended_at": (datetime.now() + timedelta(days=10)).isoformat()},
    )
    # вторая ветка — overdue
    client.post(
        "/api/v1/tasks",
        json={"name": "Просроченная", "description": "", "color": "#ef4444",
              "parent_task_id": pid,
              "ended_at": (datetime.now() - timedelta(days=2)).isoformat()},
    )
    # переключим состояние одной из веток в done
    client.patch(f"/api/v1/tasks/{sub1['id']}", json={"state": "done"})
    # overdue не трогаем — она будет с state=todo и ended_at в прошлом

    r = client.get(f"/task/{pid}/overview")
    assert r.status_code == 200
    assert "Sub-1" in r.text
    assert "Просроченная" in r.text


# ---------- Jinja CRUD ролей через formы ----------

def test_jinja_update_custom_role_via_form(client):
    _register(client, "owner@example.com")
    r = client.post(
        "/create_task",
        data={"taskName": "Проект", "taskDescription": "", "taskColor": "#000"},
        follow_redirects=False,
    )
    pid = client.get("/api/v1/tasks").json()[0]["id"]

    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "Дизайнер", "permissions": ["task.view"]},
    )
    role_id = r.json()["id"]

    # PATCH через form — изменим имя и набор прав
    from urllib.parse import urlencode
    body = urlencode([
        ("role_name", "Старший дизайнер"),
        ("permissions", "task.view"),
        ("permissions", "task.edit_settings"),
    ])
    r = client.post(
        f"/task_management/{pid}/roles/{role_id}",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    role = next(r for r in client.get(f"/api/v1/tasks/{pid}/roles").json() if r["id"] == role_id)
    assert role["name"] == "Старший дизайнер"
    assert sorted(role["permissions"]) == ["task.edit_settings", "task.view"]


def test_jinja_delete_custom_role_via_form(client):
    _register(client, "owner@example.com")
    client.post("/create_task",
                data={"taskName": "P", "taskDescription": "", "taskColor": "#000"})
    pid = client.get("/api/v1/tasks").json()[0]["id"]
    role_id = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "Удаляемая", "permissions": []},
    ).json()["id"]

    r = client.post(
        f"/task_management/{pid}/roles/{role_id}",
        data={"action": "delete"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    roles = client.get(f"/api/v1/tasks/{pid}/roles").json()
    assert all(r["id"] != role_id for r in roles)


def test_jinja_delete_system_role_via_form_blocked(client):
    """409 от формы — system role защищена."""
    _register(client, "owner@example.com")
    client.post("/create_task",
                data={"taskName": "P", "taskDescription": "", "taskColor": "#000"})
    pid = client.get("/api/v1/tasks").json()[0]["id"]
    teamlead_id = next(
        r["id"] for r in client.get(f"/api/v1/tasks/{pid}/roles").json()
        if r["name"] == "Тимлид"
    )

    r = client.post(
        f"/task_management/{pid}/roles/{teamlead_id}",
        data={"action": "delete"},
        follow_redirects=False,
    )
    assert r.status_code == 409


# ---------- /api/v1/auth/token wrong password ----------

def test_token_endpoint_wrong_password_returns_401(client):
    client.post("/api/v1/auth/register",
                json={"email": "tk@example.com", "name": "T", "surname": "K",
                      "password": "pw123456"})
    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/token",
        data={"username": "tk@example.com", "password": "wrong"},
    )
    assert r.status_code == 401
