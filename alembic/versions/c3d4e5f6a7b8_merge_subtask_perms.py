"""Объединение task.create_subtask + task.delete_subtask → task.manage_subtasks

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-09

Логика data-migration:
1. Все строки с permission IN (create_subtask, delete_subtask) преобразуются
   в manage_subtasks; имя (name-колонка) тоже обновляется.
2. Если у роли уже были обе строки — после обновления получим дубликаты.
   Их снимаем DELETE с подзапросом по min(id), оставляя одну.
3. UNIQUE-constraint'а на (task_role_id, permission) в БД нет — чистка
   опирается на простую агрегацию.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Переименовываем оба старых кода в новый
    op.execute("""
        UPDATE task_role_permissions
        SET permission = 'task.manage_subtasks',
            name       = 'task.manage_subtasks'
        WHERE permission IN ('task.create_subtask', 'task.delete_subtask')
    """)
    # 2. Удаляем дубликаты, которые получились у ролей, имевших оба исходных
    #    кода (типичный случай — Менеджер). Оставляем строку с min(id).
    op.execute("""
        DELETE FROM task_role_permissions
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM task_role_permissions
            GROUP BY task_role_id, permission
        )
    """)


def downgrade() -> None:
    # Развёртка односторонняя — без знания, какие именно роли исторически
    # имели create_subtask vs delete_subtask, их разделить нельзя. Откат
    # копирует строку manage_subtasks как create_subtask (что покроет
    # типичный сценарий "только создание", но потеряет delete-семантику).
    op.execute("""
        UPDATE task_role_permissions
        SET permission = 'task.create_subtask',
            name       = 'task.create_subtask'
        WHERE permission = 'task.manage_subtasks'
    """)
