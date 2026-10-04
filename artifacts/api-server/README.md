# Garage Management API

A production-ready REST API for managing a car garage — built with **FastAPI**, **SQLAlchemy 2 async**, and **PostgreSQL**. Designed to be consumed by a mobile client.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Variables](#environment-variables)
3. [Local Setup](#local-setup)
4. [Running the Server](#running-the-server)
5. [Database Migrations](#database-migrations)
6. [Seed Data](#seed-data)
7. [Running Tests](#running-tests)
8. [Connecting with DBeaver / pgAdmin](#connecting-with-dbeaver--pgadmin)
9. [Postman Collection](#postman-collection)
10. [Backup & Restore](#backup--restore)
11. [API Overview](#api-overview)
12. [Project Structure](#project-structure)
13. [Deployment Notes](#deployment-notes)

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| PostgreSQL | 14+ |
| pip | latest |

Optional for Docker:

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Docker Compose | 2.x |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | — (required) |
| `SESSION_SECRET` | JWT signing key (use a 32-byte random hex) | — (required) |
| `MSG91_AUTH_KEY` | MSG91 API key for OTP SMS | — (optional in dev) |
| `ENVIRONMENT` | `development` or `production` | `development` |
| `DEBUG` | Enable SQLAlchemy echo | `false` |
| `OTP_EXPIRY_SECONDS` | OTP validity window | `300` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON array) | `["*"]` |

### Database TLS policy

The API, Alembic migrations, and production schema preflight preserve the
`DATABASE_URL` SSL policy. `verify-full` verifies both the certificate chain and
database hostname; `verify-ca` verifies the chain only. `require` requires
encryption but does not guarantee server identity verification. Use
`verify-full` and your provider's `sslrootcert` for verified remote connections.
Certificate/key options are forwarded to the database drivers; an unusable
certificate configuration fails rather than being downgraded.

Explicit `disable`, `allow`, and `prefer` modes retain their driver semantics.
When no mode is supplied, driver defaults apply. Only the exact internal
`helium` host overrides the requested mode to disable TLS because that service
does not support it. Localhost and remote hosts do not receive that exception.
This URL conversion does not change any deployment environment settings.

Generate a strong secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Local Setup

```bash
# Clone the repo and enter the project directory
git clone <repo>
cd artifacts/api-server

# Create a virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure env
cp .env.example .env
# Edit .env — set DATABASE_URL and SESSION_SECRET at minimum
```

---

## Running the Server

### Uvicorn (development)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
ReDoc: [http://localhost:8000/api/redoc](http://localhost:8000/api/redoc)

### Docker Compose (full stack)

```bash
docker compose up --build
```

This starts:
- `api` — FastAPI app on port 8000
- `db` — PostgreSQL on port 5432

### Docker only (bring your own DB)

```bash
docker build -t garage-api .
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/garage_db" \
  -e SESSION_SECRET="your-secret" \
  garage-api
```

---

## Database Migrations

Migrations are managed by **Alembic** using a synchronous psycopg2 connection (asyncpg doesn't support `$$` dollar-quoted PL/pgSQL blocks in migration scripts).

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration (after changing models)
alembic revision --autogenerate -m "your description"

# Roll back one step
alembic downgrade -1

# View current revision
alembic current

# View migration history
alembic history
```

> **Note**: On Replit, `DATABASE_URL` is injected automatically. Alembic reads `alembic/env.py` which converts the URL to a synchronous `psycopg2` connection.

---

## Seed Data

The seed script populates representative data — 1 garage, 5 customers, 10 vehicles, 20 jobs (all statuses), 5 bookings, 5 service packages, and 10 notifications:

```bash
python -m app.utils.seed
```

The script is **idempotent** — re-running it skips records that already exist. After seeding:

- **Mobile**: `9000000000`
- **Sign in**: `POST /api/v1/auth/sign-in` with the mobile above, then `POST /api/v1/auth/verify-otp` to get a JWT.

---

## Running Tests

```bash
# Unit tests only (fast, no DB)
pytest tests/unit/ -v

# Integration tests (requires running server + DB)
pytest tests/integration/ -v

# All tests
pytest -v

# With coverage report
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

Unit tests cover:
- OTP generation and expiry (`tests/unit/test_otp.py`)
- Job status transition state machine (`tests/unit/test_job_status.py`)
- Analytics date bucketing logic (`tests/unit/test_analytics.py`)

Integration tests cover the full auth flow and job/customer/vehicle CRUD against the live database.

---

## Connecting with DBeaver / pgAdmin

1. Parse `DATABASE_URL` — format: `postgresql://USER:PASSWORD@HOST:PORT/DBNAME`
2. In DBeaver: **New Connection → PostgreSQL**
   - Host: `HOST` from the URL
   - Port: `PORT` (usually `5432`)
   - Database: `DBNAME`
   - Username: `USER`
   - Password: `PASSWORD`
3. On Replit, the internal host is `helium` and SSL is not used — uncheck "Use SSL".

> On Replit, the `DATABASE_URL` is available as an environment variable at runtime. You can print it (never commit it) with `echo $DATABASE_URL`.

---

## Postman Collection

Two files are provided:

| File | Purpose |
|------|---------|
| `Garage_API.postman_collection.json` | All endpoints with sample bodies and test scripts |
| `Garage.postman_environment.json` | Environment variables (`base_url`, `access_token`, etc.) |

### Import steps

1. Open Postman → **Import** → drag both JSON files.
2. Select the **Garage Management — Local** environment in the top-right dropdown.
3. Run **Sign Up** → **Verify OTP** — the test script auto-saves the JWT to `{{access_token}}`.
4. All other requests use `{{access_token}}` via collection-level Bearer auth.

### Workflow

```
Sign Up → Verify OTP ← JWT saved automatically
           ↓
       Dashboard / Jobs / Customers / Vehicles / Bookings / Analytics
```

---

## Backup & Restore

Scripts require `pg_dump` and `psql` in your PATH (they come with PostgreSQL client tools).

### Backup

```bash
bash scripts/backup_db.sh
# Creates: backups/backup_YYYYMMDD_HHMMSS.sql
```

### Restore

```bash
bash scripts/restore_db.sh backups/backup_20260717_120000.sql
```

The scripts parse `DATABASE_URL` automatically.

---

## API Overview

All responses use the envelope format:

```json
{
  "success": true,
  "message": "...",
  "data": { ... },
  "errors": [],
  "status_code": 200
}
```

Paginated endpoints return:

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "pages": 3
}
```

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/health` | — | Health check (DB ping) |
| GET | `/api/version` | — | App name and version |
| **Auth** | | | |
| POST | `/api/v1/auth/sign-up` | — | Register new user |
| POST | `/api/v1/auth/sign-in` | — | Request OTP for existing user |
| POST | `/api/v1/auth/send-otp` | — | Resend OTP |
| POST | `/api/v1/auth/verify-otp` | — | Verify OTP → JWT |
| POST | `/api/v1/auth/logout` | ✓ | Invalidate session |
| **Dashboard** | | | |
| GET | `/api/v1/dashboard` | ✓ | KPIs + recent activity |
| **Analytics** | | | |
| GET | `/api/v1/analytics` | ✓ | Revenue + job counts (`period`, `start_date`, `end_date`) |
| **Profile** | | | |
| GET | `/api/v1/profile` | ✓ | Get current user profile |
| PUT | `/api/v1/profile` | ✓ | Update name / email / mobile |
| **Garage** | | | |
| GET | `/api/v1/garage` | ✓ | Get garage info |
| PUT | `/api/v1/garage` | ✓ | Update name, address, working hours, lat/lng |
| **Customers** | | | |
| POST | `/api/v1/customers` | ✓ | Create customer |
| GET | `/api/v1/customers` | ✓ | List customers (paginated, searchable) |
| GET | `/api/v1/customers/{id}` | ✓ | Get customer |
| PUT | `/api/v1/customers/{id}` | ✓ | Update customer |
| DELETE | `/api/v1/customers/{id}` | ✓ | Soft-delete customer |
| **Vehicles** | | | |
| POST | `/api/v1/vehicles` | ✓ | Create vehicle |
| GET | `/api/v1/vehicles` | ✓ | List vehicles (paginated, filterable by customer) |
| GET | `/api/v1/vehicles/{id}` | ✓ | Get vehicle with job history |
| PUT | `/api/v1/vehicles/{id}` | ✓ | Update vehicle |
| DELETE | `/api/v1/vehicles/{id}` | ✓ | Soft-delete vehicle |
| **Jobs** | | | |
| POST | `/api/v1/jobs` | ✓ | Create job (auto `JOB-YYYYMMDD-NNNN` number) |
| GET | `/api/v1/jobs` | ✓ | List jobs (paginated, filter by status/date, search) |
| GET | `/api/v1/jobs/{id}` | ✓ | Get job with full timeline |
| PUT | `/api/v1/jobs/{id}` | ✓ | Update job details |
| PATCH | `/api/v1/jobs/{id}/status` | ✓ | Advance job status |
| PATCH | `/api/v1/jobs/{id}/complete` | ✓ | Mark complete + set final amount |
| DELETE | `/api/v1/jobs/{id}` | ✓ | Soft-delete job |
| **Bookings** | | | |
| GET | `/api/v1/bookings` | ✓ | List bookings (paginated, filterable by status) |
| GET | `/api/v1/bookings/{id}` | ✓ | Get booking detail |
| PATCH | `/api/v1/bookings/{id}/accept` | ✓ | Accept pending booking |
| PATCH | `/api/v1/bookings/{id}/reject` | ✓ | Reject booking |
| POST | `/api/v1/bookings/{id}/create-job` | ✓ | Convert booking → job atomically |
| **Service Packages** | | | |
| POST | `/api/v1/service-packages` | ✓ | Create package |
| GET | `/api/v1/service-packages` | ✓ | List packages (searchable, active filter) |
| GET | `/api/v1/service-packages/{id}` | ✓ | Get package |
| PUT | `/api/v1/service-packages/{id}` | ✓ | Update package |
| DELETE | `/api/v1/service-packages/{id}` | ✓ | Soft-delete package |
| **Notifications** | | | |
| GET | `/api/v1/notifications` | ✓ | List notifications (unread first) |
| PATCH | `/api/v1/notifications/{id}/read` | ✓ | Mark notification as read |
| **Static** | | | |
| GET | `/api/v1/static/privacy-policy` | — | Privacy policy text |
| GET | `/api/v1/static/help-support` | — | Help & support text |

### Job Status Machine

```
OPEN → IN_PROGRESS → WAITING_FOR_PARTS → IN_PROGRESS
                   → QUALITY_CHECK → IN_PROGRESS
                                   → COMPLETED (terminal)
     → CANCELLED (terminal, from any non-terminal state)
```

---

## Project Structure

```
artifacts/api-server/
├── app/
│   ├── api/v1/            # Route handlers
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── analytics.py
│   │   ├── profile.py
│   │   ├── garage.py
│   │   ├── customers.py
│   │   ├── vehicles.py
│   │   ├── jobs.py
│   │   ├── bookings.py
│   │   ├── service_packages.py
│   │   ├── notifications.py
│   │   └── static.py
│   ├── core/              # Config, logging, security, exceptions
│   ├── database/          # Engine, session factory
│   ├── dependencies/      # FastAPI deps (auth, garage scope)
│   ├── middleware/        # Request ID logging
│   ├── models/            # SQLAlchemy ORM models
│   ├── repositories/      # DB query layer
│   ├── schemas/           # Pydantic request/response models
│   ├── services/          # Business logic
│   └── utils/             # MSG91 helper, seed script
├── alembic/               # Database migrations
├── scripts/               # backup_db.sh, restore_db.sh
├── tests/
│   ├── unit/              # Fast, no-DB tests
│   └── integration/       # Live-server tests
├── Garage_API.postman_collection.json
├── Garage.postman_environment.json
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Deployment Notes

### Replit

- Publishing installs Python dependencies in the API artifact's
  `services.production.build`, using
  `python artifacts/api-server/scripts/production_build.py` from the repository
  root. There is no root `.replit` pre-build installer, so dependencies are
  installed once by the artifact that owns them.
- The build runs `python -m pip install` against this API's `requirements.txt`
  using the same interpreter that launches the build script. A failed install
  blocks publishing; the build does not connect to the database or run migrations.
- Build logs report the exit code and fixed troubleshooting hints for version
  conflicts, unavailable packages, TLS/network access, and native build failures.
  Raw pip output is deliberately withheld and its temporary log is deleted:
  private index URLs and package build scripts can expose credentials even on
  successful installs. For an unknown failure, reproduce installation in a safe
  local environment without production secrets and inspect the pip output there;
  do not paste raw output into shared logs.
- Run the isolated publishing regression checks from the repository root:
  `python -m unittest discover -s artifacts/api-server/tests/unit -p test_production_build.py -v`.
  These use mocked pip success/failure paths, not real installation or publishing.
- `DATABASE_URL` and `SESSION_SECRET` (aliased from `SESSION_SECRET`) are injected as Replit secrets — no `.env` file needed.
- Development migrations: `alembic upgrade head` against the development database.
- Production startup: `python scripts/production_start.py` checks the delivery
  schema before serving. Missing delivery migrations require explicit approval
  (`APPLY_DELIVERY_MIGRATIONS=1`); older or unknown baselines require separate
  review. See [delivery publishing safety](docs/msg91-delivery-tracking.md#production-publishing-safety).
- The workflow command is: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload`.

### Production checklist

- [ ] Set `ENVIRONMENT=production` and `DEBUG=false`
- [ ] Generate a strong `SESSION_SECRET` (32+ bytes)
- [ ] Set `CORS_ORIGINS` to your specific frontend domain(s)
- [ ] Confirm production database target/backup and review required migrations;
  use the guarded production startup command (see delivery publishing safety)
- [ ] Configure a cron job or scheduled task to run `scripts/backup_db.sh` daily
- [ ] Set `MSG91_AUTH_KEY` for real OTP SMS delivery
