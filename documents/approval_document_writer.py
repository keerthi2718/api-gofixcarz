"""Shared, plain document renderer for client API approval specifications."""
import json
import textwrap
from html import escape
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted, KeepTogether, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4


class ApprovalWriter:
    def __init__(self, title):
        self.title = title
        self.doc = Document()
        section = self.doc.sections[0]
        section.top_margin = section.bottom_margin = Inches(.7)
        section.left_margin = section.right_margin = Inches(.7)
        self.doc.styles["Normal"].font.name = "Calibri"
        self.doc.styles["Normal"].font.size = Pt(10)
        self.doc.styles["Normal"].paragraph_format.space_after = Pt(6)
        for name in ["Heading 1", "Heading 2", "Heading 3"]:
            self.doc.styles[name].font.color.rgb = RGBColor.from_string("163B58")
        self.doc.core_properties.title = title
        footer = section.footer.paragraphs[0]
        footer.text = "GoFixCarz | Admin API Requirements | Draft for Client Approval | Page "
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "PAGE")
        footer._p.append(field)
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(name="BodySpec", fontName="Helvetica", fontSize=9, leading=12, spaceAfter=6))
        self.styles.add(ParagraphStyle(name="SmallSpec", fontName="Helvetica", fontSize=8, leading=10, spaceAfter=4))
        self.styles.add(ParagraphStyle(name="CodeSpec", fontName="Courier", fontSize=7.5, leading=9,
                                      backColor=colors.HexColor("#F2F5F8"), borderPadding=6, spaceAfter=8))
        for name in ["Title", "Heading1", "Heading2", "Heading3"]:
            self.styles[name].textColor = colors.HexColor("#163B58")
        self.flow = []

    def cover(self):
        self.doc.add_heading("GoFixCarz", 0)
        self.doc.add_heading(self.title, 0)
        self.flow.extend([Spacer(1,65), Paragraph("GoFixCarz",self.styles["Title"]),
                          Paragraph(escape(self.title),self.styles["Title"]),Spacer(1,20)])

    def p(self, text, small=False):
        paragraph = self.doc.add_paragraph(text)
        if text in ("Request payload:", "Sample success response:", "Sample error response:"):
            paragraph.paragraph_format.keep_with_next = True
        self.flow.append(Paragraph(escape(text),self.styles["SmallSpec" if small else "BodySpec"]))

    def h(self, text, level=1):
        self.doc.add_heading(text, level=level)
        self.flow.append(Paragraph(escape(text),self.styles[f"Heading{level}"]))

    def br(self):
        self.doc.add_page_break()
        self.flow.append(PageBreak())

    def code(self, value):
        text = value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=True)
        lines = []
        for line in text.splitlines():
            indent = len(line)-len(line.lstrip())
            lines.extend(textwrap.wrap(line,width=88,subsequent_indent=" "*(min(indent,12)+2),
                                       replace_whitespace=False,drop_whitespace=False) or [""])
        text = "\n".join(lines)
        paragraph = self.doc.add_paragraph()
        paragraph.paragraph_format.keep_together = True
        run = paragraph.add_run(text)
        run.font.name = "Consolas"
        run.font.size = Pt(8)
        shade = OxmlElement("w:shd")
        shade.set(qn("w:fill"), "F2F5F8")
        paragraph._p.get_or_add_pPr().append(shade)
        self.flow.append(KeepTogether([Preformatted(text,self.styles["CodeSpec"])]))

    def table(self, headers, rows, widths):
        table = self.doc.add_table(rows=1,cols=len(headers))
        table.style = "Light Shading Accent 1"
        for cell,value in zip(table.rows[0].cells,headers):
            cell.text = str(value)
        repeat = OxmlElement("w:tblHeader")
        table.rows[0]._tr.get_or_add_trPr().append(repeat)
        for row in rows:
            for cell,value in zip(table.add_row().cells,row):
                cell.text = str(value)
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(8)
        data = [[Paragraph(escape(str(x)),self.styles["SmallSpec"]) for x in row] for row in [headers]+rows]
        pdf_table = Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
        pdf_table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#DFEAF2")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("GRID",(0,0),(-1,-1),.25,colors.HexColor("#D3DCE3")),
            ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
        ]))
        self.flow.extend([pdf_table,Spacer(1,10)])

    def save(self, stem):
        stem = Path(stem)
        stem.parent.mkdir(exist_ok=True,parents=True)
        self.doc.save(str(stem)+".docx")

        def footer(canvas, document):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor("#D3DCE3"))
            canvas.line(50,42,A4[0]-50,42)
            canvas.setFont("Helvetica",7)
            canvas.setFillColor(colors.HexColor("#52616E"))
            canvas.drawString(50,29,"GoFixCarz | Admin API Requirements | Draft for Client Approval")
            canvas.drawRightString(A4[0]-50,29,str(document.page))
            canvas.restoreState()

        class PDF(SimpleDocTemplate):
            def afterFlowable(self, item):
                if isinstance(item,Paragraph) and item.style.name in ("Heading1","Heading2"):
                    key = "bookmark-"+str(self.seq.nextf("bookmark"))
                    self.canv.bookmarkPage(key)
                    self.canv.addOutlineEntry(item.getPlainText(),key,0 if item.style.name=="Heading1" else 1,False)

        PDF(str(stem)+".pdf",pagesize=A4,leftMargin=50,rightMargin=50,topMargin=48,bottomMargin=55,
            title=self.title,author="GoFixCarz").build(self.flow,onFirstPage=footer,onLaterPages=footer)
