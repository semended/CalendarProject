"""Тесты для Этапа 3: запись task_events / notifications / last_login_at."""
import psycopg2

# Тот же sync URL, что в conftest — psycopg2 для прямой проверки таблиц.
_SYNC_URL = "postgresql://postgres:123@localhost:5432/testdb_test"


def _row_count(table: str) -> int:
    conn = psycopg2.connect(_SYNC_URL)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        n = cur.fetchone()[0]
    conn.close()
    return n


def _scalar(query: str):
    conn = psycopg2.connect(_SYNC_URL)
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def _register(client, email, password="pw123456"):
    r = client.post(
        "/registration",
        data={"email": email, "name": "T", "surname": "U", "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_last_login_at_set_on_login(client):
    _register(client, "ll@example.com")
    # Логинимся явно, чтобы проверить именно сценарий входа (а не registration auto-login)
    r = client.post(
        "/", data={"email": "ll@example.com", "password": "pw123456"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    last = _scalar("SELECT last_login_at FROM users WHERE email='ll@example.com'")
    assert last is not None


def test_task_creation_writes_event(client):
    _register(client, "evt@example.com")
    r = client.post(
        "/create_task",
        data={"taskName": "Эвент-тест", "taskDescription": "", "taskColor": "#222222"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert _row_count("task_events") == 1
    event_type = _scalar("SELECT event_type FROM task_events LIMIT 1")
    assert event_type == "task.created"


def test_state_change_writes_event(client):
    _register(client, "state@example.com")
    r = client.post(
        "/create_task",
        data={"taskName": "Stateful", "taskDescription": "", "taskColor": "#333333"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    task_id = client.get("/api/v1/tasks").json()[0]["id"]

    r = client.patch(f"/api/v1/tasks/{task_id}", json={"state": "in_progress"})
    assert r.status_code == 200, r.text

    state_events = _scalar(
        f"SELECT COUNT(*) FROM task_events WHERE event_type='task.state_changed' AND task_id={task_id}"
    )
    assert state_events == 1


def test_assign_task_creates_notification(client):
    # Создаём двух юзеров, добавляем второго в проект как разработчика, назначаем
    # на подзадачу — должно появиться notification.
    _register(client, "owner@example.com")
    r = client.post(
        "/create_task",
        data={"taskName": "Проект", "taskDescription": "", "taskColor": "#444444"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    parent_id = client.get("/api/v1/tasks").json()[0]["id"]

    # Зарегистрируем второго юзера в отдельном test-клиенте, чтобы не сбить сессию owner.
    _register(client, "dev@example.com")
    dev_id = client.get("/api/v1/auth/me").json()["id"]

    # Возвращаемся под owner, добавляем dev как разработчика и назначаем на подзадачу
    r = client.post("/", data={"email": "owner@example.com", "password": "pw123456"},
                    follow_redirects=False)
    assert r.status_code == 303

    # узнаём role_id "Разработчик" в проекте
    role_id = _scalar(
        f"SELECT id FROM task_roles WHERE task_id={parent_id} AND name='Разработчик'"
    )
    assert role_id is not None

    r = client.post(
        f"/task_management/{parent_id}",
        data={"email": "dev@example.com", "role_id": str(role_id)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Создаём подзадачу с assignee=dev
    r = client.post(
        f"/create_task/{parent_id}",
        data={
            "taskName": "Подзадача для dev",
            "taskDescription": "",
            "taskColor": "#555555",
            "assignee_id": str(dev_id),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    notifs = _scalar(
        f"SELECT COUNT(*) FROM notifications WHERE user_id={dev_id} "
        "AND notification_type='task_assigned'"
    )
    assert notifs == 1
