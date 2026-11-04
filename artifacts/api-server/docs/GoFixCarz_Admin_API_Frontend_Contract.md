# GoFixCarz Admin API — frontend handoff

Share this document and `GoFixCarz_Admin_API_OpenAPI.json` (machine-readable OpenAPI 3.1). The Postman collection is `GoFixCarz_Admin_APIs.postman_collection.json`.

## Production API host and URL format

Production API base URL supplied for this integration: `https://api.gofixcarz.com/api/v1`. Each endpoint below is written as a full production URL. The base URL already includes `/api/v1`; do not append that prefix twice.

- Protected admin routes: `https://api.gofixcarz.com/api/v1/admin/...`.
- Private admin authentication routes: `https://api.gofixcarz.com/api/v1/admin-auth/...`.
- Sign-in URL: `https://api.gofixcarz.com/api/v1/admin-auth/sign-in`.
- Admin identity URL: `https://api.gofixcarz.com/api/v1/admin/me`.
- Swagger: `https://api.gofixcarz.com/api/docs`; OpenAPI: `https://api.gofixcarz.com/api/openapi.json`.

The Postman collection uses a variable named `base_url` set to `https://api.gofixcarz.com/api/v1`. The OpenAPI server uses the host origin `https://api.gofixcarz.com` because the paths in that file already include `/api/v1`. No Replit deployment or server migration was performed; this change only points the handoff and Postman requests to the production host.

**Production safety:** GET requests read live production data. POST/PATCH/PUT/DELETE requests may alter real accounts, garages, tickets, notifications, reports, or other records. Treat request bodies below as examples; do not send write requests or run the collection runner as a test. Use only when authorized and when the change is intended.

## Authentication

1. `POST /api/v1/admin-auth/sign-in` with administrator email (or the accepted `identifier` alias) and password. MFA is optional and off by default (`ADMIN_MFA_REQUIRED=false`): a successful password sign-in returns the token pair directly. If production is configured to require MFA, copy `challenge_id` and call `/api/v1/admin-auth/mfa` with the current six-digit TOTP. The first enrollment response contains a private `provisioning_uri`.
2. Save `access_token` and `refresh_token` in secure client storage. Send `Authorization: Bearer <access_token>` for every `/api/v1/admin/*` request and `/admin-auth/logout`.
3. Access tokens expire after 15 minutes. Refresh rotates the refresh token; replace both tokens after every successful refresh. TOTP challenges expire after five minutes and are single-use.
4. Use `/me` and `/menus` to build navigation. The backend permission-checks every request; a hidden frontend button is not authorization.

## Response format

JSON success envelope:

```json
{
  "success": true,
  "message": "Success",
  "data": {},
  "errors": [],
  "status_code": 200
}
```

Endpoint entries below describe `data`. Validation errors use the standard envelope with `errors: [{field, message}]`; admin auth failures also use the envelope. Some business rules raise FastAPI HTTP errors in `{"detail": ...}` format. Typical statuses: 400 (invalid MFA proof), 401 (auth), 403 (permission/scope), 404 (missing/out-of-scope resource), 409 (version/idempotency/state conflict), 422 (validation), and 429 (rate limit). Export download returns CSV/XLSX bytes, not JSON.

## Copyable response examples

These are illustrative response bodies. Token, account, and record values are placeholders. Each endpoint below also lists its own success status and `data` shape; use the OpenAPI file for typed field definitions.

### Sign-in rejected — HTTP 401

This is the response returned when credentials are rejected or the account is unavailable. The API intentionally does not reveal which condition applies.

```json
{
  "success": false,
  "message": "Invalid credentials or account unavailable.",
  "data": null,
  "errors": [],
  "status_code": 401
}
```

### Sign-in requires MFA when enabled — HTTP 200

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "challenge_id": "<challenge-uuid>",
    "mfa_required": true,
    "mfa_method": "TOTP",
    "expires_in_seconds": 300,
    "enrollment_required": false
  },
  "errors": [],
  "status_code": 200
}
```

### Password sign-in (default) — HTTP 200

With `ADMIN_MFA_REQUIRED=false`, sign-in returns the access and refresh tokens
directly in the completed sign-in response below; there is no MFA challenge or
mobile number requirement.

### Sign-in completed — HTTP 200

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "access_token": "<access-token>",
    "refresh_token": "<refresh-token>",
    "token_type": "bearer",
    "expires_in": 900,
    "user": {
      "id": "<admin-uuid>",
      "email": "<admin-email>",
      "name": "<admin-name>",
      "role": "<admin-role>",
      "is_active": true,
      "role_ids": ["<role-id>"],
      "permissions": ["<permission-code>"],
      "data_scope": {
        "type": "PLATFORM",
        "garage_ids": []
      }
    }
  },
  "errors": [],
  "status_code": 200
}
```

### Request validation failed — HTTP 422

```json
{
  "success": false,
  "message": "Validation error",
  "data": null,
  "errors": [
    {
      "field": "body.password",
      "message": "Field required"
    }
  ],
  "status_code": 422
}
```

## Endpoint URLs, request parameters, payloads and responses

Total: 70 operations (66 protected admin operations and 4 private auth operations). Each entry below shows its full production URL.

### POST `https://api.gofixcarz.com/api/v1/admin-auth/sign-in`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin-auth/sign-in`  
**Authentication:** Private auth request; no bearer token  
**Summary:** Admin sign-in (private)

**Request JSON:**

```json
{
  "email": "{{adminEmail}}",
  "password": "{{adminPassword}}",
  "device_name": "Postman development test"
}
```
**Success:** HTTP 200. `data` = MFA challenge or token pair. Challenge: challenge_id, mfa_required, mfa_method, expires_in_seconds, enrollment_required, optional provisioning_uri. Token response: access_token, refresh_token, token_type, expires_in, user { id, email, name, role, is_active, role_ids, permissions, data_scope }.

### POST `https://api.gofixcarz.com/api/v1/admin-auth/mfa`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin-auth/mfa`  
**Authentication:** Private auth request; no bearer token  
**Summary:** Complete admin MFA (private)

**Request JSON:**

```json
{
  "challenge_id": "{{mfaChallengeId}}",
  "code": "123456"
}
```
**Success:** HTTP 200. `data` = Token response: access_token, refresh_token, token_type, expires_in, user { id, email, name, role, is_active, role_ids, permissions, data_scope }.

### POST `https://api.gofixcarz.com/api/v1/admin-auth/refresh`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin-auth/refresh`  
**Authentication:** Private auth request; no bearer token  
**Summary:** Refresh admin session (private)

**Request JSON:**

```json
{
  "refresh_token": "{{refreshToken}}"
}
```
**Success:** HTTP 200. `data` = Token response: access_token, refresh_token, token_type, expires_in, user { id, email, name, role, is_active, role_ids, permissions, data_scope }.

### POST `https://api.gofixcarz.com/api/v1/admin-auth/logout`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin-auth/logout`  
**Authentication:** Bearer admin access token  
**Summary:** Admin logout (private)

**Success:** HTTP 200. `data` = { logged_out: true }

## Admin

### GET `https://api.gofixcarz.com/api/v1/admin/analytics`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/analytics`  
**Authentication:** Bearer admin access token  
**Summary:** Analytics

**Parameters:**
- `period` — query; optional; string; allowed values: daily, weekly, monthly, custom; default: monthly
- `start_date` — query; optional
- `end_date` — query; optional
- `snapshot_id` — query; optional
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Analytics summary: period, start_date, end_date, total_jobs, total_revenue, status_counts, graph_data, snapshot_id, generated_at.

### GET `https://api.gofixcarz.com/api/v1/admin/audit-logs`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/audit-logs`  
**Authentication:** Bearer admin access token  
**Summary:** Audit Logs

**Parameters:**
- `actor_id` — query; optional
- `action` — query; optional
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_AdminAuditResponse_.

### GET `https://api.gofixcarz.com/api/v1/admin/billing/issues`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/billing/issues`  
**Authentication:** Bearer admin access token  
**Summary:** Billing Issues

**Parameters:**
- `garage_id` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_JobResponse_.

### GET `https://api.gofixcarz.com/api/v1/admin/bookings`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/bookings`  
**Authentication:** Bearer admin access token  
**Summary:** Bookings

**Parameters:**
- `customer_id` — query; optional
- `search` — query; optional
- `status` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_BookingResponse_.

### GET `https://api.gofixcarz.com/api/v1/admin/dashboard`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/dashboard`  
**Authentication:** Bearer admin access token  
**Summary:** Dashboard

**Parameters:**
- `snapshot_id` — query; optional
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Dashboard counts/status_counts and revenue, plus snapshot_id, generated_at, extended_metrics and metric definitions.

### GET `https://api.gofixcarz.com/api/v1/admin/garages`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garages`  
**Authentication:** Bearer admin access token  
**Summary:** Garages

**Parameters:**
- `search` — query; optional
- `user_id` — query; optional
- `city` — query; optional
- `operational_status` — query; optional
- `verification_status` — query; optional
- `location_issue` — query; optional boolean. Omit for all locations; `true`
  selects missing, partial, or out-of-range coordinates; `false` selects valid
  coordinate pairs. Invalid boolean values return 422.
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_GarageListItem_.

For support triage, use
`/api/v1/admin/garages?operational_status=ACTIVE&location_issue=true`.
The existing admin authentication, `garages.read` permission and assigned data
scope still apply. All existing filters combine before counting and pagination;
deleted garages remain excluded. No active/verified restriction is implied by
the location filter itself.

Each list item includes `job_card_count` and read-only `location_status`:
- `MISSING`: either coordinate is null, including a partial pair. This takes
  precedence if the other coordinate is out of range.
- `INVALID`: both are present but latitude is outside [-90, 90] or longitude
  outside [-180, 180].
- `VALID`: both present and within those inclusive bounds. Zero is valid.

Coordinates are returned unchanged. This is a diagnostic, not a repair or a
guarantee of nearby-search inclusion; no verification, operations, bookings or
customer search behavior changes.

### GET `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Garage Detail

**Parameters:**
- `garage_id` — path; required; string

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminGarageDetail.

### GET `https://api.gofixcarz.com/api/v1/admin/jobs`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/jobs`  
**Authentication:** Bearer admin access token  
**Summary:** Jobs

**Parameters:**
- `status` — query; optional
- `search` — query; optional
- `customer_id` — query; optional
- `booking_id` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_JobResponse_.

### GET `https://api.gofixcarz.com/api/v1/admin/jobs/{job_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/jobs/{job_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Job Detail

**Parameters:**
- `job_id` — path; required; string

**Success:** HTTP 200. `data` = Response data schema: components.schemas.JobDetailResponse.

### GET `https://api.gofixcarz.com/api/v1/admin/me`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/me`  
**Authentication:** Bearer admin access token  
**Summary:** Admin Me

**Success:** HTTP 200. `data` = Admin identity: id, email, name, role, is_active, permissions, role_ids, data_scope.

### GET `https://api.gofixcarz.com/api/v1/admin/menus`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/menus`  
**Authentication:** Bearer admin access token  
**Summary:** Admin Menus

**Success:** HTTP 200. `data` = { menus: [{ key, label, api }] }

**Request header:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:** None

**Example response (HTTP 200):**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "menus": [
      {"key": "dashboard", "label": "Dashboard", "api": "/api/v1/admin/dashboard"},
      {"key": "users", "label": "Users", "api": "/api/v1/admin/users"},
      {"key": "garages", "label": "Garages", "api": "/api/v1/admin/garages"},
      {"key": "jobs", "label": "Jobs", "api": "/api/v1/admin/jobs"},
      {"key": "bookings", "label": "Bookings", "api": "/api/v1/admin/bookings"},
      {"key": "analytics", "label": "Analytics", "api": "/api/v1/admin/analytics"},
      {"key": "billing_issues", "label": "Billing issues", "api": "/api/v1/admin/billing/issues"},
      {"key": "audit_logs", "label": "Audit logs", "api": "/api/v1/admin/audit-logs"},
      {"key": "security", "label": "Security", "api": "/api/v1/admin/staff"},
      {"key": "customers", "label": "Customers", "api": "/api/v1/admin/customers"},
      {"key": "finance", "label": "Finance", "api": "/api/v1/admin/finance/summary"},
      {"key": "notifications", "label": "Notifications", "api": "/api/v1/admin/notifications"},
      {"key": "support", "label": "Support", "api": "/api/v1/admin/support/tickets"},
      {"key": "owners", "label": "Owner performance", "api": "/api/v1/admin/garage-owner-statistics"},
      {"key": "reports", "label": "Reports", "api": "/api/v1/admin/reports/exports"}
    ]
  },
  "errors": [],
  "status_code": 200
}
```

### GET `https://api.gofixcarz.com/api/v1/admin/users`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/users`  
**Authentication:** Bearer admin access token  
**Summary:** Users

**Parameters:**
- `search` — query; optional
- `is_active` — query; optional
- `role` — query; optional
- `include_deleted` — query; optional; boolean; default: false
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_UserResponse_.

### GET `https://api.gofixcarz.com/api/v1/admin/users/{user_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/users/{user_id}`  
**Authentication:** Bearer admin access token  
**Summary:** User Detail

**Parameters:**
- `user_id` — path; required; string
- `include_deleted` — query; optional; boolean; default: false

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminUserDetail.

### PATCH `https://api.gofixcarz.com/api/v1/admin/users/{user_id}/status`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/users/{user_id}/status`  
**Authentication:** Bearer admin access token  
**Summary:** User Status

**Parameters:**
- `user_id` — path; required; string

**Request JSON:**

```json
{
  "is_active": true
}
```
**Success:** HTTP 200. `data` = Response data schema: components.schemas.UserResponse.

## Admin Finance

### GET `https://api.gofixcarz.com/api/v1/admin/disputes`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/disputes`  
**Authentication:** Bearer admin access token  
**Summary:** Disputes

**Parameters:**
- `status` — query; optional
- `customer_id` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/disputes/{dispute_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/disputes/{dispute_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Dispute Detail

**Parameters:**
- `dispute_id` — path; required; string

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/finance/summary`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/finance/summary`  
**Authentication:** Bearer admin access token  
**Summary:** Finance Summary

**Parameters:**
- `snapshot_id` — query; optional
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Finance snapshot metadata and totals in integer INR paise: gross_collected_amount, refunded_amount, net_collected_amount, captured_payments, failed_attempts, paid/issued invoice counts, invoice totals/average, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/finance/trends`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/finance/trends`  
**Authentication:** Bearer admin access token  
**Summary:** Finance Trends

**Parameters:**
- `snapshot_id` — query; optional
- `period` — query; optional; string; allowed values: daily, weekly, monthly; default: daily
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Finance snapshot metadata, period, series[] with date and gross/refund/net integer INR paise.

### GET `https://api.gofixcarz.com/api/v1/admin/invoices`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/invoices`  
**Authentication:** Bearer admin access token  
**Summary:** Invoices

**Parameters:**
- `status` — query; optional
- `customer_id` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/invoices/{invoice_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/invoices/{invoice_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Invoice Detail

**Parameters:**
- `invoice_id` — path; required; string

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/invoices/{invoice_id}/payment-attempts`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/invoices/{invoice_id}/payment-attempts`  
**Authentication:** Bearer admin access token  
**Summary:** Payment Attempts

**Parameters:**
- `invoice_id` — path; required; string
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/payments`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/payments`  
**Authentication:** Bearer admin access token  
**Summary:** Payments

**Parameters:**
- `status` — query; optional
- `customer_id` — query; optional
- `invoice_id` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/payments/{payment_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/payments/{payment_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Payment Detail

**Parameters:**
- `payment_id` — path; required; string

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

### GET `https://api.gofixcarz.com/api/v1/admin/refunds`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/refunds`  
**Authentication:** Bearer admin access token  
**Summary:** Refunds

**Parameters:**
- `status` — query; optional
- `customer_id` — query; optional
- `payment_id` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = SourceRecord detail or paginated source records. Lists include items/total/page/page_size/pages, filters, money_unit: paise, currency: INR, source_status.

## Admin Monitoring

### GET `https://api.gofixcarz.com/api/v1/admin/activity`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/activity`  
**Authentication:** Bearer admin access token  
**Summary:** Activity

**Parameters:**
- `owner_id` — query; optional
- `customer_id` — query; optional
- `booking_id` — query; optional
- `job_id` — query; optional
- `event_type` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminActivityPage.

### GET `https://api.gofixcarz.com/api/v1/admin/activity/service-funnels/{booking_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/activity/service-funnels/{booking_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Funnel

**Parameters:**
- `booking_id` — path; required; string
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminFunnelResponse.

### GET `https://api.gofixcarz.com/api/v1/admin/audit-logs/{audit_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/audit-logs/{audit_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Audit Detail

**Parameters:**
- `audit_id` — path; required; string

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminAuditResponse.

### GET `https://api.gofixcarz.com/api/v1/admin/bookings/exception-statistics`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/bookings/exception-statistics`  
**Authentication:** Bearer admin access token  
**Summary:** Booking Exceptions

**Parameters:**
- `group_by` — query; optional
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Exception aggregate: filters, generated_at, cohort, rejected/cancelled/expired counts, reason_counts, breakdown, availability metadata.

### GET `https://api.gofixcarz.com/api/v1/admin/bookings/{booking_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/bookings/{booking_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Booking Detail

**Parameters:**
- `booking_id` — path; required; string

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminBookingDetail.

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owners`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garage-owners`  
**Authentication:** Bearer admin access token  
**Summary:** Owners

**Parameters:**
- `search` — query; optional
- `status` — query; optional
- `include_deleted` — query; optional; boolean; default: false
- `min_rating` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminOwnerPage.

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owners/{owner_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garage-owners/{owner_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Owner Detail

**Parameters:**
- `owner_id` — path; required; string
- `include_deleted` — query; optional; boolean; default: false
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Response data schema: components.schemas.AdminOwnerDetailResponse.

### GET `https://api.gofixcarz.com/api/v1/admin/jobs/{job_id}/timeline`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/jobs/{job_id}/timeline`  
**Authentication:** Bearer admin access token  
**Summary:** Timeline

**Parameters:**
- `job_id` — path; required; string
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_AdminTimelineEvent_.

## Admin Operations

### GET `https://api.gofixcarz.com/api/v1/admin/alerts`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/alerts`  
**Authentication:** Bearer admin access token  
**Summary:** Alerts

**Parameters:**
- `type` — query; optional; string; default: JOB_DELAY
- `severity` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = { items: delay alerts (id, type, severity, job/state-age fields), total, page, page_size, as_of, generation }

### GET `https://api.gofixcarz.com/api/v1/admin/announcements`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/announcements`  
**Authentication:** Bearer admin access token  
**Summary:** Announcements

**Parameters:**
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Announcement: id, status, title, message, delivery_count, created_at (send returns HTTP 202).

### POST `https://api.gofixcarz.com/api/v1/admin/announcements`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/announcements`  
**Authentication:** Bearer admin access token  
**Summary:** Send Announcement

**Parameters:**
- `Idempotency-Key` — header; required; string

**Request JSON:**

```json
{
  "preview_id": "{{preview_id}}",
  "reason": "Postman development test"
}
```
**Success:** HTTP 202. `data` = Announcement: id, status, title, message, delivery_count, created_at (send returns HTTP 202).

### POST `https://api.gofixcarz.com/api/v1/admin/announcements/preview`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/announcements/preview`  
**Authentication:** Bearer admin access token  
**Summary:** Preview Announcement

**Request JSON:**

```json
{
  "audience": {
    "recipient_roles": [
      "GARAGE_OWNER"
    ],
    "garage_ids": []
  },
  "channels": [
    "IN_APP"
  ],
  "title": "Development test announcement",
  "body": "Test message. Send only to development test accounts."
}
```
**Success:** HTTP 200. `data` = { preview_id, recipient_count, delivery_count, channels, expires_at }

### GET `https://api.gofixcarz.com/api/v1/admin/announcements/{announcement_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/announcements/{announcement_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Announcement Detail

**Parameters:**
- `announcement_id` — path; required; string

**Success:** HTTP 200. `data` = Announcement/delivery records; lists use items/total/page/page_size.

### GET `https://api.gofixcarz.com/api/v1/admin/announcements/{announcement_id}/deliveries`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/announcements/{announcement_id}/deliveries`  
**Authentication:** Bearer admin access token  
**Summary:** Announcement Deliveries

**Parameters:**
- `announcement_id` — path; required; string
- `status` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Announcement/delivery records; lists use items/total/page/page_size.

### GET `https://api.gofixcarz.com/api/v1/admin/customers`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/customers`  
**Authentication:** Bearer admin access token  
**Summary:** Customers

**Parameters:**
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `account_status` — query; optional
- `has_failed_payments` — query; optional
- `has_support_flags` — query; optional
- `inactive_since` — query; optional
- `search` — query; optional

**Success:** HTTP 200. `data` = Customer list: items, total, page, page_size. Rows include id/name/contact/account_status/last_activity_at/garage_ids/support and payment-risk flags/source/restricted_fields.

### GET `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Customer Detail

**Parameters:**
- `customer_id` — path; required; string

**Success:** HTTP 200. `data` = Customer account object with vehicles[], reviews[], preview_limit.

### GET `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}/reviews`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}/reviews`  
**Authentication:** Bearer admin access token  
**Summary:** Customer Reviews

**Parameters:**
- `customer_id` — path; required; string
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Paginated SourceRecord items: items, total, page, page_size, pages.

### GET `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}/vehicles`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}/vehicles`  
**Authentication:** Bearer admin access token  
**Summary:** Customer Vehicles

**Parameters:**
- `customer_id` — path; required; string
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Paginated SourceRecord items: items, total, page, page_size, pages.

### GET `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/reviews`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/reviews`  
**Authentication:** Bearer admin access token  
**Summary:** Garage Reviews

**Parameters:**
- `garage_id` — path; required; string
- `moderation_status` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Paginated review SourceRecord items: items, total, page, page_size, pages.

### PATCH `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/status`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/status`  
**Authentication:** Bearer admin access token  
**Summary:** Garage Status

**Parameters:**
- `garage_id` — path; required; string

**Request JSON:**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "operational_status": "ACTIVE"
}
```
**Success:** HTTP 200. `data` = { id, operational_status, verification_status, version, new_work_allowed }

### PATCH `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/verification`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/verification`  
**Authentication:** Bearer admin access token  
**Summary:** Garage Verification

**Parameters:**
- `garage_id` — path; required; string

**Request JSON:**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "verification_status": "UNVERIFIED"
}
```
**Success:** HTTP 200. `data` = { id, operational_status, verification_status, version, new_work_allowed }

### GET `https://api.gofixcarz.com/api/v1/admin/jobs/delays`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/jobs/delays`  
**Authentication:** Bearer admin access token  
**Summary:** Delays

**Parameters:**
- `status` — query; optional
- `overdue` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = { items: [{ job_id, status, state_entered_at, state_age_hours, threshold_hours, overdue }], total, page, page_size, as_of }

### GET `https://api.gofixcarz.com/api/v1/admin/notifications`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/notifications`  
**Authentication:** Bearer admin access token  
**Summary:** Notifications

**Parameters:**
- `garage_id` — query; optional
- `channel` — query; optional
- `status` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Paginated notification/delivery data: items, total, page, page_size, pages; detail returns one notification/delivery object.

### GET `https://api.gofixcarz.com/api/v1/admin/notifications/{notification_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/notifications/{notification_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Notification Detail

**Parameters:**
- `notification_id` — path; required; string

**Success:** HTTP 200. `data` = Paginated notification/delivery data: items, total, page, page_size, pages; detail returns one notification/delivery object.

### GET `https://api.gofixcarz.com/api/v1/admin/support/tickets`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/support/tickets`  
**Authentication:** Bearer admin access token  
**Summary:** Tickets

**Parameters:**
- `customer_id` — query; optional
- `status` — query; optional
- `priority` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Ticket SourceRecord or paginated ticket SourceRecord rows; mutations return updated record with incremented version.

### GET `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Ticket Detail

**Parameters:**
- `ticket_id` — path; required; string

**Success:** HTTP 200. `data` = Ticket SourceRecord or paginated ticket SourceRecord rows; mutations return updated record with incremented version.

### PATCH `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/assignment`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/assignment`  
**Authentication:** Bearer admin access token  
**Summary:** Ticket Assignment

**Parameters:**
- `ticket_id` — path; required; string

**Request JSON:**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "assignee_id": "{{assignee_id}}"
}
```
**Success:** HTTP 200. `data` = Ticket SourceRecord or paginated ticket SourceRecord rows; mutations return updated record with incremented version.

### GET `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/messages`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/messages`  
**Authentication:** Bearer admin access token  
**Summary:** Ticket Messages

**Parameters:**
- `ticket_id` — path; required; string
- `limit` — query; optional; integer; default: 30
- `cursor` — query; optional

**Success:** HTTP 200. `data` = { items: [{ id, sender_role, text, created_at, client_message_id }], next_cursor }

### POST `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/messages`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/messages`  
**Authentication:** Bearer admin access token  
**Summary:** Ticket Reply

**Parameters:**
- `ticket_id` — path; required; string

**Request JSON:**

```json
{
  "client_message_id": "postman-test-001",
  "text": "Development test reply. Do not send from production."
}
```
**Success:** HTTP 201. `data` = Message: id, sender_role, text, created_at, client_message_id (HTTP 201).

### PATCH `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/priority`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/priority`  
**Authentication:** Bearer admin access token  
**Summary:** Ticket Priority

**Parameters:**
- `ticket_id` — path; required; string

**Request JSON:**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "priority": "NORMAL"
}
```
**Success:** HTTP 200. `data` = Ticket SourceRecord or paginated ticket SourceRecord rows; mutations return updated record with incremented version.

### PATCH `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/status`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/status`  
**Authentication:** Bearer admin access token  
**Summary:** Ticket Status

**Parameters:**
- `ticket_id` — path; required; string

**Request JSON:**

```json
{
  "expected_version": 1,
  "status": "IN_PROGRESS"
}
```
**Success:** HTTP 200. `data` = Ticket SourceRecord or paginated ticket SourceRecord rows; mutations return updated record with incremented version.

## Admin Owner Statistics

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics`  
**Authentication:** Bearer admin access token  
**Summary:** Owner Statistics

**Parameters:**
- `snapshot_id` — query; optional
- `exclude_inactive` — query; optional; boolean; default: false
- `sort` — query; optional; string; allowed values: jobs_created_desc, net_collected_amount_desc, owner_name_asc; default: jobs_created_desc
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Snapshot metadata and owner metric row(s); list includes items/total/page/page_size/source_totals; trend returns series[]. Finance metrics require finance.read.

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/summary`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/summary`  
**Authentication:** Bearer admin access token  
**Summary:** Owner Summary

**Parameters:**
- `snapshot_id` — query; optional
- `exclude_inactive` — query; optional; boolean; default: false
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Snapshot metadata and owner metric row(s); list includes items/total/page/page_size/source_totals; trend returns series[]. Finance metrics require finance.read.

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/{owner_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/{owner_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Owner Detail

**Parameters:**
- `owner_id` — path; required; string
- `snapshot_id` — query; optional
- `exclude_inactive` — query; optional; boolean; default: false
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Snapshot metadata and owner metric row(s); list includes items/total/page/page_size/source_totals; trend returns series[]. Finance metrics require finance.read.

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/{owner_id}/trends`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/{owner_id}/trends`  
**Authentication:** Bearer admin access token  
**Summary:** Owner Trends

**Parameters:**
- `owner_id` — path; required; string
- `snapshot_id` — query; optional
- `exclude_inactive` — query; optional; boolean; default: false
- `period` — query; optional; string; allowed values: daily, weekly, monthly; default: daily
- `date_from` — query; optional
- `date_to` — query; optional
- `timezone` — query; optional; string; default: UTC
- `city` — query; optional
- `garage_id` — query; optional

**Success:** HTTP 200. `data` = Snapshot metadata and owner metric row(s); list includes items/total/page/page_size/source_totals; trend returns series[]. Finance metrics require finance.read.

## Admin Reports

### POST `https://api.gofixcarz.com/api/v1/admin/reports/exports`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/reports/exports`  
**Authentication:** Bearer admin access token  
**Summary:** Request Export

**Parameters:**
- `Idempotency-Key` — header; required; string

**Request JSON:**

```json
{
  "report_type": "OPERATIONS",
  "format": "CSV",
  "filters": {
    "date_from": "2026-10-01",
    "date_to": "2026-10-13",
    "timezone": "UTC"
  },
  "exclude_inactive": false
}
```
**Success:** HTTP 202. `data` = Export job: id, status, report_type, format, filters, snapshot_id, row_count, source_totals, metric_definitions, expires_at, error, download_path.

### GET `https://api.gofixcarz.com/api/v1/admin/reports/exports/{export_id}`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/reports/exports/{export_id}`  
**Authentication:** Bearer admin access token  
**Summary:** Report Status

**Parameters:**
- `export_id` — path; required; string

**Success:** HTTP 200. `data` = Export job: id, status, report_type, format, filters, snapshot_id, row_count, source_totals, metric_definitions, expires_at, error, download_path.

### GET `https://api.gofixcarz.com/api/v1/admin/reports/exports/{export_id}/download`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/reports/exports/{export_id}/download`  
**Authentication:** Bearer admin access token  
**Summary:** Download Report

**Parameters:**
- `export_id` — path; required; string

**Success:** HTTP 200. `data` = CSV/XLSX attachment bytes with Content-Disposition; not JSON.

## Admin Security

### GET `https://api.gofixcarz.com/api/v1/admin/permissions`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/permissions`  
**Authentication:** Bearer admin access token  
**Summary:** Permissions

**Success:** HTTP 200. `data` = { items: [{ code, description }] }

### GET `https://api.gofixcarz.com/api/v1/admin/roles`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/roles`  
**Authentication:** Bearer admin access token  
**Summary:** Roles

**Success:** HTTP 200. `data` = { items: [{ id, name, permissions: string[] }] }

### GET `https://api.gofixcarz.com/api/v1/admin/staff`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/staff`  
**Authentication:** Bearer admin access token  
**Summary:** Staff

**Parameters:**
- `search` — query; optional
- `is_active` — query; optional
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = { items: AdminStaff[], total, page, page_size, pages }

### PUT `https://api.gofixcarz.com/api/v1/admin/staff/{admin_id}/roles`

**Production URL:** `https://api.gofixcarz.com/api/v1/admin/staff/{admin_id}/roles`  
**Authentication:** Bearer admin access token  
**Summary:** Assign Roles

**Parameters:**
- `admin_id` — path; required; string

**Request JSON:**

```json
{
  "role_ids": [
    "role_operations"
  ],
  "data_scope": {
    "type": "PLATFORM",
    "garage_ids": []
  },
  "reason": "Postman development test; assign only to a separate test admin."
}
```
**Success:** HTTP 200. `data` = Updated AdminStaff object: { id, display_name, email, is_active, role_ids, permissions, data_scope, mfa_enrolled, mfa_required }

## Frontend integration notes

- Use the `version` returned by a GET before garage or ticket changes; never assume version 1. Stale updates return 409.
- Role IDs are `role_ceo`, `role_operations`, `role_finance`, `role_support`. Finance routes/fields require `finance.read`.
- New financial metrics use integer INR paise (₹1 = 100 paise); existing dashboard/job revenue preserves recorded-job rupees.
- Real customer, payment/refund, review, and delivery rows require authentic source data. Empty data is not proof of no upstream transactions.
- Announcement sends currently support IN_APP only; PUSH/SMS/EMAIL return 409. Send is a real inbox mutation and requires `Idempotency-Key`.
- Exports are asynchronous: request -> poll status -> download when READY.
- This handoff points to the production host provided. Write examples can alter live data; only send them when authorized and when the change is intended. No server deployment was performed.

<!-- GENERATED_ENDPOINT_EXAMPLES -->

## Complete per-endpoint request and response examples

The examples in this section are the concrete contracts for all 70 operations. They supersede the schema-only success summaries above. Every response is synthetic; it shows the response envelope and representative `data` fields, not live customer or production records.

**Before using an example:** Replace each sample UUID with an existing record ID visible to the signed-in administrator. Replace `{{...}}` variables with values from the current auth response or secure client storage. These URLs use the production host, and write operations can change production data; do not send them as test requests.

All JSON responses use the same envelope: `success`, `message`, `data`, `errors`, and `status_code`. GET operations have no request body; their example URL shows path and query values. `Idempotency-Key` is required for announcement send and report export.

Some finance fields are permission-filtered. Financial values in these examples assume an administrator with the required `finance.read` permission; the customer payment-flag filter also requires it. Updating staff roles requires `security.manage` and a recent MFA check.

### GET /api/v1/admin/activity

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/activity?owner_id=66666666-6666-4666-8666-666666666666&customer_id=77777777-7777-4777-8777-777777777777&booking_id=55555555-5555-4555-8555-555555555555&job_id=44444444-4444-4444-8444-444444444444&event_type=BOOKING_CREATED&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "event-20261012-001",
        "event_type": "JOB_CREATED",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "owner_id": "66666666-6666-4666-8666-666666666666",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "booking_id": "55555555-5555-4555-8555-555555555555",
        "job_id": "44444444-4444-4444-8444-444444444444",
        "timestamp": "2026-10-12T10:00:00Z",
        "status": "IN_PROGRESS",
        "source": "job.created_at"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1,
    "filters": {
      "timezone": "UTC",
      "date_from": "2026-10-01",
      "date_to": "2026-10-12"
    },
    "generated_at": "2026-10-12T11:00:00Z",
    "unavailable_history": [
      "payments",
      "reviews"
    ],
    "restricted_history": []
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Activity. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/activity/service-funnels/{booking_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/activity/service-funnels/55555555-5555-4555-8555-555555555555?page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "booking_id": "55555555-5555-4555-8555-555555555555",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "job_ids": [
      "44444444-4444-4444-8444-444444444444"
    ],
    "linked_jobs_truncated": false,
    "events": {
      "items": [
        {
          "id": "event-20261012-001",
          "event_type": "JOB_CREATED",
          "customer_id": "77777777-7777-4777-8777-777777777777",
          "owner_id": "66666666-6666-4666-8666-666666666666",
          "garage_id": "33333333-3333-4333-8333-333333333333",
          "booking_id": "55555555-5555-4555-8555-555555555555",
          "job_id": "44444444-4444-4444-8444-444444444444",
          "timestamp": "2026-10-12T10:00:00Z",
          "status": "IN_PROGRESS",
          "source": "job.created_at"
        }
      ],
      "total": 1,
      "page": 1,
      "page_size": 20,
      "pages": 1
    },
    "data_coverage": {
      "booking_decisions": true,
      "invoices": false,
      "payments": false,
      "reviews": false
    }
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Funnel. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/alerts

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/alerts?type=JOB_DELAY&severity=MEDIUM&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "a7be53b0-3b94-5535-8c04-1504267b8f7c",
        "type": "JOB_DELAY",
        "severity": "HIGH",
        "job_id": "44444444-4444-4444-8444-444444444444",
        "job_number": "J-2026-0042",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "status": "IN_PROGRESS",
        "state_entered_at": "2026-10-12T07:00:00Z",
        "state_age_hours": 4.5,
        "threshold_hours": 2,
        "overdue": true,
        "as_of": "2026-10-12T11:30:00Z",
        "duration_basis": "latest recorded entry to current state; creation fallback"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "as_of": "2026-10-12T11:30:00Z",
    "generation": "live deterministic state episodes"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Alerts. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/analytics

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/analytics?period=monthly&start_date=2026-10-01&end_date=2026-10-12&snapshot_id=14141414-1414-4141-8141-141414141414&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "period": "monthly",
    "start_date": "2026-01-01",
    "end_date": "2026-10-12",
    "total_jobs": 4,
    "total_revenue": "7788.00",
    "status_counts": {
      "OPEN": 0,
      "IN_PROGRESS": 1,
      "WAITING_FOR_PARTS": 0,
      "QUALITY_CHECK": 0,
      "READY": 0,
      "COMPLETED": 3,
      "CANCELLED": 0
    },
    "graph_data": [
      {
        "label": "Oct 2026",
        "job_count": 4,
        "completed_count": 3,
        "revenue": "7788.00"
      }
    ],
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Analytics. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/announcements

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/announcements?page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "status": "DELIVERED",
        "title": "Service update",
        "message": "New operating hours start Monday.",
        "delivery_count": 1,
        "created_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Announcements. Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin/announcements

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/announcements`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
Idempotency-Key: demo-idempotency-key-001
```

**Request body:**

```json
{
  "preview_id": "13131313-1313-4131-8131-131313131313",
  "reason": "Scheduled maintenance notice"
}
```

**Expected response: HTTP 202**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "status": "DELIVERED",
    "title": "Service update",
    "message": "New operating hours start Monday.",
    "delivery_count": 1,
    "created_at": "2026-10-12T10:30:00Z"
  },
  "errors": [],
  "status_code": 202
}
```

_Operation: Send Announcement. Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin/announcements/preview

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/announcements/preview`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "audience": {
    "recipient_roles": [
      "GARAGE_OWNER"
    ],
    "garage_ids": [],
    "city": "Pune",
    "operational_status": "ACTIVE"
  },
  "channels": [
    "IN_APP"
  ],
  "title": "Service update",
  "body": "New operating hours start Monday."
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "preview_id": "13131313-1313-4131-8131-131313131313",
    "recipient_count": 1,
    "delivery_count": 1,
    "channels": [
      "IN_APP"
    ],
    "expires_at": "2026-10-12T11:05:00Z"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Preview Announcement. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/announcements/{announcement_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/announcements/cccccccc-cccc-4ccc-8ccc-cccccccccccc`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "status": "DELIVERED",
    "title": "Service update",
    "message": "New operating hours start Monday.",
    "delivery_count": 1,
    "created_at": "2026-10-12T10:30:00Z"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Announcement Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/announcements/{announcement_id}/deliveries

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/announcements/cccccccc-cccc-4ccc-8ccc-cccccccccccc/deliveries?status=DELIVERED&page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "recipient_id": "66666666-6666-4666-8666-666666666666",
        "channel": "IN_APP",
        "status": "DELIVERED"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Announcement Deliveries. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/audit-logs

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/audit-logs?actor_id=11111111-1111-4111-8111-111111111111&action=example&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "actor_id": "11111111-1111-4111-8111-111111111111",
        "admin_account_id": "11111111-1111-4111-8111-111111111111",
        "action": "<example>",
        "resource_id": "11111111-1111-4111-8111-111111111111",
        "details": {},
        "created_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Audit Logs. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/audit-logs/{audit_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/audit-logs/eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    "actor_id": "22222222-2222-4222-8222-222222222222",
    "admin_account_id": "22222222-2222-4222-8222-222222222222",
    "action": "jobs.read",
    "resource_id": "44444444-4444-4444-8444-444444444444",
    "details": {
      "source": "admin_console"
    },
    "created_at": "2026-10-12T10:30:00Z"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Audit Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/billing/issues

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/billing/issues?garage_id=33333333-3333-4333-8333-333333333333&page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "job_number": "<example>",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "vehicle_id": "11111111-1111-4111-8111-111111111111",
        "booking_id": "55555555-5555-4555-8555-555555555555",
        "customer_name": "<example>",
        "customer_mobile": "<example>",
        "registration_number": "<example>",
        "brand": "<example>",
        "vehicle_model": "<example>",
        "fuel_type": "<example>",
        "odometer_km": 0,
        "photos": [],
        "inspection": null,
        "services": [
          null
        ],
        "labour": null,
        "billing": {
          "services_total": 0.0,
          "labour_total": 0.0,
          "subtotal": 0.0,
          "gst_amount": 0.0,
          "grand_total": 0.0
        },
        "status": "OPEN",
        "description": "Example description",
        "estimated_amount": 0.0,
        "final_amount": 0.0,
        "completed_at": "2026-10-12T10:30:00Z",
        "created_at": "2026-10-12T10:30:00Z",
        "updated_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Billing Issues. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/bookings

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/bookings?customer_id=77777777-7777-4777-8777-777777777777&search=Aarav&status=PENDING&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "vehicle_id": "11111111-1111-4111-8111-111111111111",
        "status": "PENDING",
        "booking_date": "2026-10-12",
        "notes": "Example notes",
        "customer_name": "<example>",
        "customer_mobile": "<example>",
        "service_requested": "<example>",
        "created_at": "2026-10-12T10:30:00Z",
        "updated_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Bookings. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/bookings/exception-statistics

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/bookings/exception-statistics?group_by=owner%2Ccity&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "filters": {
      "date_from": "2026-10-01",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "generated_at": "2026-10-12T11:00:00Z",
    "cohort": "booking.created_at",
    "rejected": 1,
    "cancelled": 0,
    "expired": 0,
    "reason_counts": {
      "UNSPECIFIED": 1
    },
    "breakdown": [
      {
        "owner_id": "66666666-6666-4666-8666-666666666666",
        "city": "Pune",
        "reason": "UNSPECIFIED",
        "count": 1
      }
    ],
    "breakdown_truncated": false,
    "unavailable_states": [
      "CANCELLED",
      "EXPIRED"
    ],
    "reason_history_available": false
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Booking Exceptions. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/bookings/{booking_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/bookings/55555555-5555-4555-8555-555555555555`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "55555555-5555-4555-8555-555555555555",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "vehicle_id": "15151515-1515-4151-8151-151515151515",
    "status": "ACCEPTED",
    "booking_date": "2026-10-15",
    "notes": "Please check the brakes",
    "customer_name": "Aarav Sharma",
    "customer_mobile": "9000000000",
    "service_requested": "Brake service",
    "created_at": "2026-10-10T08:00:00Z",
    "updated_at": "2026-10-10T08:30:00Z",
    "customer": null,
    "vehicle": null,
    "linked_job_ids": [
      "44444444-4444-4444-8444-444444444444"
    ],
    "linked_jobs_truncated": false,
    "decision_actor": "66666666-6666-4666-8666-666666666666",
    "decision_reason": "Appointment confirmed",
    "decision_timestamp": "2026-10-10T08:30:00Z",
    "missing_history": [],
    "history": [],
    "history_truncated": false
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Booking Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/customers

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/customers?page=1&page_size=20&account_status=ACTIVE&has_failed_payments=true&has_support_flags=true&inactive_since=2026-10-01T00%3A00%3A00Z&search=Aarav`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "77777777-7777-4777-8777-777777777777",
        "name": "Aarav Sharma",
        "email": "aarav@example.test",
        "mobile": "9000000000",
        "account_status": "ACTIVE",
        "last_activity_at": "2026-10-12T09:00:00Z",
        "garage_ids": [
          "33333333-3333-4333-8333-333333333333"
        ],
        "has_support_flags": true,
        "has_failed_payments": false,
        "source": "CUSTOMER_APP",
        "restricted_fields": []
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

**Permission note:** If `has_failed_payments` is supplied, the caller needs `finance.read`; otherwise that customer field is redacted.

_Operation: Customers. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/customers/{customer_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/customers/77777777-7777-4777-8777-777777777777`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "77777777-7777-4777-8777-777777777777",
    "name": "Aarav Sharma",
    "email": "aarav@example.test",
    "mobile": "9000000000",
    "account_status": "ACTIVE",
    "last_activity_at": "2026-10-12T09:00:00Z",
    "garage_ids": [
      "33333333-3333-4333-8333-333333333333"
    ],
    "has_support_flags": true,
    "has_failed_payments": false,
    "source": "CUSTOMER_APP",
    "restricted_fields": [],
    "vehicles": [
      {
        "id": "15151515-1515-4151-8151-151515151515",
        "kind": "VEHICLE",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": null,
        "status": "ACTIVE",
        "occurred_at": "2026-10-12T09:00:00Z",
        "version": 1,
        "currency": null,
        "registration_number": "MH12AB1234",
        "brand": "Maruti Suzuki",
        "model": "Swift",
        "fuel_type": "PETROL"
      }
    ],
    "reviews": [
      {
        "id": "99999999-9999-4999-8999-999999999999",
        "kind": "REVIEW",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": null,
        "status": "PUBLISHED",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": null,
        "rating": 5,
        "text": "Clear estimate and prompt service"
      }
    ],
    "preview_limit": 20
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Customer Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/customers/{customer_id}/reviews

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/customers/77777777-7777-4777-8777-777777777777/reviews?page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "99999999-9999-4999-8999-999999999999",
        "kind": "REVIEW",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": null,
        "status": "PUBLISHED",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": null,
        "rating": 5,
        "text": "Clear estimate and prompt service"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Customer Reviews. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/customers/{customer_id}/vehicles

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/customers/77777777-7777-4777-8777-777777777777/vehicles?page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "15151515-1515-4151-8151-151515151515",
        "kind": "VEHICLE",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": null,
        "status": "ACTIVE",
        "occurred_at": "2026-10-12T09:00:00Z",
        "version": 1,
        "currency": null,
        "registration_number": "MH12AB1234",
        "brand": "Maruti Suzuki",
        "model": "Swift",
        "fuel_type": "PETROL"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Customer Vehicles. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/dashboard

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/dashboard?snapshot_id=14141414-1414-4141-8141-141414141414&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "total_users": 320,
    "active_users": 286,
    "total_garages": 42,
    "total_jobs": 790,
    "jobs_today": 12,
    "status_counts": {
      "OPEN": 8,
      "IN_PROGRESS": 24,
      "WAITING_FOR_PARTS": 5,
      "QUALITY_CHECK": 3,
      "READY": 2,
      "COMPLETED": 740,
      "CANCELLED": 8
    },
    "total_bookings": 510,
    "pending_bookings": 14,
    "revenue_today": "12500.00",
    "revenue_this_month": "184250.00",
    "total_revenue": "2450000.00",
    "billing_issue_count": 3,
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "extended_metrics": {
      "gross_collected_amount": 389400,
      "refunded_amount": 0,
      "net_collected_amount": 389400,
      "captured_payments": 1,
      "failed_attempts": 0,
      "paid_invoice_count": 1,
      "issued_invoice_count": 1,
      "issued_invoice_total_amount": 389400,
      "average_invoice_amount": 389400,
      "currency": "INR",
      "money_unit": "paise",
      "source_status": "RECORDED_EVENTS",
      "snapshot_expires_at": "2026-10-12T17:00:00Z"
    }
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Dashboard. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/disputes

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/disputes?status=OPEN&customer_id=77777777-7777-4777-8777-777777777777&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
        "kind": "DISPUTE",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": "99999999-9999-4999-8999-999999999999",
        "status": "OPEN",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": null,
        "reason": "Payment not recognized",
        "amount": null
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1,
    "filters": {
      "timezone": "UTC"
    },
    "money_unit": "paise",
    "currency": "INR",
    "source_status": "RECORDED_EVENTS"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Disputes. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/disputes/{dispute_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/disputes/ffffffff-ffff-4fff-8fff-ffffffffffff`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
    "kind": "DISPUTE",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "booking_id": null,
    "job_id": null,
    "parent_id": "99999999-9999-4999-8999-999999999999",
    "status": "OPEN",
    "occurred_at": "2026-10-12T10:30:00Z",
    "version": 1,
    "currency": null,
    "reason": "Payment not recognized",
    "amount": null
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Dispute Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/finance/summary

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/finance/summary?snapshot_id=14141414-1414-4141-8141-141414141414&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "expires_at": "2026-10-12T17:00:00Z",
    "filters": {
      "date_from": "2026-09-13",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "metric_definitions": {
      "collections": "CAPTURED payment events; amounts in integer INR paise"
    },
    "gross_collected_amount": 389400,
    "refunded_amount": 0,
    "net_collected_amount": 389400,
    "captured_payments": 1,
    "failed_attempts": 0,
    "paid_invoice_count": 1,
    "issued_invoice_count": 1,
    "issued_invoice_total_amount": 389400,
    "average_invoice_amount": 389400,
    "currency": "INR",
    "money_unit": "paise",
    "source_status": "RECORDED_EVENTS"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Finance Summary. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/finance/trends

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/finance/trends?snapshot_id=14141414-1414-4141-8141-141414141414&period=daily&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "expires_at": "2026-10-12T17:00:00Z",
    "filters": {
      "date_from": "2026-10-01",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "metric_definitions": {
      "collections": "CAPTURED payment events; amounts in integer INR paise"
    },
    "period": "daily",
    "series": [
      {
        "date": "2026-10-12",
        "jobs_created": 1,
        "jobs_completed": 1,
        "gross_collected_amount": 389400,
        "refunded_amount": 0,
        "net_collected_amount": 389400
      }
    ]
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Finance Trends. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garage-owner-statistics

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics?snapshot_id=14141414-1414-4141-8141-141414141414&exclude_inactive=false&sort=jobs_created_desc&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "expires_at": "2026-10-12T17:00:00Z",
    "filters": {
      "date_from": "2026-09-13",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "metric_definitions": {
      "jobs": "created-in-window cohort; current status frozen at generated_at"
    },
    "items": [
      {
        "owner_id": "66666666-6666-4666-8666-666666666666",
        "owner_name": "Aarav Sharma",
        "garage_ids": [
          "33333333-3333-4333-8333-333333333333"
        ],
        "jobs_created": 4,
        "status_counts": {
          "OPEN": 0,
          "IN_PROGRESS": 1,
          "WAITING_FOR_PARTS": 0,
          "QUALITY_CHECK": 0,
          "READY": 0,
          "COMPLETED": 3,
          "CANCELLED": 0
        },
        "completed_jobs": 3,
        "eligible_garages": 1,
        "average_jobs_per_garage": 4.0,
        "eligible_accepted_bookings": 3,
        "converted_bookings": 2,
        "conversion_percent": 66.67,
        "completion_sample_size": 2,
        "completion_total_hours": 24.0,
        "average_completion_hours": 12.0,
        "completion_exclusions": 0,
        "garage_breakdown": [
          {
            "garage_id": "33333333-3333-4333-8333-333333333333",
            "jobs_created": 4
          }
        ],
        "gross_collected_amount": 389400,
        "refunded_amount": 0,
        "net_collected_amount": 389400,
        "captured_payments": 1,
        "failed_attempts": 0,
        "paid_invoice_count": 1,
        "issued_invoice_count": 1,
        "issued_invoice_total_amount": 389400,
        "average_invoice_amount": 389400,
        "currency": "INR",
        "money_unit": "paise",
        "source_status": "RECORDED_EVENTS",
        "missing_sources": [],
        "rank": 1
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "source_totals": {
      "jobs_created": 4,
      "eligible_garages": 1,
      "eligible_accepted_bookings": 3,
      "converted_bookings": 2,
      "completion_sample_size": 2,
      "completion_total_hours": 24.0,
      "completion_exclusions": 0,
      "gross_collected_amount": 389400,
      "refunded_amount": 0,
      "net_collected_amount": 389400,
      "paid_invoice_count": 1,
      "issued_invoice_count": 1,
      "issued_invoice_total_amount": 389400,
      "failed_attempts": 0,
      "status_counts": {
        "OPEN": 0,
        "IN_PROGRESS": 1,
        "WAITING_FOR_PARTS": 0,
        "QUALITY_CHECK": 0,
        "READY": 0,
        "COMPLETED": 3,
        "CANCELLED": 0
      },
      "average_jobs_per_garage": 4.0,
      "conversion_percent": 66.67,
      "average_completion_hours": 12.0,
      "average_invoice_amount": 389400
    }
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Owner Statistics. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garage-owner-statistics/summary

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/summary?snapshot_id=14141414-1414-4141-8141-141414141414&exclude_inactive=false&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "expires_at": "2026-10-12T17:00:00Z",
    "exclude_inactive": false,
    "filters": {
      "date_from": "2026-09-13",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "metric_definitions": {
      "jobs": "created-in-window cohort; current status frozen at generated_at"
    },
    "jobs_created": 4,
    "eligible_garages": 1,
    "eligible_accepted_bookings": 3,
    "converted_bookings": 2,
    "completion_sample_size": 2,
    "completion_total_hours": 24.0,
    "completion_exclusions": 0,
    "gross_collected_amount": 389400,
    "refunded_amount": 0,
    "net_collected_amount": 389400,
    "paid_invoice_count": 1,
    "issued_invoice_count": 1,
    "issued_invoice_total_amount": 389400,
    "failed_attempts": 0,
    "status_counts": {
      "OPEN": 0,
      "IN_PROGRESS": 1,
      "WAITING_FOR_PARTS": 0,
      "QUALITY_CHECK": 0,
      "READY": 0,
      "COMPLETED": 3,
      "CANCELLED": 0
    },
    "average_jobs_per_garage": 4.0,
    "conversion_percent": 66.67,
    "average_completion_hours": 12.0,
    "average_invoice_amount": 389400
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Owner Summary. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garage-owner-statistics/{owner_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/66666666-6666-4666-8666-666666666666?snapshot_id=14141414-1414-4141-8141-141414141414&exclude_inactive=false&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "expires_at": "2026-10-12T17:00:00Z",
    "filters": {
      "date_from": "2026-09-13",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "metric_definitions": {
      "jobs": "created-in-window cohort; current status frozen at generated_at"
    },
    "owner_id": "66666666-6666-4666-8666-666666666666",
    "owner_name": "Aarav Sharma",
    "garage_ids": [
      "33333333-3333-4333-8333-333333333333"
    ],
    "jobs_created": 4,
    "status_counts": {
      "OPEN": 0,
      "IN_PROGRESS": 1,
      "WAITING_FOR_PARTS": 0,
      "QUALITY_CHECK": 0,
      "READY": 0,
      "COMPLETED": 3,
      "CANCELLED": 0
    },
    "completed_jobs": 3,
    "eligible_garages": 1,
    "average_jobs_per_garage": 4.0,
    "eligible_accepted_bookings": 3,
    "converted_bookings": 2,
    "conversion_percent": 66.67,
    "completion_sample_size": 2,
    "completion_total_hours": 24.0,
    "average_completion_hours": 12.0,
    "completion_exclusions": 0,
    "garage_breakdown": [
      {
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "jobs_created": 4
      }
    ],
    "gross_collected_amount": 389400,
    "refunded_amount": 0,
    "net_collected_amount": 389400,
    "captured_payments": 1,
    "failed_attempts": 0,
    "paid_invoice_count": 1,
    "issued_invoice_count": 1,
    "issued_invoice_total_amount": 389400,
    "average_invoice_amount": 389400,
    "currency": "INR",
    "money_unit": "paise",
    "source_status": "RECORDED_EVENTS",
    "missing_sources": []
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Owner Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garage-owner-statistics/{owner_id}/trends

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/66666666-6666-4666-8666-666666666666/trends?snapshot_id=14141414-1414-4141-8141-141414141414&exclude_inactive=false&period=daily&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "expires_at": "2026-10-12T17:00:00Z",
    "filters": {
      "date_from": "2026-10-01",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "metric_definitions": {
      "collections": "CAPTURED payment events; amounts in integer INR paise"
    },
    "period": "daily",
    "series": [
      {
        "date": "2026-10-12",
        "jobs_created": 1,
        "jobs_completed": 1,
        "gross_collected_amount": 389400,
        "refunded_amount": 0,
        "net_collected_amount": 389400
      }
    ],
    "owner_id": "66666666-6666-4666-8666-666666666666"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Owner Trends. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garage-owners

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garage-owners?search=Aarav&status=ACTIVE&include_deleted=false&min_rating=4.5&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "66666666-6666-4666-8666-666666666666",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "name": "Aarav Sharma",
        "mobile": "9000000000",
        "country_code": "91",
        "country_code_2": null,
        "email": "aarav@example.test",
        "is_active": true,
        "account_status": "ACTIVE",
        "role": "GARAGE_OWNER",
        "created_at": "2026-01-10T09:00:00Z",
        "display_name": "Aarav Sharma",
        "garage_ids": [
          "33333333-3333-4333-8333-333333333333"
        ],
        "total_garages": 1,
        "related_garages_truncated": false,
        "cities": [
          "Pune"
        ],
        "bookings": 3,
        "jobs_created": 4,
        "completed_jobs": 2,
        "completed_job_amount_paise": 389400,
        "currency": "INR",
        "average_rating": 4.5
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1,
    "filters": {
      "timezone": "UTC",
      "date_from": "2026-10-01",
      "date_to": "2026-10-12"
    },
    "generated_at": "2026-10-12T11:00:00Z",
    "metric_bases": {
      "bookings": "booking.created_at",
      "jobs_created": "job.created_at",
      "completed_jobs": "current COMPLETED state within job.created_at cohort",
      "completed_job_amount_paise": "job.completed_at; recorded final amounts, not captured payments"
    },
    "unavailable_data_sources": [
      "reviews",
      "payment_collections"
    ]
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Owners. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garage-owners/{owner_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garage-owners/66666666-6666-4666-8666-666666666666?include_deleted=false&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "66666666-6666-4666-8666-666666666666",
    "first_name": "Aarav",
    "last_name": "Sharma",
    "name": "Aarav Sharma",
    "mobile": "9000000000",
    "country_code": "91",
    "country_code_2": null,
    "email": "aarav@example.test",
    "is_active": true,
    "account_status": "ACTIVE",
    "role": "GARAGE_OWNER",
    "created_at": "2026-01-10T09:00:00Z",
    "display_name": "Aarav Sharma",
    "garage_ids": [
      "33333333-3333-4333-8333-333333333333"
    ],
    "total_garages": 1,
    "related_garages_truncated": false,
    "cities": [
      "Pune"
    ],
    "bookings": 3,
    "jobs_created": 4,
    "completed_jobs": 2,
    "completed_job_amount_paise": 389400,
    "currency": "INR",
    "average_rating": 4.5,
    "garages": [
      {
        "id": "33333333-3333-4333-8333-333333333333",
        "user_id": "66666666-6666-4666-8666-666666666666",
        "name": "Example Auto Care",
        "owner": "Aarav Sharma",
        "operational_status": "ACTIVE",
        "verification_status": "VERIFIED",
        "version": 3,
        "address": "12 Example Road",
        "city": "Pune",
        "state": "Maharashtra",
        "zipcode": "411001",
        "country": "IN",
        "alternate_number": null,
        "wheelers": [
          "2W",
          "4W"
        ],
        "working_hours": {
          "monday": "09:00-18:00"
        },
        "latitude": 18.5204,
        "longitude": 73.8567,
        "logo_object_key": null,
        "logo_url": null,
        "created_at": "2026-01-10T09:00:00Z",
        "updated_at": "2026-10-12T10:00:00Z"
      }
    ],
    "filters": {
      "timezone": "UTC",
      "date_from": "2026-10-01",
      "date_to": "2026-10-12"
    },
    "generated_at": "2026-10-12T11:00:00Z",
    "metric_bases": {
      "bookings": "booking.created_at",
      "jobs_created": "job.created_at",
      "completed_jobs": "current COMPLETED state within job.created_at cohort",
      "completed_job_amount_paise": "job.completed_at; recorded final amounts, not captured payments"
    },
    "unavailable_data_sources": [
      "reviews",
      "payment_collections"
    ]
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Owner Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garages

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garages?search=Aarav&user_id=11111111-1111-4111-8111-111111111111&city=Pune&operational_status=ACTIVE&verification_status=UNVERIFIED&location_issue=true&page=1&page_size=20`

**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "user_id": "11111111-1111-4111-8111-111111111111",
        "name": "Example Auto Care",
        "owner": "<example>",
        "operational_status": "<example>",
        "verification_status": "<example>",
        "version": 1,
        "address": "<example>",
        "city": "Pune",
        "state": "Maharashtra",
        "zipcode": "411001",
        "country": "<example>",
        "alternate_number": "<example>",
        "wheelers": [
          "<example>"
        ],
        "working_hours": {},
        "latitude": null,
        "longitude": null,
        "location_status": "MISSING",
        "job_card_count": 0,
        "logo_object_key": "<example>",
        "logo_url": "<example>",
        "created_at": "2026-10-12T10:30:00Z",
        "updated_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Garages. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garages/{garage_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garages/33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "11111111-1111-4111-8111-111111111111",
    "user_id": "11111111-1111-4111-8111-111111111111",
    "name": "Example Auto Care",
    "owner": "<example>",
    "operational_status": "<example>",
    "verification_status": "<example>",
    "version": 1,
    "address": "<example>",
    "city": "Pune",
    "state": "Maharashtra",
    "zipcode": "411001",
    "country": "<example>",
    "alternate_number": "<example>",
    "wheelers": [
      "<example>"
    ],
    "working_hours": {},
    "latitude": "<example>",
    "longitude": "<example>",
    "logo_object_key": "<example>",
    "logo_url": "<example>",
    "created_at": "2026-10-12T10:30:00Z",
    "updated_at": "2026-10-12T10:30:00Z",
    "total_jobs": 0,
    "completed_jobs": 0,
    "total_revenue": 0.0,
    "billing_issue_count": 0
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Garage Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/garages/{garage_id}/reviews

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garages/33333333-3333-4333-8333-333333333333/reviews?moderation_status=PENDING&page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "99999999-9999-4999-8999-999999999999",
        "kind": "REVIEW",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": null,
        "status": "PUBLISHED",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": null,
        "rating": 5,
        "text": "Clear estimate and prompt service"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Garage Reviews. Replace the sample IDs and filters with values for the target record._

---

### PATCH /api/v1/admin/garages/{garage_id}/status

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garages/33333333-3333-4333-8333-333333333333/status`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "operational_status": "SUSPENDED",
  "reason": "Safety review",
  "expected_version": 3
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "33333333-3333-4333-8333-333333333333",
    "operational_status": "ACTIVE",
    "verification_status": "VERIFIED",
    "version": 4,
    "new_work_allowed": true
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Garage Status. Replace the sample IDs and filters with values for the target record._

---

### PATCH /api/v1/admin/garages/{garage_id}/verification

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/garages/33333333-3333-4333-8333-333333333333/verification`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "verification_status": "VERIFIED",
  "reason": "Documents reviewed",
  "expected_version": 3
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "33333333-3333-4333-8333-333333333333",
    "operational_status": "ACTIVE",
    "verification_status": "VERIFIED",
    "version": 4,
    "new_work_allowed": true
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Garage Verification. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/invoices

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/invoices?status=DRAFT&customer_id=77777777-7777-4777-8777-777777777777&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "99999999-9999-4999-8999-999999999999",
        "kind": "INVOICE",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": "44444444-4444-4444-8444-444444444444",
        "parent_id": null,
        "status": "PAID",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": "INR",
        "invoice_number": "INV-2026-0042",
        "subtotal": 330000,
        "tax_amount": 59400,
        "discount_amount": 0,
        "total_amount": 389400
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1,
    "filters": {
      "timezone": "UTC"
    },
    "money_unit": "paise",
    "currency": "INR",
    "source_status": "RECORDED_EVENTS"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Invoices. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/invoices/{invoice_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/invoices/99999999-9999-4999-8999-999999999999`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "99999999-9999-4999-8999-999999999999",
    "kind": "INVOICE",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "booking_id": null,
    "job_id": "44444444-4444-4444-8444-444444444444",
    "parent_id": null,
    "status": "PAID",
    "occurred_at": "2026-10-12T10:30:00Z",
    "version": 1,
    "currency": "INR",
    "invoice_number": "INV-2026-0042",
    "subtotal": 330000,
    "tax_amount": 59400,
    "discount_amount": 0,
    "total_amount": 389400,
    "linked_records": [
      {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "kind": "PAYMENT",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": "44444444-4444-4444-8444-444444444444",
        "parent_id": "99999999-9999-4999-8999-999999999999",
        "status": "CAPTURED",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": "INR",
        "gateway_reference": "pay_demo_0042",
        "amount": 389400
      }
    ],
    "preview_limit": 20
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Invoice Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/invoices/{invoice_id}/payment-attempts

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/invoices/99999999-9999-4999-8999-999999999999/payment-attempts?page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "kind": "PAYMENT",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": "44444444-4444-4444-8444-444444444444",
        "parent_id": "99999999-9999-4999-8999-999999999999",
        "status": "CAPTURED",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": "INR",
        "gateway_reference": "pay_demo_0042",
        "amount": 389400
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Payment Attempts. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/jobs

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/jobs?status=OPEN&search=Aarav&customer_id=77777777-7777-4777-8777-777777777777&booking_id=55555555-5555-4555-8555-555555555555&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "job_number": "<example>",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "vehicle_id": "11111111-1111-4111-8111-111111111111",
        "booking_id": "55555555-5555-4555-8555-555555555555",
        "customer_name": "<example>",
        "customer_mobile": "<example>",
        "registration_number": "<example>",
        "brand": "<example>",
        "vehicle_model": "<example>",
        "fuel_type": "<example>",
        "odometer_km": 0,
        "photos": [],
        "inspection": null,
        "services": [
          null
        ],
        "labour": null,
        "billing": {
          "services_total": 0.0,
          "labour_total": 0.0,
          "subtotal": 0.0,
          "gst_amount": 0.0,
          "grand_total": 0.0
        },
        "status": "OPEN",
        "description": "Example description",
        "estimated_amount": 0.0,
        "final_amount": 0.0,
        "completed_at": "2026-10-12T10:30:00Z",
        "created_at": "2026-10-12T10:30:00Z",
        "updated_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Jobs. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/jobs/delays

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/jobs/delays?status=OPEN&overdue=true&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "job_id": "44444444-4444-4444-8444-444444444444",
        "job_number": "J-2026-0042",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "status": "IN_PROGRESS",
        "state_entered_at": "2026-10-12T08:00:00Z",
        "state_age_hours": 3.5,
        "threshold_hours": 2,
        "overdue": true,
        "as_of": "2026-10-12T11:30:00Z",
        "duration_basis": "latest recorded entry to current state; creation fallback"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "as_of": "2026-10-12T11:30:00Z"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Delays. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/jobs/{job_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/jobs/44444444-4444-4444-8444-444444444444`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "11111111-1111-4111-8111-111111111111",
    "job_number": "<example>",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "vehicle_id": "11111111-1111-4111-8111-111111111111",
    "booking_id": "55555555-5555-4555-8555-555555555555",
    "customer_name": "<example>",
    "customer_mobile": "<example>",
    "registration_number": "<example>",
    "brand": "<example>",
    "vehicle_model": "<example>",
    "fuel_type": "<example>",
    "odometer_km": 0,
    "photos": [],
    "inspection": null,
    "services": [
      null
    ],
    "labour": null,
    "billing": {
      "services_total": 0.0,
      "labour_total": 0.0,
      "subtotal": 0.0,
      "gst_amount": 0.0,
      "grand_total": 0.0
    },
    "status": "OPEN",
    "description": "Example description",
    "estimated_amount": 0.0,
    "final_amount": 0.0,
    "completed_at": "2026-10-12T10:30:00Z",
    "created_at": "2026-10-12T10:30:00Z",
    "updated_at": "2026-10-12T10:30:00Z",
    "customer": {
      "id": "11111111-1111-4111-8111-111111111111",
      "garage_id": "33333333-3333-4333-8333-333333333333",
      "name": "Example Auto Care",
      "mobile": "9000000000",
      "email": "aarav@example.test",
      "address": "<example>",
      "notes": "Example notes",
      "created_at": "2026-10-12T10:30:00Z",
      "updated_at": "2026-10-12T10:30:00Z"
    },
    "vehicle": {
      "id": "11111111-1111-4111-8111-111111111111",
      "garage_id": "33333333-3333-4333-8333-333333333333",
      "customer_id": "77777777-7777-4777-8777-777777777777",
      "make": "<example>",
      "model": "<example>",
      "year": 0,
      "registration_plate": "<example>",
      "vin": "<example>",
      "colour": "<example>",
      "notes": "Example notes",
      "created_at": "2026-10-12T10:30:00Z",
      "updated_at": "2026-10-12T10:30:00Z"
    },
    "timelines": []
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Job Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/jobs/{job_id}/timeline

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/jobs/44444444-4444-4444-8444-444444444444/timeline?page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "job_id": "44444444-4444-4444-8444-444444444444",
        "status": "ACTIVE",
        "notes": "Example notes",
        "created_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Timeline. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/me

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/me`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "22222222-2222-4222-8222-222222222222",
    "email": "admin@example.test",
    "name": "Example Admin",
    "role": "ADMIN",
    "is_active": true,
    "permissions": [
      "garages.read",
      "jobs.read"
    ],
    "role_ids": [
      "role_operations"
    ],
    "data_scope": {
      "type": "PLATFORM",
      "garage_ids": []
    }
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Admin Me. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/menus

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/menus`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "menus": [
      {
        "key": "dashboard",
        "label": "Dashboard",
        "api": "/api/v1/admin/dashboard"
      },
      {
        "key": "jobs",
        "label": "Jobs",
        "api": "/api/v1/admin/jobs"
      },
      {
        "key": "support",
        "label": "Support",
        "api": "/api/v1/admin/support/tickets"
      }
    ]
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Admin Menus. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/notifications

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/notifications?garage_id=33333333-3333-4333-8333-333333333333&channel=IN_APP&status=DELIVERED&page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "title": "Job status updated",
        "message": "Your vehicle is in progress.",
        "channel": "IN_APP",
        "status": "DELIVERED",
        "read_at": null
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Notifications. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/notifications/{notification_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/notifications/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "title": "Job status updated",
    "message": "Your vehicle is in progress.",
    "channel": "IN_APP",
    "status": "DELIVERED",
    "read_at": null,
    "created_at": "2026-10-12T10:30:00Z",
    "attempts": []
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Notification Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/payments

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/payments?status=CREATED&customer_id=77777777-7777-4777-8777-777777777777&invoice_id=99999999-9999-4999-8999-999999999999&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "kind": "PAYMENT",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": "44444444-4444-4444-8444-444444444444",
        "parent_id": "99999999-9999-4999-8999-999999999999",
        "status": "CAPTURED",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": "INR",
        "gateway_reference": "pay_demo_0042",
        "amount": 389400
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1,
    "filters": {
      "timezone": "UTC"
    },
    "money_unit": "paise",
    "currency": "INR",
    "source_status": "RECORDED_EVENTS"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Payments. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/payments/{payment_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/payments/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "kind": "PAYMENT",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "booking_id": null,
    "job_id": "44444444-4444-4444-8444-444444444444",
    "parent_id": "99999999-9999-4999-8999-999999999999",
    "status": "CAPTURED",
    "occurred_at": "2026-10-12T10:30:00Z",
    "version": 1,
    "currency": "INR",
    "gateway_reference": "pay_demo_0042",
    "amount": 389400,
    "linked_records": [],
    "preview_limit": 20
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Payment Detail. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/permissions

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/permissions`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "code": "jobs.read",
        "description": "jobs read"
      },
      {
        "code": "support.reply",
        "description": "support reply"
      }
    ]
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Permissions. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/refunds

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/refunds?status=PENDING&customer_id=77777777-7777-4777-8777-777777777777&payment_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "99999999-9999-4999-8999-999999999999",
        "kind": "REFUND",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "status": "SETTLED",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": "INR",
        "reason": "Customer request",
        "amount": 0
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1,
    "filters": {
      "timezone": "UTC"
    },
    "money_unit": "paise",
    "currency": "INR",
    "source_status": "RECORDED_EVENTS"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Refunds. Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin/reports/exports

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/reports/exports`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
Idempotency-Key: demo-idempotency-key-001
```

**Request body:**

```json
{
  "report_type": "OPERATIONS",
  "format": "CSV",
  "filters": {
    "date_from": "2026-10-01",
    "date_to": "2026-10-12",
    "timezone": "Asia/Kolkata",
    "city": "Pune",
    "garage_id": null,
    "owner_id": null,
    "service_id": null
  },
  "snapshot_id": null,
  "exclude_inactive": false
}
```

**Expected response: HTTP 202**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "report_type": "OPERATIONS",
    "format": "CSV",
    "filters": {
      "date_from": "2026-10-01",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "row_count": 13,
    "source_totals": {
      "jobs_created": 4,
      "bookings_created": 9
    },
    "metric_definitions": {
      "jobs": "created-in-window cohort"
    },
    "id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "status": "QUEUED",
    "expires_at": "2026-10-13T11:00:00Z",
    "error": null,
    "download_path": null
  },
  "errors": [],
  "status_code": 202
}
```

_Operation: Request Export. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/reports/exports/{export_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/reports/exports/dddddddd-dddd-4ddd-8ddd-dddddddddddd`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "report_type": "OPERATIONS",
    "format": "CSV",
    "filters": {
      "date_from": "2026-10-01",
      "date_to": "2026-10-12",
      "timezone": "UTC"
    },
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
    "generated_at": "2026-10-12T11:00:00Z",
    "row_count": 13,
    "source_totals": {
      "jobs_created": 4,
      "bookings_created": 9
    },
    "metric_definitions": {
      "jobs": "created-in-window cohort"
    },
    "id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "status": "READY",
    "expires_at": "2026-10-13T11:00:00Z",
    "error": null,
    "download_path": "/api/v1/admin/reports/exports/dddddddd-dddd-4ddd-8ddd-dddddddddddd/download"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Report Status. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/reports/exports/{export_id}/download

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/reports/exports/dddddddd-dddd-4ddd-8ddd-dddddddddddd/download`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

This endpoint returns a file download, not a JSON envelope. For a ready CSV export, the response has `Content-Type: text/csv`, `Content-Disposition: attachment; filename="operations.csv"`, `Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`.

```text
metadata,"{...JSON report metadata...}"
booking_id,created_at,garage_id,status
55555555-5555-4555-8555-555555555555,2026-10-12T10:00:00Z,33333333-3333-4333-8333-333333333333,ACCEPTED
```

**Readiness note:** The export must have status `READY`; `QUEUED` or `PROCESSING` returns HTTP 409.

_Operation: Download Report. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/roles

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/roles`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "role_support",
        "name": "Support",
        "permissions": [
          "support.read",
          "support.reply"
        ]
      }
    ]
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Roles. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/staff

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/staff?search=Aarav&is_active=true&page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "22222222-2222-4222-8222-222222222222",
        "display_name": "Example Admin",
        "email": "admin@example.test",
        "is_active": true,
        "role_ids": [
          "role_support"
        ],
        "permissions": [
          "support.read",
          "support.reply"
        ],
        "data_scope": {
          "type": "PLATFORM",
          "garage_ids": []
        },
        "mfa_enrolled": true,
        "mfa_required": false
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Staff. Replace the sample IDs and filters with values for the target record._

---

### PUT /api/v1/admin/staff/{admin_id}/roles

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/staff/22222222-2222-4222-8222-222222222222/roles`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "role_ids": [
    "role_support"
  ],
  "data_scope": {
    "type": "PLATFORM",
    "garage_ids": []
  },
  "reason": "Assign customer support responsibilities"
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "role_support",
        "name": "Support",
        "permissions": [
          "support.read",
          "support.reply"
        ]
      }
    ]
  },
  "errors": [],
  "status_code": 200
}
```

**Authorization note:** Requires `security.manage`, a recent MFA check, and a platform-scoped admin. Self role/scope changes are rejected.

_Operation: Assign Roles. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/support/tickets

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/support/tickets?customer_id=77777777-7777-4777-8777-777777777777&status=OPEN&priority=LOW&page=1&page_size=20&date_from=2026-10-01&date_to=2026-10-12&timezone=UTC&city=Pune&garage_id=33333333-3333-4333-8333-333333333333`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "88888888-8888-4888-8888-888888888888",
        "kind": "TICKET",
        "garage_id": "33333333-3333-4333-8333-333333333333",
        "customer_id": "77777777-7777-4777-8777-777777777777",
        "booking_id": null,
        "job_id": null,
        "parent_id": null,
        "status": "IN_PROGRESS",
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": null,
        "subject": "Brake service question",
        "description": "Please share an update.",
        "priority": "HIGH",
        "assignee_id": "22222222-2222-4222-8222-222222222222"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Tickets. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/support/tickets/{ticket_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/88888888-8888-4888-8888-888888888888`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "88888888-8888-4888-8888-888888888888",
    "kind": "TICKET",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "booking_id": null,
    "job_id": null,
    "parent_id": null,
    "status": "IN_PROGRESS",
    "occurred_at": "2026-10-12T10:30:00Z",
    "version": 1,
    "currency": null,
    "subject": "Brake service question",
    "description": "Please share an update.",
    "priority": "HIGH",
    "assignee_id": "22222222-2222-4222-8222-222222222222"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Ticket Detail. Replace the sample IDs and filters with values for the target record._

---

### PATCH /api/v1/admin/support/tickets/{ticket_id}/assignment

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/88888888-8888-4888-8888-888888888888/assignment`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "assignee_id": "22222222-2222-4222-8222-222222222222",
  "reason": "Assign to support queue",
  "expected_version": 2
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "88888888-8888-4888-8888-888888888888",
    "kind": "TICKET",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "booking_id": null,
    "job_id": null,
    "parent_id": null,
    "status": "IN_PROGRESS",
    "occurred_at": "2026-10-12T10:30:00Z",
    "version": 3,
    "currency": null,
    "subject": "Brake service question",
    "description": "Please share an update.",
    "priority": "HIGH",
    "assignee_id": "22222222-2222-4222-8222-222222222222"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Ticket Assignment. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/support/tickets/{ticket_id}/messages

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/88888888-8888-4888-8888-888888888888/messages?limit=30&cursor=11111111-1111-4111-8111-111111111111`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "12121212-1212-4121-8121-121212121212",
        "sender_role": "ADMIN",
        "text": "The garage has confirmed the appointment.",
        "created_at": "2026-10-12T10:30:00Z",
        "client_message_id": "support-reply-demo-001"
      }
    ],
    "next_cursor": null
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Ticket Messages. Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin/support/tickets/{ticket_id}/messages

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/88888888-8888-4888-8888-888888888888/messages`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "client_message_id": "support-reply-demo-001",
  "text": "The garage has confirmed the appointment."
}
```

**Expected response: HTTP 201**

```json
{
  "success": true,
  "message": "Created successfully",
  "data": {
    "id": "12121212-1212-4121-8121-121212121212",
    "sender_role": "ADMIN",
    "text": "The garage has confirmed the appointment.",
    "created_at": "2026-10-12T10:30:00Z",
    "client_message_id": "support-reply-demo-001"
  },
  "errors": [],
  "status_code": 201
}
```

_Operation: Ticket Reply. Replace the sample IDs and filters with values for the target record._

---

### PATCH /api/v1/admin/support/tickets/{ticket_id}/priority

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/88888888-8888-4888-8888-888888888888/priority`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "priority": "HIGH",
  "reason": "Customer cannot use vehicle",
  "expected_version": 2
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "88888888-8888-4888-8888-888888888888",
    "kind": "TICKET",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "booking_id": null,
    "job_id": null,
    "parent_id": null,
    "status": "IN_PROGRESS",
    "occurred_at": "2026-10-12T10:30:00Z",
    "version": 3,
    "currency": null,
    "subject": "Brake service question",
    "description": "Please share an update.",
    "priority": "HIGH",
    "assignee_id": "22222222-2222-4222-8222-222222222222"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Ticket Priority. Replace the sample IDs and filters with values for the target record._

---

### PATCH /api/v1/admin/support/tickets/{ticket_id}/status

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/support/tickets/88888888-8888-4888-8888-888888888888/status`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "status": "RESOLVED",
  "resolution": "Replacement part installed",
  "expected_version": 2
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "88888888-8888-4888-8888-888888888888",
    "kind": "TICKET",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "booking_id": null,
    "job_id": null,
    "parent_id": null,
    "status": "RESOLVED",
    "occurred_at": "2026-10-12T10:30:00Z",
    "version": 3,
    "currency": null,
    "subject": "Brake service question",
    "description": "Please share an update.",
    "priority": "HIGH",
    "assignee_id": "22222222-2222-4222-8222-222222222222",
    "resolution": "Replacement part installed"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Ticket Status. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/users

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/users?search=Aarav&is_active=true&role=garage_owner&include_deleted=false&page=1&page_size=20`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "items": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "name": "Example Auto Care",
        "mobile": "9000000000",
        "country_code": "91",
        "country_code_2": "<example>",
        "email": "aarav@example.test",
        "is_active": true,
        "account_status": "ACTIVE",
        "role": "garage_owner",
        "created_at": "2026-10-12T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "pages": 1
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Users. Replace the sample IDs and filters with values for the target record._

---

### GET /api/v1/admin/users/{user_id}

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/users/11111111-1111-4111-8111-111111111111?include_deleted=false`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "id": "11111111-1111-4111-8111-111111111111",
    "first_name": "Aarav",
    "last_name": "Sharma",
    "name": "Example Auto Care",
    "mobile": "9000000000",
    "country_code": "91",
    "country_code_2": "<example>",
    "email": "aarav@example.test",
    "is_active": true,
    "account_status": "ACTIVE",
    "role": "garage_owner",
    "created_at": "2026-10-12T10:30:00Z",
    "garages": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "user_id": "11111111-1111-4111-8111-111111111111",
        "name": "Example Auto Care",
        "owner": "<example>",
        "operational_status": "<example>",
        "verification_status": "<example>",
        "version": 1,
        "address": "<example>",
        "city": "Pune",
        "state": "Maharashtra",
        "zipcode": "411001",
        "country": "<example>",
        "alternate_number": "<example>",
        "wheelers": [
          "<example>"
        ],
        "working_hours": {},
        "latitude": "<example>",
        "longitude": "<example>",
        "logo_object_key": "<example>",
        "logo_url": "<example>",
        "created_at": "2026-10-12T10:30:00Z",
        "updated_at": "2026-10-12T10:30:00Z"
      }
    ]
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: User Detail. Replace the sample IDs and filters with values for the target record._

---

### PATCH /api/v1/admin/users/{user_id}/status

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin/users/11111111-1111-4111-8111-111111111111/status`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
Content-Type: application/json
```

**Request body:**

```json
{
  "is_active": false
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Account status updated",
  "data": {
    "id": "11111111-1111-4111-8111-111111111111",
    "first_name": "Aarav",
    "last_name": "Sharma",
    "name": "Example Auto Care",
    "mobile": "9000000000",
    "country_code": "91",
    "country_code_2": "<example>",
    "email": "aarav@example.test",
    "is_active": true,
    "account_status": "ACTIVE",
    "role": "garage_owner",
    "created_at": "2026-10-12T10:30:00Z"
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: User Status. Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin-auth/logout

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin-auth/logout`  
**Request headers:**

```http
Authorization: Bearer {{admin_access_token}}
```

**Request body:**

None.

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "success": true,
    "message": "Example response message",
    "data": {
      "logged_out": true
    },
    "errors": [],
    "status_code": 0
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Admin logout (private). Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin-auth/mfa

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin-auth/mfa`  
**Request headers:**

```http
Content-Type: application/json
```

**Request body:**

```json
{
  "challenge_id": "13131313-1313-4131-8131-131313131313",
  "code": "123456"
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "success": true,
    "message": "Example response message",
    "data": {
      "access_token": "<example>",
      "refresh_token": "<example>",
      "token_type": "<example>",
      "expires_in": 0,
      "user": {
        "id": "11111111-1111-4111-8111-111111111111",
        "email": "aarav@example.test",
        "name": "Example Auto Care",
        "role": "GARAGE_OWNER",
        "is_active": true,
        "role_ids": [],
        "permissions": [
          "<example>"
        ],
        "data_scope": {
          "type": "PLATFORM",
          "garage_ids": []
        }
      }
    },
    "errors": [],
    "status_code": 0
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Complete admin MFA (private). Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin-auth/refresh

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin-auth/refresh`  
**Request headers:**

```http
Content-Type: application/json
```

**Request body:**

```json
{
  "refresh_token": "{{adminRefreshTokenAtLeast32Chars}}"
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "success": true,
    "message": "Example response message",
    "data": {
      "access_token": "<example>",
      "refresh_token": "<example>",
      "token_type": "<example>",
      "expires_in": 0,
      "user": {
        "id": "11111111-1111-4111-8111-111111111111",
        "email": "aarav@example.test",
        "name": "Example Auto Care",
        "role": "GARAGE_OWNER",
        "is_active": true,
        "role_ids": [],
        "permissions": [
          "<example>"
        ],
        "data_scope": {
          "type": "PLATFORM",
          "garage_ids": []
        }
      }
    },
    "errors": [],
    "status_code": 0
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Refresh admin session (private). Replace the sample IDs and filters with values for the target record._

---

### POST /api/v1/admin-auth/sign-in

**Endpoint:** `https://api.gofixcarz.com/api/v1/admin-auth/sign-in`  
**Request headers:**

```http
Content-Type: application/json
```

**Request body:**

```json
{
  "email": "admin@example.test",
  "password": "{{adminPassword}}",
  "device_name": "Admin web"
}
```

**Expected response: HTTP 200**

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "access_token": "<access-token-from-response>",
    "refresh_token": "<refresh-token-from-response>",
    "token_type": "bearer",
    "expires_in": 900,
    "user": {
      "id": "22222222-2222-4222-8222-222222222222",
      "email": "admin@example.test",
      "name": "Example Admin",
      "role": "ADMIN",
      "is_active": true,
      "role_ids": [
        "role_operations"
      ],
      "permissions": [
        "garages.read",
        "jobs.read",
        "support.read"
      ],
      "data_scope": {
        "type": "PLATFORM",
        "garage_ids": []
      }
    }
  },
  "errors": [],
  "status_code": 200
}
```

_Operation: Admin sign-in (private). Replace the sample IDs and filters with values for the target record._

---
