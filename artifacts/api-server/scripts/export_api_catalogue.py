"""Export a shareable, self-contained API list without private admin auth."""
import html
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "gofixcarz-api-catalogue.html"


def main():
    groups = defaultdict(list)
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            auth = "JWT required" if operation.get("security") else "Public or operation-specific"
            groups[(operation.get("tags") or ["Other"])[0]].append((
                method.upper(), path, operation.get("summary", ""), auth,
            ))
    count = sum(map(len, groups.values()))
    parts = [
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GoFixCarz API catalogue</title><style>'
        'body{font:16px/1.5 system-ui,sans-serif;color:#17263a;max-width:1100px;'
        'margin:auto;padding:32px;background:#f8fafc}h1{margin-bottom:8px}'
        'section{background:white;padding:20px;margin:22px 0;border:1px solid #dce3ec;'
        'border-radius:10px;overflow-x:auto}table{width:100%;border-collapse:collapse}'
        'td,th{padding:10px;text-align:left;border-bottom:1px solid #e8edf3;vertical-align:top}'
        'code{font:13px ui-monospace,monospace}th{color:#476078}p{max-width:850px}'
        '@media print{body{padding:0;background:white}section{break-inside:avoid}}'
        '</style><body><h1>GoFixCarz API catalogue</h1>',
        f'<p>{count} documented operations. Generated from the running application contract.</p>',
        '<p>Protected operations require <code>Authorization: Bearer &lt;access_token&gt;</code>. '
        'Garage-owner resources remain tenant-scoped. Platform-wide access is provided only '
        'by admin endpoints after JWT and account validation. Private administrator authentication '
        'URLs and credentials are deliberately excluded from this catalogue.</p>',
        '<p>Admin integration: authenticate using the private contract, validate identity with '
        '<code>GET /api/v1/admin/me</code>, then fetch '
        '<code>GET /api/v1/admin/menus</code>. Do not show privileged menus when either returns '
        '401 or 403. Admin access tokens last 15 minutes; refresh sessions last seven days. '
        'Billing issue review is read-only and does not repair historical records.</p>',
    ]
    for group, rows in groups.items():
        parts.append(f'<section><h2>{html.escape(group)}</h2><table><thead><tr>'
                     '<th>Method</th><th>Path</th><th>Operation</th><th>Access</th>'
                     '</tr></thead><tbody>')
        for method, path, summary, auth in rows:
            parts.append(f'<tr><td><strong>{method}</strong></td><td><code>{html.escape(path)}</code>'
                         f'</td><td>{html.escape(summary)}</td><td>{auth}</td></tr>')
        parts.append('</tbody></table></section>')
    parts.append('</body></html>')
    OUTPUT.write_text("".join(parts))
    print(f"Exported {count} public/documented operations; private admin authentication excluded.")


if __name__ == "__main__":
    main()
