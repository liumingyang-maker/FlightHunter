"""Alembic 0009: 修复 0006/0007 缺失的 TimestampMixin 字段。

GPT-6 审核发现：从 0005 升级时 article_cache/ocr_cache 缺少
created_at_utc/updated_at_utc，ORM 查询报错。
"""

revision = "0009_fix_cache_timestamps"
down_revision = "0008_article_cache_ensure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    insp = inspect(bind)

    for table in ("article_cache", "ocr_cache"):
        if table not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        # TimestampMixin 字段
        if "created_at_utc" not in cols:
            op.add_column(table, sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=True))
        if "updated_at_utc" not in cols:
            op.add_column(table, sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=True))
        # UUIDPk 字段
        if "id" not in cols:
            op.add_column(table, sa.Column("id", sa.String(36), primary_key=True))


def downgrade() -> None:
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    insp = inspect(bind)

    for table in ("article_cache", "ocr_cache"):
        if table not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        for col in ("created_at_utc", "updated_at_utc"):
            if col in cols:
                op.drop_column(table, col)
