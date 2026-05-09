"""Integration-тесты на JWT-аутентификацию через /api/v1/auth/token."""


def _register(client, email="alice@example.com", password="secret123"):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Alice", "surname": "A"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _issue_token(client, email, password):
    # OAuth2 password grant — form-data, не JSON
    r = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    return r


def test_token_endpoint_returns_bearer_token(client):
    _register(client, email="u@example.com", password="pw123456")
    client.cookies.clear()

    r = _issue_token(client, "u@example.com", "pw123456")
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_token_endpoint_rejects_wrong_password(client):
    _register(client, email="u@example.com", password="pw123456")
    client.cookies.clear()

    r = _issue_token(client, "u@example.com", "wrong-pw")
    assert r.status_code == 401


def test_bearer_token_unlocks_me(client):
    me = _register(client, email="u@example.com", password="pw123456")
    client.cookies.clear()

    r = _issue_token(client, "u@example.com", "pw123456")
    token = r.json()["access_token"]

    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == me["id"]


def test_bearer_token_unlocks_task_crud(client):
    _register(client, email="u@example.com", password="pw123456")
    client.cookies.clear()

    r = _issue_token(client, "u@example.com", "pw123456")
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # создаём задачу через bearer
    r = client.post("/api/v1/tasks", json={"name": "via JWT"}, headers=headers)
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["name"] == "via JWT"

    # list
    r = client.get("/api/v1/tasks", headers=headers)
    assert r.status_code == 200
    assert any(t["id"] == task["id"] for t in r.json())


def test_bad_bearer_token_is_rejected(client):
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401
    assert "Невалидный" in r.json()["detail"]


def test_missing_auth_still_returns_401(client):
    # ни Bearer, ни cookie
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_jwt_does_not_authorize_html_page(client):
    """GET /main под Bearer без cookie не должен залогинить —
    HTML-зависимости (get_current_user) смотрят только на сессию."""
    _register(client, email="htmluser@example.com", password="pw123456")
    client.cookies.clear()

    r = _issue_token(client, "htmluser@example.com", "pw123456")
    token = r.json()["access_token"]

    r = client.get(
        "/main",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    # RedirectToLogin → 303 на /
    assert r.status_code == 303
    assert r.headers["location"].endswith("/")
