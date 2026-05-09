"""DELETE /api/v1/tasks/{id} — soft delete + проверка фильтрации в выборках."""


def _register(client, email="d@example.com"):
    r = client.post(
        "/registration",
        data={"email": email, "name": "D", "surname": "X", "password": "pw123456"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _project(client, name="P"):
    r = client.post(
        "/create_task",
        data={"taskName": name, "taskDescription": "", "taskColor": "#000"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client.get("/api/v1/tasks").json()[0]["id"]


def _subtask(client, parent_id, name="sub"):
    r = client.post(
        "/api/v1/tasks",
        json={"name": name, "description": "", "color": "#111",
              "parent_task_id": parent_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_delete_root_project_marks_subtree(client):
    _register(client)
    pid = _project(client)
    s1 = _subtask(client, pid, "sub-1")
    s2 = _subtask(client, pid, "sub-2")
    s11 = _subtask(client, s1, "sub-1.1")

    r = client.delete(f"/api/v1/tasks/{pid}")
    assert r.status_code == 204

    # GET всех 4 — теперь 404 (soft-deleted ≡ "не существует" для UI)
    for tid in (pid, s1, s2, s11):
        r = client.get(f"/api/v1/tasks/{tid}")
        assert r.status_code == 404

    # /api/v1/tasks тоже не должен возвращать ничего
    assert client.get("/api/v1/tasks").json() == []


def test_delete_subtask_does_not_affect_root(client):
    _register(client)
    pid = _project(client)
    sub_id = _subtask(client, pid, "будет удалена")
    keep_id = _subtask(client, pid, "останется")

    r = client.delete(f"/api/v1/tasks/{sub_id}")
    assert r.status_code == 204

    # root — на месте
    r = client.get(f"/api/v1/tasks/{pid}")
    assert r.status_code == 200

    # удалённая subtask — 404
    r = client.get(f"/api/v1/tasks/{sub_id}")
    assert r.status_code == 404

    # /subtasks возвращает только живую
    r = client.get(f"/api/v1/tasks/{pid}/subtasks")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == keep_id


def test_outsider_cannot_delete(client):
    _register(client, "owner@example.com")
    pid = _project(client)

    _register(client, "outsider@example.com")
    r = client.delete(f"/api/v1/tasks/{pid}")
    assert r.status_code == 403


def test_delete_unknown_task_returns_404(client):
    _register(client)
    r = client.delete("/api/v1/tasks/99999")
    assert r.status_code == 404


def test_delete_writes_event(client):
    """task.deleted событие пишется в task_events для аудита."""
    import psycopg2
    _register(client)
    pid = _project(client)
    _subtask(client, pid, "sub-cleanup")

    r = client.delete(f"/api/v1/tasks/{pid}")
    assert r.status_code == 204

    conn = psycopg2.connect("postgresql://postgres:123@localhost:5432/testdb_test")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM task_events WHERE event_type='task.deleted'"
        )
        n = cur.fetchone()[0]
    conn.close()
    assert n == 1
