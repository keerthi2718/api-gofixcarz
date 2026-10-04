---
name: Garage API — asyncpg & Alembic DB quirks
description: Known incompatibilities between asyncpg, Alembic, and Replit's internal Postgres that bit us during initial setup.
---

# Garage API — asyncpg & Alembic DB quirks

## Rule 1: Preserve the requested remote SSL policy across drivers

Do not treat `require`, `verify-ca`, and `verify-full` as interchangeable, or
extend the internal non-SSL exception to localhost or arbitrary remote hosts.
An omitted mode retains driver defaults; changing deployment SSL settings is
not authorized by a URL-conversion fix.

**Why:** The internal non-SSL workaround previously weakened remote certificate
verification. `require` is an encryption policy, not a guarantee of hostname
verification; callers requesting verification must receive it.

**How to apply:** Keep runtime connections, migrations, and startup schema checks
consistent when adapting database URLs. Use dummy URLs to check this without
reading credentials or contacting production.

---

## Rule 2: Alembic uses psycopg2 (sync), not asyncpg

Alembic's `env.py` was switched from `async_engine_from_config` to a standard sync `create_engine` with psycopg2. Reason: asyncpg treats `$` as a parameter placeholder, making `DO $$...$$` PL/pgSQL blocks fail with a syntax error.

**Fix:** `alembic/env.py` uses `create_engine(_sync_url, poolclass=pool.NullPool)` — no async, no asyncpg.

**Why:** Alembic is inherently synchronous at the migration-runner level. Using asyncpg adds complexity (and the $$ bug) without any benefit.

**How to apply:** Do not convert `alembic/env.py` back to async. Keep psycopg2-binary in `requirements.txt`.

---

## Rule 3: SA Enum auto-creates the PG type in `create_table`

When you use `sa.Enum("A","B", name="my_type")` inside `op.create_table(...)`, SQLAlchemy automatically emits `CREATE TYPE my_type AS ENUM (...)` before the `CREATE TABLE`. Manually creating the same type before calling `create_table` causes a `DuplicateObjectError`.

**Fix:** Declare the enum once as a variable (`booking_status = sa.Enum(...)`) and pass it into `op.create_table`. Do NOT call `op.execute("CREATE TYPE ...")` separately.

**How to apply:** See `alembic/versions/0001_initial_schema.py` for the pattern.

---

## Rule 4: Internal helium does not support SSL

Only the exact internal `helium` host has a standing non-SSL exception.

**Why:** The injected internal database URL may request SSL even though this
service does not support it. That mismatch must not prevent development startup.

**How to apply:** Restrict the exception to the effective internal host, including
all repeated or comma-separated host overrides. A `hostaddr` may determine the
actual destination while `host` is only a verification name, and service files
can supply addresses not established as internal. Preserve SSL for these
ambiguous cases. Never infer that a remote database is non-SSL because its URL
otherwise resembles the internal URL.
