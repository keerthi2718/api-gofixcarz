# Garage-owner account archival and CORS

## Account status

`account_status` in owner identity/profile and admin user responses is:

- `ACTIVE`: not archived and active.
- `INACTIVE`: not archived but disabled.
- `DELETED`: deletion timestamp is set; sign-in and existing credentials are denied.

Status is derived from existing database fields. No schema migration is needed.

## Owner endpoint

```http
DELETE /api/v1/auth/account
Authorization: Bearer <garage_owner_access_token>
Content-Type: application/json

{"confirm": true}
```

Example success (the usual API envelope may contain additional standard fields):

```json
{
  "success": true,
  "message": "Account marked deleted. All sessions have been revoked.",
  "data": {
    "account_id": "<owner_uuid>",
    "account_status": "DELETED",
    "is_active": false,
    "deleted_at": "2026-10-10T14:30:00+00:00",
    "sessions_revoked": true,
    "data_retained": true
  }
}
```

The endpoint targets the authenticated account only. It cannot accept another
account ID, an arbitrary status, or an administrator account. Confirmation must
be the JSON boolean `true` (not a string or number). Missing/false confirmation
returns 422. Missing/invalid/deleted credentials return 401; an authenticated
legacy admin principal returns 403.

Owner personal data, garages, customers, vehicles, bookings, jobs and billing
are retained. OTP state is cleared, all refresh credentials are revoked, and
existing owner access tokens fail the live account check. Changes and the audit
record commit atomically. The app should confirm with the owner, call the API,
then clear local access/refresh credentials and return to sign-in.

The original mobile/email remain reserved by existing unique constraints. No
automatic restoration or duplicate account creation is provided. A retry using
the former token returns 401 because access has already been revoked.

## Authorized historical retrieval

Default admin user reads continue to exclude deleted accounts. Administrators
can explicitly retrieve retained records:

```http
GET /api/v1/admin/users?include_deleted=true&is_active=false
GET /api/v1/admin/users/<owner_uuid>?include_deleted=true
```

The inactive list may contain both `INACTIVE` and `DELETED` records; inspect
`account_status` to distinguish them. Linked records remain stored and available
to authorized administrative reads. Normal owner access is not restored by this
flag. The existing activate/deactivate endpoint cannot reactivate a deleted user.

## CORS

The default `CORS_ORIGINS` is `["*"]`, allowing any browser origin and localhost
port. All methods/headers, including Authorization and Content-Type, are allowed.
Cookie credentials are disabled; use bearer tokens without fetch
`credentials: "include"` or Axios `withCredentials: true`. An explicitly set
`CORS_ORIGINS` environment override can still restrict the default.

## App Store caveat

This is the status-based retention policy requested by the product owner. It
does not erase personal data. Simply deactivating/archiving an account may not
satisfy Apple's account-deletion rules; do not promise approval on this basis.
The native application also needs an appropriate in-app action. True erasure
and legal retention requirements need a separately approved policy.
