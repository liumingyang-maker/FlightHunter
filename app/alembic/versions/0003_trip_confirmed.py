"""Alembic 0003: trips.confirmed — P3 确认行程后才正式扫描。"""

revision = "0003_trip_confirmed"
down_revision = "0002_official_url_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa

    from alembic import op

    op.add_column(
        "trips",
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    from alembic import op

    op.drop_column("trips", "confirmed")
