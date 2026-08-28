"""Derived fields: filing delay, trade direction, party and CEDEAR lookups."""
import csv
import datetime as dt
import re
import unicodedata

# The STOCK Act gives members 45 days to disclose.
LATE_THRESHOLD_DAYS = 45


def parse_date(s):
    try:
        return dt.datetime.strptime(str(s).strip(), "%m/%d/%Y").date()
    except (ValueError, TypeError):
        return None


def delay_days(tx_date, filed_date):
    a, b = parse_date(tx_date), parse_date(filed_date)
    if a is None or b is None:
        return None
    return (b - a).days


def direction(tx_type):
    t = (tx_type or "").lower()
    if "purchase" in t:
        return "buy"
    if "sale" in t or "sold" in t or "exchange" in t:
        return "sell"
    return "other"


def direction_label(tx_type):
    d = direction(tx_type)
    if d == "buy":
        return "BUY"
    if d == "sell":
        return "SELL · partial" if "partial" in (tx_type or "").lower() else "SELL"
    return (tx_type or "—").upper()


def _norm(name):
    n = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    n = re.sub(r"[^\w\s]", " ", n).lower()
    return " ".join(n.split())


def _short(name):
    parts = [p for p in _norm(name).split() if len(p) > 1]
    return f"{parts[0]} {parts[-1]}" if len(parts) >= 2 else " ".join(parts)


def load_members(path):
    """Index each row under both its full and first+last normalized keys."""
    index = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("name"):
                continue
            for key in (_norm(row["name"]), _short(row["name"])):
                index.setdefault(key, row)
    return index


def lookup_member(members, name):
    return members.get(_norm(name)) or members.get(_short(name))


def load_cedears(path):
    """Only rows explicitly marked available are treated as tradable.

    The file carries a leading `#` comment block explaining the VERIFY
    convention, which csv.DictReader would otherwise read as the header.
    """
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
        for row in csv.DictReader(lines):
            t = (row.get("ticker_us") or "").strip().upper()
            avail = (row.get("available") or "").strip().lower()
            if t and avail in ("yes", "true", "1"):
                out[t] = row
    return out
