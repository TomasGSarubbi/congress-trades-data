# Capitol Radar — static site generator (design)

Date: 2026-08-28
Status: approved in chat (sections 1–3)

## Goal

Turn `data/*.json` (produced by the existing, untouched scrapers) into a public,
English-language static site published free via GitHub Pages from `main` `/docs`.

The product question a reader must answer at a glance: **who bought what, and did
they sell?**

## Non-goals

- No changes to `scraper/`.
- No JS frameworks, no external JS/CSS/font dependencies, no trackers.
- No charts beyond stat tiles, one ordinal meter, and single-hue bar lists.

## Architecture

`site/build.py` is the entry point and reads as a pipeline:

    load → clean → enrich → aggregate → render

Behind it, `site/lib/` holds pure, unit-tested functions:

| Module | Responsibility |
|---|---|
| `clean.py` | asset-name cleaning, ticker recovery, slugs |
| `amounts.py` | amount-range parsing |
| `enrich.py` | filing delay, party lookup, CEDEAR lookup |
| `stats.py` | briefing / per-member / per-ticker aggregates |
| `render.py` | Jinja2 environment, page writers, RSS, sitemap |

Static data: `site/cedears.csv`, `site/members.csv`.
Templates: `site/templates/`. Styles: `site/assets/styles.css`.

## Data transforms

Observed in the real dataset (84 rows, 7 members, 56 rows with `ticker: null`).

### Asset-name cleaning — three distinct garbage families

1. **House PDF null-byte metadata.** Strip `\x00`, then cut at the first run of
   spaced single capitals followed by a colon: `\s+(?:[A-Z]\s+)*[A-Z]\s*:`.
   `Alphabet Inc. - Class A Common Stock F S: New S O: Merrill Lynch Roth IRA`
   → `Alphabet Inc. - Class A Common Stock`
2. **Senate muni run-together.** Cut at `Rate/Coupon:`; capture the tail as a
   secondary detail line.
   `PENNSYLVANIA ST TPK COMMN OIL REVRate/Coupon:5%Matures:2026-12-01`
   → name `PENNSYLVANIA ST TPK COMMN OIL REV`, detail `5% · matures 2026-12-01`
3. **Scrambled extractions.** When the surviving name has fewer than 3 letters
   after removing `(TICKER)`, `[TYPE]` and the word `Shares`, the real name was
   lost upstream. Display the ticker as the name and flag the row so the template
   links the original filing prominently. Never invent a name.

Then collapse whitespace and trim.

### Ticker recovery

Only on the strict House pattern `(TICKER) [XX]` — a symbol immediately followed
by a bracketed asset type. Recovers `ACN`, `MBGL`; correctly refuses `(SPGI)`
appearing mid-sentence in a description. Recovered tickers are marked inferred.

### Amounts

Parse to `(min, max)`; `max` is `None` when absent — the dataset contains
`"$15,001"` with no upper bound. Sorting always keys on the floor. Aggregates
render as a **range** (`$402,008 – $1,730,000`), never a single fabricated number;
`None` maxes fall back to their floor.

### Delay

`filed_date - tx_date` in days (`MM/DD/YYYY`). `> 45` sets a `late` flag.

### Party

`site/members.csv` (`name,party,state,chamber`), matched on a normalized key:
full name first, then a first+last fallback so `David H Mccormick` and
`Suzan K. Delbene` both resolve. A miss renders a grey dot and "Party unknown".
**Party is never guessed from a name.**

### Determinism

Every "today" — the 7-day window, RSS dates, the last-updated line — derives from
`meta.json.last_run_utc`, never `datetime.now()`. Unchanged data must produce
byte-identical `docs/`, so CI does not churn commits.

## Visual system

Chosen with the `dataviz` method; the palette was validated with
`scripts/validate_palette.js`, not eyeballed.

### The color budget is three hues

Four saturated hues fail: sell-orange vs Republican-red measures **ΔE 7.1** to
normal vision (floor 15), and no re-stepping fixes it in dark mode, where the
lightness band (L 0.48–0.67) is too narrow for red and orange to coexist. This is
the method's series cap binding; the prescribed fix is to cut a series.

**Adopted — "Set E":** party keeps blue/red; direction gets one hue via emphasis.

| Role | Light | Dark |
|---|---|---|
| Democrat dot | `#2a78d6` | `#3987e5` |
| Republican dot | `#a32b2b` | `#e66767` |
| BUY | `#1baf7a` | `#199e70` |
| SELL | neutral pill, no hue | neutral pill, no hue |

Validated all-pairs, both modes: worst normal-vision ΔE 24.0 light / 20.9 dark.
The dark green↔red pair sits at ΔE 6.5 (protan), inside the 6–8 warn band, which
is legal **only with secondary encoding** — satisfied by the `D`/`R` letters beside
each dot and the literal words `BUY`/`SELL` in each pill, in separate columns with
different shapes.

Republican red is re-stepped from the reference `#e34948` to `#a32b2b` in light
mode via the documented snap-to-passing procedure (hold hue, move lightness).

62 of 84 rows are sells, so colouring only BUY makes the minority signal pop —
the method's "emphasis" form.

### Other encodings

- **Amount magnitude:** a 6-step **neutral gray ordinal** meter (amounts are
  ordered buckets, so ordinal, not categorical). Validated with `--ordinal`:
  monotone L, all adjacent ΔL ≥ 0.06, light end 2.35:1 light / 2.01:1 dark.
  Gray is deliberate — hue stays reserved for meaning.
- **Late filings:** the reserved `warning` status token `#fab219`, always shipped
  as **icon + label** (`⚠ 87d · late`), never colour alone. Its 1.79:1 on the light
  surface is by design; the pairing is the sanctioned mitigation.
- **Text never wears a series colour.** Pills use ink labels on a tinted ground
  with a small solid glyph carrying the hue.

### Forms

- Index stats → **KPI row of stat tiles** (not a grouped bar chart).
- Trade of the week → **hero figure**.
- Member "top tickers" → horizontal bar list, **all bars one hue** (nominal
  categories; bar length already encodes the value), no legend.
- No line charts, no pie charts, no dual axes.

## Pages

| File | Page |
|---|---|
| `docs/index.html` | Daily briefing: last-updated, KPI row, trade of the week, latest 50 |
| `docs/member/<slug>.html` | Per legislator: all trades + mini-stats |
| `docs/ticker/<slug>.html` | Per ticker: who traded it, which direction |
| `docs/cedears.html` | CEDEAR cross-reference (the differentiator) |
| `docs/methodology.html` | Sources, 45-day rule, ranges, limits, disclaimer |
| `docs/feed.xml` `docs/sitemap.xml` `docs/robots.txt` `docs/404.html` | |
| `docs/styles.css` `docs/.nojekyll` | `.nojekyll` stops Pages running Jekyll |

**Progressive enhancement.** Tables render fully server-side. ~50 lines of vanilla
JS add chamber/direction/text filtering and column sorting via `data-*` attributes.
With JS off the site is complete and indexable.

**RSS.** Built by grouping `transactions.json` on `filed_date` (one `<item>` per
filing day, last 30) rather than from `latest.json`, so the feed is deterministic
and reconstructible from data alone.

**CEDEARs.** `site/cedears.csv` maps `ticker_us,ratio,available,note`. Ratios are
subject to corporate actions; uncertain rows carry a `note` flagging them for
verification against BYMA. Coverage today is thin (~6–8 of 20 tickers) because
56 of 84 rows have no ticker at all — a data fact, not a build limitation.

## CI

`.github/workflows/fetch.yml` gains a build step. The existing data commit, push,
and `git pull --rebase` are **kept exactly as they are**; `docs/` is committed and
pushed as a *second*, separate commit after the build. Rationale: a bug in
`build.py` must never cost a day of scraped data.

`jinja2` is added to `requirements.txt`.

## Testing

`pytest` over `site/lib/`, written test-first, with fixtures taken verbatim from
the real dataset: the null-byte Alphabet row, the run-together Pennsylvania muni,
the `Shares (ACN) [ST]` stub, and the unbounded `"$15,001"` amount.

## Constants

`NEWSLETTER_URL = "#"` at the top of `build.py`; renders as inert footer text
until it is a real URL.
