# Custom-domain HTTPS verification

Checked on 2026-10-23 at approximately 06:35–06:37 UTC.

## Result

`https://api.gofixcarz.com` is reachable with normal certificate verification.
The previously reported unexpected EOF during the TLS handshake was not
reproducible. No DNS, database, application, domain-binding, or deployment
changes were made during this investigation.

Replit deployment metadata reported a successful public autoscale deployment,
with the custom domain as the primary URL and
`https://api-gofixcarz.replit.app` as an additional URL.

## TLS evidence

Direct Python SSL connections to `api.gofixcarz.com` at `34.111.179.208`
succeeded with both TLS 1.2 and TLS 1.3, using the default trusted CA store
and hostname verification. Curl also reported certificate verification result
`0`. No verification bypass was used.

- Subject alternative name: `api.gofixcarz.com`
- Issuer: Let's Encrypt, YE2
- Valid from: 2026-10-21 13:18:24 UTC
- Valid until: 2027-01-19 13:18:23 UTC

These results demonstrate that certificate provisioning and TLS termination
are currently working for the custom hostname. They do not establish what
caused the earlier failure or when it recovered. No historical
domain-verification, certificate-provisioning, or edge-proxy event history was
available through the tools used here, so attribution among those causes
remains unconfirmed.

## Exact endpoint checks

All requests below used GET over HTTPS to `api.gofixcarz.com`, without
authentication or certificate-verification exceptions.

| Path | HTTP status | Observation |
| --- | --- | --- |
| `/health` | 200 | `{"status":"ok"}` |
| `/api/health` | 200 | Healthy; database connected |
| `/api/healthz` | 200 | Healthy; database connected |
| `/api/version` | 200 | API version response |
| `/api/docs` | 200 | Swagger UI HTML |
| `/api/v1/customers` | 401 | JSON: authentication required |
| `/__tls_probe_missing__` | 404 | JSON: not found |

The 401 and 404 are HTTP/application responses after successful TLS, not
certificate or edge handshake failures. No authenticated customer data was
accessed or changed.

An external web fetch of `https://api.gofixcarz.com/api/health` independently
returned the healthy JSON response. The external screenshot of `/health`
was blank and was not used as proof of API health.

The generated Replit hostname also returned 200 from `/health`, but its
workspace resolution used a private proxy address. That check alone would
not establish public custom-domain TLS health.

## If the failure recurs

Capture the UTC time, exact hostname/path, resolved address, and the TLS
error before changing anything. Compare custom-domain TLS with the generated
hostname, and inspect the domain verification and certificate status in
Replit Publishing. A handshake error before any HTTP response must be
investigated separately from an API 401, 404, or 500.

Do not unlink the domain, edit DNS, change database settings, or republish as
a speculative fix. Those actions were neither necessary nor performed here.
