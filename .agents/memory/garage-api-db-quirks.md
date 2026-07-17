---
name: Garage API — asyncpg & Alembic DB quirks
description: Known incompatibilities between asyncpg, Alembic, and Replit's internal Postgres that bit us during initial setup.
---

# Garage API — asyncpg & Alembic DB quirks

## Rule 1: Strip `sslmode` from the URL for asyncpg

asyncpg does not accept `sslmode` as a query parameter in the connection URL. It raises `TypeError: connect() got an unexpected keyword argument 'sslmode'`.

**Fix:** Parse the URL with `urlparse`, pop `sslmode` from the query params, then pass `ssl=<ctx>` via `connect_args` only when the host is remote (not `localhost` / `helium`).

**Why:** Replit's `DATABASE_URL` contains `?sslmode=require` but the internal Postgres host (`helium`) does not actually use SSL.

**How to apply:** See `app/database/session.py::_build_async_url()`.

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

## Rule 4: Replit Postgres (helium) has no SSL

The internal Replit Postgres host resolves to `helium` (172.24.0.3:5432) and does not support SSL. Passing `sslmode=require` (or `connect_args={"sslmode": "require"}`) causes a hard connection failure.

**Fix:** Strip `sslmode` from the connection string. For psycopg2 (Alembic), don't pass `sslmode` in `connect_args` at all — psycopg2 defaults to `prefer` which gracefully falls back to no-SSL.

**How to apply:** `alembic/env.py::_build_sync_url()` strips `sslmode` from the URL before creating the engine.
