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

1. `POST /api/v1/admin-auth/sign-in` with administrator email (or the accepted `identifier` alias) and password. If `mfa_required` is true, copy `challenge_id` and call `/api/v1/admin-auth/mfa` with the current six-digit TOTP. On first enrollment, the password-verified sign-in response also contains a secret `provisioning_uri` for an authenticator.
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

### Sign-in requires MFA — HTTP 200

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
- `page` — query; optional; integer; default: 1
- `page_size` — query; optional; integer; default: 20

**Success:** HTTP 200. `data` = Response data schema: components.schemas.PaginatedData_GarageResponse_.

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
