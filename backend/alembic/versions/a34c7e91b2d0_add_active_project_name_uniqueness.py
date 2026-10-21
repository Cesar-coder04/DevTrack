"""Enforce project name uniqueness within active scopes.

Revision ID: a34c7e91b2d0
Revises: 9d6f48c2a13b
Create Date: 2026-10-21 09:32:53
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a34c7e91b2d0"
down_revision: Union[str, Sequence[str], None] = "9d6f48c2a13b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _duplicate_group_count(
    connection,
    *,
    scope_column: str,
    scope_filter: str,
) -> int:
    query = sa.text(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT {scope_column}, name
            FROM projects
            WHERE {scope_filter}
              AND archived_at IS NULL
              AND deleted_at IS NULL
            GROUP BY {scope_column}, name
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
        """
    )
    return int(connection.scalar(query) or 0)


def upgrade() -> None:
    connection = op.get_bind()
    organization_duplicates = _duplicate_group_count(
        connection,
        scope_column="organization_id",
        scope_filter="organization_id IS NOT NULL",
    )
    personal_duplicates = _duplicate_group_count(
        connection,
        scope_column="owner_id",
        scope_filter="organization_id IS NULL AND owner_id IS NOT NULL",
    )
    if organization_duplicates or personal_duplicates:
        raise RuntimeError(
            "Cannot add project-name uniqueness: "
            f"{organization_duplicates} organization scope(s) and "
            f"{personal_duplicates} personal scope(s) contain duplicate "
            "non-archived, non-deleted names. Resolve those duplicates "
            "manually, then retry the migration."
        )

    op.add_column(
        "projects",
        sa.Column(
            "_active_organization_id",
            sa.Integer(),
            sa.Computed(
                "CASE WHEN organization_id IS NOT NULL "
                "AND archived_at IS NULL AND deleted_at IS NULL "
                "THEN organization_id ELSE NULL END"
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "_active_personal_owner_id",
            sa.Integer(),
            sa.Computed(
                "CASE WHEN organization_id IS NULL "
                "AND archived_at IS NULL AND deleted_at IS NULL "
                "THEN owner_id ELSE NULL END"
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_projects_active_organization_name",
        "projects",
        ["_active_organization_id", "name"],
    )
    op.create_unique_constraint(
        "uq_projects_active_personal_owner_name",
        "projects",
        ["_active_personal_owner_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_projects_active_personal_owner_name",
        "projects",
        type_="unique",
    )
    op.drop_constraint(
        "uq_projects_active_organization_name",
        "projects",
        type_="unique",
    )
    op.drop_column("projects", "_active_personal_owner_id")
    op.drop_column("projects", "_active_organization_id")
