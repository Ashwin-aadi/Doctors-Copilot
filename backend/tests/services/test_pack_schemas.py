"""Rule-pack schema validation (section 8 N2.5): loading each YAML pack
validates it against a pydantic schema, so a malformed pack fails CI rather
than surfacing as a runtime `KeyError` in production. Also asserts the
section 7 bilingual-reasons contract: every `reason_en`/`label_en` in
`triage_india.yaml` has a `reason_hi`/`label_hi`, both <= 60 characters.
Pure YAML + pydantic -- no DB, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ConfigDict

_PACKS_DIR = Path("backend/app/services/rules/packs")


class TierEntry(BaseModel):
    colour: str
    label_en: str
    label_hi: str
    target_minutes: int


class PriorityGroup(BaseModel):
    id: str
    bonus: int
    reason_en: str
    reason_hi: str


class TriageIndiaPack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tiers: dict[int, TierEntry]
    priority_groups: list[PriorityGroup]
    priority_group_max_bonus: int


class OptimizerPack(BaseModel):
    model_config = ConfigDict(extra="allow")
    weights: dict[str, float]
    related_specialties: dict[str, list[str]]
    min_facility_type: dict[str, str]
    free_facility_types: list[str]
    max_distance_km: float
    max_distance_km_rural: float
    horizon_days: int


class QueuePack(BaseModel):
    model_config = ConfigDict(extra="allow")
    holidays: list[str]
    aging_minutes: int
    aging_max_bonus: int
    avg_consult_minutes: int
    emergency_severity_max: int
    grace_minutes: int
    token_prefix_by_facility: dict[str, str]
    opd_sessions_ist: list[dict]


class LabRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    when: dict = {}
    specialty: list[str] = []
    labs: list[dict]
    cghs_code: str | None = None
    pmjay_package: str | None = None
    fallback: bool = False


class RedFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phrase: str
    category: str
    min_facility_type: str


class EmergencyPack(BaseModel):
    model_config = ConfigDict(extra="allow")
    red_flags: list[RedFlag]
    facility_rank: dict[str, int]


def _load(name: str) -> dict:
    return yaml.safe_load((_PACKS_DIR / name).read_text(encoding="utf-8"))


def test_triage_india_pack_schema_valid():
    TriageIndiaPack.model_validate(_load("triage_india.yaml"))


def test_optimizer_pack_schema_valid():
    OptimizerPack.model_validate(_load("optimizer.yaml"))


def test_queue_pack_schema_valid():
    QueuePack.model_validate(_load("queue.yaml"))


def test_lab_panels_pack_schema_valid():
    rules = _load("lab_panels.yaml")
    for rule in rules:
        LabRule.model_validate(rule)


def test_emergency_pack_schema_valid():
    EmergencyPack.model_validate(_load("emergency.yaml"))


def test_every_lab_rule_has_a_named_reason_per_lab():
    rules = _load("lab_panels.yaml")
    for rule in rules:
        for lab in rule["labs"]:
            assert lab.get("name")
            assert lab.get("reason")


@pytest.mark.parametrize("rule_id_marker", ["triage_india"])
def test_triage_india_bilingual_reasons_under_60_chars(rule_id_marker):
    pack = _load("triage_india.yaml")
    for tier in pack["tiers"].values():
        assert tier["label_en"] and tier["label_hi"]
        assert len(tier["label_en"]) <= 60
        assert len(tier["label_hi"]) <= 60
    for group in pack["priority_groups"]:
        assert group["reason_en"] and group["reason_hi"]
        assert len(group["reason_en"]) <= 60
        assert len(group["reason_hi"]) <= 60
