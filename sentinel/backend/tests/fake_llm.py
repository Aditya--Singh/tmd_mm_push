"""A tiny OpenAI-compatible server used to exercise the LLM code paths offline.

    uvicorn tests.fake_llm:app --port 9911
then run the backend with LLM_PROVIDER=openai_compat LLM_BASE_URL=http://127.0.0.1:9911/v1
"""
import json
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()


def _reply(system: str, user: str) -> str:
    if "Router agent" in system:
        msg = user.split("Latest user message:")[-1].strip()
        low = msg.lower()
        intent = "qa"
        if "remember" in low:
            intent = "remember"
        elif "summar" in low:
            intent = "summarize"
        elif "email" in low:
            intent = "email"
        elif "new" in low or "latest" in low:
            intent = "latest"
        return json.dumps({"intent": intent, "standalone_query": msg, "circular_ref": None, "since_days": None,
                           "source": None, "email_content": "digest" if intent == "email" else None,
                           "recipient": None, "memory_note": msg if intent == "remember" else None, "reason": "fake"})
    if "Summarizer agent" in system:
        title = re.search(r"Title: (.*)", user)
        return json.dumps({"headline": (title.group(1) if title else "Circular")[:80], "summary": "The RBI has issued instructions summarised by the fake model.",
                           "key_points": ["Point one from the document.", "Point two from the document."], "action_items": ["Review and comply."],
                           "effective_date": None, "deadline": None, "applicability": {"verdict": "Applicable", "reason": "Addressed to commercial banks."},
                           "priority": "High", "priority_reason": "fake", "tags": ["Test"], "impacted_functions": ["Compliance"]})
    if "Answer agent" in system:
        m = re.search(r"\[1\] .*?\n(.+?)(?:\n\n\[2\]|\n\nQUESTION)", user, re.S)
        src = (m.group(1) if m else "").strip()
        first = re.split(r"(?<=\.)\s", src)[0][:300]
        return f"According to the indexed directions, {first} [1]\n\n- This applies at all times as stated in the source [1]."
    if "Briefing agent" in system:
        return "Several RBI publications were issued this week; the sanctions list update needs immediate screening [1]."
    if "Memory agent" in system:
        return "User asked about leverage ratio and KYC sanctions updates."
    return "Hello! I can answer questions about RBI circulars."


@app.post("/v1/chat/completions")
async def completions(req: Request):
    body = await req.json()
    system = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
    user = body["messages"][-1]["content"]
    text = _reply(system, user)
    if not body.get("stream"):
        return JSONResponse({"id": "x", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": len(str(body["messages"])) // 4, "completion_tokens": len(text) // 4, "total_tokens": 0}})

    async def gen():
        for word in re.findall(r"\S+\s*", text):
            chunk = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                     "choices": [{"index": 0, "delta": {"content": word}, "finish_reason": None}]}
            yield f"data: {json.dumps(chunk)}\n\n"
        if (body.get("stream_options") or {}).get("include_usage"):
            yield "data: " + json.dumps({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": body["model"], "choices": [],
                                         "usage": {"prompt_tokens": 500, "completion_tokens": len(text) // 4, "total_tokens": 0}}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/embeddings")
async def embeddings(req: Request):
    """Deterministic 64-d vectors so the OpenAI-compatible embedding path can be exercised offline."""
    import hashlib

    body = await req.json()
    inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
    data = []
    for i, text in enumerate(inputs):
        vec = [0.0] * 64
        for w in str(text).lower().split():
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            vec[h % 64] += 1.0
        data.append({"object": "embedding", "index": i, "embedding": vec})
    return {"object": "list", "data": data, "model": body.get("model"), "usage": {"prompt_tokens": 0, "total_tokens": 0}}


# Ollama's own endpoints, so scripts/check.py can be tried against this fake server
@app.get("/api/tags")
def tags():
    return {"models": [{"name": "gpt-oss:20b"}, {"name": "bge-m3:latest"}]}


@app.get("/api/ps")
def ps():
    return {"models": [{"name": "gpt-oss:20b", "size": 14_000_000_000, "size_vram": 14_000_000_000}]}
