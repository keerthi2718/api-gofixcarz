"""Generate a matching Word/PDF reference from OpenAPI and sanitized test captures."""
import json
import re
import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "artifacts/api-server"))
from app.main import app
from approval_document_writer import ApprovalWriter
from build_customer_implemented_reference import resolve, describe

OUT = ROOT / "generated-artifacts"
BASE = "/api/v1/admin"
ROUTES = [
    ("GET", "/garages", "List garages, now including job_card_count", "garages.read"),
    ("GET", "/garages/{garage_id}", "Garage details and legacy recorded-amount totals", "garages.read"),
    ("GET", "/garages/{garage_id}/metrics", "Garage operational metrics", "garages.read"),
    ("GET", "/garages/{garage_id}/job-card-count", "Filtered garage job-card count", "garages.read"),
    ("GET", "/jobs/{job_id}", "Individual job-card details", "jobs.read"),
    ("PATCH", "/garages/{garage_id}", "Update garage details and/or operational/verification state", "garages.update; state fields additionally require garages.status.write / garages.verify"),
    ("PATCH", "/garages/{garage_id}/status", "Existing activation/suspension action", "garages.status.write"),
    ("PATCH", "/garages/{garage_id}/verification", "Existing approval/verification action", "garages.verify"),
    ("GET", "/invitations", "List invitations", "Platform CEO security operator"),
    ("POST", "/invitations", "Create a manual invitation", "Platform CEO security operator"),
    ("POST", "/invitations/{invitation_id}/resend", "Rotate proof and renew a pending invitation", "Platform CEO security operator"),
    ("DELETE", "/invitations/{invitation_id}", "Revoke an invitation without deleting audit history", "Platform CEO security operator"),
    ("POST", "/admin-invitations/accept", "Accept an invitation and create the frozen staff identity", "Single-use invitation proof; no existing session"),
    ("GET", "/roles", "List system and custom roles", "security.read"),
    ("POST", "/roles", "Create a custom role", "Platform CEO security operator"),
    ("PATCH", "/roles/{role_id}", "Update a custom role", "Platform CEO security operator"),
    ("DELETE", "/roles/{role_id}", "Delete an unused custom role", "Platform CEO security operator"),
    ("PUT", "/staff/{admin_id}/roles", "Assign roles and garage/platform scope", "Platform CEO security operator"),
    ("GET", "/notifications", "List admin-monitored notification records", "notifications.read"),
    ("GET", "/notifications/{notification_id}", "Inspect one notification", "notifications.read"),
    ("GET", "/support-tickets", "List support tickets (alias of /support/tickets)", "support.read"),
    ("GET", "/support-tickets/{ticket_id}", "Support ticket details", "support.read"),
    ("PATCH", "/support-tickets/{ticket_id}/assignment", "Assign support staff", "support.assign"),
    ("PATCH", "/support-tickets/{ticket_id}/priority", "Change ticket priority", "support.manage"),
    ("PATCH", "/support-tickets/{ticket_id}/status", "Transition a ticket", "support.manage"),
    ("GET", "/support-tickets/{ticket_id}/messages", "Read support messages", "support.read"),
    ("POST", "/support-tickets/{ticket_id}/messages", "Reply to support", "support.reply"),
    ("GET", "/reports/garage-performance", "Paginated garage/date/job-status performance", "reports.export + garages.read + jobs.read"),
]


def full_path(path):
    return "/api/v1" + path if path == "/admin-invitations/accept" else BASE + path


def captures(method, path, examples):
    regex = "^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(path)) + "$"
    found = []
    for key, entries in examples.items():
        m, route = key.split(" ", 1)
        if m == method and re.match(regex, route):
            found.extend(entries)
    return found


def main():
    spec = app.openapi()
    examples = json.loads((OUT / "admin-management-examples.json").read_text())
    writer = ApprovalWriter("Admin API Updates — Endpoint, Payload & Response Reference",
                            footer_label="Admin API Updates | Development reference")
    writer.cover()
    writer.p(f"Prepared {date.today().isoformat()} | Implemented development contracts | Not yet published")
    writer.p("All records and amounts are synthetic rollback-isolated test fixtures. Dynamic IDs vary between captures; "
             "examples are not a single importable dataset. Credentials and invitation proofs are placeholders only.")
    writer.p("Scope: the requested admin metrics/counts, job details, garage actions, invitations, custom roles, "
             "notifications, support tickets and filtered performance reports. Private admin sign-in URLs are deliberately omitted.")
    writer.h("Contents")
    for text in ["1. Common headers and response format", "2. Permissions and lifecycle rules",
                 "3. Endpoint index", "4. Detailed contracts", "5. Verification and rollout limits"]:
        writer.p(text)
    writer.h("1. Common headers and response format")
    writer.code("Base: <API_ORIGIN>/api/v1/admin\n"
                "Authorization: Bearer <admin_access_token>\nAccept: application/json\n"
                "Content-Type: application/json  (only requests with a JSON body)")
    writer.p("Use a dedicated active admin session, not a garage-owner/customer JWT. All returned data is scoped to permitted garages. "
             "No body is sent on GET. DELETE role/invitation operations intentionally require the documented JSON version/reason body. "
             "The invitation acceptance endpoint uses /api/v1/admin-invitations/accept and a proof instead of an existing session.")
    writer.code({"success": True, "message": "Success", "data": {}, "errors": [], "status_code": 200})
    writer.code({"success": False, "message": "VERSION_CONFLICT", "data": None,
                 "errors": [{"code": "VERSION_CONFLICT"}], "status_code": 409})
    writer.p("Common failures: 401 invalid/missing/revoked session; 403 missing permission/garage scope or required recent MFA; "
             "404 missing or inaccessible record; 409 lifecycle/version/duplicate conflict; 422 field or unsupported query validation. "
             "Date-order errors retain HTTP 400. Rate limits use HTTP 429; infrastructure rate-limit JSON may differ from the app envelope. "
             "Some privacy-filtered messages and error entries can be redacted.")
    writer.h("2. Permissions and lifecycle rules")
    rules = [
        "Security management is restricted to a dedicated active role_ceo account with PLATFORM scope and security.manage. "
        "When the existing ADMIN_MFA_REQUIRED policy is enabled, writes require MFA within five minutes. This update does not enable mandatory MFA.",
        "System roles cannot be edited/deleted. Custom role permissions must be known, unique permission codes. Names are case-insensitively unique. "
        "Custom roles are resolved from persistent definitions on every request, so an edit changes existing sessions' permissions without trusting JWT role caches.",
        "Staff assignment accepts built-in/custom role IDs and revokes that staff member's existing sessions. Self-assignment changes and removing the last active CEO remain blocked. "
        "A custom role cannot be deleted while assigned to any account or a live pending invitation.",
        "Invitations are MANUAL: email_sent is false. An authorized operator securely shares the one-time invitation_token and invitation ID. "
        "No email provider, email send, public administrator registration, or invitation UI is claimed. Never log proof values or put them in URL query strings.",
        "Invitation proofs expire after 24 hours and are stored only as SHA-256 hashes. Tokens are returned only at creation/resend, never in listing/audits. "
        "Resend rotates the proof, invalidates its predecessor, renews expiry and enforces a 60-second cooldown. Acceptance is single-use and validates the issuer is still an active platform CEO.",
        "Acceptance creates only the stored invitation identity/roles/scope. The client cannot submit alternative permissions, email or scope. "
        "Passwords contain 16–128 characters and use the existing scrypt admin password hashing. Acceptance does not bypass the normal login/MFA policy or issue a session.",
        "PENDING invitations can be revoked, including expired pending invitations. ACCEPTED/REVOKED invitations cannot be resent. "
        "Expired state is derived from expiry time; renewal is refused if another live invitation or account now owns the email.",
        "Garage actions require reason and expected_version. Use the current response version, not a fixed 1. A successful write increments it; "
        "a stale version returns 409. Ownership/user_id, arbitrary columns and job data cannot be changed through the garage PATCH.",
        "Garage operational states: ACTIVE/SUSPENDED. Verification: UNVERIFIED/VERIFIED/REJECTED. Approval means VERIFIED, not a new APPROVED enum. "
        "The generic PATCH additionally checks state-specific permissions if those fields are included.",
        "job_card_count is computed from non-deleted jobs, not cached. The list has a count per returned garage. Metrics/count/report endpoints "
        "accept garage/date/timezone/current job status filters. status refers to a JOB state, not garage activation. Dates filter job.created_at; "
        "both date endpoints are inclusive in the supplied IANA timezone. At most a 366-day difference is accepted when both endpoints are given.",
        "Job states: OPEN, IN_PROGRESS, WAITING_FOR_PARTS, QUALITY_CHECK, READY, COMPLETED, CANCELLED. "
        "Garage metrics/report totals are operational counts, not captured payment revenue. booking_count has its own booking.created_at date cohort and ignores the job-status filter.",
        "Garage-performance reports include zero-count scoped garages and paginate by garage name/ID. "
        "Existing garage details retain recorded total_revenue semantics, not evidence of gateway settlement; restricted finance fields are redacted for non-finance admins.",
        "The /support-tickets endpoints reuse the exact /support/tickets handlers and authorization; old clients remain compatible. "
        "These source-backed admin support records are distinct from customer-app /customer-support/tickets records.",
        "Support transitions: OPEN to IN_PROGRESS/WAITING_FOR_CUSTOMER/RESOLVED; IN_PROGRESS to WAITING_FOR_CUSTOMER/RESOLVED; "
        "WAITING_FOR_CUSTOMER to IN_PROGRESS/RESOLVED; RESOLVED to IN_PROGRESS/CLOSED; CLOSED is terminal. "
        "Resolution is required for RESOLVED/CLOSED. Message retries reuse client_message_id; changed text with the same ID returns 409.",
    ]
    for rule in rules:
        writer.p(rule)
    writer.h("3. Endpoint index")
    writer.table(["ID", "Method / endpoint"], [
        [f"A-{i:02d}", method + " " + full_path(path)] for i, (method, path, _, _) in enumerate(ROUTES, 1)
    ], [45, 450])
    writer.br()
    writer.h("4. Detailed contracts")
    records = []

    def code(value):
        # Keep JSON readable while allowing long records to span PDF pages.
        text = value if isinstance(value, str) else json.dumps(value, indent=2)
        lines = text.splitlines()
        for start in range(0, len(lines), 42):
            writer.code("\n".join(lines[start:start+42]))

    for index, (method, path, title, permission) in enumerate(ROUTES, 1):
        full = full_path(path)
        op = spec["paths"][full][method.lower()]
        candidates = captures(method, path, examples)
        success = next((x for x in candidates if 200 <= x["status"] < 300), None)
        if success is None:
            raise RuntimeError("Missing successful captured example: " + method + " " + path)
        writer.h(f"A-{index:02d} | {title}", 2)
        code(method + " " + full)
        writer.p("Required access: " + permission)
        if path != "/admin-invitations/accept":
            code("Authorization: Bearer <admin_access_token>\nAccept: application/json"
                 + ("\nContent-Type: application/json" if op.get("requestBody") else ""))
        else:
            code("Accept: application/json\nContent-Type: application/json")
        params = [p for p in op.get("parameters", []) if p["in"] in {"path", "query"}]
        if params:
            writer.table(["Parameter", "Location / required", "Type / constraints"], [
                [p["name"], p["in"] + (" / Yes" if p.get("required") else " / No"), describe(p["schema"], spec)]
                for p in params], [100, 95, 300])
        if success.get("query"):
            writer.p("Captured query example: " + "&".join(f"{k}={v}" for k, v in success["query"].items()))
        body = op.get("requestBody")
        writer.p("Request payload:")
        if body:
            schema = resolve(next(iter(body["content"].values()))["schema"], spec)
            rows = []
            for field, value in schema.get("properties", {}).items():
                rows.append([field, "Yes" if field in schema.get("required", []) else "No", describe(value, spec)])
                child = resolve(value, spec)
                for subfield, subschema in child.get("properties", {}).items():
                    rows.append([field + "." + subfield,
                                 "Yes if parent present" if subfield in child.get("required", []) else "No",
                                 describe(subschema, spec)])
            writer.table(["Field", "Required", "Type / constraints"], rows, [110, 100, 285])
            code(success["request"])
        else:
            writer.p("No request body.")
        writer.p(f"Sample success response: HTTP {success['status']}. Captured from fictional integration fixtures.")
        code(success["response"])
        failure = next((x for x in candidates if x["status"] >= 400), None)
        writer.p("Sample error response:")
        if failure:
            writer.p(f"HTTP {failure['status']} — captured development error.")
            code(failure["response"])
        else:
            status = 400 if path == "/admin-invitations/accept" else 401
            label = "INVITATION_INVALID_OR_EXPIRED" if status == 400 else "Authentication required."
            writer.p(f"HTTP {status} — illustrative common failure; safe message may vary.")
            code({"success": False, "message": label, "data": None, "errors": [], "status_code": status})
        records.append({"method": method, "path": full, "purpose": title,
                        "access": permission, "example": success})
    writer.h("5. Verification and rollout limits")
    writer.p("Admin integration checks use the development PostgreSQL database with rollback-isolated synthetic records. "
             "No actual staff invitation was sent, no administrator was provisioned permanently, no production data/schema was changed, "
             "and no live mail provider or gateway was contacted. Runtime startup and health are checked separately. "
             "These API changes require publishing before they appear in production.")
    writer.p("Persistence reuses the existing admin resource store for custom-role definitions and hashed invitation workflows. "
             "No schema migration is required by these changes. Deletion revokes invitations or archives role definitions; audit records are retained.")
    writer.save(OUT / "GoFixCarz_Admin_API_Updates_Reference")
    (OUT / "admin-management-contract-reference.json").write_text(json.dumps(records, indent=2))
    print(f"Generated matching Word/PDF for {len(ROUTES)} contracts.")


if __name__ == "__main__":
    main()
