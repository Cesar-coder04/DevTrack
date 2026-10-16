"""add rejected_at to organization invitations

Revision ID: 9d6f48c2a13b
Revises: 28fec1612208
Create Date: 2026-10-15 14:52:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d6f48c2a13b"
down_revision: Union[str, Sequence[str], None] = "28fec1612208"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_invitations",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_invitations", "rejected_at")
