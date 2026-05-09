"""Edge-кейсы сервисного слоя — типизированные исключения, которые
HTML-тесты не пробивают (PATCH несуществующей роли, удаление
несуществующей таски, пустое имя роли и т.п.)."""


def _register(client, email):
    r = client.post(
        "/registration",
        data={"email": email, "name": "E", "surname": "C", "password": "pw123456"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _project(client, name="P"):
    r = client.post(
        "/create_task",
        data={"taskName": name, "taskDescription": "", "taskColor": "#0ea5e9"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client.get("/api/v1/tasks").json()[0]["id"]


# ---------- roles_service ----------

def test_create_role_with_empty_name_returns_422(client):
    _register(client, "owner@example.com")
    pid = _project(client)
    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "  ", "permissions": ["task.view"]},
    )
    assert r.status_code == 422
    assert "Название" in r.json()["detail"]


def test_patch_role_not_found(client):
    _register(client, "owner@example.com")
    _project(client)
    r = client.patch("/api/v1/roles/99999", json={"name": "X"})
    assert r.status_code == 404


def test_delete_role_not_found(client):
    _register(client, "owner@example.com")
    _project(client)
    r = client.delete("/api/v1/roles/99999")
    assert r.status_code == 404


def test_outsider_cannot_patch_role(client):
    _register(client, "owner@example.com")
    pid = _project(client)
    role_id = client.get(f"/api/v1/tasks/{pid}/roles").json()[0]["id"]

    _register(client, "outsider@example.com")
    r = client.patch(f"/api/v1/roles/{role_id}", json={"name": "X"})
    assert r.status_code == 403


def test_outsider_cannot_delete_role(client):
    _register(client, "owner@example.com")
    pid = _project(client)
    # сделаем custom-роль которую можно удалить
    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "Кастомная", "permissions": []},
    )
    role_id = r.json()["id"]

    _register(client, "outsider@example.com")
    r = client.delete(f"/api/v1/roles/{role_id}")
    assert r.status_code == 403


def test_unknown_permission_codes_filtered(client):
    """В create_role/permissions можно прислать что угодно — неизвестные
    коды молча отфильтруются."""
    _register(client, "owner@example.com")
    pid = _project(client)
    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={
            "name": "Хитрая",
            "permissions": ["task.view", "wat.shenanigans", "../etc/passwd"],
        },
    )
    assert r.status_code == 201
    assert r.json()["permissions"] == ["task.view"]


# ---------- task_service ----------

def test_get_task_not_found(client):
    _register(client, "u@example.com")
    r = client.get("/api/v1/tasks/99999")
    assert r.status_code == 404


def test_patch_task_not_found(client):
    _register(client, "u@example.com")
    r = client.patch("/api/v1/tasks/99999", json={"name": "X"})
    assert r.status_code == 404


def test_subtasks_listing(client):
    _register(client, "u@example.com")
    pid = _project(client)
    r = client.post(
        "/api/v1/tasks",
        json={"name": "sub-1", "description": "", "color": "#000000",
              "parent_task_id": pid},
    )
    assert r.status_code == 201

    r = client.get(f"/api/v1/tasks/{pid}/subtasks")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["name"] == "sub-1"


def test_subtasks_listing_forbidden_for_outsider(client):
    _register(client, "owner@example.com")
    pid = _project(client)

    _register(client, "outsider@example.com")
    r = client.get(f"/api/v1/tasks/{pid}/subtasks")
    assert r.status_code == 403


def test_get_task_forbidden_for_outsider(client):
    _register(client, "owner@example.com")
    pid = _project(client)

    _register(client, "outsider@example.com")
    r = client.get(f"/api/v1/tasks/{pid}")
    assert r.status_code == 403


def test_invalid_assignee_in_create_returns_422(client):
    """API strict-mode: assignee_id не из кандидатов — 422."""
    _register(client, "u@example.com")
    pid = _project(client)
    r = client.post(
        "/api/v1/tasks",
        json={
            "name": "child",
            "description": "",
            "color": "#000000",
            "parent_task_id": pid,
            "assignee_id": 999999,
        },
    )
    assert r.status_code == 422


def test_invalid_assignee_in_patch_returns_422(client):
    _register(client, "u@example.com")
    pid = _project(client)
    r = client.patch(
        f"/api/v1/tasks/{pid}",
        json={"assignee_id": 999999},
    )
    assert r.status_code == 422


def test_outsider_cannot_patch_task(client):
    _register(client, "owner@example.com")
    pid = _project(client)
    _register(client, "outsider@example.com")
    r = client.patch(f"/api/v1/tasks/{pid}", json={"name": "Хочу хакнуть"})
    assert r.status_code == 403


# ---------- /api/v1/auth ----------

def test_register_duplicate_email_returns_409(client):
    payload = {"email": "dup@example.com", "name": "D", "surname": "U", "password": "pw123456"}
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409


def test_api_login_wrong_password(client):
    client.post("/api/v1/auth/register",
                json={"email": "wp@example.com", "name": "W", "surname": "P", "password": "good123"})
    client.cookies.clear()
    r = client.post("/api/v1/auth/login",
                    json={"email": "wp@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_api_logout(client):
    client.post("/api/v1/auth/register",
                json={"email": "lo@example.com", "name": "L", "surname": "O", "password": "pw123456"})
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    # после logout — /me должен дать 401
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
