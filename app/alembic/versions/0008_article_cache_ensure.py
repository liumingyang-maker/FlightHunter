"""Alembic 0008: article_cache 表（已在 0006/0007 创建，此处确保幂等）。"""

revision = "0008_article_cache_ensure"
down_revision = "0007_article_cache_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 已在 0006/0007 创建，此处空操作确保幂等
    pass


def downgrade() -> None:
    pass
