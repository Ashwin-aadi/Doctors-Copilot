"""add immutability triggers on lab_orders / prescriptions

Revision ID: a3f9c1d84b77
Revises: fecbbce145ed
Create Date: 2026-08-26 15:00:00.000000

Additive only -- no column changed. This is the second of the two
enforcement layers the approval-locking spec requires: the
service layer (app/api/v1/approvals.py) already rejects a re-approval of a
`locked` row with 409, but that only protects writes that go through this
router. A `BEFORE UPDATE` trigger on both tables raises `record_locked` for
*any* UPDATE attempted on a row where `OLD.locked` is true, regardless of
which code path (or a raw SQL session) issued it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a3f9c1d84b77"
down_revision: str | None = "fecbbce145ed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION block_locked_update() RETURNS trigger AS $$
        BEGIN
            IF OLD.locked THEN
                RAISE EXCEPTION 'record_locked';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER lab_order_lock BEFORE UPDATE ON lab_orders
            FOR EACH ROW EXECUTE FUNCTION block_locked_update();
        """
    )
    op.execute(
        """
        CREATE TRIGGER prescription_lock BEFORE UPDATE ON prescriptions
            FOR EACH ROW EXECUTE FUNCTION block_locked_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS prescription_lock ON prescriptions;")
    op.execute("DROP TRIGGER IF EXISTS lab_order_lock ON lab_orders;")
    op.execute("DROP FUNCTION IF EXISTS block_locked_update();")
