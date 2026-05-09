"""Тесты пользовательских сценариев через Jinja-формы.

Здесь мы ходим по тем же URL, что и реальный юзер в браузере —
через POST /, GET /main, POST /create_task и т.д. Смысл — ловить
баги интеграции формы и роута, которые API-тесты не видят.
"""

import re



def _register_form(client, email="flow@example.com", password="pw123456",
                   name="Flow", surname="Тест"):
    r = client.post(
        "/registration",
        data={"email": email, "name": name, "surname": surname, "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    # /registration делает auto-login и редиректит на /main
    assert r.headers["location"].endswith("/main")


def _login_form(client, email="flow@example.com", password="pw123456"):
    r = client.post(
        "/",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def _create_root_task(client, name="Проект через форму", color="#0ea5e9",
                      description="тест") -> int:
    r = client.post(
        "/create_task",
        data={
            "taskName": name,
            "taskDescription": description,
            "taskColor": color,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    # Без parent → редирект на /main
    assert r.headers["location"].endswith("/main")

    # вытащим id созданного: он последний у пользователя
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    tasks = [t for t in r.json() if t["name"] == name]
    assert tasks, "корневая задача не нашлась в /api/v1/tasks"
    return tasks[0]["id"]


def _get_user_id(client) -> int:
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    return r.json()["id"]


# ---------- registration + basic pages ----------

def test_form_registration_and_main_page(client):
    _register_form(client)

    r = client.get("/main")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_form_login_after_logout(client):
    _register_form(client)
    client.post("/api/v1/auth/logout")
    client.cookies.clear()

    _login_form(client)
    r = client.get("/main")
    assert r.status_code == 200


# ---------- создание задач через форму ----------

def test_create_root_task_via_form(client):
    _register_form(client)
    task_id = _create_root_task(client, name="Мой первый проект")

    r = client.get(f"/api/v1/tasks/{task_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["parent_task_id"] is None
    assert data["name"] == "Мой первый проект"


def test_create_subtask_via_path_param(client):
    """Способ №1: POST /create_task/{parent_id} (кнопка '+ Добавить задачу' в current_task.html)."""
    _register_form(client)
    root_id = _create_root_task(client, name="Корень-1")

    r = client.post(
        f"/create_task/{root_id}",
        data={
            "taskName": "Подзадача через path",
            "taskDescription": "",
            "taskColor": "#10b981",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    # при parent != None редиректим назад в проект
    assert r.headers["location"].endswith(f"/task/{root_id}")

    r = client.get(f"/api/v1/tasks/{root_id}/subtasks")
    assert r.status_code == 200
    subs = r.json()
    assert len(subs) == 1
    assert subs[0]["parent_task_id"] == root_id
    assert subs[0]["name"] == "Подзадача через path"


def test_create_subtask_via_hidden_form_field(client):
    """Регресс-тест на баг: шаблон current_task.html постит на /create_task
    (без parent в URL), а parent_task_id передаёт hidden-полем формы.

    До фикса хендлер игнорировал hidden-поле и создавал корневой проект
    параллельно с подзадачей. Проверяем что этого не происходит.
    """
    _register_form(client)
    root_id = _create_root_task(client, name="Корень-2")

    r = client.post(
        "/create_task",
        data={
            "parent_task_id": str(root_id),
            "taskName": "Подзадача через hidden",
            "taskDescription": "",
            "taskColor": "#ef4444",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"].endswith(f"/task/{root_id}"), (
        "после создания подзадачи надо редиректить обратно в проект, "
        "а не на /main"
    )

    # главное: только одна дочерняя задача, и нет паразитного корня
    r = client.get(f"/api/v1/tasks/{root_id}/subtasks")
    assert r.status_code == 200
    subs = r.json()
    assert len(subs) == 1, f"ожидалась 1 подзадача, получили {subs}"
    assert subs[0]["name"] == "Подзадача через hidden"
    assert subs[0]["parent_task_id"] == root_id

    # и никаких "левых" корневых проектов с этим именем не появилось
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    named = [t for t in r.json() if t["name"] == "Подзадача через hidden"]
    assert len(named) == 1, (
        "подзадача продублировалась в корень — баг #5 вернулся"
    )
    assert named[0]["parent_task_id"] == root_id


def test_subtask_not_shown_as_root_on_main(client):
    """Регресс: после создания подзадачи /main должен показывать
    только корневой проект, без паразитной карточки-подзадачи.

    Баг #5 (версия 2): даже когда parent_task_id правильно сохранялся,
    подзадача всё равно отображалась в ленте "Все проекты", потому что
    get_tasks_by_user_id возвращает любые задачи, где юзер имеет роль
    (включая унаследованные Тимлид-роли на подзадачах).
    """
    _register_form(client)
    root_id = _create_root_task(client, name="Единственный-корень")

    client.post(
        "/create_task",
        data={
            "parent_task_id": str(root_id),
            "taskName": "Не-должен-быть-в-ленте",
            "taskDescription": "",
            "taskColor": "#ef4444",
        },
        follow_redirects=False,
    )

    r = client.get("/main")
    assert r.status_code == 200
    # на странице "Все проекты" должна быть ровно одна карточка
    card_ids = re.findall(r'data-task-id="(\d+)"', r.text)
    assert card_ids == [str(root_id)], (
        f"в /main протекли подзадачи: {card_ids}"
    )
    assert "Не-должен-быть-в-ленте" not in r.text


def test_create_subtask_without_permission_rejected(client):
    """Чужой юзер не должен мочь добавлять подзадачи в проект, где у него нет роли."""
    _register_form(client, email="owner@example.com")
    root_id = _create_root_task(client, name="Приватный проект")
    client.post("/api/v1/auth/logout")
    client.cookies.clear()

    _register_form(client, email="intruder@example.com")
    r = client.post(
        "/create_task",
        data={
            "parent_task_id": str(root_id),
            "taskName": "Взлом",
            "taskDescription": "",
            "taskColor": "#000000",
        },
        follow_redirects=False,
    )
    assert r.status_code == 403


# ---------- страницы: календарь, расписание, ганта ----------

def test_calendar_page_renders_all_seven_weekdays(client):
    _register_form(client)
    r = client.get("/calendar")
    assert r.status_code == 200
    html = r.text
    # все 7 заголовков дней недели должны присутствовать в разметке —
    # если на фронте колонки сб/вс обрежет CSS, это не словит тест
    # (CSS ловится только в браузере), но здесь ловим регресс когда
    # сервер сам отдаёт < 7 колонок
    for dow in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
        assert f">{dow}<" in html, f"колонка {dow} пропала в календаре"


def test_calendar_links_to_schedule(client):
    _register_form(client)
    user_id = _get_user_id(client)
    r = client.get("/calendar")
    assert r.status_code == 200
    # должна быть ссылка "Неделя →" на /user/{id}/schedule
    assert f"/user/{user_id}/schedule" in r.text


def test_schedule_page_renders(client):
    _register_form(client)
    user_id = _get_user_id(client)
    r = client.get(f"/user/{user_id}/schedule")
    assert r.status_code == 200
    # должны быть все 7 заголовков дней
    for dow in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
        assert f">{dow}<" in r.text


def test_schedule_has_link_back_to_calendar(client):
    """Юзерский нюанс: из календаря есть кнопка 'Неделя →' в расписание,
    но обратного перехода в шапке расписания нет (только через сайдбар).
    Тест проверяет что в header-area расписания есть in-page ссылка на
    /calendar (а не только в общем sidebar)."""
    _register_form(client)
    user_id = _get_user_id(client)
    r = client.get(f"/user/{user_id}/schedule")
    assert r.status_code == 200
    # Вырезаем содержимое <header ...> ... </header> — sidebar туда не попадает
    m = re.search(r"<header\b[^>]*>(.*?)</header>", r.text, re.DOTALL)
    assert m, "на странице расписания должен быть <header>"
    header_html = m.group(1)
    assert "/calendar" in header_html, (
        "в шапке /user/{id}/schedule должна быть кнопка возврата "
        "в /calendar (баг #2)"
    )


def test_task_overview_gantt_page(client):
    _register_form(client)
    root_id = _create_root_task(client)
    # добавим пару подзадач для гантова
    for nm in ("A", "B", "C"):
        client.post(
            f"/create_task/{root_id}",
            data={"taskName": nm, "taskDescription": "", "taskColor": "#0ea5e9"},
        )

    r = client.get(f"/task/{root_id}/overview")
    assert r.status_code == 200
    assert "gantt-grid" in r.text
    assert "gantt-label" in r.text
