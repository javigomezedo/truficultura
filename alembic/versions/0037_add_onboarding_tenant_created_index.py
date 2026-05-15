"""Add composite index on onboarding_sessions(tenant_id, created_at).

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-15 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_onboarding_sessions_tenant_id_created_at",
        "onboarding_sessions",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_onboarding_sessions_tenant_id_created_at",
        table_name="onboarding_sessions",
    )
