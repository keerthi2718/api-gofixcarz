# MSG91 OTP delivery diagnostics

OTP submission uses MSG91's v5 OTP API with the user's GoFixAuto template:
`6aabb705139475b847069b62`. Its approved message is
`Your GoFixAuto platform account activation OTP is ##OTP##`.
MSG91 applies the template's configured sender; the backend does not override
it with a legacy SMS sender or numeric DLT ID. The backend passes its generated
OTP and expiry to MSG91 so local verification remains unchanged.
Submission acceptance is **not** handset delivery. Auth responses include `sms_request_id` and
`sms_delivery_status: "pending"` alongside the existing mobile/country fields.
This initial status means submission accepted, not a fresh delivery report.

## Setup (no live SMS required)

MSG91 documents a dedicated **SendOTP API** report webhook. It uses the same
flat `requestId`, numeric `status`, and `failureReason` fields as the existing
parser and supports custom authentication headers. No payload-parser or auth
scheme change is required. An SMS-product webhook alone is not evidence that
OTP reports are configured.

1. Ensure the delivery migrations are applied to the intended database; see
   **Production publishing safety** below. Do not point development migrations
   at production unintentionally.
2. In Replit Secrets set two independent random values, each at least 32
   characters: `MSG91_WEBHOOK_TOKEN` and `MSG91_DIAGNOSTICS_TOKEN`.
   Never reuse the MSG91 API auth key or session/JWT secret.
3. In MSG91 → **OTP → Webhook → Create Webhook**, select **OTP** and
   **On Report Received**. Configure a publicly reachable HTTPS URL ending
   in `/api/v1/auth/msg91/delivery-report`, using the actual API mount path.
4. Configure the custom header `X-MSG91-Webhook-Token` with the webhook secret.
   Configure `Content-Type: application/json` and the following flat body:

   ```json
   {
     "requestId": "{{requestId}}",
     "status": "{{status}}",
     "failureReason": "{{failureReason}}"
   }
   ```

   Do not include mobile, OTP, message text, sender credentials or user details.
   MSG91's OTP documentation specifies `status: "1"` (delivered) or `"2"`
   (failed); integer 1/2 are accepted too. The sender persists the SendOTP
   response's `request_id`, and the callback's `requestId` is matched to that
   exact ID. Do not substitute `CRQID`, `flowID` (template ID), `verified`, or
   a mobile number. The documented example's 22-character ID is supported.
   Arbitrary extra fields are discarded, but omit them at the provider too.
   Legacy form-encoded/array webhooks are deliberately unsupported.
5. For operations-only troubleshooting, GET
   `/api/v1/auth/msg91/delivery-status/{sms_request_id}` with
   `X-SMS-Diagnostics-Token`. Keep this credential on trusted server-side
   tooling, never in a mobile/frontend bundle or query string.

Without the relevant token, the endpoint fails closed with 503; an incorrect
token returns 401. Authentication uses constant-time comparison. This is a
custom shared-header authentication scheme supported by MSG91, not a claimed
provider HMAC signature or independently signed proof. Use HTTPS and rotate
both secrets when compromised.

## Production publishing safety

The delivery schema is in the existing linear Alembic chain:
`0007_garage_logo_url` → `0008_sms_delivery` →
`0009_sms_delivery_retention`. The first adds the redacted diagnostics table;
the second adds its retention index. These upgrades do not rewrite or delete
customer, user, or OTP data. Scheduled cleanup still deletes expired diagnostics
as described below.

The API artifact's production run command invokes
`python scripts/production_start.py` before Uvicorn. The script checks the
database revision and **refuses to serve** if delivery migrations are missing.
Build does not migrate a database. The development workflow remains unchanged.

- Default: read-only revision check; no schema changes. A database already at
  `0009_sms_delivery_retention` starts normally.
- Only after approval to migrate the intended production database, set
  `APPLY_DELIVERY_MIGRATIONS=1` in the production environment for publishing.
  This explicitly authorizes just the delivery upgrades from revision 0007 or
  0008 to 0009. Confirm the database target and obtain a backup first.
- The approved upgrade and revision verification run in one transaction with
  a PostgreSQL advisory lock to serialize concurrently starting instances.
  Failure rolls back and prevents Uvicorn from starting. Subsequent starts at
  0009 are no-ops; remove the opt-in flag after successful publishing.
- Empty, older, branched, or unknown database revisions fail closed, even with
  approval set. A changed code migration head also requires review; this flag
  never authorizes unrelated or future migrations. Do not use `alembic stamp`
  to bypass missing schema.
- If using a manually configured publishing command instead of the artifact,
  it must invoke the same production script. A direct Uvicorn command bypasses
  the guard. The legacy `.replit` publishing command is configured to use it too.

Only configuration, migration source, offline SQL, and mocked startup behavior
were checked for this change. Production credentials/data were not read,
no migrations were run against production, and nothing was published.

## Interpreting results

- **pending:** accepted; no final report has been observed. The OTP report guide
  documents only final statuses 1/2; the SMS guide explicitly excludes pending
  callbacks. Missing/misconfigured callbacks also leave pending, so elapsed
  time alone does not establish a carrier failure or delivery.
- **delivered:** MSG91/operator reported delivery. This does not prove that the
  user saw the SMS.
- **failed:** OTP status 2 maps to the existing generic `operator_failure`
  category unless its reason exactly matches an allowlisted DLT failure.
  This category is not a confirmed carrier root cause: the provider may report
  other failure reasons. Arbitrary failure prose is discarded to prevent
  personal data and OTP exposure. Additional existing SMS statuses (NDNC,
  rejected, blocked number, country blocked) remain accepted for backward
  compatibility, but are not promised by the OTP report guide. Check the
  matching request ID in MSG91's private OTP logs for full details.

Accepted submission IDs are persisted. Callback-only IDs are temporarily stored
without phone/user information to handle callbacks racing ahead of submission
commit; diagnostics hide them until a matching submission is registered.
Atomic PostgreSQL upserts make duplicate callbacks no-ops. Delivered takes
precedence over failed, and pending cannot overwrite either terminal status.
Timestamps record local acceptance/report receipt, not untrusted provider times.

## Retention and cleanup

The operations troubleshooting window is **30 days** for every status, including
pending. This deliberately leaves ample time for delayed final reports without
retaining diagnostics indefinitely; it is an application policy, not a claim
about MSG91's maximum delivery-report delay.

- Accepted submissions expire 30 days after local `accepted_at`.
- Callback-only rows expire 30 days after local `created_at`, including IDs that
  never match an accepted submission. A later matching acceptance starts its own
  full 30-day window and preserves any early report.
- Only timestamps strictly older than the cutoff are deleted. Reports and
  duplicate retries never extend retention, even when a status advances.
- Cleanup runs at API startup and every 24 hours using the existing scheduler.
  While the API is running successfully, deletion can lag expiry by up to one
  interval (about 31 days total). Downtime or cleanup failure postpones deletion;
  startup catches up. Each run commits atomically and logs the deleted count;
  failures are logged and the next scheduled run retries.
- Apply `alembic upgrade head` before starting the updated API. The migration
  adds an index on `coalesce(accepted_at, created_at)` for the cleanup predicate.
  It does not delete rows itself. The first cleanup may remove historical rows.

Expired accepted IDs return 404 from diagnostics after cleanup, not an inferred
delivery failure. A callback arriving after its accepted row was deleted becomes
a new callback-only row, hidden from diagnostics and subject to the same bounded
retention. It cannot restore the old acceptance or its troubleshooting history.
For older incidents, use MSG91's private console according to its own retention
policy. Cleanup affects delivery diagnostics only, not OTP verification or users.

Never log raw callback bodies, headers, provider error text or send URLs.
The OTP sender uses POST with recipient/OTP query parameters and the API key
in a header; HTTPX INFO URL logging is suppressed.
Avoid enabling HTTP wire/debug logging or forwarding tokens into proxy logs.
Callbacks have an 8 KiB body limit and validate IDs and documented numeric
statuses with generic, non-echoing errors. DB failures are not acknowledged as
successful updates, allowing reports to be retried.

## Verification and remaining external checks

Run these fully mocked checks without a database connection or live SMS:

```sh
pytest tests/unit/test_msg91.py tests/unit/test_sms_delivery.py \
  tests/unit/test_delivery_migrations.py -k 'not database_correlation'
```

Use dummy settings for isolated tests; never print or retrieve production
credentials. Additional correlation/retention tests use isolated temporary
PostgreSQL tables and must only run with an explicitly selected test/development
database. None of these tests sends SMS. Do not run the existing
live integration sign-up fixtures to check delivery: they can send real SMS.

No MSG91 dashboard changes or live SMS were performed. Documentation and mocks
verify compatibility, not the account's current webhook settings. After setup,
use an explicitly confirmed test target and compare the SendOTP response
`request_id` with the actual callback `requestId`. Inspect MSG91's **Webhook
Logs** to confirm the OTP service, callback response and request/response
snapshot if reports are missing; handle those private logs securely. A webhook
delivery error is not an SMS delivery error. Do not claim a root cause or
alter the approved DLT sender/template without the matching provider evidence.

## Sources consulted

- [MSG91: How to Receive SendOTP API Delivery Reports via Webhook](https://msg91.com/help/webhook-new/how-to-receive-otp-delivery-reports-via-webhook)
  — OTP setup, requestId, statuses 1/2, failureReason and custom headers.
- [MSG91: SendOTP API](https://docs.msg91.com/otp/sendotp)
  — v5 OTP endpoint and authkey header. Dynamic sample-response content is not
  available in the text documentation; real account correlation remains an
  explicit external check, not an assumption that mocks prove delivery.
- [MSG91: SMS Delivery Reports via Webhook (New)](https://msg91.com/help/webhook-new/how-to-receive-sms-delivery-reports-via-webhook-new)
  — requestId, numeric statuses, custom headers, pending-report limitations.
- [MSG91: What are Webhooks?](https://msg91.com/help/webhooks/what-are-webhooks-how-does-it-work)
- [MSG91: Custom Metadata Parameters](https://msg91.com/help/text-sms/custom-metadata-parameters-for-tracking-api-requests)

Documentation consulted on 2026-10-04. No speculative changes to approved SMS
content or switches to a different MSG91 sending API were made.