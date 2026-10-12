# Admin APIs — existing-data phase

This implements the user's choice to start with data already stored by the API.
It is **not approval or implementation of the full proposed admin PDF**.
No migrations, production changes, new admin provisioning, finance writes,
booking decisions on behalf of a garage, or job editing are introduced.
Private administrator authentication routes are intentionally omitted here.

## New business reads

All paths below are relative to `/api/v1/admin`; all are `GET`.

| Draft operation | Path | Supported data |
|---|---|---|
| ADM-13 | `/garage-owners` | Paginated owner accounts, garage previews, booking/job aggregates |
| ADM-14 | `/garage-owners/{owner_id}` | Owner identity and managed garage previews; optional archived-account retrieval |
| ADM-25 | `/bookings/{booking_id}` | Booking details, garage contact/vehicle records where linked, linked job previews |
| ADM-26, partial | `/bookings/exception-statistics` | Currently rejected bookings, grouped by owner/city; creation cohort, **not exception transition history** |
| ADM-29 | `/jobs/{job_id}/timeline` | Paginated chronological persisted status records and notes |
| ADM-64 | `/audit-logs/{audit_id}` | Existing stored admin audit metadata |
| ADM-65, partial | `/activity` | Recorded booking creation, job creation/completion and job status events |
| ADM-66, partial | `/activity/service-funnels/{booking_id}` | Booking, linked job previews and paginated recorded events; explicit missing downstream sources |

Existing owner, garage, job, booking, dashboard, analytics and audit-list reads
remain available. Their existing response fields and money units are retained.
The API's OpenAPI documentation includes typed schemas for the new reads.

## Inputs and common behavior

- Existing-data authorization remains platform-wide for active administrators.
  Garage owners cannot access these reads. Normal owner APIs remain tenant-scoped.
  The draft's granular roles, garage scopes and MFA are separate unapproved work.
- Collection pagination uses `page >= 1`, `1 <= page_size <= 100`, default 20.
  Owner garage previews and linked-job previews are capped at 100 and report
  truncation. Retrieve all garages with `/garages?user_id=<owner_id>` and all
  linked jobs with `/jobs?booking_id=<booking_id>` using pagination.
- `date_from`, `date_to`, `timezone`, `city`, `garage_id` apply to owner
  aggregates, bookings, jobs, activity, dashboard and analytics where exposed.
  IANA timezones such as `Asia/Kolkata` are supported. UTC remains the default
  to preserve the existing baseline; the PDF's proposed new default is not
  silently approved. Date windows are inclusive local calendar dates converted
  to UTC `[start, next-day-start)`. A supplied two-sided window cannot span more
  than 366 days. Reversed dates preserve the existing HTTP 400 contract.
- City is an exact, trimmed, case-insensitive match, not a wildcard query.
- Owner reads support `search`, account `status` (`ACTIVE`, `INACTIVE`,
  `DELETED`) and `include_deleted`. Account status is **not** garage operational
  or verification status. Selecting `DELETED` explicitly includes archived owners.
  Details require `include_deleted=true` for archived accounts.
- Bookings support persisted booking `status`, `customer_id` and `search`
  (name, mobile or requested-service text). Jobs support their persisted status,
  search, `customer_id` and `booking_id`. Customer IDs here identify garage
  contact records, **not customer login accounts**.
- Activity additionally supports `owner_id`, `customer_id`, `booking_id`,
  `job_id`, and `event_type`: `BOOKING_CREATED`, `JOB_CREATED`, `JOB_COMPLETED`,
  or `JOB_STATUS_RECORDED`. Events sort newest first with a stable tie-breaker;
  timeline reads sort oldest first. Creation events do not invent initial states.
- Audit list filtering supports actor, action, dates and timezone.
- Unknown or unavailable query parameters fail with HTTP 422 instead of being
  silently ignored. Examples include `service_id`, `min_rating`,
  `verification_status`, `snapshot_id` and unsupported grouping inputs.
- Each successful admin read writes an admin audit entry. Failed requests do
  not manufacture successful read events. Soft-deleted jobs, bookings and
  garages are excluded; preserved owner identity retrieval remains explicit.

## Metric definitions and limits

Dashboard inventory counts refer to current stored users/garages, independently
of the requested date window. Scoped inventory reflects the selected city/garage.
Jobs and bookings are creation cohorts with their current persisted statuses.
Completed-event counts and job amounts use `completed_at`. Responses include
`filters`, `generated_at` and metric definitions where relevant. They do **not**
claim to be immutable, reusable snapshots.

Analytics retains the existing daily/weekly/monthly/custom periods. Explicit
dates now apply to all periods. `start_date`/`end_date` remain accepted aliases
for analytics dates; contradictory aliases fail. `custom` requires both bounds.
Defaults remain the existing rolling daily/weekly/monthly windows, returned
explicitly. Sparse time buckets remain the existing response convention.

Existing `revenue*` fields remain the sum of recorded final amounts on completed
jobs, expressed in INR rupees. They are **not confirmed payment collections**.
The new owner `completed_job_amount_paise` uses integer INR paise and the same
recorded-job-amount basis; it is not net collection, profit or settled revenue.
Missing completion timestamps/final amounts are excluded from this sum and
remain visible through the existing billing-issue review API.

Owner ratings remain `null`, with missing data sources identified. Booking
decision actor/reason/timestamp are `null` with explicit missing history. Generic
booking notes are not guessed to be decision reasons. Rejected booking counts
use `created_at` because exception transition timestamps were never stored.
Missing reasons are `UNSPECIFIED`; `CANCELLED` and `EXPIRED` booking states are
identified as unavailable, not synthesized as zero counts. Exception group
previews are bounded at 100 with an explicit truncation flag.

Service funnels identify missing decision, invoice, payment and review history.
Only persisted events are shown; no acceptance, payment or review events are
invented from the current status or billing JSON.

## Still requiring approved policy or new sources

- MFA, granular admin permissions/data scopes, and restricted-field privacy.
- Separate garage operational/verification lifecycle and suspension effects.
- Customer login identities and reviews; customer risk/privacy rules.
- Dashboard participant cohorts, service filters, immutable snapshots and
  finance definitions backed by invoices/captured payments/refunds.
- Booking decision history and cancellation/expiry lifecycle.
- Job due dates, state/service delay thresholds and alert configuration.
- Announcements, support, exports and audit retention/privacy policy.

These are deliberately deferred rather than implemented with successful
placeholder responses.
