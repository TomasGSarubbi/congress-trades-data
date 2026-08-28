"""Repair of asset names mangled upstream by PDF/HTML extraction.

Three distinct garbage families appear in the real data; each needs its own
rule. We never invent a name: when the real one was lost upstream we say so.
"""
import re
import unicodedata

# "Name F<NUL> S<NUL>: New S<NUL> O<NUL>: Account"  ->  cut at the metadata run.
# After NUL removal this is a run of spaced single capitals ending in a colon.
_META_CUT = re.compile(r"\s+(?:[A-Z]\s+)*[A-Z]\s*:")

# "PENNSYLVANIA ST GORate/Coupon:5%Matures:2035-04-01"
_COUPON = re.compile(r"Rate/Coupon:\s*([\d.]+\s*%)\s*Matures:\s*([\d-]+)")

# The House format is "Name (TICKER) [XX]" - the bracketed asset type is what
# tells us this really is the symbol field and not prose.
_TICKER_TYPE = re.compile(r"\(([A-Z][A-Z0-9.]{0,5})\)\s*\[([A-Z]{2})\]")

_STUB_NOISE = re.compile(r"\bShares\b|\[[A-Z]{2}\]", re.I)


def _collapse(text):
    return re.sub(r"\s+", " ", text).strip()


def clean_asset(raw):
    """Return (name, detail, is_stub)."""
    if not raw:
        return ("—", None, False)

    text = raw.replace("\x00", "")
    detail = None

    m = _COUPON.search(text)
    if m:
        rate = m.group(1).replace(" ", "")
        detail = f"{rate} · matures {m.group(2)}"
        text = text[: m.start()]

    cut = _META_CUT.search(text)
    if cut:
        text = text[: cut.start()]

    name = _collapse(text)

    core = _TICKER_TYPE.sub("", name)
    core = _collapse(_STUB_NOISE.sub("", core))
    if len(re.findall(r"[A-Za-z]", core)) < 3:
        ticker = recover_ticker(raw)
        return (ticker or name or "—", detail, True)

    return (name, detail, False)


def recover_ticker(raw):
    """Recover a symbol only from the strict `(TICKER) [XX]` filing pattern."""
    if not raw:
        return None
    m = _TICKER_TYPE.search(raw.replace("\x00", ""))
    return m.group(1) if m else None


def slugify(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "unknown"
