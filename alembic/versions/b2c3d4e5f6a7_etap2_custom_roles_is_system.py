"""Задача 2: TaskRole.is_system + бэкфилл для существующих дефолтных ролей

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_roles",
        sa.Column(
            "is_system",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    # Бэкфилл: все существующие роли с дефолтными именами помечаем как
    # системные (созданы автоматически в crud.create_task_bundle).
    op.execute(
        "UPDATE task_roles SET is_system = true "
        "WHERE name IN ('Тимлид', 'Менеджер', 'Разработчик')"
    )


def downgrade() -> None:
    op.drop_column("task_roles", "is_system")
