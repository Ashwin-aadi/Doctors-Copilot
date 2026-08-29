"""Tie an uploaded report to the ordered test it answers.

The patient uploads against a specific line of the doctor's lab order --
"this is my dengue NS1" -- so the visit screen can show which tests are still
outstanding instead of an undifferentiated pile of files. Nullable: reports
uploaded outside an order (an old report the patient brings along) stay valid.

Revision ID: a3d7c1b58e94
Revises: f2c8a4e11d63
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a3d7c1b58e94"
down_revision: str | None = "f2c8a4e11d63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("test_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "test_name")
