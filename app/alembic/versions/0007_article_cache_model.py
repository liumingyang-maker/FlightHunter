"""Alembic 0007: 文章缓存表模型。"""

revision = "0007_article_cache_model"
down_revision = "0006_incremental_crawl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect

    from alembic import op

    bind = op.get_bind()
    insp = inspect(bind)
    if "article_cache" not in insp.get_table_names():
        import sqlalchemy as sa

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
    if "ocr_cache" not in insp.get_table_names():
        import sqlalchemy as sa

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
    if "article_cache" in insp.get_table_names():
        op.drop_table("article_cache")
    if "ocr_cache" in insp.get_table_names():
        op.drop_table("ocr_cache")
