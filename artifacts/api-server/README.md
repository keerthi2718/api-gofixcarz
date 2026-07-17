# Garage Management API

Production-ready FastAPI backend for the Garage Management Mobile Application.

## Tech Stack

- **Python 3.12+** · **FastAPI** · **SQLAlchemy 2.0 async** · **asyncpg**
- **PostgreSQL** · **Alembic** (migrations) · **Pydantic v2**
- **JWT** authentication · **MSG91** SMS OTP · **Loguru** logging
- **Uvicorn** ASGI server · **httpx** HTTP client

---

## Quick Start

### Option 1 — Local (uvicorn)

```bash
# 1. Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL, SESSION_SECRET, MSG91_AUTH_KEY

# 4. Run migrations
python -m alembic upgrade head

# 5. (Optional) seed sample data
python -m app.utils.seed

# 6. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

API available at `http://localhost:8080/api`
Swagger docs at `http://localhost:8080/api/docs`

### Option 2 — Docker Compose

```bash
cp .env.example .env          # edit as needed
docker compose up --build
```

The API will be available at `http://localhost:8000/api`.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string (`postgresql://user:pass@host:port/db`) |
| `SESSION_SECRET` | ✅ | Secret key for JWT signing (generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `MSG91_AUTH_KEY` | ✅ | MSG91 API authentication key |
| `OTP_EXPIRY_SECONDS` | ❌ | OTP validity window in seconds (default: 300) |
| `DEBUG` | ❌ | Enable SQL query logging (default: false) |
| `ENVIRONMENT` | ❌ | `development` or `production` (default: development) |

---

## Running Migrations

```bash
# Apply all pending migrations
python -m alembic upgrade head

# Rollback one migration
python -m alembic downgrade -1

# Show current migration status
python -m alembic current

# Show migration history
python -m alembic history
```

> **Note:** Alembic uses a synchronous psycopg2 connection. The runtime app uses async asyncpg — both work against the same database.

---

## Connecting with DBeaver / pgAdmin

Use the components of your `DATABASE_URL` to connect:

| Field | Value |
|---|---|
| Host | From `DATABASE_URL` (e.g. `localhost` or `helium`) |
| Port | `5432` |
| Database | From `DATABASE_URL` |
| Username | From `DATABASE_URL` |
| Password | From `DATABASE_URL` |
| SSL | Disable for local; Enable for cloud |

In **Replit**, your `DATABASE_URL` is available in the environment. You can find the individual components with:

```bash
python -c "
from urllib.parse import urlparse
import os
u = urlparse(os.environ['DATABASE_URL'])
print(f'Host: {u.hostname}\nPort: {u.port}\nDB: {u.path[1:]}\nUser: {u.username}')
"
```

---

## API Documentation

Interactive Swagger UI: `/api/docs`  
ReDoc: `/api/redoc`  
OpenAPI JSON: `/api/openapi.json`

### Auth Flow

```
POST /api/v1/auth/sign-up   → create account + send OTP
POST /api/v1/auth/sign-in   → send OTP to existing mobile
POST /api/v1/auth/send-otp  → resend OTP
POST /api/v1/auth/verify-otp → verify OTP → receive JWT
POST /api/v1/auth/logout    → (client discards JWT)
```

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

### Response Envelope

All responses follow this structure:

```json
{
  "success": true,
  "message": "Human-readable message",
  "data": { ... },
  "errors": [],
  "status_code": 200
}
```

---

## Importing the Postman Collection

> Generated in Task #3. Once available:

1. Open Postman → Import
2. Select `Garage_API.postman_collection.json`
3. Import `Garage.postman_environment.json` and set it as active
4. Set `base_url` to your API URL (e.g. `https://your-replit-domain.repl.co`)
5. Use **Sign Up** then **Verify OTP** — the JWT is saved automatically to `access_token`

---

## Database Backup & Restore

### Backup

```bash
# Creates backups/backup_YYYYMMDD_HHMMSS.sql
./scripts/backup_db.sh
```

### Restore

```bash
./scripts/restore_db.sh backups/backup_20250101_120000.sql
```

> Both scripts read `DATABASE_URL` from the environment (or `.env`).

---

## Running Tests

```bash
# Install test dependencies (included in requirements.txt)
pytest tests/ -v

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests (requires live DB)
pytest tests/integration/ -v
```

---

## Deployment

The project is fully portable. To deploy on any cloud:

1. Set the environment variables listed above
2. Point `DATABASE_URL` at your PostgreSQL instance
3. Run `python -m alembic upgrade head` once
4. Start with `uvicorn app.main:app --host 0.0.0.0 --port 8080`

Or use Docker:

```bash
docker build -t garage-api .
docker run -e DATABASE_URL=... -e SESSION_SECRET=... -e MSG91_AUTH_KEY=... -p 8080:8000 garage-api
```

---

## Project Structure

```
artifacts/api-server/
├── app/
│   ├── api/v1/          # Route handlers (auth, jobs, customers, …)
│   ├── core/            # Config, security, logging, exceptions
│   ├── database/        # SQLAlchemy engine, session, base models
│   ├── dependencies/    # FastAPI dependency injection (auth, db)
│   ├── middleware/       # Request ID, logging middleware
│   ├── models/          # SQLAlchemy ORM models (9 tables)
│   ├── repositories/    # DB query layer
│   ├── schemas/         # Pydantic v2 request/response schemas
│   ├── services/        # Business logic layer
│   └── utils/           # MSG91 SMS, seed script
├── alembic/             # Database migrations
├── scripts/             # backup_db.sh, restore_db.sh
├── backups/             # SQL dump files (git-ignored)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```
