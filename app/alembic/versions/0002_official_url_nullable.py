"""Alembic 增量：campaign_rounds.official_url 允许 NULL（聚合线索）。"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_official_url_nullable"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("campaign_rounds") as batch_op:
        batch_op.alter_column(
            "official_url",
            existing_type=sa.String(length=2000),
            nullable=True,
        )


def downgrade() -> None:
    op.execute("UPDATE campaign_rounds SET official_url = COALESCE(official_url, '')")
    with op.batch_alter_table("campaign_rounds") as batch_op:
        batch_op.alter_column(
            "official_url",
            existing_type=sa.String(length=2000),
            nullable=False,
        )
