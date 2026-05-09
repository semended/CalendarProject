"""Доводка покрытия: альтернативные ветки в роутерах и сервисах,
которые не пробиваются smoke-тестами."""
from datetime import datetime, timedelta


def _register(client, email="m@example.com", password="pw123456"):
    r = client.post(
        "/registration",
        data={"email": email, "name": "M", "surname": "P", "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _project(client, **fields):
    data = {"taskName": fields.pop("name", "P"),
            "taskDescription": fields.pop("desc", ""),
            "taskColor": fields.pop("color", "#0ea5e9")}
    data.update(fields)
    r = client.post("/create_task", data=data, follow_redirects=False)
    assert r.status_code == 303
    return client.get("/api/v1/tasks").json()[0]["id"]


# ---------- task_overview / Gantt ----------

def test_overview_root_without_subtasks(client):
    """Отдельный путь: пустой tree → axis_ticks=6, rows=[], track_legend=[]."""
    _register(client)
    pid = _project(client)
    r = client.get(f"/task/{pid}/overview")
    assert r.status_code == 200


def test_overview_root_without_deadline(client):
    """Без ended_at: end = start + 30d по fallback."""
    _register(client)
    pid = _project(client)  # без taskDeadline → ended_at=NULL
    r = client.get(f"/task/{pid}/overview")
    assert r.status_code == 200


def test_create_task_with_deadline(client):
    _register(client)
    deadline = (datetime.now() + timedelta(days=14)).isoformat(timespec="minutes")
    r = client.post(
        "/create_task",
        data={
            "taskName": "С дедлайном",
            "taskDescription": "",
            "taskColor": "#ff0000",
            "taskDeadline": deadline,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_create_task_empty_name_returns_template(client):
    _register(client)
    r = client.post(
        "/create_task",
        data={"taskName": "   ", "taskDescription": "", "taskColor": "#000"},
        follow_redirects=False,
    )
    # Страница рендерится с error
    assert r.status_code == 200
    assert "обязательно" in r.text.lower() or "название" in r.text.lower()


def test_create_subtask_via_post_to_task_id(client):
    """POST /task/{id} → редирект на /create_task/{id}."""
    _register(client)
    pid = _project(client)
    r = client.post(f"/task/{pid}", follow_redirects=False)
    assert r.status_code == 303
    assert f"/create_task/{pid}" in r.headers["location"]


# ---------- assignee paths ----------

def test_self_assign_via_api_patch(client):
    _register(client)
    me = client.get("/api/v1/auth/me").json()
    pid = _project(client)
    r = client.patch(f"/api/v1/tasks/{pid}", json={"assignee_id": me["id"]})
    assert r.status_code == 200
    assert r.json()["assignee_id"] == me["id"]

    # И перезаписать на None — снять assignee
    r = client.patch(f"/api/v1/tasks/{pid}", json={"assignee_id": None})
    assert r.status_code == 200
    assert r.json()["assignee_id"] is None


def test_html_form_assignee_self(client):
    _register(client)
    me = client.get("/api/v1/auth/me").json()
    pid = _project(client)
    r = client.post(
        f"/task_management/{pid}",
        data={
            "task_name": "С исполнителем",
            "task_description": "",
            "task_color": "#0ea5e9",
            "assignee_id": str(me["id"]),
            "task_state": "in_progress",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_html_form_state_change(client):
    _register(client)
    pid = _project(client)
    r = client.post(
        f"/task_management/{pid}",
        data={
            "task_name": "Р",
            "task_description": "",
            "task_color": "#0ea5e9",
            "task_state": "done",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert client.get(f"/api/v1/tasks/{pid}").json()["state"] == "done"


# ---------- settings ----------

def test_settings_remove_avatar(client):
    _register(client)
    r = client.post(
        "/user/settings",
        data={"remove_avatar": "true"},
        follow_redirects=False,
    )
    assert r.status_code == 303


# ---------- calendar with explicit month ----------

def test_calendar_explicit_month(client):
    _register(client)
    r = client.get("/calendar?month=2027-03")
    assert r.status_code == 200


def test_calendar_invalid_month_falls_back(client):
    _register(client)
    r = client.get("/calendar?month=not-a-date")
    assert r.status_code == 200


def test_schedule_invalid_week_falls_back(client):
    _register(client)
    me = client.get("/api/v1/auth/me").json()
    r = client.get(f"/user/{me['id']}/schedule?week=garbage")
    assert r.status_code == 200


def test_schedule_other_user_view(client):
    """GET /user/{id}/schedule под другим юзером — 200, но без edit-формы."""
    _register(client, "owner@example.com")
    me = client.get("/api/v1/auth/me").json()

    _register(client, "viewer@example.com")
    r = client.get(f"/user/{me['id']}/schedule")
    assert r.status_code == 200


def test_schedule_post_only_self(client):
    """POST на чужое расписание — 403."""
    _register(client, "owner@example.com")
    me = client.get("/api/v1/auth/me").json()

    _register(client, "viewer@example.com")
    r = client.post(
        f"/user/{me['id']}/schedule",
        data={"action": "add", "slot_date": "2026-06-01",
              "start_time": "10:00", "end_time": "11:00"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_user_profile_not_found(client):
    _register(client)
    r = client.get("/user/99999")
    assert r.status_code == 404


def test_user_profile_anonymous_redirects(client):
    """schedule /user/{id}/schedule без авторизации — редирект на /."""
    me = client.post(
        "/api/v1/auth/register",
        json={"email": "anon@example.com", "name": "A", "surname": "N",
              "password": "pw123456"},
    ).json()
    client.cookies.clear()
    r = client.get(f"/user/{me['id']}/schedule", follow_redirects=False)
    assert r.status_code == 303


# ---------- start page redirect for already-logged-in ----------

def test_start_page_redirects_authenticated(client):
    _register(client)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/main")


# ---------- API list with offset/limit ----------

def test_api_tasks_list_pagination(client):
    _register(client)
    for i in range(3):
        client.post(
            "/api/v1/tasks",
            json={"name": f"task-{i}", "description": "", "color": "#000"},
        )
    r = client.get("/api/v1/tasks?limit=2&offset=0")
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get("/api/v1/tasks?limit=2&offset=2")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------- public profile via /api/v1/users/{id} ----------

def test_public_profile_via_api(client):
    _register(client, "p@example.com")
    me = client.get("/api/v1/auth/me").json()

    r = client.get(f"/api/v1/users/{me['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == me["id"]


def test_public_profile_not_found(client):
    _register(client, "p@example.com")
    r = client.get("/api/v1/users/99999")
    assert r.status_code == 404
