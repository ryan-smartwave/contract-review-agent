from io import BytesIO

from src.documents.extract import extract_text_preview


def tiny_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj".encode() + obj + b"endobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)


def tiny_docx(text: str) -> bytes:
    from docx import Document

    buf = BytesIO()
    doc = Document()
    doc.add_paragraph(text)
    doc.save(buf)
    return buf.getvalue()


def test_pdf_preview_extracts_text():
    preview = extract_text_preview(tiny_pdf("Master Services Agreement v2"), "msa.pdf")
    assert "Master Services Agreement v2" in preview


def test_docx_preview_extracts_text():
    preview = extract_text_preview(tiny_docx("Section 4.2 Limitation of Liability"), "msa.docx")
    assert "Section 4.2 Limitation of Liability" in preview


def test_preview_respects_max_chars():
    preview = extract_text_preview(tiny_docx("word " * 2000), "long.docx", max_chars=100)
    assert len(preview) == 100


def test_unsupported_extension_returns_empty():
    assert extract_text_preview(b"anything", "photo.png") == ""


def test_corrupt_pdf_returns_empty_not_error():
    assert extract_text_preview(b"%PDF-not really", "broken.pdf") == ""
