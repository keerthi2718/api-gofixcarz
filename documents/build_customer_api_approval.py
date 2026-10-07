"""Generate matching client-review DOCX/PDF files from one structured specification."""
from pathlib import Path
import json
import textwrap
import zipfile
import xml.etree.ElementTree as ET
from html import escape

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted,
    KeepTogether, Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4

OUT = Path("documents")
BASE = "/api/v1/customer-app"
sections = []


def section(title, stories, screens, rules):
    sections.append(dict(title=title, stories=stories, screens=screens, rules=rules, endpoints=[]))


def api(method, path, title, request, response, *, access="Customer", status=200,
        query="", rules="", errors="401 AUTH_REQUIRED; 404 RESOURCE_NOT_FOUND", headers=""):
    sections[-1]["endpoints"].append(dict(
        method=method, path=path, title=title, request=request, response=response,
        access=access, status=status, query=query, rules=rules, errors=errors, headers=headers,
    ))


def page(items, total=None):
    return dict(items=items, page=1, page_size=20, total=len(items) if total is None else total)


def tokens():
    return dict(access_token="<access_token>", refresh_token="<refresh_token>",
                token_type="Bearer", expires_in_seconds=900, session_id="session_001")


section("Authentication and sessions", list(range(1, 6)), [1, 2, 3, 21], [
    "Core registration/login is OTP-based. Account creation occurs only after verification. Registration supports mobile OR email in this proposal; the UI discrepancy needs approval.",
    "Mobile identifiers use E.164; email identifiers are normalized. Terms consent and the published terms version are required for registration.",
    "OTP send/resend limits and failed-attempt limits must protect both channels and combine identifier, IP and device signals. Proposed OTP expiry: 5 minutes; resend cooldown: 30 seconds; maximum verification attempts: 5 per challenge. Delivery submission is not proof of delivery.",
    "Challenge IDs bind identifier, purpose and pending registration. Resending invalidates the prior challenge. OTPs are single-use. Successful login responses are issued only after validation.",
    "Access-token lifetime of 15 minutes is a proposed default, not an approved setting. Refresh-token lifetime remains a decision. Rotate refresh tokens, detect reuse, revoke the token family/session, and store mobile credentials in secure device storage.",
    "Logout revokes the current session and refresh credentials. Protected requests must honor session revocation; clearing client storage alone is insufficient.",
])
api("POST", "/auth/register", "Start verified registration",
    dict(name="Demo Customer", channel="mobile", identifier="+919000000001", terms_version="2026-10", terms_accepted=True),
    dict(challenge_id="challenge_register_001", purpose="REGISTER", expires_in_seconds=300, resend_after_seconds=30),
    access="Public", status=202, rules="All illustrated fields required. Name must be nonblank; channel is mobile or email. No customer account is created yet.",
    errors="409 ACCOUNT_ALREADY_EXISTS; 422 VALIDATION_ERROR; 429 RATE_LIMITED")
api("POST", "/auth/otp/send", "Request a login OTP",
    dict(channel="mobile", identifier="+919000000001", purpose="LOGIN"),
    dict(challenge_id="challenge_login_001", expires_in_seconds=300, resend_after_seconds=30),
    access="Public", status=202, rules="All fields required. Purpose is LOGIN; registration and contact changes use their dedicated flows. Use generic acceptance behavior to reduce account enumeration.",
    errors="422 VALIDATION_ERROR; 429 RATE_LIMITED")
api("POST", "/auth/otp/resend", "Resend OTP", dict(challenge_id="challenge_login_001"),
    dict(challenge_id="challenge_login_002", expires_in_seconds=300, resend_after_seconds=30),
    access="Public", status=202, rules="challenge_id required. Enforce cooldown and cumulative limits; previous challenge becomes unusable.",
    errors="400 CHALLENGE_INVALID; 429 RATE_LIMITED")
api("POST", "/auth/otp/verify", "Verify OTP and establish session",
    dict(challenge_id="challenge_login_002", otp="123456", device_name="Customer Phone"),
    dict(customer=dict(id="customer_001", name="Demo Customer"), **tokens()),
    access="Public", rules="challenge_id and otp required; device_name optional. OTP is a string, preserving leading zeroes. Registration challenge verification creates the account and session.",
    errors="400 OTP_INVALID; 400 OTP_EXPIRED; 429 OTP_ATTEMPTS_EXCEEDED")
api("POST", "/auth/refresh", "Rotate refresh credentials", dict(refresh_token="<refresh_token>"),
    dict(access_token="<new_access_token>", refresh_token="<rotated_refresh_token>", token_type="Bearer", expires_in_seconds=900),
    access="Refresh credential", rules="refresh_token required. Rotation is atomic; expired, revoked or reused credentials cannot establish a session.",
    errors="401 REFRESH_TOKEN_INVALID; 401 SESSION_REVOKED")
api("GET", "/auth/session", "Validate current session", None,
    dict(session_id="session_001", customer_id="customer_001", authenticated=True, expires_at="2026-10-08T10:15:00Z"))
api("POST", "/auth/logout", "Revoke current session", None, dict(logged_out=True),
    rules="Idempotent for a recognized session; do not accept a customer ID in the body.")

section("Conditional password option", [3], [1], [
    "These four operations are CONDITIONAL: include only if the client retains the password option shown on the login screen. OTP remains the core path.",
    "A verified password-setup/change proof is obtained through a purpose-bound OTP challenge extension. Do not reuse a normal access token as proof of recent verification.",
    "Use secure password hashing and an approved password policy. Reset requests must use generic responses; recovery delivery, proof issuance and expiry require a final design.",
])
api("POST", "/auth/password/login", "Password login",
    dict(identifier="customer@example.test", password="<password>", device_name="Customer Phone"),
    dict(customer=dict(id="customer_001"), **tokens()), access="Public",
    rules="identifier and password required; device_name optional. Conditional operation.",
    errors="401 INVALID_CREDENTIALS; 429 RATE_LIMITED")
api("PUT", "/auth/password", "Set or change password",
    dict(verification_token="<purpose_bound_verification_proof>", new_password="<new_password>"),
    dict(password_updated=True), rules="Both fields required. Recent verification proof is single-use and bound to password setup/change.",
    errors="400 VERIFICATION_PROOF_INVALID; 422 PASSWORD_POLICY_FAILED")
api("POST", "/auth/password/reset/request", "Request password recovery",
    dict(identifier="customer@example.test"), dict(request_received=True), access="Public", status=202,
    rules="identifier required. Generic response regardless of account existence.",
    errors="422 VALIDATION_ERROR; 429 RATE_LIMITED")
api("POST", "/auth/password/reset/confirm", "Complete password recovery",
    dict(reset_token="<reset_token>", new_password="<new_password>"),
    dict(password_reset=True, existing_sessions_revoked=True), access="Recovery credential",
    rules="Both fields required. Proof must be purpose-bound, single-use and unexpired.",
    errors="400 RESET_TOKEN_INVALID; 422 PASSWORD_POLICY_FAILED")

section("Customer profile", [6], [8], [
    "Only the authenticated customer's profile is accessible. Profile updates cannot set ownership, permissions, verified flags or account roles.",
    "Name must be nonblank. Address is optional; when provided validate city, postal code and country. Profile PATCH preserves omitted fields.",
    "Changing mobile/email requires verification of the new identifier and approved recent-authentication checks. Keep the old contact until verification completes; prevent duplicate verified contacts.",
    "Profile photos use a customer-owned READY attachment with PROFILE_PHOTO purpose. Deleting the profile photo detaches it subject to storage cleanup policy.",
])
api("GET", "/me", "View profile", None,
    dict(id="customer_001", name="Demo Customer", mobile="+919000000001", email=None,
         mobile_verified=True, email_verified=False, photo=None,
         address=dict(line1="Example Street", city="Hyderabad", postal_code="500001")))
api("PATCH", "/me", "Update name/address",
    dict(name="Demo Customer", address=dict(line1="Example Street", city="Hyderabad", state="Telangana", postal_code="500001", country="IN")),
    dict(id="customer_001", name="Demo Customer", address=dict(line1="Example Street", city="Hyderabad", state="Telangana", postal_code="500001", country="IN")),
    rules="At least one supported field required; both name and address are individually optional. Contacts must use the verified contact-change flow.",
    errors="422 VALIDATION_ERROR")
api("POST", "/me/contact-change", "Start contact change",
    dict(channel="email", new_identifier="customer@example.test"),
    dict(challenge_id="contact_challenge_001", expires_in_seconds=300), status=202,
    rules="Both fields required. channel is mobile or email. New identifier must not conflict with another account.",
    errors="409 CONTACT_ALREADY_IN_USE; 429 RATE_LIMITED")
api("POST", "/me/contact-change/verify", "Verify and apply new contact",
    dict(challenge_id="contact_challenge_001", otp="123456"),
    dict(email="customer@example.test", email_verified=True),
    rules="Both fields required. Apply the new contact atomically; recheck uniqueness.",
    errors="400 OTP_INVALID; 400 OTP_EXPIRED; 409 CONTACT_ALREADY_IN_USE; 429 RATE_LIMITED")
api("PUT", "/me/photo", "Set profile photo", dict(attachment_id="attachment_profile_001"),
    dict(photo=dict(attachment_id="attachment_profile_001", download_path=BASE+"/attachments/attachment_profile_001/download")),
    rules="attachment_id required and must be READY, PROFILE_PHOTO and customer-owned.",
    errors="422 ATTACHMENT_INVALID")
api("DELETE", "/me/photo", "Remove profile photo", None, dict(removed=True))

section("Vehicles and service history", [7, 8, 9], [9], [
    "Vehicle IDs must belong to the customer. Registration numbers are normalized and validated; duplicate active entries for the same customer are rejected.",
    "Required on create: registration_number, brand, model, fuel_type. Proposed optional fields: year, odometer_km, is_default. Fuel type must come from the approved enum; odometer is nonnegative and year is plausible.",
    "Exactly one default when vehicles exist is the proposed rule. Default changes are atomic; deletion of a default requires a replacement rule.",
    "Removal is blocked while active work exists. Use archival where necessary so historical jobs and invoices remain accessible.",
])
vehicle = dict(id="vehicle_001", registration_number="TS00AA0001", brand="Maruti Suzuki", model="Swift",
               year=2023, fuel_type="PETROL", odometer_km=25000, is_default=True)
api("POST", "/vehicles", "Add vehicle", {k:v for k,v in vehicle.items() if k!="id"}, vehicle, status=201,
    errors="409 VEHICLE_ALREADY_EXISTS; 422 VALIDATION_ERROR")
api("GET", "/vehicles", "List vehicles", None, page([vehicle]), query="page=1&page_size=20")
api("GET", "/vehicles/{vehicle_id}", "View vehicle", None, vehicle)
api("PATCH", "/vehicles/{vehicle_id}", "Edit vehicle", dict(odometer_km=26000, year=2023),
    dict(**{**vehicle, "odometer_km":26000}),
    rules="At least one editable field required. All create fields except is_default may be patched; use the dedicated default endpoint.",
    errors="409 VEHICLE_ALREADY_EXISTS; 422 VALIDATION_ERROR")
api("DELETE", "/vehicles/{vehicle_id}", "Remove vehicle", None, dict(id="vehicle_001", removed=True),
    errors="409 VEHICLE_HAS_ACTIVE_WORK")
api("PUT", "/vehicles/{vehicle_id}/default", "Choose default vehicle", None, dict(default_vehicle_id="vehicle_001"))
api("GET", "/vehicles/{vehicle_id}/service-history", "View service history", None,
    page([dict(booking_id="booking_001", job_id="job_001", job_status="COMPLETED",
               completed_at="2026-10-09T12:00:00+05:30", garage=dict(id="garage_001", name="Example Garage"),
               invoice_id="invoice_001")]), query="page=1&page_size=20")

section("Garage discovery, services and public reviews", [10, 11, 12, 13, 14, 15], [4, 5, 6, 7], [
    "Public discovery returns only published garages, active services/packages and published reviews. Do not expose private owner/admin data.",
    "Search accepts coordinates, city, postal_code or text q. latitude and longitude must be supplied together; valid ranges are -90..90 and -180..180.",
    "Optional filters: service_id, min_rating (1..5), radius_km (>0 within configured maximum), open_now, sort, page and page_size. Distance is null when no usable reference location exists.",
    "A service can be a single item or a package, using type SERVICE or PACKAGE. Return inclusions, estimate duration and server-maintained prices. Display price does not authorize a final bill.",
])
api("GET", "/service-categories", "Home/popular service categories", None,
    dict(items=[dict(id="category_001", name="Periodic Maintenance")]), access="Public",
    query="popular=true", errors="422 VALIDATION_ERROR")
api("GET", "/garages", "Search and filter garages", None,
    page([dict(id="garage_001", name="Example Garage", distance_km=2.4, average_rating=4.6, review_count=85,
               is_open=True, next_available_at="2026-10-09T10:00:00+05:30")]),
    access="Public", query="latitude=17.385&longitude=78.487&radius_km=10&min_rating=4&service_id=service_001&open_now=true&page=1&page_size=20",
    errors="422 VALIDATION_ERROR")
api("GET", "/garages/{garage_id}", "View garage profile", None,
    dict(id="garage_001", name="Example Garage", address=dict(city="Hyderabad", postal_code="500001"),
         location=dict(latitude=17.385, longitude=78.487), contact=dict(phone="+919000000002"),
         timezone="Asia/Kolkata", working_hours=[dict(day="FRIDAY", opens="09:00", closes="18:00")],
         is_open=True, average_rating=4.6, review_count=85), access="Public", errors="404 GARAGE_NOT_FOUND")
service = dict(id="service_001", name="Basic Service", type="PACKAGE", price_amount=150000, currency="INR", estimated_duration_minutes=120)
api("GET", "/garages/{garage_id}/services", "List active garage services", None, page([service]),
    access="Public", query="active=true&page=1&page_size=20", errors="404 GARAGE_NOT_FOUND")
api("GET", "/garages/{garage_id}/services/{service_id}", "View service/package inclusions", None,
    dict(**service, description="Scheduled maintenance package", inclusions=["Inspection", "Oil change labour"], active=True),
    access="Public", errors="404 SERVICE_NOT_FOUND")
api("GET", "/garages/{garage_id}/reviews", "Read published garage reviews", None,
    dict(**page([dict(id="review_public_001", rating=5, comment="Good service",
                     reviewer_display_name="Example Reviewer", created_at="2026-10-01T13:00:00+05:30")],85),
         average_rating=4.6, review_count=85), access="Public", query="page=1&page_size=20&sort=latest",
    errors="404 GARAGE_NOT_FOUND; 422 VALIDATION_ERROR")

section("Secure attachments", [16, 27, 38], [8, 10, 14, 20], [
    "Supported purposes: PROFILE_PHOTO, BOOKING_PHOTO, SUPPORT_ATTACHMENT. Job photos are uploaded by garages, not customers.",
    "Photo defaults proposed for approval: JPEG/PNG/WebP, up to 5 MB each, maximum 5 booking photos. Support formats/limits require approval.",
    "Validate actual bytes, MIME type and size; sanitize filenames; scan as appropriate. Only READY, owned, purpose-compatible attachments can be linked.",
    "Downloads authorize access using ownership or the permitted linked job/context. Never expose permanent public URLs for private files. Deletion must respect links and retention policies.",
])
api("POST", "/attachments", "Upload attachment",
    "Multipart/form-data: file=<binary image>; purpose=BOOKING_PHOTO",
    dict(id="attachment_001", purpose="BOOKING_PHOTO", filename="vehicle-front.jpg", content_type="image/jpeg", size_bytes=245000, status="READY"),
    status=201, rules="file and purpose required. Return READY only after required validation/scanning completes.",
    errors="413 ATTACHMENT_TOO_LARGE; 415 ATTACHMENT_TYPE_UNSUPPORTED; 422 ATTACHMENT_INVALID")
api("GET", "/attachments/{attachment_id}/download", "Download authorized attachment", None,
    "Binary response: Content-Type: image/jpeg; Content-Disposition: inline; filename=\"vehicle-front.jpg\"")
api("DELETE", "/attachments/{attachment_id}", "Remove unlinked attachment", None,
    dict(id="attachment_001", removed=True), errors="409 ATTACHMENT_IN_USE")

section("Availability and booking summary", [15, 16, 17, 18, 19], [10], [
    "Reject past appointment dates, inactive services and slots too short for selected service duration. Use each garage's IANA timezone; future means future at that garage.",
    "Availability is advisory. Quote creation does not reserve capacity in this proposal. Submission must atomically recheck capacity, service availability, vehicle ownership and quote validity.",
    "Selection can remain in the app until quote submission; no persistent selection API is required by the workbook.",
    "Estimated totals are computed server-side and are not final invoices. The quote binds customer, garage, vehicle, selected services, slot, notes and owned attachment IDs.",
])
api("GET", "/garages/{garage_id}/availability", "Find appointment slots", None,
    dict(date="2026-10-09", timezone="Asia/Kolkata", slots=[dict(id="slot_001", starts_at="2026-10-09T10:00:00+05:30", ends_at="2026-10-09T12:00:00+05:30", available=True)]),
    query="date=2026-10-09&service_ids=service_001", rules="date and at least one service ID required.",
    errors="422 INVALID_APPOINTMENT_DATE; 422 SERVICE_INACTIVE; 404 GARAGE_NOT_FOUND")
api("POST", "/bookings/quote", "Validate selection and review summary",
    dict(garage_id="garage_001", vehicle_id="vehicle_001", service_ids=["service_001"], slot_id="slot_001",
         notes="Please inspect engine noise", attachment_ids=["attachment_001"]),
    dict(quote_id="quote_001", garage=dict(id="garage_001", name="Example Garage"),
         vehicle=dict(id="vehicle_001", registration_number="TS00AA0001"),
         services=[dict(id="service_001", name="Basic Service", amount=150000)],
         starts_at="2026-10-09T10:00:00+05:30", notes="Please inspect engine noise", attachment_ids=["attachment_001"],
         estimated_total=150000, currency="INR", expires_at="2026-10-08T15:10:00+05:30", slot_reserved=False),
    rules="garage_id, vehicle_id, nonempty unique service_ids and slot_id required. notes and attachment_ids optional. Proposed notes limit: 2,000 characters.",
    errors="409 SLOT_UNAVAILABLE; 422 SERVICE_INACTIVE; 422 ATTACHMENT_INVALID; 404 VEHICLE_NOT_FOUND")

section("Booking management", [20, 21, 22, 23, 24], [10, 11, 12], [
    "Booking states: PENDING, ACCEPTED, REJECTED, CANCELLED, CONVERTED, EXPIRED. COMPLETED is a linked-job filter, not a booking state.",
    "Garages alone accept/reject bookings and convert them into jobs. Customers cannot supply garage decision timestamps or change status directly.",
    "Proposed baseline: customer cancellation is allowed only while PENDING, before work begins. Accepted-booking cancellation, cutoff periods and fees need client approval. Expose can_cancel and a reason when unavailable.",
    "Idempotency keys are scoped to customer and operation. Same key and same payload return the original result; same key with a different payload returns 409. Capacity and booking creation occur atomically.",
])
api("POST", "/bookings", "Submit booking request", dict(quote_id="quote_001"),
    dict(id="booking_001", reference="GFC-B-000001", garage_id="garage_001", vehicle_id="vehicle_001",
         status="PENDING", starts_at="2026-10-09T10:00:00+05:30", estimated_total=150000, currency="INR", job_id=None),
    status=201, headers="Idempotency-Key: <unique_key>", rules="quote_id required. customer_id is derived from the session and is not accepted from the client.",
    errors="409 SLOT_UNAVAILABLE; 409 QUOTE_EXPIRED; 409 IDEMPOTENCY_CONFLICT")
api("GET", "/bookings", "List own bookings", None,
    page([dict(id="booking_001", reference="GFC-B-000001", status="PENDING",
               garage=dict(id="garage_001", name="Example Garage"), starts_at="2026-10-09T10:00:00+05:30", job_id=None)]),
    query="status=PENDING&page=1&page_size=20",
    rules="Optional status, vehicle_id, garage_id and linked_job_status filters. Completed tab: linked_job_status=COMPLETED.",
    errors="422 INVALID_STATUS_FILTER")
api("GET", "/bookings/{booking_id}", "View booking and garage decision", None,
    dict(id="booking_001", reference="GFC-B-000001", status="ACCEPTED", vehicle_id="vehicle_001",
         garage_id="garage_001", service_ids=["service_001"], notes="Please inspect engine noise",
         attachment_ids=["attachment_001"], rejection_reason=None, accepted_at="2026-10-08T16:00:00+05:30",
         job_id=None, can_cancel=False, cancellation_unavailable_reason="Only pending bookings can be cancelled"))
api("GET", "/bookings/{booking_id}/timeline", "Read booking lifecycle", None,
    dict(items=[dict(status="PENDING", timestamp="2026-10-08T15:00:00+05:30", note="Booking submitted"),
                dict(status="ACCEPTED", timestamp="2026-10-08T16:00:00+05:30", note="Appointment confirmed")]))
api("POST", "/bookings/{booking_id}/cancel", "Cancel eligible booking",
    dict(reason="Change of plans"),
    dict(id="booking_002", status="CANCELLED", cancellation_reason="Change of plans", cancelled_at="2026-10-08T15:30:00+05:30"),
    rules="reason required, nonblank, proposed maximum 500 characters. Sample cancellation uses a separate PENDING booking_002; booking_001 was accepted.",
    errors="409 CANCELLATION_NOT_ALLOWED")

section("Published job tracking - read only", [24, 25, 26, 27], [13, 14], [
    "Job states: OPEN, IN_PROGRESS, WAITING_FOR_PARTS, QUALITY_CHECK, READY, COMPLETED, CANCELLED.",
    "Customer access is read-only. No customer job-create, job-update, status-change, labour/parts mutation or garage-photo upload operation is permitted.",
    "Only published/customer-visible findings, notes, photos, services, parts and labour are returned. Exclude internal notes, cost margins, staff-only fields and unrelated customer information.",
    "Timeline events are chronological. A converted booking exposes its linked garage-created job and job creation timestamp.",
])
api("GET", "/jobs", "List accessible jobs", None,
    page([dict(id="job_001", job_number="GFC-J-000001", booking_id="booking_001", vehicle_id="vehicle_001", status="IN_PROGRESS")]),
    query="status=IN_PROGRESS&page=1&page_size=20",
    rules="Optional status and vehicle_id filters.", errors="422 INVALID_STATUS_FILTER")
api("GET", "/jobs/{job_id}", "Read published job details", None,
    dict(id="job_001", job_number="GFC-J-000001", booking_id="booking_001", garage_id="garage_001",
         vehicle_id="vehicle_001", status="IN_PROGRESS", created_at="2026-10-09T10:00:00+05:30",
         inspection_findings=[dict(description="Engine inspection completed")],
         services=[dict(name="Basic Service")], parts=[dict(name="Engine oil", quantity=1)],
         labour=[dict(description="Oil change")], photos=[dict(attachment_id="job_photo_001")], invoice_id=None))
api("GET", "/jobs/{job_id}/timeline", "Read status timeline", None,
    page([dict(status="OPEN", timestamp="2026-10-09T10:00:00+05:30", note="Vehicle received", attachment_ids=[]),
          dict(status="IN_PROGRESS", timestamp="2026-10-09T10:15:00+05:30", note="Inspection started", attachment_ids=["job_photo_001"])]),
    query="page=1&page_size=20")

section("Invoices and secure PDF downloads", [28, 29, 30], [15], [
    "Expose only the customer's published final invoice after the job meets completion/publication rules. Missing historical bills are not fabricated by this specification.",
    "Payment display states: UNPAID, PENDING, PAID, FAILED, REFUNDED. These must be derived from server-confirmed financial records and reconciled attempts.",
    "Amounts are integer paise in INR. Example: subtotal 150000 + tax 27000 - discount 0 = total 177000. Tax/discount ordering and legal invoice fields must follow the approved billing policy.",
    "Invoice PDF is an authenticated binary response. The mobile app uses its native share action after download; no separate public share endpoint is required.",
])
invoice_summary = dict(id="invoice_001", invoice_number="GFC-I-000001", job_id="job_001",
                       total_amount=177000, currency="INR", payment_status="UNPAID")
api("GET", "/invoices", "List final invoices", None, page([invoice_summary]),
    query="payment_status=UNPAID&page=1&page_size=20", rules="Optional payment_status, job_id and vehicle_id filters.")
api("GET", "/invoices/{invoice_id}", "View invoice charges", None,
    dict(**invoice_summary, garage_id="garage_001", vehicle_id="vehicle_001",
         line_items=[dict(type="SERVICE", description="Inspection", quantity=1, unit_amount=50000, line_total=50000),
                     dict(type="PART", description="Engine oil", quantity=1, unit_amount=80000, line_total=80000),
                     dict(type="LABOUR", description="Oil change labour", quantity=1, unit_amount=20000, line_total=20000)],
         subtotal_amount=150000, discount_amount=0, taxes=[dict(name="GST", rate_percent=18, amount=27000)],
         paid_amount=0, balance_due=177000),
    errors="404 INVOICE_NOT_AVAILABLE")
api("GET", "/invoices/{invoice_id}/pdf", "Download/share invoice PDF", None,
    'Binary response: Content-Type: application/pdf; Content-Disposition: attachment; filename="GFC-I-000001.pdf"',
    errors="404 INVOICE_NOT_AVAILABLE")

section("Payments and safe retries", [31, 32], [16], [
    "Payment provider is undecided. Checkout fields are illustrative placeholders until the selected provider's official contract is adopted.",
    "The backend calculates the invoice balance, currency and gateway order. Never accept client-supplied settled status or amount.",
    "Retry uses the same creation endpoint with a new idempotency key after a confirmed failed attempt. Reuse an active valid attempt; reject creation for a fully settled invoice.",
    "Only a verified provider webhook or server-side gateway verification may confirm settlement. Verify order mapping, amount and currency; deduplicate events; make invoice/payment changes transactional.",
    "return_path is optional and restricted to approved in-app routes; never accept an arbitrary external redirect. Partial payments/refunds are outside the approved scope until separately decided.",
])
api("POST", "/invoices/{invoice_id}/payment-attempts", "Start or retry payment", dict(return_path="/payments/result"),
    dict(id="payment_001", invoice_id="invoice_001", amount=177000, currency="INR", status="PENDING",
         checkout=dict(provider="<configured_provider>", order_id="<provider_order_id>", session_token="<short_lived_checkout_token>")),
    status=201, headers="Idempotency-Key: <unique_key>", rules="Body may be {}. Return 200 if reusing an existing active attempt rather than creating one.",
    errors="409 INVOICE_ALREADY_PAID; 409 IDEMPOTENCY_CONFLICT; 502 PAYMENT_PROVIDER_UNAVAILABLE")
api("GET", "/payments/{payment_id}", "Check confirmed payment result", None,
    dict(id="payment_002", invoice_id="invoice_001", amount=177000, currency="INR", status="PAID",
         paid_at="2026-10-09T12:30:00+05:30", receipt_available=True),
    rules="Example shows the successful retry payment_002; payment_001 appears as failed in attempt history.")
api("GET", "/invoices/{invoice_id}/payment-attempts", "Read payment attempt history", None,
    page([dict(id="payment_001", status="FAILED", failure_code="PAYMENT_DECLINED", amount=177000, currency="INR"),
          dict(id="payment_002", status="PAID", amount=177000, currency="INR")]),
    query="page=1&page_size=20")
api("GET", "/payments/{payment_id}/receipt", "Download settled payment receipt", None,
    'Binary PDF response: Content-Type: application/pdf; Content-Disposition: attachment; filename="payment-receipt.pdf"',
    rules="Available only for a server-confirmed paid attempt.", errors="409 RECEIPT_NOT_AVAILABLE")

section("Notifications and unified activity center", [23, 33, 34], [4, 17], [
    "Categories: BOOKINGS, JOBS, INVOICES, MESSAGES, PAYMENTS, REVIEWS, SUPPORT. Each event includes timestamp, read state and authorized linked-record context.",
    "Create in-app activity independently of push delivery. Booking accepted/rejected, job created/status changed, invoice published, payment outcome, message/review/support events feed this center.",
    "Device tokens belong to an app installation bound to the current customer/session. Logout detaches it as appropriate; do not keep sending a previous customer's private events on a shared phone.",
])
api("PUT", "/devices/{installation_id}", "Register/update push installation",
    dict(platform="ANDROID", push_token="<device_push_token>"), dict(installation_id="installation_001", registered=True),
    rules="platform and push_token required; platform enum ANDROID or IOS.",
    errors="422 DEVICE_INVALID")
api("DELETE", "/devices/{installation_id}", "Unregister push installation", None, dict(unregistered=True))
api("GET", "/notifications", "List/filter activity", None,
    dict(**page([dict(id="notification_001", category="BOOKINGS", event_type="BOOKING_ACCEPTED",
                     title="Booking accepted", body="Example Garage accepted your booking",
                     related=dict(type="BOOKING", id="booking_001"), is_read=False,
                     created_at="2026-10-08T16:00:00+05:30")]), unread_count=1),
    query="category=BOOKINGS&unread_only=true&page=1&page_size=20",
    rules="Omit category for All. unread_count is the count matching the selected category, independent of pagination.",
    errors="422 INVALID_CATEGORY")
api("PATCH", "/notifications/{notification_id}", "Mark notification read",
    dict(is_read=True), dict(id="notification_001", is_read=True, read_at="2026-10-08T16:05:00+05:30"),
    rules="is_read required and must be true for this contract.", errors="422 VALIDATION_ERROR")
api("POST", "/notifications/read-all", "Mark all/filtered activity read",
    dict(category="BOOKINGS"), dict(updated_count=5),
    rules="category optional; {} marks all categories. Operate on current customer's records only.",
    errors="422 INVALID_CATEGORY")

section("Garage conversations", [], [18], [
    "This is UI-required scope even though the workbook has no separate numbered messaging story.",
    "Start conversations using exactly one customer-owned booking_id or job_id. Derive the garage from that record. Reuse an existing conversation for the context; define continuity when a booking converts to a job.",
    "Only context participants can read/send. Proposed messages are plain text with maximum 2,000 characters. Post-completion/cancellation sending permissions need approval.",
    "client_message_id is required for sends and deduplicated per sender/conversation. Cursor pagination is chronological and stable. Matching garage-side participant APIs are required.",
])
api("POST", "/conversations", "Open or reuse contextual conversation",
    dict(booking_id="booking_001"), dict(id="conversation_001", garage_id="garage_001", booking_id="booking_001", job_id=None, can_send=True),
    status=201, rules="Exactly one booking_id or job_id required. Return 200 when reusing an existing conversation.",
    errors="422 CONVERSATION_CONTEXT_INVALID; 403 MESSAGING_NOT_ALLOWED")
api("GET", "/conversations", "List conversations", None,
    page([dict(id="conversation_001", garage_name="Example Garage", booking_id="booking_001",
               unread_count=1, last_message="Your appointment is confirmed")]), query="page=1&page_size=20")
api("GET", "/conversations/{conversation_id}/messages", "Read message history", None,
    dict(items=[dict(id="message_001", sender_role="GARAGE", text="Your appointment is confirmed",
                    created_at="2026-10-08T16:00:00+05:30")], next_cursor=None),
    query="limit=30", rules="cursor optional; limit proposed range 1..100.")
api("POST", "/conversations/{conversation_id}/messages", "Send customer message",
    dict(client_message_id="client_message_001", text="Thank you. I will arrive on time."),
    dict(id="message_002", sender_role="CUSTOMER", text="Thank you. I will arrive on time.", created_at="2026-10-08T16:10:00+05:30"),
    status=201, rules="Both fields required. sender_role and timestamp are server-controlled.",
    errors="409 CONVERSATION_CLOSED; 409 MESSAGE_ID_CONFLICT; 422 MESSAGE_INVALID")
api("POST", "/conversations/{conversation_id}/read", "Advance read marker",
    dict(last_read_message_id="message_001"), dict(last_read_message_id="message_001", unread_count=0),
    rules="last_read_message_id required and must belong to this conversation; markers cannot move backwards.",
    errors="422 MESSAGE_INVALID")

section("Ratings and reviews", [35, 36], [19], [
    "Only the customer owning a COMPLETED job may review it. Enforce one review per completed job; derive garage_id and customer_id server-side.",
    "rating is required integer 1..5; comment optional, proposed maximum 2,000 characters. Author may edit subject to an approved edit window.",
    "Examples propose PENDING moderation before publication and after editing. Public endpoints exclude unapproved content. Define rating aggregation and moderation policy before implementation.",
])
api("POST", "/jobs/{job_id}/review", "Submit rating/review",
    dict(rating=5, comment="Good service and clear communication."),
    dict(id="review_001", job_id="job_001", garage_id="garage_001", rating=5,
         comment="Good service and clear communication.", moderation_status="PENDING", published=False), status=201,
    errors="409 JOB_NOT_COMPLETED; 409 REVIEW_ALREADY_EXISTS; 422 REVIEW_INVALID")
api("GET", "/me/reviews", "View own reviews/edit eligibility", None,
    page([dict(id="review_001", job_id="job_001", garage_id="garage_001", rating=5,
               comment="Good service and clear communication.", moderation_status="PENDING", published=False, can_edit=True)]),
    query="page=1&page_size=20")
api("PATCH", "/reviews/{review_id}", "Edit own review",
    dict(rating=4, comment="Good service; delivery took longer than expected."),
    dict(id="review_001", rating=4, comment="Good service; delivery took longer than expected.",
         moderation_status="PENDING", published=False),
    rules="At least one of rating or comment required. Only author can edit.",
    errors="409 REVIEW_EDIT_WINDOW_CLOSED; 422 REVIEW_INVALID")

section("Help, policies and support", [37, 38], [20], [
    "Only published FAQs/help/privacy/terms are public. Version policies and preserve the accepted terms version on registration.",
    "Ticket requires category, subject and description. Proposed text limits: subject 200 characters; description 5,000; reply 2,000. Categories and attachment limits require approval.",
    "Optional linked booking/job/invoice/payment IDs must be owned by the customer and mutually consistent; general issues need no linked IDs.",
    "Customers view status and external replies only; they cannot set internal ticket status or access internal support notes. Reopening/closing policy requires approval.",
])
api("GET", "/faqs", "Read FAQs", None,
    page([dict(id="faq_001", question="How do I cancel a booking?",
               answer="Open the booking and select Cancel when cancellation is permitted.")]),
    access="Public", query="category=BOOKINGS&page=1&page_size=20", errors="422 VALIDATION_ERROR")
api("GET", "/content/{slug}", "Read published help/policies", None,
    dict(slug="privacy-policy", title="Privacy Policy", version="2026-10", content_format="plain_text",
         content="Published policy content", published_at="2026-10-01T09:00:00Z"),
    access="Public", rules="Supported slugs: help, privacy-policy, terms-and-conditions.",
    errors="404 CONTENT_NOT_FOUND")
api("POST", "/support/tickets", "Create support request",
    dict(category="PAYMENT", subject="Payment status not updated",
         description="Payment completed but the invoice still shows pending.",
         booking_id="booking_001", job_id="job_001", invoice_id="invoice_001", payment_id="payment_002", attachment_ids=[]),
    dict(id="ticket_001", reference="GFC-S-000001", status="OPEN", created_at="2026-10-09T12:40:00+05:30"),
    status=201, errors="422 LINKED_RECORD_INVALID; 422 ATTACHMENT_INVALID; 422 VALIDATION_ERROR")
api("GET", "/support/tickets", "List own tickets", None,
    page([dict(id="ticket_001", reference="GFC-S-000001", subject="Payment status not updated", status="OPEN")]),
    query="status=OPEN&page=1&page_size=20")
api("GET", "/support/tickets/{ticket_id}", "View ticket status/context", None,
    dict(id="ticket_001", category="PAYMENT", subject="Payment status not updated",
         description="Payment completed but the invoice still shows pending.", status="IN_PROGRESS",
         booking_id="booking_001", job_id="job_001", invoice_id="invoice_001", payment_id="payment_002", attachment_ids=[]))
api("GET", "/support/tickets/{ticket_id}/messages", "Read customer-visible support replies", None,
    dict(items=[dict(id="support_message_001", sender_role="SUPPORT", text="We are checking your payment.",
                    created_at="2026-10-09T13:00:00+05:30")], next_cursor=None),
    query="limit=30", rules="cursor optional; limit proposed range 1..100.")
api("POST", "/support/tickets/{ticket_id}/messages", "Reply to support",
    dict(client_message_id="support_client_message_001", text="Please share an update.", attachment_ids=[]),
    dict(id="support_message_002", sender_role="CUSTOMER", text="Please share an update.",
         created_at="2026-10-09T13:10:00+05:30"), status=201,
    rules="client_message_id and nonblank text required; attachment_ids optional and customer-owned.",
    errors="409 TICKET_REPLY_NOT_ALLOWED; 409 MESSAGE_ID_CONFLICT; 422 ATTACHMENT_INVALID")


def workbook_rows():
    source = Path("attached_assets/GoFixCarz_Customer_App_UI_and_User_Stories_1791365184539.xlsx")
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(source) as z:
        strings = ["".join(t.text or "" for t in item.findall(".//m:t", ns))
                   for item in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        sheets = []
        for name in ("sheet1", "sheet2"):
            rows = []
            for row in ET.fromstring(z.read(f"xl/worksheets/{name}.xml")).findall(".//m:row", ns):
                values = []
                for cell in row.findall("m:c", ns):
                    v = cell.find("m:v", ns)
                    value = v.text if v is not None else ""
                    values.append(strings[int(value)] if cell.get("t") == "s" else value)
                rows.append(values)
            sheets.append(rows[1:])
        return sheets


def make_documents():
    OUT.mkdir(exist_ok=True)
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(.7)
    sec.bottom_margin = Inches(.7)
    sec.left_margin = sec.right_margin = Inches(.7)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(6)
    for style in ["Heading 1", "Heading 2", "Heading 3"]:
        doc.styles[style].font.color.rgb = RGBColor.from_string("163B58")
    footer = sec.footer.paragraphs[0]
    footer.text = "GoFixCarz | Customer API Requirements | Draft for Client Approval | Page "
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    doc.core_properties.title = "GoFixCarz Customer API Requirements - Client Approval"
    doc.core_properties.subject = "Proposed endpoints, payloads, responses and approval decisions"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodySpec", fontName="Helvetica", fontSize=9, leading=12, spaceAfter=6))
    styles.add(ParagraphStyle(name="SmallSpec", fontName="Helvetica", fontSize=8, leading=10, spaceAfter=4))
    styles.add(ParagraphStyle(name="CodeSpec", fontName="Courier", fontSize=7, leading=8.5, spaceAfter=7,
                              backColor=colors.HexColor("#F2F5F8"), borderPadding=6))
    for name in ["Title", "Heading1", "Heading2", "Heading3"]:
        styles[name].textColor = colors.HexColor("#163B58")
    flow = []

    def p(text, small=False):
        doc.add_paragraph(text)
        flow.append(Paragraph(escape(text), styles["SmallSpec" if small else "BodySpec"]))

    def h(text, level=1):
        doc.add_heading(text, level=level)
        flow.append(Paragraph(escape(text), styles[f"Heading{level}"]))

    def br():
        doc.add_page_break()
        flow.append(PageBreak())

    def code(data):
        text = json.dumps(data, indent=2, ensure_ascii=True) if not isinstance(data, str) else data
        # Wrap visually in both formats; the underlying structured examples are separately validated.
        lines = []
        for line in text.splitlines():
            indent = len(line)-len(line.lstrip())
            lines.extend(textwrap.wrap(line, width=92, subsequent_indent=" "*(min(indent,12)+2),
                                       replace_whitespace=False, drop_whitespace=False) or [""])
        text = "\n".join(lines)
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(text)
        run.font.name = "Consolas"
        run.font.size = Pt(8)
        paragraph.paragraph_format.space_after = Pt(8)
        paragraph.paragraph_format.keep_together = True
        shade = OxmlElement("w:shd")
        shade.set(qn("w:fill"), "F2F5F8")
        paragraph._p.get_or_add_pPr().append(shade)
        flow.append(KeepTogether([Preformatted(text, styles["CodeSpec"])]))

    def table(headers, rows, widths):
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Light Shading Accent 1"
        for cell, value in zip(t.rows[0].cells, headers):
            cell.text = value
        for row in rows:
            for cell, value in zip(t.add_row().cells, row):
                cell.text = str(value)
        repeat = OxmlElement("w:tblHeader")
        t.rows[0]._tr.get_or_add_trPr().append(repeat)
        for row in t.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(8)
        data = [[Paragraph(escape(str(x)), styles["SmallSpec"]) for x in row] for row in [headers]+rows]
        pdf_t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        pdf_t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#DFEAF2")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LINEBELOW", (0,0), (-1,0), .5, colors.HexColor("#163B58")),
            ("GRID", (0,1), (-1,-1), .25, colors.HexColor("#D3DCE3")),
            ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ]))
        flow.extend([pdf_t, Spacer(1,10)])

    doc.add_heading("GoFixCarz", 0)
    doc.add_heading("Customer API Requirements", 0)
    flow.extend([Spacer(1,65), Paragraph("GoFixCarz", styles["Title"]),
                 Paragraph("Customer API Requirements", styles["Title"]), Spacer(1,18)])
    p("DRAFT FOR CLIENT APPROVAL")
    p("Version 1.0 | Prepared 7 October 2026")
    p("Request payloads, sample responses, business rules and approval decisions")
    p("Source: GoFixCarz Customer App UI and User Stories workbook - 38 user stories across 15 epics and 21 UI screens.")
    p("This document proposes the customer-app API contract. It does not certify existing implementation or authorize development, data changes, payment configuration or publishing.")
    p("All example people, contacts, identifiers, amounts and records are synthetic. Credential fields contain placeholders only.")
    p("Prepared for client review. Please approve the scope and resolve the decision register before implementation.")
    br()
    h("Contents")
    for text in ["1. Scope and conventions", "2. Endpoint index", "3. Detailed API contracts",
                 "4. Supporting garage and gateway contracts", "5. Existing-versus-proposed gap summary",
                 "6. Story and screen traceability", "7. Approval decision register", "8. Client sign-off"]:
        p(text)
    p("The detailed sections follow the index order. Word headings provide navigation; PDF bookmarks provide section navigation.")
    h("1. Scope and conventions")
    p(f"Proposed base path: {BASE}. Endpoint paths in the detailed sections are relative to this base unless explicitly stated otherwise.")
    p("Access: Public = no customer login; Customer = Authorization: Bearer <access_token>; Refresh/Recovery credential = the purpose-specific proof shown in the request. Every private record is scoped to the authenticated customer.")
    p("GET requests have no body. Path placeholders are required opaque IDs (UUIDs are recommended in implementation); example short IDs improve readability. Reject invalid IDs and unknown fields. Do not accept client ownership, role, status or monetary authority fields.")
    p("Default pagination: page=1, page_size=20; proposed bounds page >= 1 and page_size 1..100. Cursor-based message endpoints use opaque next_cursor. Lists show items and total; [] is a valid empty result.")
    p("Times are ISO 8601 with UTC Z or explicit offsets. Garage appointment rules use its IANA timezone. Monetary amounts are integer paise; currency is INR in these examples. Monetary precision and tax calculations are server-controlled.")
    p("POST creation normally returns 201; delivery requests return 202; reads/updates/actions return 200. Binary downloads do not use the JSON envelope. Provider acceptance is not confirmation of OTP delivery or payment settlement.")
    p("Shared JSON success envelope (all detailed JSON examples use this complete structure):")
    code(dict(success=True, message="Booking retrieved", data=dict(id="booking_001", status="PENDING")))
    p("Shared JSON error envelope:")
    code(dict(success=False, message="The selected slot is no longer available",
              error=dict(code="SLOT_UNAVAILABLE", details=dict(slot_id="slot_001"))))
    p("Every endpoint-specific error code below uses this envelope, with a clear safe message and relevant field details. Common errors: 401 AUTH_REQUIRED/SESSION_EXPIRED; 403 FORBIDDEN; 404 RESOURCE_NOT_FOUND; 422 VALIDATION_ERROR; 429 RATE_LIMITED. Return Retry-After for rate limits. Another customer's private record should appear as 404 to avoid existence leaks.")
    p("Examples are snapshots across a journey, not simultaneous records: booking_001 progresses from PENDING to ACCEPTED to CONVERTED; job_001 progresses to COMPLETED; invoice_001 moves from UNPAID to PAID after payment_002 succeeds. booking_002 illustrates an independent cancelled booking.")
    p("Priority: source stories remain Must Have or Should Have as recorded in the traceability appendix. UI-only items remain required for approval review rather than silently excluded. Password operations are explicitly conditional.")
    br()
    h("2. Endpoint index")
    index_rows = []
    num = 0
    for s in sections:
        for e in s["endpoints"]:
            num += 1
            e["id"] = f"API-{num:02d}"
            index_rows.append([e["id"], e["method"]+" "+e["path"], e["access"]])
    table(["ID", "Endpoint (relative to base path)", "Access"], index_rows, [46,340,109])
    br()
    h("3. Detailed API contracts")
    for s in sections:
        h(s["title"], 2)
        refs = ", ".join(f"US-{i}" for i in s["stories"]) or "UI-only requirement"
        p("Traceability: "+refs+" | "+", ".join(f"UI-{i:02d}" for i in s["screens"]), small=True)
        for rule in s["rules"]:
            p("• "+rule)
        for e in s["endpoints"]:
            h(e["id"]+" | "+e["title"], 3)
            p(e["method"]+" "+BASE+e["path"], small=True)
            p(f"Access: {e['access']} | Success HTTP: {e['status']}", small=True)
            if e["headers"]:
                p("Required extra header: "+e["headers"], small=True)
            if e["query"]:
                p("Sample query: ?"+e["query"], small=True)
            if e["rules"]:
                p("Fields and rules: "+e["rules"], small=True)
            p("Request payload:", small=True)
            code("No request body." if e["request"] is None else e["request"])
            p("Sample success response:", small=True)
            response = e["response"]
            code(response if isinstance(response,str) else dict(success=True, message=e["title"]+" successful", data=response))
            p("Representative failures: "+e["errors"]+". Common authentication/validation rules also apply where relevant.", small=True)
        br()
    h("4. Supporting garage and gateway contracts")
    p("These operations support the customer journey but are NOT customer mutation permissions.")
    h("Garage booking decisions and job creation", 2)
    p("The existing garage-scoped router contains the operations below. These are abbreviated illustrative examples, not exact reproductions of every current response field.")
    table(["Method / full path", "Request", "Illustrative response data"], [
        ["PATCH /api/v1/bookings/{booking_id}/accept", "No body", '{"id":"booking_001","status":"ACCEPTED"}'],
        ["PATCH /api/v1/bookings/{booking_id}/reject", "Currently no body", '{"id":"booking_001","status":"REJECTED"}'],
        ["POST /api/v1/bookings/{booking_id}/create-job", "No body", '{"id":"job_001","booking_id":"booking_001","status":"OPEN"}'],
    ], [230,95,170])
    p("Gap: rejection-reason support requires a reviewed garage contract extension, e.g. {\"reason\":\"Requested appointment unavailable\"}. Garage job status changes, invoice publication and replies require corresponding customer-visible read/events, not customer write access.")
    h("Payment provider callback", 2)
    p("Proposed full path: POST /api/v1/payment-webhooks/{provider}. Access: verified provider signature, not customer bearer authentication. The actual body and signature headers depend on the approved gateway.")
    p("Illustrative normalized event after provider-specific verification:")
    code(dict(event_id="gateway_event_001", event_type="payment.succeeded", provider_order_id="<provider_order_id>",
              provider_payment_id="<provider_payment_id>", amount=177000, currency="INR"))
    p("Sample acknowledgement: HTTP 200")
    code(dict(received=True))
    p("Failures: 400 INVALID_EVENT; 401 INVALID_SIGNATURE; 409 PAYMENT_MAPPING_MISMATCH. Deduplicate event_id, enforce permitted attempt transitions, verify amount/currency/order and update settlement transactionally. A repeated valid event returns the same acknowledgement without duplicating a charge.")
    h("Customer activity events", 2)
    p("Supporting events: BOOKING_ACCEPTED, BOOKING_REJECTED, JOB_CREATED, JOB_STATUS_CHANGED, INVOICE_PUBLISHED, PAYMENT_SUCCEEDED, PAYMENT_FAILED, MESSAGE_RECEIVED, REVIEW_MODERATED, SUPPORT_UPDATED. Events carry only authorized linked context and drive in-app records plus best-effort push. Event names are proposed, not existing implementation claims.")
    br()
    h("5. Existing-versus-proposed gap summary")
    table(["Area", "Observed baseline", "Required customer-app gap"], [
        ["Identity", "Existing garage-owned customer records are tenant-scoped management records.", "Separate verified customer identity and customer-scoped sessions; safe linking to garage records without granting garage/admin privileges."],
        ["Garage booking operations", "Garage list/detail/accept/reject/create-job routes exist.", "Customer request/quote/cancellation/discovery; verified ownership mapping; rejection reason and activity delivery."],
        ["Jobs and billing", "Owner-side modules cover jobs, vehicles and billing concepts.", "Read-only published customer projections and secure final invoice/PDF access; reuse suitable logic only after access review."],
        ["Other customer surfaces", "Not certified as customer contracts by this review.", "Customer discovery, payments, notifications, messaging, reviews and support need contract/implementation verification."],
    ], [95,185,215])
    p("This is a requirements review, not a complete implementation audit. No proposed route above is labelled implemented. Existing code may be reusable but its caller permissions and ownership model must be adapted and verified.")
    br()
    h("6. Story and screen traceability")
    story_rows, screen_rows = workbook_rows()
    assert len(story_rows)==38 and len(screen_rows)==21
    h("All 38 user stories", 2)
    rows = []
    for row in story_rows:
        sid = int(row[2].split("-")[1])
        matches = [s for s in sections if sid in s["stories"]]
        assert matches, row[2]
        endpoint_ids = [e["id"] for s in matches for e in s["endpoints"]]
        rows.append([row[2], row[1], row[5], ", ".join(endpoint_ids)])
    table(["Story", "Source epic", "Priority", "Covering API IDs"], rows, [43,115,65,272])
    p("Each story maps to the related feature group; the detailed group rules identify lifecycle, ownership and validation behavior. US-23 also depends on garage-only accept/reject operations and generated activity events.")
    h("All 21 UI screens", 2)
    rows = []
    for row in screen_rows:
        uid = int(row[0].split("-")[1])
        matches = [s for s in sections if uid in s["screens"]]
        assert matches, row[0]
        rows.append([row[0], row[2], ", ".join(e["id"] for s in matches for e in s["endpoints"])])
    table(["Screen", "Source screen", "Covering API IDs"], rows, [48,135,312])
    p("Explicit UI additions covered: profile photo; default vehicle; garage communication; review editing; activity filters. Booking Completed is derived from linked job completion.")
    br()
    h("7. Approval decision register")
    decisions = [
        ("D-01", "Registration contact", "Approve mobile OR email registration, or revise stories to mobile-required registration."),
        ("D-02", "Password option", "Include conditional password login/setup/recovery APIs or remove the password UI option."),
        ("D-03", "OTP and sessions", "Approve expiry, resend/attempt limits, refresh lifetime, recent-verification rules and contact-change protections."),
        ("D-04", "Scheduling", "Approve capacity model, quote expiry, slot reservation behavior and timezone rules. Proposed quote does not reserve a slot."),
        ("D-05", "Cancellation", "Approve pending-only cancellation or define accepted-booking cutoff/fees/refunds."),
        ("D-06", "Attachments", "Approve photo types, 5 MB/photo, five booking photos, support formats, scanning and retention."),
        ("D-07", "Payments", "Choose provider; approve retry/reconciliation, receipts, full/partial payment scope and refund display rules."),
        ("D-08", "Reviews", "Approve moderation-before-publication, re-moderation after edits, edit window and public reviewer display policy."),
        ("D-09", "Messaging", "Approve eligible contexts, post-completion/cancellation permissions, continuity on job conversion and retention."),
        ("D-10", "Support/content", "Approve categories/statuses, reply/closure policy, policy versions and content ownership."),
        ("D-11", "Vehicle ownership", "Approve linking verified customer identities to pre-existing garage vehicle/customer records; define duplicate and dispute handling."),
        ("D-12", "Billing publication", "Approve final invoice visibility, taxes/discounts and legal invoice fields. No historical bill repair is authorized."),
    ]
    table(["ID", "Decision", "Client confirmation required"], [list(x) for x in decisions], [44,112,339])
    p("All proposed defaults remain unapproved until confirmed. Open decisions may change request fields, endpoint behavior or delivery scope.")
    h("8. Client sign-off")
    p("Approval requested: customer API scope, story/UI coverage, payload/response direction, role boundaries and the decisions above.")
    p("Approval is for this requirements baseline only. Implementation effort, delivery schedule, provider costs and production changes require separate agreement.")
    for text in ["Client / organization: ____________________________________",
                 "Reviewer name / role: ___________________________________",
                 "Decision: Approve / Approve with changes / Revise",
                 "Approved decisions / requested changes: __________________",
                 "________________________________________________________",
                 "Signature / written approval reference: __________________",
                 "Approval date: __________________________________________"]:
        p(text)
    doc.save(OUT/"GoFixCarz_Customer_API_Requirements_Client_Approval.docx")

    def footer_pdf(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D3DCE3"))
        canvas.line(50,42,A4[0]-50,42)
        canvas.setFont("Helvetica",7)
        canvas.setFillColor(colors.HexColor("#52616E"))
        canvas.drawString(50,29,"GoFixCarz | Customer API Requirements | Draft for Client Approval")
        canvas.drawRightString(A4[0]-50,29,str(document.page))
        canvas.restoreState()

    class PDF(SimpleDocTemplate):
        def afterFlowable(self, item):
            if isinstance(item, Paragraph) and item.style.name in ("Heading1","Heading2"):
                key = "bookmark-"+str(self.seq.nextf("bookmark"))
                self.canv.bookmarkPage(key)
                level = 0 if item.style.name=="Heading1" else 1
                self.canv.addOutlineEntry(item.getPlainText(), key, level, False)

    pdf = PDF(str(OUT/"GoFixCarz_Customer_API_Requirements_Client_Approval.pdf"), pagesize=A4,
              rightMargin=50,leftMargin=50,topMargin=48,bottomMargin=55,
              title="GoFixCarz Customer API Requirements - Client Approval",author="GoFixCarz")
    pdf.build(flow, onFirstPage=footer_pdf, onLaterPages=footer_pdf)
    # Machine-readable source helps verify examples, without exposing credentials.
    (OUT/"customer-api-specification-source.json").write_text(json.dumps(sections, indent=2))
    print(f"Generated {num} proposed customer operations; 38 stories and 21 screens mapped.")


if __name__ == "__main__":
    make_documents()
