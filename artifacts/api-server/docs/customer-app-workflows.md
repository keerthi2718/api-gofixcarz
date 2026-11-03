# Customer app workflow APIs

## Garage/service discovery and distance

Four additional customer-authenticated discovery operations are implemented:
POST garage search, GET garage detail, POST located garage detail and GET
paginated active garage services. They read the owner's catalogue directly and
return the same IDs used by existing availability, quote and booking submission.
See [the discovery-to-booking contract](customer-garage-discovery.md) for complete
headers, payloads, responses, distance semantics and the external app handoff.
The implementation counts below describe the earlier workflow inventory,
excluding these four additional discovery operations.

The customer-only approval inventory now has 57 implemented operations out of
58 applicable operations. Four conditional password operations remain excluded
under the approved mobile-only OTP policy. API-41 checkout creation is explicitly
pending Razorpay integration, by the user's choice.

One additional authenticated job-photo download supports published job photos,
bringing the runtime surface to 59 customer operations: 58 working operations
and one explicit pending checkout operation.

## Development policies

- Garage accounts are VERIFIED by default at creation; existing development
  garages are marked VERIFIED. Operational status remains a separate control.
  Production data is not changed by this development update.
- Customer-owned vehicles; no historical contact/vehicle matching.
- First vehicle is default; removal archives, blocks active work, and selects
  the oldest remaining vehicle as replacement default.
- Existing private S3 storage is preserved. Images are decoded, validated and
  re-encoded, removing metadata. JPEG/PNG/WebP, 5 MiB, 20 million pixels,
  no animation. Support uploads are images under the same policy.
  DELETE revokes access transactionally; physical S3 removal is deferred until
  a separately approved retention/cleanup policy exists.
- Customer appointment selection is optional. A quote may omit `slot_id` or
  send null; it uses real selected service prices and creates no slot records.
  Owners can still offer explicit capacity slots and a garage timezone.
  Quotes expire in ten minutes; submission locks the quote (and selected slot,
  if any), rechecks the selection, and creates deliberate new-work garage records.
- Slotless bookings remain PENDING with null schedule fields until the owner
  confirms a real time. Owner acceptance records `owner_accepted_at` separately;
  `PATCH /api/v1/bookings/{booking_id}/schedule` then sets the schedule and
  changes status to ACCEPTED. Its body contains timezone-aware ISO datetimes
  `scheduled_start` and `scheduled_end`. Accepted slotless bookings can be
  rescheduled through that same endpoint. Existing slot-based acceptance is unchanged.
- Cancellation is allowed for unscheduled or future PENDING bookings without a job. Cancelled
  bookings cannot be accepted/converted by garage APIs.
  A 60-second background worker expires past unattended PENDING appointments.
- Job status is visible on explicitly linked work; details/photos require
  deliberate owner publication. Legacy internal/timeline notes are omitted.
- Invoice publication is owner-only on completed work, computes paise totals,
  and does not claim payment. Development PDFs need legal billing review before
  production use.
- Payment reads use trusted financial sources; only CAPTURED records yield
  receipts. Checkout creation returns `503 PAYMENT_PROVIDER_NOT_CONFIGURED`.
- In-app activity is durable. Push registration is real but delivery is not
  configured; responses disclose `push_delivery_configured: false`. Logout
  detaches installations. Razorpay callbacks/events are not implemented.
- Conversations reuse booking context after conversion; terminal work is
  read-only. Idempotent message IDs and stable cursor ordering are enforced.
- One review per completed owned job; seven-day editing window; moderation
  is required after creation/edit.
- Support accepts consistent owned contexts or general issues, external-only
  replies, and read-only resolved/closed states. Separate scoped admin APIs
  permit replies/status updates and moderation.

## Participant routes

Owner slot configuration is under `/api/v1/garage/customer-slots`.
Customer-visible job publication and invoice publication are under
`/api/v1/jobs/{job_id}/customer-publication` and `customer-invoice`.
Owner conversation participants use `/api/v1/garage/customer-conversations`.
Admin support/moderation use `/api/v1/admin/customer-support/tickets` and
`/api/v1/admin/customer-reviews`. Admin role permissions and garage scopes apply.
These supporting URLs are not included in the customer-only Word document.

## Development verification and document regeneration

```sh
cd artifacts/api-server
CUSTOMER_CONTRACT_EXAMPLES="$PWD/../../generated-artifacts/customer-contract-examples.json" \
  python -m pytest tests/integration/test_customer_workspace.py \
  tests/integration/test_customer_app.py tests/unit/ -q
python scripts/export_customer_openapi.py
cd ../..
pnpm --filter @workspace/api-spec run codegen
python documents/build_customer_implemented_reference.py
```

Tests use real internal development PostgreSQL with mocked SMS/S3, no real
payments/push delivery, rollback-isolated fictional accounts and cleaned abuse
counters. The document builder requires successful captured samples and checks
every endpoint against live OpenAPI; it does not claim draft payloads work.

Migration `0016_customer_workspace` was applied to development only. It adds
customer tables and CANCELLED/EXPIRED enum values. Downgrade deliberately does
not attempt destructive PostgreSQL enum-value removal. Production publishing,
production migrations, live provider credentials, orphan-object retention
automation and legal tax-invoice review are not part of this implementation.
