# Demo accounts

Seeded by `python scripts/seed_users.py` (idempotent -- safe to re-run).
Every account uses the password **`Demo@12345`** (the spec's literal
`Demo@1234` is 9 characters, one short of this checkpoint's own >=10-char
password policy in `app/core/security.py`; bumped by one digit so every
account can actually log in -- see docs/DECISIONS.md).

All emails are `@demo.example`. This overlaps with `scripts/seed.py`
(Ashwin's), which seeds the same doctor/patient UUIDs under `@doctorcopilot.dev`
with password `demo-password-123` -- whichever script ran last wins on those
fields. See docs/DECISIONS.md for why the two weren't consolidated.

## Admins

| Email | Fixed user id | Name |
|---|---|---|
| admin1@demo.example | `00000000-0000-0000-0000-000000000601` | Ritu Agarwal |
| admin2@demo.example | `00000000-0000-0000-0000-000000000602` | Manoj Krishnan |

## Staff

| Email | Fixed user id | Name |
|---|---|---|
| staff1@demo.example | `00000000-0000-0000-0000-000000000603` | Neha Kulkarni |
| staff2@demo.example | `00000000-0000-0000-0000-000000000604` | Suresh Pillai |

## Doctors

| Email | Fixed user id | Name | Specialty | Clinic |
|---|---|---|---|---|
| doctor1@demo.example | `...000401` | Dr. Ananya Rao | General medicine | Yamuna Nagar PHC (Delhi) |
| doctor2@demo.example | `...000402` | Dr. Vikram Shah | Cardiology | Shivaji Nagar CHC (Maharashtra) |
| doctor3@demo.example | `...000403` | Dr. Meera Iyer | Paediatrics | Jayanagar Clinic (Karnataka) |
| doctor4@demo.example | `...000404` | Dr. Rohan Kapoor | Dermatology | Yamuna Nagar PHC (Delhi) |
| doctor5@demo.example | `...000405` | Dr. Priya Nair | Orthopaedics | Shivaji Nagar CHC (Maharashtra) |
| doctor6@demo.example | `...000406` | Dr. Arjun Malhotra | Neurology | Jayanagar Clinic (Karnataka) |

Each doctor carries a placeholder NMC registration number
(`NMC-{year}-{number}`) and consultation fee in ₹300-₹900.

## Patients

12 patients, `patient1@demo.example` .. `patient12@demo.example`, fixed user ids
`00000000-0000-0000-0000-0000000005{01..12}`, patient record ids
`00000000-0000-0000-0000-0000000001{01..12}`. Addresses cycle across Delhi,
Maharashtra and Karnataka with real PIN codes; each carries a placeholder
14-digit ABHA number in `xx-xxxx-xxxx-xxxx` format.

## Clinics

| Name | State | PIN | Emergency-capable |
|---|---|---|---|
| Yamuna Nagar Primary Health Centre | Delhi | 110002 | Yes |
| Shivaji Nagar Community Health Centre | Maharashtra | 411005 | No |
| Jayanagar Multispecialty Clinic | Karnataka | 560041 | Yes |

## Reset demo state

```bash
python scripts/seed_users.py
```

Re-running is idempotent: existing rows are updated in place by their fixed
id, nothing is duplicated.
