"""Fail closed before serving production traffic if delivery schema is missing."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    # Imports inside the guard keep connection/configuration errors redacted too.
    try:
        from app.core.config import settings
        from app.database.delivery_migrations import ensure_delivery_schema

        approval = os.environ.get("APPLY_DELIVERY_MIGRATIONS", "0")
        if approval not in ("0", "1"):
            raise RuntimeError("Invalid migration approval flag")
        ensure_delivery_schema(settings.DATABASE_URL, allow_upgrade=approval == "1")
    except Exception:
        # No exception text: drivers can embed credentials/URLs in errors.
        print(
            "Production schema check failed. Review publishing schema changes "
            "and database connectivity; API was not started. "
            "See docs/msg91-delivery-tracking.md.",
            file=sys.stderr,
        )
        return 1
    os.execvp("uvicorn", [
        "uvicorn", "app.main:app", "--host", "0.0.0.0",
        "--port", os.environ.get("PORT", "8080"),
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())