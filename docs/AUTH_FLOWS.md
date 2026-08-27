# Authentication Flows

Sequence diagrams for the four core auth flows: login, captcha, refresh
rotation, and doctor approval-lock. See [`CAPTCHA.md`](CAPTCHA.md) for the
captcha algorithm itself and [`SECURITY.md`](SECURITY.md) (CP4) for the
threat model behind each control shown here.

## 1. Login (captcha-gated, uniform-timing)

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API (auth.py)
    participant R as Redis
    participant D as Postgres

    C->>A: GET /captcha/challenge
    A->>R: store {challenge, salt, expiry, used=false}
    A-->>C: {algorithm, challenge, salt, maxnumber}
    Note over C: brute-force salt+n until sha256 == challenge
    C->>A: POST /auth/login<br/>X-Captcha-Token, {email, password}
    A->>R: verify captcha (hash + single-use)
    R-->>A: ok, mark used=true
    A->>R: is_login_locked(email)?
    alt account locked (5 consecutive failures)
        A-->>C: 429 RATE_LIMITED (Retry-After)
    else not locked
        A->>D: SELECT user WHERE email
        Note over A: bcrypt-verify against the real hash,<br/>or a dummy hash if no such user<br/>(unknown-email and wrong-password<br/>cost the same wall-clock time)
        alt credentials invalid
            A->>R: record_login_failure(email)
            A-->>C: 401 AUTH_INVALID_CREDENTIALS
        else credentials valid
            A->>R: clear_login_failures(email)
            A->>A: issue_token_pair(user_id, role, ip, ua)
            A->>R: store refresh jti + session metadata
            A-->>C: 200 {access_token, refresh_token,<br/>Set-Cookie: refresh_token (HttpOnly)}
        end
    end
```

## 2. Captcha challenge/solve/verify

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API (captcha.py)
    participant R as Redis

    C->>A: GET /captcha/challenge
    A->>A: salt = random 16 bytes hex<br/>number = random int [0, CAPTCHA_DIFFICULTY)<br/>challenge = sha256(salt + str(number))
    A->>R: SET {challenge -> {salt, expiry, used:false}} EX CAPTCHA_TTL_SECONDS
    A-->>C: {algorithm:"SHA-256", challenge, salt, maxnumber}
    Note over C: for n in 0..maxnumber:<br/> if sha256(salt+str(n)) == challenge: found
    C->>A: request with X-Captcha-Token = base64({challenge, salt, number})
    A->>A: recompute sha256(salt + str(number))
    alt hash mismatch
        A-->>C: 400 CAPTCHA_INVALID
    else hash matches
        A->>R: GET challenge entry
        alt not found / expired / already used
            A-->>C: 400 CAPTCHA_INVALID
        else valid, unused
            A->>R: SET used=true (single-use, replay-proof)
            A-->>C: request proceeds
        end
    end
```

## 3. Refresh token rotation + reuse detection

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API (auth.py)
    participant R as Redis

    C->>A: POST /auth/refresh (cookie or body refresh_token)
    A->>A: decode_token, check typ == "refresh"
    A->>R: is_denylisted(jti)?
    alt jti already denylisted (stolen/replayed token)
        A->>R: revoke every jti in this token's family
        A-->>C: 401 AUTH_INVALID_CREDENTIALS<br/>(entire session lineage killed)
    else jti not denylisted
        A->>R: GET auth:refresh:active:{jti}
        alt not active
            A-->>C: 401 AUTH_INVALID_CREDENTIALS
        else active
            A->>R: revoke(jti) -> denylist + remove from active/session sets
            A->>A: issue new access + refresh (same family)
            A->>R: register new refresh: active key, family set,<br/>user session set, session metadata (ip/ua/issued_at)
            A-->>C: 200 {access_token, refresh_token,<br/>Set-Cookie: refresh_token}
        end
    end
```

## 4. Doctor approval + immutable lock

```mermaid
sequenceDiagram
    participant Doc as Doctor (client)
    participant A as API (approvals.py)
    participant D as Postgres
    participant R as Redis
    participant N as notify() (P3.2)

    Doc->>A: POST /approvals/lab-order/{id}<br/>X-Captcha-Token, Bearer (role=doctor)
    A->>A: require_role("doctor") + require_captcha
    A->>D: SELECT lab_order WHERE id
    alt already locked
        A->>D: INSERT audit_log (rejected attempt)
        A-->>Doc: 409 LOCKED
    else not locked
        A->>D: resolve doctor_id from caller,<br/>SELECT visit, check visit.doctor_id == doctor_id
        alt not the assigned doctor
            A-->>Doc: 403 AUTH_FORBIDDEN
        else assigned
            A->>A: content_hash = sha256(canonical_json(items))
            A->>D: UPDATE lab_order SET approved_by, approved_at,<br/>content_hash, locked=true, status="approved"<br/>(BEFORE UPDATE trigger also blocks any future<br/>write once locked=true, even outside this router)
            A->>D: INSERT audit_log (approval)
            A->>R: PUBLISH approval.locked {entity, id, content_hash}
            A->>N: notify(patient_user_id, "lab_order_approved", {...})
            A-->>Doc: 200 {locked:true, approved_by, approved_at, content_hash}
        end
    end
```
