"""Этап 3: last_login_at, task_events, task_comments, notifications

Revision ID: a1b2c3d4e5f6
Revises: 85155a07e605
Create Date: 2026-05-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "85155a07e605"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "task_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("task_events_task_id_idx", "task_events", ["task_id"])
    op.create_index("task_events_created_at_idx", "task_events", ["created_at"])

    op.create_table(
        "task_comments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("author_user_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("task_comments_task_id_idx", "task_comments", ["task_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "notifications_user_unread_idx", "notifications", ["user_id", "read_at"]
    )
    op.create_index(
        "notifications_created_at_idx", "notifications", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("notifications_created_at_idx", table_name="notifications")
    op.drop_index("notifications_user_unread_idx", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("task_comments_task_id_idx", table_name="task_comments")
    op.drop_table("task_comments")

    op.drop_index("task_events_created_at_idx", table_name="task_events")
    op.drop_index("task_events_task_id_idx", table_name="task_events")
    op.drop_table("task_events")

    op.drop_column("users", "last_login_at")
