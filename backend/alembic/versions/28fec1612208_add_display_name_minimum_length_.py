"""add display name minimum length constraint

Revision ID: 28fec1612208
Revises: bfe1b4a2edc5
Create Date: 2026-10-14 14:39:32.554141

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28fec1612208'
down_revision: Union[str, Sequence[str], None] = 'bfe1b4a2edc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_display_name_min_length",
        "users",
        "CHAR_LENGTH(display_name) >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_display_name_min_length",
        "users",
        type_="check",
    )
