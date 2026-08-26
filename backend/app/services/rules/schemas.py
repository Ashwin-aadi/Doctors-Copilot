"""Response-shape extension over Ashwin's frozen `app.schemas.triage.SuggestedLab`.

The frozen schema carries `name`, `loinc`, `reason`, `source` -- no coverage
fields. Section 4.2 asks `recommend_labs` to surface `cghs_code`/
`pmjay_package` "where present, so the UI can show whether the test is
covered." Rather than edit `app/schemas/triage.py` (banned), this module
subclasses it additively within an owned path, following the same pattern as
`app/services/scheduling/schemas.py::DoctorRankedOut`.
"""

from __future__ import annotations

from app.schemas.triage import SuggestedLab


class SuggestedLabOut(SuggestedLab):
    cghs_code: str | None = None
    pmjay_package: str | None = None
