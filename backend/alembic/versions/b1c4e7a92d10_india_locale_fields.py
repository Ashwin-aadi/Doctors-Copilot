"""add India locale fields: ABHA id, state/PIN, NMC registration

Revision ID: b1c4e7a92d10
Revises: ae87c336b2c2
Create Date: 2026-08-25 18:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b1c4e7a92d10'
down_revision: str | None = 'ae87c336b2c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('patients', sa.Column('state', sa.String(length=64), nullable=True))
    op.add_column('patients', sa.Column('pin_code', sa.String(length=6), nullable=True))
    op.add_column('patients', sa.Column('abha_id', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_patients_abha_id'), 'patients', ['abha_id'], unique=False)

    op.add_column('clinics', sa.Column('state', sa.String(length=64), nullable=True))
    op.add_column('clinics', sa.Column('pin_code', sa.String(length=6), nullable=True))

    op.add_column('doctors', sa.Column('nmc_reg_no', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('doctors', 'nmc_reg_no')

    op.drop_column('clinics', 'pin_code')
    op.drop_column('clinics', 'state')

    op.drop_index(op.f('ix_patients_abha_id'), table_name='patients')
    op.drop_column('patients', 'abha_id')
    op.drop_column('patients', 'pin_code')
    op.drop_column('patients', 'state')
