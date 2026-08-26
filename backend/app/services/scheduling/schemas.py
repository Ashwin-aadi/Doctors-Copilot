"""Response-shape extension over Ashwin's frozen `app.schemas.scheduling`.

`DoctorRanked` (app/schemas/ -- not an owned path) doesn't carry
`reasons_hi`, but the project spec (section 7) mandates a bilingual reasons list on
every ranked-doctor result. Rather than edit `app/schemas/scheduling.py`
(banned), this module subclasses it additively within an owned path.
`DoctorRankedOut` is a strict superset of `DoctorRanked` so it still satisfies
the frozen `rank_doctors(...) -> list[DoctorRanked]` contract. See
docs/DECISIONS.md for the DRIFT note asking Ashwin to fold `reasons_hi` into
the canonical schema.
"""

from __future__ import annotations

from app.schemas.scheduling import DoctorRanked


class DoctorRankedOut(DoctorRanked):
    reasons_hi: list[str] = []
