"""Conversations, streaming chat (Server-Sent Events) and user memory."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.chat import run_chat
from app.api.deps import client_ip, current_user
from app.core.db import get_db
from app.core.models import Conversation, MemoryNote, Message, User
from app.core.utils import iso
from app.observability import audit

router = APIRouter(prefix="/api", tags=["chat"])


def msg_out(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "citations": m.citations or [],
        "meta": m.meta or {},
        "trace_id": m.trace_id,
        "created_at": iso(m.created_at),
    }


@router.get("/conversations")
def list_conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(100).all()
    return [{"id": c.id, "title": c.title, "updated_at": iso(c.updated_at), "has_summary": bool(c.summary)} for c in rows]


@router.get("/conversations/{cid}")
def get_conversation(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Conversation not found.")
    return {"id": c.id, "title": c.title, "summary": c.summary, "messages": [msg_out(m) for m in c.messages]}


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.patch("/conversations/{cid}")
def rename_conversation(cid: int, body: RenameIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Conversation not found.")
    c.title = body.title
    return {"ok": True}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Conversation not found.")
    db.delete(c)
    db.commit()
    audit.record(user.email, "conversation.delete", resource=f"conversation:{cid}", ip=client_ip(request))
    return {"ok": True}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    circular_id: int | None = None  # limit the conversation turn to one circular
    include_older: bool = False  # also search superseded yearly versions of master circulars


@router.post("/chat/stream")
async def chat_stream(body: ChatIn, request: Request, user: User = Depends(current_user)):
    ip = client_ip(request)

    async def gen():
        try:
            async for event in run_chat(user, body.conversation_id, body.message.strip(), ip=ip, scope_id=body.circular_id, include_older=body.include_older):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:  # pragma: no cover - last line of defence
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/memory")
def get_memory(user: User = Depends(current_user), db: Session = Depends(get_db)):
    notes = db.query(MemoryNote).filter(MemoryNote.user_id == user.id).order_by(MemoryNote.id.desc()).all()
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id, Conversation.summary != "")
        .order_by(Conversation.updated_at.desc())
        .limit(20)
        .all()
    )
    return {
        "notes": [{"id": n.id, "content": n.content, "created_at": iso(n.created_at)} for n in notes],
        "conversation_summaries": [{"conversation_id": c.id, "title": c.title, "summary": c.summary} for c in convs],
    }


class NoteIn(BaseModel):
    content: str = Field(min_length=2, max_length=500)


@router.post("/memory")
def add_note(body: NoteIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = MemoryNote(user_id=user.id, content=body.content.strip())
    db.add(n)
    db.commit()
    audit.record(user.email, "memory.save", resource=f"memory:{n.id}", details={"note": n.content[:200]}, ip=client_ip(request))
    return {"id": n.id, "content": n.content, "created_at": iso(n.created_at)}


@router.delete("/memory/{nid}")
def delete_note(nid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.get(MemoryNote, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Note not found.")
    db.delete(n)
    db.commit()
    audit.record(user.email, "memory.delete", resource=f"memory:{nid}", ip=client_ip(request))
    return {"ok": True}
