"""Notifier agent: composes and sends alert, digest and on-demand e-mails over SMTP.

With no SMTP password configured, e-mails are not sent; they are written to data/outbox/*.eml ("dry_run") so the
whole flow can still be demonstrated and audited.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.config import get_settings
from app.core.db import session_scope
from app.core.models import Circular, EmailLog, utcnow
from app.core.utils import as_utc
from app.observability import audit
from app.observability.tracer import tracer

log = logging.getLogger("sentinel.notifier")

# PNB brand palette (adjust here if the bank's brand guide specifies different values)
NAVY, GOLD, MAROON, INK, MUTED, PAPER = "#8E1B33", "#F2A900", "#B42318", "#23181B", "#6B5F63", "#F6F4F5"
DEEP = "#5E0F21"
TYPE_LABELS = {"notification": "Notification", "press_release": "Press release",
               "master_circular": "Master Circular", "master_direction": "Master Direction"}


def type_label(source: str) -> str:
    return TYPE_LABELS.get(source, source.replace("_", " ").title())
PRIO_COLORS = {"High": MAROON, "Medium": "#8A6D12", "Low": "#3D5A80"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _e(s: str | None) -> str:
    return html.escape(s or "")


def _fmt_date(dt: datetime | None) -> str:
    if not dt:
        return "-"
    return as_utc(dt).astimezone(timezone.utc).strftime("%d %b %Y")


def _shell(title: str, body: str, trace_id: str | None) -> str:
    s = get_settings()
    return f"""<!doctype html><html><body style="margin:0;background:{PAPER};font-family:Segoe UI,Arial,sans-serif;color:{INK}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER};padding:24px 0">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;background:#ffffff;border:1px solid #DDE1E7">
<tr><td style="background:{DEEP};padding:18px 28px;color:#fff">
  <div style="font-family:Georgia,serif;font-size:20px;letter-spacing:.2px">{_e(s.org_short)} Regulatory Sentinel</div>
  <div style="font-size:12px;color:#F3D9DF;margin-top:2px">{_e(title)} &nbsp;|&nbsp; {_e(s.org_name)}</div>
</td></tr>
<tr><td style="height:3px;background:{GOLD}"></td></tr>
<tr><td style="padding:24px 28px">{body}</td></tr>
<tr><td style="padding:16px 28px;border-top:1px solid #E6E9EE;font-size:11px;color:{MUTED};line-height:1.5">
  Summaries are generated automatically by AI agents and may contain errors. Always read the original RBI document
  before acting on it. Sent by {_e(s.email_from_name)} &lt;{_e(s.email_from)}&gt;.
  {f'<br>Trace ID: <span style="font-family:Consolas,monospace">{_e(trace_id)}</span> (open it under Agent traces to see every agent step).' if trace_id else ''}
</td></tr>
</table></td></tr></table></body></html>"""


def _chip(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 8px;border:1px solid {color};color:{color};'
        f'font-size:11px;border-radius:3px;margin-right:6px">{_e(text)}</span>'
    )


def _circular_block(c: Circular, full: bool = True) -> str:
    s = get_settings()
    sm = c.summary or {}
    prio = sm.get("priority") or c.priority
    applic = (sm.get("applicability") or {}).get("verdict") or c.applicability
    reason = (sm.get("applicability") or {}).get("reason", "")
    refs = " / ".join(x for x in [c.rbi_ref, c.dept_ref] if x) or "-"
    lis = lambda items: "".join(f'<li style="margin:0 0 6px">{_e(i)}</li>' for i in items)  # noqa: E731
    parts = [
        f'<div style="margin-bottom:6px">{_chip(prio + " priority", PRIO_COLORS.get(prio, NAVY))}{_chip(applic, NAVY)}'
        f'{_chip(type_label(c.source), MUTED)}{_chip("Updated by RBI", GOLD) if c.revision else ""}</div>',
        f'<div style="font-family:Georgia,serif;font-size:18px;line-height:1.35;margin:8px 0 4px">'
        f'<a href="{_e(c.url)}" style="color:{NAVY};text-decoration:none">{_e(c.title)}</a></div>',
        f'<div style="font-size:12px;color:{MUTED};margin-bottom:12px">{_e(refs)} &nbsp;|&nbsp; {_fmt_date(c.published_at)}'
        f'{" &nbsp;|&nbsp; " + _e(c.department) if c.department else ""}</div>',
    ]
    if sm.get("summary"):
        parts.append(f'<p style="font-size:14px;line-height:1.6;margin:0 0 12px">{_e(sm["summary"])}</p>')
    if full and sm.get("key_points"):
        parts.append(f'<div style="font-weight:600;font-size:13px;margin-top:10px">Key points</div><ul style="font-size:13px;line-height:1.5;padding-left:18px">{lis(sm["key_points"])}</ul>')
    if full and sm.get("action_items"):
        parts.append(
            f'<div style="background:#FBF6E6;border-left:3px solid {GOLD};padding:10px 14px;margin:10px 0">'
            f'<div style="font-weight:600;font-size:13px">Action for the bank</div>'
            f'<ul style="font-size:13px;line-height:1.5;padding-left:18px;margin:6px 0 0">{lis(sm["action_items"])}</ul></div>'
        )
    if full and (sm.get("effective_date") or reason):
        parts.append(
            f'<div style="font-size:12px;color:{MUTED};margin-top:8px">'
            f'{"Effective: " + _e(sm.get("effective_date")) + " &nbsp;|&nbsp; " if sm.get("effective_date") else ""}'
            f'Applicability: {_e(reason)}</div>'
        )
    links = [f'<a href="{_e(c.url)}" style="color:{NAVY}">Read on rbi.org.in</a>']
    if c.pdf_url:
        links.append(f'<a href="{_e(c.pdf_url)}" style="color:{NAVY}">PDF</a>')
    links.append(f'<a href="{_e(s.public_url)}/circulars/{c.id}" style="color:{NAVY}">Open in Sentinel</a>')
    parts.append(f'<div style="font-size:13px;margin-top:14px">{" &nbsp;·&nbsp; ".join(links)}</div>')
    return "".join(parts)


def _circular_text(c: Circular) -> str:
    sm = c.summary or {}
    lines = [("[Updated] " if c.revision else "") + c.title, type_label(c.source), f"{c.rbi_ref or ''} {c.dept_ref or ''}".strip(), f"Priority: {sm.get('priority', c.priority)}",
             f"Applicability: {(sm.get('applicability') or {}).get('verdict', c.applicability)}", "", sm.get("summary", "")]
    if sm.get("action_items"):
        lines += ["", "Action for the bank:"] + [f"- {a}" for a in sm["action_items"]]
    lines += ["", f"Original: {c.url}"]
    return "\n".join(lines)


def compose_alert(c: Circular, trace_id: str | None) -> tuple[str, str, str]:
    prio = (c.summary or {}).get("priority") or c.priority
    what = "Updated" if c.revision else "New"
    subject = f"[RBI {type_label(c.source)}][{what}][{prio}] {c.title}"[:250]
    heading = "RBI has updated a document" if c.revision else "New publication from the Reserve Bank of India"
    return subject, _shell(heading, _circular_block(c), trace_id), _circular_text(c)


def compose_digest(circs: list[Circular], trace_id: str | None, heading: str | None = None) -> tuple[str, str, str]:
    order = {"High": 0, "Medium": 1, "Low": 2}
    circs = sorted(circs, key=lambda c: (order.get(c.priority, 3), -(as_utc(c.published_at) or utcnow()).timestamp()))
    high = sum(1 for c in circs if c.priority == "High")
    subject = f"[RBI Digest] {len(circs)} new publication{'s' if len(circs) != 1 else ''}" + (f" - {high} high priority" if high else "")
    rows = "".join(
        f'<div style="padding:16px 0;border-bottom:1px solid #E6E9EE">{_circular_block(c, full=c.priority == "High")}</div>'
        for c in circs
    )
    intro = f'<p style="font-size:14px;margin:0 0 8px">{_e(heading or "The following RBI publications were detected and indexed.")}</p>'
    text = "\n\n----\n\n".join(_circular_text(c) for c in circs)
    return subject, _shell("Digest of new RBI publications", intro + rows, trace_id), text


def compose_answer(question: str, answer_md: str, sources: list[dict], trace_id: str | None) -> tuple[str, str, str]:
    paras = "".join(f'<p style="font-size:14px;line-height:1.6;margin:0 0 10px">{_e(p)}</p>' for p in answer_md.split("\n\n") if p.strip())
    src = "".join(
        f'<li style="margin-bottom:4px">[{s.get("n")}] <a href="{_e(s.get("url"))}" style="color:{NAVY}">{_e(s.get("title"))}</a> {_e(s.get("rbi_ref") or "")}</li>'
        for s in sources
    )
    body = (
        f'<div style="font-size:12px;color:{MUTED}">Your question</div>'
        f'<div style="font-family:Georgia,serif;font-size:17px;margin:4px 0 16px">{_e(question)}</div>{paras}'
        + (f'<div style="font-weight:600;font-size:13px;margin-top:14px">Sources</div><ul style="font-size:13px;padding-left:18px">{src}</ul>' if src else "")
    )
    subject = f"[RBI Sentinel] {question[:120]}"
    text = f"Q: {question}\n\n{answer_md}\n\nSources:\n" + "\n".join(f"[{s.get('n')}] {s.get('title')} {s.get('url')}" for s in sources)
    return subject, _shell("Answer from the Regulatory Sentinel assistant", body, trace_id), text


def _smtp_send(msg: EmailMessage) -> None:
    s = get_settings()
    ctx = ssl.create_default_context()
    if s.smtp_port == 465:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ctx, timeout=30) as server:
            server.login(s.smtp_username, s.smtp_password)
            server.send_message(msg)
        return
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as server:
        server.ehlo()
        if s.smtp_use_starttls:
            server.starttls(context=ctx)
            server.ehlo()
        if s.smtp_username and s.smtp_password:
            server.login(s.smtp_username, s.smtp_password)
        server.send_message(msg)


async def send_email(
    kind: str,
    recipients: list[str],
    subject: str,
    html_body: str,
    text_body: str,
    *,
    circular_ids: list[int] | None = None,
    triggered_by: str = "system",
    enabled: bool = True,
) -> dict:
    s = get_settings()
    recipients = [r for r in dict.fromkeys(r.strip() for r in recipients) if EMAIL_RE.match(r)]
    async with tracer.span(
        "Notifier", f"send {kind} e-mail", input={"to": recipients, "subject": subject, "circular_ids": circular_ids}
    ) as sp:
        status, error = "sent", None
        if not recipients:
            status, error = "failed", "no valid recipients"
        elif not (s.email_enabled and enabled):
            status = "disabled"
        else:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = formataddr((s.email_from_name, s.email_from))
            msg["To"] = ", ".join(recipients)
            msg["Message-ID"] = make_msgid(domain="rbi-sentinel.local")
            msg["X-Sentinel-Trace"] = sp.trace_id
            msg.set_content(text_body)
            msg.add_alternative(html_body, subtype="html")
            if s.smtp_dry_run:
                status = "dry_run"
                path = s.data_dir / "outbox" / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}-{sp.id[:8]}.eml"
                path.write_bytes(bytes(msg))
                sp.set(outbox_file=str(path))
            else:
                try:
                    await asyncio.to_thread(_smtp_send, msg)
                except Exception as exc:
                    status, error = "failed", f"{type(exc).__name__}: {exc}"
                    sp.status = "error"
        with session_scope() as db:
            db.add(
                EmailLog(
                    kind=kind,
                    recipients=recipients,
                    subject=subject,
                    status=status,
                    error=error,
                    circular_ids=circular_ids,
                    trace_id=sp.trace_id,
                    triggered_by=triggered_by,
                )
            )
            if circular_ids and status in ("sent", "dry_run"):
                for c in db.query(Circular).filter(Circular.id.in_(circular_ids)).all():
                    c.notified_at = utcnow()
                    if kind in ("alert", "digest"):
                        c.status = "notified"
        audit.record(
            triggered_by,
            "email.send",
            resource=f"email:{kind}",
            details={"to": recipients, "subject": subject, "status": status, "error": error, "circular_ids": circular_ids},
        )
        sp.output = {"status": status, "error": error, "recipients": recipients}
        if status == "failed":
            log.error("e-mail failed", extra={"kind": kind, "error": error})
        else:
            log.info("e-mail %s", status, extra={"kind": kind, "to": recipients})
        return {"status": status, "error": error, "recipients": recipients}
