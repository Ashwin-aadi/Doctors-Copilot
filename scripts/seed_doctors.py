#!/usr/bin/env python
"""Synthetic doctor directory: many specialties, regions, languages and tariffs.

`scripts/seed.py` seeds the six fixed demo doctors that tests and curl sessions
pin by UUID. That is too thin to exercise the ranking optimiser, which filters
on specialty, distance, consultation fee, language and scheme empanelment --
with six doctors in three cities, every query returns nearly the same list.

This script generates a realistic Indian clinic network on top of it: eleven
facilities across nine states (primary health centre through district hospital
and private multispecialty), staffed with doctors covering every bookable
specialty in `rag.triage_rag.CANONICAL_SPECIALTIES`. Super-specialty posts only
appear at the facility tiers that actually run those OPDs, so a PHC lookup for
cardiology correctly falls through to the district hospital.

Generation is seeded, so re-running produces identical rows, and every record is
written by primary key -- the script is safe to run repeatedly and never
disturbs the fixed demo records seeded by `seed.py`.

  clinics       00000000-0000-0000-0000-0000000010{01-11}
  doctor users  00000000-0000-0000-0000-0000000040{01-..}
  doctors       00000000-0000-0000-0000-0000000020{01-..}
  availability  00000000-0000-0000-0000-000000810{...}

Usage:
    python scripts/seed_doctors.py [--dry-run]
"""

import argparse
import asyncio
import random
import sys
from datetime import date, time, timedelta
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from passlib.context import CryptContext  # noqa: E402

from app.db.models.scheduling import Availability, Clinic, Doctor  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEMO_PASSWORD_HASH = pwd_context.hash("demo-password-123")

# Fixed so the generated directory is reproducible across machines and runs.
RNG_SEED = 20260831


# --- regions ------------------------------------------------------------
#
# Language codes are ISO 639-1, matching what the scheduling optimiser filters
# on. Councils are the real state medical councils that issue the registration
# a doctor practises under.

REGIONS: dict[str, dict] = {
    "delhi": {
        "city": "New Delhi", "state": "Delhi", "lat": 28.6139, "lng": 77.2090,
        "languages": ["hi", "en"], "council": "Delhi Medical Council", "code": "DMC",
        "first_m": ["Rohit", "Aman", "Karan", "Sahil", "Nikhil"],
        "first_f": ["Neha", "Pooja", "Ritika", "Shweta", "Aarti"],
        "surnames": ["Khanna", "Chadha", "Sethi", "Bhatia", "Ahuja", "Grover"],
    },
    "maharashtra": {
        "city": "Pune", "state": "Maharashtra", "lat": 18.5204, "lng": 73.8567,
        "languages": ["mr", "hi", "en"], "council": "Maharashtra Medical Council",
        "code": "MMC",
        "first_m": ["Sameer", "Nilesh", "Prasad", "Ketan", "Omkar"],
        "first_f": ["Snehal", "Manasi", "Rutuja", "Vaishali", "Sayali"],
        "surnames": ["Deshpande", "Kulkarni", "Joshi", "Patil", "Gokhale", "Sawant"],
    },
    "mumbai": {
        "city": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "lng": 72.8777,
        "languages": ["mr", "hi", "en"], "council": "Maharashtra Medical Council",
        "code": "MMC",
        "first_m": ["Zaid", "Farhan", "Jatin", "Rahul", "Imran"],
        "first_f": ["Sana", "Ayesha", "Zoya", "Alisha", "Tanvi"],
        "surnames": ["Merchant", "Shaikh", "Contractor", "Dalal", "Mehta", "Ansari"],
    },
    "karnataka": {
        "city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lng": 77.5946,
        "languages": ["kn", "en"], "council": "Karnataka Medical Council", "code": "KMC",
        "first_m": ["Ravi", "Manjunath", "Girish", "Suresh", "Praveen"],
        "first_f": ["Shruthi", "Deepa", "Chaitra", "Ashwini", "Sowmya"],
        "surnames": ["Gowda", "Shetty", "Hegde", "Rao", "Bhat", "Kamath"],
    },
    "tamilnadu": {
        "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lng": 80.2707,
        "languages": ["ta", "en"], "council": "Tamil Nadu Medical Council", "code": "TNMC",
        "first_m": ["Karthik", "Senthil", "Muthu", "Bala", "Dinesh"],
        "first_f": ["Lakshmi", "Revathi", "Kavitha", "Janani", "Divya"],
        "surnames": [
            "Subramanian", "Venkatesan", "Krishnan", "Natarajan", "Rajagopal", "Sundaram",
        ],
    },
    "telangana": {
        "city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "lng": 78.4867,
        "languages": ["te", "hi", "en"], "council": "Telangana State Medical Council",
        "code": "TSMC",
        "first_m": ["Srinivas", "Kiran", "Naveen", "Harish", "Vamsi"],
        "first_f": ["Swapna", "Anitha", "Sirisha", "Padmaja", "Bhavani"],
        "surnames": ["Reddy", "Naidu", "Chowdary", "Rao", "Goud", "Varma"],
    },
    "westbengal": {
        "city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lng": 88.3639,
        "languages": ["bn", "hi", "en"], "council": "West Bengal Medical Council",
        "code": "WBMC",
        "first_m": ["Subhash", "Anirban", "Debashis", "Sourav", "Tapan"],
        "first_f": ["Rituparna", "Moushumi", "Paromita", "Sanchita", "Ipsita"],
        "surnames": ["Chatterjee", "Banerjee", "Mukherjee", "Ghosh", "Dasgupta", "Sen"],
    },
    "uttarpradesh": {
        "city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "lng": 80.9462,
        "languages": ["hi", "en"], "council": "Uttar Pradesh Medical Council", "code": "UPMC",
        "first_m": ["Alok", "Devendra", "Pankaj", "Shivam", "Yogesh"],
        "first_f": ["Sunita", "Kavya", "Preeti", "Nidhi", "Rachna"],
        "surnames": ["Srivastava", "Tripathi", "Awasthi", "Dixit", "Pandey", "Bajpai"],
    },
    "rajasthan": {
        "city": "Jaipur", "state": "Rajasthan", "lat": 26.9124, "lng": 75.7873,
        "languages": ["hi", "en"], "council": "Rajasthan Medical Council", "code": "RMC",
        "first_m": ["Mahendra", "Bhanwar", "Jitendra", "Lokesh", "Vikas"],
        "first_f": ["Suman", "Rekha", "Meenakshi", "Jyoti", "Bhavna"],
        "surnames": ["Rathore", "Choudhary", "Shekhawat", "Jain", "Meena", "Sisodia"],
    },
    "assam": {
        "city": "Guwahati", "state": "Assam", "lat": 26.1445, "lng": 91.7362,
        "languages": ["as", "bn", "hi", "en"], "council": "Assam Medical Council",
        "code": "AMC",
        "first_m": ["Bhaskar", "Nayan", "Pranab", "Dhrubajyoti", "Ranjit"],
        "first_f": ["Rimpi", "Munmun", "Nabanita", "Jonali", "Parismita"],
        "surnames": ["Baruah", "Hazarika", "Sarma", "Gogoi", "Bora", "Deka"],
    },
}


# --- facilities ---------------------------------------------------------
#
# Tiers follow the public health system: PHC (primary health centre) -> CHC
# (community health centre) -> SDH (sub-divisional hospital) -> DH (district
# hospital), plus private clinic and hospital. The slugs are the ones the
# scheduling optimiser ranks on (`services/rules/packs/optimizer.yaml`), not
# the mixed-case set `api/v1/doctors_profile.py` validates against -- see the
# DRIFT note in docs/DECISIONS.md. `fee_multiplier` turns the specialty
# base tariff into what that tier actually charges -- a government PHC is
# nearly free, a private tower is not.

FACILITY_TIERS: dict[str, dict] = {
    "phc": {"fee_multiplier": 0.2, "emergency": False, "schemes": ["state_scheme", "pmjay"]},
    "chc": {"fee_multiplier": 0.35, "emergency": False, "schemes": ["state_scheme", "pmjay"]},
    "sdh": {"fee_multiplier": 0.5, "emergency": True, "schemes": ["state_scheme", "pmjay"]},
    "dh": {"fee_multiplier": 0.6, "emergency": True,
           "schemes": ["state_scheme", "pmjay", "cghs"]},
    "private_clinic": {"fee_multiplier": 0.85, "emergency": False, "schemes": ["cghs"]},
    "private_hospital": {"fee_multiplier": 1.0, "emergency": True,
                         "schemes": ["pmjay", "cghs"]},
}

# Specialties a tier is staffed for. Anything beyond this list is referred
# upward, which is what the referral pathway looks like on the ground.
CORE_OPD = ["general_medicine", "pediatrics", "obstetrics_gynaecology"]
DISTRICT_OPD = CORE_OPD + [
    "general_surgery", "orthopedics", "dermatology", "ophthalmology",
    "ent", "psychiatry", "pulmonology",
]

TIER_SPECIALTIES: dict[str, list[str] | None] = {
    "phc": CORE_OPD,
    "chc": CORE_OPD + ["general_surgery", "orthopedics", "dermatology", "ophthalmology"],
    "sdh": DISTRICT_OPD,
    "dh": None,       # None means every specialty
    "private_clinic": None,
    "private_hospital": None,
}

CLINICS: list[dict] = [
    {"name": "Chandni Chowk Urban Primary Health Centre", "region": "delhi",
     "tier": "phc", "pin_code": "110006", "dlat": 0.032, "dlng": -0.007},
    {"name": "Lok Nayak District Hospital", "region": "delhi",
     "tier": "dh", "pin_code": "110002", "dlat": 0.0, "dlng": 0.014},
    {"name": "Aundh Community Health Centre", "region": "maharashtra",
     "tier": "chc", "pin_code": "411007", "dlat": 0.043, "dlng": -0.049},
    {"name": "Andheri Multispecialty Hospital", "region": "mumbai",
     "tier": "private_hospital", "pin_code": "400053", "dlat": 0.043, "dlng": -0.023},
    {"name": "Koramangala Multispecialty Clinic", "region": "karnataka",
     "tier": "private_clinic", "pin_code": "560034", "dlat": -0.036, "dlng": 0.030},
    {"name": "Kilpauk Government Sub-Divisional Hospital", "region": "tamilnadu",
     "tier": "sdh", "pin_code": "600010", "dlat": 0.001, "dlng": -0.029},
    {"name": "Gandhi District Hospital, Secunderabad", "region": "telangana",
     "tier": "dh", "pin_code": "500003", "dlat": 0.056, "dlng": 0.007},
    {"name": "Salt Lake Community Health Centre", "region": "westbengal",
     "tier": "chc", "pin_code": "700091", "dlat": 0.014, "dlng": 0.045},
    {"name": "Balrampur District Hospital", "region": "uttarpradesh",
     "tier": "dh", "pin_code": "226018", "dlat": 0.008, "dlng": -0.010},
    {"name": "Jhotwara Primary Health Centre", "region": "rajasthan",
     "tier": "phc", "pin_code": "302012", "dlat": 0.021, "dlng": -0.038},
    {"name": "Guwahati Medical College Outreach Clinic", "region": "assam",
     "tier": "sdh", "pin_code": "781032", "dlat": 0.007, "dlng": -0.019},
]


# --- specialties --------------------------------------------------------
#
# `count` is how many doctors to generate across the whole network, tracking
# the real staffing pyramid: plenty of general medicine, a handful of
# super-specialists. `base_fee` is the private-tier consultation fee in INR,
# before the facility multiplier.

SPECIALTIES: dict[str, dict] = {
    "general_medicine": {
        "count": 8, "base_fee": 500, "slot": 10,
        "quals": ["MBBS", "MBBS, MD (General Medicine)", "MBBS, DNB (Medicine)"],
        "also": [],
    },
    "pediatrics": {
        "count": 5, "base_fee": 600, "slot": 15,
        "quals": ["MBBS, MD (Paediatrics)", "MBBS, DCH, DNB (Paediatrics)"],
        "also": [],
    },
    "obstetrics_gynaecology": {
        "count": 5, "base_fee": 700, "slot": 15,
        "quals": ["MBBS, MS (Obstetrics & Gynaecology)", "MBBS, DGO, DNB (Obs & Gyn)"],
        "also": [],
    },
    "general_surgery": {
        "count": 4, "base_fee": 700, "slot": 15,
        "quals": ["MBBS, MS (General Surgery)", "MBBS, DNB (General Surgery)"],
        "also": [],
    },
    "orthopedics": {
        "count": 4, "base_fee": 700, "slot": 15,
        "quals": ["MBBS, MS (Orthopaedics)", "MBBS, D.Ortho, DNB (Orthopaedics)"],
        "also": [],
    },
    "cardiology": {
        "count": 3, "base_fee": 1200, "slot": 20,
        "quals": ["MBBS, MD (Medicine), DM (Cardiology)", "MBBS, MD, DNB (Cardiology)"],
        "also": ["general_medicine"],
    },
    "dermatology": {
        "count": 3, "base_fee": 600, "slot": 10,
        "quals": ["MBBS, MD (Dermatology, Venereology & Leprosy)", "MBBS, DDVL"],
        "also": [],
    },
    "pulmonology": {
        "count": 3, "base_fee": 800, "slot": 15,
        "quals": ["MBBS, MD (Respiratory Medicine)", "MBBS, MD (TB & Chest)"],
        "also": ["general_medicine"],
    },
    "ent": {
        "count": 3, "base_fee": 550, "slot": 10,
        "quals": ["MBBS, MS (ENT)", "MBBS, DLO, DNB (Otorhinolaryngology)"],
        "also": [],
    },
    "ophthalmology": {
        "count": 3, "base_fee": 550, "slot": 10,
        "quals": ["MBBS, MS (Ophthalmology)", "MBBS, DO, DNB (Ophthalmology)"],
        "also": [],
    },
    "psychiatry": {
        "count": 3, "base_fee": 900, "slot": 30,
        "quals": ["MBBS, MD (Psychiatry)", "MBBS, DPM, DNB (Psychiatry)"],
        "also": [],
    },
    "endocrinology": {
        "count": 2, "base_fee": 1000, "slot": 20,
        "quals": ["MBBS, MD (Medicine), DM (Endocrinology)"],
        "also": ["general_medicine"],
    },
    "gastroenterology": {
        "count": 2, "base_fee": 1100, "slot": 20,
        "quals": ["MBBS, MD (Medicine), DM (Gastroenterology)"],
        "also": ["general_medicine"],
    },
    "nephrology": {
        "count": 2, "base_fee": 1100, "slot": 20,
        "quals": ["MBBS, MD (Medicine), DM (Nephrology)"],
        "also": ["general_medicine"],
    },
    "neurology": {
        "count": 2, "base_fee": 1200, "slot": 20,
        "quals": ["MBBS, MD (Medicine), DM (Neurology)"],
        "also": ["general_medicine"],
    },
    "urology": {
        "count": 2, "base_fee": 900, "slot": 15,
        "quals": ["MBBS, MS (General Surgery), MCh (Urology)"],
        "also": ["general_surgery"],
    },
}

# OPD shifts. Government facilities run a morning OPD; private clinics add an
# evening sitting for patients who cannot take a working day off.
SHIFTS: dict[str, tuple[time, time]] = {
    "morning": (time(9, 0), time(13, 0)),
    "afternoon": (time(12, 0), time(16, 0)),
    "evening": (time(17, 0), time(20, 30)),
    "fullday": (time(9, 0), time(17, 0)),
}


def clinic_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{1000 + i:012d}")


def doctor_user_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{4000 + i:012d}")


def doctor_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{2000 + i:012d}")


def availability_id(doc_i: int, block: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{810000 + doc_i * 20 + block:012d}")


async def _get_or_create(session, model, id_, **fields):
    existing = await session.get(model, id_)
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing
    obj = model(id=id_, **fields)
    session.add(obj)
    return obj


def _eligible_clinics(specialty: str) -> list[int]:
    """1-based indices of clinics whose tier staffs this specialty."""
    out = []
    for idx, c in enumerate(CLINICS, start=1):
        allowed = TIER_SPECIALTIES[c["tier"]]
        if allowed is None or specialty in allowed:
            out.append(idx)
    return out


def _slugify(name: str) -> str:
    return name.replace("Dr. ", "").lower().replace(" ", ".")


def build_directory() -> list[dict]:
    """Generate the doctor rows deterministically."""
    rng = random.Random(RNG_SEED)
    used_names: set[str] = set()
    used_emails: set[str] = set()
    doctors: list[dict] = []
    index = 0

    for specialty, spec in SPECIALTIES.items():
        # Shuffle the eligible clinics per specialty so the same facility is
        # not always first in line, then deal posts round-robin: every
        # specialty spreads over as many regions as it has doctors.
        order = _eligible_clinics(specialty)
        rng.shuffle(order)

        for j in range(spec["count"]):
            index += 1
            c_idx = order[j % len(order)]
            clinic = CLINICS[c_idx - 1]
            region = REGIONS[clinic["region"]]
            tier = FACILITY_TIERS[clinic["tier"]]

            # Name, unique across the directory.
            candidate = ""
            for _ in range(60):
                pool = region["first_f"] if rng.random() < 0.45 else region["first_m"]
                candidate = f"Dr. {rng.choice(pool)} {rng.choice(region['surnames'])}"
                if candidate not in used_names:
                    break
            used_names.add(candidate)

            email = f"{_slugify(candidate)}@doctorcopilot.dev"
            if email in used_emails:
                email = f"{_slugify(candidate)}.{index}@doctorcopilot.dev"
            used_emails.add(email)

            # Consultation fee: the specialty tariff scaled to the facility
            # tier, jittered, rounded to the nearest 50 rupees the way a real
            # rate card is. Government tiers never exceed a token fee.
            raw = spec["base_fee"] * tier["fee_multiplier"] * rng.uniform(0.85, 1.2)
            fee = float(max(50, round(raw / 50) * 50))

            # Languages: the region's, occasionally with a neighbouring one so
            # language-filtered ranking has something to discriminate on.
            languages = list(region["languages"])
            if rng.random() < 0.3:
                extra = rng.choice(["hi", "en", "ur", "ml", "pa", "or"])
                if extra not in languages:
                    languages.append(extra)

            specialties = [specialty]
            # A super-specialist still runs the parent department's OPD.
            if spec["also"] and rng.random() < 0.6:
                specialties += spec["also"]

            years = rng.randint(3, 28)

            doctors.append({
                "index": index,
                "clinic_index": c_idx,
                "name": candidate,
                "email": email,
                "phone": f"+9198{index:04d}{rng.randint(10000, 99999)}"[:15],
                "specialties": specialties,
                "primary_specialty": specialty,
                "qualifications": rng.choice(spec["quals"]),
                "nmc_reg_no": f"{region['code']}-{2026 - years}-{rng.randint(10000, 99999)}",
                "registration_council": region["council"],
                "languages": languages,
                "fee": fee,
                "rating": round(rng.uniform(3.6, 4.9), 1),
                "slot_minutes": spec["slot"],
                "shifts": (
                    ["morning", "evening"] if clinic["tier"].startswith("private")
                    else ["morning"] if rng.random() < 0.6
                    else [rng.choice(["morning", "afternoon", "fullday"])]
                ),
                # Mon-Fri always; Saturday OPD at roughly half the posts.
                "weekdays": list(range(6)) if rng.random() < 0.5 else list(range(5)),
            })

    return doctors


async def seed(dry_run: bool = False) -> None:
    doctors = build_directory()

    if dry_run:
        _report(doctors)
        return

    async with SessionLocal() as session:
        today = date.today()

        for i, c in enumerate(CLINICS, start=1):
            region = REGIONS[c["region"]]
            tier = FACILITY_TIERS[c["tier"]]
            await _get_or_create(
                session, Clinic, clinic_id(i),
                name=c["name"],
                lat=round(region["lat"] + c["dlat"], 6),
                lng=round(region["lng"] + c["dlng"], 6),
                is_emergency_capable=tier["emergency"],
                state=region["state"], pin_code=c["pin_code"],
                facility_type=c["tier"], schemes=list(tier["schemes"]),
            )
        await session.flush()

        for d in doctors:
            u_id = doctor_user_id(d["index"])
            await _get_or_create(
                session, User, u_id,
                email=d["email"], phone=d["phone"],
                password_hash=DEMO_PASSWORD_HASH, role="doctor", is_active=True,
            )
            await _get_or_create(
                session, Doctor, doctor_id(d["index"]),
                user_id=u_id, name=d["name"],
                specialties=d["specialties"],
                qualifications=d["qualifications"],
                nmc_reg_no=d["nmc_reg_no"],
                registration_council=d["registration_council"],
                languages=d["languages"],
                fee=d["fee"], rating=d["rating"],
                clinic_id=clinic_id(d["clinic_index"]),
            )
        await session.flush()

        for d in doctors:
            block = 0
            for shift in d["shifts"]:
                start, end = SHIFTS[shift]
                for weekday in d["weekdays"]:
                    await _get_or_create(
                        session, Availability, availability_id(d["index"], block),
                        doctor_id=doctor_id(d["index"]),
                        clinic_id=clinic_id(d["clinic_index"]),
                        weekday=weekday, start_time=start, end_time=end,
                        slot_minutes=d["slot_minutes"],
                        valid_from=today, valid_to=today + timedelta(days=90),
                    )
                    block += 1

        await session.commit()

    _report(doctors)


def _report(doctors: list[dict]) -> None:
    print(f"clinics: {len(CLINICS)}   doctors: {len(doctors)}")
    print()
    print(f"{'specialty':<26}{'n':>3}  regions")
    for specialty in SPECIALTIES:
        rows = [d for d in doctors if d["primary_specialty"] == specialty]
        cities = sorted(
            {REGIONS[CLINICS[d["clinic_index"] - 1]["region"]]["city"] for d in rows}
        )
        print(f"{specialty:<26}{len(rows):>3}  {', '.join(cities)}")
    print()
    print(f"{'facility':<45}{'tier':<18}{'staff':>5}")
    for i, c in enumerate(CLINICS, start=1):
        n = sum(1 for d in doctors if d["clinic_index"] == i)
        print(f"{c['name']:<45}{c['tier']:<18}{n:>5}")
    fees = sorted(d["fee"] for d in doctors)
    langs = sorted({lang for d in doctors for lang in d["languages"]})
    print()
    print(f"fee range: Rs {fees[0]:.0f} - Rs {fees[-1]:.0f}   languages: {', '.join(langs)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a synthetic doctor directory.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the generated directory without writing to the database",
    )
    args = parser.parse_args()
    asyncio.run(seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
