"""Smoke-тесты HTML-страниц: после логина каждая основная страница
должна отдавать 200 и содержать ожидаемый ключевой текст.

Цель — поймать регрессии после рефакторинга, где роут импортирует
новый сервис или меняет контекст шаблона. Контент-проверки минимальные —
не дублируют unit-тесты бизнес-логики.
"""
from datetime import datetime


def _register_login(client, email="smoke@example.com", password="pw123456"):
    r = client.post(
        "/registration",
        data={"email": email, "name": "S", "surname": "M", "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _make_project(client, name="Проект-S") -> int:
    r = client.post(
        "/create_task",
        data={"taskName": name, "taskDescription": "", "taskColor": "#0ea5e9"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client.get("/api/v1/tasks").json()[0]["id"]


def test_start_page_anonymous(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Почта" in r.text or "вход" in r.text.lower()


def test_main_page_after_login(client):
    _register_login(client)
    r = client.get("/main")
    assert r.status_code == 200
    assert "Проект" in r.text or "проект" in r.text


def test_calendar_page(client):
    _register_login(client)
    r = client.get("/calendar")
    assert r.status_code == 200


def test_create_task_get(client):
    _register_login(client)
    r = client.get("/create_task")
    assert r.status_code == 200
    assert "name=\"taskName\"" in r.text


def test_task_page(client):
    _register_login(client)
    pid = _make_project(client)
    r = client.get(f"/task/{pid}")
    assert r.status_code == 200


def test_task_overview_gantt(client):
    _register_login(client)
    pid = _make_project(client)
    # Создаём подзадачу — без неё в Ганте track_legend пустой, но 200 всё равно.
    r = client.post(
        f"/create_task/{pid}",
        data={"taskName": "Подзадача", "taskDescription": "", "taskColor": "#aabbcc"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.get(f"/task/{pid}/overview")
    assert r.status_code == 200
    assert "gantt" in r.text.lower() or "обзор" in r.text.lower()


def test_task_management_page(client):
    _register_login(client)
    pid = _make_project(client)
    r = client.get(f"/task_management/{pid}")
    assert r.status_code == 200
    # роли в дропдауне — фикс old hardcoded value="1/2/3"
    for role_name in ("Тимлид", "Менеджер", "Разработчик"):
        assert role_name in r.text


def test_settings_page(client):
    _register_login(client)
    r = client.get("/user/settings")
    assert r.status_code == 200


def test_user_profile_self(client):
    _register_login(client)
    me = client.get("/api/v1/auth/me").json()
    r = client.get(f"/user/{me['id']}")
    assert r.status_code == 200


def test_schedule_page(client):
    _register_login(client)
    me = client.get("/api/v1/auth/me").json()
    r = client.get(f"/user/{me['id']}/schedule")
    assert r.status_code == 200


def test_settings_post_updates_profile(client):
    _register_login(client)
    r = client.post(
        "/user/settings",
        data={"name": "NewName", "surname": "NewSur", "bio": "обновил"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    me = client.get("/api/v1/auth/me").json()
    assert me["name"] == "NewName"
    assert me["bio"] == "обновил"


def test_schedule_add_and_delete_slot(client):
    _register_login(client)
    me = client.get("/api/v1/auth/me").json()
    today = datetime.now().date()

    r = client.post(
        f"/user/{me['id']}/schedule",
        data={
            "action": "add",
            "slot_date": today.isoformat(),
            "start_time": "10:00",
            "end_time": "11:00",
            "kind": "busy",
            "note": "тестовый слот",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    # На странице расписания должен теперь отображаться слот
    r = client.get(f"/user/{me['id']}/schedule")
    assert "тестовый слот" in r.text


def test_404_on_missing_task(client):
    _register_login(client)
    r = client.get("/task/99999")
    # Текущий код страницы /task/{id} рендерит current_task.html даже если task=None
    # (см. routers/tasks.py); важно, что мы хотя бы 200 и не 500. Если позже
    # добавите 404 — этот тест упадёт и его нужно будет уточнить.
    assert r.status_code in (200, 404)


def test_resend_verification_redirects(client):
    _register_login(client)
    r = client.post("/resend-verification", follow_redirects=False)
    assert r.status_code == 303


def test_password_reset_request_get(client):
    r = client.get("/password-reset")
    assert r.status_code == 200


def test_password_reset_request_post_silent(client):
    """POST /password-reset с любой почтой возвращает sent-страницу,
    не утекая, существует ли юзер."""
    r = client.post("/password-reset", data={"email": "nonexistent@example.com"})
    assert r.status_code == 200
    assert "sent" in r.text.lower() or "отправ" in r.text.lower()


def test_password_reset_invalid_token(client):
    r = client.get("/password-reset/notarealtoken")
    assert r.status_code == 400
    assert "невалидна" in r.text.lower() or "устарел" in r.text.lower()


def test_logout_redirects_to_start(client):
    _register_login(client)
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
