"""Graph schema: node uniqueness constraints. Idempotent -- safe to call on
every startup or before every ingest run.

    (:Patient)-[:HAD]->(:Encounter)-[:YIELDED]->(:LabResult)
    (:Patient)-[:DIAGNOSED_WITH {since}]->(:Condition)
    (:Patient)-[:PRESCRIBED {start,end,dose}]->(:Medication)
    (:Patient)-[:ALLERGIC_TO {severity}]->(:Allergen)
    (:Encounter)-[:AT]->(:Clinic)
    (:Encounter)-[:WITH]->(:Doctor)
"""

from app.kg.client import run_write

CONSTRAINTS = [
    "CREATE CONSTRAINT patient_id IF NOT EXISTS FOR (p:Patient) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT drug_rxcui IF NOT EXISTS FOR (m:Medication) REQUIRE m.rxcui IS UNIQUE",
    "CREATE CONSTRAINT encounter_id IF NOT EXISTS FOR (e:Encounter) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT lab_id IF NOT EXISTS FOR (l:LabResult) REQUIRE l.id IS UNIQUE",
    "CREATE CONSTRAINT condition_name IF NOT EXISTS FOR (c:Condition) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT allergen_name IF NOT EXISTS FOR (a:Allergen) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT clinic_id IF NOT EXISTS FOR (c:Clinic) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT doctor_id IF NOT EXISTS FOR (d:Doctor) REQUIRE d.id IS UNIQUE",
]


async def ensure_schema() -> None:
    for stmt in CONSTRAINTS:
        await run_write(stmt)
