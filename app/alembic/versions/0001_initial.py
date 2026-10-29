"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-29

"""

from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 使用 metadata.create_all 生成与 ORM 一致的初始结构，
    # 避免手写 20+ 表与模型漂移；后续增量用独立 revision。
    from app.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.models import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
