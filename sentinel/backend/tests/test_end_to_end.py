"""End-to-end test of the whole application against local RSS fixtures (no network, no LLM)."""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

ADMIN = {"email": "sireejaa.uppal@pnb.bank.in", "password": "Test@Pass123"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def stream_chat(client, auth, message, conversation_id=None):
    events = []
    with client.stream("POST", "/api/chat/stream", json={"message": message, "conversation_id": conversation_id}, headers=auth) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={**ADMIN, "password": "wrong"})
    assert r.status_code == 401


def test_requires_auth(client):
    assert client.get("/api/circulars").status_code == 401


def test_sync_ingests_and_notifies(client, auth):
    r = client.post("/api/sync", headers=auth)
    assert r.json()["status"] in ("started", "running")
    for _ in range(100):
        st = client.get("/api/sync/status", headers=auth).json()
        if not st["running"] and st["last_result"]:
            break
        time.sleep(0.2)
    res = st["last_result"]
    # 3 notifications + 1 press release + 4 master circulars (2 this year, 2 from 2025-26 via the year links) + 3 directions
    assert res["ingested"] == 11, res
    assert all(f["ok"] for f in res["feeds"]), res["feeds"]
    assert res["notification"]["status"] == "sent"

    items = client.get("/api/circulars", headers=auth).json()["items"]
    by_ref = {c["rbi_ref"]: c for c in items}
    uapa = by_ref["RBI/2026-27/302"]
    assert uapa["dept_ref"].startswith("DoR.AML")
    assert uapa["priority"] == "High"
    assert uapa["applicability"] == "Applicable"
    assert uapa["summary"]["action_items"], "extractive summary should find action sentences"
    pr = [c for c in items if c["source"] == "press_release"][0]
    if os.environ.get("LLM_PROVIDER") == "none":  # rules-only mode
        assert pr["applicability"] == "Informational"
    else:
        assert "llm" in uapa["summary"]["generated_by"]

    emails = client.get("/api/emails", headers=auth).json()
    assert emails and all(e["status"] == "dry_run" for e in emails)
    assert "sireejaa.uppal@pnb.bank.in" in emails[0]["recipients"]

    # second sync finds nothing new (idempotent)
    client.post("/api/sync", headers=auth)
    for _ in range(100):
        st = client.get("/api/sync/status", headers=auth).json()
        if not st["running"]:
            break
        time.sleep(0.2)
    assert st["last_result"]["ingested"] == 0


def test_chat_qa_with_citations_and_trace(client, auth):
    ev = stream_chat(client, auth, "What is the minimum leverage ratio for a D-SIB?")
    types = [e["type"] for e in ev]
    assert types[0] == "meta" and types[-1] == "done", types
    agents = [e["agent"] for e in ev if e["type"] == "step" and e["status"] == "done"]
    assert agents[:4] == ["Memory", "Router", "Retriever", "Verifier"] or "Retriever" in agents
    sources = next(e for e in ev if e["type"] == "sources")["items"]
    assert any("Leverage" in s["text"] or "leverage" in s["text"] for s in sources[:3])
    trace_id = ev[-1]["trace_id"]
    t = client.get(f"/api/traces/{trace_id}", headers=auth).json()
    assert {s["agent"] for s in t["spans"]} >= {"Memory", "Router", "Retriever", "Verifier"}
    assert t["status"] == "ok"

    conv_id = ev[0]["conversation_id"]
    # follow-up in the same conversation keeps memory
    ev2 = stream_chat(client, auth, "remember that I work in the compliance department", conv_id)
    assert ev2[-1]["intent"] == "remember"
    mem = client.get("/api/memory", headers=auth).json()
    assert any("compliance" in n["content"] for n in mem["notes"])

    # feedback on the answer
    r = client.post("/api/feedback", json={"message_id": ev[-1]["message_id"], "rating": 1, "tags": ["helpful"]}, headers=auth)
    assert r.status_code == 200
    fb = client.get("/api/feedback", headers=auth).json()
    assert fb["stats"]["positive"] == 1


def test_chat_email_and_policy(client, auth):
    ev = stream_chat(client, auth, "Send me today's digest by email")
    done = ev[-1]
    assert done["intent"] == "email"
    assert done["actions"][0]["status"] == "dry_run"
    blocked = stream_chat(client, auth, "email the answer to outsider@example.com")
    text = "".join(e.get("text", "") for e in blocked if e["type"] in ("replace", "token"))
    assert "only e-mail registered users" in text


def test_summarize_and_latest(client, auth):
    ev = stream_chat(client, auth, "Summarise RBI/2026-27/300")
    text = next(e["text"] for e in ev if e["type"] == "replace")
    assert "Lead Bank" in text
    ev = stream_chat(client, auth, "what's new this week?")
    assert ev[-1]["intent"] == "latest"


def test_dashboard_settings_and_audit_chain(client, auth):
    d = client.get("/api/dashboard", headers=auth).json()
    assert d["kpis"]["indexed"] == 11
    assert d["kpis"]["master_documents"] == 7
    assert {c["source"] for c in d["coverage"]} == {"notification", "press_release", "master_circular", "master_direction"}
    assert any(a["name"] == "Watcher" and a["runs_24h"] > 0 for a in d["agents"])

    r = client.put("/api/settings", json={"subscribers": ["sireejaa.uppal@pnb.bank.in", "team@pnb.bank.in"]}, headers=auth)
    assert r.status_code == 200 and "team@pnb.bank.in" in r.json()["subscribers"]
    assert client.post("/api/settings/test-email", headers=auth).json()["status"] == "dry_run"

    v = client.get("/api/audit/verify", headers=auth).json()
    assert v["intact"] and v["verified"] > 5

    # tamper with history -> chain must break at that row
    from app.core.db import session_scope
    from app.core.models import AuditEvent

    with session_scope() as db:
        row = db.query(AuditEvent).order_by(AuditEvent.id).offset(2).first()
        row.actor = "attacker@example.com"
        tampered = row.id
    v = client.get("/api/audit/verify", headers=auth).json()
    assert not v["intact"] and v["broken_at_id"] == tampered


def test_logs_have_trace_ids(client, auth):
    logs = client.get("/api/logs", headers=auth).json()
    assert any(l.get("trace_id") for l in logs)


def wait_sync(client, auth):
    client.post("/api/sync", headers=auth)
    for _ in range(150):
        st = client.get("/api/sync/status", headers=auth).json()
        if not st["running"] and st["last_result"]:
            return st["last_result"]
        time.sleep(0.2)
    raise AssertionError("sync did not finish")


def test_master_documents_metadata(client, auth):
    items = client.get("/api/circulars?source=master_circular", headers=auth).json()["items"]
    by_title = {c["title"][:40]: c for c in items}
    sc = next(c for c in items if "Scheduled Castes" in c["title"])
    assert sc["listing_group"] == "Financial Inclusion and Development"
    assert sc["published_at"].startswith("2026-10-01")
    assert sc["pdf_url"].startswith("https://rbidocs.rbi.org.in/")
    assert sc["applicability"] == "Applicable"
    ucb = next(c for c in items if "UCBs" in c["title"])
    assert ucb["applicability"] == "Not applicable" and ucb["priority"] == "Low"
    md = client.get("/api/circulars?source=master_direction", headers=auth).json()["items"]
    cva = next(c for c in md if "Credit Valuation" in c["title"])
    assert cva["priority"] == "High" and cva["rbi_ref"] == "RBI/DOR/2026-27/474"
    detail = client.get(f"/api/circulars/{cva['id']}", headers=auth).json()
    assert "mark-to-market" in detail["text"]
    # the assistant can answer from a master direction
    ev = stream_chat(client, auth, "Within how many days is a term loan classified as NPA under the master direction?")
    sources = next(e for e in ev if e["type"] == "sources")["items"]
    assert sources and sources[0]["source"] == "master_direction"
    assert "90 days" in sources[0]["text"]


def test_revised_master_direction_is_reingested_and_alerted(client, auth):
    from conftest import PAGES

    page = PAGES / "md_list.html"
    page.write_text(page.read_text().replace(
        "Credit Valuation Adjustment Framework) Directions, 2026</a>",
        "Credit Valuation Adjustment Framework) Directions, 2026 (Updated as on November 10, 2026)</a>"))
    before = len(client.get("/api/emails", headers=auth).json())
    res = wait_sync(client, auth)
    assert res["revised_items"] == 1 and res["ingested"] == 1, res
    cva = next(c for c in client.get("/api/circulars?revised=true", headers=auth).json()["items"])
    assert cva["revision"] == 1 and "Updated as on" in cva["title"]
    emails = client.get("/api/emails", headers=auth).json()
    assert len(emails) == before + 1 and "[Updated]" in emails[0]["subject"]


def test_all_financial_years_and_superseded_versions(client, auth):
    items = client.get("/api/circulars?source=master_circular", headers=auth).json()["items"]
    years = {c["financial_year"] for c in items}
    assert {"2026-2027", "2025-2026"} <= years
    sc = [c for c in items if "Scheduled Castes" in c["title"]]
    assert len(sc) == 2
    old = next(c for c in sc if c["financial_year"] == "2025-2026")
    new = next(c for c in sc if c["financial_year"] == "2026-2027")
    assert old["superseded_by"] == new["id"] and new["superseded_by"] is None
    # chat over all circulars ignores the superseded copy unless asked
    ev = stream_chat(client, auth, "credit facilities to scheduled castes and scheduled tribes quarterly review")
    ids = {s["circular_id"] for s in next(e for e in ev if e["type"] == "sources")["items"]}
    assert old["id"] not in ids
    events = []
    with client.stream("POST", "/api/chat/stream", headers=auth, json={
            "message": "credit facilities to scheduled castes old arrangement quarterly", "include_older": True}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    ids = {s["circular_id"] for s in next(e for e in events if e["type"] == "sources")["items"]}
    assert old["id"] in ids


def test_scoped_chat_and_per_circular_summary(client, auth):
    md = client.get("/api/circulars?source=master_direction", headers=auth).json()["items"]
    cva = next(c for c in md if "Credit Valuation" in c["title"])
    events = []
    with client.stream("POST", "/api/chat/stream", headers=auth, json={"message": "what is new?", "circular_id": cva["id"]}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    sources = next(e for e in events if e["type"] == "sources")["items"]
    assert sources and {s["circular_id"] for s in sources} == {cva["id"]}
    out = client.post(f"/api/circulars/{cva['id']}/summarize", headers=auth).json()
    assert out["summary"]


def test_login_and_email_can_be_switched_off(client):
    from app.config import get_settings

    s = get_settings()
    s.auth_enabled, s.email_enabled = False, False
    try:
        assert client.get("/api/circulars").status_code == 200  # no token needed
        me = client.get("/api/auth/me").json()
        assert me["email"] == "sireejaa.uppal@pnb.bank.in" and not me["must_change_password"]
        meta = client.get("/api/meta").json()
        assert meta["auth_enabled"] is False and meta["email_enabled"] is False
        events = []
        with client.stream("POST", "/api/chat/stream", json={"message": "email me this week's digest"}) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        text = "".join(e.get("text", "") for e in events if e["type"] == "replace")
        assert "switched off" in text
        assert "frame-ancestors" in client.get("/api/meta").headers["content-security-policy"]
    finally:
        s.auth_enabled, s.email_enabled = True, True
