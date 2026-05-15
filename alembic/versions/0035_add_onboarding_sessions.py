"""add onboarding_sessions table

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column(
            "state_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_onboarding_sessions_id", "onboarding_sessions", ["id"], unique=False
    )
    op.create_index(
        "ix_onboarding_sessions_tenant_id",
        "onboarding_sessions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_onboarding_sessions_created_by_user_id",
        "onboarding_sessions",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_onboarding_tenant_status",
        "onboarding_sessions",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_onboarding_tenant_status", table_name="onboarding_sessions")
    op.drop_index(
        "ix_onboarding_sessions_created_by_user_id", table_name="onboarding_sessions"
    )
    op.drop_index("ix_onboarding_sessions_tenant_id", table_name="onboarding_sessions")
    op.drop_index("ix_onboarding_sessions_id", table_name="onboarding_sessions")
    op.drop_table("onboarding_sessions")
