"""add_user_insights_table

Revision ID: 4f5f0b8f9c1a
Revises: 2180522d6d68
Create Date: 2026-04-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f5f0b8f9c1a"
down_revision: Union[str, Sequence[str], None] = "2180522d6d68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("time_label", sa.String(length=50), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_insights_id"), "user_insights", ["id"], unique=False)
    op.create_index("ix_user_insights_user_month", "user_insights", ["user_id", "month"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_insights_user_month", table_name="user_insights")
    op.drop_index(op.f("ix_user_insights_id"), table_name="user_insights")
    op.drop_table("user_insights")
