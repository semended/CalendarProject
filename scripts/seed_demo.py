"""Наполняет БД демо-пользователем с огромной занятостью.

Запуск:
    python -m scripts.seed_demo

Создаёт (или обновляет):
- пользователя demo@demo.ru / пароль demo
- 6 проектов, каждый с 3-уровневым деревом подзадач (~80 задач)
- ~50 availability-слотов (busy / meeting / focus / off) на ближайшие 6 недель

Идемпотентно — повторный запуск удаляет прежние данные демо-юзера и создаёт заново.
"""

import asyncio
import random
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import (
    AvailabilitySlot,
    Task,
    TaskRole,
    TaskRolePermission,
    TaskUserRole,
    User,
)
from app.permissions import ensure_role_permissions
from app.security import hash_password

DEMO_EMAIL = "demo@demo.ru"
DEMO_PASSWORD = "demo"

COLORS = ["#0ea5e9", "#f97316", "#10b981", "#a855f7", "#ef4444", "#eab308", "#14b8a6", "#ec4899"]
STATES = ["todo", "in_progress", "review", "done", "paused"]

PROJECTS = [
    {
        "name": "Релиз мобильного приложения v2.0",
        "desc": "Большой кросс-командный проект: iOS, Android, бэкенд, QA, маркетинг.",
        "subtasks": [
            ("Архитектура и дизайн системы", [
                "Обновить C4-диаграммы",
                "Ревью API контрактов",
                "Решить про миграцию на gRPC",
            ]),
            ("iOS клиент", [
                "Переписать экран профиля на SwiftUI",
                "Интегрировать push-уведомления",
                "Тёмная тема",
                "Локализация EN/RU/DE",
            ]),
            ("Android клиент", [
                "Compose-миграция экрана ленты",
                "ExoPlayer вместо MediaPlayer",
                "Очистить deprecated API-вызовы",
            ]),
            ("Бэкенд", [
                "Оптимизация запросов к ленте",
                "Новые ручки для фичи stories",
                "Rate limiting на /api/v2/*",
            ]),
            ("QA и релиз", [
                "Regression pack обновить",
                "Нагрузочное тестирование",
                "Подготовить release notes",
            ]),
        ],
    },
    {
        "name": "Миграция инфраструктуры в Kubernetes",
        "desc": "Перевозим монолит и сервисы с VM на k8s-кластер.",
        "subtasks": [
            ("Подготовка кластера", ["Helm charts", "Ingress + TLS", "Observability stack"]),
            ("Монолит → контейнер", ["Dockerfile", "Health-checks", "Config через env"]),
            ("CI/CD пайплайны", ["ArgoCD", "Staging env", "Blue-green deploy"]),
            ("Данные", ["Репликация Postgres", "Бэкап-стратегия", "Миграция Redis"]),
        ],
    },
    {
        "name": "Редизайн личного кабинета",
        "desc": "Переделываем ЛК — новая информационная архитектура, фигма, фронт.",
        "subtasks": [
            ("Исследования", ["Интервью с пользователями", "Юзабилити-тесты старой версии"]),
            ("UX/UI", ["Новая IA", "Макеты в Figma", "Design system update"]),
            ("Frontend", ["Миграция на Next.js 15", "Storybook для новых компонентов", "A/B тест"]),
        ],
    },
    {
        "name": "Годовой отчёт и аудит",
        "desc": "Подготовка финансового и технического отчёта за 2025.",
        "subtasks": [
            ("Финансы", ["P&L сборка", "Reconciliation с банком", "Аудиторский пакет"]),
            ("Техника", ["Обзор SLA", "Инцидент post-mortems", "Капекс-план"]),
            ("Презентация", ["Слайды для борда", "One-pager для инвесторов"]),
        ],
    },
    {
        "name": "ML-платформа: MVP",
        "desc": "Строим внутреннюю ML-платформу: feature store, training, serving.",
        "subtasks": [
            ("Feature store", ["Схема offline/online", "SDK для DS", "Пайплайн ингеста"]),
            ("Training", ["Airflow + MLflow", "Регистри моделей"]),
            ("Serving", ["K8s-инференс", "Canary deploy моделей", "Мониторинг дрифта"]),
        ],
    },
    {
        "name": "Онбординг новых инженеров",
        "desc": "Улучшаем процесс введения в строй новичков: документация, buddy, первые задачи.",
        "subtasks": [
            ("Документация", ["Dev setup guide", "Архитектурный обзор", "Кодстайл"]),
            ("Процесс", ["Buddy-программа", "Чеклист первых 2 недель"]),
            ("Автоматизация", ["Скрипт-инсталлер окружения", "Стартовые репозитории"]),
        ],
    },
]


def offset(days: int, hour: int = 18) -> datetime:
    """Дедлайн = сегодня + days, с заданным часом."""
    base = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    return base + timedelta(days=days)


async def wipe_demo(db, user_id: int) -> None:
    root_ids = (
        await db.execute(
            select(Task.id).where(Task.creator_id == user_id, Task.parent_task_id.is_(None))
        )
    ).scalars().all()
    # CASCADE в БД сам унесёт подзадачи, task_roles, task_user_roles
    for rid in root_ids:
        await db.execute(delete(Task).where(Task.id == rid))
    await db.execute(delete(AvailabilitySlot).where(AvailabilitySlot.user_id == user_id))
    await db.commit()


async def add_task_with_role(
    db, *, creator_id, name, description, color, duration, parent_task_id, ended_at, state,
) -> Task:
    task = Task(
        creator_id=creator_id,
        parent_task_id=parent_task_id,
        name=name,
        description=description,
        color=color,
        duration=duration,
        ended_at=ended_at,
        state=state,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    if parent_task_id is None:
        # Для корня — заводим роли и назначаем юзера тимлидом.
        teamlead = TaskRole(task_id=task.id, name="Тимлид")
        manager = TaskRole(task_id=task.id, name="Менеджер")
        dev = TaskRole(task_id=task.id, name="Разработчик")
        db.add_all([teamlead, manager, dev])
        await db.commit()
        for r in (teamlead, manager, dev):
            await db.refresh(r)
            await ensure_role_permissions(db, r)
        db.add(TaskUserRole(user_id=creator_id, task_id=task.id, task_role_id=teamlead.id))
        await db.commit()
    return task


async def seed_availability(db, user_id: int) -> None:
    rng = random.Random(42)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    kinds = ["busy", "meeting", "focus", "off"]
    notes = {
        "busy": ["Встреча с командой", "Ревью PR", "1:1 с тимлидом", "Синк по релизу"],
        "meeting": ["Планирование спринта", "Демо заказчику", "Интервью кандидата", "Standup"],
        "focus": ["Работа над дизайн-доком", "Фикс багов", "Кодревью", "Рефакторинг модуля"],
        "off": ["Обед", "Спортзал", "Отгул — врач"],
    }

    for d in range(-7, 35):  # прошлая неделя + 5 недель вперёд
        day = today + timedelta(days=d)
        if day.weekday() >= 5:  # выходные — 1-2 события
            count = rng.randint(0, 2)
        else:
            count = rng.randint(2, 4)
        used_hours: list[tuple[int, int]] = []
        for _ in range(count):
            kind = rng.choice(kinds)
            start_h = rng.randint(9, 19)
            length = rng.choice([1, 1, 2, 3])
            end_h = min(start_h + length, 22)
            # избегаем пересечений внутри дня
            if any(not (end_h <= s or start_h >= e) for s, e in used_hours):
                continue
            used_hours.append((start_h, end_h))
            note = rng.choice(notes[kind])
            db.add(AvailabilitySlot(
                user_id=user_id,
                start_at=day.replace(hour=start_h),
                end_at=day.replace(hour=end_h),
                kind=kind,
                note=note,
            ))
    await db.commit()


async def main() -> None:
    async with SessionLocal() as db:
        # 1) Пользователь
        existing = (
            await db.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing:
            user = existing
            user.password = hash_password(DEMO_PASSWORD)
            user.confirmed = True
            await db.commit()
            await wipe_demo(db, user.id)
            print(f"[=] Обновил demo-юзера (id={user.id}), старые задачи снесены.")
        else:
            user = User(
                email=DEMO_EMAIL,
                name="Демо",
                surname="Пользователь",
                password=hash_password(DEMO_PASSWORD),
                bio="Это тестовый аккаунт с большим количеством задач и занятости.",
                position="Engineering Manager",
                company="Demo Corp",
                workplace="Москва",
                pronouns="они/их",
                confirmed=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"[+] Создал demo-юзера id={user.id}.")

        rng = random.Random(1)
        total = 0

        # 2) Проекты
        for proj_idx, proj in enumerate(PROJECTS):
            proj_end = offset(30 + proj_idx * 10, hour=18)
            proj_color = COLORS[proj_idx % len(COLORS)]
            project = await add_task_with_role(
                db,
                creator_id=user.id,
                name=proj["name"],
                description=proj["desc"],
                color=proj_color,
                duration=int((proj_end - datetime.now()).total_seconds()),
                parent_task_id=None,
                ended_at=proj_end,
                state="in_progress",
            )
            total += 1

            for block_idx, (block_name, leaves) in enumerate(proj["subtasks"]):
                # средний уровень
                mid_end = offset(10 + proj_idx * 5 + block_idx * 3, hour=17)
                block = await add_task_with_role(
                    db,
                    creator_id=user.id,
                    name=block_name,
                    description=f"Блок работ: {block_name}.",
                    color=proj_color,
                    duration=int((mid_end - datetime.now()).total_seconds()),
                    parent_task_id=project.id,
                    ended_at=mid_end,
                    state=rng.choice(["todo", "in_progress", "review"]),
                )
                total += 1

                for leaf_idx, leaf_name in enumerate(leaves):
                    # часть задач просрочена, часть будущая
                    days_shift = rng.randint(-10, 25)
                    leaf_end = offset(days_shift, hour=rng.choice([11, 14, 17, 19]))
                    state = rng.choice(STATES)
                    await add_task_with_role(
                        db,
                        creator_id=user.id,
                        name=leaf_name,
                        description=f"Подзадача «{leaf_name}» для блока «{block_name}».",
                        color=proj_color,
                        duration=max(3600, int((leaf_end - datetime.now()).total_seconds())),
                        parent_task_id=block.id,
                        ended_at=leaf_end,
                        state=state,
                    )
                    total += 1

        print(f"[+] Создал {total} задач ({len(PROJECTS)} проектов + блоки + листья).")

        # 3) Занятость
        await seed_availability(db, user.id)
        slot_count = (
            await db.execute(
                select(AvailabilitySlot).where(AvailabilitySlot.user_id == user.id)
            )
        ).scalars().all()
        print(f"[+] Добавил {len(slot_count)} слотов занятости на 6 недель.")

        print()
        print("─" * 60)
        print(f"Готово. Логинься: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print("─" * 60)


if __name__ == "__main__":
    asyncio.run(main())
