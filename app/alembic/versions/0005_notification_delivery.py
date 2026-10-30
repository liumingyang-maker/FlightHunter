"""Alembic 0005: 通知送达持久状态 — 跨进程幂等与失败重试。"""

revision = "0005_notification_delivery"
down_revision = "0004_source_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    insp = inspect(bind)
    if "notification_deliveries" in insp.get_table_names():
        return
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("notification_id", sa.String(36), nullable=True),
        sa.UniqueConstraint("event_key", "channel", name="uq_notification_delivery_event_channel"),
    )
    op.create_index("ix_notification_deliveries_event_key", "notification_deliveries", ["event_key"])


def downgrade() -> None:
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    if "notification_deliveries" in inspect(bind).get_table_names():
        op.drop_table("notification_deliveries")
