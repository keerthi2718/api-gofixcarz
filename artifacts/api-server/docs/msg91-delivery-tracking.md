# MSG91 OTP delivery diagnostics

The sender, route, DLT ID and message text are unchanged. Submission acceptance
is **not** handset delivery. Auth responses now include `sms_request_id` and
`sms_delivery_status: "pending"` alongside the existing mobile/country fields.
This initial status means submission accepted, not a fresh delivery report.

## Setup (no live SMS required)

1. Apply `alembic upgrade head` from `artifacts/api-server` to the intended
   database. Do not point development migrations at production unintentionally.
2. In Replit Secrets set two independent random values, each at least 32
   characters: `MSG91_WEBHOOK_TOKEN` and `MSG91_DIAGNOSTICS_TOKEN`.
   Never reuse the MSG91 API auth key or session/JWT secret.
3. In MSG91 → SMS → Webhook (New), create **On Report Received** for all final
   statuses, including delivered, failed and rejected. **On Request Received**
   does not confirm delivery. Configure a publicly reachable HTTPS URL ending
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
   Legacy form-encoded/array webhooks are deliberately unsupported; use this
   configured Webhook (New) contract.
5. For operations-only troubleshooting, GET
   `/api/v1/auth/msg91/delivery-status/{sms_request_id}` with
   `X-SMS-Diagnostics-Token`. Keep this credential on trusted server-side
   tooling, never in a mobile/frontend bundle or query string.

Without the relevant token, the endpoint fails closed with 503; an incorrect
token returns 401. Authentication uses constant-time comparison. This is a
custom shared-header authentication scheme supported by MSG91, not a claimed
provider HMAC signature. Use HTTPS and rotate both secrets when compromised.

## Interpreting results

- **pending:** accepted; no final report has been observed. MSG91 does not send
  pending delivery webhooks. Missing/misconfigured callbacks also leave pending,
  so this does not establish a carrier failure or delivery.
- **delivered:** MSG91/operator reported delivery. This does not prove that the
  user saw the SMS.
- **failed:** operator failure, NDNC, rejected, blocked number, country blocked,
  or a specifically allowlisted DLT template/sender failure category. Arbitrary
  failure prose is discarded to prevent personal data and OTP exposure. Check
  the matching request ID in MSG91's private report console for full details.

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
The legacy sender uses GET parameters; HTTPX INFO URL logging is suppressed.
Avoid enabling HTTP wire/debug logging or forwarding tokens into proxy logs.
Callbacks have an 8 KiB body limit and validate IDs and documented numeric
statuses with generic, non-echoing errors. DB failures are not acknowledged as
successful updates, allowing reports to be retried.

## Verification and remaining external checks

Run `pytest tests/unit/test_msg91.py tests/unit/test_sms_delivery.py tests/unit/test_sms_delivery_retention.py`.
Submission and HTTP callback tests are mocked; the correlation test uses an
isolated temporary PostgreSQL table. None sends SMS. Do not run the existing
live integration sign-up fixtures to check delivery: they can send real SMS.

No MSG91 dashboard changes or live SMS were performed. After webhook setup,
use an explicitly confirmed test target and inspect its actual report before
claiming a root cause or altering the approved DLT sender/template.

## Sources consulted

- [MSG91: SMS Delivery Reports via Webhook (New)](https://msg91.com/help/webhook-new/how-to-receive-sms-delivery-reports-via-webhook-new)
  — requestId, numeric statuses, custom headers, pending-report limitations.
- [MSG91: What are Webhooks?](https://msg91.com/help/webhooks/what-are-webhooks-how-does-it-work)
- [MSG91: Custom Metadata Parameters](https://msg91.com/help/text-sms/custom-metadata-parameters-for-tracking-api-requests)

Documentation consulted on 2026-10-04. No speculative changes to approved SMS
content or switches to a different MSG91 sending API were made.