"""add food semantic search

Revision ID: b7e4c1f9a2d3
Revises: 568d31c31491
Create Date: 2026-11-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e4c1f9a2d3"
down_revision: str | Sequence[str] | None = "568d31c31491"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("calorie_chart", sa.Column("search_text", sa.String(length=512), nullable=True))
    # No vector index yet: an exact scan is fast at this table's size. Add HNSW when it grows.
    op.add_column("calorie_chart", sa.Column("embedding", Vector(1024), nullable=True))
    op.create_table(
        "food_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("food_item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["food_item_id"], ["calorie_chart.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias"),
    )
    op.create_index(
        op.f("ix_food_aliases_food_item_id"), "food_aliases", ["food_item_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_food_aliases_food_item_id"), table_name="food_aliases")
    op.drop_table("food_aliases")
    op.drop_column("calorie_chart", "embedding")
    op.drop_column("calorie_chart", "search_text")
    # The vector extension is left installed; other tables may come to use it.
