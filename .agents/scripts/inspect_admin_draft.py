"""Extract a paged API draft and render its opening page for inspection."""
from pathlib import Path

import fitz


source = Path("attached_assets/GoFixCarz_Admin_APIs_draft.docx_1791801665639.pdf")
with fitz.open(source) as document:
    sections = []
    print(f"Pages: {len(document)}")
    for index, page in enumerate(document):
        text = page.get_text()
        sections.append(f"\n=== PAGE {index + 1} ===\n{text}")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        print(f"{index + 1}: {' | '.join(lines[:4])}")
    Path("/tmp/admin-draft.txt").write_text("".join(sections))
    document[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save("/tmp/admin-draft-page-1.png")
