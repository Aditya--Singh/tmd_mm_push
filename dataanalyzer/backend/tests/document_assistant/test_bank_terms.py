from app.tabs.document_assistant.bank_terms import DEFAULT_FILE, BankTerms, load_terms

REQUIRED = [
    "vide",
    "updation",
    "may please",
    "positively",
    "failing which",
    "at the earliest",
    "kindly",
    "lakh",
    "crore",
    "NPA",
    "CASA",
    "KYC",
    "RBI",
    "PNB",
    "CBS",
    "NEFT",
    "RTGS",
    "IFSC",
    "MSME",
    "SARFAESI",
    "OTS",
    "ZO",
    "CO",
    "HO",
    "DGM",
    "AGM",
    "CGM",
]


def test_reference_file_has_required_terms():
    assert DEFAULT_FILE.is_file()
    terms = load_terms(DEFAULT_FILE)
    assert set(REQUIRED) <= set(terms)
    assert not any(t.startswith("#") for t in terms)


def test_load_skips_comments_blanks_and_duplicates(tmp_path):
    f = tmp_path / "terms.txt"
    f.write_text("# comment\n\n  may   please \nvide\nvide\n", encoding="utf-8")
    assert load_terms(f) == ["may please", "vide"]
    assert load_terms(tmp_path / "missing.txt") == []


def test_env_var_overrides_file(tmp_path, monkeypatch):
    f = tmp_path / "terms.txt"
    f.write_text("SMA\n", encoding="utf-8")
    monkeypatch.setenv("BANK_TERMS_FILE", str(f))
    assert BankTerms.load().terms == ["SMA"]


def test_matching_rules():
    terms = BankTerms(["CO", "kindly", "may please"])
    text = (
        "Kindly note that the CO and co-op accounts may\nplease be closed. Kindlyness."
    )
    found = [(text[s:e], t) for s, e, t in terms.spans(text)]
    assert ("Kindly", "kindly") in found  # lower-case entries ignore case
    assert ("CO", "CO") in found
    assert ("may\nplease", "may please") in found  # any whitespace between words
    assert len(found) == 3  # not "co-op" (acronyms match case) nor "Kindlyness"


def test_false_alarm_only_when_the_term_is_changed():
    terms = BankTerms(["lakh", "vide"])
    text = "The recovery are below Rs. 25 lakh, as per letter issued vide ref 1."
    vide = text.index("vide")
    assert terms.is_false_alarm(text, vide, vide + 4, ["by"])
    assert terms.is_false_alarm(text, vide - 7, vide + 4, ["issued in"])
    assert terms.is_false_alarm(text, vide, vide + 4, [])
    # A sentence-level fix that keeps the term is fine.
    end = text.index(",")
    assert not terms.is_false_alarm(text, 4, end, ["recovery is below Rs. 25 lakh"])
    # Not touching a term at all.
    assert not terms.is_false_alarm(text, 13, 16, ["is"])
