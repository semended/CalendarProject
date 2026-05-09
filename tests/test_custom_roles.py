"""Тесты для Задачи 2: кастомные роли проекта.

Проверяем CRUD через API + защиту системных ролей + работу с правами через
наследование (тимлид корня может управлять ролями подзадачи).
"""


def _register(client, email, password="pw123456"):
    r = client.post(
        "/registration",
        data={"email": email, "name": "T", "surname": "U", "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def _login(client, email, password="pw123456"):
    r = client.post("/", data={"email": email, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text


def _make_project(client, name="Проект"):
    r = client.post(
        "/create_task",
        data={"taskName": name, "taskDescription": "", "taskColor": "#777777"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client.get("/api/v1/tasks").json()[0]["id"]


def test_default_three_roles_exist_and_are_system(client):
    _register(client, "owner@example.com")
    pid = _make_project(client)

    r = client.get(f"/api/v1/tasks/{pid}/roles")
    assert r.status_code == 200, r.text
    roles = r.json()
    names = sorted(r["name"] for r in roles)
    assert names == ["Менеджер", "Разработчик", "Тимлид"]
    for role in roles:
        assert role["is_system"] is True


def test_create_custom_role(client):
    _register(client, "owner@example.com")
    pid = _make_project(client)

    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={
            "name": "Дизайнер",
            "permissions": ["task.view", "task.edit_settings"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Дизайнер"
    assert body["is_system"] is False
    assert sorted(body["permissions"]) == ["task.edit_settings", "task.view"]


def test_cannot_delete_system_role(client):
    _register(client, "owner@example.com")
    pid = _make_project(client)
    roles = client.get(f"/api/v1/tasks/{pid}/roles").json()
    teamlead_id = next(r["id"] for r in roles if r["name"] == "Тимлид")

    r = client.delete(f"/api/v1/roles/{teamlead_id}")
    assert r.status_code == 409, r.text


def test_cannot_rename_system_role(client):
    _register(client, "owner@example.com")
    pid = _make_project(client)
    roles = client.get(f"/api/v1/tasks/{pid}/roles").json()
    teamlead_id = next(r["id"] for r in roles if r["name"] == "Тимлид")

    r = client.patch(
        f"/api/v1/roles/{teamlead_id}", json={"name": "Босс"}
    )
    assert r.status_code == 409, r.text


def test_can_update_system_role_permissions(client):
    """У системной роли можно менять набор прав, но не имя."""
    _register(client, "owner@example.com")
    pid = _make_project(client)
    roles = client.get(f"/api/v1/tasks/{pid}/roles").json()
    dev_id = next(r["id"] for r in roles if r["name"] == "Разработчик")

    r = client.patch(
        f"/api/v1/roles/{dev_id}",
        json={"permissions": ["task.view", "task.edit_settings"]},
    )
    assert r.status_code == 200, r.text
    assert sorted(r.json()["permissions"]) == ["task.edit_settings", "task.view"]


def test_delete_custom_role(client):
    _register(client, "owner@example.com")
    pid = _make_project(client)
    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "Тестер", "permissions": ["task.view"]},
    )
    assert r.status_code == 201
    role_id = r.json()["id"]

    r = client.delete(f"/api/v1/roles/{role_id}")
    assert r.status_code == 204

    roles = client.get(f"/api/v1/tasks/{pid}/roles").json()
    assert all(r["id"] != role_id for r in roles)


def test_update_custom_role_permissions(client):
    _register(client, "owner@example.com")
    pid = _make_project(client)
    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "Аналитик", "permissions": ["task.view"]},
    )
    role_id = r.json()["id"]

    r = client.patch(
        f"/api/v1/roles/{role_id}",
        json={"name": "Аналитик-сеньор", "permissions": []},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Аналитик-сеньор"
    assert r.json()["permissions"] == []


def test_outsider_cannot_create_role(client):
    _register(client, "owner@example.com")
    pid = _make_project(client)
    _register(client, "outsider@example.com")
    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "Чужак", "permissions": ["task.view"]},
    )
    assert r.status_code == 403


def test_assign_user_to_custom_role(client):
    """Назначение через POST /task_management/{task_id} с form-data — добавление участника."""
    _register(client, "owner@example.com")
    pid = _make_project(client)
    r = client.post(
        f"/api/v1/tasks/{pid}/roles",
        json={"name": "Дизайнер", "permissions": ["task.view"]},
    )
    role_id = r.json()["id"]

    _register(client, "guest@example.com")
    _login(client, "owner@example.com")

    r = client.post(
        f"/task_management/{pid}",
        data={"email": "guest@example.com", "role_id": str(role_id)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Подтверждаем что кастомная роль действительно назначилась
    r = client.get(f"/task/{pid}")
    assert r.status_code == 200
    assert "Дизайнер" in r.text


def test_jinja_create_role_via_form(client):
    """POST /task_management/{task_id}/roles с form-data — создание роли через Jinja."""
    _register(client, "owner@example.com")
    pid = _make_project(client)

    # Передаём чекбокс-список через MultiDict-эквивалент httpx (tuple-list в content).
    # `data={"permissions": ["a", "b"]}` httpx уже не поддерживает; используем
    # сырой urlencode, который точно сериализуется в repeated key.
    from urllib.parse import urlencode
    body = urlencode([
        ("role_name", "QA"),
        ("permissions", "task.view"),
        ("permissions", "task.edit_settings"),
    ])
    r = client.post(
        f"/task_management/{pid}/roles",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    roles = client.get(f"/api/v1/tasks/{pid}/roles").json()
    qa = next((r for r in roles if r["name"] == "QA"), None)
    assert qa is not None
    assert sorted(qa["permissions"]) == ["task.edit_settings", "task.view"]
