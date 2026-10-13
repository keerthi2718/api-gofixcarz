# Platform admin APIs

Base path: `/api/v1/admin`. Swagger documentation: `/api/docs`.

## Login and authorization

Dedicated administrators have a separate `admin_accounts` table. They authenticate
with email and password through a private authentication contract, intentionally
excluded from public OpenAPI and this shared document. Do not distribute its
sign-in URL or any passwords in API handoffs. This is documentation privacy,
not a substitute for authentication or authorization.

Successful login returns `data.access_token`, a rotating `data.refresh_token`,
`expires_in=900`, `token_type=bearer`, and safe admin identity fields. Send
`Authorization: Bearer <access_token>` on subsequent admin requests. Call `/me`
and then `/menus` before showing privileged navigation. Failed/expired sessions
must clear client navigation and require authentication again. There is no
dashboard frontend in this API artifact; these are backend integration contracts.

Dedicated JWTs require the configured signing algorithm, issuer, audience,
expiry, token purpose, and a live session. Passwords are salted scrypt hashes;
only refresh-token hashes are persisted. Access tokens expire after 15 minutes;
refresh sessions expire after seven days. Refresh rotation immediately revokes
the old session, including its access token. Logout also revokes access and refresh.
Password credential-version changes and account deactivation invalidate sessions.

Login is limited to five requests per minute per IP. Five failed passwords lock
an account for 15 minutes, with counters persisted in PostgreSQL. Auth responses
are marked `Cache-Control: no-store`; unknown, disabled, locked, and wrong-password
accounts receive the same generic login error. Never log credentials or tokens.

Previously explicitly promoted OTP administrators retain their existing owner
authentication contract; public signup still cannot grant admin privileges.

An admin does not need to own a garage. Tokens include a signed `role` claim,
but the database role is checked on every request. An old token cannot retain
admin permissions after demotion. Inactive/deleted accounts are denied.
Missing/invalid JWTs return 401; authenticated non-admin accounts return 403.

## Endpoints

| Method | Path | Inputs / behavior |
|---|---|---|
| GET | `/me` | Current admin identity |
| GET | `/menus` | Authorized Dashboard, Users, Garages, Jobs, Bookings, Analytics, Billing issues, Audit logs menu entries |
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

Successful admin reads, status changes, and dedicated login/session events are
recorded in the audit table. Legacy actors use `actor_id`; dedicated identities
use `admin_account_id`. Exactly one actor reference is required per entry.
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

No account is auto-created on startup or promoted by signup. Dedicated admins
do not need a mobile number, garage, owner registration, or an OTP/SMS.

A trusted operator can explicitly create a separate **development-only** account:

```sh
python scripts/bootstrap_dev_admin.py --email <admin-email>
python scripts/bootstrap_dev_admin.py --email <admin-email> --apply
```

Set `ADMIN_BOOTSTRAP_PASSWORD` through the workspace's secure secret flow first,
using a unique password of 16–128 characters. Never pass a password as a command
argument, print it, put it in this document, or save it in source files. The
script consumes the value only inside runtime and writes a password hash. It
refuses non-internal-development targets and will not overwrite existing credentials.
Nothing automatically provisions production.

An alternative operator-only first-admin setup API is documented separately in
`admin-first-signup.private.md`. It is disabled by default and requires a private
setup key and an empty dedicated admin account store. Admin MFA is optional and
off by default; set `ADMIN_MFA_REQUIRED=true` to require authenticator enrollment.
Keep that private setup contract out of public OpenAPI and shared API catalogues.

For legacy OTP admins, a trusted operator must select an existing, active user.

For **development only**, from `artifacts/api-server`:

```sh
python scripts/grant_dev_admin.py --user-id <UUID>
python scripts/grant_dev_admin.py --user-id <UUID> --apply
```

The first command previews access; the second grants it and records a bootstrap
audit entry. This tool refuses non-internal-development database targets.
Sign in again for a token whose displayed role is `admin`.

For Replit-managed production, publish the development schema changes through
the normal Publishing flow. Development credentials and assignments do **not**
provision a production admin. A trusted production operator must separately
provision a dedicated account using a reviewed secure process after schema
rollout; development bootstrap scripts deliberately cannot write to production.
For legacy OTP accounts only, the operator separately assigns the chosen user's
admin role. Never overwrite production data with development data.
No production schema/data migration or role assignment is run at startup.
