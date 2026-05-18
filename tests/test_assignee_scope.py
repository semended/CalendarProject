"""Регрессы для двух связанных багов:

1. assignee-кандидаты должны браться из ПРЯМОЙ команды задачи, а не из корня
   проекта. Член корня без явной роли на подзадаче не может быть назначен.
2. Открытие проекта с «частичным доступом» (юзер — член только подзадачи) не
   должно падать в 500 из-за lazy-load `Task.assignee` в Jinja-контексте.
"""
import os

import psycopg2


def _scalar(sql: str):
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None


def _register(client, email):
    r = client.post(
        "/registration",
        data={"email": email, "name": "U", "surname": "S", "password": "pw123456"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client.get("/api/v1/auth/me").json()["id"]


def _login(client, email):
    r = client.post(
        "/",
        data={"email": email, "password": "pw123456"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _project(client, name="Root"):
    r = client.post(
        "/create_task",
        data={"taskName": name, "taskDescription": "", "taskColor": "#0ea5e9"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client.get("/api/v1/tasks").json()[0]["id"]


def _subtask(client, parent_id: int, name="Sub") -> int:
    r = client.post(
        "/api/v1/tasks",
        json={"name": name, "description": "", "color": "#222222", "parent_task_id": parent_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _add_member(client, task_id: int, email: str, role_name: str):
    """Найти role_id с указанным именем на task_id или любом её предке."""
    role_id = _scalar(
        f"""
        WITH RECURSIVE chain AS (
            SELECT id, parent_task_id FROM tasks WHERE id={task_id}
            UNION ALL
            SELECT t.id, t.parent_task_id FROM tasks t
            JOIN chain c ON t.id = c.parent_task_id
        )
        SELECT r.id FROM task_roles r
        JOIN chain c ON r.task_id = c.id
        WHERE r.name='{role_name}'
        LIMIT 1
        """
    )
    assert role_id is not None, f"role {role_name!r} not found on task {task_id} or ancestors"
    r = client.post(
        f"/task_management/{task_id}",
        data={"email": email, "role_id": str(role_id)},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def test_assignee_candidates_include_direct_subtask_members(client):
    """Главный регресс Bug 1: прямой член подзадачи должен попадать в кандидатов.

    Раньше get_assignee_candidates возвращал членов КОРНЯ, и Designer'а
    подзадачи (не входящего в корень) нельзя было выбрать через UI или API.
    """
    _register(client, "owner@example.com")
    pid = _project(client, name="Root P")
    sid = _subtask(client, pid, name="UX/UI")

    designer_id = _register(client, "designer@example.com")
    _login(client, "owner@example.com")
    # Добавим designer-а на подзадачу с правом view, но без членства на корне
    r = client.post(
        f"/api/v1/tasks/{sid}/roles",
        json={"name": "Designer", "permissions": ["task.view"]},
    )
    assert r.status_code == 201, r.text
    _add_member(client, sid, "designer@example.com", "Designer")

    # Designer прямого членства на корне НЕ имеет
    direct_root = _scalar(
        f"SELECT COUNT(*) FROM task_user_roles WHERE user_id={designer_id} AND task_id={pid}"
    )
    assert direct_root == 0, "test setup: designer должен быть только на подзадаче"

    # PATCH через API: назначаем designer-а на ПОДЗАДАЧУ — должно пройти
    r = client.patch(f"/api/v1/tasks/{sid}", json={"assignee_id": designer_id})
    assert r.status_code == 200, r.text
    assert r.json()["assignee_id"] == designer_id

    # А вот назначить его же на КОРЕНЬ нельзя — он не член корня
    r = client.patch(f"/api/v1/tasks/{pid}", json={"assignee_id": designer_id})
    assert r.status_code == 422, r.text


def test_root_only_member_cannot_be_assigned_to_subtask(client):
    """Bug 1 — обратная сторона: член только корня не может быть assignee
    на подзадаче, если не входит в её команду явно. Воспроизводит сценарий
    Demo User из бага: Demo — Тимлид корня, но если убрать его прямое
    членство на подзадаче (как в demo seed), назначить его на subtask нельзя.
    """
    owner_id = _register(client, "owner@example.com")
    pid = _project(client, name="Root P")
    sid = _subtask(client, pid, name="UX/UI")

    # create_task_bundle авто-добавляет создателя на любую подзадачу. Снимем,
    # чтобы получить чистый сценарий «член только корня».
    r = client.post(
        f"/task_management/{sid}/members/{owner_id}/delete",
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert _scalar(
        f"SELECT COUNT(*) FROM task_user_roles WHERE user_id={owner_id} AND task_id={sid}"
    ) == 0

    # PATCH owner на subtask — 422 (не в прямой команде)
    r = client.patch(f"/api/v1/tasks/{sid}", json={"assignee_id": owner_id})
    assert r.status_code == 422, r.text


def test_partial_access_user_can_open_root_project(client):
    """Юзер N — член только подзадачи. У корневой подзадачи (sibling) есть
    assignee_id != NULL. Открытие /task/{root} не должно падать в 500."""
    owner_id = _register(client, "owner2@example.com")
    pid = _project(client, name="Root2")
    sid_visible = _subtask(client, pid, name="UX/UI 2")
    sid_with_assignee = _subtask(client, pid, name="Sibling с assignee")

    # owner — прямой Тимлид sibling-подзадачи (auto-added в create_task_bundle).
    # Назначаем его на эту подзадачу как assignee.
    r = client.patch(
        f"/api/v1/tasks/{sid_with_assignee}",
        json={"assignee_id": owner_id},
    )
    assert r.status_code == 200, r.text

    # Регистрируем нового юзера N и добавляем его только на sid_visible
    n_id = _register(client, "newuser@example.com")
    _login(client, "owner2@example.com")
    _add_member(client, sid_visible, "newuser@example.com", "Разработчик")

    # Логинимся под N, открываем корневой проект
    _login(client, "newuser@example.com")
    r = client.get(f"/task/{pid}")
    assert r.status_code == 200, r.text
    # Проверим, что страница реально отрендерилась и упоминает assignee
    # (sibling-подзадача показывается как «нет доступа» — без @, но рендер
    # не должен валиться)
    assert "Root2" in r.text or "UX/UI 2" in r.text or "Sibling" in r.text
