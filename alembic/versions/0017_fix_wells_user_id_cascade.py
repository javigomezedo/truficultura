"""fix_wells_user_id_cascade

La FK wells.user_id → users.id se creó en 0006 sin ON DELETE CASCADE
(se omitió en la migración manual aunque el modelo ya lo tenía).
Esta migración la recrea con el comportamiento correcto.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, Sequence[str], None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("wells_user_id_fkey", "wells", type_="foreignkey")
    op.create_foreign_key(
        "wells_user_id_fkey",
        "wells",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("wells_user_id_fkey", "wells", type_="foreignkey")
    op.create_foreign_key(
        "wells_user_id_fkey",
        "wells",
        "users",
        ["user_id"],
        ["id"],
    )
