"""add doctor consultation languages and clinic scheme empanelment

`doctors.registration_council` and `clinics.facility_type` already shipped in
d4a1f6e29c88; this revision only adds the two columns the scheduling optimiser
still reads out of a hard-coded override table.

Revision ID: c9d2b7a34f18
Revises: a3d7c1b58e94
Create Date: 2026-08-31 10:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9d2b7a34f18"
down_revision: str | None = "a3d7c1b58e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "doctors",
        sa.Column(
            "languages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "clinics",
        sa.Column(
            "schemes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("clinics", "schemes")
    op.drop_column("doctors", "languages")
