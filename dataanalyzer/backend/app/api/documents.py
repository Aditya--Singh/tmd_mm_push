"""The documents a person shares, and what is found in them.

A document is uploaded, read, described, drawn and summarised. The findings are kept with
the document, so that a person may come back to them.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.analysis.insights import (
    answer_question,
    rule_based_insights,
    write_insights,
    write_summary,
)
from app.analysis.plots import build_plots
from app.analysis.profiling import (
    DocumentError,
    is_readable,
    preview_of,
    profile_of,
    read_document,
)
from app.config import get_settings
from app.core.db import get_db
from app.core.models import Document
from app.core.security import current_session, require_admin
from sqlalchemy.orm import Session

log = logging.getLogger("analyzer.documents")

router = APIRouter(prefix="/api/documents", tags=["documents"])

def _data_dir() -> Path:
    """Where this app keeps its files."""
    return Path(get_settings().data_dir).resolve()


#: Where the documents and their pictures are kept.
UPLOADS = _data_dir() / "uploads"
PLOTS = _data_dir() / "plots"


def _as_dict(text: str, fallback) -> object:
    try:
        return json.loads(text) if text else fallback
    except (TypeError, ValueError):
        return fallback


def _as_json(value: object) -> str:
    return json.dumps(value, default=str)


def _document_of(db: Session, document_id: int) -> Document:
    document = db.query(Document).filter(Document.id == document_id).first()

    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such document.")

    return document


def _present(document: Document) -> dict:
    """A document, as the interface shows it."""
    return {
        "id": document.id,
        "name": document.name,
        "filename": document.filename,
        "sheet": document.sheet,
        "sizeBytes": document.size_bytes,
        "rows": document.rows,
        "columns": document.columns,
        "uploadedBy": document.uploaded_by,
        "uploadedAt": document.uploaded_at.isoformat() if document.uploaded_at else None,
        "profile": _as_dict(document.profile, {}),
        "preview": _as_dict(document.preview, []),
        "summary": document.summary,
        "summaryReason": document.summary_reason,
        "insights": _as_dict(document.insights, []),
        "plots": _as_dict(document.plots, []),
    }


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    session: dict = Depends(current_session),
):
    """The documents this person may see."""
    documents = db.query(Document).order_by(Document.uploaded_at.desc()).all()

    return {
        "documents": [
            {
                "id": document.id,
                "name": document.name,
                "filename": document.filename,
                "sizeBytes": document.size_bytes,
                "rows": document.rows,
                "columns": document.columns,
                "uploadedBy": document.uploaded_by,
                "uploadedAt": document.uploaded_at.isoformat() if document.uploaded_at else None,
                "hasSummary": bool(document.summary),
            }
            for document in documents
        ],
        "username": session["username"],
        "role": session["role"],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    session: dict = Depends(current_session),
):
    """
    Take a document, read it, and describe it.

    The document is kept in `data/uploads` and the findings with it in the database. The
    name of the file is kept as it was given, so that the person recognises it.
    """
    settings = get_settings()
    filename = Path(file.filename or "document").name

    if not is_readable(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Share an Excel workbook or a CSV file.",
        )

    UPLOADS.mkdir(parents=True, exist_ok=True)

    target = UPLOADS / f"{filename}"

    try:
        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
    finally:
        await file.close()

    if target.stat().st_size > settings.max_upload_bytes:
        target.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"The document is larger than {settings.max_upload_bytes // (1024 * 1024)} MB. "
                "Share a smaller one, or a part of it."
            ),
        )

    try:
        frame, sheets = read_document(target, filename)
    except DocumentError as exc:
        target.unlink(missing_ok=True)

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    profile = profile_of(frame, settings.preview_rows)
    preview = preview_of(frame, settings.preview_rows)

    document = Document(
        name=Path(filename).stem or filename,
        filename=filename,
        sheet=sheets[0] if sheets else "",
        size_bytes=target.stat().st_size,
        rows=profile["rows"],
        columns=profile["columns"],
        uploaded_by=session["username"],
        profile=_as_json(profile),
        preview=_as_json(preview),
        insights=_as_json([]),
        plots=_as_json([]),
    )

    db.add(document)
    db.flush()

    try:
        pictures = build_plots(frame, PLOTS / str(document.id))
    except Exception as exc:
        # A picture that cannot be drawn must not stop the document from being
        # read: the figures and the findings are worth more than the pictures.
        log.warning("the pictures of %s could not be drawn: %s", filename, exc)

        pictures = []

    document.plots = _as_json(pictures)

    summary, reason = await write_summary(profile, preview)

    document.summary = summary
    document.summary_reason = reason

    found = rule_based_insights(profile, profile.get("correlations") or {})

    model_findings, _ = await write_insights(profile, preview)

    document.insights = _as_json((found + model_findings)[:12])

    db.commit()

    log.info(
        "a document was shared by %s: %s (%s rows)",
        session["username"],
        filename,
        profile["rows"],
    )

    return _present(document)


@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    session: dict = Depends(current_session),
):
    """One document, with everything that was found in it."""
    return _present(_document_of(db, document_id))


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    session: dict = Depends(require_admin),
):
    """Remove a document. Only an administrator may do this."""
    document = _document_of(db, document_id)

    (UPLOADS / document.filename).unlink(missing_ok=True)
    shutil.rmtree(PLOTS / str(document.id), ignore_errors=True)

    db.delete(document)
    db.commit()

    log.info("a document was removed by %s", session["username"])

    return {"removed": document_id}


@router.post("/{document_id}/summary")
async def make_summary(
    document_id: int,
    db: Session = Depends(get_db),
    session: dict = Depends(current_session),
):
    """Write the summary of a document again."""
    document = _document_of(db, document_id)

    profile = _as_dict(document.profile, {})
    preview = _as_dict(document.preview, [])

    summary, reason = await write_summary(profile, preview)

    document.summary = summary
    document.summary_reason = reason

    db.commit()

    return {"summary": summary, "reason": reason}


@router.post("/{document_id}/insights")
async def make_insights(
    document_id: int,
    db: Session = Depends(get_db),
    session: dict = Depends(current_session),
):
    """Look for the findings of a document again."""
    document = _document_of(db, document_id)

    profile = _as_dict(document.profile, {})
    preview = _as_dict(document.preview, [])

    found = rule_based_insights(profile, profile.get("correlations") or {})

    model_findings, reason = await write_insights(profile, preview)

    document.insights = _as_json((found + model_findings)[:12])

    db.commit()

    return {"insights": _as_dict(document.insights, []), "reason": reason}


class AskIn(BaseModel):
    question: str = ""


@router.post("/{document_id}/ask")
async def ask_about(
    document_id: int,
    body: AskIn,
    db: Session = Depends(get_db),
    session: dict = Depends(current_session),
):
    """Ask a question about a document."""
    question = body.question.strip()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The question is empty."
        )

    document = _document_of(db, document_id)

    answer = await answer_question(
        _as_dict(document.profile, {}), _as_dict(document.preview, []), question
    )

    return {"answer": answer}
