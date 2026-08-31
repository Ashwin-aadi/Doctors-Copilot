"""index the columns every hot query filters on

Not one foreign key on the clinical tables was indexed, so every "this patient's
results", "this visit's documents" and "this clinic's queue" lookup was a
sequential scan. That is survivable on demo data and stops being survivable the
moment the audit log or the lab results grow, which they do on every request.

The composite pairs match how the queries actually read: results are always
fetched for a patient in observation order, and the queue is always read for one
clinic filtered by status and ordered by severity, so the sort comes free off
the index instead of a separate pass.

Revision ID: f3b8c07e41da
Revises: e7a4c81d95f2
Create Date: 2026-08-31 19:05:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "f3b8c07e41da"
down_revision: str | None = "e7a4c81d95f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index name, table, columns)
_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_lab_results_patient_observed", "lab_results", ["patient_id", "observed_at"]),
    ("ix_lab_results_document_id", "lab_results", ["document_id"]),
    ("ix_documents_patient_id", "documents", ["patient_id"]),
    ("ix_visits_patient_id", "visits", ["patient_id"]),
    ("ix_visits_doctor_id", "visits", ["doctor_id"]),
    ("ix_lab_orders_visit_id", "lab_orders", ["visit_id"]),
    ("ix_lab_orders_patient_id", "lab_orders", ["patient_id"]),
    ("ix_prescriptions_visit_id", "prescriptions", ["visit_id"]),
    ("ix_prescriptions_patient_id", "prescriptions", ["patient_id"]),
    ("ix_queue_entries_clinic_status_esi", "queue_entries", ["clinic_id", "status", "severity_esi"]),
    ("ix_queue_entries_patient_id", "queue_entries", ["patient_id"]),
    ("ix_appointments_doctor_slot", "appointments", ["doctor_id", "slot_start"]),
    ("ix_appointments_patient_id", "appointments", ["patient_id"]),
    ("ix_availability_doctor_weekday", "availability", ["doctor_id", "weekday"]),
    # The audit log is append-only and read newest-first per actor; it is also
    # the table that grows fastest, so it benefits most.
    ("ix_audit_logs_actor_ts", "audit_logs", ["actor_id", "ts"]),
    ("ix_audit_logs_entity", "audit_logs", ["entity", "entity_id"]),
    ("ix_notifications_user_read", "notifications", ["user_id", "read_at"]),
    ("ix_file_objects_patient_id", "file_objects", ["patient_id"]),
    ("ix_doctors_clinic_id", "doctors", ["clinic_id"]),
    ("ix_patients_user_id", "patients", ["user_id"]),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name, table, columns in _INDEXES:
        # Tables and columns vary a little across the branches this has to apply
        # on top of; a missing one is not worth failing a deploy over.
        found = conn.exec_driver_sql(
            "select count(*) from information_schema.columns "
            "where table_schema = 'public' and table_name = %s and column_name = any(%s)",
            (table, columns),
        ).scalar()
        if found != len(columns):
            continue
        op.execute(
            f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({", ".join(columns)})'
        )


def downgrade() -> None:
    for name, _table, _columns in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
