# Customer app APIs — first implemented phase

Historical first-phase scope. See `customer-app-workflows.md` for the expanded
implementation and the explicitly pending Razorpay checkout endpoint.

Base path: `/api/v1/customer-app`. Interactive contracts: `/api/docs`.
The customer approval PDF remains a draft inventory, not a claim that all 62
operations are implemented.

## Approved scope

- Mobile OTP only; email and the four conditional password endpoints are excluded.
- OTP expiry 300 seconds, resend cooldown 30 seconds, five attempts per chain.
- Access tokens expire after 900 seconds.
- Refresh credentials rotate on every use. Sessions expire 30 days after the
  original OTP login; rotation does not extend this absolute deadline.
- New accounts are created only after registration OTP verification.
- No automatic linking to imported customer accounts or garage contact/vehicle
  records. Garage and admin authentication remain unchanged.

The existing MSG91 sender/template is preserved. This implementation validates
Indian mobile numbers as `+91` plus ten digits beginning with 6–9, matching the
currently configured provider. Other countries require a separate delivery
configuration review. SMS provider acceptance is **not** confirmation of delivery.
Provider rejection returns `503 OTP_DELIVERY_UNAVAILABLE`; there is no fake-success
fallback and no response includes an OTP.

## Implemented operations

| Draft ID | Method | Path |
| --- | --- | --- |
| API-01 | POST | `/auth/register` |
| API-02 | POST | `/auth/otp/send` |
| API-03 | POST | `/auth/otp/resend` |
| API-04 | POST | `/auth/otp/verify` |
| API-05 | POST | `/auth/refresh` |
| API-06 | GET | `/auth/session` |
| API-07 | POST | `/auth/logout` |
| API-12 | GET | `/me` |
| API-13 | PATCH | `/me` |
| API-14 | POST | `/me/contact-change` |
| API-15 | POST | `/me/contact-change/verify` |

These 11 operations are the first phase, not the whole customer backend.
Contact change is mobile-only. Profile photo operations API-16/17 are deferred
until customer-owned secure attachment storage is implemented. Vehicle,
booking, tracking, billing/payment, messaging, notifications, review and support
operations remain unimplemented and need their remaining product approvals.
The public browsing APIs excluded from the PDF are also excluded here.

## Requests and responses

Use JSON and the existing envelope:

```json
{
  "success": true,
  "message": "Success",
  "data": {},
  "errors": [],
  "status_code": 200
}
```

Authentication/profile responses, including errors, use `Cache-Control: no-store`.
Protected calls require `Authorization: Bearer <customer_access_token>`.
Do not put tokens or OTPs in URLs or application logs.
An optional stable `X-Device-ID` is an additional rate-limit signal, not an
authentication credential; clients can spoof it, so IP/mobile limits remain
mandatory.

### Register

`POST /auth/register` returns 202 on SMS submission acceptance:

```json
{
  "name": "Demo Customer",
  "channel": "mobile",
  "identifier": "+919000000001",
  "terms_version": "2026-10",
  "terms_accepted": true
}
```

```json
{
  "challenge_id": "<uuid>",
  "purpose": "REGISTER",
  "expires_in_seconds": 300,
  "resend_after_seconds": 30
}
```

`CUSTOMER_TERMS_VERSION` sets the currently accepted version (development default
`2026-10`). Publish/review actual terms before production rollout; this setting
does not publish legal content. Registration records consent version/time.

### Login / resend / verify

`POST /auth/otp/send`:

```json
{"channel": "mobile", "identifier": "+919000000001", "purpose": "LOGIN"}
```

Unknown/inactive identifiers receive the same submission response but cannot
establish sessions, even with the submitted code. This flow never creates an
account. All send paths share mobile abuse limits.

`POST /auth/otp/resend`:

```json
{"challenge_id": "<uuid>"}
```

Resend returns a **new** challenge ID and invalidates the previous challenge.
Resending or restarting while a challenge chain is live does not reset its
verification attempt count. A contact-change resend additionally requires the
same still-valid customer session that initiated it.

`POST /auth/otp/verify`:

```json
{"challenge_id": "<uuid>", "otp": "012345", "device_name": "Customer Phone"}
```

The OTP is a six-character string, including leading zeroes. The response data
contains `customer`, `access_token`, `refresh_token`, `token_type: "Bearer"`,
`expires_in_seconds: 900`, and `session_id`. Codes are single-use and bound to
their challenge, phone and purpose. Contact-change codes cannot establish login.

### Refresh / session / logout

`POST /auth/refresh`:

```json
{"refresh_token": "<current_refresh_token>"}
```

Returns the same session ID with a new token pair. Persist the new refresh
credential securely and discard the old one. Reuse of any older refresh
credential revokes that session and all successor credentials, including
already-issued access tokens on their next protected request. Clients must
serialize refresh calls: parallel refreshes using one credential count as reuse.

`GET /auth/session` returns `session_id`, `customer_id`, `authenticated` and
`expires_at` (the access-token expiry).

`POST /auth/logout` has no body. It revokes the current session. Repeat logout
with the same otherwise-valid access token is idempotent; profile/session and
refresh requests are denied after logout.

### Profile and mobile change

`GET /me` returns verified mobile, name, address, and customer ID. `email` and
`photo` are null in this phase. `email_verified` is false.

`PATCH /me`:

```json
{
  "name": "Demo Customer",
  "address": {
    "line1": "Example Street",
    "city": "Hyderabad",
    "state": "Telangana",
    "postal_code": "500001",
    "country": "IN"
  }
}
```

At least one field is required. Omitted fields stay unchanged; `address: null`
clears the address. A supplied address requires line1, city, postal code and
two-letter uppercase country. Name cannot be blank or null. Unknown fields,
contact fields, ownership, roles and verified flags are rejected.

`POST /me/contact-change`:

```json
{"channel": "mobile", "new_identifier": "+919000000002"}
```

Requires OTP authentication within the last 15 minutes. This conservative
recent-authentication rule applies to initiation, resend and completion.
The original phone remains unchanged until successful verification.

`POST /me/contact-change/verify`:

```json
{"challenge_id": "<uuid>", "otp": "012345"}
```

Only the initiating customer/session can complete it. Phone uniqueness is
rechecked atomically. Other sessions and pending login/contact challenges are
revoked; the recently authenticated initiating session remains active.

## Abuse protection and storage

PostgreSQL counters survive process restarts and error rollbacks. Per fixed
15-minute window, sends allow 5/mobile, 20/IP and 10/device (when supplied).
Verification/refresh allow 60/IP and 30/device, plus five OTP guesses per
challenge chain. Send limits also count rejected cooldown/duplicate attempts.
The IP limit can affect people sharing an address; review trusted proxy
forwarding/traffic requirements before production.

OTPs use cryptographic randomness and are stored only as secret-keyed hashes.
Refresh credentials are stored only as hashes. Purpose and customer audience
prevent garage/admin credentials from authorizing customer requests and vice
versa. Account status from the admin customer-account model is authoritative:
non-ACTIVE accounts cannot authenticate or use existing sessions.

Daily cleanup removes expired challenges/rate counters after a 24-hour grace
period, and expired sessions/refresh ledgers after the same grace period.
Used refresh hashes remain for the whole session lifetime to detect replay.
Cleanup never deletes customer identity/profile records.

## Development verification and rollout

Migration `0015_customer_auth` creates only additive customer-auth tables.
It was applied to the internal **development** database. Production database
changes, publishing, terms approval and live SMS delivery verification are
**not** included or claimed.

Run API regression checks:

```sh
cd artifacts/api-server
python -m pytest tests/integration/test_customer_app.py -q
```

Tests use real development PostgreSQL and mocked SMS submission; they never
send real messages. Test accounts are rolled back and uniquely keyed durable
rate counters are removed.

Sync implemented OpenAPI contracts for workspace clients after changes:

```sh
cd artifacts/api-server
python scripts/export_customer_openapi.py
cd ../..
pnpm --filter @workspace/api-spec run codegen
```

The exporter includes implemented routes only, never the remaining draft APIs.
Production delivery-only migration approval remains bounded to the original
delivery schema; it does **not** authorize customer-schema upgrades.
