"""Alembic 0006: 持久增量采集——ETag/缓存/分页/文章键。"""

revision = "0006_incremental_crawl"
down_revision = "0005_notification_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    insp = inspect(bind)

    # Source 表增量字段
    cols = {c["name"] for c in insp.get_columns("sources")}
    for col, typ in [
        ("etag", sa.Text()),
        ("last_modified", sa.Text()),
        ("content_hash", sa.Text()),
        ("next_due_at", sa.Text()),
        ("consecutive_failures", sa.Integer()),
    ]:
        if col not in cols:
            op.add_column("sources", sa.Column(col, typ, nullable=True))

    # 文章缓存表
    if "article_cache" not in insp.get_table_names():
        op.create_table(
            "article_cache",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source_id", sa.String(36), nullable=True),
            sa.Column("url_hash", sa.Text(), nullable=True),
            sa.Column("guid", sa.Text(), nullable=True),
            sa.Column("content_hash", sa.Text(), nullable=True),
            sa.Column("parse_version", sa.Text(), nullable=True),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("published_at", sa.Text(), nullable=True),
            sa.Column("first_seen_at", sa.Text(), nullable=True),
            sa.Column("last_checked_at", sa.Text(), nullable=True),
            sa.Column("last_changed_at", sa.Text(), nullable=True),
            sa.Column("etag", sa.Text(), nullable=True),
            sa.Column("last_modified", sa.Text(), nullable=True),
        )

    # OCR 缓存表
    if "ocr_cache" not in insp.get_table_names():
        op.create_table(
            "ocr_cache",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("image_hash", sa.Text(), nullable=True),
            sa.Column("ocr_lang", sa.Text(), nullable=True),
            sa.Column("model_version", sa.Text(), nullable=True),
            sa.Column("ocr_text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    insp = inspect(bind)

    for col in ["etag", "last_modified", "content_hash", "next_due_at", "consecutive_failures"]:
        if col in {c["name"] for c in insp.get_columns("sources")}:
            op.drop_column("sources", col)

    if "article_cache" in insp.get_table_names():
        op.drop_table("article_cache")
    if "ocr_cache" in insp.get_table_names():
        op.drop_table("ocr_cache")
