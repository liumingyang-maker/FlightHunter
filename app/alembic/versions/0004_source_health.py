"""Alembic 0004: 来源健康字段 — 区分尝试/成功/有价值情报。"""

revision = "0004_source_health"
down_revision = "0003_trip_confirmed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("sources")}
    if "last_attempt_at" not in cols:
        op.add_column("sources", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    if "last_success_at" not in cols:
        op.add_column("sources", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))
    if "last_valuable_at" not in cols:
        op.add_column("sources", sa.Column("last_valuable_at", sa.DateTime(timezone=True), nullable=True))
    if "last_signal_count" not in cols:
        op.add_column("sources", sa.Column("last_signal_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    if "last_result" not in cols:
        op.add_column("sources", sa.Column("last_result", sa.String(40), nullable=True))


def downgrade() -> None:
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("sources")}
    for name in ("last_result", "last_signal_count", "last_valuable_at", "last_success_at", "last_attempt_at"):
        if name in cols:
            op.drop_column("sources", name)
