"""Integration-тесты: реально бьют в Postgres.

Каждый тест получает свежую БД через фикстуры в conftest.py."""


def _register(client, email="alice@example.com", password="secret123", name="Alice", surname="Доу"):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name, "surname": surname},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_register_creates_user_and_logs_in(client):
    me = _register(client)
    assert me["email"] == "alice@example.com"
    assert me["name"] == "Alice"
    assert me["id"] > 0

    # register auto-login — /auth/me уже отдаёт того же юзера
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["id"] == me["id"]


def test_register_conflict_on_duplicate_email(client):
    _register(client)
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "other1", "name": "X", "surname": "Y"},
    )
    assert r.status_code == 409


def test_login_with_valid_creds(client):
    _register(client, email="bob@example.com", password="pw123456")
    client.cookies.clear()  # сбрасываем авто-логин после register

    r = client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "pw123456"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "bob@example.com"

    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200


def test_login_rejects_wrong_password(client):
    _register(client, email="eve@example.com", password="correct1")
    client.cookies.clear()

    r = client.post(
        "/api/v1/auth/login",
        json={"email": "eve@example.com", "password": "wrong-password"},
    )
    assert r.status_code == 401


def test_logout_invalidates_session(client):
    _register(client)
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200

    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_full_task_lifecycle(client):
    _register(client)

    # пустой список
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    assert r.json() == []

    # создаём корневую задачу
    r = client.post("/api/v1/tasks", json={
        "name": "Проект A",
        "description": "описание",
        "color": "#0ea5e9",
    })
    assert r.status_code == 201, r.text
    root = r.json()
    assert root["name"] == "Проект A"
    assert root["parent_task_id"] is None
    assert root["state"] == "todo"

    # подзадача
    r = client.post("/api/v1/tasks", json={
        "name": "Подзадача 1",
        "parent_task_id": root["id"],
    })
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["parent_task_id"] == root["id"]

    # /tasks теперь видит обе
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert root["id"] in ids
    assert sub["id"] in ids

    # /subtasks
    r = client.get(f"/api/v1/tasks/{root['id']}/subtasks")
    assert r.status_code == 200
    subs = r.json()
    assert len(subs) == 1
    assert subs[0]["id"] == sub["id"]

    # patch state
    r = client.patch(f"/api/v1/tasks/{root['id']}", json={"state": "in_progress"})
    assert r.status_code == 200
    assert r.json()["state"] == "in_progress"

    # read-back подтверждает
    r = client.get(f"/api/v1/tasks/{root['id']}")
    assert r.status_code == 200
    assert r.json()["state"] == "in_progress"


def test_patch_state_rejects_invalid_value(client):
    _register(client)
    r = client.post("/api/v1/tasks", json={"name": "t"})
    task_id = r.json()["id"]

    r = client.patch(f"/api/v1/tasks/{task_id}", json={"state": "garbage"})
    assert r.status_code == 422


def test_other_user_cannot_view_task(client):
    _register(client, email="a@example.com", password="pw123456")
    r = client.post("/api/v1/tasks", json={"name": "секрет"})
    task_id = r.json()["id"]
    client.post("/api/v1/auth/logout")
    client.cookies.clear()

    _register(client, email="b@example.com", password="pw123456", name="Bob", surname="B")
    r = client.get(f"/api/v1/tasks/{task_id}")
    assert r.status_code == 403


def test_other_user_cannot_patch_task(client):
    _register(client, email="a@example.com", password="pw123456")
    r = client.post("/api/v1/tasks", json={"name": "мой проект"})
    task_id = r.json()["id"]
    client.post("/api/v1/auth/logout")
    client.cookies.clear()

    _register(client, email="b@example.com", password="pw123456", name="Bob", surname="B")
    r = client.patch(f"/api/v1/tasks/{task_id}", json={"name": "хакнул"})
    assert r.status_code == 403


def test_get_missing_task_returns_404(client):
    _register(client)
    r = client.get("/api/v1/tasks/99999999")
    assert r.status_code == 404


def test_public_user_endpoint_respects_privacy(client):
    # user A регистрируется, получает свой id
    a = _register(client, email="a@example.com", password="pw123456")
    client.post("/api/v1/auth/logout")
    client.cookies.clear()

    # неавторизованный зритель видит только публичные поля (name/surname),
    # а email скрыт (по умолчанию privacy_email='self')
    r = client.get(f"/api/v1/users/{a['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Alice"
    assert data.get("email") is None
