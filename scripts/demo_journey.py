"""End-to-end demo pathway: one patient, triage to generic substitution.

Drives the real HTTP API in the order the demo is presented, so every beat
of docs/DEMO_SCRIPT.md has a runnable equivalent. Nothing here is mocked --
the LLM, retrieval, OCR, scheduling and approval paths are the production
ones. Two steps reach into Postgres directly and say so when they do:

  * assigning the booked doctor to the demo visit (no endpoint owns this)
  * creating the draft Prescription row (POST /prescriptions is not in the
    contract; only POST /approvals/prescription/{id} exists)

Usage
-----
    python scripts/demo_journey.py                 # full journey
    python scripts/demo_journey.py --keep-going    # do not stop at first failure
    python scripts/demo_journey.py --from 7        # resume at beat 7
    python scripts/demo_journey.py --json out.json # machine-readable transcript

Prerequisites: `make up`, `make migrate`, `make seed`, `make api`, and for
the OCR beat either `make worker` or nothing at all (the script falls back
to running the worker function in-process).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

BASE = os.environ.get("DEMO_API_BASE", os.environ.get("VITE_API_BASE", "http://localhost:8000"))
API = f"{BASE}/api/v1"

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000101")
PATIENT_USER_ID = UUID("00000000-0000-0000-0000-000000000501")
VISIT_ID = UUID("00000000-0000-0000-0000-000000000301")

# seed.py and seed_users.py both write these user rows; whichever ran last
# wins the email column, so try each domain in turn.
PATIENT_EMAILS = ["patient1@doctorcopilot.dev", "patient1@demo.example"]
DOCTOR_EMAIL_DOMAINS = ["doctorcopilot.dev", "demo.example"]
PASSWORDS = ["demo-password-123", "Demo@12345"]

# The leptospirosis-style presentation the triage pipeline was hardened
# against: discriminating features (calf myalgia, stagnant water, dark urine)
# plus explicit denials that must never resurface as red flags.
TRIAGE_TURNS = [
    "I have had high fever for the last five days with severe headache.",
    "My calf muscles hurt a lot, it is hard to walk. I also feel nauseous and "
    "have vomited twice.",
    "There is a mild reddish rash on my chest. I waded through stagnant flood "
    "water near my house about a week ago.",
    "My urine has been noticeably dark for two days and I have mild abdominal "
    "discomfort.",
    "No, I have no shortness of breath and no chest pain or difficulty "
    "breathing. No blood in vomit, urine or stool. No chronic illness, no "
    "regular medicines.",
]

BRAND_TO_LOOK_UP = "Dolo 650"

# Used once the scripted history is exhausted but triage is still asking.
FILLER_ANSWER = "No, nothing else. I have no other symptoms."


class Beat:
    """One numbered step of the demo, with the state it hands to the next."""

    def __init__(self, number: int, title: str) -> None:
        self.number = number
        self.title = title
        self.status = "pending"
        self.detail: dict[str, Any] = {}
        self.error: str | None = None


class Journey:
    def __init__(self, *, keep_going: bool, start_at: int) -> None:
        self.keep_going = keep_going
        self.start_at = start_at
        self.beats: list[Beat] = []
        self.client = httpx.Client(timeout=120.0)
        self.state: dict[str, Any] = {}

    # ---------------------------------------------------------------- infra

    def beat(self, number: int, title: str):
        def decorator(fn):
            def runner() -> bool:
                b = Beat(number, title)
                self.beats.append(b)
                if number < self.start_at:
                    b.status = "skipped"
                    print(f"  {number:>2}. {title} ... SKIPPED (--from {self.start_at})")
                    return True
                print(f"  {number:>2}. {title}")
                started = time.time()
                try:
                    fn(b)
                    b.status = "ok"
                    b.detail["elapsed_s"] = round(time.time() - started, 2)
                    return True
                except Exception as exc:  # noqa: BLE001 - demo runner reports, never raises
                    b.status = "failed"
                    b.error = f"{type(exc).__name__}: {exc}"
                    print(f"      FAILED  {b.error}")
                    return False

            self._register(runner)
            return fn

        return decorator

    def _register(self, runner) -> None:
        self._runners = getattr(self, "_runners", [])
        self._runners.append(runner)

    def run(self) -> int:
        print(f"\nDoctor's Copilot -- end-to-end demo journey against {BASE}\n")
        for runner in getattr(self, "_runners", []):
            ok = runner()
            if not ok and not self.keep_going:
                break
        return self.report()

    def report(self) -> int:
        print("\n  " + "-" * 62)
        failed = [b for b in self.beats if b.status == "failed"]
        pending = [b for b in self.beats if b.status == "pending"]
        passed = [b for b in self.beats if b.status == "ok"]
        print(
            f"  {len(passed)} passed, {len(failed)} failed, "
            f"{len(pending)} not reached\n"
        )
        for b in failed:
            print(f"  FAILED  {b.number:>2}. {b.title}\n          {b.error}")
        return 1 if failed else 0

    # ------------------------------------------------------------- helpers

    def say(self, line: str) -> None:
        print(f"      {line}")

    def _check(self, response: httpx.Response, expect: int | tuple[int, ...] = 200) -> Any:
        codes = (expect,) if isinstance(expect, int) else expect
        if response.status_code not in codes:
            raise RuntimeError(
                f"{response.request.method} {response.request.url.path} -> "
                f"{response.status_code} (wanted {codes}): {response.text[:400]}"
            )
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.content

    def get(self, path: str, *, token: str | None = None, expect=200, **kw) -> Any:
        return self._check(
            self.client.get(f"{API}{path}", headers=self._auth(token), **kw), expect
        )

    def post(self, path: str, *, token: str | None = None, captcha=False, expect=200, **kw) -> Any:
        headers = self._auth(token)
        if captcha:
            headers["X-Captcha-Token"] = self.solve_captcha()
        return self._check(self.client.post(f"{API}{path}", headers=headers, **kw), expect)

    def _auth(self, token: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"} if token else {}

    def solve_captcha(self) -> str:
        """Brute-force the proof-of-work challenge exactly as the browser does."""
        challenge = self._check(self.client.get(f"{API}/captcha/challenge"))
        salt = challenge["salt"]
        target = challenge["challenge"]
        for n in range(challenge["maxnumber"] + 1):
            if hashlib.sha256(f"{salt}{n}".encode()).hexdigest() == target:
                payload = {"challenge": target, "salt": salt, "number": n}
                return base64.b64encode(json.dumps(payload).encode()).decode()
        raise RuntimeError("captcha unsolvable within maxnumber")

    def login_as(self, user_id: UUID) -> tuple[str, dict]:
        """Sign in as a seeded user with exactly one POST /auth/login.

        seed.py and seed_users.py disagree on both the email domain and the
        password, and whichever ran last wins. Guessing over HTTP burns the
        login rate limit and trips the 5-failure account lockout, so the row
        is read from Postgres and the password checked against the stored
        hash locally -- the network sees one attempt with known-good input.
        """

        from app.core.security import verify_password
        from app.db.models.user import User
        from app.db.session import SessionLocal

        async def resolve() -> tuple[str, str]:
            async with SessionLocal() as s:
                user = await s.get(User, user_id)
                if user is None:
                    raise RuntimeError(f"user {user_id} not seeded -- run `make seed`")
                for candidate in PASSWORDS:
                    if verify_password(candidate, user.password_hash):
                        return user.email, candidate
                raise RuntimeError(
                    f"{user.email}: no known demo password matches the stored hash"
                )

        email, password = asyncio.run(resolve())
        self.clear_lockout(email)

        r = self.client.post(
            f"{API}/auth/login",
            json={"email": email, "password": password},
            headers={"X-Captcha-Token": self.solve_captcha()},
        )
        body = self._check(r)
        token = body.get("access_token") or body.get("access") or body["token"]
        self.state.setdefault("emails", {})[str(user_id)] = email
        return token, body

    def clear_lockout(self, email: str) -> None:
        """Drop any progressive-lockout / failure counters left by earlier runs."""
        try:
            from redis import Redis

            from app.core.config import get_settings

            r = Redis.from_url(get_settings().redis_url)
            for key in r.scan_iter(match="auth:login:*"):
                if email.encode() in key or email in key.decode(errors="ignore"):
                    r.delete(key)
        except Exception:  # noqa: BLE001 - best effort, never blocks the demo
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--from", dest="start_at", type=int, default=1)
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    args = parser.parse_args()

    j = Journey(keep_going=args.keep_going, start_at=args.start_at)

    # ============================================================ 1. health
    @j.beat(1, "Stack is up (postgres, redis, neo4j, chroma, llm)")
    def _(b: Beat) -> None:
        health = j._check(j.client.get(f"{BASE}/health"))
        down = [k for k, v in health.items() if v == "down"]
        j.say(f"health: {health}")
        if down:
            raise RuntimeError(f"dependencies down: {down}")
        b.detail["health"] = health

    # ======================================================== 2. patient in
    @j.beat(2, "Patient signs in (Aarav Sharma)")
    def _(b: Beat) -> None:
        token, body = j.login_as(PATIENT_USER_ID)
        j.state["patient_token"] = token
        me = j.get("/auth/me", token=token)
        j.say(f"logged in as {me.get('email')} ({me.get('role')})")
        b.detail["me"] = me

    # =========================================================== 3. triage
    @j.beat(3, "Pre-assessment triage conversation")
    def _(b: Beat) -> None:
        start = j.post("/triage/session", json={}, params={"patient_id": str(PATIENT_ID)})
        session_id = start["session_id"]
        j.state["triage_session_id"] = session_id
        j.say(f"session {session_id}")
        j.say(f"copilot asks: {start['assistant'][:100]}")
        # The scripted history first, then honest "nothing further" answers
        # until triage itself closes the session -- GET /result 404s while
        # the conversation is still open, and no endpoint force-finalizes it.
        turn = None
        scripted = list(TRIAGE_TURNS)
        for i in range(1, 13):
            line = scripted.pop(0) if scripted else FILLER_ANSWER
            turn = j.post(
                f"/triage/{session_id}/message",
                json={"session_id": session_id, "content": line},
            )
            j.say(f"patient turn {i}: {line[:64]}...")
            j.say(f"  -> {turn['assistant'][:96]}")
            if turn["done"]:
                j.say(f"  -> triage closed the conversation after {i} turns")
                break
        if turn is None or not turn["done"]:
            raise RuntimeError(
                "triage never set done=True; GET /result cannot be reached "
                "(no force-finalize endpoint exists in the contract)"
            )
        b.detail["session_id"] = session_id
        b.detail["turns"] = i

    @j.beat(4, "Triage result: state, red flags, ESI, colour, citations")
    def _(b: Beat) -> None:
        result = j.get(f"/triage/{j.state['triage_session_id']}/result")
        j.state["triage"] = result
        j.state["specialty"] = result.get("specialty") or "general_medicine"
        j.state["severity_esi"] = result["severity_esi"]

        j.say(f"ESI {result['severity_esi']} / {result['triage_colour'].upper()}")
        j.say(f"specialty: {result['specialty']}   confidence: {result['confidence']}")
        j.say(f"red flags: {result['red_flags'] or 'none'}")
        for d in (result.get("differentials") or [])[:5]:
            name = d.get("condition") or d.get("name")
            j.say(f"  differential: {name}  ({d.get('likelihood', '?')})")
        j.say(f"suggested labs: {[lab['name'] for lab in result['suggested_labs']]}")
        j.say(f"citations: {len(result['citations'])}")

        # The grounding guarantees the pipeline was hardened for -- assert
        # them here so the demo fails loudly rather than quietly regressing.
        denied = {"difficulty breathing", "shortness of breath", "chest pain"}
        leaked = [f for f in result["red_flags"] if any(d in f.lower() for d in denied)]
        if leaked:
            raise RuntimeError(f"denied symptom resurfaced as a red flag: {leaked}")
        if result["severity_esi"] <= 2 and not result["red_flags"]:
            raise RuntimeError("ESI 1-2 asserted with no supporting red flag")
        b.detail["triage"] = {
            k: result[k] for k in ("severity_esi", "triage_colour", "red_flags", "specialty")
        }

    # ========================================================== 5. booking
    @j.beat(5, "Book the optimal doctor from the triage session")
    def _(b: Beat) -> None:
        ranked = j.post(
            "/appointments/simulate",
            token=j.state["patient_token"],
            json={"specialty": j.state["specialty"], "lat": 28.61, "lng": 77.20},
        )
        for d in ranked[:3]:
            j.say(
                f"candidate: {d['name']} ({d['specialty']}) fee Rs.{d['fee']:.0f} "
                f"queue {d['queue_load']} score {d['score']:.2f}"
            )

        booking = j.post(
            "/appointments",
            token=j.state["patient_token"],
            captcha=True,
            expect=201,
            json={
                "patient_id": str(PATIENT_ID),
                "specialty": j.state["specialty"],
                "lat": 28.61,
                "lng": 77.20,
                "triage_session_id": j.state["triage_session_id"],
                "preferred_from": datetime.now(UTC).isoformat(),
            },
        )
        appt = booking["appointment"]
        doctor = booking["doctor"]
        queue = booking["queue"]
        j.state["appointment"] = appt
        j.state["doctor_id"] = UUID(doctor["doctor_id"])
        j.state["clinic_id"] = UUID(doctor["clinic_id"])
        j.state["queue_entry_id"] = queue["id"]

        j.say(f"booked {doctor['name']} at {appt['slot_start']}")
        j.say(
            f"queue position {queue['position']}, ESI {queue['severity_esi']} "
            f"({queue['triage_colour']}), est. wait {queue['estimated_wait_minutes']} min"
        )
        if queue["severity_esi"] != j.state["severity_esi"]:
            raise RuntimeError(
                "triage severity did not carry into the queue entry "
                f"({j.state['severity_esi']} -> {queue['severity_esi']})"
            )
        b.detail["appointment"] = appt

    # =================================== 6. bind the visit to this journey
    @j.beat(6, "Attach triage + booked doctor to the demo visit [direct DB]")
    def _(b: Beat) -> None:
        from app.db.models.clinical import Visit
        from app.db.session import SessionLocal

        async def bind() -> str:
            async with SessionLocal() as s:
                visit = await s.get(Visit, VISIT_ID)
                if visit is None:
                    raise RuntimeError("visit 301 missing -- run `make seed` first")
                visit.triage_session_id = UUID(j.state["triage_session_id"])
                visit.doctor_id = j.state["doctor_id"]
                visit.state = "TRIAGED"
                visit.updated_at = datetime.now(UTC)
                await s.commit()
                return visit.state

        state = asyncio.run(bind())
        j.say("no endpoint assigns a doctor to a visit -- writing it directly")
        j.say(f"visit {VISIT_ID} reset to {state} for doctor {j.state['doctor_id']}")
        b.detail["visit_state"] = state

    # ======================================================= 7. doctor in
    @j.beat(7, "Doctor signs in (the doctor the optimizer picked)")
    def _(b: Beat) -> None:
        from app.db.models.scheduling import Doctor
        from app.db.session import SessionLocal

        async def resolve() -> UUID:
            async with SessionLocal() as s:
                doctor = await s.get(Doctor, j.state["doctor_id"])
                return doctor.user_id

        doctor_user_id = asyncio.run(resolve())
        token, _ = j.login_as(doctor_user_id)
        j.state["doctor_token"] = token
        me = j.get("/auth/me", token=token)
        j.say(f"logged in as {me.get('email')} ({me.get('role')})")
        b.detail["doctor_email"] = me.get("email")

    # ====================================================== 8. lab orders
    @j.beat(8, "Recommend the lab panel (rules + RAG merge)")
    def _(b: Beat) -> None:
        order = j.post(
            "/lab-orders/recommend",
            token=j.state["doctor_token"],
            json={"visit_id": str(VISIT_ID)},
        )
        j.state["lab_order_id"] = order["id"]
        for item in order["items"]:
            j.say(f"lab: {item['name']}  [{item.get('source', '?')}] {item.get('reason', '')[:60]}")
        if not order["items"]:
            raise RuntimeError("lab recommendation returned an empty panel")
        b.detail["items"] = [i["name"] for i in order["items"]]

    @j.beat(9, "Doctor signs the lab order (captcha + lock)")
    def _(b: Beat) -> None:
        approved = j.post(
            f"/approvals/lab-order/{j.state['lab_order_id']}",
            token=j.state["doctor_token"],
            captcha=True,
        )
        j.say(f"locked={approved.get('locked')} hash={str(approved.get('content_hash'))[:16]}...")

        from app.db.models.clinical import Visit
        from app.db.session import SessionLocal

        async def link() -> None:
            async with SessionLocal() as s:
                visit = await s.get(Visit, VISIT_ID)
                visit.lab_order_id = UUID(j.state["lab_order_id"])
                await s.commit()

        asyncio.run(link())
        visit = j.post(
            f"/visits/{VISIT_ID}/advance",
            token=j.state["doctor_token"],
            json={"target": "LABS_SUGGESTED"},
        )
        visit = j.post(
            f"/visits/{VISIT_ID}/advance",
            token=j.state["doctor_token"],
            json={"target": "LABS_APPROVED"},
        )
        j.say(f"visit state -> {visit['state']}")
        b.detail["state"] = visit["state"]

    # ============================================================= 10. OCR
    @j.beat(10, "Patient uploads the lab report -- OCR and parse")
    def _(b: Beat) -> None:
        fixture = ROOT / "ml" / "fixtures" / "cbc.pdf"
        if not fixture.exists():
            raise RuntimeError(f"fixture missing: {fixture}")

        with fixture.open("rb") as fh:
            doc = j._check(
                j.client.post(
                    f"{API}/documents/upload",
                    headers={
                        "Authorization": f"Bearer {j.state['patient_token']}",
                        "X-Captcha-Token": j.solve_captcha(),
                    },
                    files={"file": (fixture.name, fh, "application/pdf")},
                    data={"patient_id": str(PATIENT_ID)},
                )
            )
        document_id = doc["id"]
        j.state["document_id"] = document_id
        j.say(f"document {document_id} queued from {fixture.name}")

        deadline = time.time() + 45
        status = doc["status"]
        while time.time() < deadline and status in ("queued", "processing"):
            time.sleep(2)
            status = j.get(f"/documents/{document_id}", token=j.state["patient_token"])["status"]

        if status in ("queued", "processing"):
            j.say("no rq worker responding -- running the worker in-process")
            from app.workers.ocr_worker import process_document

            # STORAGE_ROOT is a relative path, so the worker only resolves
            # uploaded files from backend/ -- the cwd `make worker` uses.
            cwd = Path.cwd()
            try:
                import os as _os

                _os.chdir(ROOT / "backend")
                process_document(str(document_id))
            finally:
                import os as _os

                _os.chdir(cwd)

        final = j.get(f"/documents/{document_id}", token=j.state["patient_token"])
        if final["status"] != "done":
            raise RuntimeError(f"OCR ended in {final['status']}: {final.get('error')}")

        j.say(f"engine={final['engine']} confidence={final['mean_confidence']}")
        for lab in final["labs"][:8]:
            j.say(
                f"  {lab['normalized_name']}: {lab['value']} {lab.get('unit') or ''} "
                f"[{lab['flag']}]"
            )
        if not final["labs"]:
            raise RuntimeError("OCR produced no structured lab results")
        j.state["labs"] = final["labs"]
        b.detail["labs"] = len(final["labs"])

    @j.beat(11, "Results land on the visit")
    def _(b: Beat) -> None:
        visit = j.post(
            f"/visits/{VISIT_ID}/advance",
            token=j.state["doctor_token"],
            json={"target": "RESULTS_UPLOADED"},
        )
        j.say(f"visit state -> {visit['state']}")
        b.detail["state"] = visit["state"]

    # ================================================ 12. knowledge graph
    @j.beat(12, "Knowledge graph: patient context and timeline")
    def _(b: Beat) -> None:
        from app.kg.ingest import sync_patient

        asyncio.run(sync_patient(PATIENT_ID))
        context = j.get(f"/kg/patient/{PATIENT_ID}/context", token=j.state["doctor_token"])
        timeline = j.get(f"/kg/patient/{PATIENT_ID}/timeline", token=j.state["doctor_token"])
        j.say(f"conditions: {context.get('conditions')}")
        j.say(f"medications: {context.get('medications')}")
        j.say(f"allergies: {context.get('allergies')}")
        j.say(f"recent labs: {len(context.get('recent_labs') or [])}, timeline events: {len(timeline)}")
        j.state["kg_conditions"] = [
            c.get("name") for c in (context.get("conditions") or []) if c.get("name")
        ]
        j.state["kg_allergies"] = [
            a.get("name") for a in (context.get("allergies") or []) if a.get("name")
        ]
        b.detail["context_keys"] = sorted(context)

    # ==================================================== 13. clinical RAG
    @j.beat(13, "Clinical copilot brief (cited, grounded)")
    def _(b: Beat) -> None:
        started = time.time()
        brief = j.post(
            "/copilot/brief",
            token=j.state["doctor_token"],
            json={"visit_id": str(VISIT_ID)},
        )
        j.state["brief"] = brief
        j.say(f"built in {time.time() - started:.1f}s, confidence {brief['confidence']}")
        j.say(f"summary: {brief['summary'][:200]}")
        for d in brief["differentials"][:5]:
            j.say(f"  differential: {d}")
        for c in brief["cautions"][:4]:
            j.say(f"  caution: {c}")
        for cite in brief["citations"][:5]:
            j.say(f"  [{cite['n']}] {cite['title']} -- {cite['source']}")
        if len(brief["citations"]) < 1:
            raise RuntimeError("brief carries no citations")
        b.detail["citations"] = len(brief["citations"])

    @j.beat(14, "Visit reaches BRIEF_READY -> CONSULTED")
    def _(b: Beat) -> None:
        j.post(
            f"/visits/{VISIT_ID}/advance",
            token=j.state["doctor_token"],
            json={"target": "BRIEF_READY"},
        )
        visit = j.post(
            f"/visits/{VISIT_ID}/advance",
            token=j.state["doctor_token"],
            json={"target": "CONSULTED"},
        )
        j.say(f"visit state -> {visit['state']}")
        b.detail["state"] = visit["state"]

    # ========================================================= 15. safety
    @j.beat(15, "Medication suggestion and safety screen")
    def _(b: Beat) -> None:
        # Prefer the brief's differentials; fall back to the conditions the
        # knowledge graph actually holds for this patient. openFDA indications
        # do not index every tropical diagnosis, so a differential like
        # "leptospirosis" legitimately returns no labelled candidate.
        conditions = (
            (j.state.get("brief", {}).get("differentials") or [])
            + j.state.get("kg_conditions", [])
        )[:2] or ["type 2 diabetes mellitus"]
        j.say(f"screening for: {conditions}")
        candidates = j.post(
            "/ml/medications/suggest",
            token=j.state["doctor_token"],
            json={
                "conditions": conditions,
                "current_medications": [],
                "allergies": j.state.get("kg_allergies") or ["penicillin"],
            },
        )
        for c in candidates[:5]:
            j.say(
                f"candidate: {c['name']} ({c['ingredient']}) "
                f"NLEM={c['nlem_listed']} JanAushadhi={c['jan_aushadhi_available']} "
                f"MRP={c.get('mrp_inr')}"
            )
            if c["safety_flags"]:
                j.say(f"    flags: {c['safety_flags']}")
        if not candidates:
            raise RuntimeError("no medication candidates returned")
        j.state["chosen_med"] = candidates[0]

        report = j.post(
            "/ml/interactions",
            token=j.state["doctor_token"],
            json={
                "medications": [candidates[0]["name"], "doxycycline"],
                "allergies": ["penicillin"],
                "conditions": conditions,
            },
        )
        j.say(
            f"interactions: {len(report['pairs'])} pairs, "
            f"{len(report['allergy_conflicts'])} allergy conflicts, "
            f"{len(report['contraindications'])} contraindications"
        )
        for p in report["pairs"][:3]:
            j.say(f"  {p['drug_a']} + {p['drug_b']}: {p['severity']} -- {p['mechanism'][:60]}")
        b.detail["candidates"] = [c["name"] for c in candidates[:5]]

    # ======================================================== 16. generics
    @j.beat(16, "Brand to generic: NLEM, Jan Aushadhi, rupee price")
    def _(b: Beat) -> None:
        mapping = j.get(
            "/medications/generic",
            token=j.state["doctor_token"],
            params={"brand": BRAND_TO_LOOK_UP},
        )
        j.say(f"{BRAND_TO_LOOK_UP} -> {mapping.get('ingredient') or mapping.get('generic_name')}")
        for g in (mapping.get("generics") or [])[:4]:
            j.say(
                f"  {g.get('name')}  MRP Rs.{g.get('mrp_inr')} -> Rs.{g.get('price_inr')} "
                f"({g.get('savings_pct')}% off)  JA code {g.get('jan_aushadhi_code')}"
            )
        for r in mapping.get("reasons", []):
            j.say(f"  reason: {r}")
        b.detail["mapping"] = mapping.get("reasons")

    # ==================================================== 17. prescription
    @j.beat(17, "Draft the prescription [direct DB] and sign it")
    def _(b: Beat) -> None:
        from app.db.models.clinical import Prescription
        from app.db.session import SessionLocal

        med = j.state.get("chosen_med") or {"name": "Doxycycline 100 mg", "ingredient": "doxycycline"}
        items = [
            {
                "name": med["name"],
                "ingredient": med.get("ingredient"),
                "dose": "100 mg",
                "frequency": "twice daily",
                "duration_days": 7,
            }
        ]
        prescription_id = uuid4()

        async def draft() -> None:
            async with SessionLocal() as s:
                s.add(
                    Prescription(
                        id=prescription_id,
                        visit_id=VISIT_ID,
                        patient_id=PATIENT_ID,
                        items=items,
                        approved_by=None,
                        approved_at=None,
                        content_hash=None,
                        locked=False,
                    )
                )
                await s.commit()

        asyncio.run(draft())
        j.say("no POST /prescriptions in the contract -- drafting the row directly")
        j.state["prescription_id"] = str(prescription_id)

        signed = j.post(
            f"/approvals/prescription/{prescription_id}",
            token=j.state["doctor_token"],
            captcha=True,
        )
        j.say(f"signed: locked={signed.get('locked')} hash={str(signed.get('content_hash'))[:16]}...")
        b.detail["prescription_id"] = str(prescription_id)

    @j.beat(18, "Safety-gated generic substitutions for the prescription")
    def _(b: Beat) -> None:
        subs = j.get(
            "/medications/substitutions",
            token=j.state["doctor_token"],
            params={"prescription_id": j.state["prescription_id"]},
        )
        if not subs:
            j.say("no substitution offered (brand may already be the generic)")
        for s in subs[:5]:
            j.say(f"  {s}")
        b.detail["substitutions"] = len(subs)

    @j.beat(19, "Visit closes at PRESCRIBED")
    def _(b: Beat) -> None:
        visit = j.post(
            f"/visits/{VISIT_ID}/advance",
            token=j.state["doctor_token"],
            json={"target": "PRESCRIBED"},
        )
        j.say(f"visit state -> {visit['state']}")
        missing = [
            k for k in ("triage", "brief", "documents", "queue") if not visit.get(k)
        ]
        j.say(f"assembled VisitOut sections present: {[k for k in ('triage','brief','documents','queue') if visit.get(k)]}")
        if visit["state"] != "PRESCRIBED":
            raise RuntimeError(f"visit ended in {visit['state']}")
        b.detail["missing_sections"] = missing

    @j.beat(20, "Patient-facing artefacts: PDF export and plain-language chat")
    def _(b: Beat) -> None:
        pdf = j.client.get(
            f"{API}/exports/prescription/{j.state['prescription_id']}.pdf",
            headers={"Authorization": f"Bearer {j.state['doctor_token']}"},
        )
        if pdf.status_code == 200:
            out = ROOT / "infra" / "storage" / "demo_prescription.pdf"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(pdf.content)
            j.say(f"prescription PDF written to {out} ({len(pdf.content)} bytes)")
        else:
            # weasyprint needs the GTK/pango native libraries, absent on a
            # stock Windows box. Reported, not fatal -- the PDF is a
            # convenience artefact, not a step the clinical pipeline needs.
            j.say(f"PDF export unavailable ({pdf.status_code}) -- see notes")
            b.detail["pdf_error"] = pdf.text[:200]

        # Read the SSE stream to completion; abandoning it mid-iteration
        # resets the connection and looks like a server fault when it is not.
        # A fresh connection: the failed PDF export above leaves the pooled
        # one in a state Windows resets on the next write.
        chat_client = httpx.Client(timeout=120.0)
        chat = chat_client.post(
            f"{API}/chat/patient",
            headers={"Authorization": f"Bearer {j.state['patient_token']}"},
            json={"message": "What did my blood test show, and what is this medicine for?"},
        )
        if chat.status_code != 200:
            raise RuntimeError(f"patient chat -> {chat.status_code}: {chat.text[:200]}")

        body = chat.text
        tokens = [
            json.loads(line[6:])["text"]
            for line in body.splitlines()
            if line.startswith("data: ") and '"text"' in line
        ]
        cites = [line for line in body.splitlines() if line.startswith("event: citation")]
        j.say("patient chat reply:")
        j.say(f'  "{"".join(tokens)[:220]}"')
        j.say(f"  citations streamed: {len(cites)}")
        if not tokens:
            raise RuntimeError("patient chat streamed no tokens")
        b.detail["chat_tokens"] = len(tokens)
        b.detail["chat_citations"] = len(cites)

    code = j.run()

    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                [
                    {
                        "n": b.number,
                        "title": b.title,
                        "status": b.status,
                        "error": b.error,
                        "detail": b.detail,
                    }
                    for b in j.beats
                ],
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"  transcript written to {args.json_out}")

    return code


if __name__ == "__main__":
    raise SystemExit(main())
