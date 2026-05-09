"""Полный сценарий восстановления пароля через токен (выпускаем токен
руками — почтового клиента в тестах нет)."""
from app.tokens import make_reset_token


def _register(client, email="reset@example.com", password="oldpass"):
    r = client.post(
        "/registration",
        data={"email": email, "name": "R", "surname": "U", "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_password_reset_full_cycle(client):
    _register(client)
    token = make_reset_token("reset@example.com")

    r = client.get(f"/password-reset/{token}")
    assert r.status_code == 200
    assert "csrf_token" in r.text or "token" in r.text

    r = client.post(
        f"/password-reset/{token}",
        data={"password": "newpass1", "password2": "newpass1"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "обновл" in r.text.lower() or "новым" in r.text.lower()

    # Старый пароль больше не подходит
    r = client.post(
        "/", data={"email": "reset@example.com", "password": "oldpass"},
        follow_redirects=False,
    )
    assert r.status_code == 200  # остаётся на /, не редирект
    assert "Неправильный" in r.text

    # Новый — подходит
    r = client.post(
        "/", data={"email": "reset@example.com", "password": "newpass1"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_password_reset_password_mismatch(client):
    _register(client)
    token = make_reset_token("reset@example.com")
    r = client.post(
        f"/password-reset/{token}",
        data={"password": "abcdef", "password2": "different"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "не совпадают" in r.text.lower()


def test_password_reset_too_short(client):
    _register(client)
    token = make_reset_token("reset@example.com")
    r = client.post(
        f"/password-reset/{token}",
        data={"password": "abc", "password2": "abc"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "не короче" in r.text.lower()


def test_password_reset_user_deleted(client, monkeypatch):
    """Если юзер исчез между выдачей токена и его использованием — 404."""
    token = make_reset_token("ghost@example.com")
    r = client.get(f"/password-reset/{token}")
    assert r.status_code == 404
