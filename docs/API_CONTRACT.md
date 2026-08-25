# API Contract

Version: v1 (draft — additive only once tagged `## FROZEN` at CP4).

## Locale

The API is built for Indian deployment. Consumers should assume:

| Concern | Convention |
|---|---|
| Currency | INR. `fee`, `mrp_inr` and any price field are rupees. |
| Timezone | `Asia/Kolkata`. All timestamps are serialised as UTC ISO-8601; render in IST. |
| Phone | `+91` E.164. |
| Address | `address` plus `state` (Indian state or union territory) and `pin_code` (6 digits). |
| Patient identity | Optional `abha_id` — Ayushman Bharat Health Account, 14 digits. |
| Doctor identity | Optional `nmc_reg_no` — National Medical Commission registration. |
| Triage | `severity_esi` (1–5) is the machine value; `triage_colour` (`red`/`yellow`/`green`) is the MoHFW/AIIMS casualty code derived from it — ESI 1–2 red, 3 yellow, 4–5 green. |
| Emergency copy | Emergency guidance cites **112**, ambulance **108**. Never 911. |
| Medicines | `nlem_listed` marks India's National List of Essential Medicines; `jan_aushadhi_available` marks a generic stocked at Jan Aushadhi Kendras. |
| Data protection | Consent and retention follow the DPDP Act 2023, not HIPAA. |

## Error envelope

Every non-2xx response follows:

```json
{"error":{"code":"AUTH_INVALID_CREDENTIALS","message":"human readable","request_id":"uuid","details":{}}}
```

Codes: `AUTH_INVALID_CREDENTIALS, AUTH_TOKEN_EXPIRED, AUTH_FORBIDDEN, CAPTCHA_REQUIRED, CAPTCHA_INVALID, VALIDATION_FAILED, NOT_FOUND, LOCKED, CONFLICT, RATE_LIMITED, UPSTREAM_UNAVAILABLE, MODEL_UNAVAILABLE, INTERNAL, NOT_IMPLEMENTED`

`NOT_IMPLEMENTED` (HTTP 501) marks endpoints whose owner has not shipped a real implementation yet; it disappears from the contract as each checkpoint lands.

## Endpoint table

| Method | Path | Owner | Auth | Captcha |
|---|---|---|---|---|
| POST | `/api/v1/auth/register` | P | – | ✅ |
| POST | `/api/v1/auth/login` | P | – | ✅ |
| POST | `/api/v1/auth/refresh` | P | refresh | – |
| POST | `/api/v1/auth/logout` | P | any | – |
| GET | `/api/v1/auth/me` | P | any | – |
| GET | `/api/v1/captcha/challenge` | P | – | – |
| POST | `/api/v1/captcha/verify` | P | – | – |
| GET/POST/PATCH | `/api/v1/patients[/{id}]` | P | self/doctor/staff | – |
| GET | `/api/v1/patients/{id}/consent` | P | self/doctor | – |
| POST | `/api/v1/files` | P | any | ✅ |
| GET | `/api/v1/files/{id}` | P | owner/doctor | – |
| POST | `/api/v1/approvals/lab-order/{id}` | P | doctor | ✅ |
| POST | `/api/v1/approvals/prescription/{id}` | P | doctor | ✅ |
| GET | `/api/v1/audit` | P | doctor/admin | – |
| GET/POST | `/api/v1/notify[/{id}/read]` | P | any | – |
| GET | `/api/v1/exports/{type}/{id}.pdf` | P | owner/doctor | – |
| GET/POST/PATCH | `/api/v1/doctors-profile` | P | admin | – |
| POST | `/api/v1/triage/session` | A | patient | – |
| POST | `/api/v1/triage/{id}/message` | A | patient | – |
| GET | `/api/v1/triage/{id}/result` | A | patient/doctor | – |
| POST | `/api/v1/chat/patient` (SSE) | A | patient | – |
| POST | `/api/v1/copilot/brief` | A | doctor | – |
| GET | `/api/v1/kg/patient/{id}/timeline` | A | self/doctor | – |
| GET | `/api/v1/kg/patient/{id}/context` | A | doctor | – |
| GET | `/api/v1/visits/{id}` | A | self/doctor | – |
| POST | `/api/v1/visits/{id}/advance` | A | doctor/staff | – |
| WS | `/ws/visit/{id}`, `/ws/queue/{clinic_id}` | A | any/staff | – |
| POST | `/api/v1/documents/upload` | V | any | ✅ |
| GET | `/api/v1/documents/{id}` | V | owner/doctor | – |
| POST | `/api/v1/ml/entities` | V | doctor/internal | – |
| POST | `/api/v1/ml/interactions` | V | doctor/internal | – |
| POST | `/api/v1/ml/labs/flag` | V | doctor/internal | – |
| POST | `/api/v1/ml/summary` | V | doctor | – |
| POST | `/api/v1/ml/medications/suggest` | V | doctor | – |
| GET | `/api/v1/doctors` | N | any | – |
| POST/GET/PATCH | `/api/v1/appointments[/{id}]` | N | patient/staff | ✅ POST |
| POST | `/api/v1/appointments/simulate` | N | any | – |
| GET | `/api/v1/queue/{clinic_id}` | N | doctor/staff | – |
| POST | `/api/v1/queue/{id}/next` | N | doctor/staff | – |
| POST | `/api/v1/queue/{id}/escalate` | N | doctor/staff | – |
| POST | `/api/v1/lab-orders/recommend` | N | doctor/staff | – |
| GET | `/api/v1/lab-orders/{id}` | N | owner/doctor | – |
| GET | `/api/v1/medications/generic` | N | any | – |
| GET | `/health` | A | – | – |

`/api/v1/medications/generic` maps an Indian brand name to its ingredient/generic and returns NLEM listing, Jan Aushadhi availability and indicative ₹ MRP.

All routes above are live in the OpenAPI schema as of A1.2, returning `NOT_IMPLEMENTED` until their owning checkpoint lands the real handler. `/health` and the triage/copilot/kg/visits scaffolding are Ashwin's own routes and fill in across the CP1–CP3 build sequence.

## Core schemas

See `backend/app/schemas/` — `common.py`, `auth.py`, `patient.py`, `triage.py`, `document.py`, `ml.py`, `scheduling.py`, `copilot.py`, `visit.py`. Field shapes match this contract exactly; `frontend/src/lib/types.ts` is generated from `openapi.json` via `make openapi` and must never be hand-edited.

## Interfaces (internal, not HTTP)

```python
# app/llm/gateway.py
async def complete(prompt: str, *, system: str | None = None, max_tokens: int = 1024,
                   temperature: float = 0.2) -> str: ...
async def stream(prompt: str, *, system: str | None = None, max_tokens: int = 1024,
                 temperature: float = 0.2) -> AsyncIterator[str]: ...
async def json_complete(prompt: str, *, schema: type[BaseModel], system: str | None = None,
                        retries: int = 2) -> BaseModel: ...

# app/rag/store.py
class VectorStore:
    def upsert(self, collection: str, chunks: list[Chunk]) -> None: ...
    def query(self, collection: str, text: str, k: int = 8, where: dict | None = None) -> list[Hit]: ...
    def count(self, collection: str) -> int: ...
# collections: "guidelines" | "clinical" | f"patient_{patient_id}"

# app/rag/retriever.py
async def hybrid(collection: str, query: str, k: int = 8, where: dict | None = None) -> list[Hit]: ...

# app/kg/queries.py
async def patient_context(patient_id: UUID) -> dict
async def patient_timeline(patient_id: UUID) -> list[dict]
```

These land in A1.3 and A2.2; stub modules do not yet exist to avoid dead code ahead of their checkpoint.
