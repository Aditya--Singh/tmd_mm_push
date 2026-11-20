import asyncio
import io
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

from app.core.uploads import validate_upload


def upload(name, data):
    return UploadFile(file=io.BytesIO(data), filename=name)


def check(name, data, **kw):
    return asyncio.run(validate_upload(upload(name, data), **kw))


def make_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def make_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.txt", "x")
    return buf.getvalue()


@pytest.mark.parametrize(
    "name,data,ext",
    [
        ("circular.pdf", b"%PDF-1.7\n...", ".pdf"),
        ("Letter.DOCX", make_docx(), ".docx"),
        ("notes.txt", "नमस्ते hello".encode(), ".txt"),
    ],
)
def test_valid_files(name, data, ext):
    f = check(name, data)
    assert f.ext == ext
    assert f.filename == name
    assert f.content == data


def test_filename_is_sanitized():
    assert check("../../etc/evil.txt", b"x").filename == "evil.txt"
    assert check("C:\\Users\\a\\doc.txt", b"x").filename == "doc.txt"


def assert_rejected(status, name, data, **kw):
    with pytest.raises(HTTPException) as exc:
        check(name, data, **kw)
    assert exc.value.status_code == status


def test_disallowed_extension():
    assert_rejected(415, "script.exe", b"MZ")
    assert_rejected(415, "noext", b"hello")


def test_custom_allowlist():
    assert_rejected(415, "a.txt", b"hello", allowed={".pdf"})


@pytest.mark.parametrize(
    "name,data",
    [
        ("fake.pdf", b"not a pdf"),
        ("fake.docx", b"%PDF-1.4"),
        ("plain.docx", make_zip()),
        ("bad.docx", b"PK\x03\x04garbage"),
        ("binary.txt", b"\xff\xfe\x00\x81"),
    ],
)
def test_content_mismatch(name, data):
    assert_rejected(415, name, data)


def test_empty_file():
    assert_rejected(400, "empty.txt", b"")


def test_oversize_file():
    assert_rejected(413, "big.txt", b"a" * 101, max_bytes=100)
    assert check("ok.txt", b"a" * 100, max_bytes=100).content == b"a" * 100


def test_size_limit_from_env(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    assert_rejected(413, "big.txt", b"a" * (1024 * 1024 + 1))


# --- PPTX, XLSX, CSV, JSON ----------------------------------------------------

ALL_TYPES = {".pdf", ".docx", ".txt", ".pptx", ".xlsx", ".csv", ".json"}


def make_office_zip(*members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in members:
            zf.writestr(name, "<x/>")
    return buf.getvalue()


PPTX = make_office_zip("[Content_Types].xml", "ppt/presentation.xml")
XLSX = make_office_zip("[Content_Types].xml", "xl/workbook.xml")
XLSX_MACRO = make_office_zip("xl/workbook.xml", "xl/vbaProject.bin")


@pytest.mark.parametrize(
    "name,data,ext",
    [
        ("deck.pptx", PPTX, ".pptx"),
        ("Report.XLSX", XLSX, ".xlsx"),
        ("branches.csv", b"branch,amount\nUdaipur,100\n", ".csv"),
        ("excel-export.csv", b"\xef\xbb\xbfbranch,amount\nJaipur,5\n", ".csv"),
        ("data.json", b'{"rows": [{"a": 1}]}', ".json"),
        ("bom.json", b"\xef\xbb\xbf[1, 2, 3]", ".json"),
    ],
)
def test_new_valid_types(name, data, ext):
    f = check(name, data, allowed=ALL_TYPES)
    assert f.ext == ext
    assert f.content == data


@pytest.mark.parametrize(
    "name,data",
    [
        ("letter.pptx", make_docx()),
        ("deck.xlsx", PPTX),
        ("sheet.docx", XLSX),
        ("macro.xlsx", XLSX_MACRO),
        ("notzip.pptx", b"%PDF-1.4"),
        ("broken.json", b'{"a": 1,'),
        ("binary.csv", b"\xff\xfe\x00\x81"),
        ("nul.csv", b"a,b\x00\n1,2\n"),
        ("nul.txt", b"hello\x00world"),
        ("utf16.json", '{"a": 1}'.encode("utf-16")),
    ],
)
def test_new_types_content_mismatch(name, data):
    assert_rejected(415, name, data, allowed=ALL_TYPES)


def test_new_types_not_allowed_by_default():
    assert_rejected(415, "deck.pptx", PPTX)
    assert_rejected(415, "data.csv", b"a,b\n")


def test_unsupported_type_in_allowlist_is_a_programming_error():
    with pytest.raises(ValueError, match=".exe"):
        check("a.txt", b"x", allowed={".txt", ".exe"})
