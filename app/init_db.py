"""Создаёт все таблицы в БД по моделям SQLAlchemy.

Запуск:
    python -m app.init_db
"""
from app.crud import init_db


if __name__ == "__main__":
    init_db()
    print("База данных инициализирована")
