"""Response-shape extension over Ashwin's frozen `app.schemas.scheduling.QueueEntryOut`.

Adds `token` (the printable OPD token, e.g. `D-042`) and `reasons_hi`
(bilingual reasons per the project spec's section 7) additively, in an owned path,
without editing `app/schemas/scheduling.py`. See docs/DECISIONS.md.
"""

from __future__ import annotations

from app.schemas.scheduling import QueueEntryOut as _QueueEntryOutBase


class QueueEntryOut(_QueueEntryOutBase):
    token: str
    reasons_hi: list[str] = []
