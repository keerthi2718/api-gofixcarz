"""Build a customer-only Word reference from live OpenAPI and captured test responses.

Generate sanitized samples first with CUSTOMER_CONTRACT_EXAMPLES pointing to
generated-artifacts/customer-contract-examples.json when running integration tests.
No production URL, credentials, OTPs or live customer data are required.
"""
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from datetime import date, timedelta
from docx import Document
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "artifacts/api-server"))
from app.main import app

BASE = "/api/v1/customer-app"
EXCLUDED = {"API-08", "API-09", "API-10", "API-11"}
AUTH = {"API-01", "API-02", "API-03", "API-04", "API-05", "API-06", "API-07",
        "API-12", "API-13", "API-14", "API-15"}
UUID_EXAMPLE = "11111111-1111-4111-8111-111111111111"
VALUES = {
    "name": "Demo Customer", "identifier": "+919000000001", "new_identifier": "+919000000002",
    "channel": "mobile", "purpose": "LOGIN", "terms_version": "2026-10", "terms_accepted": True,
    "otp": "012345", "device_name": "Customer Phone", "refresh_token": "<current_refresh_token>",
    "registration_number": "TS00AA0001", "brand": "Maruti Suzuki", "model": "Swift",
    "fuel_type": "PETROL", "year": 2023, "odometer_km": 25000,
    "line1": "Example Street", "city": "Hyderabad", "state": "Telangana",
    "postal_code": "500001", "country": "IN", "notes": "Please inspect engine noise",
    "reason": "Change of plans", "platform": "ANDROID", "push_token": "<device_push_token>",
    "client_message_id": "app-message-001", "text": "Please share an update.",
    "rating": 5, "comment": "Good service and clear communication.",
    "category": "GENERAL", "subject": "Service question", "description": "Please help with my service.",
    "is_read": True, "return_path": "/payments/result",
    "token_type": "Bearer", "access_token": "<customer_access_token>", "mobile": "+919000000001",
    "mobile_verified": True, "email_verified": False, "expires_in_seconds": 900,
    "resend_after_seconds": 30, "authenticated": True,
}


def resolve(schema, spec):
    if "$ref" in schema:
        return resolve(spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]], spec)
    if "anyOf" in schema:
        nonnull = next((s for s in schema["anyOf"] if s.get("type") != "null"), {})
        return resolve(nonnull, spec)
    if "allOf" in schema:
        return resolve(schema["allOf"][0], spec)
    return schema


def sample(schema, spec, name=""):
    schema = resolve(schema, spec)
    if name in VALUES:
        value = VALUES[name]
        if "enum" not in schema or value in schema["enum"]:
            return value
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if schema.get("format") == "uuid":
        return UUID_EXAMPLE
    if schema.get("format") == "date-time":
        return "2026-10-20T10:00:00+05:30"
    if schema.get("format") == "date":
        return (date.today() + timedelta(days=2)).isoformat()
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        result = {}
        for key, value in schema.get("properties", {}).items():
            if key in {"booking_id", "job_id", "invoice_id", "payment_id"} and "Ticket" in schema.get("title", ""):
                continue  # A valid general ticket needs no linked context.
            if key == "job_id" and schema.get("title") == "ConversationStart":
                continue
            result[key] = sample(value, spec, key)
        return result
    if kind == "array":
        if schema.get("default") == []:
            return []
        return [sample(schema.get("items", {}), spec)]
    if kind == "integer":
        return schema.get("default", max(1, schema.get("minimum", 1)))
    if kind == "number":
        return schema.get("default", schema.get("minimum", 1))
    if kind == "boolean":
        return schema.get("default", True)
    if kind == "null":
        return None
    return "<value>"


def describe(schema, spec):
    original = schema
    schema = resolve(schema, spec)
    kind = schema.get("format") or schema.get("type", "object")
    if schema.get("type") == "array":
        kind = "array of " + describe(schema.get("items", {}), spec)
    constraints = []
    for key, label in (("minimum", "min"), ("maximum", "max"), ("minLength", "min characters"),
                       ("maxLength", "max characters"), ("minItems", "min items"), ("maxItems", "max items")):
        if key in schema:
            constraints.append(f"{label}: {schema[key]}")
    if "enum" in schema:
        constraints.append("values: " + ", ".join(map(str, schema["enum"])))
    if "const" in schema:
        constraints.append("must be " + str(schema["const"]).lower())
    if "pattern" in schema:
        constraints.append("pattern: " + schema["pattern"])
    if any(item.get("type") == "null" for item in original.get("anyOf", [])):
        constraints.append("nullable")
    return kind + ("; " + "; ".join(constraints) if constraints else "")


def code(doc, value):
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
    for line in text.splitlines():
        paragraph = doc.add_paragraph(style="No Spacing")
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(line)
        run.font.name = "Consolas"
        run.font.size = Pt(8)
    doc.add_paragraph()


def table(doc, headers, rows):
    result = doc.add_table(rows=1, cols=len(headers))
    result.style = "Light Shading Accent 1"
    for cell, text in zip(result.rows[0].cells, headers):
        cell.text = text
    for row in rows:
        for cell, text in zip(result.add_row().cells, row):
            cell.text = str(text)


POLICIES = {
    "Vehicles and service history": "Vehicles are account-owned, with one default whenever active vehicles exist. Registration is normalized to 4–20 uppercase letters/digits. Archival preserves history; active work blocks removal. No phone/registration matching claims historical garage records. First default replacement is the oldest remaining active vehicle.",
    "Secure attachments": "Private existing S3 storage; JPEG/PNG/WebP only, maximum 5 MiB (5,242,880 bytes) and 20 million decoded pixels. Single-frame images are decoded and re-encoded without metadata. No arbitrary PDFs/executables or antivirus-service claim. Support attachments use these same image rules. Bookings/tickets accept up to five attachments. Linked files cannot be deleted. DELETE transactionally revokes access; physical S3 removal awaits an approved retention/cleanup policy.",
    "Availability and booking summary": "Owners configure explicit non-overlapping slots with IANA timezone and capacity. No invented availability. Services require positive duration and active state. Quotes expire after 10 minutes and do not reserve capacity. Submission locks the slot, rechecks ownership/capacity/service price/duration and creates a new explicitly linked garage contact/vehicle for new work only.",
    "Booking management": "Only future PENDING bookings with no linked job can be cancelled. A background worker expires unattended PENDING appointments after their start time, running every 60 seconds in batches of 100. Past pending appointments cannot be accepted or converted. Garages accept/reject/convert through their separate APIs. Idempotency-Key is required for submission; replay returns the stored original response, even if later booking state changes. A changed payload with the same key returns 409.",
    "Published job tracking - read only": "Job status/timestamps come from explicitly linked garage jobs. Details expose only a garage-published whitelisted projection. Raw inspection/billing/internal notes and staff identifiers are excluded. Legacy timeline notes have no publication flag and are omitted. Published photos are authenticated binary downloads.",
    "Invoices and secure PDF downloads": "Only owned, issued final invoices for completed jobs are exposed. Owner publication computes subtotal + tax - discount in integer INR paise. Payment state comes from confirmed payment/refund records, not job amounts or an invoice PAID label. PDFs are development invoice representations; legal tax-invoice fields require production billing review.",
    "Payments and safe retries": "Razorpay remains the selected provider, but checkout integration is pending by explicit user choice. API-41 returns 503 PAYMENT_PROVIDER_NOT_CONFIGURED after authentication and invoice ownership validation; it does not create an order or accept a payment. The three read endpoints work only with existing trusted financial records. Receipt is a PDF and requires a CAPTURED record.",
    "Notifications and unified activity center": "In-app activity is persisted independently of push. Booking decisions, job status/publication, invoice publication, garage replies, review and support actions create activity. Push-token registration is stored and logout detaches it; push delivery itself is not configured and is explicitly reported as false. No payment-outcome webhook is claimed while Razorpay is pending.",
    "Garage conversations": "Exactly one owned booking/job context; a converted booking reuses the same conversation. Text is limited to 2,000 characters. Messages are idempotent by participant/conversation/client_message_id and cursor order is stable. Completed/cancelled jobs and rejected/cancelled/expired bookings are read-only. Read markers cannot move backwards.",
    "Ratings and reviews": "One review per owned completed job; integer rating 1–5, optional comment up to 2,000 characters. Editing is allowed for seven days from creation and returns the review to PENDING moderation. Admin moderation is role- and garage-scope-protected. This customer document does not include public review browsing.",
    "Customer support tickets and replies": "Categories: GENERAL, BOOKING, SERVICE, PAYMENT, ACCOUNT, TECHNICAL. Subject 200, description 5,000, reply 2,000 characters. Optional linked contexts must be owned and consistent. Only external customer/admin replies are returned. CLOSED/RESOLVED tickets are read-only; only authorized admin support can update status.",
}


def main():
    spec = app.openapi()
    groups = json.loads((ROOT / "documents/customer-only-api-specification-source.json").read_text())
    examples_path = ROOT / "generated-artifacts/customer-contract-examples.json"
    examples = json.loads(examples_path.read_text())
    doc = Document()
    section = doc.sections[0]
    section.top_margin = section.bottom_margin = Inches(.65)
    section.left_margin = section.right_margin = Inches(.7)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(10)
    normal.paragraph_format.space_after = Pt(5)
    doc.add_heading("GoFixCarz Customer API Reference", 0)
    doc.add_paragraph("Implemented development contracts • Customer-only • October 2026")
    doc.add_heading("Scope and implementation status", 1)
    doc.add_paragraph(
        "58 applicable operations from the customer-only approval inventory, plus one supporting private job-photo download. "
        "57 inventory operations are implemented; API-41 checkout creation is intentionally pending Razorpay. "
        "Including the photo download, 58 operational endpoints and one explicit pending endpoint are registered. "
        "The four conditional password operations are excluded because mobile-only OTP was approved.")
    doc.add_paragraph(
        "This is a development implementation, not production deployment or approval. Development database migration only. "
        "Tests use real development PostgreSQL with mocked SMS and S3; live SMS, AWS access, push delivery, "
        "and Razorpay checkout are not verified by these tests.")
    doc.add_heading("Base URL and common headers", 1)
    code(doc, "<API_ORIGIN>/api/v1/customer-app")
    doc.add_paragraph("Use the configured API origin. No production hostname is assumed. Interactive documentation: /api/docs.")
    table(doc, ["Header", "When required"], [
        ["Authorization: Bearer <customer_access_token>", "All protected customer calls; never use garage/admin tokens."],
        ["Content-Type: application/json", "JSON requests with a body."],
        ["Content-Type: multipart/form-data; boundary=…", "Attachment upload; let the HTTP client set the boundary."],
        ["Idempotency-Key: <unique-operation-key>", "Booking submission and pending payment-attempt creation."],
        ["Accept: application/json", "JSON endpoints. Binary endpoints use image/* or application/pdf."],
        ["X-Device-ID: <stable-installation-id>", "Optional OTP/refresh abuse-limit signal; not an authentication credential."],
    ])
    doc.add_paragraph("All customer responses, including errors, use Cache-Control: no-store. IDs are UUIDs unless explicitly stated. "
                      "Keep tokens/OTPs out of URLs and logs. Every money amount is integer paise in INR.")
    doc.add_heading("Response envelope and errors", 1)
    code(doc, {"success": True, "message": "Success", "data": {}, "errors": [], "status_code": 200})
    code(doc, {"success": False, "message": "RESOURCE_NOT_FOUND", "data": None,
               "errors": [{"code": "RESOURCE_NOT_FOUND"}], "status_code": 404})
    doc.add_paragraph("Validation errors use errors entries with field and message instead of code. "
                      "The global per-IP traffic limiter may return its own 429 JSON format; clients must handle "
                      "429 by HTTP status, not assume every infrastructure error uses this envelope. "
                      "Binary image/PDF responses are not JSON envelopes.")
    doc.add_paragraph("Common failures: 401 invalid/revoked/expired session; 404 missing or non-owned resource; "
                      "409 workflow, duplicate, capacity or idempotency conflict; 422 invalid fields. "
                      "Attachment failures add 413 size, 415 format, and 503 storage unavailable. "
                      "OTP flows add 400 proof failures, 403 recent authentication, 429 abuse/cooldown and 503 submission failure.")
    doc.add_heading("Authentication rules", 1)
    doc.add_paragraph("Mobile-only Indian +91 numbers beginning with 6–9. OTP expiry five minutes; resend cooldown 30 seconds; "
                      "five cumulative guesses per live resend chain. Access tokens 15 minutes; rotating sessions have an "
                      "absolute 30-day lifetime. Reused refresh credentials revoke the session. New-mobile change requires "
                      "OTP authentication within 15 minutes and preserves the old mobile until verification. Email and password login are not supported.")
    doc.add_heading("Endpoint index", 1)
    index = []
    for group in groups:
        for e in group["endpoints"]:
            if e["id"] not in EXCLUDED:
                index.append([e["id"], e["method"], e["path"], "PENDING Razorpay" if e["id"] == "API-41" else "Implemented"])
    index.append(["Supporting", "GET", "/jobs/{job_id}/photos/{photo_index}", "Implemented"])
    table(doc, ["ID", "Method", "Relative endpoint", "Status"], index)
    for group in groups:
        entries = [e for e in group["endpoints"] if e["id"] not in EXCLUDED]
        if not entries:
            continue
        doc.add_page_break()
        doc.add_heading(group["title"], 1)
        if group["title"] in POLICIES:
            doc.add_paragraph(POLICIES[group["title"]])
        for e in entries:
            write_endpoint(doc, e, spec, examples)
    doc.add_page_break()
    doc.add_heading("Supporting private job-photo download", 1)
    write_endpoint(doc, {"id": "Supporting", "method": "GET", "path": "/jobs/{job_id}/photos/{photo_index}",
                         "title": "Download an authorized published garage job photo"}, spec, examples)
    doc.add_heading("Excluded and pending work", 1)
    doc.add_paragraph("API-08–11 password flows remain deliberately excluded. Razorpay order creation, callbacks/webhooks, "
                      "gateway verification, refunds, live push delivery and production rollout are not implemented or claimed. "
                      "Garage/admin participant endpoints exist separately to configure slots, publish customer job/invoice data, "
                      "reply to conversations/support, and moderate reviews. Their URLs are deliberately excluded from this customer-only catalogue.")
    output = ROOT / "generated-artifacts/GoFixCarz_Customer_API_Reference.docx"
    doc.save(output)
    manifest = {"registered_operations": len(index), "applicable_inventory_operations": 58,
                "implemented_inventory_operations": 57, "pending": ["API-41"], "excluded": sorted(EXCLUDED)}
    (ROOT / "generated-artifacts/customer-reference-coverage.json").write_text(json.dumps(manifest, indent=2))
    print(f"Saved {output.relative_to(ROOT)} with {len(index)} endpoint descriptions.")


def write_endpoint(doc, endpoint, spec, examples):
    method, path = endpoint["method"], BASE + endpoint["path"]
    operation = spec["paths"][path][method.lower()]
    doc.add_heading(f"{endpoint['id']} — {endpoint['title']}", 2)
    code(doc, method + " " + path)
    protected = endpoint["id"] not in {"API-01", "API-02", "API-03", "API-04", "API-05"}
    doc.add_paragraph("Status: pending Razorpay checkout integration." if endpoint["id"] == "API-41" else "Status: implemented.")
    doc.add_heading("Headers", 3)
    headers = ["Accept: " + ("application/pdf" if path.endswith(("/pdf", "/receipt")) else
                            "image/*" if "/photos/" in path or path.endswith("/download") else "application/json")]
    if protected:
        headers.append("Authorization: Bearer <customer_access_token>")
    elif endpoint["id"] == "API-03":
        headers.append("Authorization: Bearer <customer_access_token> (required only for contact-change resend)")
    body = operation.get("requestBody", {})
    if body:
        headers.append("Content-Type: " + next(iter(body["content"])))
    for param in operation.get("parameters", []):
        if param["in"] == "header":
            headers.append(param["name"] + ": <value>" + (" (required)" if param.get("required") else " (optional)"))
    if endpoint["id"] in {"API-01", "API-02", "API-03", "API-04", "API-05"}:
        headers.append("X-Device-ID: <stable-installation-id> (optional)")
    code(doc, "\n".join(headers))
    params = [p for p in operation.get("parameters", []) if p["in"] in {"query", "path"}]
    if params:
        doc.add_heading("Path and query parameters", 3)
        table(doc, ["Name", "Location", "Required", "Type / constraints"],
              [[p["name"], p["in"], "Yes" if p.get("required") else "No", describe(p["schema"], spec)] for p in params])
    doc.add_heading("Payload", 3)
    if body:
        mime, content = next(iter(body["content"].items()))
        schema = resolve(content["schema"], spec)
        if mime == "multipart/form-data":
            code(doc, "file=<binary JPEG/PNG/WebP image>\npurpose=BOOKING_PHOTO")
        else:
            payload = sample(schema, spec)
            if endpoint["id"] == "API-21":
                payload = {"odometer_km": 26000}
            if endpoint["id"] == "API-13":
                payload.pop("name", None)
                payload["name"] = "Demo Customer"
            code(doc, payload)
        properties = schema.get("properties", {})
        table(doc, ["Field", "Required", "Type / constraints"],
              [[name, "Yes" if name in schema.get("required", []) else "No", describe(field, spec)]
               for name, field in properties.items()])
        doc.add_paragraph("Unknown fields are rejected. Omitted PATCH fields stay unchanged; nullable fields may be cleared. "
                          "Server-controlled ownership, roles, status and financial totals cannot be supplied.")
    else:
        doc.add_paragraph("No request body.")
    if endpoint["id"] == "API-28":
        doc.add_paragraph("Repeat service_ids for multiple services: ?date=2026-10-20&service_ids=<uuid>&service_ids=<uuid>.")
    if endpoint["id"] == "API-41":
        doc.add_paragraph("Body may be {}. return_path, if provided, must be /payments/result. No order or checkout fields are returned while pending.")
    doc.add_heading("Response", 3)
    entries = examples.get(method + " " + path, [])
    success = next((entry for entry in entries if 200 <= entry["status"] < 300), None)
    if endpoint["id"] == "API-41":
        success = next((entry for entry in entries if entry["status"] == 503), None)
    if success:
        doc.add_paragraph(f"HTTP {success['status']}. Example captured from development integration tests "
                          "(fictional test records; IDs vary).")
        code(doc, success["body"])
    elif endpoint["id"] in AUTH:
        response_code = next(code for code in operation["responses"] if code.startswith("2"))
        schema = operation["responses"][response_code]["content"]["application/json"]["schema"]
        generated = sample(schema, spec)
        if isinstance(generated, dict):
            generated["success"], generated["status_code"], generated["errors"] = True, int(response_code), []
            generated["message"] = "Success"
            if isinstance(generated.get("data"), dict):
                if endpoint["id"] in {"API-01", "API-02", "API-03", "API-14"}:
                    generated["data"]["expires_in_seconds"] = 300
                if endpoint["id"] in {"API-01", "API-02", "API-03"}:
                    generated["data"]["purpose"] = "REGISTER" if endpoint["id"] == "API-01" else "LOGIN"
                if endpoint["id"] == "API-12":
                    generated["data"]["photo"] = None
        doc.add_paragraph(f"HTTP {response_code}. Schema-derived example; tokens shown as placeholders.")
        code(doc, generated)
    else:
        raise RuntimeError(f"Missing successful captured response for {method} {path}")
    failures = [entry for entry in entries if entry["status"] >= 400]
    if failures and endpoint["id"] != "API-41":
        doc.add_heading("Example failure", 3)
        code(doc, failures[0]["body"])
    if endpoint["id"] == "API-03":
        doc.add_paragraph("Resending returns a NEW challenge ID and invalidates the previous one; persist the replacement ID.")
    if endpoint["id"] in {"API-04", "API-05"}:
        doc.add_paragraph("Store the latest refresh token securely and discard its predecessor. Serialize refresh requests; replay revokes the session.")
    if endpoint["id"] == "API-15":
        doc.add_paragraph("Verification is bound to the initiating session. The old mobile is replaced only after success; other sessions are revoked.")


if __name__ == "__main__":
    main()
