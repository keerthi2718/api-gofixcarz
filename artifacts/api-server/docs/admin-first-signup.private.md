# Private first-admin signup

For the trusted platform operator only. Do not publish this guide, put it in
the public API catalogue, or distribute filled-in passwords or setup keys.

This creates the first dedicated platform administrator. It does not create a
garage, send SMS, promote a garage owner, overwrite credentials, or log in the
new account. Additional staff must use the existing authenticated staff controls.

## Enable deliberately

1. Configure a unique random `ADMIN_SETUP_KEY` of 32–256 characters through the
   secure Secrets flow. This is a setup authorization key, **not** the new
   administrator's password. Never send the real key or password in chat.
2. Set `ADMIN_SIGNUP_ENABLED=true` only in the environment you intend to initialize.
   Both settings are needed; missing/short setup keys keep the route disabled.
3. Restart development to use development settings, or republish to apply
   production settings. For Replit-managed production PostgreSQL, review the
   schema additions in Publish and preserve production data. Do not select
   overwrite data or run the development bootstrap script against production.
4. Send the HTTPS request below from a trusted operator device. Use Postman
   local/Vault secrets for the key and password; do not export their values.
5. After successful creation, set `ADMIN_SIGNUP_ENABLED=false` and remove the
   setup key, then restart/republish the relevant environment.

Any existing dedicated admin account, including an inactive account, closes
this endpoint. It cannot reset an existing administrator's password. A
transaction-scoped PostgreSQL table lock serializes the emptiness check and
creation across workers and other admin insertion paths. The account and audit
event commit together before a successful response is returned.

## Request

`POST /api/v1/admin-auth/sign-up`

Production request URL after republishing:
`https://api.gofixcarz.com/api/v1/admin-auth/sign-up`

Headers:

```text
Content-Type: application/json
X-Admin-Setup-Key: {{admin_setup_key}}
```

JSON body (substitute private local variables, not literal placeholder values):

```json
{
  "email": "{{admin_email}}",
  "name": "Platform administrator",
  "password": "{{admin_password}}"
}
```

Email is normalized to lowercase, name is trimmed and must be 1–255 characters,
and password must be 16–128 characters. Password whitespace is preserved.
Extra fields such as `role_ids`, `garage_scope`, `is_active`, or `mfa_required`
are rejected. The operator cannot choose weaker authorization through the body.

## Success — HTTP 201

All successful and expected setup-error responses include `Cache-Control: no-store`.

```json
{
  "success": true,
  "message": "Admin account created. Sign in to complete MFA.",
  "data": {
    "id": "11111111-1111-4111-8111-111111111111",
    "email": "admin@example.com",
    "name": "Platform administrator",
    "role": "admin",
    "is_active": true,
    "role_ids": ["role_ceo"],
    "mfa_required": true,
    "next_step": "SIGN_IN_AND_COMPLETE_MFA"
  },
  "errors": [],
  "status_code": 201
}
```

The created identity has platform-wide scope and the initial CEO permission
role. Only a salted password hash is stored. Neither password, setup key,
password hash, access token, nor refresh token is returned.

## Sign in after signup

Use the chosen email and password with the existing private
`POST /api/v1/admin-auth/sign-in` endpoint. It returns an MFA challenge rather
than usable tokens. Enroll the returned `provisioning_uri` in an authenticator
app and submit its current six-digit code and the returned `challenge_id` to
`POST /api/v1/admin-auth/mfa`. Only completing MFA issues the admin session.

Keep the provisioning URI private too. Signup does not disable or bypass MFA.

## Errors

| HTTP status | Meaning |
| --- | --- |
| 404 | Setup disabled, or configured setup key missing/invalid length. |
| 403 | Setup key header missing, wrong, or invalid length. |
| 409 | A dedicated admin already exists; signup remains closed even if inactive. |
| 422 | Invalid email/name/password or unexpected request fields. |
| 429 | Rate limited: at most five signup attempts per minute per client IP. |
| 503 | Setup lock/database unavailable; retry after checking server readiness. |

Example when an account already exists:

```json
{
  "success": false,
  "message": "An admin account already exists. First-admin signup is closed.",
  "data": null,
  "errors": [],
  "status_code": 409
}
```

The setup route is intentionally excluded from public OpenAPI/Swagger. Its
privacy is not a security boundary: the setup key, opt-in flag, database guard,
password hashing, and MFA remain mandatory.
