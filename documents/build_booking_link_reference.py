"""Customer/garage booking handoff, generated without changing application data."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "artifacts/api-server"))
from app.main import app
from app.schemas.booking import BookingResponse, BookingDetailResponse
from app.schemas.job import JobResponse
from app.schemas.customer_workspace import QuoteRequest, BookingSubmit, SlotCreate, CancelRequest
from app.schemas.customer_discovery import DiscoveryGarage, DiscoveryService, GarageSearch, LocationInput
from approval_document_writer import ApprovalWriter
from build_customer_implemented_reference import resolve, describe

OUT = ROOT / "generated-artifacts"
G, V, S, SLOT, Q, B, J, CONTACT, GV = [
    f"10000000-0000-4000-8000-{i:012d}" for i in range(1, 10)
]
DAY = (date.today() + timedelta(days=7)).isoformat()
START, END = DAY + "T10:00:00+05:30", DAY + "T11:00:00+05:30"
STAMP = date.today().isoformat() + "T09:00:00+05:30"
GARAGE = {"id": G, "name": "Example Partner Garage"}
VEHICLE = {"id": V, "registration_number": "DEMO-VEHICLE"}
SERVICES = [{"id": S, "name": "Brake inspection", "amount": 50000, "duration_minutes": 60}]
SLOT_BODY = {"starts_at": START, "ends_at": END, "timezone": "Asia/Kolkata", "capacity": 2}
QUOTE_BODY = {"garage_id": G, "vehicle_id": V, "service_ids": [S], "slot_id": SLOT,
              "notes": "Please inspect the brakes", "attachment_ids": []}
QUOTE = {"quote_id": Q, "garage": GARAGE, "vehicle": VEHICLE, "services": SERVICES,
         "starts_at": START, "ends_at": END, "notes": QUOTE_BODY["notes"], "attachment_ids": [],
         "estimated_total": 50000, "currency": "INR",
         "expires_at": date.today().isoformat() + "T09:10:00+05:30",
         "slot_reserved": False, "slot_id": SLOT}
CUSTOMER_BOOKING = {"id": B, "status": "PENDING", "garage": GARAGE, "vehicle": VEHICLE,
                    "services": SERVICES, "starts_at": START, "ends_at": END,
                    "notes": QUOTE_BODY["notes"], "attachment_ids": [],
                    "estimated_total": 50000, "currency": "INR", "can_cancel": True,
                    "cancel_reason": None, "linked_job_id": None, "linked_job_status": None,
                    "created_at": STAMP}
OWNER_BOOKING = BookingResponse(
    id=B, garage_id=G, customer_id=CONTACT, vehicle_id=GV, status="PENDING",
    booking_date=DAY, notes=QUOTE_BODY["notes"], customer_name="Example Customer",
    customer_mobile=None, service_requested="Brake inspection", created_at=STAMP, updated_at=STAMP,
).model_dump(mode="json")
OWNER_DETAIL = BookingDetailResponse(**OWNER_BOOKING).model_dump(mode="json")
OWNER_JOB = JobResponse(id=J, job_number="JOB-DEMO-001", garage_id=G, customer_id=CONTACT,
                       vehicle_id=GV, booking_id=B, status="OPEN",
                       description="Brake inspection", created_at=STAMP,
                       updated_at=STAMP).model_dump(mode="json")
CUSTOMER_JOB = {"id": J, "job_number": "JOB-DEMO-001", "booking_id": B, "vehicle_id": V,
                "garage": GARAGE, "status": "OPEN", "created_at": STAMP, "completed_at": None,
                "published": False, "findings": [], "notes": None,
                "services": [], "parts": [], "labour": [], "photos": []}
DISCOVERY_SERVICE = DiscoveryService(
    id=S, name="Brake inspection", description="Inspection of brakes",
    price_inr="500.00", amount=50000, duration_minutes=60,
    booking_eligible=True, unavailable_reason=None,
).model_dump(mode="json")
DISCOVERY_GARAGE = DiscoveryGarage(
    **GARAGE, address="Example Street", city="Bengaluru", state="Karnataka",
    zipcode="560001", country="IN", distance_km=2.4, matched_by=["service"],
    active_service_count=1, matching_service_count=1, services=[DISCOVERY_SERVICE],
    services_has_more=False, services_path=f"/api/v1/customer-app/garages/{G}/services",
    booking_eligible=True, booking_prerequisites=["SELECT_VEHICLE", "CHECK_AVAILABILITY", "CONFIRM_QUOTE"],
).model_dump(mode="json")


def page(item):
    return {"items": [item], "total": 1, "page": 1, "page_size": 20, "pages": 1}


def changed(status):
    return {**OWNER_BOOKING, "status": status}


# side, method, path, body, success data, HTTP status, explanation
ROUTES = [
    ("Customer", "POST", "/customer-app/garages/search",
     {"q": "Brake", "search_by": "service", "latitude": 12.9716, "longitude": 77.5946, "radius_km": 5},
     {**page(DISCOVERY_GARAGE), "radius_km": 5, "distance_type": "STRAIGHT_LINE"}, 200,
     "Search service names or set search_by=garage for garage names, all for both. Service-only matches preview matching services; garage-name matches preview the full active catalogue. Coordinates are body-only; radius defaults to 5 km, maximum 200 km. Distance filtering occurs before pagination."),
    ("Customer", "GET", "/customer-app/garages/{garage_id}", None,
     {**DISCOVERY_GARAGE, "distance_km": None, "matched_by": [], "matching_service_count": 0}, 200,
     "Customer-safe selected garage with up to five active services. Without location distance is null, never zero. Excludes unavailable garages and internal owner fields."),
    ("Customer", "POST", "/customer-app/garages/{garage_id}/details",
     {"latitude": 12.9716, "longitude": 77.5946},
     {**DISCOVERY_GARAGE, "matched_by": [], "matching_service_count": 0}, 200,
     "Send the same chosen location as search to show selected-garage distance. Label it straight-line, not driving distance. Do not send coordinates in URLs or analytics logs."),
    ("Customer", "GET", "/customer-app/garages/{garage_id}/services", None,
     page(DISCOVERY_SERVICE), 200,
     "Full paginated active catalogue; optional q filters service name. price_inr is a decimal INR string; amount is integer paise. Retain exact service IDs for availability and quote. Missing/nonpositive duration prevents booking eligibility."),
    ("Garage owner", "POST", "/garage/customer-slots", SLOT_BODY,
     {"id": SLOT, **SLOT_BODY, "active": True}, 201,
     "One-time setup: create a future slot before the customer requests availability. Mixed timezones and overlapping active slots are rejected."),
    ("Garage owner", "GET", "/garage/customer-slots", None,
     {"items": [{"id": SLOT, **SLOT_BODY, "active": True}]}, 200,
     "View this owner's garage slots. The optional date parameter currently does not filter this owner list; filter returned timestamps client-side if needed."),
    ("Garage owner", "DELETE", "/garage/customer-slots/{slot_id}", None,
     {"id": SLOT, "active": False}, 200,
     "Disable future selection of a slot. Existing bookings remain accessible; this is not booking cancellation."),
    ("Customer", "GET", "/customer-app/garages/{garage_id}/availability", None,
     {"date": DAY, "timezone": "Asia/Kolkata", "slots": [
         {"id": SLOT, "starts_at": START, "ends_at": END, "available": True}]}, 200,
     "Required query: date and repeated service_ids. Use only an available returned slot; availability is not a reservation."),
    ("Customer", "POST", "/customer-app/bookings/quote", QUOTE_BODY, QUOTE, 200,
     "Use a customer-owned vehicle, active services belonging to this garage and a suitable future slot. Quote lasts 10 minutes and does not reserve capacity."),
    ("Customer", "POST", "/customer-app/bookings", {"quote_id": Q}, CUSTOMER_BOOKING, 201,
     "Required Idempotency-Key header. Save data.id as booking_id. This creates the same booking the owner sees; no forwarding API or webhook is required."),
    ("Garage owner", "GET", "/bookings", None, page(OWNER_DETAIL), 200,
     "For incoming work use status=PENDING&page=1&page_size=20. The authenticated owner's garage is selected by the server, not a request garage_id."),
    ("Garage owner", "GET", "/bookings/{booking_id}", None, OWNER_DETAIL, 200,
     "Look up the exact booking_id returned to the customer. Another garage's booking is not accessible."),
    ("Garage owner", "PATCH", "/bookings/{booking_id}/accept", None, changed("ACCEPTED"), 200,
     "Only a future, non-cancelled PENDING customer appointment can be accepted. No JSON payload or rejection/acceptance reason field is defined."),
    ("Garage owner", "PATCH", "/bookings/{booking_id}/reject", None, changed("REJECTED"), 200,
     "Alternative branch: reject PENDING or ACCEPTED work. No body is defined. Do not run this and the happy-path conversion against the same booking."),
    ("Customer", "GET", "/customer-app/bookings", None, page(CUSTOMER_BOOKING), 200,
     "List only the signed-in customer's linked bookings; optional status, vehicle_id, garage_id and linked_job_status filters."),
    ("Customer", "GET", "/customer-app/bookings/{booking_id}", None,
     {**CUSTOMER_BOOKING, "status": "ACCEPTED", "can_cancel": False,
      "cancel_reason": "Only future PENDING bookings may be cancelled"}, 200,
     "Read after owner acceptance/rejection. After conversion, status is CONVERTED, linked_job_id is the new job ID, and linked_job_status is its current job state."),
    ("Customer", "GET", "/customer-app/bookings/{booking_id}/timeline", None,
     {"items": [{"event": "PENDING", "occurred_at": STAMP},
                {"event": "ACCEPTED", "occurred_at": STAMP, "reason": None},
                {"event": "CONVERTED", "occurred_at": STAMP, "reason": None},
                {"event": "JOB_CREATED", "job_id": J, "occurred_at": STAMP}]}, 200,
     "Chronological booking events plus linked job creation. Timestamps here are illustrative; actual actions have their own timestamps."),
    ("Customer", "POST", "/customer-app/bookings/{booking_id}/cancel",
     {"reason": "Change of plans"}, {"id": B, "status": "CANCELLED", "cancelled_at": STAMP}, 200,
     "Alternative branch: customer may cancel only a future PENDING booking with no job. Accepted bookings cannot be cancelled through this customer endpoint."),
    ("Garage owner", "POST", "/bookings/{booking_id}/create-job", None, OWNER_JOB, 200,
     "Converts PENDING or ACCEPTED work atomically into a job. Recommended UI flow: accept first, then create job. Response data.id is job_id, data.booking_id is the original booking ID. Booking becomes CONVERTED."),
    ("Customer", "GET", "/customer-app/jobs/{job_id}", None, CUSTOMER_JOB, 200,
     "Read the linked job using linked_job_id. This is a restricted customer projection, not the owner job response. No internal staff/cost records are exposed."),
    ("Customer", "GET", "/customer-app/jobs/{job_id}/timeline", None,
     {"items": [{"id": "10000000-0000-4000-8000-000000000010",
                 "status": "OPEN", "occurred_at": STAMP}]}, 200,
     "Read the linked job's recorded status history. Booking status and job status are separate state machines."),
]


def envelope(data, status=200, message="Success"):
    return {"success": True, "message": message, "data": data, "errors": [], "status_code": status}


def main():
    spec = app.openapi()
    writer = ApprovalWriter("Customer to Garage Owner — Booking Integration",
                            footer_label="Customer / Garage Booking Integration")
    writer.cover()
    writer.p("Endpoint, header, payload, response and shared-ID flow guide. No admin APIs.")
    writer.p(f"Prepared {date.today().isoformat()}. Source-checked against current development routes. "
             "All response examples are illustrative synthetic fixtures, not live bookings or proof of production availability. "
             "Sample dates/IDs must be replaced. No application code, accounts or booking data were changed to create this guide.")
    writer.h("1. What connects the two applications")
    writer.p("Both applications use the same backend booking record. Customer submission selects garage_id and returns data.id. "
             "That exact booking ID appears in the selected garage owner's booking list. The customer does not call the owner app, "
             "supply an owner password, or make a second booking to forward the request.")
    writer.code("Customer searches service or garage -> sees distance + services\n"
                "Owner creates appointment slot\n"
                "Customer selects garage + services + own vehicle\n"
                "Customer reads availability -> creates quote -> submits booking\n"
                "Owner reads same booking_id -> accepts OR rejects\n"
                "Customer reads booking detail / timeline for updated status\n"
                "Owner creates job -> booking status CONVERTED\n"
                "Customer reads linked_job_id -> customer job / timeline")
    writer.p("Acceptance, rejection, cancellation and conversion examples represent different stages or alternative branches. "
             "Do not execute every mutation sequentially on a single booking.")
    writer.h("2. Environment, authentication and prerequisites")
    writer.p("Base URL: <API_ORIGIN>/api/v1. Obtain the agreed test server address from the backend owner; "
             "this guide does not invent a production or staging hostname. Confirm this API version is deployed before integration.")
    writer.code("Customer requests:\nAuthorization: Bearer <customer_access_token>\n"
                "Garage-owner requests:\nAuthorization: Bearer <garage_owner_access_token>\n"
                "Both:\nAccept: application/json\nContent-Type: application/json  (JSON bodies only)\n"
                "Customer booking submission also:\nIdempotency-Key: booking-request-001")
    writer.p("Tokens are role-specific and not interchangeable. The developer should receive a test customer account, "
             "a separate test owner account, and confirmed garage/service IDs through the normal secure setup. "
             "Customer login/OTP, token refresh and vehicle creation are prerequisites, not duplicated in this booking-only guide.")
    writer.p("The garage must be active, have active services with a positive duration and suitable future slots. "
             "Service IDs must belong to the selected garage. The customer vehicle ID must belong to the authenticated customer. "
             "The implemented discovery endpoints below supply the real garage/service IDs. The external customer app implements "
             "its search bar, distance labels, selection and Book button against these contracts.")
    writer.p("Nearby results use approximate straight-line Haversine distance (mean Earth radius 6371.0088 km), not road distance. "
             "Show e.g. '2.4 km away - straight-line' beside search garages and selected garage services. Location is optional for text-only "
             "search; nearby browsing needs both coordinates. Missing/invalid garage coordinates are excluded from nearby results. "
             "Location body metadata accuracy_meters/captured_at is accepted but not stored or used to enforce freshness. "
             "Use fresh mobile coordinates or a manually selected location; Google driving distance and travel time are not implemented.")
    writer.h("3. ID mapping — essential for integration")
    writer.table(["ID", "Source and use"], [
        ["garage_id", "Discovery result item.id. Selects the receiving garage. Owner requests derive their garage from the owner session."],
        ["vehicle_id (customer)", "Customer vehicle API. Used in quote request and customer responses."],
        ["service_ids", "Active services for the selected garage; not arbitrary service names."],
        ["slot_id", "Owner creates it; customer availability returns it; customer submits it with the quote request."],
        ["quote_id", "Quote response data.quote_id -> customer submission body.quote_id."],
        ["booking_id", "Customer submission data.id -> owner list item.id -> owner accept/reject/create-job path."],
        ["job_id", "Owner create-job response data.id -> customer booking data.linked_job_id -> customer job endpoints."],
        ["Owner customer_id / vehicle_id", "Garage-scoped contact/vehicle IDs created by the backend bridge. They need not equal customer account/vehicle IDs. Never match records by phone or registration."],
    ], [125, 370])
    writer.h("4. Status, retry and refresh rules")
    for text in [
        "Booking states: PENDING, ACCEPTED, REJECTED, CONVERTED, CANCELLED, EXPIRED. A completed job does not rename its booking to COMPLETED; the booking remains CONVERTED.",
        "Normal branches: PENDING -> ACCEPTED -> CONVERTED; PENDING/ACCEPTED -> REJECTED; future PENDING without a job -> CANCELLED. Unattended pending appointments may become EXPIRED through server maintenance. Owner acceptance checks the appointment has not expired or been cancelled.",
        "Backend also allows direct PENDING -> CONVERTED. CONVERTED means a job was created, not that service is finished. Job states are OPEN, IN_PROGRESS, WAITING_FOR_PARTS, QUALITY_CHECK, READY, COMPLETED and CANCELLED.",
        "Quote expiry is 10 minutes. Capacity is checked again at submission and serialized server-side. Availability and quote creation do not reserve the slot. Quote service/vehicle/time/price changes can require a fresh quote.",
        "Generate one Idempotency-Key per intended booking. Retry an uncertain submission with the same key AND same quote_id; a different quote with that key returns 409 IDEMPOTENCY_CONFLICT. Successful replay returns the saved original response, not a live booking refresh. Fetch booking detail for current state.",
        "Use customer booking.detail can_cancel to control the cancel button; the server still rechecks. Do not retry owner accept/reject/create-job blindly after a network timeout. Fetch current booking detail first; these owner actions do not define an idempotency header.",
        "For initial integration, refresh owner booking lists and customer booking/detail timelines on screen entry and after actions. Bounded polling while a relevant screen is visible is an integration recommendation, not a server push guarantee. No websocket endpoint or push-delivery SLA is promised.",
        "Quotes/customer estimated_total and service amount values in this flow are INR minor units (paise): 50000 = INR 500.00. Owner job amount fields use the owner's decimal money format; do not apply the same conversion blindly.",
        "No private historical garage contacts/jobs are automatically claimed by a customer account. The linkage is explicitly created for newly submitted customer bookings. Do not implement matching/linking by phone number or registration number.",
    ]:
        writer.p(text)
    writer.p("After job creation, the customer booking detail includes these linkage fields "
             "(excerpt only; the full booking projection still contains its other fields):")
    writer.code({"id": B, "status": "CONVERTED", "linked_job_id": J,
                 "linked_job_status": "OPEN", "can_cancel": False})
    writer.h("5. Endpoint index")
    writer.table(["ID", "Caller", "Method / path (append to /api/v1)"], [
        [f"B-{i:02}", role, f"{method} {path}"]
        for i, (role, method, path, *_rest) in enumerate(ROUTES, 1)
    ], [40, 75, 380])
    writer.br()
    writer.h("6. Endpoint contracts")

    def code(value):
        lines = (value if isinstance(value, str) else json.dumps(value, indent=2)).splitlines()
        for start in range(0, len(lines), 32):
            writer.code("\n".join(lines[start:start + 32]))

    validated = []
    for i, (role, method, path, body, data, status, note) in enumerate(ROUTES, 1):
        full = "/api/v1" + path
        op = spec["paths"][full][method.lower()]
        writer.h(f"B-{i:02} | {role} | {method} {path}", 2)
        writer.p(note)
        code("Authorization: Bearer <" + ("customer_access_token" if role == "Customer" else "garage_owner_access_token") +
             ">\nAccept: application/json" + ("\nContent-Type: application/json" if body else "") +
             ("\nIdempotency-Key: booking-request-001" if path == "/customer-app/bookings" and method == "POST" else ""))
        params = [p for p in op.get("parameters", []) if p["in"] in {"path", "query"}]
        if params:
            writer.table(["Parameter", "Location / required", "Type and constraints"], [
                [p["name"], p["in"] + (" / Yes" if p.get("required") else " / No"), describe(p["schema"], spec)]
                for p in params
            ], [100, 95, 300])
        if "availability" in path:
            code(f"GET {full.replace('{garage_id}', G)}?date={DAY}&service_ids={S}")
            writer.p("For multiple services repeat the query parameter: service_ids=<id1>&service_ids=<id2>.")
        writer.p("Request payload:")
        if body is None:
            writer.p("No request body. Do not invent reason or other fields for owner accept/reject/create-job.")
        else:
            schema = resolve(op["requestBody"]["content"]["application/json"]["schema"], spec)
            writer.table(["Field", "Required", "Type and constraints"], [
                [k, "Yes" if k in schema.get("required", []) else "No", describe(v, spec)]
                for k, v in schema["properties"].items()
            ], [100, 65, 330])
            code(body)
            model = (SlotCreate if path == "/garage/customer-slots" else
                     GarageSearch if path.endswith("/garages/search") else
                     LocationInput if path.endswith("/details") else
                     QuoteRequest if path.endswith("/quote") else
                     BookingSubmit if path == "/customer-app/bookings" else CancelRequest)
            model.model_validate(body)
        writer.p(f"Sample success response: HTTP {status}. Illustrative; all optional/default owner fields are shown.")
        msg = ("Bookings retrieved" if role == "Garage owner" and path == "/bookings" else
               "Booking retrieved" if role == "Garage owner" and method == "GET" and path.startswith("/bookings/") else
               "Booking accepted" if path.endswith("/accept") else "Booking rejected" if path.endswith("/reject") else
               "Job created from booking" if path.endswith("/create-job") else "Success")
        response = envelope(data, status, msg)
        code(response)
        validated.append({"method": method, "path": full, "role": role, "request": body, "response": response})
    writer.h("7. Errors and integration checklist")
    writer.p("All examples above use the standard success/message/data/errors/status_code JSON envelope. "
             "Treat HTTP status as authoritative. Error message/code spelling differs between customer and owner handlers; "
             "do not assume every error has the same errors[] shape.")
    code({"success": False, "message": "QUOTE_EXPIRED", "data": None,
          "errors": [{"code": "QUOTE_EXPIRED"}], "status_code": 409})
    writer.p("Illustrative customer error above; check HTTP status and the documented customer code. "
             "Customer failures include 404 missing/non-owned vehicle, quote or booking; "
             "409 QUOTE_EXPIRED, QUOTE_STALE, SLOT_UNAVAILABLE, GARAGE_UNAVAILABLE, IDEMPOTENCY_CONFLICT or BOOKING_CANNOT_CANCEL; "
             "422 malformed UUID/date, missing fields or invalid service selection. Refresh relevant data before retrying a conflict.")
    writer.p("Owner failures include 404 missing/non-owned booking and 400 invalid state or expired/cancelled appointment. "
             "Both roles require valid sessions; authentication/authorization failures use 401/403 as applicable. "
             "Owner ACCEPTED work may be converted while a garage is suspended, but accepting new work and converting PENDING work require the garage to allow new work.")
    for text in [
        "Happy path: create slot -> customer quote/submit -> owner lists same booking ID -> accept -> customer sees ACCEPTED -> create job -> customer sees CONVERTED + linked_job_id -> customer fetches job.",
        "Use separate test bookings for rejection and cancellation. Confirm another garage owner/customer cannot retrieve or mutate the booking.",
        "Retry the identical customer submission with the same key; confirm one booking. Reuse the key with another quote; confirm conflict.",
        "Check full/disabled/expired slots and expired/stale quotes. Verify duplicate owner conversion does not create another job; read current booking after an uncertain result.",
    ]:
        writer.p(text)
    writer.p("Out of scope: admin APIs/credentials, anonymous discovery, driving distance/navigation, mobile UI implementation, invoices/payments, "
             "chat and full job-edit/publication contracts. This handoff focuses only on linking customer bookings to the garage owner and continuing into job tracking.")
    writer.save(OUT / "GoFixCarz_Customer_Garage_Booking_Integration")
    (OUT / "booking-link-reference-validation.json").write_text(json.dumps({
        "contracts_checked_in_openapi": len(validated),
        "example_kind": "illustrative synthetic; not newly exercised live requests",
        "requests_schema_validated": True, "contracts": validated,
    }, indent=2))
    print(f"Generated PDF and Word; {len(validated)} current route contracts checked.")


if __name__ == "__main__":
    main()
