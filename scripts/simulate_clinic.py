#!/usr/bin/env python
"""One district-hospital OPD day, simulated (section 8 N3.5).

400 patients, 6 doctors, two IST sessions (09:00-13:00 and 17:00-20:00) with
the morning surge an Indian government OPD actually sees. The point is not a
pretty number -- it is to hold the queue policy to account at the volume it
will really run at, and to prove the same seed replays to the same JSON.

Deliberately a pure in-memory discrete-event simulation: no DB, no Redis, no
network. It exercises the *policy* (the priority key from `packs/queue.yaml`
and `packs/triage_india.yaml`, the aging rule, the statutory bonus, the
emergency pre-empt), which is the part that can silently regress. Wiring it
through Postgres would test SQLAlchemy, take minutes instead of seconds, and
make the "runs with the network unplugged" requirement impossible to meet.

Usage:
    python scripts/simulate_clinic.py --seed 42 --out /tmp/sim.json
    python scripts/simulate_clinic.py --load 1000 --report
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKS = _REPO_ROOT / "backend" / "app" / "services" / "rules" / "packs"

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SERVICE_DATE = dt.date(2026, 7, 13)  # a Monday in monsoon season


def _pack(name: str) -> dict:
    return yaml.safe_load((_PACKS / name).read_text(encoding="utf-8")) or {}


QUEUE_PACK = _pack("queue.yaml")
TRIAGE_PACK = _pack("triage_india.yaml")

AVG_CONSULT_MINUTES = QUEUE_PACK["avg_consult_minutes"]
AGING_MINUTES = QUEUE_PACK["aging_minutes"]
AGING_MAX_BONUS = QUEUE_PACK["aging_max_bonus"]
EMERGENCY_SEVERITY_MAX = QUEUE_PACK["emergency_severity_max"]
TOKEN_PREFIX = QUEUE_PACK["token_prefix_by_facility"]["dh"]
# All statutory groups carry bonus 1, capped by `priority_group_max_bonus`.
STATUTORY_BONUS = min(
    min(int(g["bonus"]) for g in TRIAGE_PACK["priority_groups"]),
    int(TRIAGE_PACK["priority_group_max_bonus"]),
)

# --- the day's shape -------------------------------------------------------

N_PATIENTS = 400
N_DOCTORS = 6
SESSIONS_IST = [(dt.time(9, 0), dt.time(13, 0)), (dt.time(17, 0), dt.time(20, 0))]

# ~65% of arrivals land before 11:00 IST -- the classic government-OPD
# morning crush, where people queue from before the counter opens.
MORNING_SURGE_CUTOFF = dt.time(11, 0)
MORNING_SURGE_SHARE = 0.65

TIER_MIX = {1: 0.01, 2: 0.06, 3: 0.28, 4: 0.45, 5: 0.20}
WALK_IN_SHARE = 0.70
NO_SHOW_SHARE_OF_BOOKED = 0.12

PRIORITY_GROUP_SHARES = {
    "pregnant_third_trimester": 0.08,
    "infant_under_1": 0.06,
    "senior_citizen_60_plus": 0.14,
}

# Monsoon fever surge: a fifth of arrivals present as acute febrile illness
# and route into the dengue/malaria/enteric-fever rule path.
MONSOON_FEVER_SHARE = 0.20

# Injected mid-day emergencies (minutes after the morning session opens).
INJECTED_EMERGENCIES = [
    (95, "obstetric", "post-partum haemorrhage", "chc"),
    (150, "trauma", "road traffic accident polytrauma", "dh"),
    (215, "envenoming", "snakebite with bleeding gums", "dh"),
]

# Indicative per-item generic saving, rupees. Deliberately a flat modelled
# figure rather than a live lookup: the simulation must run offline, and the
# real per-brand numbers are already asserted in test_rxnorm/test_substitution.
SAVINGS_PER_SUBSTITUTION_INR = 42.0
SUBSTITUTION_RATE = 0.55


def _colour(severity: int) -> str:
    return TRIAGE_PACK["tiers"][severity]["colour"]


def _open_minutes_between(start: dt.datetime, end: dt.datetime) -> float:
    """Minutes between two moments that fall inside an open OPD session.

    The clinic runs two IST sessions with a four-hour break between them, so
    elapsed wall-clock time overstates queue wait for anyone who crosses the
    break. Computed by intersecting `[start, end)` with each session window.
    """
    if end <= start:
        return 0.0
    total = 0.0
    for window_start, window_end in _session_windows():
        overlap_start = max(start, window_start)
        overlap_end = min(end, window_end)
        if overlap_end > overlap_start:
            total += (overlap_end - overlap_start).total_seconds() / 60
    return total


@lru_cache(maxsize=1)
def _session_windows() -> tuple[tuple[dt.datetime, dt.datetime], ...]:
    return tuple(
        (
            dt.datetime.combine(SERVICE_DATE, start, tzinfo=IST),
            dt.datetime.combine(SERVICE_DATE, end, tzinfo=IST),
        )
        for start, end in SESSIONS_IST
    )


@dataclass
class Patient:
    index: int
    severity: int
    walk_in: bool
    priority_group: str | None
    febrile: bool
    arrival: dt.datetime
    token: str
    scheduled: dt.datetime | None = None
    emergency: bool = False
    emergency_kind: str | None = None
    required_facility: str | None = None

    no_show: bool = False
    started: dt.datetime | None = None
    finished: dt.datetime | None = None
    doctor: int | None = None
    referred_out: bool = False
    substituted: bool = False

    @property
    def wait_minutes(self) -> float:
        """Time spent actually waiting at the OPD, excluding the 13:00-17:00
        IST break.

        Counting the closed break as queue time is not what happens: when the
        morning session ends the counter closes and the patient goes home
        with their token for the evening session. Charging them those four
        hours would report ~400-minute waits for people who waited about 90
        minutes in the hall, and would make the tier-4/5 threshold a measure
        of the lunch break rather than of the queue policy.
        """
        if self.started is None:
            return float("nan")
        return max(0.0, _open_minutes_between(self.arrival, self.started))


@dataclass
class Clock:
    """Injected time. Nothing in this module reads the wall clock, so a run
    is a pure function of (seed, parameters).
    """

    now: dt.datetime

    def advance_to(self, moment: dt.datetime) -> None:
        if moment > self.now:
            self.now = moment


@dataclass
class Sim:
    seed: int = 42
    n_patients: int = N_PATIENTS
    n_doctors: int = N_DOCTORS
    patients: list[Patient] = field(default_factory=list)
    double_books: int = 0

    def _rng(self) -> random.Random:
        return random.Random(self.seed)

    # --- arrival generation ------------------------------------------------

    def _arrival_times(self, rng: random.Random) -> list[dt.datetime]:
        """Poisson-ish arrivals modulated by the morning surge: draw a uniform
        offset inside whichever window the patient is assigned to, then sort.
        Using sorted uniforms rather than an explicit exponential process
        keeps the arrival count exact at `n_patients`, which the tier-mix and
        no-show shares below both depend on.
        """
        (m_start, m_end), (e_start, e_end) = _session_windows()
        surge_end = dt.datetime.combine(SERVICE_DATE, MORNING_SURGE_CUTOFF, tzinfo=IST)

        n_surge = int(self.n_patients * MORNING_SURGE_SHARE)
        n_rest_morning = int(self.n_patients * 0.15)
        n_evening = self.n_patients - n_surge - n_rest_morning

        def _uniform_in(a: dt.datetime, b: dt.datetime, count: int) -> list[dt.datetime]:
            span = (b - a).total_seconds()
            return [a + dt.timedelta(seconds=rng.uniform(0, span)) for _ in range(count)]

        times = (
            _uniform_in(m_start, surge_end, n_surge)
            + _uniform_in(surge_end, m_end, n_rest_morning)
            + _uniform_in(e_start, e_end, n_evening)
        )
        times.sort()
        return times

    def _draw_severity(self, rng: random.Random) -> int:
        roll = rng.random()
        cumulative = 0.0
        for tier in sorted(TIER_MIX):
            cumulative += TIER_MIX[tier]
            if roll <= cumulative:
                return tier
        return 5

    def _draw_priority_group(self, rng: random.Random) -> str | None:
        roll = rng.random()
        cumulative = 0.0
        # Deterministic order: iterate the dict as written, never a set.
        for group, share in PRIORITY_GROUP_SHARES.items():
            cumulative += share
            if roll <= cumulative:
                return group
        return None

    def build(self) -> None:
        rng = self._rng()
        arrivals = self._arrival_times(rng)

        self.patients = []
        for i, arrival in enumerate(arrivals):
            severity = self._draw_severity(rng)
            walk_in = rng.random() < WALK_IN_SHARE
            patient = Patient(
                index=i,
                severity=severity,
                walk_in=walk_in,
                priority_group=self._draw_priority_group(rng),
                febrile=rng.random() < MONSOON_FEVER_SHARE,
                arrival=arrival,
                token=f"{TOKEN_PREFIX}-{i + 1:03d}",
                emergency=severity <= EMERGENCY_SEVERITY_MAX,
            )
            if not walk_in:
                # booked patients have a slot; a share of them never turn up
                patient.scheduled = arrival
                patient.no_show = rng.random() < NO_SHOW_SHARE_OF_BOOKED
            patient.substituted = rng.random() < SUBSTITUTION_RATE
            self.patients.append(patient)

        self._inject_emergencies()

    def _inject_emergencies(self) -> None:
        """Three mid-day emergencies: an obstetric case, a polytrauma and a
        snakebite. Each overrides an existing arrival rather than adding one,
        so the day's headcount stays exactly `n_patients`.
        """
        morning_start = _session_windows()[0][0]
        for offset_minutes, kind, _label, required_facility in INJECTED_EMERGENCIES:
            moment = morning_start + dt.timedelta(minutes=offset_minutes)
            # the first still-unstarted arrival at or after `moment`
            candidate = next(
                (p for p in self.patients if p.arrival >= moment and not p.emergency),
                None,
            )
            if candidate is None:
                continue
            candidate.severity = 1
            candidate.emergency = True
            candidate.emergency_kind = kind
            candidate.required_facility = required_facility
            candidate.no_show = False
            # an emergency needing a facility this DH cannot provide is
            # referred up the ladder rather than queued here
            candidate.referred_out = required_facility not in ("dh", "chc", "phc", "sdh")

    # --- the queue policy under test ---------------------------------------

    def _effective_severity(self, patient: Patient, waited_minutes: float) -> int:
        """Mirrors `app.services.queueing.pq._effective_severity` exactly --
        aging plus the statutory bonus, both floored above RED. Kept in step
        deliberately: a simulation that scores a different policy from the
        one in production measures nothing.
        """
        aging_bonus = min(AGING_MAX_BONUS, int(waited_minutes // AGING_MINUTES))
        statutory_bonus = STATUTORY_BONUS if patient.priority_group else 0
        effective = patient.severity - aging_bonus - statutory_bonus
        if not patient.emergency:
            effective = max(effective, EMERGENCY_SEVERITY_MAX + 1)
        return max(1, effective)

    def _sort_key(self, patient: Patient, now: dt.datetime) -> tuple:
        # hall time, not elapsed time -- see `Patient.wait_minutes`
        waited = _open_minutes_between(patient.arrival, now)
        return (
            0 if patient.emergency else 1,
            self._effective_severity(patient, waited),
            0 if patient.priority_group else 1,
            -waited,
            patient.scheduled or dt.datetime.max.replace(tzinfo=dt.UTC),
            patient.arrival,
            patient.index,
        )

    def run(self) -> None:
        """Serve the day: 6 doctors, each free at a time, pulling the
        highest-priority waiting patient whenever they finish.
        """
        windows = _session_windows()
        doctor_free = [windows[0][0] for _ in range(self.n_doctors)]
        doctor_seen: list[int] = [0] * self.n_doctors

        pending = [p for p in self.patients if not p.no_show and not p.referred_out]
        pending.sort(key=lambda p: (p.arrival, p.index))
        waiting: list[Patient] = []
        cursor = 0

        while cursor < len(pending) or waiting:
            # the doctor who frees up soonest takes the next patient
            doctor = min(range(self.n_doctors), key=lambda d: (doctor_free[d], d))
            now = doctor_free[doctor]

            # admit everyone who has arrived by now
            while cursor < len(pending) and pending[cursor].arrival <= now:
                waiting.append(pending[cursor])
                cursor += 1

            if not waiting:
                # idle until the next arrival
                if cursor < len(pending):
                    doctor_free[doctor] = pending[cursor].arrival
                    continue
                break

            waiting.sort(key=lambda p: self._sort_key(p, now))
            patient = waiting.pop(0)

            start = max(now, patient.arrival)
            start = self._respect_session_break(start)

            patient.started = start
            patient.doctor = doctor
            patient.finished = start + dt.timedelta(minutes=AVG_CONSULT_MINUTES)
            doctor_free[doctor] = patient.finished
            doctor_seen[doctor] += 1

        self._doctor_seen = doctor_seen

    def _respect_session_break(self, moment: dt.datetime) -> dt.datetime:
        """No consult starts inside the 13:00-17:00 IST break. IST is a
        half-hour offset, so every comparison is done on IST wall-clock, not
        on a UTC hour.
        """
        (_m_start, m_end), (e_start, _e_end) = _session_windows()
        if m_end <= moment < e_start:
            return e_start
        return moment

    # --- reporting ---------------------------------------------------------

    def report(self) -> dict:
        served = [p for p in self.patients if p.started is not None]
        by_tier: dict[str, dict] = {}
        for tier in sorted(TIER_MIX):
            waits = [p.wait_minutes for p in served if p.severity == tier]
            by_tier[str(tier)] = {
                "colour": _colour(tier),
                "count": len(waits),
                "mean_wait_minutes": round(statistics.fmean(waits), 2) if waits else 0.0,
                "p95_wait_minutes": round(_p95(waits), 2) if waits else 0.0,
                "max_wait_minutes": round(max(waits), 2) if waits else 0.0,
            }

        by_colour: dict[str, dict] = {}
        for colour in ("red", "yellow", "green"):
            waits = [p.wait_minutes for p in served if _colour(p.severity) == colour]
            by_colour[colour] = {
                "count": len(waits),
                "mean_wait_minutes": round(statistics.fmean(waits), 2) if waits else 0.0,
                "p95_wait_minutes": round(_p95(waits), 2) if waits else 0.0,
                "max_wait_minutes": round(max(waits), 2) if waits else 0.0,
            }

        emergencies = [p for p in served if p.emergency]
        emergency_waits = [p.wait_minutes for p in emergencies]

        seen = getattr(self, "_doctor_seen", [0] * self.n_doctors)
        total_seen = sum(seen) or 1
        utilisation = [count / total_seen for count in seen]

        low_tier_waits = [p.wait_minutes for p in served if p.severity in (4, 5)]

        substituted = [p for p in self.patients if p.substituted and not p.no_show]

        return {
            "seed": self.seed,
            "service_date": SERVICE_DATE.isoformat(),
            "patients": self.n_patients,
            "doctors": self.n_doctors,
            "served": len(served),
            "no_shows": sum(1 for p in self.patients if p.no_show),
            "referred_out": sum(1 for p in self.patients if p.referred_out),
            "double_books": self.double_books,
            "walk_in_share": round(
                sum(1 for p in self.patients if p.walk_in) / len(self.patients), 3
            ),
            "febrile_share": round(
                sum(1 for p in self.patients if p.febrile) / len(self.patients), 3
            ),
            "by_tier": by_tier,
            "by_colour": by_colour,
            "emergency": {
                "count": len(emergencies),
                "max_time_to_consult_minutes": round(max(emergency_waits), 2)
                if emergency_waits
                else 0.0,
                "mean_time_to_consult_minutes": round(statistics.fmean(emergency_waits), 2)
                if emergency_waits
                else 0.0,
            },
            "max_wait_tier_4_5_minutes": round(max(low_tier_waits), 2) if low_tier_waits else 0.0,
            "doctor_utilisation": [round(u, 4) for u in utilisation],
            "doctor_utilisation_stddev": round(statistics.pstdev(utilisation), 4)
            if len(utilisation) > 1
            else 0.0,
            "statutory_priority": _statutory_report(served),
            "staffing": self._staffing(),
            "total_savings_inr": round(len(substituted) * SAVINGS_PER_SUBSTITUTION_INR, 2),
        }

    def _staffing(self) -> dict:
        """Whether this day is staffed within the optimizer's own per-doctor
        session cap.

        `optimizer.yaml: max_patients_per_doctor_per_session` is a hard filter
        in `rank_doctors` -- a doctor at the cap is removed from the candidate
        set. A simulated day that puts more than the cap on each doctor is
        therefore a day the scheduler itself would refuse to book, and its
        wait figures should be read as an over-capacity scenario rather than
        as the policy's steady state.
        """
        cap = int(
            _pack("optimizer.yaml").get("max_patients_per_doctor_per_session", 50)
        )
        per_doctor = self.n_patients / self.n_doctors
        return {
            "patients_per_doctor": round(per_doctor, 2),
            "session_cap": cap,
            "doctors_required_at_cap": -(-self.n_patients // cap),  # ceil
            "within_session_cap": per_doctor <= cap,
        }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    # nearest-rank p95: deterministic, and correct for small samples where
    # an interpolating percentile would invent a value nobody waited.
    index = max(0, min(len(ordered) - 1, int(round(0.95 * len(ordered))) - 1))
    return ordered[index]


def _session_of(moment: dt.datetime) -> int:
    """Which OPD session a moment falls in (0 morning, 1 evening)."""
    for i, (start, end) in enumerate(_session_windows()):
        if start <= moment < end:
            return i
    return len(_session_windows()) - 1


def _statutory_report(served: list[Patient]) -> dict:
    """Every statutory-priority patient's wait against the median wait of
    comparable patients -- same tier, same OPD session.

    Compared within the session, not across the whole day: a patient who
    walks in at 19:30 into a full evening queue cannot wait less than the
    09:05 arrival who found an empty hall, and no priority rule can change
    that. Measuring against the whole-day tier median would report those
    late arrivals as fairness breaches when the queue in fact placed them
    ahead of every comparable non-priority patient beside them.
    """
    out: dict[str, dict] = {}
    for group in PRIORITY_GROUP_SHARES:
        members = [p for p in served if p.priority_group == group]
        breaches = 0
        for patient in members:
            peers = [
                p.wait_minutes
                for p in served
                if p.severity == patient.severity
                and _session_of(p.arrival) == _session_of(patient.arrival)
            ]
            if not peers:
                continue
            if patient.wait_minutes > statistics.median(peers):
                breaches += 1
        out[group] = {
            "count": len(members),
            "waits_above_comparable_median": breaches,
            "mean_wait_minutes": round(
                statistics.fmean([p.wait_minutes for p in members]), 2
            )
            if members
            else 0.0,
        }
    return out


def simulate(seed: int = 42, n_patients: int = N_PATIENTS, n_doctors: int = N_DOCTORS) -> dict:
    """Run one OPD day and return its report. Pure in `(seed, n_patients,
    n_doctors)` -- the same arguments always produce byte-identical JSON.
    """
    sim = Sim(seed=seed, n_patients=n_patients, n_doctors=n_doctors)
    sim.build()
    sim.run()
    return sim.report()


def load_probe(operations: int) -> dict:
    """Queue-operation throughput on the policy layer (N4.3's budget, run
    here so the number is available before hardening starts).
    """
    sim = Sim(seed=42, n_patients=min(operations, 2000))
    sim.build()

    now = _session_windows()[0][0] + dt.timedelta(minutes=30)
    waiting = sim.patients[:200]

    durations: list[float] = []
    for _ in range(operations):
        start = time.perf_counter()
        sorted(waiting, key=lambda p: sim._sort_key(p, now))
        durations.append((time.perf_counter() - start) * 1000)

    return {
        "operations": operations,
        "queue_op_p50_ms": round(statistics.median(durations), 3),
        "queue_op_p95_ms": round(_p95(durations), 3),
        "queue_op_max_ms": round(max(durations), 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patients", type=int, default=N_PATIENTS)
    parser.add_argument("--doctors", type=int, default=N_DOCTORS)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--load", type=int, default=None, help="run N queue operations")
    parser.add_argument("--report", action="store_true", help="print the report to stdout")
    args = parser.parse_args(argv)

    if args.load is not None:
        result = load_probe(args.load)
    else:
        result = simulate(
            seed=args.seed, n_patients=args.patients, n_doctors=args.doctors
        )

    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.report or args.out is None:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
