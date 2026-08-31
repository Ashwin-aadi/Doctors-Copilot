"""scope documents to the visit they were uploaded for

`documents` carried only `patient_id`, so every surface that asked for "this
visit's reports" got the patient's entire document history instead. A visit
showed lab values from episodes it had nothing to do with, the
RESULTS_UPLOADED guard passed on a report uploaded for some other visit, and
the clinical brief reasoned over the lot -- which is also what pushed the
Groq request past its payload limit and made every brief fall back.

The backfill is best effort: a document is attributed to the most recent visit
of the same patient whose signed lab order actually asked for that test.
Anything uploaded loose, with no `test_name`, cannot be attributed to a visit
and is left unscoped rather than guessed at.

Revision ID: e7a4c81d95f2
Revises: d1e5f3b62a09
Create Date: 2026-08-31 16:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7a4c81d95f2"
down_revision: str | None = "d1e5f3b62a09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_visit_id",
        "documents",
        "visits",
        ["visit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_documents_visit_id", "documents", ["visit_id"], unique=False)

    op.execute(
        """
        UPDATE documents d
        SET visit_id = v.id
        FROM visits v
        JOIN lab_orders lo ON lo.id = v.lab_order_id
        WHERE d.visit_id IS NULL
          AND d.test_name IS NOT NULL
          AND v.patient_id = d.patient_id
          AND EXISTS (
              SELECT 1 FROM jsonb_array_elements(lo.items) item
              WHERE item->>'name' = d.test_name
          )
          AND v.created_at = (
              SELECT MAX(v2.created_at)
              FROM visits v2
              JOIN lab_orders lo2 ON lo2.id = v2.lab_order_id
              WHERE v2.patient_id = d.patient_id
                AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(lo2.items) i2
                    WHERE i2->>'name' = d.test_name
                )
          );
        """
    )


def downgrade() -> None:
    op.drop_index("ix_documents_visit_id", table_name="documents")
    op.drop_constraint("fk_documents_visit_id", "documents", type_="foreignkey")
    op.drop_column("documents", "visit_id")
