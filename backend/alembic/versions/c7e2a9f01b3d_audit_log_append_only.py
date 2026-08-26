"""revoke UPDATE/DELETE on audit_logs (append-only)

Revision ID: c7e2a9f01b3d
Revises: a3f9c1d84b77
Create Date: 2026-08-26 16:00:00.000000

CLAUDE.md P2.4: "revoke UPDATE, DELETE on audit_log from the app role".
Table is actually named `audit_logs` (plural, per
app/db/models/audit.py's `__tablename__`) -- the spec's singular
`audit_log` was a naming slip, not a second table.

KNOWN LIMITATION (documented rather than silently shipped, per this
checkpoint's own instructions): `settings.database_url`/`postgres_user`
(currently `copilot`) is the *same* role that runs migrations, i.e. the
role that owns this table. PostgreSQL table owners always retain full
DML privileges regardless of REVOKE -- only re-assigning ownership
(`ALTER TABLE ... OWNER TO`) to a different, unprivileged role, or
`ALTER TABLE ... FORCE ROW LEVEL SECURITY` with matching policies, would
actually stop the app's own connection from writing UPDATE/DELETE. This
REVOKE is still applied for defense-in-depth (it will bite if a
lower-privileged application role is introduced later, e.g. splitting
migration-runner vs. app-runtime credentials), but as configured today it
does **not** make audit_logs actually tamper-proof against the app's own
DB credential -- flagged as a CP4 hardening item in docs/SECURITY.md.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7e2a9f01b3d"
down_revision: str | None = "a3f9c1d84b77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = "copilot"


def upgrade() -> None:
    op.execute(f'REVOKE UPDATE, DELETE ON audit_logs FROM "{_APP_ROLE}";')


def downgrade() -> None:
    op.execute(f'GRANT UPDATE, DELETE ON audit_logs TO "{_APP_ROLE}";')
