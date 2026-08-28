# Capitol Radar Static Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a public English-language static site in `docs/` from `data/*.json`, publishable free via GitHub Pages from `main` `/docs`.

**Architecture:** `site/build.py` is a thin entry point running `load → clean → enrich → aggregate → render`. All non-trivial logic lives in small, pure, unit-tested modules under `site/lib/`. Jinja2 renders templates from `site/templates/` into `docs/`. Static reference data (`members.csv`, `cedears.csv`) is hand-maintained.

**Tech Stack:** Python 3.12, Jinja2, pytest. No JS frameworks, no external runtime dependencies, no trackers.

**Spec:** `specs/2026-08-28-capitol-radar-site-design.md`

## Global Constraints

- **Do not modify `scraper/`.** Read `data/*.json` only.
- **Determinism is mandatory.** All "now"/"today" logic derives from `meta.json.last_run_utc`. `datetime.now()`, `date.today()` and `time.time()` must not appear anywhere in `site/`. Unchanged input must produce byte-identical `docs/`.
- **Site language is English.** Brand name: `Capitol Radar`.
- **Site root is `docs/`.** Never write specs, plans, or notes into `docs/` — it is the published web root and `build.py` owns it.
- **No external assets.** No CDN scripts, no web fonts, no remote images, no analytics. Font stack is `system-ui, -apple-system, "Segoe UI", sans-serif`.
- **Colour tokens are fixed and validated — do not substitute values.**
  - Light: surface `#fcfcfb`, page `#f9f9f7`, ink `#0b0b0b`, ink-2 `#52514e`, muted `#898781`, grid `#e1e0d9`, D `#2a78d6`, R `#a32b2b`, buy `#1baf7a`, warning `#fab219`
  - Dark: surface `#161616`, page `#0d0d0d`, ink `#ffffff`, ink-2 `#c3c2b7`, muted `#898781`, grid `#2c2c2a`, D `#3987e5`, R `#e66767`, buy `#199e70`, warning `#fab219`
  - Amount ramp light: `#a9a79f,#938f86,#7c796f,#66635a,#504e46,#3a3934`
  - Amount ramp dark: `#4a4945,#5e5d57,#74726a,#8b897f,#a3a096,#bbb8ad`
- **SELL gets no hue.** Only BUY is coloured (emphasis form). Party is a dot *plus* a `D`/`R` letter — never colour alone. Late filings are `⚠ Nd · late` — never colour alone.
- **Never fabricate a party.** Unmatched member → grey dot, "Party unknown".
- **Never fabricate an amount.** Aggregates render as ranges.
- `NEWSLETTER_URL = "#"` constant in `build.py`; renders inert while `"#"`.

---

## File Structure

| File | Responsibility |
|---|---|
| `site/build.py` | Entry point; pipeline orchestration; `NEWSLETTER_URL` |
| `site/lib/__init__.py` | Empty package marker |
| `site/lib/amounts.py` | Amount-range parsing and formatting |
| `site/lib/clean.py` | Asset-name cleaning, ticker recovery, slugs |
| `site/lib/enrich.py` | Dates/delay, direction, party lookup, CEDEAR lookup |
| `site/lib/stats.py` | Briefing, per-member and per-ticker aggregates |
| `site/lib/render.py` | Jinja2 env, page writers, RSS, sitemap |
| `site/members.csv` | `name,party,state,chamber` reference data |
| `site/cedears.csv` | `ticker_us,ratio,available,note` reference data |
| `site/templates/*.html` | Jinja2 templates |
| `site/assets/styles.css` | The single stylesheet |
| `site/assets/app.js` | ~50 lines vanilla JS: filter + sort |
| `site/tests/test_*.py` | pytest suites |
| `requirements.txt` | add `jinja2` |
| `requirements-dev.txt` | `pytest` |
| `.github/workflows/fetch.yml` | add build + second commit |

---

### Task 1: Amount parsing

**Files:**
- Create: `site/lib/__init__.py` (empty), `site/lib/amounts.py`
- Test: `site/tests/test_amounts.py`

**Interfaces:**
- Consumes: nothing
- Produces: `parse_amount(raw: str | None) -> tuple[int | None, int | None]`, `format_range(lo: int | None, hi: int | None) -> str`, `AMOUNT_BUCKETS: list[int]`, `bucket_index(lo: int | None) -> int` returning `0..5`

- [ ] **Step 1: Write the failing test**

```python
# site/tests/test_amounts.py
import pytest
from lib.amounts import parse_amount, format_range, bucket_index


@pytest.mark.parametrize("raw,expected", [
    ("$1,001 - $15,000", (1001, 15000)),
    ("$50,001 - $100,000", (50001, 100000)),
    ("$1,000,001 - $5,000,000", (1000001, 5000000)),
    # Real row in data/transactions.json: a floor with no upper bound.
    ("$15,001", (15001, None)),
    ("Over $50,000,000", (50000000, None)),
    ("", (None, None)),
    (None, (None, None)),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_format_range_uses_both_bounds():
    assert format_range(1001, 15000) == "$1,001 – $15,000"


def test_format_range_open_ended_never_invents_an_upper_bound():
    assert format_range(15001, None) == "$15,001+"


def test_format_range_empty():
    assert format_range(None, None) == "—"


def test_bucket_index_is_monotone_and_clamped():
    assert bucket_index(1001) == 0
    assert bucket_index(5_000_000) == 5
    assert bucket_index(None) == 0
    assert bucket_index(1001) < bucket_index(100_001) < bucket_index(5_000_000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd site && python -m pytest tests/test_amounts.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'lib.amounts'`

- [ ] **Step 3: Write minimal implementation**

```python
# site/lib/amounts.py
"""Parsing of STOCK Act amount ranges.

The law only requires a range, so every amount is an interval. Some filings
carry only a floor (e.g. "$15,001"); we keep the upper bound as None rather
than inventing one.
"""
import re

_NUM = re.compile(r"\$\s*([\d,]+)")

# Floors of the disclosure brackets, used only to size the magnitude meter.
AMOUNT_BUCKETS = [1_001, 15_001, 50_001, 100_001, 250_001, 1_000_001]


def parse_amount(raw):
    """Return (low, high). `high` is None when the filing gives no upper bound."""
    if not raw:
        return (None, None)
    nums = [int(n.replace(",", "")) for n in _NUM.findall(raw)]
    if not nums:
        return (None, None)
    if len(nums) == 1:
        return (nums[0], None)
    return (nums[0], nums[1])


def format_range(lo, hi):
    if lo is None:
        return "—"
    if hi is None:
        return f"${lo:,}+"
    return f"${lo:,} – ${hi:,}"


def bucket_index(lo):
    """Index 0..5 into the 6-step ordinal amount ramp."""
    if lo is None:
        return 0
    idx = 0
    for i, floor in enumerate(AMOUNT_BUCKETS):
        if lo >= floor:
            idx = i
    return idx
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd site && python -m pytest tests/test_amounts.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add site/lib/__init__.py site/lib/amounts.py site/tests/test_amounts.py
git commit -m "feat(site): amount range parsing"
```

---

### Task 2: Asset-name cleaning, ticker recovery, slugs

**Files:**
- Create: `site/lib/clean.py`
- Test: `site/tests/test_clean.py`

**Interfaces:**
- Consumes: nothing
- Produces: `clean_asset(raw: str | None) -> tuple[str, str | None, bool]` returning `(name, detail, is_stub)`; `recover_ticker(raw: str | None) -> str | None`; `slugify(text: str) -> str`

- [ ] **Step 1: Write the failing test**

Every fixture below is copied verbatim from `data/transactions.json`.

```python
# site/tests/test_clean.py
from lib.clean import clean_asset, recover_ticker, slugify


def test_strips_house_pdf_null_byte_metadata():
    raw = ("Alphabet Inc. - Class A Common Stock F\x00\x00\x00\x00\x00 "
           "S\x00\x00\x00\x00\x00: New S\x00\x00\x00\x00\x00\x00\x00\x00\x00 "
           "O\x00: Merrill Lynch Roth IRA")
    name, detail, stub = clean_asset(raw)
    assert name == "Alphabet Inc. - Class A Common Stock"
    assert stub is False


def test_strips_trailing_description_metadata():
    raw = ("Bloom Energy Corporation Class A Common Stock F\x00\x00\x00\x00\x00 "
           "S\x00\x00\x00\x00\x00: New D\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00: "
           "Purchased 10,000 shares")
    name, _, stub = clean_asset(raw)
    assert name == "Bloom Energy Corporation Class A Common Stock"
    assert stub is False


def test_splits_run_together_municipal_bond():
    raw = "PENNSYLVANIA ST TPK COMMN OIL REVRate/Coupon:5%Matures:2026-12-01"
    name, detail, stub = clean_asset(raw)
    assert name == "PENNSYLVANIA ST TPK COMMN OIL REV"
    assert detail == "5% · matures 2026-12-01"
    assert stub is False


def test_flags_stub_when_real_name_was_lost_upstream():
    raw = ("Shares (ACN) [ST] F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New "
           "S\x00\x00\x00\x00\x00\x00\x00\x00\x00 O\x00: Trust 2 Accenture plc "
           "Class A Ordinary")
    name, _, stub = clean_asset(raw)
    assert stub is True
    assert name == "ACN"


def test_leaves_clean_names_untouched():
    for raw in ["Vanguard FTSE Developed Markets ETF",
                "iShares Core S&P 500 ETF",
                "NEW WORLD FUND INC - Class R-6"]:
        name, detail, stub = clean_asset(raw)
        assert name == raw
        assert detail is None
        assert stub is False


def test_collapses_whitespace():
    assert clean_asset("Foo   Bar\t Baz")[0] == "Foo Bar Baz"


def test_recovers_ticker_from_strict_house_pattern():
    assert recover_ticker("Shares (ACN) [ST] F\x00: New") == "ACN"
    assert recover_ticker("(MBGL) [ST] F\x00: New") == "MBGL"


def test_refuses_ticker_mentioned_in_prose():
    # (SPGI) here is narrative, not the filing's symbol field.
    raw = "Asset acquired through a S&P Global (SPGI) spinoff."
    assert recover_ticker(raw) is None


def test_slugify():
    assert slugify("David H Mccormick") == "david-h-mccormick"
    assert slugify("Suzan K. Delbene") == "suzan-k-delbene"
    assert slugify("BRK.B") == "brk-b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd site && python -m pytest tests/test_clean.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'lib.clean'`

- [ ] **Step 3: Write minimal implementation**

```python
# site/lib/clean.py
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

# The House format is "Name (TICKER) [XX]" — the bracketed asset type is what
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd site && python -m pytest tests/test_clean.py -v`
Expected: all PASS

- [ ] **Step 5: Verify against the whole real dataset**

Run this scratch check and read the output — no row may still contain `\x00`, `Rate/Coupon`, or a ` X:` metadata run:

```bash
cd site && python -c "
import json, sys; sys.path.insert(0,'.')
from lib.clean import clean_asset
rows = json.load(open('../data/transactions.json'))
bad = [r['asset'] for r in rows if any(t in clean_asset(r['asset'])[0] for t in ('\x00','Rate/Coupon',': New'))]
print('dirty rows remaining:', len(bad))
for b in bad[:5]: print(repr(b))
"
```
Expected: `dirty rows remaining: 0`

- [ ] **Step 6: Commit**

```bash
git add site/lib/clean.py site/tests/test_clean.py
git commit -m "feat(site): asset name cleaning and ticker recovery"
```

---

### Task 3: Reference data + enrichment

**Files:**
- Create: `site/lib/enrich.py`, `site/members.csv`, `site/cedears.csv`
- Test: `site/tests/test_enrich.py`

**Interfaces:**
- Consumes: `lib.clean.slugify`
- Produces: `parse_date(s) -> date | None`; `delay_days(tx, filed) -> int | None`; `direction(tx_type) -> "buy"|"sell"|"other"`; `direction_label(tx_type) -> str`; `load_members(path) -> dict`; `lookup_member(members, name) -> dict | None`; `load_cedears(path) -> dict`; `LATE_THRESHOLD_DAYS = 45`

**`site/members.csv`** — seed with only members whose party is certain. Header: `name,party,state,chamber`. Include at minimum the seven present in the data:

```csv
name,party,state,chamber
Nancy Pelosi,D,CA,House
John Boozman,R,AR,Senate
David McCormick,R,PA,Senate
Michael Rulli,R,OH,House
Kelly Morrison,D,MN,House
Suzan DelBene,D,WA,House
William Keating,D,MA,House
```

Add further frequent filers only where certain. **An absent or uncertain member must be left out** — a grey "Party unknown" dot is correct; a guessed party is not.

**`site/cedears.csv`** — header `ticker_us,ratio,available,note`. `ratio` is CEDEARs-per-underlying-share as `N:1`. Ratios change with corporate actions, so every row that is not certain carries a `note` of `VERIFY`. Seed the ~60 most liquid; the user-supplied anchors are `AAPL 20:1, MSFT 15:1, NVDA 24:1, GOOGL 58:1, AMZN 144:1, TSLA 15:1, META 24:1, INTC 10:1, KO 5:1`.

- [ ] **Step 1: Write the failing test**

```python
# site/tests/test_enrich.py
import datetime as dt
from lib.enrich import (parse_date, delay_days, direction, direction_label,
                        load_members, lookup_member, LATE_THRESHOLD_DAYS)


def test_parse_date():
    assert parse_date("08/19/2026") == dt.date(2026, 8, 19)
    assert parse_date("") is None
    assert parse_date("garbage") is None


def test_delay_days():
    assert delay_days("08/19/2026", "08/27/2026") == 8
    assert delay_days("", "08/27/2026") is None


def test_late_threshold_is_the_stock_act_rule():
    assert LATE_THRESHOLD_DAYS == 45


def test_direction_covers_all_three_real_tx_types():
    assert direction("Purchase") == "buy"
    assert direction("Sale (Partial)") == "sell"
    assert direction("Sale (Full)") == "sell"


def test_direction_label_distinguishes_partial_from_full():
    assert direction_label("Purchase") == "BUY"
    assert direction_label("Sale (Full)") == "SELL"
    assert direction_label("Sale (Partial)") == "SELL · partial"


def test_lookup_member_matches_middle_initial(tmp_path):
    csv = tmp_path / "m.csv"
    csv.write_text("name,party,state,chamber\nDavid McCormick,R,PA,Senate\n")
    members = load_members(csv)
    # The data spells it "David H Mccormick".
    assert lookup_member(members, "David H Mccormick")["party"] == "R"


def test_lookup_member_matches_punctuated_name(tmp_path):
    csv = tmp_path / "m.csv"
    csv.write_text("name,party,state,chamber\nSuzan DelBene,D,WA,House\n")
    assert lookup_member(load_members(csv), "Suzan K. Delbene")["party"] == "D"


def test_lookup_member_never_guesses(tmp_path):
    csv = tmp_path / "m.csv"
    csv.write_text("name,party,state,chamber\nNancy Pelosi,D,CA,House\n")
    assert lookup_member(load_members(csv), "Some Unknown Person") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd site && python -m pytest tests/test_enrich.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'lib.enrich'`

- [ ] **Step 3: Write minimal implementation**

```python
# site/lib/enrich.py
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
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = (row.get("ticker_us") or "").strip().upper()
            if t and (row.get("available") or "").strip().lower() in ("yes", "true", "1"):
                out[t] = row
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd site && python -m pytest tests/test_enrich.py -v`
Expected: all PASS

- [ ] **Step 5: Verify every member in the real data resolves**

```bash
cd site && python -c "
import json, sys; sys.path.insert(0,'.')
from lib.enrich import load_members, lookup_member
m = load_members('members.csv')
rows = json.load(open('../data/transactions.json'))
miss = sorted({r['member'] for r in rows if lookup_member(m, r['member']) is None})
print('unmatched members:', miss)
"
```
Expected: `unmatched members: []`. If any name is listed, add it to `members.csv` **only** if its party is certain.

- [ ] **Step 6: Commit**

```bash
git add site/lib/enrich.py site/members.csv site/cedears.csv site/tests/test_enrich.py
git commit -m "feat(site): enrichment, party and CEDEAR reference data"
```

---

### Task 4: Aggregates

**Files:**
- Create: `site/lib/stats.py`
- Test: `site/tests/test_stats.py`

**Interfaces:**
- Consumes: `lib.amounts.parse_amount`, `lib.amounts.format_range`
- Produces: `total_range(rows) -> tuple[int,int]`; `top_tickers(rows, n=5) -> list[tuple[str,int]]`; `average_delay(rows) -> float | None`; `briefing(rows, as_of) -> dict`

The rows passed in are the *enriched* dicts built in Task 6 (they carry `amount_lo`, `amount_hi`, `delay`, `ticker`, `direction`).

- [ ] **Step 1: Write the failing test**

```python
# site/tests/test_stats.py
from lib.stats import total_range, top_tickers, average_delay


def row(lo=None, hi=None, delay=None, ticker=None):
    return {"amount_lo": lo, "amount_hi": hi, "delay": delay, "ticker": ticker}


def test_total_range_sums_both_bounds():
    rows = [row(1001, 15000), row(50001, 100000)]
    assert total_range(rows) == (51002, 115000)


def test_total_range_falls_back_to_floor_when_no_upper_bound():
    # Never invent an upper bound: an open-ended row contributes its floor.
    assert total_range([row(15001, None)]) == (15001, 15001)


def test_total_range_empty():
    assert total_range([]) == (0, 0)


def test_top_tickers_ignores_rows_without_a_ticker():
    rows = [row(ticker="ACN"), row(ticker="ACN"), row(ticker=None), row(ticker="LLY")]
    assert top_tickers(rows, n=2) == [("ACN", 2), ("LLY", 1)]


def test_average_delay_skips_unknown_delays():
    assert average_delay([row(delay=10), row(delay=20), row(delay=None)]) == 15.0
    assert average_delay([row(delay=None)]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd site && python -m pytest tests/test_stats.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'lib.stats'`

- [ ] **Step 3: Write minimal implementation**

```python
# site/lib/stats.py
"""Aggregates. Totals are always ranges — the law only discloses ranges."""
from collections import Counter


def total_range(rows):
    lo = hi = 0
    for r in rows:
        a = r.get("amount_lo")
        if a is None:
            continue
        lo += a
        # No upper bound disclosed: the floor is all we honestly have.
        hi += r.get("amount_hi") or a
    return (lo, hi)


def top_tickers(rows, n=5):
    c = Counter(r["ticker"] for r in rows if r.get("ticker"))
    return c.most_common(n)


def average_delay(rows):
    vals = [r["delay"] for r in rows if r.get("delay") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd site && python -m pytest tests/test_stats.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add site/lib/stats.py site/tests/test_stats.py
git commit -m "feat(site): aggregate statistics"
```

---

### Task 5: Stylesheet and client-side behaviour

**Files:**
- Create: `site/assets/styles.css`, `site/assets/app.js`

No tests — verified visually in Task 9.

- [ ] **Step 1: Write `site/assets/styles.css`**

Structure it exactly in this order: tokens on bare `:root` (the complete light palette), then `@media (prefers-color-scheme: dark) { :root { … } }` redefining **only** the token values. Mobile-first; the trade table collapses to stacked cards under 720px. Required token names and values are in **Global Constraints** — copy them verbatim.

Key components to style: `.kpi-row` / `.kpi` (stat tiles), `.hero-figure` (≥48px value), `.trade-table`, `.pill--buy` (tinted ground, ink label, solid `#1baf7a` glyph) and `.pill--sell` (neutral ground, no hue), `.dot--d` / `.dot--r` / `.dot--unknown` (8px, always followed by a `D`/`R`/`?` letter), `.meter` (6 spans using the validated ordinal ramp), `.badge--late` (`#fab219` + `⚠` + text), `.badge--cedear`.

`body` must set an explicit token background — never transparent.

- [ ] **Step 2: Write `site/assets/app.js`**

~50 lines, no dependencies, no network. It reads `data-chamber`, `data-direction`, `data-search`, `data-amount`, `data-delay`, `data-txdate` off each `<tr>` and hides non-matching rows; column headers with `data-sort` toggle ascending/descending. It must degrade cleanly: the markup is complete without it.

```javascript
(function () {
  var table = document.querySelector('[data-filterable]');
  if (!table) return;
  var rows = Array.prototype.slice.call(table.tBodies[0].rows);
  var q = document.getElementById('q');
  var chamber = document.getElementById('f-chamber');
  var dirn = document.getElementById('f-direction');
  var count = document.getElementById('result-count');

  function apply() {
    var term = (q && q.value || '').toLowerCase();
    var c = chamber && chamber.value || '';
    var d = dirn && dirn.value || '';
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (!c || r.dataset.chamber === c) &&
               (!d || r.dataset.direction === d) &&
               (!term || r.dataset.search.indexOf(term) !== -1);
      r.hidden = !ok;
      if (ok) shown++;
    });
    if (count) count.textContent = shown + ' of ' + rows.length + ' trades';
  }

  [q, chamber, dirn].forEach(function (el) {
    if (el) el.addEventListener('input', apply);
  });

  table.querySelectorAll('th[data-sort]').forEach(function (th) {
    th.addEventListener('click', function () {
      var key = th.dataset.sort;
      var asc = th.dataset.dir !== 'asc';
      th.dataset.dir = asc ? 'asc' : 'desc';
      rows.sort(function (a, b) {
        var x = a.dataset[key], y = b.dataset[key];
        var nx = parseFloat(x), ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
        return asc ? String(x).localeCompare(y) : String(y).localeCompare(x);
      });
      var body = table.tBodies[0];
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });

  apply();
})();
```

- [ ] **Step 3: Commit**

```bash
git add site/assets/
git commit -m "feat(site): stylesheet and client-side filter/sort"
```

---

### Task 6: Build entry point and the record model

**Files:**
- Create: `site/build.py`
- Test: `site/tests/test_build.py`

**Interfaces:**
- Consumes: everything from Tasks 1–4
- Produces: `NEWSLETTER_URL`; `SITE_NAME = "Capitol Radar"`; `build_records(rows, members, cedears) -> list[dict]`; `main() -> None`

Each record carries: `chamber, member, member_slug, party, state, owner, ticker, ticker_slug, ticker_inferred, asset, asset_detail, asset_stub, asset_type, tx_type, direction, direction_label, tx_date, filed_date, tx_date_sort, filed_date_sort, amount, amount_lo, amount_hi, amount_display, amount_bucket, delay, late, cedear, source, id`.

- [ ] **Step 1: Write the failing test**

```python
# site/tests/test_build.py
import build


def test_build_records_enriches_a_real_row():
    row = {"chamber": "Senate", "member": "David H Mccormick", "owner": "Spouse",
           "ticker": None,
           "asset": "PENNSYLVANIA ST GORate/Coupon:5%Matures:2035-04-01",
           "asset_type": "Municipal Security", "tx_type": "Sale (Partial)",
           "tx_date": "08/19/2026", "filed_date": "08/27/2026",
           "amount": "$50,001 - $100,000", "source": "http://x", "id": "abc"}
    members = {"david mccormick": {"name": "David McCormick", "party": "R",
                                   "state": "PA", "chamber": "Senate"}}
    rec = build.build_records([row], members, {})[0]
    assert rec["party"] == "R"
    assert rec["asset"] == "PENNSYLVANIA ST GO"
    assert rec["direction"] == "sell"
    assert rec["direction_label"] == "SELL · partial"
    assert rec["amount_lo"] == 50001
    assert rec["delay"] == 8
    assert rec["late"] is False
    assert rec["member_slug"] == "david-h-mccormick"


def test_build_records_flags_late_filings():
    row = {"chamber": "House", "member": "X", "owner": "Self", "ticker": "AAPL",
           "asset": "Apple Inc", "asset_type": "ST", "tx_type": "Purchase",
           "tx_date": "01/01/2026", "filed_date": "06/01/2026",
           "amount": "$1,001 - $15,000", "source": "http://x", "id": "d"}
    rec = build.build_records([row], {}, {})[0]
    assert rec["late"] is True
    assert rec["party"] is None          # never guessed
    assert rec["delay"] == 151


def test_build_records_attaches_cedear_when_available():
    row = {"chamber": "House", "member": "X", "owner": "Self", "ticker": "AAPL",
           "asset": "Apple Inc", "asset_type": "ST", "tx_type": "Purchase",
           "tx_date": "01/01/2026", "filed_date": "01/10/2026",
           "amount": "$1,001 - $15,000", "source": "http://x", "id": "e"}
    cedears = {"AAPL": {"ticker_us": "AAPL", "ratio": "20:1", "available": "yes"}}
    assert build.build_records([row], {}, cedears)[0]["cedear"]["ratio"] == "20:1"


def test_no_wall_clock_anywhere_in_site_package():
    """Determinism guard: the build must key off meta.json, never the clock."""
    import pathlib
    src = ""
    for p in pathlib.Path(__file__).resolve().parents[1].rglob("*.py"):
        if "tests" in p.parts:
            continue
        src += p.read_text()
    for banned in ("datetime.now(", "date.today(", "time.time("):
        assert banned not in src, f"non-deterministic call {banned} found"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd site && python -m pytest tests/test_build.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'build'`

- [ ] **Step 3: Implement `site/build.py`**

Top-of-file constants:

```python
NEWSLETTER_URL = "#"          # set to the real signup URL when it exists
SITE_NAME = "Capitol Radar"
SITE_TAGLINE = "Congressional stock trades, tracked daily."
SITE_URL = "https://tomasgsarubbi.github.io/congress-trades-data"
```

`build_records` maps each raw row through Tasks 1–4:
- `asset, asset_detail, asset_stub = clean_asset(row["asset"])`
- `ticker = row["ticker"] or recover_ticker(row["asset"])`, setting `ticker_inferred` when it came from recovery
- `party`/`state` from `lookup_member`, else `None`
- `delay = delay_days(...)`, `late = delay is not None and delay > LATE_THRESHOLD_DAYS`
- `amount_lo, amount_hi = parse_amount(row["amount"])`, `amount_display = format_range(...)`, `amount_bucket = bucket_index(amount_lo)`
- `*_sort` fields are ISO strings from `parse_date` (empty string when unparseable) so JS sorts correctly
- `cedear = cedears.get(ticker)` when `ticker` is set

`main()` reads `data/transactions.json` and `data/meta.json`, derives `as_of = meta["last_run_utc"]`, builds records, sorts by `filed_date_sort` descending then `tx_date_sort` descending, and calls the Task 7/8 renderers. **No wall-clock calls.**

- [ ] **Step 4: Run tests**

Run: `cd site && python -m pytest tests/ -v`
Expected: all PASS, including `test_no_wall_clock_anywhere_in_site_package`

- [ ] **Step 5: Commit**

```bash
git add site/build.py site/tests/test_build.py
git commit -m "feat(site): build entry point and record model"
```

---

### Task 7: Templates — base, index, member, ticker

**Files:**
- Create: `site/lib/render.py`, `site/templates/base.html`, `site/templates/index.html`, `site/templates/member.html`, `site/templates/ticker.html`, `site/templates/_trade_table.html`

**Interfaces:**
- Consumes: `build.build_records`, `lib.stats`
- Produces: `env(template_dir)`; `write_page(env, template, out_path, **ctx)`; `render_site(records, as_of, out_dir)`

- [ ] **Step 1: Write `base.html`**

Autoescaping ON. Blocks: `title`, `description`, `content`. `<head>` carries a unique `<title>` and `<meta name="description">` per page plus `og:title`, `og:description`, `og:type`, `og:url`, and `<link rel="alternate" type="application/rss+xml">`. Footer on every page: `Capitol Radar · Made in Buenos Aires`, a link to `/methodology.html`, and the newsletter slot rendering as inert text while `NEWSLETTER_URL == "#"`.

- [ ] **Step 2: Write `_trade_table.html`**

One shared macro used by all three pages. Each `<tr>` carries `data-chamber`, `data-direction`, `data-search` (lowercased member + asset + ticker), `data-amount` (the floor), `data-delay`, `data-txdate`. Columns: member (party dot + `D`/`R` letter + chamber), asset + ticker (+ CEDEAR badge linking to `/cedears.html`), direction pill, amount (meter + range text), tx date, filed date, delay (with `⚠ Nd · late` when `late`).

- [ ] **Step 3: Write `index.html`**

Last-updated line from `as_of`; a KPI row of four stat tiles (new trades, largest trade this week, fastest disclosure, slowest disclosure); "Trade of the Week" as a hero figure (largest trade in the 7 days before `as_of`); the filter row (`#q`, `#f-chamber`, `#f-direction`, `#result-count`) in one row above the table; the latest 50 trades.

- [ ] **Step 4: Write `member.html` and `ticker.html`**

`member.html`: name, party, state, chamber; stat tiles for total traded (a **range**), average delay, trade count; top-tickers bar list with **all bars in one hue**, no legend; full trade table.
`ticker.html`: symbol and resolved name; who traded it and in which direction; CEDEAR availability; full trade table.

- [ ] **Step 5: Render and inspect**

Run: `cd site && python build.py && python -m http.server -d ../docs 8000`
Open `http://localhost:8000/` and confirm the KPI row, hero figure, pills, meters, party dots and late badges all render, in both colour schemes.

- [ ] **Step 6: Commit**

```bash
git add site/lib/render.py site/templates/
git commit -m "feat(site): base, index, member and ticker templates"
```

---

### Task 8: CEDEARs page, methodology page, feed, sitemap

**Files:**
- Create: `site/templates/cedears.html`, `site/templates/methodology.html`, `site/templates/404.html`
- Modify: `site/lib/render.py`

- [ ] **Step 1: `cedears.html`**

Explain what a CEDEAR is (a BYMA-listed certificate representing a fixed ratio of an underlying US share, tradable in pesos from Argentina). Then the cross-reference table: every ticker traded by Congress in the period that has a CEDEAR, with ratio, direction traded, and who traded it. State plainly how many traded tickers have no CEDEAR, and that ratios change with corporate actions and must be verified against BYMA. Rows flagged `VERIFY` in `cedears.csv` render with a visible "unverified ratio" marker.

- [ ] **Step 2: `methodology.html`**

Sources (Senate eFD, House Clerk), the STOCK Act 45-day rule, why amounts are ranges, limitations (paper PTRs omitted; ~two thirds of rows carry no ticker), the rolling 120-day window, and a clear disclaimer: **public information published for educational purposes; not investment advice.**

- [ ] **Step 3: `feed.xml` and `sitemap.xml` in `render.py`**

RSS: group records by `filed_date`, one `<item>` per filing day (most recent 30), `<pubDate>` in RFC-822 derived from the filing date, title `N trades disclosed on <date>`, description summarising members and largest trade. Sitemap: every generated HTML page. Also emit `robots.txt` and an empty `.nojekyll`.

- [ ] **Step 4: Validate the feed and sitemap parse**

```bash
cd /Users/tomassarubbi/Documents/congress-trades-data && python -c "
import xml.dom.minidom as m
for f in ('docs/feed.xml','docs/sitemap.xml'):
    m.parse(f); print(f, 'parses OK')
"
```
Expected: both print `parses OK`

- [ ] **Step 5: Commit**

```bash
git add site/templates/ site/lib/render.py
git commit -m "feat(site): CEDEARs page, methodology, RSS and sitemap"
```

---

### Task 9: Full local run, determinism check, and CI wiring

**Files:**
- Modify: `.github/workflows/fetch.yml`, `requirements.txt`
- Create: `requirements-dev.txt`

- [ ] **Step 1: Add `jinja2` to `requirements.txt`; create `requirements-dev.txt` containing `pytest`**

- [ ] **Step 2: Full clean run**

```bash
cd /Users/tomassarubbi/Documents/congress-trades-data && rm -rf docs && python site/build.py && find docs -type f | sort
```
Expected: `index.html`, `cedears.html`, `methodology.html`, `404.html`, `styles.css`, `app.js`, `feed.xml`, `sitemap.xml`, `robots.txt`, `.nojekyll`, one `member/*.html` per member, one `ticker/*.html` per ticker.

- [ ] **Step 3: Prove determinism**

```bash
cd /Users/tomassarubbi/Documents/congress-trades-data && \
  find docs -type f -exec md5 {} \; | sort > /tmp/a.txt && \
  rm -rf docs && python site/build.py && \
  find docs -type f -exec md5 {} \; | sort > /tmp/b.txt && \
  diff /tmp/a.txt /tmp/b.txt && echo "DETERMINISTIC"
```
Expected: prints `DETERMINISTIC` with no diff. If it differs, a wall-clock or set-iteration ordering leak remains — fix it before continuing.

- [ ] **Step 4: Modify `.github/workflows/fetch.yml`**

Keep the existing `Commit data` step **exactly as it is**, including `git pull --rebase origin main` and `git push`. Append two steps after it:

```yaml
      - name: Build site
        run: python site/build.py

      - name: Commit site
        run: |
          git config user.name "trades-bot"
          git config user.email "actions@users.noreply.github.com"
          git add docs/
          git diff --cached --quiet || git commit -m "site: $(date -u +%F)"
          git pull --rebase origin main
          git push
```

A failure in `Build site` therefore cannot lose that day's scraped data — it has already been committed and pushed.

- [ ] **Step 5: Verify the workflow file parses**

```bash
cd /Users/tomassarubbi/Documents/congress-trades-data && python -c "
import yaml; w=yaml.safe_load(open('.github/workflows/fetch.yml'))
names=[s.get('name') for s in w['jobs']['fetch']['steps']]
print(names)
assert names[-2:] == ['Build site','Commit site']
print('workflow OK')"
```
Expected: `workflow OK`

- [ ] **Step 6: Run the full test suite**

Run: `cd site && python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt .github/workflows/fetch.yml
git commit -m "ci: build and publish the site after each data run"
```
