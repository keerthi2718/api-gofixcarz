# Customer discovery and date-only booking: frontend handoff

This is the current contract for nearby search and new customer booking creation.
Examples are illustrative: use IDs returned by the backend, the customer's selected
map location, and the selected date. Do not hardcode the example IDs or coordinates.

## Authentication and common response

Customer operations require:

```http
Authorization: Bearer <customer_access_token>
Content-Type: application/json
```

Booking submission additionally requires `Idempotency-Key: <unique-request-key>`.
Generate one key for one intended booking. Reuse it with the identical request after
a timeout; use a new key for a different booking. Reusing a key with changed input
returns `409 IDEMPOTENCY_CONFLICT`. An identical retry returns the existing booking
with its current status, not a second booking.

Owner operations use the garage-owner token, not the customer token.
Responses use this envelope:

```json
{
  "success": true,
  "message": "Success",
  "data": {},
  "errors": [],
  "status_code": 200
}
```

Customer locations travel in request bodies, not URLs, and responses use
`Cache-Control: no-store`. They are not saved to the customer's profile.

## Step 1: Search nearby garages or services

`POST /api/v1/customer-app/garages/search`

```json
{
  "latitude": 17.385044,
  "longitude": 78.486671,
  "radius_km": 200,
  "q": "oil",
  "search_by": "service"
}
```

- Both coordinates are now required. Changing location means repeating this request
  with the newly selected coordinates; the frontend must replace its old results.
- `radius_km` is optional: omitted/null defaults to **200 KM**; a positive value
  up to 200 explicitly narrows the radius.
- Omit `q` or send `""` to browse all eligible nearby garages.
- `search_by` is `all` (default), `service`, or `garage`. Matching is case-insensitive
  literal substring matching by service/garage name.
- Optional `city` narrows the result by saved city, case-insensitively and trimmed.
  It does not bypass the radius or substitute for coordinates.
- Only non-deleted garages with `operational_status: ACTIVE` and
  `verification_status: VERIFIED` are included. Missing/invalid garage map pins
  cannot satisfy the radius. No coordinates are inferred or invented.
- Distance is geographic straight-line distance, **not road distance**, nearest first.
- **All matching garages are returned in one response.** Old `page`/`page_size`
  fields are accepted but ignored; there is no search result truncation.
- Each result includes all matching active services for a service-only match, or
  the full active catalogue for a matching garage name. No five-service cap remains.

`data` contains:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 0,
  "pages": 0,
  "radius_km": 200,
  "distance_type": "STRAIGHT_LINE"
}
```

For nonempty results, `page_size` equals `total`, and `pages` is 1. These metadata
fields remain for client compatibility; no further search page needs fetching.
Each garage includes `id`, `name`, address fields, `distance_km`, `services`,
service counts, `booking_eligible`, and `services_has_more: false`.
Services include `id`, `name`, `description`, `price_inr`, `amount`,
`currency`, `duration_minutes`, and `booking_eligible`.
Missing duration does not prevent date-only booking.

## Step 2: Open a garage and its complete service catalogue

| Method | Endpoint | Input / behavior |
|---|---|---|
| GET | `/api/v1/customer-app/garages/{garage_id}` | Full active catalogue; distance is null without a selected location |
| POST | `/api/v1/customer-app/garages/{garage_id}/details` | JSON body with latitude and longitude to return distance |
| GET | `/api/v1/customer-app/garages/{garage_id}/services` | All active services by default; optional `q` filters names |

The services endpoint supports optional explicit `page_size`/`page` for older clients,
but the frontend does not need pagination when these parameters are omitted.
Unverified, rejected, inactive, or deleted garages are not exposed through these routes.
These routes read the garage owner's actual existing service catalogue.

## Step 3: Select or create a customer-owned vehicle

`GET /api/v1/customer-app/vehicles` lists the customer's vehicles.
This endpoint retains its existing pagination, unlike garage search.

`POST /api/v1/customer-app/vehicles` creates a vehicle:

```json
{
  "registration_number": "TS09AB1234",
  "brand": "Maruti Suzuki",
  "model": "Swift",
  "fuel_type": "PETROL",
  "year": 2023
}
```

Use the returned `data.id` as `vehicle_id`. Another customer's vehicle is rejected.
Do not use the owner's internal garage vehicle ID.

## Step 4: Optional booking summary

`POST /api/v1/customer-app/bookings/summary`

```json
{
  "garage_id": "11111111-1111-4111-8111-111111111111",
  "vehicle_id": "22222222-2222-4222-8222-222222222222",
  "service_ids": ["33333333-3333-4333-8333-333333333333"],
  "booking_date": "2030-01-10",
  "notes": "Please inspect engine noise",
  "attachment_ids": []
}
```

Display `data.garage`, `data.vehicle`, `data.services`, `data.booking_date`,
`data.estimated_total`, and `data.currency`.
No booking, slot reservation, or quote ID is created by this preview.
Use `booking_date` in `YYYY-MM-DD` form. Today and future dates are accepted using
the current `Asia/Kolkata` business-date policy; past dates return 422.
Between 1 and 20 distinct service IDs and up to 5 booking-photo attachment IDs are accepted.

Money rules:
- Service `price_inr` is rupees (serialized as a decimal string).
- Service `amount` and `estimated_total` are integer **paise**.
- `estimated_total` is exactly the sum of the selected service amounts.
- No booking fees, extra charges, or Code ID are added to this flow.
- No client-supplied price or total can override backend service prices.

## Step 5: Submit directly, without slot_id or quote_id

`POST /api/v1/customer-app/bookings`

Headers:

```http
Authorization: Bearer <customer_access_token>
Content-Type: application/json
Idempotency-Key: <unique-key-for-this-booking>
```

Body:

```json
{
  "garage_id": "11111111-1111-4111-8111-111111111111",
  "vehicle_id": "22222222-2222-4222-8222-222222222222",
  "service_ids": ["33333333-3333-4333-8333-333333333333"],
  "booking_date": "2030-01-10",
  "notes": "Please inspect engine noise",
  "attachment_ids": [],
  "expected_total": 150000
}
```

Use the same selection as the reviewed summary. `expected_total` is optional and
must be the reviewed paise total, not a manually calculated charge. If current
service prices differ, the server returns `409 PRICE_CHANGED`; refresh the summary
and ask the customer to confirm the new price before resubmitting.
Without `expected_total`, submission uses current backend prices.

Summary is optional: the frontend may submit the selection directly.
Submission rechecks the date, garage verification/operational status, vehicle
ownership, active service membership, attachments, and prices.

HTTP 201 returns `data.id` (the booking ID), `status: PENDING`, `garage`, `vehicle`,
`services`, `booking_date`, `estimated_total`, `currency`, cancellation information,
and timestamps. Legacy `starts_at` and `ends_at` fields are null for new date-only
bookings; never use them to require a time-slot selection.
No `slot_id` or `quote_id` is accepted or returned.
Unknown fields such as `slot_id`, `quote_id`, `code_id`, `booking_fee`, or a
client-authored `total` are rejected with 422.

The previous `POST /bookings/quote` operation is removed. The old availability route
is deprecated and is not needed for this flow. Existing slot-based bookings,
storage, and owner slot-management records are retained for compatibility.
An internal immutable service snapshot is saved automatically; the frontend never
has to create, persist, or submit its storage identifier.

## Step 6: Garage owner receives and acts on the booking

New requests use the existing shared bookings table and the selected garage ID.
After submission commits, the owner can fetch the request immediately:

| Method | Endpoint | Result |
|---|---|---|
| GET | `/api/v1/bookings?status=PENDING` | Owner's pending bookings; existing owner pagination remains |
| GET | `/api/v1/bookings/{booking_id}` | Owner's booking with customer, vehicle, requested service names and booking date |
| PATCH | `/api/v1/bookings/{booking_id}/accept` | No body; changes status to `ACCEPTED` |
| PATCH | `/api/v1/bookings/{booking_id}/reject` | No body; changes status to `REJECTED` |

Use a garage-owner access token. Garage scoping prevents another garage from reading
or acting on the booking. Date-only requests need no slot to be accepted.

Scope note: this change does **not** rename the existing acceptance status to
`CONFIRMED`; customer and owner APIs continue to report `ACCEPTED`.
The existing owner booking response exposes requested service names rather than
the customer's structured price snapshot/total. Extending that owner projection is
separate work. This document does not claim an owner-dashboard frontend change.

## Step 7: Customer reads the synchronized status

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/customer-app/bookings` | Customer's bookings; existing pagination remains |
| GET | `/api/v1/customer-app/bookings/{booking_id}` | Current backend booking status, date, selected services and frozen total |
| GET | `/api/v1/customer-app/bookings/{booking_id}/timeline` | Booking events |
| POST | `/api/v1/customer-app/bookings/{booking_id}/cancel` | `{"reason":"Change of plans"}` |

Submission is `PENDING`; owner acceptance is `ACCEPTED`; owner rejection is `REJECTED`.
Customer reads use the same booking row as owner actions. The frontend must re-fetch
after actions or on its normal refresh schedule; no live push/socket delivery is
claimed. A pending date-only request without a job may be cancelled through its
selected day. After that day passes in Asia/Kolkata, unattended pending requests
expire; accepted work is not automatically expired.

## Important error handling

| HTTP | Code / condition | Frontend handling |
|---|---|---|
| 401 | Missing/expired customer session | Refresh/login |
| 404 | Garage or owned vehicle not found | Reload selection; do not substitute IDs |
| 409 | `GARAGE_UNAVAILABLE` | Garage is no longer active and verified |
| 409 | `PRICE_CHANGED` | Refresh summary and confirm again |
| 409 | `IDEMPOTENCY_CONFLICT` | Never reuse a key for different input |
| 422 | `INVALID_APPOINTMENT_DATE` | Select today or a future date |
| 422 | `SERVICE_INACTIVE` | Reload the catalogue and reselect services |
| 422 | Invalid/unknown request fields | Correct the request contract |

## Storage and rollout

No schema change is required for this feature. Existing nullable-slot compatibility
and historical scheduling storage must be preserved. No production rows or schema
are changed by development tests. Publish through the normal flow after frontend
clients adopt the breaking search/booking input changes.
