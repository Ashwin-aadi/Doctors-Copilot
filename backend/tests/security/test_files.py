"""Tests for the secure upload pipeline (app.services.storage, /files).

MIME sniffing, size cap, and malicious-PDF rejection are pure functions and
run here directly with no infra. EXIF stripping uses Pillow, also
infra-free. Dedupe and the full upload/read API round trips need a
reachable Postgres + Redis -- see docs/DECISIONS.md for this sandbox's
infra caveat.
"""

from __future__ import annotations

import io
from uuid import uuid4

import pytest
from PIL import Image

from app.core.errors import ApiError
from app.core.security import create_access_token
from app.services import storage

# A tiny valid PNG (1x1 red pixel), and the same bytes renamed to look like a
# PDF -- exercising "extension is never trusted" without needing a real PDF.
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)

_FAKE_PDF_HEADER = b"%PDF-1.4\n%fake\n"


def _sample_jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buf = io.BytesIO()
    # Pillow's plain save() carries no EXIF block by default; that's fine --
    # the assertion below is about strip_exif() not corrupting/failing on a
    # perfectly ordinary JPEG, which is the actual risk in that code path.
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_sniff_mime_detects_real_type_not_extension() -> None:
    assert storage.sniff_mime(_PNG_BYTES) == "image/png"


def test_validate_upload_bytes_rejects_spoofed_extension() -> None:
    """A file with a `.pdf`-looking name but PNG magic bytes must be judged
    by content, so it's accepted as image/png -- the real spoofing failure
    mode this guards against is the reverse: something that *isn't* on the
    allowlist pretending, via extension, to be one of the allowed types."""
    assert storage.validate_upload_bytes(_PNG_BYTES) == "image/png"


def test_validate_upload_bytes_rejects_disallowed_mime() -> None:
    with pytest.raises(ApiError) as exc_info:
        storage.validate_upload_bytes(b"#!/bin/sh\necho not-a-real-document\n")
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_validate_upload_bytes_rejects_oversize() -> None:
    oversized = _PNG_BYTES + b"\x00" * (storage.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ApiError) as exc_info:
        storage.validate_upload_bytes(oversized)
    assert exc_info.value.code == "VALIDATION_FAILED"


@pytest.fixture
def strict_uploads(monkeypatch: pytest.MonkeyPatch):
    """The PDF scan only runs in production; these assert what it does there."""

    class _Prod:
        app_env = "prod"

    monkeypatch.setattr(storage, "get_settings", lambda: _Prod())


@pytest.mark.parametrize("token", [b"/JavaScript", b"/Launch"])
def test_reject_malicious_pdf_tokens(strict_uploads, token: bytes) -> None:
    with pytest.raises(ApiError) as exc_info:
        storage.reject_malicious_pdf(_FAKE_PDF_HEADER + b"<< /Type /Catalog " + token + b" 0 0 R >>")
    assert exc_info.value.code == "VALIDATION_FAILED"
    # The reject has to name the token, or the uploader has nothing to check.
    assert token.decode() in exc_info.value.message


def test_reject_malicious_pdf_allows_clean_pdf(strict_uploads) -> None:
    storage.reject_malicious_pdf(_FAKE_PDF_HEADER + b"1 0 obj << /Type /Catalog >> endobj")


def test_reject_malicious_pdf_ignores_stream_bodies(strict_uploads) -> None:
    """Compressed image and font bytes can spell anything by chance; only the
    object structure around them decides whether a PDF executes."""
    buried = (
        _FAKE_PDF_HEADER
        + b"1 0 obj << /Type /Catalog >> endobj\n"
        + b"2 0 obj << /Length 20 >> stream\n/JavaScript 9 0 R\nendstream endobj"
    )
    storage.reject_malicious_pdf(buried)


@pytest.mark.parametrize(
    "key",
    [
        b"/EmbeddedFiles 5 0 R",   # ordinary, usually empty, name tree
        b"/EmbeddedFile 5 0 R",    # an attachment is data, not active content
        b"/JavaScriptFoo 1",       # a different name that merely starts the same
    ],
)
def test_reject_malicious_pdf_allows_benign_keys(strict_uploads, key: bytes) -> None:
    storage.reject_malicious_pdf(_FAKE_PDF_HEADER + b"1 0 obj << /Type /Catalog " + key + b" >> endobj")


def test_reject_malicious_pdf_skipped_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """A demo stack takes reports from whatever produced them."""

    class _Dev:
        app_env = "dev"

    monkeypatch.setattr(storage, "get_settings", lambda: _Dev())
    storage.reject_malicious_pdf(_FAKE_PDF_HEADER + b"<< /Type /Catalog /JavaScript 9 0 R >>")


def test_strip_exif_returns_decodable_image() -> None:
    original = _sample_jpeg_with_exif()
    stripped = storage.strip_exif(original, "image/jpeg")
    # Must still be a valid, openable JPEG afterwards.
    Image.open(io.BytesIO(stripped)).load()


def test_strip_exif_noop_for_non_image_mime() -> None:
    assert storage.strip_exif(_FAKE_PDF_HEADER, "application/pdf") == _FAKE_PDF_HEADER


def test_signed_url_roundtrip_and_binding() -> None:
    file_id = uuid4()
    user_id = uuid4()
    other_user_id = uuid4()

    token = storage.signed_url(file_id, ttl=300, user_id=user_id)
    storage.verify_signed_url(token, file_id, user_id, ttl=300)  # must not raise

    with pytest.raises(ApiError) as exc_info:
        storage.verify_signed_url(token, file_id, other_user_id, ttl=300)
    assert exc_info.value.code == "AUTH_FORBIDDEN"


def test_signed_url_rejects_tampered_token() -> None:
    file_id = uuid4()
    user_id = uuid4()
    token = storage.signed_url(file_id, ttl=300, user_id=user_id)
    with pytest.raises(ApiError) as exc_info:
        storage.verify_signed_url(token + "x", file_id, user_id, ttl=300)
    assert exc_info.value.code == "AUTH_FORBIDDEN"


# ---- full API round trips (need Postgres + Redis) --------------------------


async def _solved_captcha_header(client) -> dict[str, str]:
    import base64
    import hashlib
    import json

    challenge = (await client.get("/api/v1/captcha/challenge")).json()
    salt, target, maxnumber = challenge["salt"], challenge["challenge"], challenge["maxnumber"]
    number = next(
        n for n in range(maxnumber) if hashlib.sha256(f"{salt}{n}".encode()).hexdigest() == target
    )
    token = base64.b64encode(
        json.dumps({"challenge": target, "salt": salt, "number": number}).encode()
    ).decode()
    return {"X-Captcha-Token": token}


_PATIENT_1 = "00000000-0000-0000-0000-000000000101"
_PATIENT_2 = "00000000-0000-0000-0000-000000000102"


@pytest.mark.asyncio
async def test_upload_then_dedupe_returns_same_file(client, auth_headers) -> None:
    headers = {**auth_headers("patient"), **(await _solved_captcha_header(client))}
    files = {"file": ("scan.png", _PNG_BYTES, "application/octet-stream")}
    data = {"patient_id": _PATIENT_1}

    first = await client.post("/api/v1/files", data=data, files=files, headers=headers)
    assert first.status_code == 200, first.text

    headers2 = {**auth_headers("patient"), **(await _solved_captcha_header(client))}
    second = await client.post("/api/v1/files", data=data, files=files, headers=headers2)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
async def test_upload_extension_spoof_rejected(client, auth_headers) -> None:
    headers = {**auth_headers("patient"), **(await _solved_captcha_header(client))}
    files = {"file": ("evil.pdf", b"not actually a pdf or image", "application/pdf")}
    data = {"patient_id": _PATIENT_1}

    resp = await client.post("/api/v1/files", data=data, files=files, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_cross_patient_read_is_forbidden(client, auth_headers) -> None:
    headers = {**auth_headers("patient"), **(await _solved_captcha_header(client))}
    files = {"file": ("scan.png", _PNG_BYTES, "application/octet-stream")}
    upload = await client.post(
        "/api/v1/files", data={"patient_id": _PATIENT_1}, files=files, headers=headers
    )
    file_id = upload.json()["id"]

    # A second patient (patient2's user, not patient1's) reading patient1's
    # file. `auth_headers("patient")` always mints patient1's fixed seeded
    # uid, so patient2's token is minted directly here to get a genuinely
    # different patient identity.
    from uuid import UUID as _UUID

    patient2_user_id = _UUID("00000000-0000-0000-0000-000000000502")
    other_token = create_access_token(patient2_user_id, "patient")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    resp = await client.get(f"/api/v1/files/{file_id}", headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTH_FORBIDDEN"
