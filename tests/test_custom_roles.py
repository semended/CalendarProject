"""Тесты для Задачи 2: кастомные роли проекта.

Проверяем CRUD через API + защиту системных ролей + работу с правами через
наследование (тимлид корня может управлять ролями подзадачи).
"""
import psycopg2


_SYNC_URL = "postgresql://postgres:123@localhost:5432/testdb_test"


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


def _make_subtask(client, parent_id, name="Подзадача"):
    r = client.post(
        "/api/v1/tasks",
        json={"name": name, "parent_task_id": parent_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


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


def test_default_roles_have_merged_subtask_permission(client):
    """После объединения create_subtask + delete_subtask дефолтные роли
    должны видеть единый код task.manage_subtasks."""
    _register(client, "owner@example.com")
    pid = _make_project(client)

    roles = client.get(f"/api/v1/tasks/{pid}/roles").json()

    teamlead = next(r for r in roles if r["name"] == "Тимлид")
    assert "task.manage_subtasks" in teamlead["permissions"]
    assert "task.create_subtask" not in teamlead["permissions"]
    assert "task.delete_subtask" not in teamlead["permissions"]

    manager = next(r for r in roles if r["name"] == "Менеджер")
    assert "task.manage_subtasks" in manager["permissions"]

    dev = next(r for r in roles if r["name"] == "Разработчик")
    assert "task.manage_subtasks" in dev["permissions"]


def test_known_permissions_endpoint_returns_four_codes(client):
    _register(client, "anyone@example.com")
    r = client.get("/api/v1/permissions")
    assert r.status_code == 200
    perms = set(r.json())
    assert perms == {
        "task.view",
        "task.edit_settings",
        "task.manage_members",
        "task.manage_subtasks",
    }


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


def test_assign_user_rejects_role_from_other_tree(client):
    _register(client, "owner@example.com")
    project_a = _make_project(client, "Проект A")
    r = client.post("/api/v1/tasks", json={"name": "Проект B"})
    assert r.status_code == 201, r.text
    project_b = r.json()["id"]
    foreign_role_id = client.get(f"/api/v1/tasks/{project_b}/roles").json()[0]["id"]

    _register(client, "guest@example.com")
    _login(client, "owner@example.com")

    r = client.post(
        f"/task_management/{project_a}",
        data={"email": "guest@example.com", "role_id": str(foreign_role_id)},
        follow_redirects=False,
    )
    assert r.status_code == 422


def test_assign_user_accepts_ancestor_role_for_subtask(client):
    _register(client, "owner@example.com")
    project_id = _make_project(client)
    subtask_id = _make_subtask(client, project_id)
    root_role_id = client.get(f"/api/v1/tasks/{project_id}/roles").json()[0]["id"]

    _register(client, "guest@example.com")
    guest_id = client.get("/api/v1/auth/me").json()["id"]
    _login(client, "owner@example.com")

    r = client.post(
        f"/task_management/{subtask_id}",
        data={"email": "guest@example.com", "role_id": str(root_role_id)},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    role_task_id = _scalar(
        "SELECT tr.task_id "
        "FROM task_user_roles tur "
        "JOIN task_roles tr ON tr.id = tur.task_role_id "
        f"WHERE tur.task_id = {subtask_id} AND tur.user_id = {guest_id}"
    )
    assert role_task_id == project_id


def test_subtask_roles_include_ancestor_custom_role(client):
    _register(client, "owner@example.com")
    project_id = _make_project(client)
    r = client.post(
        f"/api/v1/tasks/{project_id}/roles",
        json={"name": "QA", "permissions": ["task.view"]},
    )
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]
    subtask_id = _make_subtask(client, project_id)

    roles = client.get(f"/api/v1/tasks/{subtask_id}/roles").json()
    inherited = next((r for r in roles if r["id"] == role_id), None)
    assert inherited is not None
    assert inherited["task_id"] == project_id


def test_subtask_management_does_not_edit_inherited_roles(client):
    _register(client, "owner@example.com")
    project_id = _make_project(client)
    r = client.post(
        f"/api/v1/tasks/{project_id}/roles",
        json={"name": "QA", "permissions": ["task.view"]},
    )
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]
    subtask_id = _make_subtask(client, project_id)

    r = client.get(f"/task_management/{subtask_id}")
    assert r.status_code == 200, r.text
    assert f'<option value="{role_id}">QA (из проекта Проект) ✦</option>' in r.text
    assert f'action="/task_management/{subtask_id}/roles/{role_id}"' not in r.text
    assert "У этой задачи нет собственных ролей" in r.text


def test_subtask_reuses_root_system_roles(client):
    _register(client, "owner@example.com")
    project_id = _make_project(client)
    subtask_id = _make_subtask(client, project_id)

    subtask_roles_count = _scalar(
        f"SELECT COUNT(*) FROM task_roles WHERE task_id = {subtask_id}"
    )
    assignment_role_task_id = _scalar(
        "SELECT tr.task_id "
        "FROM task_user_roles tur "
        "JOIN task_roles tr ON tr.id = tur.task_role_id "
        f"WHERE tur.task_id = {subtask_id}"
    )

    assert subtask_roles_count == 0
    assert assignment_role_task_id == project_id


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
