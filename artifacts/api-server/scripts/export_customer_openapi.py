"""Sync implemented FastAPI customer contracts into the workspace API clients.

Run from artifacts/api-server, then run the workspace's API code generator.
The draft inventory is not used here: only implemented operations are exported.
"""
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402


def main():
    target = Path(__file__).resolve().parents[3] / "lib/api-spec/openapi.yaml"
    existing = yaml.safe_load(target.read_text())
    runtime = app.openapi()
    prefix = "/api/v1/customer-app"
    paths = {path.removeprefix("/api"): operations for path, operations in runtime["paths"].items()
             if path.startswith(prefix)}
    # This owner action completes the customer booking contract. Keep its
    # request/response schemas available to both client integrations.
    schedule_path = "/api/v1/bookings/{booking_id}/schedule"
    paths[schedule_path.removeprefix("/api")] = runtime["paths"][schedule_path]
    for path in list(existing["paths"]):
        if path.startswith("/v1/customer-app"):
            del existing["paths"][path]
    existing["paths"].update(paths)
    required = set()

    def references(value):
        if isinstance(value, dict):
            ref = value.get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                required.add(ref.rsplit("/", 1)[1])
            for nested in value.values():
                references(nested)
        elif isinstance(value, list):
            for nested in value:
                references(nested)

    references(paths)
    pending = set(required)
    processed = set()
    while pending:
        name = pending.pop()
        references(runtime["components"]["schemas"][name])
        existing["components"]["schemas"][name] = runtime["components"]["schemas"][name]
        processed.add(name)
        pending = required - processed
    existing["components"].setdefault("securitySchemes", {}).update(
        runtime["components"].get("securitySchemes", {}))
    if not any(tag["name"] == "Customer App" for tag in existing.get("tags", [])):
        existing.setdefault("tags", []).append({
            "name": "Customer App", "description": "Mobile OTP customer authentication and profile APIs.",
        })
    target.write_text(yaml.safe_dump(existing, sort_keys=False, allow_unicode=True))
    print(f"Exported {sum(len(ops) for ops in paths.values())} customer operations.")


if __name__ == "__main__":
    main()
