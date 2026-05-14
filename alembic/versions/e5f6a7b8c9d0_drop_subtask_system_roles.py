"""Удалить клоны системных ролей подзадач

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-13

Data-only миграция: назначения на системные роли подзадач переводятся на
одноимённые системные роли корня, после чего клоны удаляются.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROLES_TO_MERGE_CTE = """
WITH RECURSIVE task_tree AS (
    SELECT id, parent_task_id, id AS root_id
    FROM tasks
    WHERE parent_task_id IS NULL
    UNION ALL
    SELECT t.id, t.parent_task_id, tt.root_id
    FROM tasks t
    JOIN task_tree tt ON t.parent_task_id = tt.id
),
roles_to_merge AS (
    SELECT tr.id AS old_id, tr_root.id AS new_id
    FROM task_roles tr
    JOIN task_tree tt ON tr.task_id = tt.id AND tt.id != tt.root_id
    JOIN task_roles tr_root
      ON tr_root.task_id = tt.root_id
     AND tr_root.name = tr.name
     AND tr_root.is_system = true
    WHERE tr.is_system = true
)
"""


def upgrade() -> None:
    op.execute(_ROLES_TO_MERGE_CTE + """
        DELETE FROM task_user_roles tur
        USING roles_to_merge rtm
        WHERE tur.task_role_id = rtm.old_id
          AND EXISTS (
              SELECT 1
              FROM task_user_roles existing
              WHERE existing.user_id = tur.user_id
                AND existing.task_id = tur.task_id
                AND existing.task_role_id = rtm.new_id
          )
    """)
    op.execute(_ROLES_TO_MERGE_CTE + """
        UPDATE task_user_roles tur
        SET task_role_id = rtm.new_id
        FROM roles_to_merge rtm
        WHERE tur.task_role_id = rtm.old_id
    """)
    op.execute(_ROLES_TO_MERGE_CTE + """
        DELETE FROM task_role_permissions trp
        USING roles_to_merge rtm
        WHERE trp.task_role_id = rtm.old_id
    """)
    op.execute(_ROLES_TO_MERGE_CTE + """
        DELETE FROM task_roles tr
        USING roles_to_merge rtm
        WHERE tr.id = rtm.old_id
    """)


def downgrade() -> None:
    # Развёртка односторонняя: после слияния нет журнала, по которому можно
    # восстановить старые id ролей и их индивидуальные наборы прав.
    pass
