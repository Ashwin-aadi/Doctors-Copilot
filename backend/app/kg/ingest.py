"""Sync a patient's Postgres state into the knowledge graph.

`sync_patient` is idempotent (every write is a Cypher MERGE on a natural
key) and safe to call on every visit-state transition -- see
`app/services/visit.py`. It reads Patient.conditions/allergies/medications
(free-text JSONB the patient or a doctor typed in), the patient's LabResults,
and Prescriptions, plus Virat's NER-extracted entities where available.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.clinical import LabResult, Prescription, Visit
from app.db.models.patient import Patient
from app.db.session import SessionLocal
from app.kg.client import run_write
from app.kg.schema import ensure_schema

log = get_logger(__name__)

# TEMP-ADAPTER: remove when Virat ships app/ml/ner.py extracting structured
# conditions/medications from clinical text. Until then we fall back to the
# patient's own free-text conditions/allergies/medications JSONB fields.
try:
    from app.ml.ner import extract_entities  # type: ignore[import-not-found]
except ImportError:

    async def extract_entities(text: str) -> dict:  # noqa: ARG001
        return {"conditions": [], "medications": [], "allergens": []}


async def sync_patient(patient_id: UUID) -> None:
    await ensure_schema()

    async with SessionLocal() as db:
        patient = await db.get(Patient, patient_id)
        if patient is None:
            return

        await run_write(
            "MERGE (p:Patient {id: $id}) SET p.name = $name, p.synced_at = $now",
            id=str(patient_id),
            name=patient.name,
            now=datetime.now(UTC).isoformat(),
        )

        for condition in patient.conditions or []:
            name = condition if isinstance(condition, str) else condition.get("name")
            if not name:
                continue
            since = None if isinstance(condition, str) else condition.get("since")
            await run_write(
                "MERGE (c:Condition {name: $name}) "
                "WITH c MATCH (p:Patient {id: $pid}) "
                "MERGE (p)-[r:DIAGNOSED_WITH]->(c) SET r.since = $since",
                name=name,
                pid=str(patient_id),
                since=since,
            )

        for allergen in patient.allergies or []:
            name = allergen if isinstance(allergen, str) else allergen.get("name")
            if not name:
                continue
            severity = None if isinstance(allergen, str) else allergen.get("severity")
            await run_write(
                "MERGE (a:Allergen {name: $name}) "
                "WITH a MATCH (p:Patient {id: $pid}) "
                "MERGE (p)-[r:ALLERGIC_TO]->(a) SET r.severity = $severity",
                name=name,
                pid=str(patient_id),
                severity=severity,
            )

        for med in patient.medications or []:
            name = med if isinstance(med, str) else med.get("name")
            if not name:
                continue
            rxcui = None if isinstance(med, str) else med.get("rxcui")
            dose = None if isinstance(med, str) else med.get("dose")
            await run_write(
                "MERGE (m:Medication {rxcui: coalesce($rxcui, 'name:' + $name)}) "
                "SET m.name = $name "
                "WITH m MATCH (p:Patient {id: $pid}) "
                "MERGE (p)-[r:PRESCRIBED]->(m) SET r.dose = $dose",
                name=name,
                rxcui=rxcui,
                pid=str(patient_id),
                dose=dose,
            )

        prescriptions = (
            await db.execute(select(Prescription).where(Prescription.patient_id == patient_id))
        ).scalars().all()
        for rx in prescriptions:
            for item in rx.items or []:
                name = item.get("name") if isinstance(item, dict) else None
                if not name:
                    continue
                rxcui = item.get("rxcui") if isinstance(item, dict) else None
                await run_write(
                    "MERGE (m:Medication {rxcui: coalesce($rxcui, 'name:' + $name)}) "
                    "SET m.name = $name "
                    "WITH m MATCH (p:Patient {id: $pid}) "
                    "MERGE (p)-[r:PRESCRIBED]->(m) SET r.start = $start",
                    name=name,
                    rxcui=rxcui,
                    pid=str(patient_id),
                    start=rx.created_at.isoformat() if rx.created_at else None,
                )

        visits = (
            await db.execute(select(Visit).where(Visit.patient_id == patient_id))
        ).scalars().all()
        for visit in visits:
            await run_write(
                "MERGE (e:Encounter {id: $eid}) SET e.state = $state, e.created_at = $created "
                "WITH e MATCH (p:Patient {id: $pid}) MERGE (p)-[:HAD]->(e)",
                eid=str(visit.id),
                state=visit.state,
                created=visit.created_at.isoformat() if visit.created_at else None,
                pid=str(patient_id),
            )
            if visit.doctor_id:
                await run_write(
                    "MERGE (d:Doctor {id: $did}) "
                    "WITH d MATCH (e:Encounter {id: $eid}) MERGE (e)-[:WITH]->(d)",
                    did=str(visit.doctor_id),
                    eid=str(visit.id),
                )

            labs = (
                await db.execute(select(LabResult).where(LabResult.patient_id == patient_id))
            ).scalars().all()
            for lab in labs:
                await run_write(
                    "MERGE (l:LabResult {id: $lid}) "
                    "SET l.test_name = $name, l.value = $value, l.unit = $unit, "
                    "l.flag = $flag, l.observed_at = $observed "
                    "WITH l MATCH (e:Encounter {id: $eid}) MERGE (e)-[:YIELDED]->(l)",
                    lid=str(lab.id),
                    name=lab.normalized_name or lab.test_name,
                    value=lab.value_num if lab.value_num is not None else lab.value_text,
                    unit=lab.unit,
                    flag=lab.flag,
                    observed=lab.observed_at.isoformat() if lab.observed_at else None,
                    eid=str(visit.id),
                )

    log.info("kg_synced", patient_id=str(patient_id))
