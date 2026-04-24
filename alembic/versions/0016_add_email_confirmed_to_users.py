"""add email_confirmed to users

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default="true",  # existing users are already confirmed
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "email_confirmed")
