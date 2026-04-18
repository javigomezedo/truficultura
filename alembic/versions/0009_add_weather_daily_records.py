"""add weather daily records

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weather_daily_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("station_code", sa.String(length=20), nullable=True),
        sa.Column("province_code", sa.String(length=10), nullable=True),
        sa.Column("municipality_code", sa.String(length=10), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=False),
        sa.Column("is_forecast", sa.Boolean(), nullable=False),
        sa.Column("quality_status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "date",
            "station_code",
            "province_code",
            "municipality_code",
            "is_forecast",
            name="uq_weather_daily_scope",
        ),
    )
    op.create_index(
        "ix_weather_daily_records_id", "weather_daily_records", ["id"], unique=False
    )
    op.create_index(
        "ix_weather_daily_records_date",
        "weather_daily_records",
        ["date"],
        unique=False,
    )
    op.create_index(
        "ix_weather_daily_records_station_code",
        "weather_daily_records",
        ["station_code"],
        unique=False,
    )
    op.create_index(
        "ix_weather_daily_records_province_code",
        "weather_daily_records",
        ["province_code"],
        unique=False,
    )
    op.create_index(
        "ix_weather_daily_records_municipality_code",
        "weather_daily_records",
        ["municipality_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weather_daily_records_municipality_code", table_name="weather_daily_records"
    )
    op.drop_index(
        "ix_weather_daily_records_province_code", table_name="weather_daily_records"
    )
    op.drop_index(
        "ix_weather_daily_records_station_code", table_name="weather_daily_records"
    )
    op.drop_index("ix_weather_daily_records_date", table_name="weather_daily_records")
    op.drop_index("ix_weather_daily_records_id", table_name="weather_daily_records")
    op.drop_table("weather_daily_records")
