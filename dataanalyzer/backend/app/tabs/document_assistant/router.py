"""HTTP routes for the Document Assistant tab (phases 2-4: upload, Summarize, Rewrite,
Proofread, downloads and Ask about data)."""

import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.languagetool import LanguageToolClient
from app.core.ollama import OllamaClient, OllamaContextError, OllamaError
from app.core.session import current_session, require_admin
from app.core.uploads import SUPPORTED_TYPES, ValidatedFile, validate_upload

from . import segments as seg
from .data_cells import Cell, TextCells, edited_sheet_csv, text_cells, write_back
from .data_chat import ask
from .docx_writer import apply_span_edits, new_docx, replace_paragraphs
from .extraction import DATA_TYPES, Extracted, ExtractionError, extract, sheet_preview
from .file_store import FileExpired, FileStore, StoredFile, get_store
from .proofread import ProofreadUnavailable, apply_to_text, proofread_document
from .rewrite import DocumentTooLong, rewrite_document, same_words
from .rewrite import check_length as check_edit_length
from .summarize import (
    Event,
    SummaryTooLong,
    check_length,
    summarize_data,
    summarize_text,
)
from .xlsx_writer import CellNotEditable, has_drawings

router = APIRouter(prefix="/api/document-assistant", tags=["document-assistant"])
log = logging.getLogger(__name__)

LLM_UNAVAILABLE = (
    "The language model is not available right now. Please check that Ollama is running "
    "and try again."
)
TOO_LONG = "This document is too long to process in one go. Please shorten it."
PROOFREAD_UNAVAILABLE = (
    "Proofreading is not available right now: neither LanguageTool nor the language "
    "model could be reached. Please check that both are running and try again."
)
REWRITE_DATA = (
    "Rewrite works on documents and text. For data files, use Proofread, Summarize or "
    "Ask about data."
)
NO_TEXT_CELLS = (
    "This file has no text columns to check. Numbers, amounts, dates and codes are not "
    "proofread."
)
NOT_DATA = "Ask about data works with Excel, CSV and JSON files."
MAX_QUESTION_CHARS = 2_000
# Cell values are short, so the LLM checks more of them per request than paragraphs.
DATA_SECTION_CELLS = 25

DOCX_SPAN_WARNINGS = [
    (
        "Where a correction covers text with mixed formatting (for example a word that "
        "is half bold), the corrected text takes the formatting of its first part."
    ),
    "Text in text boxes, footnotes, endnotes, comments and fields was not checked.",
]
DOCX_REWRITE_WARNINGS = [
    (
        "Rewritten paragraphs keep their paragraph style and main formatting. Bold, "
        "italic or underlined phrases keep their formatting only where they appear "
        "unchanged; other character formatting inside them (colours, highlights, mixed "
        "fonts) is lost."
    ),
    (
        "Tables, paragraphs with links, fields or images, and letter formalities "
        "(salutation, closing, reference, address, subject, signature) were not rewritten."
    ),
]
DATA_WARNINGS = {
    ".xlsx": [
        "Each corrected cell takes a single style: mixed formatting inside it is lost.",
        "Formula cells, numbers, dates and codes were not checked or changed.",
    ],
    ".csv": [],
    ".json": ["Values and key order are kept; indentation is changed to 2 spaces."],
}
XLSX_DRAWINGS_WARNING = (
    "This workbook has charts, images or shapes. They are removed when the corrected "
    "workbook is saved. To keep them, download the CSV of the edited sheet instead and "
    "copy the corrections into your original file."
)
NEW_DOCX_WARNINGS = [
    (
        "This is a new, plain Word document. The original file's layout and formatting "
        "are not kept."
    )
]

MEDIA_TYPES = {
    ".txt": "text/plain; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json",
}


def get_ollama() -> OllamaClient:
    return OllamaClient()


def get_languagetool() -> LanguageToolClient:
    return LanguageToolClient()


def _extract_or_raise(file: ValidatedFile) -> Extracted:
    try:
        return extract(file)
    except ExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None


def _get(store: FileStore, file_id: str) -> StoredFile:
    try:
        return store.get(file_id)
    except FileExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from None


def _load(store: FileStore, file_id: str) -> Extracted:
    stored = _get(store, file_id)
    return _extract_or_raise(
        ValidatedFile(stored.filename, stored.ext, stored.read_bytes())
    )


def _document(
    store: FileStore, text: str | None, file_id: str | None, mode: str
) -> tuple[seg.SegmentedText, StoredFile | None, TextCells | None]:
    """The paragraphs to rewrite or proofread, from pasted text or an uploaded file.

    For a data file (Proofread only), the paragraphs are the distinct values of its text
    columns, and the cells holding each value are returned too.
    """
    if (text is None) == (file_id is None):
        raise HTTPException(status_code=400, detail="Send either text or a file id.")
    cells = None
    if file_id is None:
        if not text.strip():
            raise HTTPException(status_code=400, detail="Please enter some text.")
        doc, stored = seg.from_text(text), None
    else:
        stored = _get(store, file_id)
        extracted = _load(store, file_id)  # rejects tracked changes, scanned PDFs, ...
        if extracted.kind == "data":
            if mode != "Proofread":
                raise HTTPException(status_code=422, detail=REWRITE_DATA)
            cells = text_cells(stored.ext, stored.read_bytes())
            if not cells.doc.segments:
                raise HTTPException(status_code=422, detail=NO_TEXT_CELLS)
            doc = cells.doc
        elif stored.ext == ".docx":
            doc = seg.from_docx(stored.read_bytes())
        else:
            doc = seg.from_text(extracted.text)
    try:
        check_edit_length(doc.text, mode)
    except DocumentTooLong as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    return doc, stored, cells


def _derived_name(stored: StoredFile | None, suffix: str, ext: str) -> str:
    stem = Path(stored.filename).stem if stored else "document"
    return f"{stem}-{suffix}{ext}"


@router.post("/extract")
async def extract_upload(
    file: UploadFile = File(...),
    store: FileStore = Depends(get_store),
    session: dict = Depends(current_session),
) -> dict:
    validated = await validate_upload(file, allowed=SUPPORTED_TYPES)
    result = _extract_or_raise(validated)
    stored = store.save(validated.filename, validated.content)
    body: dict = {
        "file_id": stored.id,
        "filename": stored.filename,
        "kind": result.kind,
        "notices": result.notices,
        "expires_at": stored.expires_at,
    }
    if result.kind == "text":
        body.update(text=result.text, word_count=result.word_count)
    else:
        body.update(
            row_count=result.row_count,
            sheets=[sheet_preview(s) for s in result.sheets],
        )
    return body


class SummarizeRequest(BaseModel):
    text: str | None = None
    file_id: str | None = None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _sse_stream(events: AsyncIterator[Event | dict]) -> StreamingResponse:
    # Closing the response (the user pressed Stop) closes these generators, which closes
    # the HTTP stream to Ollama and stops generation.
    return StreamingResponse(
        _event_stream(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _event_stream(events: AsyncIterator[Event | dict]) -> AsyncIterator[str]:
    """Turn events into SSE frames. Errors become a final "error" event."""
    try:
        async for event in events:
            if isinstance(event, Event):
                event = {"type": event.type, "text": event.text}
            yield _sse(event)
    except OllamaContextError:
        yield _sse({"type": "error", "code": "too_long", "message": TOO_LONG})
        return
    except ProofreadUnavailable:
        yield _sse(
            {
                "type": "error",
                "code": "llm_unavailable",
                "message": PROOFREAD_UNAVAILABLE,
            }
        )
        return
    except OllamaError as exc:
        log.warning("Model request failed: %s", exc)
        yield _sse(
            {"type": "error", "code": "llm_unavailable", "message": LLM_UNAVAILABLE}
        )
        return
    yield _sse({"type": "done"})


@router.post("/summarize")
async def summarize(
    req: SummarizeRequest,
    store: FileStore = Depends(get_store),
    client: OllamaClient = Depends(get_ollama),
    session: dict = Depends(current_session),
) -> StreamingResponse:
    if (req.text is None) == (req.file_id is None):
        raise HTTPException(status_code=400, detail="Send either text or a file id.")

    if req.file_id is not None:
        extracted = _load(store, req.file_id)
    else:
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Please enter some text.")
        extracted = Extracted("text", text=req.text)

    if extracted.kind == "data":
        events = summarize_data(extracted.sheets, client)
    else:
        try:
            check_length(extracted.text)
        except SummaryTooLong as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from None
        events = summarize_text(extracted.text, client)
    return _sse_stream(events)


class RewriteRequest(BaseModel):
    text: str | None = None
    file_id: str | None = None
    style: Literal["formal", "polite"] = "formal"


@router.post("/rewrite")
async def rewrite(
    req: RewriteRequest,
    store: FileStore = Depends(get_store),
    client: OllamaClient = Depends(get_ollama),
    session: dict = Depends(current_session),
) -> StreamingResponse:
    doc, _, _ = _document(store, req.text, req.file_id, "Rewrite")
    return _sse_stream(rewrite_document(doc, req.style, client))


class ProofreadRequest(BaseModel):
    text: str | None = None
    file_id: str | None = None


@router.post("/proofread")
async def proofread(
    req: ProofreadRequest,
    store: FileStore = Depends(get_store),
    client: OllamaClient = Depends(get_ollama),
    lt: LanguageToolClient = Depends(get_languagetool),
    session: dict = Depends(current_session),
) -> StreamingResponse:
    doc, _, cells = _document(store, req.text, req.file_id, "Proofread")
    if cells is None:
        return _sse_stream(proofread_document(doc, client, lt))
    events = proofread_document(doc, client, lt, max_paragraphs=DATA_SECTION_CELLS)
    notice = (
        f"Only text columns were checked ({', '.join(cells.columns)}). Each distinct "
        "value is shown once; an accepted fix is applied to every cell in its column "
        "with that value."
    )
    return _sse_stream(_with_notice(events, notice))


async def _with_notice(events: AsyncIterator[dict], notice: str) -> AsyncIterator[dict]:
    async for event in events:
        if event["type"] == "result":
            event = {**event, "notices": [notice, *event["notices"]]}
        yield event


class AcceptedEdit(BaseModel):
    start: int
    end: int
    replacement: str


class ApplyRequest(BaseModel):
    text: str | None = None
    file_id: str | None = None
    accepted: list[AcceptedEdit]


@router.post("/proofread/apply")
async def proofread_apply(
    req: ApplyRequest,
    store: FileStore = Depends(get_store),
    session: dict = Depends(current_session),
) -> dict:
    doc, stored, cells = _document(store, req.text, req.file_id, "Proofread")
    edits = [(e.start, e.end, e.replacement) for e in req.accepted]
    if stored is not None:
        # Edits inside links or fields, or across paragraphs, cannot go back into a file.
        edits = [e for e in edits if doc.is_applicable(e[0], e[1])]
    try:
        text = apply_to_text(doc.text, edits)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    body: dict = {"text": text, "warnings": []}
    if stored is not None and stored.ext == ".docx":
        located = []
        for start, end, replacement in edits:
            index, s, e = doc.locate(start, end)
            located.append((index, s, e, replacement))
        content, skipped = apply_span_edits(stored.read_bytes(), located)
        name = _derived_name(stored, "proofread", ".docx")
        out = store.save(name, content)
        warnings = list(DOCX_SPAN_WARNINGS)
        if skipped:
            warnings.append(
                f"{skipped} correction(s) could not be applied to the file."
            )
        body.update(file_id=out.id, filename=out.filename, warnings=warnings)
    elif cells is not None:
        body.update(_apply_to_data(store, stored, doc, cells, edits))
    return body


def _apply_to_data(
    store: FileStore,
    stored: StoredFile,
    doc: seg.SegmentedText,
    cells: TextCells,
    edits: list[tuple[int, int, str]],
) -> dict[str, Any]:
    """Write accepted fixes into every cell holding each corrected value."""
    by_segment: dict[int, list[tuple[int, int, str]]] = {}
    for start, end, replacement in edits:
        index, s, e = doc.locate(start, end)
        by_segment.setdefault(index, []).append((s, e, replacement))
    changes: dict[Cell, str] = {}
    for index, local in by_segment.items():
        value = apply_to_text(doc.segments[index].text, local)
        for cell in cells.cells[index]:
            changes[cell] = value

    original = stored.read_bytes()
    try:
        content = write_back(stored.ext, original, changes)
    except CellNotEditable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    out = store.save(_derived_name(stored, "proofread", stored.ext), content)
    warnings = list(DATA_WARNINGS[stored.ext])
    alternatives = []
    if stored.ext == ".xlsx" and has_drawings(original):
        warnings.insert(0, XLSX_DRAWINGS_WARNING)
        for sheet in sorted({c.sheet for c in changes}):
            safe = re.sub(r"[^\w\- ]+", "_", sheet).strip() or "sheet"
            alt = store.save(
                _derived_name(stored, f"{safe}-proofread", ".csv"),
                edited_sheet_csv(original, sheet, changes),
            )
            alternatives.append(
                {
                    "file_id": alt.id,
                    "filename": alt.filename,
                    "label": f"CSV of {sheet}",
                }
            )
    return {
        "file_id": out.id,
        "filename": out.filename,
        "warnings": warnings,
        "alternatives": alternatives,
    }


class ExportRequest(BaseModel):
    text: str
    format: Literal["txt", "docx"]
    source_file_id: str | None = None


@router.post("/export")
async def export(
    req: ExportRequest,
    store: FileStore = Depends(get_store),
    session: dict = Depends(current_session),
) -> dict:
    """Save a result as a downloadable file. A DOCX source is edited in place."""
    stored = _get(store, req.source_file_id) if req.source_file_id else None
    text = req.text.replace("\r\n", "\n")
    warnings: list[str] = []

    if req.format == "txt":
        data = text.encode("utf-8")
        if stored is not None and stored.ext == ".txt":
            original = stored.read_bytes()
            # Spec 5.4: line endings (and a byte-order mark) are kept.
            if b"\r\n" in original:
                data = data.replace(b"\n", b"\r\n")
            if original.startswith(b"\xef\xbb\xbf"):
                data = b"\xef\xbb\xbf" + data
        name = _derived_name(stored, "edited", ".txt")
    elif stored is not None and stored.ext == ".docx":
        original = stored.read_bytes()
        doc = seg.from_docx(original)
        paragraphs = seg.split_blocks(text)
        if len(paragraphs) != len(doc.segments):
            raise HTTPException(
                status_code=422,
                detail=f"The original document has {len(doc.segments)} paragraphs but the "
                f"edited text has {len(paragraphs)}. To save into the original Word file, "
                "keep one blank line between paragraphs and do not add or remove "
                "paragraphs. Or download a new Word document instead.",
            )
        changed = {
            i: new
            for i, (new, old) in enumerate(zip(paragraphs, doc.segments))
            if not same_words(new, old.text)
        }
        # The user may edit formalities by hand; only tables and links cannot be saved.
        locked = [i for i in changed if not doc.segments[i].replaceable]
        data = replace_paragraphs(
            original, {i: t for i, t in changed.items() if i not in locked}
        )
        warnings = list(DOCX_REWRITE_WARNINGS)
        if locked:
            warnings.append(
                f"{len(locked)} edited paragraph(s) in tables or with links could not "
                "be saved into the file."
            )
        name = _derived_name(stored, "edited", ".docx")
    else:
        data = new_docx(text)
        warnings = list(NEW_DOCX_WARNINGS) if stored is not None else []
        name = _derived_name(stored, "edited", ".docx")

    out = store.save(name, data)
    return {"file_id": out.id, "filename": out.filename, "warnings": warnings}


class ChatTurn(BaseModel):
    question: str
    operation: dict[str, Any] | None = None
    answer: str | None = None


class AskRequest(BaseModel):
    file_id: str
    question: str
    history: list[ChatTurn] = Field(default_factory=list)


@router.post("/data/ask")
async def data_ask(
    req: AskRequest,
    store: FileStore = Depends(get_store),
    client: OllamaClient = Depends(get_ollama),
    session: dict = Depends(current_session),
) -> StreamingResponse:
    """One chat turn about a data file. The browser keeps the conversation and sends the
    earlier turns each time; the server keeps no chat state."""
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please type a question.")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Please keep the question under {MAX_QUESTION_CHARS:,} characters.",
        )
    stored = _get(store, req.file_id)
    if stored.ext not in DATA_TYPES:
        raise HTTPException(status_code=422, detail=NOT_DATA)
    extracted = _load(store, req.file_id)
    history = [t.model_dump() for t in req.history]
    return _sse_stream(ask(extracted.sheets, question, history, client))


@router.get("/download/{file_id}")
async def download(
    file_id: str,
    store: FileStore = Depends(get_store),
    session: dict = Depends(current_session),
) -> FileResponse:
    stored = _get(store, file_id)
    return FileResponse(
        stored.path,
        filename=stored.filename,
        media_type=MEDIA_TYPES.get(stored.ext, "application/octet-stream"),
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    store: FileStore = Depends(get_store),
    session: dict = Depends(require_admin),
) -> Response:
    store.delete(file_id)
    return Response(status_code=204)
