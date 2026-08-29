"""Visit.triage_session_id releases its session on delete

Booking now links the visit to the triage session that produced it, so the
existing RESTRICT foreign key blocks deleting a session any visit still
references. As with `lab_order_id`, the pointer is a convenience: when the
session it names goes away, the right outcome is a visit with no triage
session, not a refused delete.

Revision ID: f2c8a4e11d63
Revises: e6b3d0a71c45
"""

from alembic import op

revision: str = "f2c8a4e11d63"
down_revision: str | None = "e6b3d0a71c45"
branch_labels = None
depends_on = None

CONSTRAINT = "visits_triage_session_id_fkey"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "visits", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT, "visits", "triage_sessions", ["triage_session_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "visits", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT, "visits", "triage_sessions", ["triage_session_id"], ["id"]
    )
