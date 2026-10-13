# GoFixCarz admin API — development implementation

## Scope and readiness

All **62 business operations** from the requirements PDF are registered under
`/api/v1/admin`. The **four private authentication operations** are implemented
but intentionally excluded from this document and public OpenAPI.

This is a development implementation using the approved conservative rules,
not production policy sign-off. Development migrations were applied only to
the internal development database. No production migrations or publishing
were performed.

Interactive business contracts are available in `/api/docs`; the machine-readable
schema is `/api/openapi.json`. Responses use the existing `APIResponse` envelope.
Use a dedicated administrative bearer session; garage-owner credentials cannot
access the administrative API.

## Operation coverage

| PDF operations | Implemented group |
| --- | --- |
| ADM-01–04 | Private password verification, TOTP enrollment/proof, rotating refresh, logout |
| ADM-05–10 | Identity, authorized menus, permission catalogue, fixed roles, staff listing, role/scope assignment |
| ADM-11–12 | Dashboard and analytics, legacy financial meanings preserved, stored snapshot support |
| ADM-13–16 | Owner summaries/details and garage lists/details, city/status/verification and owner rating filters |
| ADM-17–19 | Versioned operational and verification changes, persisted review inspection |
| ADM-20–23 | Actual customer-account reads, AND-combined risk filters, vehicles and reviews |
| ADM-24–26 | Bookings, recorded decisions/history, exception grouping using recorded transition timestamps |
| ADM-27–31 | Jobs, recorded timelines, current-state delays, deterministic live delay alerts |
| ADM-32–41 | Financial summaries/trends, invoices, payment attempts, payments, refunds and disputes |
| ADM-42–48 | In-app notification inspection, external delivery read models, frozen announcement previews, idempotent send, deliveries |
| ADM-49–55 | Support lists/details, assignment, priority, chronological messages, deduplicated replies and lifecycle transitions |
| ADM-56–59 | Owner rankings, reconciled totals, weighted completion averages, per-owner breakdowns and trends |
| ADM-60–62 | Queued exports, protected status polling and CSV/XLSX downloads |
| ADM-63–66 | Audit reads, redaction, unified stored-source activity and service funnels |

“Implemented” means routes, persistence and server-side behavior exist. It does
**not** mean an external payment gateway, customer application, or messaging
provider is connected, or that every proposed extension has a source already.

## Authorization and privacy

- Dedicated admin passwords and mandatory TOTP are the normal development
  policy. Seeds are encrypted, codes cannot be reused, and challenges expire
  after five minutes and are bound to credential version.
- Access sessions last 15 minutes. Refresh families have a seven-day absolute
  lifetime, rotate on use, and are revoked after replay. Logout invalidates the
  current session. MFA failures and password failures have bounded retries.
- Privileged changes require MFA verified within five minutes; re-authenticate
  through the private flow for a fresh proof.
- Approved development roles are `role_ceo`, `role_operations`, `role_finance`
  and `role_support`. Fixed role definitions are visible through `/roles`.
- Only a platform-scoped security administrator can assign roles. Self
  role/scope changes are forbidden. CEO assignments require platform scope.
  Role/scope changes invalidate the recipient's existing sessions.
- Scope is enforced in ORM reads, aggregate queries and eager relationships,
  not just menus. Garage-scoped staff see only linked customer accounts and
  records in their permitted garages. Out-of-scope details return 404.
- Monetary fields are null with `restricted_fields` metadata when the
  administrator lacks `finance.read`; financial endpoints themselves require
  that permission. Restricted financial activity is not exposed.
- Secrets, credentials and token-shaped audit fields are redacted. Administrative
  JSON responses and downloads use `Cache-Control: no-store`.
- `ALLOW_LEGACY_ADMIN_TOKENS` defaults to false. Its true setting is an explicit
  compatibility escape hatch, used only by regression fixtures; it is not a
  recommended deployment configuration.

## Garage controls

Status and verification are independent. Existing garages start `ACTIVE` and
`UNVERIFIED` without any invented document approval. Both changes require a
reason and `expected_version`. A stale version returns 409.

Example status request:

```json
{
  "operational_status": "SUSPENDED",
  "reason": "Partner quality review",
  "expected_version": 1
}
```

Suspension prevents manual new job creation and new booking acceptance.
Existing jobs remain readable and can progress. Work accepted before suspension
may still be converted to a job. Verification never lifts a suspension.

## Actual customer and financial sources

Garage contact records are **not** customer login accounts. Job final amounts
and billing JSON are **not** captured payments.

Separate customer accounts, account-to-garage links, invoice/payment/refund/
dispute records, reviews, vehicles, delivery records and support tickets have
persisted source models. The development ingestion tool accepts only validated
source batches:

```sh
cd artifacts/api-server
PYTHONPATH=. python scripts/import_admin_sources.py /path/to/authentic-source-batch.json
```

This tool refuses non-development or non-internal databases. It performs one
atomic import, requires stable external identifiers, validates cross-garage/
customer relationships, rejects raw gateway/credential fields, and validates
capture/refund limits. It is append-only; it does not masquerade as a public
financial mutation or edit API.

The batch schema is `SourceBatch` in `app/schemas/admin_operations.py`. Accounts
have actual source identity, name, optional contact data, account status,
last activity, and garage associations. Each record has a kind, source/external
ID, garage, actual event timestamp, safe typed payload and optional linked IDs.
Money is nonnegative integer INR paise. Parent records must be imported before
their attempts/refunds/disputes.

No artificial production records are seeded. Empty source lists report empty
results; financial summaries return `source_status: NO_RECORDS`. That is not a
claim that an unconnected external system has no transactions.

### Metric bases and snapshots

- Gross collections: captured payment events in the window.
- Refunds: settled refund events in the window; net collections = gross − refunds.
- Paid-invoice counts require cumulative captures covering the nonvoid invoice.
- Issued invoice totals/averages use nonvoid issued/paid invoice records, separately
  from collections.
- Completion averages use valid completed jobs from the creation cohort, with
  sample sizes and invalid-timestamp exclusions.
- Conversion uses distinct accepted booking-event IDs in the selected window and
  their recorded conversions by snapshot time. Historical acceptance events
  that never existed are not invented.
- Owner totals and averages use the full filtered owner set, not the current page.
  Zero-job garages count in the denominator. Empty denominators return null.
- Fresh finance/owner snapshots default to an explicit 30-day calendar window
  in the requested IANA timezone; UTC is the compatibility default.
- Legacy dashboard/job amount fields keep their rupee-based recorded-job meaning.
  New financial fields use paise and their own documented event-date window.
- Stored snapshots freeze the selected records and totals. They expire after
  `ADMIN_SNAPSHOT_HOURS` (default 24), are requester/scope-bound, and reject
  mismatched filters. Admin GET transactions use repeatable reads.
- Data selection and exports are bounded by `ADMIN_MAX_REPORT_ROWS` (default
  10,000); oversized requests fail rather than return partial “complete” data.

Canonical service-ID filtering remains unavailable because existing job/booking
records do not persist those associations. Requests for it fail explicitly.
Existing historical booking exceptions without stored transition events retain
the labeled legacy creation-date view. Supply `group_by` to use recorded
exception events grouped by any combination of owner, garage, reason, city, day.

## Delays and alerts

`ADMIN_DELAY_HOURS` defaults to 24, configurable from 1 to 720. Active jobs are
overdue when time in their current state reaches that threshold. State entry
uses the latest recorded matching timeline event; missing history explicitly
falls back to job creation. Terminal jobs are excluded.

Alerts are deterministic live state episodes. Severity is MEDIUM at the
threshold and HIGH at twice the threshold. Repeated reads do not create
duplicate notification sends. These APIs do not send customer notifications.

## Announcements

Development sends support **IN_APP only**. PUSH/SMS/EMAIL preview requests return
409 `CHANNEL_NOT_CONFIGURED`; provider approval, valid templates and participant
consent must exist before activating those channels. No provider acceptance is
represented as final delivery.

Preview resolves active garage owners within caller scope and freezes the
audience, channels, title and body for five minutes, with a 1,000-garage limit.

```json
{
  "audience": {"recipient_roles": ["GARAGE_OWNER"], "garage_ids": []},
  "channels": ["IN_APP"],
  "title": "Operational update",
  "body": "Please review appointment availability."
}
```

Send requires an `Idempotency-Key` header and:

```json
{"preview_id": "<preview UUID>", "reason": "Appointment capacity review"}
```

It does not accept content changes after preview. A changed idempotency payload
returns 409. In-app delivery and the announcement/audit records commit
atomically, so delivery means the notification is actually in the existing
garage inbox.

## Support

Tickets are sourced records, not invented placeholder conversations. Permitted
statuses are OPEN, IN_PROGRESS, WAITING_FOR_CUSTOMER, RESOLVED and CLOSED.
Priorities are LOW, NORMAL, HIGH and URGENT.

Status policy:

- OPEN → IN_PROGRESS / WAITING_FOR_CUSTOMER / RESOLVED.
- IN_PROGRESS → WAITING_FOR_CUSTOMER / RESOLVED.
- WAITING_FOR_CUSTOMER → IN_PROGRESS / RESOLVED.
- RESOLVED → IN_PROGRESS / CLOSED.
- CLOSED is final; reopening is forbidden.

Assignment requires active support-authorized staff with compatible garage
scope. Changes use reasons and expected versions. Resolving/closing requires
resolution text. Replies have at most 2,000 characters and deduplicate the
client message ID per ticket/sender. Closed tickets reject new replies.
Only external reply operations exist; no internal-note payload is accepted.

Messages are persisted in the ticket conversation, and the garage participant
receives an existing in-app inbox notification. A separate customer application's
conversation/delivery integration must be connected to expose replies in that
application; customer-account records alone are not a customer-authentication
or messaging transport.

## Exports

Request `OPERATIONS`, `FINANCE` or `GARAGE_OWNER_PERFORMANCE` with CSV/XLSX,
filters and an `Idempotency-Key`. Requests return 202/QUEUED. The managed server's
five-second scheduler processes bounded batches; status progresses to READY or
FAILED. Pending jobs survive restarts because their snapshots/jobs are in SQL.

Downloads require the requester, unchanged scope, `reports.export` and current
report read permissions. Expired jobs return 410; unfinished jobs return 409.
Owner-performance exports omit financial fields unless authorized. Each report
includes filters, snapshot, generation time, source totals and definitions.
Spreadsheet-formula injection is sanitized. File bytes are generated in memory,
not stored as database blobs. Files exceeding 10 MiB or XLSX cell bounds fail.
Snapshot/report expiry limits access; expiry is not a promise of physical SQL
purging or audit retention deletion.

## Production handoff

Before publishing, obtain separate approval for the new schema, MFA enrollment/
recovery rollout, scope assignments, domain-source integration, notification
channels/consent and data retention. Delivery-only migration startup remains
bounded to its original delivery target; it never applies these admin migrations
under that approval.
