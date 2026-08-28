#!/usr/bin/env python3
"""Capitol Radar - static site generator.

Reads the JSON produced by scraper/ and writes a complete static site to
docs/, which GitHub Pages serves from main.

The build is deterministic by contract: every notion of "now" comes from
data/meta.json's last_run_utc, never from the wall clock, so rebuilding on
unchanged data produces byte-identical output and CI does not churn commits.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.amounts import bucket_index, format_range, parse_amount
from lib.clean import clean_asset, recover_ticker, slugify
from lib.enrich import (LATE_THRESHOLD_DAYS, delay_days, direction,
                        direction_label, load_cedears, load_roster,
                        lookup_member, parse_date)
from lib import render

NEWSLETTER_URL = "#"          # set to the real signup URL when it exists
SITE_NAME = "Capitol Radar"
SITE_TAGLINE = "Congressional stock trades, tracked daily."
SITE_URL = "https://tomasgsarubbi.github.io/congress-trades-data"

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs"
HERE = pathlib.Path(__file__).resolve().parent


def build_records(rows, members, cedears):
    """Turn raw scraper rows into fully enriched render records."""
    records = []
    for row in rows:
        asset, asset_detail, asset_stub = clean_asset(row.get("asset"))

        ticker = (row.get("ticker") or "").strip() or None
        ticker_inferred = False
        if not ticker:
            recovered = recover_ticker(row.get("asset"))
            if recovered:
                ticker, ticker_inferred = recovered, True

        member = row.get("member") or "Unknown"
        info = lookup_member(members, member) if members else None

        lo, hi = parse_amount(row.get("amount"))
        delay = delay_days(row.get("tx_date"), row.get("filed_date"))
        tx_d = parse_date(row.get("tx_date"))
        filed_d = parse_date(row.get("filed_date"))

        records.append({
            "chamber": row.get("chamber") or "—",
            "member": member,
            # Canonical slug: one person, one URL, even when filings spell
            # the name differently. Falls back to the filing name when the
            # person is not on the roster.
            "member_slug": (info or {}).get("slug") or slugify(member),
            "party": (info or {}).get("party") or None,
            "state": (info or {}).get("state") or None,
            "owner": row.get("owner") or "—",
            "ticker": ticker,
            "ticker_slug": slugify(ticker) if ticker else None,
            "ticker_inferred": ticker_inferred,
            "asset": asset,
            "asset_detail": asset_detail,
            "asset_stub": asset_stub,
            "asset_type": row.get("asset_type") or "—",
            "tx_type": row.get("tx_type") or "—",
            "direction": direction(row.get("tx_type")),
            "direction_label": direction_label(row.get("tx_type")),
            "tx_date": row.get("tx_date") or "—",
            "filed_date": row.get("filed_date") or "—",
            "tx_date_sort": tx_d.isoformat() if tx_d else "",
            "filed_date_sort": filed_d.isoformat() if filed_d else "",
            "amount": row.get("amount") or "—",
            "amount_lo": lo,
            "amount_hi": hi,
            "amount_display": format_range(lo, hi),
            "amount_bucket": bucket_index(lo),
            "delay": delay,
            "late": delay is not None and delay > LATE_THRESHOLD_DAYS,
            "cedear": cedears.get(ticker) if ticker else None,
            "source": row.get("source") or "",
            "id": row.get("id") or "",
        })

    # Newest filings first; stable and total, so the order never wobbles.
    records.sort(key=lambda r: (r["filed_date_sort"], r["tx_date_sort"],
                                r["member"], r["id"]), reverse=True)
    return records


def main():
    rows = json.loads((DATA / "transactions.json").read_text())
    meta = json.loads((DATA / "meta.json").read_text())
    members, roster = load_roster(HERE / "legislators.csv", HERE / "members.csv")
    cedears = load_cedears(HERE / "cedears.csv")

    records = build_records(rows, members, cedears)

    render.render_site(
        records=records,
        meta=meta,
        cedears=cedears,
        roster=roster,
        out_dir=OUT,
        assets_dir=HERE / "assets",
        template_dir=HERE / "templates",
        site={"name": SITE_NAME, "tagline": SITE_TAGLINE, "url": SITE_URL,
              "newsletter_url": NEWSLETTER_URL,
              "late_threshold": LATE_THRESHOLD_DAYS},
    )
    print(f"Built {len(records)} trades, {len(roster)} tracked people -> {OUT}")


if __name__ == "__main__":
    main()
