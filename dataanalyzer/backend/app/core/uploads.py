"""Upload validation shared by all tabs: file type, content signature and size."""

import io
import json
import os
import zipfile
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

DEFAULT_ALLOWED = frozenset({".pdf", ".docx", ".txt"})
SUPPORTED_TYPES = frozenset(
    {".pdf", ".docx", ".txt", ".pptx", ".xlsx", ".csv", ".json"}
)
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ValidatedFile:
    filename: str
    ext: str
    content: bytes


def _safe_name(name: str | None) -> str:
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    return base or "upload"


def _zip_members(content: bytes) -> set[str] | None:
    """Names inside a ZIP-based Office file, or None if it is not a valid ZIP."""
    if not content.startswith(b"PK\x03\x04"):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return set(zf.namelist())
    except zipfile.BadZipFile:
        return None


def _utf8_text(content: bytes) -> str | None:
    """Decoded text if the content is UTF-8 (BOM allowed) with no NUL bytes."""
    if b"\x00" in content:
        return None
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _content_matches(ext: str, content: bytes) -> bool:
    if ext == ".pdf":
        return content.startswith(b"%PDF-")
    if ext in (".docx", ".pptx", ".xlsx"):
        members = _zip_members(content)
        if members is None:
            return False
        if ext == ".docx":
            return "word/document.xml" in members
        if ext == ".pptx":
            return "ppt/presentation.xml" in members
        # Macro-enabled workbooks are not accepted (spec section 5.3).
        return "xl/workbook.xml" in members and "xl/vbaProject.bin" not in members
    if ext in (".txt", ".csv", ".json"):
        text = _utf8_text(content)
        if text is None:
            return False
        if ext == ".json":
            try:
                json.loads(text)
            except ValueError:
                return False
        return True
    return False


async def validate_upload(
    file: UploadFile,
    allowed: set[str] | frozenset[str] = DEFAULT_ALLOWED,
    max_bytes: int | None = None,
) -> ValidatedFile:
    """Read and validate an upload. Raises HTTPException 400/413/415 on failure."""
    unsupported = set(allowed) - SUPPORTED_TYPES
    if unsupported:
        raise ValueError(f"Unsupported upload types: {sorted(unsupported)}")
    limit = max_bytes if max_bytes is not None else get_settings().max_upload_bytes
    filename = _safe_name(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{ext or 'none'}' is not allowed. Allowed: {', '.join(sorted(allowed))}",
        )

    buf = bytearray()
    while chunk := await file.read(CHUNK_SIZE):
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File is larger than the {limit // (1024 * 1024)} MB limit.",
            )
    content = bytes(buf)
    if not content:
        raise HTTPException(status_code=400, detail="File is empty.")
    if not _content_matches(ext, content):
        raise HTTPException(
            status_code=415,
            detail=f"File content does not match its '{ext}' extension.",
        )
    return ValidatedFile(filename=filename, ext=ext, content=content)
