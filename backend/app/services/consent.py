"""DPDP Act, 2023 -- style consent artefact storage, modelled on the ABDM
consent artefact shape so it can be mapped to a real ABDM consent request
later.

Reads/writes the `consents` table through a local SQLAlchemy Core `Table`
object rather than Ashwin's `Consent` ORM class in `app/db/models/patient.py`
(which only maps the original `version`/`accepted_at`/`ip` columns) -- the
extra DPDP fields were added additively via migration `fecbbce145ed` without
touching that file. See docs/DECISIONS.md.

Consent is never hard-deleted: withdrawal sets `withdrawn_at` on the most
recent artefact, so both the grant and the withdrawal stay auditable, per
the DPDP Act's requirement that both events be provable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession

_metadata = MetaData()

consents_table = Table(
    "consents",
    _metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("patient_id", UUID(as_uuid=True), ForeignKey("patients.id")),
    Column("version", String(32)),
    Column("accepted_at", DateTime(timezone=True)),
    Column("ip", String(64)),
    Column("purpose", JSONB),
    Column("data_categories", JSONB),
    Column("language", String(8)),
    Column("expiry", DateTime(timezone=True)),
    Column("granular_scopes", JSONB),
    Column("withdrawn_at", DateTime(timezone=True)),
)

DEFAULT_SCOPES = ("triage", "copilot", "share_with_doctor", "research")

# Versioned consent notice text, English and Hindi (DPDP Act mandates the
# purpose/data-categories notice be understandable to the data principal).
CONSENT_NOTICES: dict[str, dict[str, str]] = {
    "1.0": {
        "en": (
            "We collect your personal and health data (name, contact details, "
            "symptoms, lab reports, prescriptions) to provide triage, connect "
            "you with a doctor, and maintain your treatment record, as allowed "
            "under the Digital Personal Data Protection Act, 2023. You may "
            "withdraw consent at any time; some records may still be retained "
            "where clinical-record law requires it. You choose which uses "
            "below you allow."
        ),
        "hi": (
            "हम आपकी व्यक्तिगत और स्वास्थ्य जानकारी (नाम, संपर्क विवरण, लक्षण, "
            "लैब रिपोर्ट, नुस्खे) का उपयोग ट्राइएज देने, आपको डॉक्टर से जोड़ने और "
            "आपका उपचार रिकॉर्ड बनाए रखने के लिए करते हैं, जैसा कि डिजिटल व्यक्तिगत "
            "डेटा संरक्षण अधिनियम, 2023 के तहत अनुमति है। आप किसी भी समय सहमति वापस "
            "ले सकते हैं; कुछ रिकॉर्ड चिकित्सा-रिकॉर्ड कानून की आवश्यकता होने पर "
            "बनाए रखे जा सकते हैं। नीचे आप चुन सकते हैं कि किन उपयोगों की अनुमति देनी है।"
        ),
    }
}


def _row_to_dict(row: Any) -> dict:
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "version": row.version,
        "accepted_at": row.accepted_at,
        "ip": row.ip,
        "purpose": row.purpose or [],
        "data_categories": row.data_categories or [],
        "language": row.language,
        "expiry": row.expiry,
        "granular_scopes": row.granular_scopes or {},
        "withdrawn_at": row.withdrawn_at,
    }


async def get_latest_consent(db: AsyncSession, patient_id: uuid.UUID) -> dict | None:
    result = await db.execute(
        select(consents_table)
        .where(consents_table.c.patient_id == patient_id)
        .order_by(consents_table.c.accepted_at.desc())
        .limit(1)
    )
    row = result.first()
    return _row_to_dict(row) if row is not None else None


async def get_active_consent(db: AsyncSession, patient_id: uuid.UUID) -> dict | None:
    """The latest consent, unless it has been withdrawn or has expired."""
    consent = await get_latest_consent(db, patient_id)
    if consent is None or consent["withdrawn_at"] is not None:
        return None
    expiry = consent.get("expiry")
    if expiry is not None and expiry <= datetime.now(UTC):
        return None
    return consent


async def record_consent(
    db: AsyncSession,
    patient_id: uuid.UUID,
    *,
    version: str,
    purpose: list[str],
    data_categories: list[str],
    language: str,
    expiry: datetime | None,
    granular_scopes: dict[str, bool],
    ip: str | None,
) -> dict:
    consent_id = uuid.uuid4()
    accepted_at = datetime.now(UTC)
    await db.execute(
        consents_table.insert().values(
            id=consent_id,
            patient_id=patient_id,
            version=version,
            accepted_at=accepted_at,
            ip=ip,
            purpose=purpose,
            data_categories=data_categories,
            language=language,
            expiry=expiry,
            granular_scopes=granular_scopes,
            withdrawn_at=None,
        )
    )
    await db.commit()
    consent = await get_latest_consent(db, patient_id)
    assert consent is not None
    return consent


async def withdraw_consent(db: AsyncSession, patient_id: uuid.UUID) -> dict | None:
    consent = await get_latest_consent(db, patient_id)
    if consent is None or consent["withdrawn_at"] is not None:
        return consent
    await db.execute(
        consents_table.update()
        .where(consents_table.c.id == consent["id"])
        .values(withdrawn_at=datetime.now(UTC))
    )
    await db.commit()
    return await get_latest_consent(db, patient_id)
