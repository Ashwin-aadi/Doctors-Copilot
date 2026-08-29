"""Visit.lab_order_id releases its order on delete

`POST /lab-orders/recommend` now points the visit at the draft it just created,
so the doctor's visit screen can link through to the approval page. That made
the existing RESTRICT foreign key bite: deleting a lab order failed while any
visit still referenced it, which blocks both test teardown and the ordinary
case of discarding a superseded draft. The pointer is a convenience, not a
record -- dropping it to NULL is the right thing to happen when the order it
names goes away.

Revision ID: e6b3d0a71c45
Revises: d4a1f6e29c88
"""

from alembic import op

revision: str = "e6b3d0a71c45"
down_revision: str | None = "d4a1f6e29c88"
branch_labels = None
depends_on = None

CONSTRAINT = "visits_lab_order_id_fkey"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "visits", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT, "visits", "lab_orders", ["lab_order_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "visits", type_="foreignkey")
    op.create_foreign_key(CONSTRAINT, "visits", "lab_orders", ["lab_order_id"], ["id"])
