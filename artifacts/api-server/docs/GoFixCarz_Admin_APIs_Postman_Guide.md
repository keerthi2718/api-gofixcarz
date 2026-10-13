# GoFixCarz Admin APIs — Postman guide (production target)

This file accompanies **GoFixCarz_Admin_APIs.postman_collection.json**. Import that collection into Postman. It targets the live production API; read the production warning before sending any request.

- Public admin operations: **66**. Private auth operations: **4**.
- Base path: `https://api.gofixcarz.com/api/v1/admin`; private auth path: `https://api.gofixcarz.com/api/v1/admin-auth`.
- Set `base_url` to `https://api.gofixcarz.com/api/v1` (includes `/api/v1`; requests append `/admin/...` or `/admin-auth/...`).
- Create a private Postman environment. Set `adminEmail`, `adminPassword` (mark it Secret), `adminToken` (Secret), `refreshToken` (Secret), and `mfaChallengeId`. Do not put real credentials in an exported collection.
- Send **Sign In**. If it returns an MFA challenge, copy `data.challenge_id` into `mfaChallengeId`. On first enrollment only, add `data.provisioning_uri` to an authenticator. Then send **Complete MFA** with the current six-digit code.
- The example MFA code is a placeholder. TOTP challenges expire in five minutes and are single-use. Refresh rotates the refresh token; replace both environment values with the new ones.
- UUID path placeholders are examples, not real records. For authorized versioned writes, first GET the production record and use its current `expected_version`; stale versions return 409. Do not use live records to test mutations.
- PRODUCTION WARNING: this collection targets live data. GET requests read production records; POST/PATCH/PUT/DELETE requests may create or change live data or send in-app messages. Do not run mutations or the collection runner for testing. Financial reads require a finance-authorized role. Live customer/finance/review results require authentic source records.
- Announcement previews support `IN_APP`; PUSH/SMS/EMAIL currently return `CHANNEL_NOT_CONFIGURED`. Reuse an Idempotency-Key only when retrying the same request.
- Standard responses use the API envelope: `success`, `message`, `data`, `errors`, `status_code`.

## Production base and endpoint URLs

The API base URL supplied for this handoff is `https://api.gofixcarz.com/api/v1`. For example, sign-in is `https://api.gofixcarz.com/api/v1/admin-auth/sign-in` and the admin identity endpoint is `https://api.gofixcarz.com/api/v1/admin/me`. The imported collection now uses the matching `base_url` variable.

## 00 Private Authentication

### POST `https://api.gofixcarz.com/api/v1/admin-auth/sign-in` — Sign In (private)

Private admin password verification. If MFA is required, the response contains challenge_id and (on first enrollment only) provisioning_uri. Add the URI to an authenticator, then use Complete MFA. Never share the provisioning URI or tokens.

**Example JSON body**

```json
{
  "email": "{{adminEmail}}",
  "password": "{{adminPassword}}",
  "device_name": "Postman development test"
}
```

### POST `https://api.gofixcarz.com/api/v1/admin-auth/mfa` — Complete MFA (private)

Enter the current six-digit TOTP from the enrolled authenticator. The example code is a placeholder. Challenge expires after five minutes and is single-use. Copy data.access_token to the Postman environment variable adminToken and data.refresh_token to refreshToken.

**Example JSON body**

```json
{
  "challenge_id": "{{mfaChallengeId}}",
  "code": "123456"
}
```

### POST `https://api.gofixcarz.com/api/v1/admin-auth/refresh` — Refresh Session (private)

Refresh tokens rotate: copy the newly returned access_token and refresh_token over the old environment values. Reusing the old refresh token revokes its family.

**Example JSON body**

```json
{
  "refresh_token": "{{refreshToken}}"
}
```

### POST `https://api.gofixcarz.com/api/v1/admin-auth/logout` — Logout (private)

Revoke the current dedicated admin session. Requires Bearer {{adminToken}}.

## Admin

### GET `https://api.gofixcarz.com/api/v1/admin/menus` — Admin Menus

### GET `https://api.gofixcarz.com/api/v1/admin/me` — Admin Me

Admin identity; no owned garage is required.

### GET `https://api.gofixcarz.com/api/v1/admin/dashboard` — Dashboard

**Parameters**

- `snapshot_id` (query; optional)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/users` — Users

**Parameters**

- `search` (query; optional)
- `is_active` (query; optional)
- `role` (query; optional)
- `include_deleted` (query; optional; default: false)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/users/{user_id}` — User Detail

**Parameters**

- `user_id` (path; required)
- `include_deleted` (query; optional; default: false)

### PATCH `https://api.gofixcarz.com/api/v1/admin/users/{user_id}/status` — User Status

Activate/deactivate garage-owner accounts; admin deactivation is disallowed.

**Parameters**

- `user_id` (path; required)

**Example JSON body**

```json
{
  "is_active": true
}
```

### GET `https://api.gofixcarz.com/api/v1/admin/garages` — Garages

**Parameters**

- `search` (query; optional)
- `user_id` (query; optional)
- `city` (query; optional)
- `operational_status` (query; optional)
- `verification_status` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}` — Garage Detail

**Parameters**

- `garage_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/jobs` — Jobs

**Parameters**

- `status` (query; optional)
- `search` (query; optional)
- `customer_id` (query; optional)
- `booking_id` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/jobs/{job_id}` — Job Detail

**Parameters**

- `job_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/bookings` — Bookings

**Parameters**

- `customer_id` (query; optional)
- `search` (query; optional)
- `status` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/analytics` — Analytics

**Parameters**

- `period` (query; optional; values: daily, weekly, monthly, custom; default: monthly)
- `start_date` (query; optional)
- `end_date` (query; optional)
- `snapshot_id` (query; optional)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/billing/issues` — Billing Issues

Read-only review of completed jobs missing final amount, billing or completion time.

**Parameters**

- `garage_id` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/audit-logs` — Audit Logs

**Parameters**

- `actor_id` (query; optional)
- `action` (query; optional)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

## Admin Finance

### GET `https://api.gofixcarz.com/api/v1/admin/finance/summary` — Finance Summary

**Parameters**

- `snapshot_id` (query; optional)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/finance/trends` — Finance Trends

**Parameters**

- `snapshot_id` (query; optional)
- `period` (query; optional; values: daily, weekly, monthly; default: daily)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/invoices` — Invoices

**Parameters**

- `status` (query; optional)
- `customer_id` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/payments` — Payments

**Parameters**

- `status` (query; optional)
- `customer_id` (query; optional)
- `invoice_id` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/refunds` — Refunds

**Parameters**

- `status` (query; optional)
- `customer_id` (query; optional)
- `payment_id` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/disputes` — Disputes

**Parameters**

- `status` (query; optional)
- `customer_id` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/invoices/{invoice_id}` — Invoice Detail

**Parameters**

- `invoice_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/payments/{payment_id}` — Payment Detail

**Parameters**

- `payment_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/disputes/{dispute_id}` — Dispute Detail

**Parameters**

- `dispute_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/invoices/{invoice_id}/payment-attempts` — Payment Attempts

**Parameters**

- `invoice_id` (path; required)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

## Admin Monitoring

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owners` — Owners

**Parameters**

- `search` (query; optional)
- `status` (query; optional)
- `include_deleted` (query; optional; default: false)
- `min_rating` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owners/{owner_id}` — Owner Detail

**Parameters**

- `owner_id` (path; required)
- `include_deleted` (query; optional; default: false)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/bookings/exception-statistics` — Booking Exceptions

**Parameters**

- `group_by` (query; optional)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/bookings/{booking_id}` — Booking Detail

**Parameters**

- `booking_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/jobs/{job_id}/timeline` — Timeline

**Parameters**

- `job_id` (path; required)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/audit-logs/{audit_id}` — Audit Detail

**Parameters**

- `audit_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/activity` — Activity

**Parameters**

- `owner_id` (query; optional)
- `customer_id` (query; optional)
- `booking_id` (query; optional)
- `job_id` (query; optional)
- `event_type` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/activity/service-funnels/{booking_id}` — Funnel

**Parameters**

- `booking_id` (path; required)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

## Admin Operations

### PATCH `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/status` — Garage Status

**Parameters**

- `garage_id` (path; required)

**Example JSON body**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "operational_status": "ACTIVE"
}
```

### PATCH `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/verification` — Garage Verification

**Parameters**

- `garage_id` (path; required)

**Example JSON body**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "verification_status": "UNVERIFIED"
}
```

### GET `https://api.gofixcarz.com/api/v1/admin/garages/{garage_id}/reviews` — Garage Reviews

**Parameters**

- `garage_id` (path; required)
- `moderation_status` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/customers` — Customers

**Parameters**

- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `account_status` (query; optional)
- `has_failed_payments` (query; optional)
- `has_support_flags` (query; optional)
- `inactive_since` (query; optional)
- `search` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}` — Customer Detail

**Parameters**

- `customer_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}/vehicles` — Customer Vehicles

**Parameters**

- `customer_id` (path; required)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/customers/{customer_id}/reviews` — Customer Reviews

**Parameters**

- `customer_id` (path; required)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/jobs/delays` — Delays

**Parameters**

- `status` (query; optional)
- `overdue` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/alerts` — Alerts

**Parameters**

- `type` (query; optional; default: JOB_DELAY)
- `severity` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/notifications` — Notifications

**Parameters**

- `garage_id` (query; optional)
- `channel` (query; optional)
- `status` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/notifications/{notification_id}` — Notification Detail

**Parameters**

- `notification_id` (path; required)

### POST `https://api.gofixcarz.com/api/v1/admin/announcements/preview` — Preview Announcement

**Example JSON body**

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

### POST `https://api.gofixcarz.com/api/v1/admin/announcements` — Send Announcement

**Parameters**

- `Idempotency-Key` (header; required)

**Example JSON body**

```json
{
  "preview_id": "{{preview_id}}",
  "reason": "Postman development test"
}
```

### GET `https://api.gofixcarz.com/api/v1/admin/announcements` — Announcements

**Parameters**

- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/announcements/{announcement_id}` — Announcement Detail

**Parameters**

- `announcement_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/announcements/{announcement_id}/deliveries` — Announcement Deliveries

**Parameters**

- `announcement_id` (path; required)
- `status` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### GET `https://api.gofixcarz.com/api/v1/admin/support/tickets` — Tickets

**Parameters**

- `customer_id` (query; optional)
- `status` (query; optional)
- `priority` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}` — Ticket Detail

**Parameters**

- `ticket_id` (path; required)

### PATCH `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/assignment` — Ticket Assignment

**Parameters**

- `ticket_id` (path; required)

**Example JSON body**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "assignee_id": "{{assignee_id}}"
}
```

### PATCH `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/priority` — Ticket Priority

**Parameters**

- `ticket_id` (path; required)

**Example JSON body**

```json
{
  "reason": "Postman development test",
  "expected_version": 1,
  "priority": "NORMAL"
}
```

### PATCH `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/status` — Ticket Status

**Parameters**

- `ticket_id` (path; required)

**Example JSON body**

```json
{
  "expected_version": 1,
  "status": "IN_PROGRESS"
}
```

### GET `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/messages` — Ticket Messages

**Parameters**

- `ticket_id` (path; required)
- `limit` (query; optional; default: 30)
- `cursor` (query; optional)

### POST `https://api.gofixcarz.com/api/v1/admin/support/tickets/{ticket_id}/messages` — Ticket Reply

**Parameters**

- `ticket_id` (path; required)

**Example JSON body**

```json
{
  "client_message_id": "postman-test-001",
  "text": "Development test reply. Do not send from production."
}
```

## Admin Owner Statistics

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics` — Owner Statistics

**Parameters**

- `snapshot_id` (query; optional)
- `exclude_inactive` (query; optional; default: false)
- `sort` (query; optional; values: jobs_created_desc, net_collected_amount_desc, owner_name_asc; default: jobs_created_desc)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/summary` — Owner Summary

**Parameters**

- `snapshot_id` (query; optional)
- `exclude_inactive` (query; optional; default: false)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/{owner_id}` — Owner Detail

**Parameters**

- `owner_id` (path; required)
- `snapshot_id` (query; optional)
- `exclude_inactive` (query; optional; default: false)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

### GET `https://api.gofixcarz.com/api/v1/admin/garage-owner-statistics/{owner_id}/trends` — Owner Trends

**Parameters**

- `owner_id` (path; required)
- `snapshot_id` (query; optional)
- `exclude_inactive` (query; optional; default: false)
- `period` (query; optional; values: daily, weekly, monthly; default: daily)
- `date_from` (query; optional)
- `date_to` (query; optional)
- `timezone` (query; optional; default: UTC)
- `city` (query; optional)
- `garage_id` (query; optional)

## Admin Reports

### POST `https://api.gofixcarz.com/api/v1/admin/reports/exports` — Request Export

**Parameters**

- `Idempotency-Key` (header; required)

**Example JSON body**

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

### GET `https://api.gofixcarz.com/api/v1/admin/reports/exports/{export_id}` — Report Status

**Parameters**

- `export_id` (path; required)

### GET `https://api.gofixcarz.com/api/v1/admin/reports/exports/{export_id}/download` — Download Report

**Parameters**

- `export_id` (path; required)

## Admin Security

### GET `https://api.gofixcarz.com/api/v1/admin/permissions` — Permissions

### GET `https://api.gofixcarz.com/api/v1/admin/roles` — Roles

### GET `https://api.gofixcarz.com/api/v1/admin/staff` — Staff

**Parameters**

- `search` (query; optional)
- `is_active` (query; optional)
- `page` (query; optional; default: 1)
- `page_size` (query; optional; default: 20)

### PUT `https://api.gofixcarz.com/api/v1/admin/staff/{admin_id}/roles` — Assign Roles

**Parameters**

- `admin_id` (path; required)

**Example JSON body**

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

