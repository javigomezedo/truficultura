"""rename tables and columns to english

Revision ID: 0001
Revises:
Create Date: 2026-03-21
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    legacy_tables = {"parcelas", "gastos", "ingresos"}
    english_tables = {"plots", "expenses", "incomes"}

    # Fresh DB path (e.g. Fly dev/prod bootstrap): create baseline schema directly.
    if not legacy_tables.issubset(table_names):
        if english_tables.issubset(table_names):
            return

        op.create_table(
            "plots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column(
                "polygon", sa.String(length=100), nullable=False, server_default=""
            ),
            sa.Column(
                "cadastral_ref",
                sa.String(length=100),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "hydrant", sa.String(length=100), nullable=False, server_default=""
            ),
            sa.Column(
                "num_holm_oaks", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("planting_date", sa.Date(), nullable=False),
            sa.Column("area_ha", sa.Float(), nullable=True),
            sa.Column("production_start", sa.Date(), nullable=True),
            sa.Column("percentage", sa.Float(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("id"),
        )

        op.create_table(
            "expenses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=False),
            sa.Column(
                "person", sa.String(length=200), nullable=False, server_default=""
            ),
            sa.Column("plot_id", sa.Integer(), nullable=True),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(
                ["plot_id"],
                ["plots.id"],
                name="expenses_plot_id_fkey",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

        op.create_table(
            "incomes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("plot_id", sa.Integer(), nullable=True),
            sa.Column("amount_kg", sa.Float(), nullable=False, server_default="0"),
            sa.Column(
                "category", sa.String(length=200), nullable=False, server_default=""
            ),
            sa.Column("euros_per_kg", sa.Float(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(
                ["plot_id"],
                ["plots.id"],
                name="incomes_plot_id_fkey",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

        return

    # ------------------------------------------------------------------ #
    # 1. Drop FK constraints before renaming referenced tables/columns
    # ------------------------------------------------------------------ #
    op.drop_constraint("gastos_parcela_id_fkey", "gastos", type_="foreignkey")
    op.drop_constraint("ingresos_parcela_id_fkey", "ingresos", type_="foreignkey")

    # ------------------------------------------------------------------ #
    # 2. Rename tables
    # ------------------------------------------------------------------ #
    op.rename_table("parcelas", "plots")
    op.rename_table("gastos", "expenses")
    op.rename_table("ingresos", "incomes")

    # ------------------------------------------------------------------ #
    # 3. Rename columns in plots
    # ------------------------------------------------------------------ #
    op.alter_column("plots", "nombre", new_column_name="name")
    op.alter_column("plots", "poligono", new_column_name="polygon")
    op.alter_column("plots", "parcela", new_column_name="cadastral_ref")
    op.alter_column("plots", "hidrante", new_column_name="hydrant")
    op.alter_column("plots", "n_carrascas", new_column_name="num_holm_oaks")
    op.alter_column("plots", "fecha_plantacion", new_column_name="planting_date")
    op.alter_column("plots", "superficie_ha", new_column_name="area_ha")
    op.alter_column("plots", "inicio_produccion", new_column_name="production_start")
    op.alter_column("plots", "porcentaje", new_column_name="percentage")

    # ------------------------------------------------------------------ #
    # 4. Rename columns in expenses
    # ------------------------------------------------------------------ #
    op.alter_column("expenses", "fecha", new_column_name="date")
    op.alter_column("expenses", "concepto", new_column_name="description")
    op.alter_column("expenses", "persona", new_column_name="person")
    op.alter_column("expenses", "parcela_id", new_column_name="plot_id")
    op.alter_column("expenses", "cantidad", new_column_name="amount")

    # ------------------------------------------------------------------ #
    # 5. Rename columns in incomes
    # ------------------------------------------------------------------ #
    op.alter_column("incomes", "fecha", new_column_name="date")
    op.alter_column("incomes", "parcela_id", new_column_name="plot_id")
    op.alter_column("incomes", "cantidad_kg", new_column_name="amount_kg")
    op.alter_column("incomes", "categoria", new_column_name="category")
    op.alter_column("incomes", "euros_kg", new_column_name="euros_per_kg")

    # ------------------------------------------------------------------ #
    # 6. Recreate FK constraints pointing to new table/column names
    # ------------------------------------------------------------------ #
    op.create_foreign_key(
        "expenses_plot_id_fkey",
        "expenses",
        "plots",
        ["plot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "incomes_plot_id_fkey",
        "incomes",
        "plots",
        ["plot_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Drop new FK constraints
    # ------------------------------------------------------------------ #
    op.drop_constraint("expenses_plot_id_fkey", "expenses", type_="foreignkey")
    op.drop_constraint("incomes_plot_id_fkey", "incomes", type_="foreignkey")

    # ------------------------------------------------------------------ #
    # 2. Reverse column renames in incomes
    # ------------------------------------------------------------------ #
    op.alter_column("incomes", "euros_per_kg", new_column_name="euros_kg")
    op.alter_column("incomes", "category", new_column_name="categoria")
    op.alter_column("incomes", "amount_kg", new_column_name="cantidad_kg")
    op.alter_column("incomes", "plot_id", new_column_name="parcela_id")
    op.alter_column("incomes", "date", new_column_name="fecha")

    # ------------------------------------------------------------------ #
    # 3. Reverse column renames in expenses
    # ------------------------------------------------------------------ #
    op.alter_column("expenses", "amount", new_column_name="cantidad")
    op.alter_column("expenses", "plot_id", new_column_name="parcela_id")
    op.alter_column("expenses", "person", new_column_name="persona")
    op.alter_column("expenses", "description", new_column_name="concepto")
    op.alter_column("expenses", "date", new_column_name="fecha")

    # ------------------------------------------------------------------ #
    # 4. Reverse column renames in plots
    # ------------------------------------------------------------------ #
    op.alter_column("plots", "percentage", new_column_name="porcentaje")
    op.alter_column("plots", "production_start", new_column_name="inicio_produccion")
    op.alter_column("plots", "area_ha", new_column_name="superficie_ha")
    op.alter_column("plots", "planting_date", new_column_name="fecha_plantacion")
    op.alter_column("plots", "num_holm_oaks", new_column_name="n_carrascas")
    op.alter_column("plots", "hydrant", new_column_name="hidrante")
    op.alter_column("plots", "cadastral_ref", new_column_name="parcela")
    op.alter_column("plots", "polygon", new_column_name="poligono")
    op.alter_column("plots", "name", new_column_name="nombre")

    # ------------------------------------------------------------------ #
    # 5. Rename tables back
    # ------------------------------------------------------------------ #
    op.rename_table("plots", "parcelas")
    op.rename_table("expenses", "gastos")
    op.rename_table("incomes", "ingresos")

    # ------------------------------------------------------------------ #
    # 6. Recreate original FK constraints
    # ------------------------------------------------------------------ #
    op.create_foreign_key(
        "gastos_parcela_id_fkey",
        "gastos",
        "parcelas",
        ["parcela_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "ingresos_parcela_id_fkey",
        "ingresos",
        "parcelas",
        ["parcela_id"],
        ["id"],
        ondelete="SET NULL",
    )
