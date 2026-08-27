"""CP3: notification locale pref, doctor/clinic profile fields, availability
blackout calendar

Revision ID: d4a1f6e29c88
Revises: c7e2a9f01b3d
Create Date: 2026-08-27 09:00:00.000000

Additive only -- no existing column dropped or narrowed. `app/db/models/`
(Ashwin's) is not touched: `users.preferred_language`, `doctors.
registration_council`, `doctors.registration_year` and `clinics.
facility_type` are all read/written through local SQLAlchemy Core `Table`
objects (`app/services/notify.py`, `app/api/v1/doctors_profile.py`) -- same
pattern already established for `consents` in `fecbbce145ed`. The new
`availability_blackouts` table (national holidays + doctor/clinic leave) has
no ORM model at all for the same reason; it's read/written the same way.
Noted to Ashwin in docs/DECISIONS.md for folding into the real ORM models
when convenient.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4a1f6e29c88"
down_revision: str | None = "c7e2a9f01b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferred_language", sa.String(length=8), nullable=False, server_default="en"),
    )
    op.add_column("doctors", sa.Column("registration_council", sa.String(length=64), nullable=True))
    op.add_column("doctors", sa.Column("registration_year", sa.Integer(), nullable=True))
    op.add_column(
        "clinics",
        sa.Column("facility_type", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "availability_blackouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clinic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinics.id"),
            nullable=True,
        ),
        sa.Column(
            "doctor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctors.id"),
            nullable=True,
        ),
        sa.Column("blackout_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_availability_blackouts_date", "availability_blackouts", ["blackout_date"]
    )

    # Seed the fixed 2026 national holidays the P3.4 spec names (Republic Day,
    # Independence Day, Gandhi Jayanti). doctor_id/clinic_id NULL == applies
    # to every doctor/clinic (a national holiday, not a personal leave day).
    op.execute(
        """
        INSERT INTO availability_blackouts (id, clinic_id, doctor_id, blackout_date, reason, state, created_at)
        VALUES
            (gen_random_uuid(), NULL, NULL, '2026-01-26', 'Republic Day', NULL, now()),
            (gen_random_uuid(), NULL, NULL, '2026-08-15', 'Independence Day', NULL, now()),
            (gen_random_uuid(), NULL, NULL, '2026-10-02', 'Gandhi Jayanti', NULL, now())
        """
    )


def downgrade() -> None:
    op.drop_index("ix_availability_blackouts_date", table_name="availability_blackouts")
    op.drop_table("availability_blackouts")
    op.drop_column("clinics", "facility_type")
    op.drop_column("doctors", "registration_year")
    op.drop_column("doctors", "registration_council")
    op.drop_column("users", "preferred_language")
