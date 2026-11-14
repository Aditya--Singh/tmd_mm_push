"""Turn RBI HTML/PDF into clean structured text, extract circular metadata, and chunk it.

Chunking is structure-aware: RBI circulars are written in numbered paragraphs ("2.", "(i)", "4(3)") and tables, so we
split on paragraph boundaries, keep tables row-intact, and prepend a contextual header (title, reference number,
date) to every chunk so a chunk retrieved on its own still says which circular it came from.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime

from bs4 import BeautifulSoup

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})\b")
RBI_REF_RE = re.compile(r"\bRBI/(?:[A-Z]+/)?\d{4}-\d{2}/\d+\b")
SALUTATION_RE = re.compile(r"^(Madam|Dear Sir|Sir|Madam\s*/\s*Sir|Madam\s*/\s*Dear Sir)\b", re.I)

DEPARTMENTS = {
    "DOR": "Department of Regulation",
    "DOS": "Department of Supervision",
    "FIDD": "Financial Inclusion and Development Department",
    "FED": "Foreign Exchange Department",
    "A.P. (DIR SERIES)": "Foreign Exchange Department",
    "DPSS": "Department of Payment and Settlement Systems",
    "DCM": "Department of Currency Management",
    "DGBA": "Department of Government and Bank Accounts",
    "FMRD": "Financial Markets Regulation Department",
    "FMOD": "Financial Markets Operations Department",
    "CEPD": "Consumer Education and Protection Department",
    "IDMD": "Internal Debt Management Department",
    "DEPR": "Department of Economic and Policy Research",
    "DOT": "Department of Information Technology",
    "CO.DIT": "Department of Information Technology",
    "DSIM": "Department of Statistics and Information Management",
    "RPCD": "Rural Planning and Credit Department",
    "DBR": "Department of Banking Regulation",
    "DNBR": "Department of Non-Banking Regulation",
    "DCBR": "Department of Co-operative Bank Regulation",
    "FINTECH": "Fintech Department",
    "ENFD": "Enforcement Department",
}

NOT_FOR_COMMERCIAL_BANKS = re.compile(
    r"co-operative banks|nbfc|non-banking financial|payments? banks|small finance banks|regional rural banks|"
    r"housing finance|asset reconstruction|primary \(urban\)|local area banks",
    re.I,
)


@dataclass
class CircularMeta:
    rbi_ref: str | None = None
    dept_ref: str | None = None
    department: str | None = None
    issued_on: datetime | None = None
    addressees: str | None = None
    signatory: str | None = None


def html_to_text(html: str) -> str:
    """Readable text with paragraph breaks; tables rendered as pipe-separated rows."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript", "img"]):
        bad.decompose()
    for s in soup.find_all("s"):  # struck-through text in amendment circulars = deleted wording
        s.replace_with(f"[deleted: {s.get_text(' ', strip=True)}]")
    for table in soup.find_all("table"):
        if table.find("table"):
            continue  # layout wrapper table; inner tables are handled on their own
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if cells:
                rows.append(" | ".join(cells))
        if len(rows) > 1 or (rows and table.find_parent("table")):
            table.replace_with(soup.new_string("\n\n" + "\n".join(rows) + "\n\n"))
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "tr"]):
        block.insert_before("\n\n")
        block.insert_after("\n\n")
    text = soup.get_text("")
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "") for p in reader.pages]
    text = "\n\n".join(pages)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_metadata(text: str) -> CircularMeta:
    meta = CircularMeta()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = lines[:40]

    m = RBI_REF_RE.search(text[:2000])
    if m:
        meta.rbi_ref = m.group(0)
        for i, ln in enumerate(head):
            if meta.rbi_ref in ln:
                rest = ln.replace(meta.rbi_ref, "").strip()
                candidate = rest or (head[i + 1] if i + 1 < len(head) else "")
                if candidate and "/" in candidate and len(candidate) < 120 and not DATE_RE.search(candidate):
                    meta.dept_ref = candidate
                break
    if meta.dept_ref:
        upper = meta.dept_ref.upper()
        for code, name in sorted(DEPARTMENTS.items(), key=lambda kv: -len(kv[0])):
            if upper.startswith(code) or f".{code}." in upper or upper.startswith(code.replace(".", "")):
                meta.department = name
                break

    d = DATE_RE.search(text[:3000])
    if d:
        try:
            meta.issued_on = datetime.strptime(f"{d.group(1)} {d.group(2)} {d.group(3)}", "%B %d %Y")
        except ValueError:
            pass
        # addressees = lines between the date line and the salutation
        date_idx = next((i for i, ln in enumerate(head) if d.group(0) in ln), None)
        if date_idx is not None:
            block = []
            for ln in head[date_idx + 1 : date_idx + 12]:
                if SALUTATION_RE.match(ln):
                    break
                block.append(ln)
            if block and len(" ".join(block)) < 600:
                meta.addressees = " ".join(block).strip(" ,")

    tail = lines[-8:]
    for i, ln in enumerate(tail):
        if re.match(r"^\(.+\)$", ln) and len(ln) < 80:
            role = tail[i + 1] if i + 1 < len(tail) else ""
            meta.signatory = f"{ln.strip('()')}, {role}".strip(", ")
    return meta


OTHER_ENTITY_TITLE = re.compile(
    r"\(?\s*(small finance banks?|payments? banks?|regional rural banks?|local area banks?|co-?operative banks?|"
    r"urban co-?operative|rural co-?operative|ucbs?|stcbs?|dccbs?|rrbs?|sfbs?|non-banking financial|nbfcs?|non-bank|housing finance|"
    r"credit information compan|asset reconstruction compan|all india financial institutions?|primary dealers?)\b",
    re.I,
)
# headings on RBI's Master Circular / Master Direction pages -> what they usually mean for a scheduled commercial bank
GROUP_APPLICABILITY = [
    (r"commercial bank", "Applicable", "Listed under commercial banks on the RBI page."),
    (r"foreign exchange", "Applicable", "Foreign exchange directions apply to the bank as an Authorised Dealer Category-I."),
    (r"financial inclusion", "Applicable", "Financial inclusion / priority sector instructions apply to scheduled commercial banks."),
    (r"banker to (govern|bank)|debt manager|issuer of currency|currency management|government and bank", "Applicable",
     "Agency banking / currency chest instructions apply to banks that conduct this business."),
    (r"consumer education|customer", "Review", "Consumer protection directions - check the regulated-entity category in the title."),
    (r"payment and settlement|payment system", "Review", "Payment-system directions - applicable where the bank runs that payment business."),
    (r"financial market|markets", "Review", "Market directions - applicable to the bank's treasury where it participates."),
    (r"co-?operative|non-?bank|nbfc|small finance|payments bank|regional rural|local area|primary dealer|"
     r"all india financial|credit information|asset reconstruction|housing finance", "Not applicable",
     "Listed under another category of regulated entity."),
]


# reasons that rest on explicit text in the title or addressee list; these override a model's opinion
STRONG_REASONS = ("Title names another category", "Addressed only to other categories", "Addressed to commercial banks")


def applicability_heuristic(title: str, addressees: str | None, source: str, listing_group: str | None = None) -> tuple[str, str]:
    """Rule-based first pass on whether a document applies to a scheduled commercial bank (e.g., a PSB)."""
    if source == "press_release":
        return "Informational", "Press release - informational unless it announces regulatory action."
    low = f"{title} {addressees or ''}".lower()
    if re.search(r"commercial banks|all banks|all scheduled|public sector banks|lead banks|authori[sz]ed dealer category", low):
        return "Applicable", "Addressed to commercial banks / authorised dealers."
    if "draft" in low:
        return "For comments", "Draft issued for public comments; no compliance obligation yet."
    if source in ("master_circular", "master_direction"):
        if OTHER_ENTITY_TITLE.search(title[:120]):
            return "Not applicable", f"Title names another category of regulated entity ({OTHER_ENTITY_TITLE.search(title[:120]).group(1)})."
        if addressees and NOT_FOR_COMMERCIAL_BANKS.search(addressees):
            return "Not applicable", "Addressed only to other categories of regulated entities."
        group = (listing_group or "").lower()
        for pat, verdict, reason in GROUP_APPLICABILITY:
            if group and re.search(pat, group):
                return verdict, reason
        return "Review", "Consolidated instruction; the RBI listing heading does not settle applicability."
    if addressees and NOT_FOR_COMMERCIAL_BANKS.search(addressees):
        return "Not applicable", "Addressed only to other categories of regulated entities."
    return "Review", "Addressees not explicit; compliance team should review."


HIGH_PRIORITY = re.compile(
    r"uapa|sanction|freez|fraud|cyber|kyc|anti-money|aml|monetary policy|repo rate|crr|slr|penal|immediate effect|"
    r"capital adequacy|leverage ratio|liquidity coverage|priority sector|expected credit loss",
    re.I,
)
LOW_PRIORITY = re.compile(r"tender|speech|recruitment|holiday|museum|auction result|money market operations", re.I)


def priority_heuristic(title: str, text: str, source: str, applicability: str | None = None, revised: bool = False) -> tuple[str, str]:
    probe = f"{title}\n{text[:1500]}"
    if applicability == "Not applicable":
        return "Low", "Not addressed to commercial banks."
    if source in ("master_circular", "master_direction"):
        kind = "Master Direction" if source == "master_direction" else "Master Circular"
        if revised:
            return "Medium", f"{kind} revised by RBI - compare with the bank's current policy."
        if HIGH_PRIORITY.search(probe) or (source == "master_direction" and applicability == "Applicable"):
            return "High", f"New {kind} applicable to the bank; consolidates binding instructions."
        return "Medium", f"{kind} consolidating earlier instructions."
    if HIGH_PRIORITY.search(probe):
        return "High", f"Touches a high-impact area ({HIGH_PRIORITY.search(probe).group(0)})."
    if LOW_PRIORITY.search(title) or (source == "press_release" and "direction" not in probe.lower()):
        return "Low", "Routine / informational publication."
    return "Medium", "Regulatory instruction with moderate operational impact."


TAG_RULES = {
    "KYC / AML": r"kyc|know your customer|uapa|money laundering|aml|sanctions list|pmla",
    "Capital & Prudential": r"capital adequacy|leverage ratio|basel|prudential|provisioning|expected credit loss|ecl",
    "Foreign Exchange": r"fema|foreign exchange|authori[sz]ed dealer|overseas|ecb|lrs",
    "Priority Sector & Inclusion": r"priority sector|lead bank|financial inclusion|msme|agricultur|kcc",
    "Payments": r"payment|upi|neft|rtgs|card|prepaid|digital rupee",
    "Monetary Policy": r"monetary policy|repo|reverse repo|crr|slr|liquidity adjustment",
    "Credit & Lending": r"loan|lending|credit|advances|recovery|npa|wilful default",
    "Customer Service": r"customer service|grievance|ombudsman|fair practices",
    "Governance & Risk": r"operational risk|governance|audit|compliance|risk management|outsourcing",
    "IT & Cyber": r"cyber|information technology|it governance|digital|outsourcing of it",
    "Markets & Treasury": r"government securities|g-sec|treasury|money market|derivative|investment portfolio",
}


def tag_heuristic(title: str, text: str) -> list[str]:
    probe = f"{title}\n{text[:4000]}".lower()
    return [tag for tag, pat in TAG_RULES.items() if re.search(pat, probe)][:5]


# ---------------------------------------------------------------- chunking
_SENT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\d])")


def chunk_text(text: str, size_words: int = 220, overlap_words: int = 40) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[str] = []
    for p in paragraphs:
        words = p.split()
        if len(words) <= int(size_words * 1.3):
            units.append(p)
            continue
        if "|" in p and "\n" in p:  # big table: split by rows
            rows, cur = p.split("\n"), []
            for r in rows:
                cur.append(r)
                if sum(len(x.split()) for x in cur) >= size_words:
                    units.append("\n".join(cur))
                    cur = []
            if cur:
                units.append("\n".join(cur))
            continue
        sentences, cur = _SENT.split(p), []
        for sent in sentences:
            cur.append(sent)
            if sum(len(x.split()) for x in cur) >= size_words:
                units.append(" ".join(cur))
                cur = []
        if cur:
            units.append(" ".join(cur))

    chunks: list[str] = []
    cur: list[str] = []
    cur_words = 0
    for u in units:
        n = len(u.split())
        if cur and cur_words + n > size_words:
            chunks.append("\n\n".join(cur))
            # overlap: carry trailing units totalling <= overlap_words
            carry, carry_words = [], 0
            for prev in reversed(cur):
                w = len(prev.split())
                if carry_words + w > overlap_words:
                    break
                carry.insert(0, prev)
                carry_words += w
            cur, cur_words = carry, carry_words
        cur.append(u)
        cur_words += n
    if cur:
        chunks.append("\n\n".join(cur))
    # drop chunks that are pure overlap duplicates
    out: list[str] = []
    for c in chunks:
        if not out or c != out[-1]:
            out.append(c)
    return out


def contextual_header(title: str, rbi_ref: str | None, issued: datetime | None, source: str, group: str | None = None) -> str:
    bits = [title.strip()]
    if group:
        bits.append(group)
    if rbi_ref:
        bits.append(rbi_ref)
    if issued:
        bits.append(issued.strftime("%d %b %Y"))
    bits.append(source.replace("_", " ").title())
    return " | ".join(bits)
