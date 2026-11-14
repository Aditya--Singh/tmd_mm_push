"""Readers for RBI listing pages that have no RSS feed: Master Circulars and Master Directions.

    Master Circulars   https://rbi.org.in/Scripts/BS_ViewMasterCirculardetails.aspx   (detail: BS_ViewMasCirculardetails.aspx?id=N)
    Master Directions  https://rbi.org.in/Scripts/BS_ViewMasterDirections.aspx         (detail: BS_ViewMasDirections.aspx?id=N)

Both pages are tables that read top to bottom as:

    <department heading row>        e.g. "Financial Inclusion and Development", "Commercial Banks"
    <date row>                      e.g. "Oct 01, 2026"
    <document row>                  title link to the detail page + PDF link + size
    <document row> ...

The parser does not depend on CSS classes or ids. It walks the innermost table rows in document order, remembers
the latest heading and date, and emits one item per row that links to a detail page. If RBI changes the layout,
the Watcher span reports "0 entries parsed" instead of failing silently.

Earlier financial years of Master Circulars are loaded by the page's own script. We try the standard ASP.NET
mechanisms (a __doPostBack target, or a hidden "year" field submitted with the form) and record in the trace
exactly what was found, so the behaviour on the live site is visible and adjustable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

log = logging.getLogger("sentinel.rbi_pages")
IST = timezone(timedelta(hours=5, minutes=30))

DETAIL_PATTERNS = {
    "master_circular": re.compile(r"BS_ViewMasCirculardetails\.aspx\?id=(\d+)", re.I),
    "master_direction": re.compile(r"BS_ViewMasDirections\.aspx\?id=(\d+)", re.I),
}
SHORT_DATE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),\s*(\d{4})$", re.I
)
YEAR_LABEL = re.compile(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$")
POSTBACK = re.compile(r"__doPostBack\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")
JS_CALL = re.compile(r"([A-Za-z_]\w*)\s*\(([^)]*)\)")


def parse_date(text: str) -> datetime | None:
    m = SHORT_DATE.match(text.strip())
    if not m:
        return None
    mon = m.group(1)[:3].title()
    try:
        d = datetime.strptime(f"{mon} {int(m.group(2)):02d} {m.group(3)}", "%b %d %Y")
    except ValueError:
        return None
    return d.replace(hour=12, tzinfo=IST).astimezone(timezone.utc)


def _leaf_rows(soup: BeautifulSoup) -> list[Tag]:
    return [tr for tr in soup.find_all("tr") if not tr.find("tr")]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_listing(html: str, base_url: str, source: str) -> list[dict]:
    """Return [{guid, rbi_id, title, link, pdf_url, published_at, listing_group}] in page order."""
    pattern = DETAIL_PATTERNS[source]
    soup = BeautifulSoup(html, "lxml")
    items: list[dict] = []
    seen: set[str] = set()
    group: str | None = None
    date: datetime | None = None

    rows = _leaf_rows(soup)
    for tr in rows:
        anchors = [a for a in tr.find_all("a", href=True) if pattern.search(a["href"])]
        if not anchors:
            text = _clean(tr.get_text(" "))
            if not text:
                continue
            d = parse_date(text)
            if d:
                date = d
            elif len(text) <= 140 and not YEAR_LABEL.match(text) and "No Master" not in text:
                group, date = text, None
            continue
        a = anchors[0]
        rid = pattern.search(a["href"]).group(1)
        if rid in seen:
            continue
        seen.add(rid)
        title = _clean(a.get_text(" ")) or _clean(tr.get_text(" "))
        pdf = None
        for other in tr.find_all("a", href=True):
            if other["href"].lower().split("?")[0].endswith(".pdf"):
                pdf = urljoin(base_url, other["href"]).replace("http://rbidocs", "https://rbidocs")
                break
        items.append(
            {
                "guid": f"{source}:{rid}",
                "rbi_id": rid,
                "title": title,
                "link": urljoin(base_url, a["href"]),
                "pdf_url": pdf,
                "published_at": date,
                "listing_group": group,
            }
        )

    if not items:  # layout without tables: fall back to any matching links on the page
        for a in soup.find_all("a", href=True):
            m = pattern.search(a["href"])
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                items.append({"guid": f"{source}:{m.group(1)}", "rbi_id": m.group(1), "title": _clean(a.get_text(" ")),
                              "link": urljoin(base_url, a["href"]), "pdf_url": None, "published_at": None, "listing_group": None})
    return items


def _form_fields(soup: BeautifulSoup) -> dict[str, str]:
    form = soup.find("form")
    fields: dict[str, str] = {}
    if not form:
        return fields
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name or inp.get("type", "").lower() in ("submit", "button", "image", "checkbox", "radio"):
            continue
        fields[name] = inp.get("value", "")
    return fields


def discover_year_requests(html: str, base_url: str, years: int) -> tuple[list[dict], dict]:
    """Work out how the page loads earlier years. Returns (requests to make, diagnostic info for the trace)."""
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a"):
        if YEAR_LABEL.match(a.get_text(" ")):
            links.append(a)
    diag: dict = {"year_links_found": len(links), "method": None}
    if not links or years <= 0:
        diag["method"] = "none (no year links)" if not links else "disabled"
        return [], diag

    form = soup.find("form")
    action = urljoin(base_url, form.get("action")) if form and form.get("action") else base_url
    fields = _form_fields(soup)
    year_fields = [k for k in fields if "year" in k.lower()]
    requests: list[dict] = []
    for a in links[1 : years + 1]:  # links[0] is the current year, already loaded
        label = _clean(a.get_text(" "))
        start_year = YEAR_LABEL.match(label).group(1)
        script = " ".join(filter(None, [a.get("href", ""), a.get("onclick", "")]))
        pb = POSTBACK.search(script)
        if pb:
            data = {**fields, "__EVENTTARGET": pb.group(1), "__EVENTARGUMENT": pb.group(2)}
            requests.append({"label": label, "method": "POST", "url": action, "data": data})
            diag["method"] = "__doPostBack"
            continue
        call = JS_CALL.search(script.replace("javascript:", ""))
        arg = None
        if call:
            nums = re.findall(r"\d{4}", call.group(2))
            arg = nums[0] if nums else None
            diag["script_function"] = call.group(1)
        if year_fields:
            data = dict(fields)
            for f in year_fields:
                data[f] = arg or start_year
            requests.append({"label": label, "method": "POST", "url": action, "data": data})
            diag["method"] = f"form post with {', '.join(year_fields)}"
        else:
            diag["method"] = "unknown - year links are script-only; only the current year is read"
            diag["sample_link"] = script[:200]
    return requests, diag


def subject_key(title: str) -> str:
    """Normalised subject of a master circular, so the 2025 and 2026 versions of the same circular match."""
    t = (title or "").lower()
    t = re.sub(r"\(updated[^)]*\)", " ", t)
    t = re.sub(r"master circulars?", " ", t)
    t = re.sub(r"\b(19|20)\d{2}(\s*-\s*\d{2,4})?\b", " ", t)
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\b(on|the|of|for|to|and|in|a|an)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def financial_year(dt: datetime | None) -> str | None:
    if not dt:
        return None
    d = dt.astimezone(IST)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{start + 1}"


# ------------------------------------------------------------- year archive
def _archive_cache_path():
    from app.config import get_settings

    return get_settings().data_dir / "master_circular_archive.json"


def _load_archive_cache() -> dict | None:
    """{"scanned_at", "rows", "years_ok", "years_failed", "report"} or None."""
    path = _archive_cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if "years_ok" not in data:  # written by an older version that cached partial reads: start over
            return None
        for r in data["rows"]:
            r["published_at"] = datetime.fromisoformat(r["published_at"]) if r.get("published_at") else None
        data["scanned_at"] = datetime.fromisoformat(data["scanned_at"])
        return data
    except Exception:
        return None


def _save_archive_cache(rows: list[dict], years_ok: list[str], years_failed: list[str], report: dict) -> None:
    out = [{**r, "published_at": r["published_at"].isoformat() if r.get("published_at") else None} for r in rows]
    _archive_cache_path().write_text(json.dumps({
        "scanned_at": datetime.now(timezone.utc).isoformat(), "rows": out,
        "years_ok": years_ok, "years_failed": years_failed, "report": report,
    }))


_MARK_GONE = "() => window.__sentinelMark === undefined && document.readyState === 'complete'"
_FINGERPRINT = (
    "() => [...document.querySelectorAll('a')].filter(a => /BS_ViewMasCirculardetails/i.test(a.getAttribute('href') || ''))"
    ".map(a => a.getAttribute('href')).join('|')"
)


async def _click_and_wait(page, link, timeout_s: float = 60.0) -> str:
    """Click a year link and return the HTML of the page that results.

    RBI's year links first jump to '#' on the same page, then post the form back, so "a navigation happened" is not
    enough. We tag the current document and wait until that document is gone (full reload) and the new one is
    complete; if the site updates the table in place instead, we wait for the list of circular links to change.
    """
    await page.evaluate("() => { window.__sentinelMark = 1; }")
    before = await page.evaluate(_FINGERPRINT)
    await link.evaluate("el => el.click()")  # works for links hidden under 'Archives'
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    settled_since = None
    while loop.time() < deadline:
        await asyncio.sleep(0.5)
        try:
            if await page.evaluate(_MARK_GONE):
                break  # a new document replaced the old one and finished loading
            now = await page.evaluate(_FINGERPRINT)
            if now != before:  # in-place update: wait until it has been stable for a moment
                settled_since = settled_since or loop.time()
                if loop.time() - settled_since > 1.5:
                    break
        except Exception:
            continue  # the page is between documents; keep polling
    else:
        pass  # nothing changed (e.g. clicking the year already shown): read what is there
    for attempt in range(6):
        try:
            await page.wait_for_load_state("load", timeout=15_000)
            return await page.content()
        except Exception:
            await asyncio.sleep(1 + attempt)
    return await page.content()


async def read_year_archive(url: str, limit: int | None, only: set[str] | None = None) -> tuple[list[dict], dict]:
    """Open the Master Circulars page in headless Chromium and click every financial-year link (archives included).

    RBI's year links post the page back to itself, so the only reliable way to read older years is to click them
    the way a person does. Each year's table is parsed with the same parser as the current page.
    `only` limits the run to these year labels (used to retry years that failed last time).
    """
    from playwright.async_api import async_playwright

    from app.config import get_settings

    s = get_settings()
    page_url = url if url.startswith(("http", "file:")) else Path(url).resolve().as_uri()
    rows: list[dict] = []
    report: dict = {"method": "headless browser (clicks each year link)", "years": []}
    async with async_playwright() as p:
        kw: dict = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if s.chromium_path:
            kw["executable_path"] = s.chromium_path
        browser = await p.chromium.launch(**kw)
        try:
            ctx = await browser.new_context(user_agent=s.http_user_agent, ignore_https_errors=not s.http_verify_ssl)
            page = await ctx.new_page()
            page.set_default_timeout(60_000)
            await page.goto(page_url, wait_until="load")
            labels = await page.evaluate(
                "() => [...document.querySelectorAll('a')].map(a => a.textContent.trim().replace(/\\s+/g, ''))"
                ".filter(t => /^\\d{4}-\\d{4}$/.test(t))"
            )
            labels = list(dict.fromkeys(labels))
            report["year_links"] = len(labels)
            if limit is not None:
                labels = labels[: limit + 1]
            if only is not None:
                labels = [l for l in labels if l in only]
            for label in labels:
                start, end = label.split("-")
                pattern = re.compile(rf"^\s*{start}\s*-\s*{end}\s*$")
                try:
                    link = page.locator("a").filter(has_text=pattern).first
                    html = await _click_and_wait(page, link)
                    items = parse_listing(html, url, "master_circular")
                    for it in items:
                        it["listing_year"] = label
                    rows.extend(items)
                    report["years"].append({"year": label, "entries": len(items)})
                except Exception as exc:
                    report["years"].append({"year": label, "error": f"{type(exc).__name__}: {exc}"[:200]})
                    try:
                        await page.goto(page_url, wait_until="load")
                    except Exception:
                        pass
                await asyncio.sleep(s.polite_delay_seconds)
        finally:
            await browser.close()
    report["entries"] = len(rows)
    return rows, report


async def fetch_listing(client: httpx.AsyncClient, source: str, url: str, past_years: int | None, fetch_bytes) -> tuple[list[dict], dict]:
    """Fetch and parse one listing page. For Master Circulars, also every earlier financial year."""
    from app.config import get_settings

    raw = await fetch_bytes(client, url)
    html = raw.decode("utf-8", errors="replace")
    items = parse_listing(html, url, source)
    report: dict = {"current_page_entries": len(items)}
    if source == "master_circular" and past_years != 0:
        s = get_settings()
        cache = _load_archive_cache()
        now = datetime.now(timezone.utc)
        fresh = cache and now - cache["scanned_at"] < timedelta(hours=s.master_circular_archive_refresh_hours)
        retry_due = cache and cache["years_failed"] and now - cache["scanned_at"] > timedelta(minutes=20)
        try:
            if fresh and not retry_due:
                extra = cache["rows"]
                info = {**cache.get("report", {}), "from_cache": True, "scanned_at": cache["scanned_at"].isoformat()}
            else:
                only = set(cache["years_failed"]) if (fresh and retry_due) else None
                got, info = await read_year_archive(url, past_years, only=only)
                ok = [y["year"] for y in info["years"] if "entries" in y]
                failed = [y["year"] for y in info["years"] if "error" in y]
                if only is not None:  # merge the retried years into what was already read
                    keep = [r for r in cache["rows"] if r.get("listing_year") not in set(ok)]
                    got = keep + got
                    ok = sorted(set(cache["years_ok"]) | set(ok), reverse=True)
                    info["retried_years"] = sorted(only, reverse=True)
                extra = got
                if ok:
                    _save_archive_cache(extra, ok, failed, info)
                info["years_read"], info["years_failed"] = len(ok), failed
        except Exception as exc:  # Playwright missing or the site blocked the browser: try a plain form post
            log.warning("year archive via browser failed, trying form post", extra={"error": str(exc)[:200]})
            extra, info = (cache["rows"] if cache else []), {"method": "headless browser failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
            if url.startswith("http"):
                reqs, diag = discover_year_requests(html, url, past_years or 50)
                info["form_post"] = diag
                for req in reqs:
                    try:
                        resp = await client.post(req["url"], data=req["data"])
                        resp.raise_for_status()
                        extra.extend(parse_listing(resp.text, url, source))
                    except Exception as e2:
                        info.setdefault("form_post_errors", []).append(str(e2)[:120])
        known = {i["guid"] for i in items}
        added = [i for i in extra if i["guid"] not in known and not known.add(i["guid"])]
        items.extend(added)
        report["archive"] = info
    report["entries"] = len(items)
    return items, report
