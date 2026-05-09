"""Optional из этапа 3: Task.deleted_at для soft delete

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-09

Поведение: задача с deleted_at IS NOT NULL не показывается в списках/деревьях,
но физически остаётся в БД (для восстановления и аудита). Жёсткий DELETE
оставлен только для явного "забыть навсегда" — в текущем UI его нет.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "tasks_deleted_at_idx", "tasks", ["deleted_at"]
    )


def downgrade() -> None:
    op.drop_index("tasks_deleted_at_idx", table_name="tasks")
    op.drop_column("tasks", "deleted_at")
