# Platform admin APIs

Base path: `/api/v1/admin`. Swagger documentation: `/api/docs`.

## Login and authorization

Admins use the existing authentication flow:

1. `POST /api/v1/auth/sign-in` with `{"mobile":"<registered 10-digit mobile>"}`.
2. `POST /api/v1/auth/verify-otp` with mobile and received OTP.
3. Read `data.access_token` and `data.user.role` (`admin` or `garage_owner`).
4. Send `Authorization: Bearer <access_token>` on admin requests.
5. Refresh through `POST /api/v1/auth/refresh`.

An admin does not need to own a garage. Tokens include a signed `role` claim,
but the database role is checked on every request. An old token cannot retain
admin permissions after demotion. Inactive/deleted accounts are denied.
Missing/invalid JWTs return 401; authenticated non-admin accounts return 403.

## Endpoints

| Method | Path | Inputs / behavior |
|---|---|---|
| GET | `/me` | Current admin identity |
| GET | `/dashboard` | Platform counts, status breakdown, revenue and billing issue count |
| GET | `/users` | `search`, `is_active`, `role`, pagination |
| GET | `/users/{user_id}` | User and their garages |
| PATCH | `/users/{user_id}/status` | `{"is_active":false}` or `true` |
| GET | `/garages` | `search`, `user_id`, pagination |
| GET | `/garages/{garage_id}` | Garage with job/revenue/billing issue totals |
| GET | `/jobs` | `garage_id`, `status`, `search`, `date_from`, `date_to`, pagination |
| GET | `/jobs/{job_id}` | Details, saved billing and timeline |
| GET | `/bookings` | `garage_id`, `status`, pagination |
| GET | `/analytics` | Optional `garage_id`; `period=daily\|weekly\|monthly\|custom`; custom requires dates |
| GET | `/billing/issues` | Optional `garage_id`, pagination; read-only |
| GET | `/audit-logs` | `actor_id`, `action`, `date_from`, `date_to`, pagination |

Pagination uses `page=1&page_size=20`, maximum page size 100. Responses use
the existing envelope: `success`, `message`, `data`, `errors`, `status_code`.
Lists have `data.items`, `total`, `page`, `page_size`, `pages`. Dates are ISO dates.
Money is serialized as two-decimal numeric values (JSON numbers).

Successful admin reads and status changes are recorded in the audit table.
Status changes and their audit entry commit in the same transaction.
OTP values, tokens, token hashes and full request bodies are never included.
Deactivation revokes refresh tokens and clears outstanding OTPs. Admin accounts
cannot be deactivated through the dashboard, preventing accidental admin lockout.
Role assignment is not exposed through signup, profile or status APIs.

Existing garage-owner APIs retain their ownership checks. `/admin` APIs provide
the platform-wide access; an admin JWT is not a bypass for owner endpoints.
Billing issue review does not recalculate historical bills or invent timestamps.
Revenue is based on completed jobs' saved final amounts and completion dates;
job counts are based on creation dates. Report dates use server/DB dates,
matching the existing backend's reporting convention.

## First admin setup

All existing accounts default to `garage_owner`. No account is auto-promoted.
A trusted operator must select an existing, active account.

For **development only**, from `artifacts/api-server`:

```sh
python scripts/grant_dev_admin.py --user-id <UUID>
python scripts/grant_dev_admin.py --user-id <UUID> --apply
```

The first command previews access; the second grants it and records a bootstrap
audit entry. This tool refuses non-internal-development database targets.
Sign in again for a token whose displayed role is `admin`.

For Replit-managed production, publish the development schema changes through
the normal Publishing flow. A development role assignment does **not** promote
the same account in production. The trusted production operator must separately
assign `admin` to the chosen production account in the database management UI.
Do not enable any overwrite-data option to perform that assignment.
No production schema/data migration or role assignment is run at startup.
