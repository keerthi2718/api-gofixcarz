---
name: Production migration approval
description: Why automatic delivery migration startup is bounded and opt-in.
---

For Replit-managed production databases, Publish owns schema changes. Do not
run startup migrations; check the actual required schema read-only.

**Why:** Publish synchronizes table structure but does not necessarily update
Alembic's revision row. A strict revision guard rejected a production database
that already had the delivery table and index.

**How to apply:** Validate required structure rather than treating stale
`alembic_version` as proof that managed production is missing migrations.
Never stamp a revision to bypass this distinction.

For external production databases, publishing must not silently authorize all pending migrations.
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