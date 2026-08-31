"""link an amended lab order to the signed order it supersedes

A signed lab order is immutable -- `lab_order_lock` raises `record_locked` on
any UPDATE, and the content hash is what the doctor's signature covers. When a
doctor steps a visit back to the lab-order stage the order has to become
editable again, so the reopened order is a new draft carrying the previous
order's items, not a mutation of the signed one. `supersedes_id` is the chain
that keeps the original findable from its replacement.

Revision ID: d1e5f3b62a09
Revises: c9d2b7a34f18
Create Date: 2026-08-31 16:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d1e5f3b62a09"
down_revision: str | None = "c9d2b7a34f18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lab_orders",
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_lab_orders_supersedes_id",
        "lab_orders",
        "lab_orders",
        ["supersedes_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_lab_orders_supersedes_id", "lab_orders", ["supersedes_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_lab_orders_supersedes_id", table_name="lab_orders")
    op.drop_constraint("fk_lab_orders_supersedes_id", "lab_orders", type_="foreignkey")
    op.drop_column("lab_orders", "supersedes_id")
