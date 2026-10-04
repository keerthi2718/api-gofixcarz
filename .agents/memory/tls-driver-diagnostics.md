---
name: TLS driver diagnostics
description: Why libpq and Python TLS errors can differ for the same generated revocation material.
---

Do not assume psycopg2/libpq and Python's ssl module expose the same OpenSSL diagnostics, even in the same process.

**Why:** In this environment, psycopg2 uses a bundled libpq/OpenSSL stack while asyncpg uses Python's ssl stack. An incorrectly signed RSA CRL produced a lower-level padding error through libpq, but a structured CRL-signature verification error through Python. Fresh unrelated RSA keys can also fail the modulus check before padding verification.

**How to apply:** Require handshake rejection in both drivers, use structured verification codes where exposed, and constrain libpq assertions to relevant TLS errors rather than assuming Python's message. Keep valid-material controls so unrelated connectivity failures cannot masquerade as successful policy checks.