---
name: Production migration approval
description: Why automatic delivery migration startup is bounded and opt-in.
---

Production publishing must not silently authorize all pending migrations.
Delivery-only startup migration approval is intentionally bounded, with a
read-only check by default. When adding later migrations, review and update
the publishing policy rather than broadening approval to all migrations.

**Why:** The delivery diagnostics work required publishing readiness without
permission to mutate production data. Applying every pending migration could
also run older, unrelated data transformations. Missing schema should block a
new deployment rather than allow broken diagnostics to serve users.

**How to apply:** Separate approval to publish from approval to migrate the
intended production database. Preserve the approved baseline and migration
scope, and coordinate concurrent starters. Never treat a missing schema as
permission to stamp a revision or apply unrelated upgrades.