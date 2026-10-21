"""Combine the existing development contract reference with workbook traceability.

Documentation only: never imports or starts the application or contacts services.
Both deliverables are rendered from the same final Word document content.
"""
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import re
import textwrap
import zipfile
import xml.etree.ElementTree as ET

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.table import Table as WordTable
from docx.text.paragraph import Paragraph as WordParagraph
import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle,
    PageBreak,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated-artifacts"
STEM = OUT / "GoFixCarz_Customer_API_Workbook_Reference"
BASE = "/api/v1/customer-app"
EXCLUDED = {"API-08", "API-09", "API-10", "API-11"}


def workbook():
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    source = ROOT / "attached_assets/GoFixCarz_Customer_App_UI_and_User_Stories_1791365184539.xlsx"
    with zipfile.ZipFile(source) as archive:
        strings = ["".join(t.text or "" for t in item.findall(".//m:t", ns))
                   for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        result = []
        for name in ("sheet1", "sheet2"):
            rows = []
            for row in ET.fromstring(archive.read(f"xl/worksheets/{name}.xml")).findall(".//m:row", ns):
                values = {}
                for cell in row.findall("m:c", ns):
                    value = cell.find("m:v", ns)
                    raw = value.text if value is not None else ""
                    values[re.sub(r"\d", "", cell.get("r"))] = strings[int(raw)] if cell.get("t") == "s" else raw
                rows.append([values.get(chr(65 + i), "") for i in range(6)])
            result.append(rows[1:])
    assert len(result[0]) == 38 and len(result[1]) == 21
    return result


def table(doc, headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Shading Accent 1"
    for cell, value in zip(t.rows[0].cells, headers):
        cell.text = str(value)
    repeat = OxmlElement("w:tblHeader")
    t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        for cell, value in zip(t.add_row().cells, row):
            cell.text = str(value)
    for row in t.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)
    return t


def code(doc, data):
    text = json.dumps(data, indent=2) if not isinstance(data, str) else data
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(8)


def add_after(paragraph, text):
    node = OxmlElement("w:p")
    paragraph._p.addnext(node)
    p = WordParagraph(node, paragraph._parent)
    p.add_run(text)
    return p


def render_pdf(doc, output):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodyRef", fontSize=9, leading=12, spaceAfter=5))
    styles.add(ParagraphStyle(name="SmallRef", fontSize=7.5, leading=9.5))
    styles.add(ParagraphStyle(name="CodeRef", fontName="Courier", fontSize=7,
                              leading=8.5, spaceAfter=0, backColor=colors.HexColor("#F2F5F8")))
    for name in ("Title", "Heading1", "Heading2", "Heading3"):
        styles[name].textColor = colors.HexColor("#163B58")
    flow = []
    code_lines = []

    def flush():
        if code_lines:
            # Group consecutive source code lines; allow pagination between lines.
            for line in code_lines:
                wrapped = textwrap.wrap(line, width=105, subsequent_indent="  ",
                                        replace_whitespace=False, drop_whitespace=False) or [""]
                flow.append(Preformatted("\n".join(wrapped), styles["CodeRef"]))
            flow.append(Spacer(1, 7))
            code_lines.clear()

    for element in doc.element.body:
        if element.tag == qn("w:p"):
            p = WordParagraph(element, doc)
            if p._p.xpath('.//w:br[@w:type="page"]'):
                flush()
                if flow and not isinstance(flow[-1], PageBreak):
                    flow.append(PageBreak())
            text = p.text
            if not text:
                continue
            is_code = any(r.font.name in {"Consolas", "Courier New"} for r in p.runs)
            if is_code:
                code_lines.extend(text.splitlines())
                continue
            flush()
            name = p.style.name
            style = styles["Heading" + name[-1]] if name.startswith("Heading") else (
                styles["Title"] if name == "Title" else styles["BodyRef"])
            flow.append(Paragraph(escape(text).replace("\n", "<br/>"), style))
        elif element.tag == qn("w:tbl"):
            flush()
            t = WordTable(element, doc)
            count = len(t.columns)
            weights = {
                2: [0.30, 0.70], 3: [0.17, 0.25, 0.58], 4: [0.16, 0.15, 0.22, 0.47],
                5: [0.10, 0.17, 0.17, 0.18, 0.38],
            }.get(count, [1 / count] * count)
            # Endpoint index needs a wider route column.
            first = [c.text for c in t.rows[0].cells]
            if first == ["ID", "Method", "Relative endpoint", "Status"]:
                weights = [0.11, 0.10, 0.56, 0.23]
            rows = [[Paragraph(escape(c.text).replace("\n", "<br/>"), styles["SmallRef"])
                     for c in row.cells] for row in t.rows]
            rendered = Table(rows, colWidths=[495 * w for w in weights], repeatRows=1, hAlign="LEFT")
            rendered.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DFEAF2")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D3DCE3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            flow.extend([rendered, Spacer(1, 8)])
    flush()

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#52616E"))
        canvas.drawString(50, 28, "GoFixCarz | Customer-only API workbook reference | Development snapshot")
        canvas.drawRightString(A4[0] - 50, 28, str(document.page))
        canvas.restoreState()

    class PDF(SimpleDocTemplate):
        def afterFlowable(self, item):
            if isinstance(item, Paragraph) and item.style.name in ("Heading1", "Heading2"):
                key = "section-" + str(self.seq.nextf("section"))
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(item.getPlainText(), key,
                                         0 if item.style.name == "Heading1" else 1, False)

    PDF(str(output), pagesize=A4, leftMargin=50, rightMargin=50,
        topMargin=45, bottomMargin=50, title="GoFixCarz Customer API Workbook Reference",
        author="GoFixCarz").build(flow, onFirstPage=footer, onLaterPages=footer)


def main():
    OUT.mkdir(exist_ok=True)
    stories, screens = workbook()
    groups = json.loads((ROOT / "documents/customer-only-api-specification-source.json").read_text())
    examples = json.loads((OUT / "customer-contract-examples.json").read_text())
    source = Document(OUT / "GoFixCarz_Customer_API_Reference.docx")
    endpoints = {e["id"]: (e, group) for group in groups for e in group["endpoints"] if e["id"] not in EXCLUDED}
    assert len(endpoints) == 58
    # Add traceability and a concrete failure example to EVERY customer operation.
    for p in list(source.paragraphs):
        if p.style.name != "Heading 2":
            continue
        match = re.match(r"(API-\d+) ", p.text)
        supporting = p.text.startswith("Supporting —")
        if not match and not supporting:
            continue
        if supporting:
            refs = "US-27 | UI-14"
            key = "GET " + BASE + "/jobs/{job_id}/photos/{photo_index}"
            eid = "Supporting"
        else:
            eid = match.group(1)
            e, group = endpoints[eid]
            refs = ", ".join(f"US-{s}" for s in group["stories"]) + " | " + ", ".join(f"UI-{s:02d}" for s in group["screens"])
            key = e["method"] + " " + BASE + e["path"]
        after = add_after(p, "Related requirements (feature-group mapping): " + refs)
        failures = [x for x in examples.get(key, []) if x["status"] >= 400]
        failure = failures[0] if failures else {
            "status": 422 if eid in {"API-01", "API-02", "API-03", "API-04", "API-05"} else 401,
            "body": {
                "success": False,
                "message": "Validation error" if eid in {"API-01", "API-02", "API-03", "API-04", "API-05"} else "Authentication required",
                "data": None,
                "errors": [{"field": "request", "message": "Invalid or missing required value"}] if eid in {"API-01", "API-02", "API-03", "API-04", "API-05"} else [{"code": "AUTH_REQUIRED"}],
                "status_code": 422 if eid in {"API-01", "API-02", "API-03", "API-04", "API-05"} else 401,
            },
        }
        after = add_after(after, f"Representative failure: HTTP {failure['status']}; "
                          + ("captured development example." if failures else "illustrative common-error example; diagnostic wording may vary."))
        error_p = add_after(after, json.dumps(failure["body"], indent=2))
        for r in error_p.runs:
            r.font.name, r.font.size = "Consolas", Pt(8)

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Inches(.65)
    sec.left_margin = sec.right_margin = Inches(.7)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)
    doc.core_properties.title = "GoFixCarz Customer API Workbook Reference"
    doc.add_heading("GoFixCarz", 0)
    doc.add_heading("Customer API Workbook Reference", 0)
    doc.add_paragraph("Customer-only contracts, workbook requirements and delivery status")
    doc.add_paragraph("Prepared 21 October 2026 | Development reference; not a production certification")
    doc.add_paragraph("Source: GoFixCarz Customer App UI and User Stories workbook: 38 stories, 15 epics, 21 screens.")
    doc.add_paragraph("This document consolidates the existing development API reference and recorded synthetic integration-test examples. "
                      "It does not re-run implementation verification, certify current production availability, or authorize changes to code, data or services.")
    doc.add_paragraph("Customer pre-login authentication is included; general public browsing/content, garage/admin URLs and provider callback URLs are excluded as requested. "
                      "The older requirements drafts are not the current development contract where they conflict with later approvals.")
    doc.add_paragraph("All examples use fictional test records or placeholders. IDs can vary between test captures; examples from separate requests "
                      "must not be treated as a single importable dataset. Do not use any shown value as a live credential.")
    doc.add_heading("Contents", 1)
    contents = [
        "1. Scope, decisions and delivery gaps",
        "2. Common conventions, endpoint index and detailed contracts",
        "3. Lifecycle, ownership and backend integration boundaries",
        "4. Complete user-story traceability",
        "5. Complete screen traceability",
        "6. Assumptions and remaining decisions",
    ]
    for item in contents:
        doc.add_paragraph(item)
    doc.add_paragraph("Use Word's navigation pane or PDF bookmarks for section and endpoint navigation. Page numbers differ between formats; content is matched.")
    doc.add_heading(contents[0], 1)
    table(doc, ["Area", "Current documented direction"], [
        ["Authentication", "Approved mobile-only OTP; Indian +91 numbers. No email login/verification or password APIs. Email/password workbook options are not delivered."],
        ["Customer boundary", "Customer JWT/session and verified account ownership only. Garage contact records are not customer login identities; no automatic historical matching."],
        ["Booking and files", "Approved pending-only cancellation, customer-owned vehicles, private JPEG/PNG/WebP up to 5 MiB; concrete limits in contracts below."],
        ["Payments", "Razorpay selected. Checkout is pending: API-41 returns 503 PAYMENT_PROVIDER_NOT_CONFIGURED. Online payment and retry acceptance criteria remain unmet."],
        ["Notifications", "Persistent in-app activity documented. Push installation registration is not push delivery; live push delivery remains unconfigured."],
        ["Public browsing", "US-10–14 and US-37 URL catalogues excluded. Mixed screens are only partly covered. Service/garage selection comes from a separate approved source."],
        ["Deployment", "Development snapshot only. No production rollout, live SMS delivery, live storage operation, gateway settlement or availability certification."],
    ])
    doc.add_heading(contents[1], 1)
    # Preserve all original contracts, payload tables and captured response examples.
    for element in source.element.body:
        if element.tag != qn("w:sectPr"):
            doc.element.body.insert(len(doc.element.body) - 1, deepcopy(element))
    doc.add_page_break()
    doc.add_heading(contents[2], 1)
    for text in [
        "Booking states: PENDING, ACCEPTED, REJECTED, CANCELLED, CONVERTED, EXPIRED. "
        "Customer submits PENDING; garage alone accepts/rejects and creates the linked job. Cancellation is allowed only for future PENDING bookings without a job. "
        "Unattended past pending appointments expire. The completed-bookings UI is a linked_job_status=COMPLETED filter, not a new booking state.",
        "Job states: OPEN, IN_PROGRESS, WAITING_FOR_PARTS, QUALITY_CHECK, READY, COMPLETED, CANCELLED. "
        "Only garages change jobs. Customer endpoints return published read-only projections and authorized photos, never internal staff/cost fields.",
        "Times use ISO 8601 with an offset or UTC Z. Scheduling uses the garage's IANA timezone. "
        "Quotes expire after ten minutes and do not reserve capacity. Submission atomically rechecks capacity, services, prices and ownership. "
        "Replaying an idempotency key with the same payload returns the stored result; changing its payload returns 409.",
        "Money is integer INR paise. Invoice states shown to customers are UNPAID, PENDING, PAID, FAILED, REFUNDED, derived from trusted financial records. "
        "A CAPTURED payment record is distinct from invoice display state PAID. No new settlement is produced while checkout is pending.",
        "A future gateway integration must verify signatures and obtain server-confirmed order mapping, amount, currency and payment outcome. "
        "Deduplicate events and update payment/invoice/activity records transactionally. Never trust a client success screen. "
        "These are deferred backend requirements, not implemented callback contracts or URLs in this customer-only document.",
        "Reuse is limited to backend domain facts: garage services/slots, linked jobs, published invoices, storage adapters and OTP submission. "
        "The customer identity/session, explicit account ownership, bookings/quotes, activity, contextual conversations, reviews and tickets have separate customer-facing contracts. "
        "Garage/admin operations remain separately authorized and are not client-callable alternatives.",
        "Default collection pagination is page=1 and page_size=20 where declared, with page_size at most 100. "
        "Cursor message endpoints instead use limit and next_cursor. Empty items is a valid result; endpoint parameter tables are authoritative.",
    ]:
        doc.add_paragraph(text)

    def mapped(number, key):
        return [e["id"] for group in groups if number in group[key] for e in group["endpoints"] if e["id"] not in EXCLUDED]

    story_notes = {
        1: "Partial vs workbook: mobile-only approved; email registration excluded.",
        2: "Mobile OTP supported; no email OTP.",
        3: "OTP login only; password option removed by later approval.",
        6: "Name/address/photo/mobile supported; email contact change excluded.",
        9: "Explicitly account-linked history only; no automatic legacy matching.",
        15: "Partial: selected service IDs/summary supported; public service catalogue excluded.",
        23: "In-app event supported; live push delivery pending.",
        26: "Published events supported; legacy unflagged notes deliberately omitted.",
        29: "Reads trusted financial records; does not prove live gateway integration.",
        31: "Pending: checkout intentionally returns 503; no live payment.",
        32: "Pending: no payment creation/retry until Razorpay integration.",
        33: "Partial: in-app updates supported; live push/payment-webhook events pending.",
    }
    doc.add_page_break()
    doc.add_heading(contents[3], 1)
    doc.add_paragraph("Each original story and its acceptance criteria is retained below. API IDs map the feature group, not a claim that every acceptance criterion is delivered. "
                      "Status notes take precedence over a nonempty mapping.")
    for row in stories:
        sid = int(row[2].split("-")[1])
        ids = mapped(sid, "stories")
        doc.add_heading(f"{row[2]} | {row[1]} | {row[5]}", 2)
        doc.add_paragraph(row[3])
        doc.add_paragraph("Workbook acceptance criteria: " + row[4])
        doc.add_paragraph("Customer operations: " + (", ".join(ids) if ids else "None — excluded public browsing/content requirement."))
        note = story_notes.get(sid, "Documented development contract; not production verification." if ids else "Intentionally excluded by the later customer-only scope.")
        doc.add_paragraph("Coverage / limitation: " + note)
    doc.add_page_break()
    doc.add_heading(contents[4], 1)
    screen_notes = {
        1: "Partial: mobile-only OTP; email/password UI options excluded.",
        3: "Partial: mobile required; optional-email registration is not supported.",
        4: "Partial: customer shortcuts/activity only; public search/popular/nearby discovery excluded.",
        5: "Excluded: public garage search.",
        6: "Excluded: public garage detail/reviews/service listing.",
        7: "Partial: selected service IDs are submitted in API-29; public service details excluded.",
        8: "Partial: mobile contact changes only; email editing not supported.",
        12: "Completed tab is derived from linked completed jobs; EXPIRED remains a booking state.",
        16: "Pending: Razorpay checkout/retry. Trusted existing records/receipt reads only.",
        17: "In-app activity/filtering; push delivery and live payment events pending.",
        18: "Contextual messages supported; live push delivery pending.",
        20: "Partial: tickets/replies supported; FAQ/privacy/terms public content excluded.",
    }
    for row in screens:
        uid = int(row[0].split("-")[1])
        ids = mapped(uid, "screens")
        if uid == 7:
            ids = ["API-29"]
        doc.add_heading(f"{row[0]} | {row[2]}", 2)
        doc.add_paragraph("Workbook components: " + row[3])
        doc.add_paragraph("Expected behavior: " + row[4])
        doc.add_paragraph("Workbook dependencies: " + row[5])
        doc.add_paragraph("Customer operations: " + (", ".join(ids) if ids else "None in this customer-only catalogue."))
        doc.add_paragraph("Coverage / limitation: " + screen_notes.get(uid, "Documented development contract; not production verification."))
    doc.add_heading(contents[5], 1)
    table(doc, ["Item", "Decision / remaining limitation"], [
        ["Later approvals", "Mobile-only OTP/no password; pending-only cancellation; private images; reviews moderated before publication; conversations restricted to owned booking/job contexts; Razorpay selected but checkout deferred."],
        ["Security defaults", "Access 15 minutes; session absolute maximum 30 days; OTP expiry 5 minutes, resend cooldown 30 seconds, five cumulative guesses per resend chain; new-mobile change requires OTP authentication within 15 minutes. These are development rules, not universal production policy."],
        ["Ownership", "Do not infer a login identity from a garage contact/phone or claim historical invoices for a newly registered customer. New work uses explicit ownership/linkage."],
        ["Files/retention", "5 MiB and 20 million decoded pixels; at most five linked booking/ticket images. No arbitrary document upload or antivirus-service claim. Physical deletion/retention policy still requires approval."],
        ["Reviews/messages", "Seven-day review editing with re-moderation. Terminal booking/job conversations and closed/resolved support tickets are read-only. Retention policy needs production review."],
        ["Billing", "Legal tax invoice fields, final tax/discount policy, refunds and partial-payment scope require approval. No historical missing invoice is repaired or fabricated."],
        ["Remaining delivery", "Razorpay connection and secure settlement integration; push delivery; production verification. None is represented as working by this document."],
        ["Public dependencies", "A separate public product/API may supply garage/service selection and legal content. No public or other-role URL catalogue is included here."],
    ])
    footer = sec.footer.paragraphs[0]
    footer.text = "GoFixCarz | Customer-only API workbook reference | Page "
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    doc.save(STEM.with_suffix(".docx"))
    render_pdf(doc, STEM.with_suffix(".pdf"))
    pdf = fitz.open(STEM.with_suffix(".pdf"))
    text = "\n".join(p.get_text() for p in pdf)
    assert all(f"US-{i} |" in text for i in range(1, 39))
    assert all(f"UI-{i:02d} |" in text for i in range(1, 22))
    assert all(eid in text for eid in endpoints)
    assert "PAYMENT_PROVIDER_NOT_CONFIGURED" in text
    assert "Admin API Requirements" not in text
    # Geometric check includes all text spans; footers are intentionally below body.
    overflow = []
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    if x0 < 40 or x1 > page.rect.width - 35 or y0 < 20 or y1 > page.rect.height - 15:
                        overflow.append([page.number + 1, span["text"]])
    assert not overflow, overflow[:10]
    for i in [0, 5, len(pdf) - 3]:
        pdf[i].get_pixmap(matrix=fitz.Matrix(1, 1)).save(str(OUT / f"customer-workbook-page-{i+1}.png"))
    report = {
        "stories": 38, "screens": 21, "inventory_operations": 58,
        "supporting_operations": 1, "pending_operation": "API-41",
        "excluded_password_operations": sorted(EXCLUDED), "pdf_pages": len(pdf),
        "checks": ["All story/screen IDs", "All applicable operation IDs", "Pending payment visible",
                   "Customer footer", "Text inside page bounds", "Shared Word/PDF source"],
    }
    (OUT / "customer-workbook-validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
