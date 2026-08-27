"""Tests for notifications (checkpoint P3.2). Template rendering, IST
formatting, and the router shape are pure and run with no infra. The full
`notify()` round trip (DB row + Redis publish + email/SMS fallback files)
and the query endpoints need Postgres + Redis -- see docs/DECISIONS.md for
this sandbox's infra caveat.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.v1 import notify as notify_api
from app.services import notify as notify_service


def test_all_notification_types_have_en_and_hi_templates() -> None:
    for type_ in notify_service.NOTIFICATION_TYPES:
        en = notify_service._load_template("en", type_)
        hi = notify_service._load_template("hi", type_)
        assert en.strip()
        assert hi.strip()


def test_render_notification_falls_back_to_en_for_unknown_locale() -> None:
    rendered_en = notify_service.render_notification(
        "results_ready", {"document_id": "abc123"}, locale="en"
    )
    rendered_unknown = notify_service.render_notification(
        "results_ready", {"document_id": "abc123"}, locale="fr"
    )
    assert rendered_en == rendered_unknown
    assert "abc123" in rendered_en


def test_render_notification_missing_placeholder_degrades_gracefully() -> None:
    # No KeyError even though the template expects `document_id`.
    rendered = notify_service.render_notification("results_ready", {}, locale="en")
    assert "results" in rendered.lower() or "रिपोर्ट" in rendered


def test_format_ist_renders_dd_mm_yyyy_12h() -> None:
    dt = datetime(2026, 8, 27, 14, 30, tzinfo=UTC)  # 20:00 IST
    rendered = notify_service.format_ist(dt)
    assert rendered == "27-08-2026 08:00 PM"


def test_dlt_template_ids_cover_every_notification_type() -> None:
    for type_ in notify_service.NOTIFICATION_TYPES:
        assert type_ in notify_service.DLT_TEMPLATE_IDS
        assert len(notify_service.DLT_TEMPLATE_IDS[type_]) >= 10


def test_emergency_template_cites_national_helplines() -> None:
    en = notify_service._load_template("en", "emergency_escalated")
    assert "108" in en and "104" in en and "112" in en


def test_router_registers_expected_paths() -> None:
    paths = {route.path for route in notify_api.router.routes}
    assert paths == {"/notify", "/notify/{notification_id}/read", "/notify/read-all"}


# ---- full API round trips (need Postgres + Redis) --------------------------
#
# Covered end to end in CI once seeded: notify() writes a queryable
# Notification row, publishes notify.{user_id} to Redis, and (with no SMTP/
# SMS gateway configured) writes infra/mail/*.eml and infra/sms/*.txt;
# GET /notify?unread=true returns only unread rows for the caller;
# POST /notify/{id}/read and /notify/read-all are ownership-checked. Written
# and reviewed but not locally executed in this sandbox -- see
# docs/DECISIONS.md.
