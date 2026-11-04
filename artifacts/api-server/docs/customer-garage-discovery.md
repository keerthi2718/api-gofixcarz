# Customer search, distance and booking integration

These are implemented **development backend contracts**, not proof of a
production rollout. The customer app is maintained outside this workspace.
Use the same API origin as its existing customer authentication and bookings.
No admin or owner credential is needed for discovery.

## Headers and privacy

Every endpoint requires `Authorization: Bearer <customer_access_token>`.
Send `Accept: application/json`; POST requests also send
`Content-Type: application/json`. Responses use the existing
`{success,message,data,errors,status_code}` envelope and `Cache-Control: no-store`.
Unknown JSON fields are rejected.

Send customer coordinates only in the documented POST bodies, **never in URL
query parameters**. Application request logs record paths, not these bodies;
discovery does not persist location history. Disable/redact request-body
capture in external proxies, analytics and crash-reporting tools too.
Coordinates describe the customer's current or manually selected location,
not the garage owner's live position.

## 1. Search by service or garage

`POST /api/v1/customer-app/garages/search`

```json
{
  "q": "Oil change",
  "search_by": "service",
  "latitude": 12.9716,
  "longitude": 77.5946,
  "radius_km": 5,
  "page": 1,
  "page_size": 20
}
```

| Field | Rule |
| --- | --- |
| q | Trimmed case-insensitive partial **name** search, at most 100 characters; `%`, `_`, `/` are literal, not wildcard syntax |
| search_by | `service`, `garage` or `all` (default); `all` is suitable for one search bar |
| city | Optional saved-city filter, at most 100 characters; trimmed, case-insensitive **exact** match (not address, name, substring or geocoding). Allows city-only browsing, including garages without map pins |
| latitude / longitude | Optional complete, finite pair; ranges -90..90 and -180..180; zero is valid |
| radius_km | Optional, greater than 0 and at most 200; defaults to 5 when coordinates are supplied **without city**; cannot be used without coordinates. With city, only an explicitly supplied radius limits geographic distance |
| accuracy_meters | Optional finite 0..100000 mobile accuracy estimate; requires coordinates; not used to expand radius |
| captured_at | Optional ISO timestamp supplied by the app; requires coordinates; not stored and does not enforce freshness |
| page / page_size | Defaults 1 / 20; page 1..100000, page size 1..100 |

- **Service search:** `{"q":"Oil change","search_by":"service"}` finds garages
  with matching active services; each garage preview contains only matching
  services.
- **Garage search:** `{"q":"ABC Garage","search_by":"garage"}` finds garages by
  name; its service preview contains active services without filtering service
  names by `"ABC Garage"`.
- **Unified search:** `search_by: "all"` matches garage names or service names.
  A garage-name match shows its full active catalogue preview; a service-only
  match shows matching services. `matched_by` explains the match.
- **Nearby browsing:** omit `q` (or use an empty string) and supply coordinates.
- **City browsing:** send `{"city":"Hyderabad","page":1,"page_size":20}`.
  This uses the existing garage's saved city and existing owner service catalogue,
  including active garages without coordinates. Optional `q`/`search_by` further
  filter names within the city. Blank city is treated as omitted.
  Coordinates may also be supplied to calculate and sort by distance, with
  unknown distances last, but **no implicit radius** is applied in city mode.
  Explicitly supplying `radius_km` applies a strict intersection of city and
  radius, excluding missing/invalid map pins. Omit `radius_km` for city fallback.
- **Text-only fallback:** omit coordinates and radius; `distance_km` is null.
  Empty text without coordinates or a nonblank city is a 422 error.

Illustrative response (IDs and prices are examples, not seeded records):

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [{
      "id": "10000000-0000-4000-8000-000000000001",
      "name": "ABC Garage",
      "address": "Example Street",
      "city": "Bengaluru",
      "state": "Karnataka",
      "zipcode": "560001",
      "country": "IN",
      "distance_km": 2.4,
      "distance_type": "STRAIGHT_LINE",
      "matched_by": ["service"],
      "active_service_count": 12,
      "matching_service_count": 1,
      "services": [{
        "id": "10000000-0000-4000-8000-000000000003",
        "name": "Oil change",
        "description": "Engine oil replacement",
        "price_inr": "500.00",
        "amount": 50000,
        "currency": "INR",
        "duration_minutes": 30,
        "booking_eligible": true,
        "unavailable_reason": null
      }],
      "services_has_more": false,
      "services_path": "/api/v1/customer-app/garages/10000000-0000-4000-8000-000000000001/services",
      "booking_eligible": true,
      "booking_prerequisites": ["SELECT_VEHICLE", "CHECK_AVAILABILITY", "CONFIRM_QUOTE"]
    }],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1,
    "radius_km": 5,
    "distance_type": "STRAIGHT_LINE"
  },
  "errors": [],
  "status_code": 200
}
```

### Distance rules

Distances use a clamped Haversine calculation with mean Earth radius
6371.0088 km. This is an approximate **straight-line geographic** distance,
not an ellipsoidal survey measurement or driving distance. Real-world accuracy
also depends on the phone fix and saved garage pin; obtain a fresh fix, disclose
low accuracy, and allow manual location selection in the external app.

The radius predicate and nearest-first ordering use the unrounded distance
before pagination; the API displays three decimals in kilometres. For UI,
format appropriately, e.g. **“2.4 km away · straight-line”** in both search
results and garage service selection. Tie-breaks are case-insensitive garage
name then ID; text-only ordering uses those same tie-breaks.

Garages with missing/out-of-range coordinates are excluded from radius-filtered results,
but can appear in text-only or city results with distance unavailable. Do not display
missing distance as zero. Radius eligibility is based on the saved pin, not a
claim that the customer can reach the garage within that road distance.
City browsing does not claim that a garage without a pin is nearby; display
“Distance unavailable” rather than a numeric distance for those results. No
coordinates are guessed from city or address, and garage records are not changed.
If a visible distance is close to the boundary, display rounding can differ
from the precise value used for eligibility.

No Google call, credential or paid mapping service is required or configured.
Driving distance/traffic estimates remain excluded; never label this field
“driving distance”.

## 2. Selected garage and complete catalogue

| Method and endpoint | Request | Response data |
| --- | --- | --- |
| `GET /api/v1/customer-app/garages/{garage_id}` | No body | Customer-safe garage detail, bounded active-service preview, distance null |
| `POST /api/v1/customer-app/garages/{garage_id}/details` | `{"latitude":12.9716,"longitude":77.5946}` | Same detail with distance from that location; accepts the same optional accuracy/timestamp metadata |
| `GET /api/v1/customer-app/garages/{garage_id}/services?page=1&page_size=20` | Optional query `q` filters service name; page size 1..100 | `{items:[service],total,page,page_size,pages}` |

Use the **same chosen location** for search and selected-garage details.
Detail does not impose a radius, allowing the app to display the selected
garage's distance independently of a previous search.

Previews contain at most five services. `services_has_more` refers to the
preview's applicable set; `active_service_count` always counts the full active
catalogue, while `matching_service_count` counts the search-name matches.
Follow `services_path` without `q` for all services, or pass the original
service search text as `q` for matching services only. Page beyond the end
returns an empty list; no matches means `total: 0, pages: 0`.

Deleted/suspended garages and deleted/inactive services are excluded.
No new VERIFIED-only rule is imposed. A garage with no active bookable service
can be discovered by name but has `booking_eligible: false`. Missing/nonpositive
duration (or invalid negative price) makes a service ineligible; do not enable
its Book selection. `booking_eligible: true` means catalogue configuration is
suitable to request availability/quote, **not** that a slot is reserved or free.
Prices may change; the quote is authoritative. `price_inr` is a decimal string
for display; `amount` is integer **paise**, consistent with quote service amounts.

## 3. Continue into the existing shared booking

1. Retain the exact selected garage `id` and selected services' `id` values.
   Do not submit search strings, create duplicate services or forward to an
   owner app endpoint.
2. Get the customer's vehicles through `GET /api/v1/customer-app/vehicles`
   and select the customer's `vehicle_id`.
3. Read `GET /api/v1/customer-app/garages/{garage_id}/availability?date=YYYY-MM-DD&service_ids=<id>`.
   Repeat `service_ids` for multiple services. Choose an available returned
   slot; availability does not reserve capacity.
4. `POST /api/v1/customer-app/bookings/quote`:

   ```json
   {
     "garage_id": "10000000-0000-4000-8000-000000000001",
     "vehicle_id": "10000000-0000-4000-8000-000000000002",
     "service_ids": ["10000000-0000-4000-8000-000000000003"],
     "slot_id": "10000000-0000-4000-8000-000000000004"
   }
   ```

5. Display the server's quoted services, timing, currency and `estimated_total`
   in paise for confirmation. `POST /api/v1/customer-app/bookings` with
   `{"quote_id":"<returned-quote-id>"}` and a stable `Idempotency-Key` header.
   Retry the same request/key after an uncertain response, not a new booking.
6. Save response `data.id` as **booking_id**. The garage owner reads this exact
   ID in `GET /api/v1/bookings` and `GET /api/v1/bookings/{booking_id}` with its
   owner credential. No second record, forwarding request or identity matching.
7. Owner uses `PATCH /api/v1/bookings/{booking_id}/accept` or `/reject`.
   Customer refreshes booking detail/list or timeline to see the result.
8. Owner uses `POST /api/v1/bookings/{booking_id}/create-job`. Customer booking
   becomes `CONVERTED` and exposes `linked_job_id`/`linked_job_status`; use
   `GET /api/v1/customer-app/jobs/{linked_job_id}` for customer-safe job tracking.

The existing server revalidates service activity/ownership/duration, garage
availability, vehicle ownership, quote freshness/prices and slot capacity.
Search is not a reservation. Re-fetch availability and quote after a conflict;
do not trust a stale search price. Refresh booking state on screen entry and
while awaiting an owner decision; this change does not add push delivery.

## Errors and integration checks

401: missing/expired/wrong-role customer token. 404: garage missing, deleted or
unavailable on detail/catalogue reads. 422: invalid fields, partial coordinates,
radius without location or missing text/location. Booking retains its existing
404/409/422 rules; never translate conflicts into a successful local booking.

The runtime OpenAPI is at `/api/openapi.json`; the workspace API spec and generated
client/validator packages include these contracts. See the booking PDF/Word
guide for existing owner/customer status, headers and error flows.

Run from `artifacts/api-server`:

```sh
python -m pytest tests/integration/test_customer_discovery.py tests/integration/test_customer_workspace.py -q
python scripts/export_customer_openapi.py
```

Then from the workspace root:

```sh
pnpm --filter @workspace/api-spec run codegen
```

Integration fixtures enforce the internal development database, roll back their
records and mock SMS/storage; no real messages, Google calls, production schema
changes or publishing are part of this implementation.
