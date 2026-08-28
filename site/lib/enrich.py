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


# Generational suffixes are not surnames: without this, "Angus S. King, Jr."
# keys on "jr" and never matches a filing that says "Angus King".
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _short(name):
    parts = [p for p in _norm(name).split()
             if len(p) > 1 and p not in _SUFFIXES]
    return f"{parts[0]} {parts[-1]}" if len(parts) >= 2 else " ".join(parts)


def _read_csv(path):
    """Read a CSV whose header may be preceded by a `#` comment block."""
    with open(path, newline="", encoding="utf-8") as fh:
        lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


_PARTY_LETTER = {"democrat": "D", "republican": "R", "independent": "I"}


def load_roster(legislators_path, overrides_path=None):
    """Build the tracked-people roster.

    The vendored legislators file supplies every *current* member. The
    optional overrides file (members.csv) supplies former members who still
    appear in filings, plus any manual correction, and wins on conflict.

    Returns (index, people): `index` maps normalized name keys to a person,
    `people` is the deduplicated roster sorted by name.
    """
    from lib.clean import slugify

    people = {}
    index = {}

    def register(person, keys):
        people[id(person)] = person
        for key in keys:
            if key:
                index.setdefault(key, person)

    for row in _read_csv(legislators_path):
        first = (row.get("first_name") or "").strip()
        last = (row.get("last_name") or "").strip()
        nick = (row.get("nickname") or "").strip()
        name = (row.get("full_name") or f"{first} {last}").strip()
        if not name:
            continue
        party = (row.get("party") or "").strip().lower()
        person = {
            "name": name,
            "party": _PARTY_LETTER.get(party, party[:1].upper() or None),
            "state": (row.get("state") or "").strip() or None,
            "chamber": "Senate" if (row.get("type") or "").strip() == "sen" else "House",
            "slug": slugify(name),
        }
        # Index on every spelling a filing might plausibly use: the formal
        # full name, first+last, and the nickname ("Chris Coons" for
        # "Christopher A. Coons").
        register(person, [
            _norm(name), _short(name),
            _norm(f"{first} {last}") if first and last else None,
            _norm(f"{nick} {last}") if nick and last else None,
        ])

    if overrides_path:
        for row in _read_csv(overrides_path):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            same_as = (row.get("same_as") or "").strip()
            if same_as:
                # Alias: point this spelling at an existing roster person.
                # If the target is unknown we register nothing rather than
                # invent a person.
                target = index.get(_norm(same_as)) or index.get(_short(same_as))
                if target is not None:
                    index.setdefault(_norm(name), target)
                    index.setdefault(_short(name), target)
                continue

            fields = {
                "party": (row.get("party") or "").strip() or None,
                "state": (row.get("state") or "").strip() or None,
                "chamber": (row.get("chamber") or "").strip() or None,
            }
            existing = index.get(_norm(name)) or index.get(_short(name))
            if existing is not None:
                # Same person, spelled differently: correct them in place
                # rather than seating a duplicate in the roster.
                existing.update({k: v for k, v in fields.items() if v})
                index.setdefault(_norm(name), existing)
                index.setdefault(_short(name), existing)
                continue
            person = {"name": name, "slug": slugify(name), **fields}
            register(person, [_norm(name), _short(name)])

    return index, sorted(people.values(), key=lambda p: p["name"])


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
