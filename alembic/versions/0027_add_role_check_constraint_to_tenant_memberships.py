"""add check constraint on tenant_membership role

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-05
"""

from alembic import op

revision: str = "0027"
down_revision: str = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_tenant_membership_role",
        "tenant_memberships",
        "role IN ('owner', 'admin', 'member')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_tenant_membership_role",
        "tenant_memberships",
        type_="check",
    )
