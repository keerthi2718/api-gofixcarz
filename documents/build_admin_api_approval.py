"""Admin-only approval requirements derived from the attached 29-story CSV."""
import csv
import json
from pathlib import Path
from approval_document_writer import ApprovalWriter

BASE = "/api/v1/admin"
SOURCE = Path("attached_assets/GoFixCarz_Admin_User_Stories_1791436872802.csv")
STEM = "documents/GoFixCarz_Admin_Only_APIs_Client_Approval"
groups = []


def group(title, stories, rules):
    groups.append(dict(title=title,stories=stories,rules=rules,endpoints=[]))


def api(method,path,title,request,response,permission,*,status=200,query="",rules="",errors="404 RESOURCE_NOT_FOUND",private=False,headers=""):
    groups[-1]["endpoints"].append(dict(method=method,path=path,title=title,request=request,response=response,
        permission=permission,status=status,query=query,rules=rules,errors=errors,private=private,headers=headers))


def page(items):
    return dict(items=items,page=1,page_size=20,total=len(items))


FILTERS = dict(date_from="2026-10-01",date_to="2026-10-08",timezone="Asia/Kolkata",city="Hyderabad",garage_id=None,service_id=None)
QUERY = "date_from=2026-10-01&date_to=2026-10-08&timezone=Asia%2FKolkata&city=Hyderabad"
META = dict(filters=FILTERS,snapshot_id="snapshot_001",generated_at="2026-10-08T15:00:00+05:30")
STATUSES = dict(OPEN=3,IN_PROGRESS=7,WAITING_FOR_PARTS=4,QUALITY_CHECK=2,READY=1,COMPLETED=30,CANCELLED=3)

group("Secure admin access - private route locations withheld",[1],[
    "The CSV requires secure login with MFA/OTP support and secure expiry. Shared documents must not reveal the private admin sign-in location. Logical operations below intentionally have no URL; location and security configuration are distributed privately.",
    "Admin accounts are separate from garage-owner/customer identities. No public registration or self-promotion is permitted. Passwords and codes are placeholders; never include real credentials in client documents.",
    "Proposed baseline: password plus mandatory MFA for administrative access. TOTP is recommended; an approved verified OTP factor may be used instead. Challenge and proof must be purpose-bound, short-lived, single-use and rate-limited.",
    "Invalid credentials use generic errors. Token rotation/reuse detection, secure device storage, session revocation, recent MFA for privileged actions and administrative session timeout need final approval. Existing password/session support does not imply MFA is implemented.",
])
api("POST","[private URL withheld]","Private operation: begin admin sign-in",
    dict(identifier="admin@example.test",password="<password>",device_name="Admin workstation"),
    dict(challenge_id="admin_challenge_001",mfa_required=True,mfa_method="TOTP",expires_in_seconds=300),
    "Pre-session admin verification",private=True,
    rules="identifier and password required; device_name optional. Do not issue a business-data access token before the required factor passes.",
    errors="401 INVALID_CREDENTIALS; 429 RATE_LIMITED")
api("POST","[private URL withheld]","Private operation: complete admin MFA",
    dict(challenge_id="admin_challenge_001",code="123456"),
    dict(admin=dict(id="admin_001",display_name="Example Administrator",role_ids=["role_ceo"]),
         access_token="<admin_access_token>",refresh_token="<admin_refresh_token>",expires_in_seconds=900,session_id="admin_session_001"),
    "MFA challenge",private=True,rules="Both fields required. code is a string. This is a proposed private MFA contract, not an exposed route.",
    errors="400 MFA_INVALID; 400 MFA_EXPIRED; 429 RATE_LIMITED")
api("POST","[private URL withheld]","Private operation: refresh admin session",
    dict(refresh_token="<admin_refresh_token>"),
    dict(access_token="<new_admin_access_token>",refresh_token="<rotated_admin_refresh_token>",expires_in_seconds=900),
    "Refresh credential",private=True,rules="refresh_token required; reject revoked/expired/reused credentials.",
    errors="401 SESSION_EXPIRED; 401 REFRESH_REUSE_DETECTED")
api("POST","[private URL withheld]","Private operation: revoke current session",None,dict(logged_out=True),
    "Authenticated admin session",private=True,rules="Revoke current session and refresh credentials; protected access must honor revocation.")

group("Identity, roles and permission-aware navigation",[20],[
    "RBAC is enforced server-side for every read, export and mutation, not only by hiding screens. Cross-garage access is limited to the admin's permitted data scope.",
    "Proposed functional permissions are shown per operation. CEO may receive approved full access; operations, finance and support roles receive least privilege. Role names do not bypass permission checks.",
    "Role assignment requires security.manage and recent MFA. Prevent self-escalation and removing the last active security administrator. Log before/after permission changes and revoke/re-evaluate affected sessions.",
    "Staff/role reads and role assignment are required to support AUS-20. Creating/deleting staff accounts or dynamic role creation is outside these stories; provisioning stays deliberate and private.",
])
api("GET","/me","Read admin identity and effective permissions",None,
    dict(id="admin_001",display_name="Example Administrator",role_ids=["role_ceo"],
         permissions=["dashboard.read","garages.read","finance.read","reports.export"],data_scope=dict(type="PLATFORM")),
    "Authenticated admin",rules="Return effective permissions, permitted garage scope and current identity; never return credential hashes.")
api("GET","/menus","Read authorized admin menus",None,
    dict(items=[dict(key="dashboard",label="Dashboard",permission="dashboard.read"),
                dict(key="finance",label="Finance",permission="finance.read")]),
    "Authenticated admin",rules="Return only authorized menu keys; private sign-in routes are never included.")
api("GET","/permissions","Read permission catalogue",None,
    dict(items=[dict(code="garages.status.write",description="Activate or suspend a garage"),
                dict(code="security.manage",description="Assign admin staff roles")]),"security.read")
api("GET","/roles","Read approved admin roles",None,
    dict(items=[dict(id="role_operations",name="Operations",permissions=["garages.read","bookings.read","jobs.read"]),
                dict(id="role_finance",name="Finance",permissions=["finance.read","reports.export"])]),"security.read")
api("GET","/staff","List admin staff and assigned roles",None,
    page([dict(id="admin_002",display_name="Example Operations Staff",is_active=True,role_ids=["role_operations"])]),
    "security.read",query="search=Operations&is_active=true&page=1&page_size=20")
api("PUT","/staff/{admin_id}/roles","Assign approved roles/data scope",
    dict(role_ids=["role_operations"],data_scope=dict(type="GARAGES",garage_ids=["garage_001"]),reason="Regional operations assignment"),
    dict(admin_id="admin_002",role_ids=["role_operations"],data_scope=dict(type="GARAGES",garage_ids=["garage_001"]),audit_id="audit_001"),
    "security.manage",rules="All fields required. role_ids must be valid approved roles; type is PLATFORM or GARAGES. GARAGES requires nonempty unique garage_ids. Reject escalation outside grantor authority.",
    errors="403 PRIVILEGE_ESCALATION_DENIED; 409 LAST_SECURITY_ADMIN; 422 ROLE_INVALID")

group("Executive dashboard and consistent analytics",[2,3],[
    "Common filters: date_from, date_to, timezone, city, garage_id, service_id. Apply the same normalized filters, permission scope and snapshot to all cards/charts.",
    "Server generates snapshot_id/as_of on initial read. Clients may pass snapshot_id on subsequent related dashboard/statistics/export reads. Expired snapshots produce 409 and require reload.",
    "Dashboard customer/garage counts are distinct participants in the selected segment/time range; lifetime totals require a separate explicitly-labelled view. Active job statuses are OPEN, IN_PROGRESS, WAITING_FOR_PARTS, QUALITY_CHECK and READY.",
    "Financial net_collected_amount means confirmed gross captured payments minus settled refunds, including tax; it is not profit or statutory revenue. Return taxes/discounts separately and approve the accounting definition.",
])
api("GET","/dashboard","Read executive KPI dashboard",None,
    dict(**META,kpis=dict(garages=2,customers=40,bookings=60,active_jobs=17,completed_jobs=30,cancelled_jobs=3,
                         cancelled_bookings=4,payment_failures=3,gross_collected_amount=3540000,refunded_amount=118000,
                         net_collected_amount=3422000,currency="INR")),
    "dashboard.read",query=QUERY,rules="Filters are optional; default date window must be returned explicitly. Proposed metrics extend the existing dashboard contract.")
api("GET","/analytics","Read filtered time-series charts",None,
    dict(**META,period="daily",series=[dict(date="2026-10-08",bookings=8,jobs_created=5,jobs_completed=3,
         captured_amount=354000,refunded_amount=0,net_collected_amount=354000)],currency="INR"),
    "dashboard.read",query=QUERY+"&period=daily",
    rules="period supports daily, weekly, monthly or custom. Chart time buckets and metric definitions must match the dashboard.",
    errors="422 DATE_RANGE_INVALID; 409 SNAPSHOT_EXPIRED")

group("Garage owners, profiles and operational controls",[4,5,6],[
    "Owner identity and garage identity are distinct; one owner can manage several garages. Lists include ratings, booking/job/revenue aggregates and selected filters.",
    "Operational status (ACTIVE, SUSPENDED) and verification status (UNVERIFIED, VERIFIED) are separate controls. Verification does not silently activate a suspended garage.",
    "Suspension blocks discovery/new bookings according to approved policy, while preserving historical records and handling existing work explicitly. Status changes are audited with reason, actor and timestamp.",
    "Support/complaint counts link to support tickets; garage profile includes active services, hours, invoices, reviews and recent activity without exposing credential or bank secrets.",
])
api("GET","/garage-owners","List garage owners and activity",None,
    page([dict(id="owner_001",display_name="Example Garage Owner",garage_ids=["garage_001"],city="Hyderabad",
               account_status="ACTIVE",average_rating=4.6,bookings=20,jobs_created=30,net_collected_amount=2242000,currency="INR")]),
    "garages.read",query=QUERY+"&search=Example&status=ACTIVE&min_rating=4&page=1&page_size=20",
    rules="Optional search, owner status, city, min_rating, garage_id and reporting filters. Account status is not garage operational status.")
api("GET","/garage-owners/{owner_id}","View owner and managed garages",None,
    dict(id="owner_001",display_name="Example Garage Owner",account_status="ACTIVE",
         garages=[dict(id="garage_001",name="Example Garage",operational_status="ACTIVE",verification_status="VERIFIED")]),
    "garages.read")
api("GET","/garages","List admin-visible garages",None,
    page([dict(id="garage_001",owner_id="owner_001",name="Example Garage",city="Hyderabad",operational_status="ACTIVE",
               verification_status="VERIFIED",average_rating=4.6)]),"garages.read",
    query="city=Hyderabad&operational_status=ACTIVE&verification_status=VERIFIED&page=1&page_size=20")
api("GET","/garages/{garage_id}","Inspect garage profile and operations",None,
    dict(id="garage_001",owner_id="owner_001",name="Example Garage",city="Hyderabad",timezone="Asia/Kolkata",
         operational_status="ACTIVE",verification_status="VERIFIED",
         services=[dict(id="service_001",name="Basic Service",price_amount=100000,currency="INR")],
         working_hours=[dict(day="THURSDAY",opens="09:00",closes="18:00")],
         summary=dict(bookings=20,jobs=30,invoices=20,average_rating=4.6,complaints=2),
         recent_activity=[dict(type="JOB_CREATED",job_id="job_001",timestamp="2026-10-08T10:00:00+05:30")]),
    "garages.read",rules="Collections in this summary are bounded previews. Related bookings/jobs/invoices/support APIs allow garage_id filtering and pagination.")
api("PATCH","/garages/{garage_id}/status","Activate or suspend garage",
    dict(operational_status="SUSPENDED",reason="Partner quality review",expected_version=3),
    dict(id="garage_002",operational_status="SUSPENDED",version=4,audit_id="audit_002"),
    "garages.status.write",rules="All fields required. Use expected_version for concurrency; sample change targets garage_002, separate from active garage_001.",
    errors="409 VERSION_CONFLICT; 422 INVALID_STATUS_TRANSITION")
api("PATCH","/garages/{garage_id}/verification","Verify garage",
    dict(verification_status="VERIFIED",reason="Required documents reviewed",expected_version=4),
    dict(id="garage_002",operational_status="SUSPENDED",verification_status="VERIFIED",version=5,audit_id="audit_003"),
    "garages.verify",rules="All fields required. Verification/reversal transitions need policy; changing verification does not override operational suspension.",
    errors="409 VERSION_CONFLICT; 422 VERIFICATION_REQUIREMENTS_NOT_MET")
api("GET","/garages/{garage_id}/reviews","Inspect garage ratings/reviews",None,
    page([dict(id="review_001",customer_id="customer_001",job_id="job_001",rating=4,comment="Good service",
               moderation_status="PUBLISHED")]),"garages.read",query="moderation_status=PUBLISHED&page=1&page_size=20",
    rules="Inspection only; review moderation writes are not requested in this source.")

group("Customer account and risk monitoring",[7,8],[
    "Customer login identities must be distinguished from garage-owned contact records. Cross-platform customer reads require customers.read; do not mistake owner accounts for customer identities.",
    "Customer list filters include search, account_status, inactive_since, last activity, failed-payment count and support flags. Define the inactivity threshold in configuration.",
    "Profile shows paginated linked vehicles, bookings, jobs, invoices, payment attempts, reviews and support tickets. Return permission-filtered summaries and use related list endpoints for drill-down.",
    "The source requests identifying inactive/blocked accounts, not authority to block/delete customers. No customer-blocking, impersonation or credential reset operation is added.",
])
api("GET","/customers","List customers and risk flags",None,
    page([dict(id="customer_001",display_name="Example Customer",account_status="ACTIVE",
               last_activity_at="2026-10-08T12:00:00+05:30",failed_payments=1,support_flags=["OPEN_PAYMENT_TICKET"])]),
    "customers.read",query="account_status=ACTIVE&has_failed_payments=true&has_support_flags=true&page=1&page_size=20",
    rules="All filters optional and combined with AND. Optional inactive_since uses last_activity_at before the supplied cutoff, with never-active handling defined in policy.")
api("GET","/customers/{customer_id}","Inspect customer and linked records",None,
    dict(id="customer_001",display_name="Example Customer",account_status="ACTIVE",
         vehicles=[dict(id="vehicle_001",registration_number="TS00AA0001",model="Swift")],
         bookings=[dict(id="booking_001",status="CONVERTED")],jobs=[dict(id="job_001",status="COMPLETED")],
         invoices=[dict(id="invoice_001",total_amount=118000,payment_status="PAID")],
         payments=[dict(id="payment_001",status="PAID")],reviews=[dict(id="review_001",rating=4)],
         support_tickets=[dict(id="ticket_001",status="OPEN")],related_preview_limit=5),
    "customers.read",rules="Linked finance details additionally require finance.read. Paginate full related data via the dedicated lists; vehicle and review list operations below complete the profile drill-down.")
api("GET","/customers/{customer_id}/vehicles","Inspect all customer vehicles",None,
    page([dict(id="vehicle_001",registration_number="TS00AA0001",brand="Maruti Suzuki",model="Swift",fuel_type="PETROL")]),
    "customers.read",query="page=1&page_size=20")
api("GET","/customers/{customer_id}/reviews","Inspect customer review history",None,
    page([dict(id="review_001",garage_id="garage_001",job_id="job_001",rating=4,moderation_status="PUBLISHED")]),
    "customers.read",query="page=1&page_size=20")

group("Booking monitoring and exception trends",[9,10],[
    "Read-only monitoring; admin does not accept/reject or convert bookings on behalf of a garage in this requirements baseline.",
    "Booking states: PENDING, ACCEPTED, REJECTED, CANCELLED, CONVERTED, EXPIRED. Include actor, timestamps, rejection/cancellation/expiry reasons and linked job where available.",
    "Exception charts break down rejected/cancelled/expired bookings by reason, owner, city and time using the same filter/snapshot convention. Missing reasons are explicitly categorized as UNSPECIFIED.",
])
api("GET","/bookings","Monitor bookings across permitted garages",None,
    page([dict(id="booking_001",customer_id="customer_001",garage_id="garage_001",owner_id="owner_001",
               vehicle_id="vehicle_001",service_ids=["service_001"],starts_at="2026-10-08T10:00:00+05:30",
               status="CONVERTED",created_at="2026-10-07T15:00:00+05:30",accepted_at="2026-10-07T16:00:00+05:30",job_id="job_001")]),
    "bookings.read",query=QUERY+"&status=CONVERTED&customer_id=customer_001&page=1&page_size=20")
api("GET","/bookings/{booking_id}","Inspect booking history/decision reasons",None,
    dict(id="booking_002",status="REJECTED",customer_id="customer_002",garage_id="garage_002",owner_id="owner_002",
         reason="Requested slot unavailable",decision_actor=dict(role="GARAGE_OWNER",id="owner_002"),
         decided_at="2026-10-08T11:00:00+05:30",timeline=[dict(status="PENDING",timestamp="2026-10-08T10:50:00+05:30"),
         dict(status="REJECTED",timestamp="2026-10-08T11:00:00+05:30")]),"bookings.read")
api("GET","/bookings/exception-statistics","Read booking exception breakdowns",None,
    dict(**META,totals=dict(REJECTED=6,CANCELLED=4,EXPIRED=2),
         by_reason=[dict(reason="UNSPECIFIED",count=2),dict(reason="Requested slot unavailable",count=10)],
         by_owner=[dict(owner_id="owner_001",count=7),dict(owner_id="owner_002",count=5)]),
    "bookings.read",query=QUERY+"&group_by=owner,reason,day",
    rules="group_by supports owner, garage, reason, city, day. Date basis is the exception transition timestamp.",
    errors="422 INVALID_GROUPING; 409 SNAPSHOT_EXPIRED")

group("Job monitoring, timeline and delay alerts",[11,12],[
    "Job states: OPEN, IN_PROGRESS, WAITING_FOR_PARTS, QUALITY_CHECK, READY, COMPLETED, CANCELLED. Return complete authorized detail without granting job-edit/status-change powers.",
    "Delay detection uses configured thresholds per service/state and recorded timestamps. State duration starts at entry into the current state; overall overdue compares an approved due_at against as_of.",
    "Jobs waiting for parts are filterable independently of being overdue. Alerts show measured duration, threshold and the current delay reason. Configuration ownership must be approved.",
])
api("GET","/jobs","Monitor job cards",None,
    page([dict(id="job_001",job_number="GFC-J-000001",garage_id="garage_001",customer_id="customer_001",
               vehicle_id="vehicle_001",status="COMPLETED",created_at="2026-10-08T10:00:00+05:30",
               completed_at="2026-10-08T12:00:00+05:30")]),"jobs.read",
    query=QUERY+"&status=COMPLETED&customer_id=customer_001&page=1&page_size=20")
api("GET","/jobs/{job_id}","Inspect job findings and charges",None,
    dict(id="job_001",garage_id="garage_001",customer_id="customer_001",vehicle_id="vehicle_001",status="COMPLETED",
         services=[dict(id="service_001",name="Basic Service")],parts=[dict(name="Engine oil",quantity=1)],
         labour=[dict(description="Oil change")],inspection_findings=["Routine maintenance completed"],
         created_at="2026-10-08T10:00:00+05:30",completed_at="2026-10-08T12:00:00+05:30"),
    "jobs.read",rules="Mask restricted notes/financial fields where the admin lacks their permissions.")
api("GET","/jobs/{job_id}/timeline","Inspect chronological job events",None,
    page([dict(status="OPEN",timestamp="2026-10-08T10:00:00+05:30",actor_id="owner_001"),
          dict(status="COMPLETED",timestamp="2026-10-08T12:00:00+05:30",actor_id="owner_001")]),
    "jobs.read",query="page=1&page_size=20")
api("GET","/jobs/delays","Identify delayed/waiting jobs",None,
    page([dict(id="job_003",garage_id="garage_001",status="WAITING_FOR_PARTS",state_entered_at="2026-10-06T10:00:00+05:30",
               measured_state_hours=53,threshold_hours=24,is_overdue=True,reason="Part not received")]),
    "jobs.read",query="status=WAITING_FOR_PARTS&overdue=true&garage_id=garage_001&page=1&page_size=20",
    rules="Return as_of in list metadata; sample durations measured at 2026-10-08T15:00:00+05:30.")
api("GET","/alerts","Read operational delay alerts",None,
    page([dict(id="alert_001",type="JOB_DELAY",severity="HIGH",job_id="job_003",garage_id="garage_001",
               threshold_hours=24,measured_hours=53,detected_at="2026-10-08T15:00:00+05:30")]),
    "jobs.read",query="type=JOB_DELAY&severity=HIGH&page=1&page_size=20",
    rules="Alert generation/deduplication must be defined; this read API does not imply a customer notification or intervention mutation.")

group("Finance, invoices, payments, refunds and disputes",[13,14],[
    "Finance is read-only investigation/reporting in the source. No payment-status override, refund initiation, charge, invoice-edit or missing-bill repair endpoint is proposed.",
    "Amounts are integer paise, INR. Full/partial refunds are separate settled financial events, not failed payment attempts. Reconcile capture/refund amounts before reporting.",
    "Sanitize gateway responses: expose approved response codes, timestamps and transaction references only. Exclude secrets, signatures, card/bank details and raw unrestricted gateway payloads.",
    "Financial reports include totals/trends, status, garage breakdown, tax and discount totals. Different event date bases must be explicit: invoice issued_at; payment captured_at; refund settled_at; dispute opened_at.",
])
api("GET","/finance/summary","Read financial totals and breakdown",None,
    dict(**META,gross_collected_amount=3540000,refunded_amount=118000,net_collected_amount=3422000,
         issued_invoice_total_amount=3540000,tax_amount=540000,discount_amount=0,failed_attempts=3,currency="INR",
         by_garage=[dict(garage_id="garage_001",net_collected_amount=2242000),
                    dict(garage_id="garage_002",net_collected_amount=1180000)]),
    "finance.read",query=QUERY,rules="Return event-date bases and matching filter metadata; payment trends available through finance analytics.",
    errors="422 DATE_RANGE_INVALID; 409 SNAPSHOT_EXPIRED")
api("GET","/finance/trends","Read finance trends",None,
    dict(**META,currency="INR",series=[dict(date="2026-10-08",captured_amount=354000,refunded_amount=0,
         net_collected_amount=354000,tax_amount=54000,discount_amount=0,failed_attempts=1)]),
    "finance.read",query=QUERY+"&period=daily")
api("GET","/invoices","List invoices with billing totals",None,
    page([dict(id="invoice_001",job_id="job_001",customer_id="customer_001",garage_id="garage_001",
               subtotal_amount=100000,tax_amount=18000,discount_amount=0,total_amount=118000,payment_status="PAID",currency="INR")]),
    "finance.read",query=QUERY+"&customer_id=customer_001&payment_status=PAID&page=1&page_size=20")
api("GET","/invoices/{invoice_id}","Inspect invoice and payment links",None,
    dict(id="invoice_001",job_id="job_001",customer_id="customer_001",garage_id="garage_001",
         line_items=[dict(type="SERVICE",description="Basic Service",quantity=1,unit_amount=100000,line_total=100000)],
         subtotal_amount=100000,taxes=[dict(name="GST",rate_percent=18,amount=18000)],discount_amount=0,
         total_amount=118000,currency="INR",payment_status="PAID",payment_ids=["payment_001"]),
    "finance.read")
api("GET","/payments","Find failed/disputed or settled payments",None,
    page([dict(id="payment_001",invoice_id="invoice_001",customer_id="customer_001",garage_id="garage_001",
               status="PAID",amount=118000,currency="INR",dispute_status="NONE")]),
    "finance.read",query=QUERY+"&status=PAID&disputed=false&page=1&page_size=20",
    rules="Optional customer_id, invoice_id, garage_id, status and disputed filters. Failure and dispute are different dimensions.")
api("GET","/payments/{payment_id}","Inspect payment attempt and safe gateway result",None,
    dict(id="payment_failed_001",invoice_id="invoice_002",customer_id="customer_002",garage_id="garage_002",
         status="FAILED",amount=118000,currency="INR",gateway=dict(provider="<configured_provider>",
         order_reference="<synthetic_order_reference>",response_code="PAYMENT_DECLINED",responded_at="2026-10-08T12:00:00+05:30"),
         dispute_ids=[],related_attempt_ids=["payment_failed_001"]),"finance.read")
api("GET","/invoices/{invoice_id}/payment-attempts","Inspect every attempt for invoice",None,
    page([dict(id="payment_001",status="PAID",amount=118000,created_at="2026-10-08T12:15:00+05:30")]),
    "finance.read",query="page=1&page_size=20")
api("GET","/refunds","Inspect refund records",None,
    page([dict(id="refund_001",payment_id="payment_001",invoice_id="invoice_001",garage_id="garage_001",
               amount=11800,currency="INR",status="SETTLED",settled_at="2026-10-08T13:00:00+05:30")]),
    "finance.read",query=QUERY+"&status=SETTLED&page=1&page_size=20")
api("GET","/disputes","Find disputed payments",None,
    page([dict(id="dispute_001",payment_id="payment_003",invoice_id="invoice_003",customer_id="customer_003",
               garage_id="garage_001",status="OPEN",reason="Customer reports duplicate payment")]),
    "finance.read",query=QUERY+"&status=OPEN&page=1&page_size=20")
api("GET","/disputes/{dispute_id}","Inspect dispute context and evidence",None,
    dict(id="dispute_001",payment_id="payment_003",invoice_id="invoice_003",customer_id="customer_003",
         garage_id="garage_001",status="OPEN",reason="Customer reports duplicate payment",
         support_ticket_id="ticket_002",timeline=[dict(event="DISPUTE_OPENED",timestamp="2026-10-08T14:00:00+05:30")]),
    "finance.read",rules="Read-only evidence; resolving/closing a gateway dispute needs separate scope.")

group("Notification monitoring and operational announcements",[15,16],[
    "Notifications are searchable by recipient role/ID, event type, booking/job/invoice, delivery status and timestamp. In-app read status and push delivery status are distinct.",
    "Announcements select a permitted customer/garage audience, store message, audience snapshot, actor, delivery outcomes and audit record. Preview before send, use idempotency and bound recipient counts.",
    "Sending operational announcements does not authorize marketing campaigns. Permissions, channel consent, text limits, delivery provider, recipient scope and suppression policies need approval.",
])
api("GET","/notifications","Inspect platform notification delivery",None,
    page([dict(id="notification_001",recipient=dict(role="CUSTOMER",id="customer_001"),
               event_type="INVOICE_PUBLISHED",invoice_id="invoice_001",delivery_status="DELIVERED",
               read_at=None,created_at="2026-10-08T12:10:00+05:30")]),
    "notifications.read",query=QUERY+"&recipient_role=CUSTOMER&event_type=INVOICE_PUBLISHED&status=DELIVERED&page=1&page_size=20",
    rules="Optional recipient_id, booking_id, job_id and invoice_id filters.")
api("GET","/notifications/{notification_id}","Inspect safe delivery attempts",None,
    dict(id="notification_001",recipient=dict(role="CUSTOMER",id="customer_001"),
         title="Invoice available",body="Your final invoice is ready.",
         attempts=[dict(channel="PUSH",status="DELIVERED",attempted_at="2026-10-08T12:10:00+05:30",provider_code="ACCEPTED")]),
    "notifications.read",rules="Do not expose recipient device tokens, provider credentials or raw provider responses.")
api("POST","/announcements/preview","Preview announcement audience",
    dict(audience=dict(recipient_roles=["GARAGE_OWNER"],city="Hyderabad",garage_ids=["garage_001"]),
         channels=["IN_APP","PUSH"],title="Operational update",body="Please review appointment availability."),
    dict(preview_id="preview_001",recipient_count=1,expires_at="2026-10-08T15:10:00+05:30"),
    "announcements.send",rules="All fields required. Resolve recipients within caller scope; proposed title limit 120, body limit 2,000.",
    errors="422 AUDIENCE_INVALID; 413 AUDIENCE_TOO_LARGE")
api("POST","/announcements","Queue approved operational announcement",
    dict(preview_id="preview_001",reason="Appointment capacity review"),
    dict(id="announcement_001",status="QUEUED",recipient_count=1,audit_id="audit_004"),"announcements.send",status=202,
    headers="Idempotency-Key: <unique_key>",rules="Both fields required; recent MFA recommended. Persist audience/message snapshot from preview; do not accept changed content with an old preview.",
    errors="409 PREVIEW_EXPIRED; 409 IDEMPOTENCY_CONFLICT")
api("GET","/announcements","List sent/queued announcements",None,
    page([dict(id="announcement_001",title="Operational update",status="COMPLETED",recipient_count=1,delivered_count=1,failed_count=0)]),
    "notifications.read",query=QUERY+"&status=COMPLETED&page=1&page_size=20")
api("GET","/announcements/{announcement_id}","Inspect audience and delivery totals",None,
    dict(id="announcement_001",status="COMPLETED",audience=dict(recipient_roles=["GARAGE_OWNER"],garage_ids=["garage_001"]),
         channels=["IN_APP","PUSH"],recipient_count=1,delivered_count=1,failed_count=0,actor_id="admin_001",audit_id="audit_004"),
    "notifications.read",rules="Recipient totals are distinct recipients; per-channel delivery attempts are separately listed.")
api("GET","/announcements/{announcement_id}/deliveries","Inspect announcement delivery outcomes",None,
    page([dict(recipient_id="owner_001",recipient_role="GARAGE_OWNER",channel="PUSH",status="DELIVERED")]),
    "notifications.read",query="status=DELIVERED&page=1&page_size=20")

group("Support ticket assignment, priority, replies and closure",[17],[
    "Support permissions independently control reading, assigning, setting priority, replying and changing status. Assignment targets active authorized support staff.",
    "Proposed statuses: OPEN, IN_PROGRESS, WAITING_FOR_CUSTOMER, RESOLVED, CLOSED. Priorities: LOW, NORMAL, HIGH, URGENT. Approve permitted transitions and reopening policy.",
    "Ticket links may include customer, garage, booking, job, invoice and payment. Access to linked financial detail still requires finance.read. Every mutation is audited.",
    "Replies are customer/garage-visible according to the ticket participant context. Internal notes must never leak into external replies; this baseline provides external reply operations only.",
])
api("GET","/support/tickets","Find support tickets",None,
    page([dict(id="ticket_001",subject="Invoice question",customer_id="customer_001",garage_id="garage_001",
               status="OPEN",priority="NORMAL",assignee_id=None)]),"support.read",
    query="status=OPEN&priority=NORMAL&customer_id=customer_001&garage_id=garage_001&page=1&page_size=20")
api("GET","/support/tickets/{ticket_id}","Inspect support ticket and record links",None,
    dict(id="ticket_001",subject="Invoice question",description="Please clarify the charges.",customer_id="customer_001",
         garage_id="garage_001",booking_id="booking_001",job_id="job_001",invoice_id="invoice_001",
         status="OPEN",priority="NORMAL",assignee_id=None,version=1),
    "support.read")
api("PATCH","/support/tickets/{ticket_id}/assignment","Assign/unassign support staff",
    dict(assignee_id="admin_support_001",reason="Finance support queue",expected_version=1),
    dict(id="ticket_001",assignee_id="admin_support_001",version=2,audit_id="audit_005"),"support.assign",
    rules="All fields required; assignee_id may be null to unassign. Validate scope and staff eligibility.",
    errors="422 ASSIGNEE_INVALID; 409 VERSION_CONFLICT")
api("PATCH","/support/tickets/{ticket_id}/priority","Change ticket priority",
    dict(priority="HIGH",reason="Customer service blocked",expected_version=2),
    dict(id="ticket_001",priority="HIGH",version=3,audit_id="audit_006"),"support.manage",
    rules="All fields required.",errors="422 PRIORITY_INVALID; 409 VERSION_CONFLICT")
api("GET","/support/tickets/{ticket_id}/messages","Read ticket messages",None,
    dict(items=[dict(id="support_message_001",sender_role="CUSTOMER",text="Please clarify the charges.",
                    created_at="2026-10-08T12:30:00+05:30")],next_cursor=None),
    "support.read",query="limit=30",rules="cursor optional; limit 1..100.")
api("POST","/support/tickets/{ticket_id}/messages","Reply to customer/garage",
    dict(client_message_id="admin_reply_001",text="We are reviewing your invoice."),
    dict(id="support_message_002",sender_role="ADMIN",text="We are reviewing your invoice.",
         created_at="2026-10-08T15:00:00+05:30",audit_id="audit_007"),"support.reply",status=201,
    rules="Both fields required; text nonblank, proposed maximum 2,000 characters. Deduplicate client_message_id.",
    errors="409 TICKET_CLOSED; 409 MESSAGE_ID_CONFLICT; 422 MESSAGE_INVALID")
api("PATCH","/support/tickets/{ticket_id}/status","Resolve or close ticket",
    dict(status="CLOSED",resolution="Charges explained and confirmed by the customer.",expected_version=3),
    dict(id="ticket_001",status="CLOSED",closed_at="2026-10-08T16:00:00+05:30",version=4,audit_id="audit_008"),
    "support.manage",rules="status and expected_version required; resolution required for RESOLVED/CLOSED. Enforce approved transitions.",
    errors="409 STATUS_TRANSITION_INVALID; 409 VERSION_CONFLICT")

group("Garage-owner performance statistics and formulas",list(range(21,29)),[
    "All statistics use the same normalized date/city/garage/service filters, permission scope and snapshot; exports include filters, generated timestamp and source totals.",
    "Jobs-created/status-cohort basis: jobs created in the selected period; status counts are their current status as_of. Status totals must reconcile to that filtered cohort job list. Do not mix created-in-period and completed-in-period counts without labels.",
    "Average jobs per garage = total cohort jobs / eligible garage count. Eligible garages include zero-job garages in the permitted segment; exclude inactive only when exclude_inactive=true. Return null, not zero, when denominator is zero.",
    "Conversion = converted_by_as_of / eligible_accepted_bookings * 100. Eligible cohort: accepted_at in the selected window, including bookings later CONVERTED; exclude invalid/deleted records under an approved policy. Numerator is the converted subset, not all converted bookings across unrelated dates.",
    "Average completion duration = sum(completed_at - created_at) / completed valid jobs in the created-in-period cohort, measured in hours. Exclude unfinished/cancelled/invalid-timestamp records and return exclusions/sample size; no samples means null.",
    "Average invoice amount = sum(final nonvoid invoice total_amount issued in period) / invoice count. Keep this separate from net collections and paid-invoice count. Collections use captured_at and refunds settled_at.",
    "Owner rankings use a deterministic tie-breaker (owner ID) and an explicit sort metric. Multi-garage owners are one aggregate row with garage_ids. Drill-down rows preserve owner identity and filter scope.",
])
owner_rows = [
    dict(owner_id="owner_001",owner_name="Example Owner A",garage_ids=["garage_001"],rank=1,jobs_created=30,
         status_counts=dict(OPEN=2,IN_PROGRESS=4,WAITING_FOR_PARTS=2,QUALITY_CHECK=1,READY=0,COMPLETED=20,CANCELLED=1),
         eligible_accepted_bookings=10,converted_bookings=8,conversion_percent=80,completion_sample_size=20,
         average_completion_hours=4.5,overdue_jobs=2,gross_collected_amount=2360000,refunded_amount=118000,
         net_collected_amount=2242000,paid_invoice_count=20,issued_invoice_count=20,issued_invoice_total_amount=2360000,
         average_invoice_amount=118000,failed_attempts=2,currency="INR"),
    dict(owner_id="owner_002",owner_name="Example Owner B",garage_ids=["garage_002"],rank=2,jobs_created=20,
         status_counts=dict(OPEN=1,IN_PROGRESS=3,WAITING_FOR_PARTS=2,QUALITY_CHECK=1,READY=1,COMPLETED=10,CANCELLED=2),
         eligible_accepted_bookings=10,converted_bookings=7,conversion_percent=70,completion_sample_size=10,
         average_completion_hours=6,overdue_jobs=3,gross_collected_amount=1180000,refunded_amount=0,
         net_collected_amount=1180000,paid_invoice_count=10,issued_invoice_count=10,issued_invoice_total_amount=1180000,
         average_invoice_amount=118000,failed_attempts=1,currency="INR"),
]
api("GET","/garage-owner-statistics","Compare owners, rankings and operational/finance metrics",None,
    dict(**META,items=owner_rows,page=1,page_size=20,total=2,source_totals=dict(jobs_created=50,status_counts=STATUSES,
         eligible_accepted_bookings=20,converted_bookings=15,net_collected_amount=3422000,paid_invoice_count=30)),
    "owner_statistics.read + finance.read for monetary fields",query=QUERY+"&sort=jobs_created_desc&exclude_inactive=true&page=1&page_size=20",
    rules="Optional owner_id and snapshot_id. Without finance.read omit monetary fields with restricted_fields metadata; do not return misleading zeroes.",
    errors="422 DATE_RANGE_INVALID; 409 SNAPSHOT_EXPIRED")
api("GET","/garage-owner-statistics/summary","Read reconcilable owner-performance totals/averages",None,
    dict(**META,total_jobs_created=50,eligible_garages=2,average_jobs_per_garage=25,exclude_inactive=True,
         status_counts=STATUSES,eligible_accepted_bookings=20,converted_bookings=15,conversion_percent=75,
         completion_sample_size=30,completion_total_hours=150,average_completion_hours=5,
         net_collected_amount=3422000,paid_invoice_count=30,average_invoice_amount=118000,currency="INR"),
    "owner_statistics.read + finance.read for monetary fields",query=QUERY+"&exclude_inactive=true",
    rules="Return formulas/numerator/denominator and exclusions in metric metadata. Weighted completion mean: (20*4.5+10*6)/30=5 hours.")
api("GET","/garage-owner-statistics/{owner_id}","Inspect one owner's performance and garage breakdown",None,
    dict(**META,owner_id="owner_001",jobs_created=30,completed_jobs=20,eligible_accepted_bookings=10,
         converted_bookings=8,conversion_percent=80,average_completion_hours=4.5,completion_sample_size=20,
         garage_breakdown=[dict(garage_id="garage_001",jobs_created=30,overdue_jobs=2)]),
    "owner_statistics.read",query=QUERY,
    rules="Financial metrics may be included only with finance.read. Garage/job drill-down uses matching owner_id/garage_id filters.")
api("GET","/garage-owner-statistics/{owner_id}/trends","Read owner job/conversion/collection trends",None,
    dict(**META,owner_id="owner_001",period="daily",series=[dict(date="2026-10-08",jobs_created=3,jobs_completed=2,
         eligible_accepted_bookings=2,converted_bookings=1,conversion_percent=50)]),
    "owner_statistics.read",query=QUERY+"&period=daily",rules="Provide explicitly labelled bucket date bases and numerators/denominators. Optional finance series requires finance.read.")

group("Operational, financial and owner-performance exports",[18,28],[
    "Exports are protected asynchronous resources, not public URLs. Require reports.export plus every data permission needed by the selected report; recheck at download.",
    "Supported proposed types: OPERATIONS, FINANCE, GARAGE_OWNER_PERFORMANCE. CSV and XLSX formats; sanitize spreadsheet-formula injection, redact restricted PII and define retention/size limits.",
    "Every export includes normalized filters, snapshot/as_of, generated timestamp, row count, metric definitions and source totals. GARAGE_OWNER_PERFORMANCE is one row per owner; multiple garage IDs are explicit.",
    "Status: QUEUED, PROCESSING, READY, FAILED, EXPIRED. Failed exports expose a safe error; never silently deliver partial results as complete. Capture format/requester/scope in audit.",
])
api("POST","/reports/exports","Request authorized filtered report",
    dict(report_type="GARAGE_OWNER_PERFORMANCE",format="CSV",filters=FILTERS,snapshot_id="snapshot_001",exclude_inactive=True),
    dict(id="export_001",status="QUEUED",report_type="GARAGE_OWNER_PERFORMANCE",format="CSV",audit_id="audit_009"),
    "reports.export + selected report read permissions",status=202,headers="Idempotency-Key: <unique_key>",
    rules="report_type, format and filters required. snapshot_id optional; generate a fresh snapshot if omitted. exclude_inactive applies only to owner performance.",
    errors="403 REPORT_SCOPE_DENIED; 409 SNAPSHOT_EXPIRED; 413 EXPORT_TOO_LARGE; 429 EXPORT_LIMIT_REACHED")
api("GET","/reports/exports/{export_id}","Poll report generation and reconcile totals",None,
    dict(id="export_001",status="READY",report_type="GARAGE_OWNER_PERFORMANCE",format="CSV",filters=FILTERS,
         snapshot_id="snapshot_001",generated_at="2026-10-08T15:05:00+05:30",row_count=2,
         source_totals=dict(jobs_created=50,net_collected_amount=3422000),
         download_path=BASE+"/reports/exports/export_001/download",expires_at="2026-10-09T15:05:00+05:30"),
    "reports.export + selected report read permissions")
api("GET","/reports/exports/{export_id}/download","Download protected report",None,
    'Binary response: Content-Type: text/csv; Content-Disposition: attachment; filename="garage-owner-performance.csv"',
    "reports.export + selected report read permissions",
    rules="Requester or approved supervisory scope only; verify current permission, READY status and expiry. XLSX uses its correct MIME type.",
    errors="409 EXPORT_NOT_READY; 410 EXPORT_EXPIRED")

group("Audit trail and unified customer/garage activity",[19,29],[
    "Audit records cover successful/failed login, status/account/role changes, financial actions, announcements and exports; actor, time, IP/device, result, correlation ID and approved before/after details are retained.",
    "Audit is append-only; no admin update/delete audit operation. Protect logs from secret/OTP/token/raw gateway payload leakage. IP/device data is privileged, masked or policy-limited.",
    "Unified activity links customer booking, garage acceptance, job creation/status, invoice, payment and review events using stable IDs/correlation. Missing events are shown explicitly, not invented.",
    "Financial activity fields require finance.read. Audit log read requires audit.read and is itself auditable.",
])
api("GET","/audit-logs","Search audited administrative/security actions",None,
    page([dict(id="audit_002",actor_id="admin_001",action="GARAGE_SUSPENDED",resource=dict(type="GARAGE",id="garage_002"),
               timestamp="2026-10-08T14:00:00+05:30",ip_address="192.0.2.10",device="Example workstation",
               result="SUCCESS",reason="Partner quality review",correlation_id="correlation_001")]),
    "audit.read",query=QUERY+"&actor_id=admin_001&action=GARAGE_SUSPENDED&result=SUCCESS&page=1&page_size=20")
api("GET","/audit-logs/{audit_id}","Inspect safe audit details",None,
    dict(id="audit_002",actor_id="admin_001",action="GARAGE_SUSPENDED",resource=dict(type="GARAGE",id="garage_002"),
         before=dict(operational_status="ACTIVE"),after=dict(operational_status="SUSPENDED"),
         result="SUCCESS",reason="Partner quality review",timestamp="2026-10-08T14:00:00+05:30"),
    "audit.read")
api("GET","/activity","Monitor linked customer and garage service activity",None,
    page([dict(id="activity_001",event_type="BOOKING_CREATED",customer_id="customer_001",owner_id="owner_001",
               garage_id="garage_001",booking_id="booking_001",timestamp="2026-10-07T15:00:00+05:30"),
          dict(id="activity_002",event_type="JOB_CREATED",customer_id="customer_001",owner_id="owner_001",
               garage_id="garage_001",booking_id="booking_001",job_id="job_001",timestamp="2026-10-08T10:00:00+05:30")]),
    "activity.read",query=QUERY+"&customer_id=customer_001&garage_id=garage_001&page=1&page_size=20",
    rules="Optional owner_id, event_type, booking_id, job_id, invoice_id filters; apply linked-domain permissions.")
api("GET","/activity/service-funnels/{booking_id}","Inspect complete linked service funnel",None,
    dict(booking_id="booking_001",customer_id="customer_001",garage_id="garage_001",job_id="job_001",invoice_id="invoice_001",
         events=[dict(type="BOOKING_CREATED",timestamp="2026-10-07T15:00:00+05:30"),
                 dict(type="BOOKING_ACCEPTED",timestamp="2026-10-07T16:00:00+05:30"),
                 dict(type="JOB_CREATED",timestamp="2026-10-08T10:00:00+05:30"),
                 dict(type="JOB_COMPLETED",timestamp="2026-10-08T12:00:00+05:30"),
                 dict(type="INVOICE_PUBLISHED",timestamp="2026-10-08T12:10:00+05:30"),
                 dict(type="PAYMENT_CONFIRMED",payment_id="payment_001",timestamp="2026-10-08T12:15:00+05:30"),
                 dict(type="REVIEW_SUBMITTED",review_id="review_001",timestamp="2026-10-08T12:20:00+05:30")]),
    "activity.read + relevant linked-record permissions")


def build():
    with SOURCE.open(newline="",encoding="utf-8-sig") as stream:
        stories = list(csv.DictReader(stream))
    assert len(stories)==29
    assert len({r["Epic ID"] for r in stories})==13
    endpoints = [e for g in groups for e in g["endpoints"]]
    for n,e in enumerate(endpoints,1):
        e["id"]=f"ADM-{n:02d}"
    w=ApprovalWriter("Admin-Only API Requirements")
    w.cover()
    w.p("DRAFT FOR CLIENT APPROVAL")
    w.p("Version 1.0 | Prepared 8 October 2026")
    w.p("Based on GoFixCarz Admin User Stories: 29 stories across 13 epics.")
    w.p("Admin-only contracts with request payloads, sample responses, permission rules, reporting formulas and client approval decisions.")
    w.p("No public/customer/garage-owner API catalogue is included. Private admin authentication URLs and credentials are intentionally withheld; secure access is documented as logical operations.")
    w.p("This is a proposed requirements baseline, not an assertion that all APIs are implemented. Existing admin functionality is distinguished from required additions. No code, account, financial or production change is authorized by this document.")
    w.p("All identifiers, contacts, people, financial data and gateway references in examples are synthetic. Tokens/passwords are placeholders.")
    w.br()
    w.h("Contents")
    for title in ["1. Scope, access and conventions","2. Admin operation index","3. Detailed admin contracts",
                  "4. Existing baseline and requirements gaps","5. Story-to-API traceability",
                  "6. Client decision register","7. Client sign-off"]:
        w.p(title)
    w.h("1. Scope, access and conventions")
    w.p(f"Proposed business API base path: {BASE}. Relative paths below are admin-only and require an authenticated authorized admin. Authentication URL locations are never printed; the private operation entries cannot be used as URL requests.")
    w.p("Authorization: Bearer <admin_access_token>. Validate active account, session and effective permission/scope on every operation. Garage/customer tokens are not valid substitutes. A global CEO scope is assigned explicitly, not inferred from signup.")
    w.p("GET has no request body; required opaque path IDs use readable synthetic values here (UUID recommended). Query booleans/numbers are typed. Reject unsupported fields, negative pagination and invalid enum/filter values.")
    w.p("Pagination: page >= 1, default page_size=20, maximum 100; cursor message pagination default limit=30, maximum 100. Empty lists return items: []. Path IDs and ownership/scope are validated on each request.")
    w.p("Date filters are inclusive local dates in timezone (default proposed Asia/Kolkata). Implement as start inclusive/end exclusive after timezone conversion. date_from <= date_to; set maximum ranges for expensive reports. Returned filters and generated_at make the actual window explicit.")
    w.p("Timestamp: ISO 8601 with timezone. Money: integer paise with currency INR; 118000 = INR 1,180. Examples have invoice subtotal 100000 + GST 18000 = 118000. Currency conversions and profit calculations are not introduced.")
    w.p("Common success envelope:")
    w.code(dict(success=True,message="Dashboard retrieved",data=dict(snapshot_id="snapshot_001")))
    w.p("Common error envelope:")
    w.code(dict(success=False,message="You do not have permission to suspend garages",
                error=dict(code="PERMISSION_DENIED",details=dict(required_permission="garages.status.write"))))
    w.p("Common failures: 401 ADMIN_AUTH_REQUIRED / SESSION_EXPIRED; 403 PERMISSION_DENIED / DATA_SCOPE_DENIED; 404 RESOURCE_NOT_FOUND; 422 VALIDATION_ERROR; 429 RATE_LIMITED. Endpoint-specific failures use the same envelope. Hide outside-scope record existence where appropriate.")
    w.p("Mutation idempotency and optimistic version checks protect duplicate sends/exports and conflicting edits. Required reason fields are nonblank strings, proposed maximum 500 characters. Audit all privileged changes; never log secrets.")
    w.p("Static routes such as /jobs/delays and /bookings/exception-statistics must be registered ahead of dynamic ID routes or otherwise explicitly disambiguated in implementation.")
    w.p("Priority remains the source Must Have / Should Have; operational scope is limited to the stories. The sign-off does not authorize broad new writes such as refund initiation, customer blocking, job editing or admin self-registration.")
    w.br()
    w.h("2. Admin operation index")
    w.table(["ID","Method / proposed admin path or private operation","Permission"],[
        [e["id"], e["method"]+" "+(e["title"] if e["private"] else e["path"]), e["permission"]] for e in endpoints
    ],[44,276,175])
    w.br()
    w.h("3. Detailed admin contracts")
    for g in groups:
        w.h(g["title"],2)
        w.p("Stories: "+", ".join(f"AUS-{i}" for i in g["stories"]),small=True)
        for rule in g["rules"]: w.p("• "+rule)
        for e in g["endpoints"]:
            w.h(e["id"]+" | "+e["title"],3)
            w.p(e["method"]+" "+("Private authentication URL withheld" if e["private"] else BASE+e["path"]),small=True)
            w.p(f"Permission / proof: {e['permission']} | Success HTTP: {e['status']}",small=True)
            if e["headers"]: w.p("Required header: "+e["headers"],small=True)
            if e["query"]: w.p("Sample query: ?"+e["query"],small=True)
            if e["rules"]: w.p("Field validation / operation rules: "+e["rules"],small=True)
            w.p("Request payload:",small=True)
            w.code("No request body." if e["request"] is None else e["request"])
            w.p("Sample success response:",small=True)
            w.code(e["response"] if isinstance(e["response"],str) else dict(success=True,message=e["title"]+" successful",data=e["response"]))
            w.p("Representative failures: "+e["errors"]+". Common authorization and validation failures also apply.",small=True)
        w.br()
    w.h("4. Existing baseline and requirements gaps")
    w.p("The observed admin router provides menus/identity, dashboard, owner-oriented users/status, garages/detail, jobs/detail, booking list, basic analytics, billing-issue review and audit list. These are a starting point, not complete acceptance of the CSV.")
    w.table(["Area","Observed baseline","Required gap / proposed extension"],[
        ["Secure access","Dedicated protected admin identity/session mechanism exists.","MFA/OTP requirement must be verified/added; private routes are withheld."],
        ["Dashboard/filtering","Dashboard/basic analytics routes exist.","Full KPI set, city/service/date consistency, snapshots and explicit metric bases."],
        ["Partners/customers","Owner/garage reads; user status update is owner-oriented.","Owner aggregates, separate customer identity views, garage activation/verification control, risk/activity fields."],
        ["Bookings/jobs","Booking list and job list/detail exist.","Decision reasons, timeline/exception trends, delay thresholds/alerts and consistent drill-down."],
        ["Finance","Read-only billing issue review exists.","Confirmed invoices/payments/refunds/disputes, safe gateway evidence and reconciled financial trends."],
        ["Communications/support","Not certified by this router review.","Delivery monitoring, announcement audience/send/results and support assignment/replies/closure."],
        ["RBAC/audit","Admin protection/basic audit list exists.","Fine-grained roles/scopes, permission-aware exports, full actor/result/device/action coverage."],
        ["Owner performance/exports/activity","Not certified by this router review.","AUS-21..29 formulas, reconciled cohort statistics, owner exports and linked service funnel."],
    ],[89,173,233])
    w.p("All contracts in this approval document are proposed requirements, including changes to existing business paths. Existing response shapes may differ. This is a limited baseline review, not certification of every database/service capability or migration plan.")
    w.br()
    w.h("5. Story-to-API traceability")
    trace=[]
    for story in stories:
        number=int(story["User Story ID"].split("-")[1])
        matching=[g for g in groups if number in g["stories"]]
        assert matching,story["User Story ID"]
        ids=[e["id"] for g in matching for e in g["endpoints"]]
        trace.append([story["User Story ID"],story["Epic Name"],story["Priority"],", ".join(ids)])
    w.table(["Story","Source epic","Priority","Covering operations"],trace,[46,115,65,269])
    w.p("AUS-1 is covered by logical private authentication operations without exposing URLs. AUS-21..28 use the performance contracts and formulas; AUS-18/28 share authorized export operations. All 29 source stories are mapped.")
    w.br()
    w.h("6. Client decision register")
    decisions=[
        ["AD-01","Admin security","Approve MFA method, factor enrollment/recovery, session expiry, recent-MFA checks, trusted-device policy and private route distribution."],
        ["AD-02","Roles and scope","Approve CEO/operations/finance/support roles, granular permissions, global/garage scopes and authority for role assignment."],
        ["AD-03","Partner status","Approve activation/suspension/verification rules, required evidence and handling of existing jobs/bookings during suspension."],
        ["AD-04","Customer monitoring","Approve inactivity threshold, blocked-state source and privacy/masking. Customer blocking/impersonation is not included."],
        ["AD-05","Metric cohorts","Approve event date bases, accepted-booking conversion cohort, job status cohort, zero-activity garage inclusion and snapshot behavior."],
        ["AD-06","Financial definitions","Approve net collections versus accounting revenue, refund/tax/discount treatment, invoice averages and provider dispute evidence. No new financial writes."],
        ["AD-07","Delay thresholds","Approve state/service thresholds, due dates, alert severity/deduplication and intervention ownership."],
        ["AD-08","Announcements","Approve channels, consent/purpose, audience maximum, previews, recipient suppression and delivery/retry rules."],
        ["AD-09","Support","Approve categories, priorities, transitions, assignment eligibility, external replies, closure/reopening and SLA."],
        ["AD-10","Exports","Approve CSV/XLSX formats, data masking, report row/range limits, retention/expiry and supervisory download access."],
        ["AD-11","Audit/privacy","Approve logged security/action fields, IP/device access, retention, redaction and evidence controls."],
    ]
    w.table(["ID","Topic","Approval required"],decisions,[46,107,342])
    w.p("Proposed defaults are not approved production settings. Resolve these decisions before final API implementation or estimating delivery.")
    w.h("7. Client sign-off")
    w.p("Approval requested: admin-only business API scope, private secure access requirements, all 29 story mappings, payload/response direction, formulas, permissions and decision register.")
    w.p("Approval confirms requirements only. Account provisioning, production deployment, historical billing repair, provider configuration and financial actions require separate authorization.")
    for text in ["Client / organization: ____________________________________","Reviewer name / role: ___________________________________",
                 "Decision: Approve / Approve with changes / Revise",
                 "Approved decisions / requested changes: __________________",
                 "________________________________________________________",
                 "Signature / written approval reference: __________________",
                 "Approval date: __________________________________________"]:
        w.p(text)
    w.save(STEM)
    Path("documents/admin-api-specification-source.json").write_text(json.dumps(groups,indent=2))
    print(f"Generated {len(endpoints)} admin operations ({sum(e['private'] for e in endpoints)} private logical authentication operations); all 29 stories mapped.")


if __name__=="__main__":
    build()
