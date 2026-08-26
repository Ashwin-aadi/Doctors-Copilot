"""add DPDP-style consent artefact fields to consents

Revision ID: fecbbce145ed
Revises: b1c4e7a92d10
Create Date: 2026-08-26 13:10:00.000000

Additive only -- no column on `consents` is dropped or narrowed. The extra
columns (`purpose`, `data_categories`, `language`, `expiry`,
`granular_scopes`, `withdrawn_at`) model the ABDM-style consent artefact
required by the P1.4 spec. `app/db/models/patient.py`'s `Consent` ORM class (Ashwin's,
not touched here) still maps only its original three columns; the API layer
(`app/api/v1/patients.py`) reads/writes the full row through a local
SQLAlchemy Core `Table` object instead. Noted to Ashwin in docs/DECISIONS.md.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'fecbbce145ed'
down_revision: str | None = 'b1c4e7a92d10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('consents', sa.Column('purpose', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('consents', sa.Column('data_categories', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('consents', sa.Column('language', sa.String(length=8), nullable=True))
    op.add_column('consents', sa.Column('expiry', sa.DateTime(timezone=True), nullable=True))
    op.add_column('consents', sa.Column('granular_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('consents', sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_consents_patient_id'), 'consents', ['patient_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_consents_patient_id'), table_name='consents')
    op.drop_column('consents', 'withdrawn_at')
    op.drop_column('consents', 'granular_scopes')
    op.drop_column('consents', 'expiry')
    op.drop_column('consents', 'language')
    op.drop_column('consents', 'data_categories')
    op.drop_column('consents', 'purpose')
