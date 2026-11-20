"""Build small test files in memory. No files from private/ are ever used."""

import io

import pandas as pd


def make_docx(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    from docx import Document

    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_docx_with_tracked_change() -> bytes:
    from docx import Document
    from docx.oxml import parse_xml

    doc = Document()
    p = doc.add_paragraph("Kept text. ")
    ins = parse_xml(
        '<w:ins xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'w:id="1" w:author="A" w:date="2026-01-01T00:00:00Z">'
        "<w:r><w:t>Inserted text.</w:t></w:r></w:ins>"
    )
    p._p.append(ins)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_pptx(slides: list[list[str]], table: list[list[str]] | None = None) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    layout = prs.slide_layouts[6]  # blank
    for lines in slides:
        slide = prs.slides.add_slide(layout)
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(2))
        box.text_frame.text = "\n".join(lines)
    if table:
        slide = prs.slides.add_slide(layout)
        shape = slide.shapes.add_table(
            len(table), len(table[0]), Inches(1), Inches(1), Inches(6), Inches(2)
        )
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                shape.table.cell(r, c).text = value
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def make_xlsx(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str | None]) -> bytes:
    """A minimal PDF. Each page shows one line of text; None gives a page with no text."""
    objects: list[bytes] = []
    n = len(pages)
    font_id = 3 + 2 * n
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i, text in enumerate(pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        stream = (
            f"BT /F1 12 Tf 72 720 Td ({_escape(text)}) Tj ET".encode() if text else b""
        )
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def make_rich_docx() -> bytes:
    """A DOCX with the features spec 5.1 says must survive edits.

    Paragraphs, in order:
      0 "KYC Update" (Heading 1)
      1 "The branch " + bold "manger" + " will review it."
      2 bold "Please acc" + "omodate the request."
      3 "Visit " + link "our websit" + " today."
      4-7 table cells: "Account", "Amount", "Savings", "1,000"
      8 italic "Unchanged closing paragraph."
      9 "First item" (List Number)
    """
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches

    doc = Document()
    section = doc.sections[0]
    section.left_margin = Inches(1.25)
    section.header.paragraphs[0].text = "Punjab National Bank - Letterhead"
    section.footer.paragraphs[0].text = "Confidential"

    doc.add_heading("KYC Update", level=1)

    p = doc.add_paragraph("The branch ")
    p.add_run("manger").bold = True
    p.add_run(" will review it.")

    p = doc.add_paragraph()
    p.add_run("Please acc").bold = True
    p.add_run("omodate the request.")

    p = doc.add_paragraph("Visit ")
    r_id = p.part.relate_to("https://example.invalid/", RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "our websit"
    run.append(t)
    link.append(run)
    p._p.append(link)
    p.add_run(" today.")

    table = doc.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    for r, row in enumerate([["Account", "Amount"], ["Savings", "1,000"]]):
        for c, value in enumerate(row):
            table.cell(r, c).text = value

    doc.add_paragraph().add_run("Unchanged closing paragraph.").italic = True
    doc.add_paragraph("First item", style="List Number")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_emphasis_docx() -> bytes:
    """Paragraphs with bold, italic and underlined phrases inside normal text.

    0 "Recovery in " + bold "NPA accounts" + " is " + italic "below target" + " this quarter."
    1 bold "Note:" + " branches must " + underline "submit" + " the report."
    2 bold "Overdue" + bold " loans" + " are rising."  (one phrase split over two runs)
    """
    from docx import Document

    doc = Document()
    p = doc.add_paragraph("Recovery in ")
    p.add_run("NPA accounts").bold = True
    p.add_run(" is ")
    p.add_run("below target").italic = True
    p.add_run(" this quarter.")

    p = doc.add_paragraph()
    p.add_run("Note:").bold = True
    p.add_run(" branches must ")
    p.add_run("submit").underline = True
    p.add_run(" the report.")

    p = doc.add_paragraph()
    p.add_run("Overdue").bold = True
    p.add_run(" loans").bold = True
    p.add_run(" are rising in every zone this quarter.")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
