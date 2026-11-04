"""Refresh only the garage-list handoff from live OpenAPI, preserving private auth docs.

Run from the API directory: python scripts/export_admin_garage_contract.py
Other handoff operations are deliberately left unchanged.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app

DOCS = Path(__file__).resolve().parents[1] / "docs"
PATH = "/api/v1/admin/garages"


def main():
    schema = app.openapi()
    operation = schema["paths"][PATH]["get"]
    target = DOCS / "GoFixCarz_Admin_API_OpenAPI.json"
    handoff = json.loads(target.read_text())
    saved = handoff["paths"][PATH]["get"]
    # Keep the handoff's AdminBearerAuth security scheme and private setup policy.
    saved["parameters"] = operation["parameters"]
    saved["responses"] = operation["responses"]
    schemas = handoff["components"]["schemas"]
    visited = set()

    def copy_references(value):
        if isinstance(value, dict):
            if ref := value.get("$ref"):
                prefix = "#/components/schemas/"
                if not ref.startswith(prefix):
                    raise ValueError(f"Unexpected schema reference: {ref}")
                name = ref[len(prefix):]
                if name not in visited:
                    visited.add(name)
                    schemas[name] = schema["components"]["schemas"][name]
                    copy_references(schemas[name])
            for item in value.values():
                copy_references(item)
        elif isinstance(value, list):
            for item in value:
                copy_references(item)

    copy_references(saved["parameters"])
    copy_references(saved["responses"])
    target.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + "\n")

    target = DOCS / "GoFixCarz_Admin_APIs.postman_collection.json"
    collection = json.loads(target.read_text())

    def update_requests(items):
        for item in items:
            update_requests(item.get("item", []))
            request = item.get("request", {})
            url = request.get("url", {})
            if (request.get("method") == "GET" and isinstance(url, dict)
                    and url.get("raw", "").split("?")[0] == "{{base_url}}/admin/garages"):
                query = url.setdefault("query", [])
                if not any(p["key"] == "location_issue" for p in query):
                    query.append({
                        "key": "location_issue", "value": "true", "disabled": True,
                        "description": "Optional: true for missing/invalid pins, false for valid pairs. "
                                       "Combine with operational_status=ACTIVE for active garages.",
                    })

    update_requests(collection["item"])
    target.write_text(json.dumps(collection, indent=2, ensure_ascii=False) + "\n")
    print(f"Refreshed garage-list operation and {len(visited)} referenced schemas.")


if __name__ == "__main__":
    main()
