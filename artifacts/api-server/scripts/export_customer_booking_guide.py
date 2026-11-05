"""Export the maintained frontend guide as a self-contained downloadable HTML file."""
from html import escape
from pathlib import Path
import re


def inline(text):
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", escape(text))
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)


def main():
    docs = Path(__file__).resolve().parents[1] / "docs"
    blocks = []
    lines = []
    fenced = False
    table = False

    def flush():
        nonlocal lines, table
        if lines:
            text = "\n".join(lines)
            blocks.append(("<pre>" + escape(text) + "</pre>") if table else
                          ("<p>" + inline(text) + "</p>"))
        lines, table = [], False

    for line in (docs / "customer-garage-discovery.md").read_text().splitlines():
        if line.startswith("```"):
            if fenced:
                blocks.append("<pre>" + escape("\n".join(lines)) + "</pre>")
                lines = []
            else:
                flush()
            fenced = not fenced
        elif fenced:
            lines.append(line)
        elif not line.strip():
            flush()
        elif line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            blocks.append(f"<h{level}>" + inline(line[level:].strip()) + f"</h{level}>")
        elif line.startswith("|"):
            if not table:
                flush()
            table = True
            lines.append(line)
        elif line.startswith("- "):
            flush()
            blocks.append("<p class='item'>" + inline(line) + "</p>")
        else:
            lines.append(line)
    flush()
    output = docs / "customer-booking-frontend-guide.html"
    output.write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Customer discovery and booking API guide</title><style>"
        "body{font:16px/1.6 system-ui,sans-serif;color:#17263a;max-width:1050px;margin:auto;padding:30px}"
        "h1,h2,h3{line-height:1.3}h2{margin-top:40px;border-bottom:1px solid #ddd;padding-bottom:10px}"
        "pre{background:#f3f5f8;padding:18px;overflow:auto;border-radius:6px;font-size:13px}"
        "code{background:#f3f5f8;padding:2px 4px;font-size:14px}p{white-space:pre-line}"
        ".item{margin:8px 0}@media print{body{padding:0}pre{white-space:pre-wrap}}"
        "</style><body>" + "\n".join(blocks) + "</body></html>"
    )
    print(f"Exported {output.name}")


if __name__ == "__main__":
    main()
