# Captcha protocol

Self-hosted proof-of-work captcha, ALTCHA-style. No third-party vendor, no API
key, no external network call at verify time. Implementation:
`backend/app/core/captcha.py`; routes: `GET /api/v1/captcha/challenge`,
`POST /api/v1/captcha/verify`, both in `backend/app/api/v1/auth.py`.

## How it works

1. **Challenge.** The server generates a random 16-byte `salt` (hex) and a
   random integer `number` in `[0, CAPTCHA_DIFFICULTY)`, then computes
   `challenge = sha256(salt + str(number))`. It stores `challenge -> salt` in
   Redis with a TTL (`CAPTCHA_TTL_SECONDS`) and returns the challenge to the
   client -- **never the number**.
2. **Solve (client).** The client brute-forces `n` from `0` upward until
   `sha256(salt + str(n)) == challenge`, then base64-encodes
   `{"challenge", "salt", "number": n}` as JSON.
3. **Verify.** The client sends that base64 string as the `X-Captcha-Token`
   header on the protected request. The server decodes it, re-derives the
   hash, and does an atomic `GETDEL` on the Redis key: if the key is gone
   (never existed, expired, or already consumed) it's `CAPTCHA_INVALID`; if
   the stored salt or the recomputed hash doesn't match, also
   `CAPTCHA_INVALID`. `GETDEL` is atomic, so single-use holds even under a
   concurrent replay of the same token -- there's no separate "used" flag to
   race.

## Endpoints

### `GET /api/v1/captcha/challenge`

No auth required. Response:

```json
{
  "algorithm": "SHA-256",
  "challenge": "9f2c...",
  "salt": "a1b2c3...",
  "maxnumber": 50000
}
```

### `POST /api/v1/captcha/verify`

Header: `X-Captcha-Token: <base64 of {"challenge","salt","number"}>`.

- `200 {"status": "ok"}` on success (and the token is now consumed).
- `400 CAPTCHA_INVALID` -- malformed token, unknown/expired/already-used
  challenge, or a wrong solution.
- `400 CAPTCHA_REQUIRED` -- header missing entirely.

This endpoint is a standalone way to pre-verify a solve; the same
`X-Captcha-Token` header is also read directly by the `require_captcha`
dependency on every captcha-gated route below, so a client normally solves
once and sends the token straight to the real endpoint rather than calling
`/captcha/verify` first.

## Captcha-gated routes

`POST /auth/register`, `POST /auth/login`, `POST /files`,
`POST /documents/upload`, `POST /appointments`, `POST /approvals/*`.

## Error codes

| Code | When |
|---|---|
| `CAPTCHA_REQUIRED` | `X-Captcha-Token` header absent on a gated route |
| `CAPTCHA_INVALID` | malformed token, expired/unknown/already-used challenge, or wrong solution |

## JS solver (copy-paste)

```js
export async function solve({challenge, salt, maxnumber}) {
  const enc = new TextEncoder();
  for (let n = 0; n <= maxnumber; n++) {
    const h = await crypto.subtle.digest("SHA-256", enc.encode(salt + n));
    const hex = [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("");
    if (hex === challenge) return btoa(JSON.stringify({challenge, salt, number: n}));
  }
  throw new Error("captcha_unsolvable");
}
```

Usage:

```js
const challenge = await fetch("/api/v1/captcha/challenge").then(r => r.json());
const token = await solve(challenge);
await fetch("/api/v1/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Captcha-Token": token },
  body: JSON.stringify({ email, password }),
});
```
