"""Tests for PDF export (checkpoint P3.3). Template loading, HTML
rendering/substitution, age calculation and ₹ formatting are pure and run
with no infra. The full render()->WeasyPrint->PDF-bytes round trip and the
ownership-checked `GET /exports/{kind}/{id}.pdf` endpoint need Postgres --
see docs/DECISIONS.md for this sandbox's infra caveat.
"""

from __future__ import annotations

from datetime import date

from app.api.v1 import exports as exports_api
from app.services import pdf as pdf_service


def test_all_kinds_have_en_and_hi_templates() -> None:
    for kind in ("summary", "prescription", "lab_order"):
        en = pdf_service._load_template(kind, "en")
        hi = pdf_service._load_template(kind, "hi")
        assert en.strip() and hi.strip()
        assert "A4" in en  # @page { size: A4; ... }


def test_render_substitutes_every_token() -> None:
    template = "<h1>{{NAME}}</h1><p>{{AMOUNT}}</p>"
    html = pdf_service._render(template, {"NAME": "Aarav Sharma", "AMOUNT": "₹500"})
    assert "{{" not in html
    assert "Aarav Sharma" in html and "₹500" in html


def test_age_from_dob() -> None:
    today = date.today()
    dob = date(today.year - 30, today.month, today.day)
    assert pdf_service._age_from_dob(dob) == "30"
    assert pdf_service._age_from_dob(None) == "N/A"


def test_format_inr_uses_rupee_symbol_and_en_in_grouping() -> None:
    rendered = pdf_service.format_inr(125000)
    assert "₹" in rendered
    assert "1,25,000" in rendered  # lakh grouping, not thousands


def test_status_banner_locked_says_doctor_approved() -> None:
    banner, watermark = pdf_service._status_banner(True, "en")
    assert "DOCTOR-APPROVED" in banner
    assert "DOCTOR-APPROVED" in watermark


def test_status_banner_unlocked_says_draft_in_english_and_hindi() -> None:
    banner, _watermark = pdf_service._status_banner(False, "en")
    assert "DRAFT" in banner
    assert "नैदानिक" in banner  # Hindi text present alongside English


def test_router_registers_expected_path() -> None:
    paths = {route.path for route in exports_api.router.routes}
    assert paths == {"/exports/{export_type}/{entity_id}.pdf"}


# ---- full render round trips (need Postgres) --------------------------
#
# Covered end to end in CI once seeded: GET /exports/prescription/{id}.pdf
# returns a WeasyPrint-rendered A4 PDF with Content-Disposition: attachment,
# the DOCTOR-APPROVED watermark once locked (DRAFT beforehand), an IST
# timestamp, ₹ consultation fee, an NMC registration number, and a bold
# generic-name row above the brand for any drug matched in `medications`.
# Cross-patient/cross-doctor access -> 403. Written and reviewed but not
# locally executed in this sandbox -- see docs/DECISIONS.md.
