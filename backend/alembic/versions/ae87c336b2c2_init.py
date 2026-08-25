"""init

Revision ID: ae87c336b2c2
Revises:
Create Date: 2026-08-25 16:30:16.263431

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'ae87c336b2c2'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('clinics',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('is_emergency_capable', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('users',
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    op.create_table('medications',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('rxcui', sa.String(length=32), nullable=True),
        sa.Column('ingredient', sa.String(length=255), nullable=True),
        sa.Column('form', sa.String(length=64), nullable=True),
        sa.Column('strength', sa.String(length=64), nullable=True),
        sa.Column('is_generic', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_medications_rxcui'), 'medications', ['rxcui'], unique=False)

    op.create_table('patients',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('dob', sa.Date(), nullable=True),
        sa.Column('sex', sa.String(length=16), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('allergies', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('medications', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('doctors',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('specialties', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('qualifications', sa.String(length=500), nullable=True),
        sa.Column('fee', sa.Float(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=False),
        sa.Column('clinic_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('triage_sessions',
        sa.Column('patient_id', sa.UUID(), nullable=True),
        sa.Column('transcript', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # lab_orders.visit_id and visits.lab_order_id are mutually dependent;
    # lab_orders is created without that FK, added below once visits exists.
    op.create_table('lab_orders',
        sa.Column('visit_id', sa.UUID(), nullable=False),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('locked', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('visits',
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=True),
        sa.Column('state', sa.String(length=32), nullable=False),
        sa.Column('triage_session_id', sa.UUID(), nullable=True),
        sa.Column('lab_order_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
        sa.ForeignKeyConstraint(['lab_order_id'], ['lab_orders.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['triage_session_id'], ['triage_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_foreign_key(
        'fk_lab_orders_visit_id_visits', 'lab_orders', 'visits', ['visit_id'], ['id'],
    )

    op.create_table('audit_logs',
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('role', sa.String(length=32), nullable=True),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('entity', sa.String(length=128), nullable=False),
        sa.Column('entity_id', sa.String(length=64), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('diff_hash', sa.String(length=64), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('notifications',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('appointments',
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('clinic_id', sa.UUID(), nullable=False),
        sa.Column('slot_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('slot_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('availabilities',
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('clinic_id', sa.UUID(), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('slot_minutes', sa.Integer(), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('consents',
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.String(length=32), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('file_objects',
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('path', sa.String(length=1000), nullable=False),
        sa.Column('mime', sa.String(length=128), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('uploaded_by', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_file_objects_sha256'), 'file_objects', ['sha256'], unique=False)

    op.create_table('prescriptions',
        sa.Column('visit_id', sa.UUID(), nullable=False),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('locked', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['visit_id'], ['visits.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('documents',
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('file_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('engine', sa.String(length=64), nullable=True),
        sa.Column('mean_confidence', sa.Float(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('error', sa.String(length=1000), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['file_objects.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('queue_entries',
        sa.Column('appointment_id', sa.UUID(), nullable=True),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('clinic_id', sa.UUID(), nullable=False),
        sa.Column('severity_esi', sa.Integer(), nullable=False),
        sa.Column('emergency', sa.Boolean(), nullable=False),
        sa.Column('enqueued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('lab_results',
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('test_name', sa.String(length=255), nullable=False),
        sa.Column('normalized_name', sa.String(length=255), nullable=False),
        sa.Column('value_num', sa.Float(), nullable=True),
        sa.Column('value_text', sa.String(length=255), nullable=True),
        sa.Column('unit', sa.String(length=64), nullable=True),
        sa.Column('ref_low', sa.Float(), nullable=True),
        sa.Column('ref_high', sa.Float(), nullable=True),
        sa.Column('flag', sa.String(length=16), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('lab_results')
    op.drop_table('queue_entries')
    op.drop_table('documents')
    op.drop_table('prescriptions')
    op.drop_index(op.f('ix_file_objects_sha256'), table_name='file_objects')
    op.drop_table('file_objects')
    op.drop_table('consents')
    op.drop_table('availabilities')
    op.drop_table('appointments')
    op.drop_table('notifications')
    op.drop_table('audit_logs')
    op.drop_constraint('fk_lab_orders_visit_id_visits', 'lab_orders', type_='foreignkey')
    op.drop_table('visits')
    op.drop_table('lab_orders')
    op.drop_table('triage_sessions')
    op.drop_table('doctors')
    op.drop_table('patients')
    op.drop_index(op.f('ix_medications_rxcui'), table_name='medications')
    op.drop_table('medications')
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('clinics')
