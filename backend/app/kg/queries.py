"""Read-side KG queries. Both are graph-down-safe: `run_query` returns `[]`
on any Neo4j error, so both functions degrade to an empty-but-valid shape
rather than raising -- callers (triage, copilot brief) never see a 500 just
because the graph is unreachable.
"""

from uuid import UUID

from app.core.cache import cached_json
from app.kg.client import run_query

# The visit screen asks for the same context from several panels at once, and
# the brief asks again while building. Short enough that a sync during the visit
# is picked up on the next panel, long enough to collapse one screen's worth of
# duplicate graph round trips into a single query.
_CONTEXT_TTL_SECONDS = 60

_CONTEXT_QUERY = """
MATCH (p:Patient {id: $pid})
OPTIONAL MATCH (p)-[dc:DIAGNOSED_WITH]->(cond:Condition)
OPTIONAL MATCH (p)-[pr:PRESCRIBED]->(med:Medication)
OPTIONAL MATCH (p)-[al:ALLERGIC_TO]->(alg:Allergen)
OPTIONAL MATCH (p)-[:HAD]->(enc:Encounter)-[:YIELDED]->(lab:LabResult)
WITH p,
     collect(DISTINCT {name: cond.name, since: dc.since}) AS conditions,
     collect(DISTINCT {name: med.name, rxcui: med.rxcui, dose: pr.dose}) AS medications,
     collect(DISTINCT {name: alg.name, severity: al.severity}) AS allergies,
     collect(DISTINCT {test_name: lab.test_name, value: lab.value, unit: lab.unit,
                        flag: lab.flag, observed_at: lab.observed_at}) AS labs
RETURN conditions, medications, allergies, labs
"""

_TIMELINE_QUERY = """
MATCH (p:Patient {id: $pid})-[:HAD]->(e:Encounter)
OPTIONAL MATCH (e)-[:WITH]->(d:Doctor)
OPTIONAL MATCH (e)-[:YIELDED]->(l:LabResult)
RETURN e.id AS encounter_id, e.state AS state, e.created_at AS created_at,
       d.id AS doctor_id, collect(DISTINCT l.test_name) AS labs
ORDER BY e.created_at DESC
"""


def _drop_empty(items: list[dict], key: str = "name") -> list[dict]:
    return [item for item in items if item.get(key)]


def patient_context_key(patient_id: UUID) -> str:
    return f"cache:kg:patient_context:{patient_id}"


async def patient_context(patient_id: UUID) -> dict:
    return await cached_json(
        patient_context_key(patient_id),
        ttl_seconds=_CONTEXT_TTL_SECONDS,
        produce=lambda: _patient_context_uncached(patient_id),
        dump=lambda value: value,
        load=lambda value: value,
    )


async def _patient_context_uncached(patient_id: UUID) -> dict:
    rows = await run_query(_CONTEXT_QUERY, pid=str(patient_id))
    if not rows:
        return {"conditions": [], "medications": [], "allergies": [], "recent_labs": []}
    row = rows[0]
    labs = sorted(
        (lab for lab in row.get("labs", []) if lab.get("test_name")),
        key=lambda lab: lab.get("observed_at") or "",
        reverse=True,
    )[:10]
    return {
        "conditions": _drop_empty(row.get("conditions", [])),
        "medications": _drop_empty(row.get("medications", [])),
        "allergies": _drop_empty(row.get("allergies", [])),
        "recent_labs": labs,
    }


async def patient_timeline(patient_id: UUID) -> list[dict]:
    rows = await run_query(_TIMELINE_QUERY, pid=str(patient_id))
    return [
        {
            "encounter_id": row.get("encounter_id"),
            "state": row.get("state"),
            "created_at": row.get("created_at"),
            "doctor_id": row.get("doctor_id"),
            "labs": [lab for lab in row.get("labs", []) if lab],
        }
        for row in rows
    ]
