"""Jinja2 rendering, plus the feed, sitemap and static asset copying.

Everything here is deterministic: dates come from the records and from
meta.json, never from the clock, and every iteration order is explicitly
sorted.
"""
import datetime as dt
import html
import pathlib
import shutil
from collections import defaultdict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lib.amounts import format_range
from lib.stats import average_delay, top_tickers, total_range

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def pretty_date(iso):
    """2026-08-27 -> 27 Aug 2026. Locale-independent, hence deterministic."""
    if not iso:
        return "—"
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def rfc822(iso):
    d = dt.date.fromisoformat(iso)
    return (f"{_DAYS[d.weekday()]}, {d.day:02d} {_MONTHS[d.month - 1]} "
            f"{d.year} 00:00:00 +0000")


def env(template_dir):
    e = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    e.filters["pretty_date"] = pretty_date
    e.filters["money"] = lambda n: f"${n:,}" if n is not None else "—"
    e.filters["range_money"] = lambda pair: format_range(pair[0], pair[1])
    return e


def _as_of_date(meta):
    """The build's reference 'today', taken from the scraper's last run."""
    stamp = (meta or {}).get("last_run_utc") or ""
    return dt.date.fromisoformat(stamp[:10]) if stamp[:10] else None


def _window(records, as_of, days):
    if as_of is None:
        return list(records)
    floor = as_of - dt.timedelta(days=days)
    out = []
    for r in records:
        if not r["filed_date_sort"]:
            continue
        if dt.date.fromisoformat(r["filed_date_sort"]) >= floor:
            out.append(r)
    return out


def _largest(records):
    scored = [r for r in records if r["amount_lo"] is not None]
    if not scored:
        return None
    return max(scored, key=lambda r: (r["amount_lo"], r["id"]))


def _extreme_delay(records, pick):
    scored = [r for r in records if r["delay"] is not None]
    if not scored:
        return None
    return pick(scored, key=lambda r: (r["delay"], r["id"]))


def render_site(records, meta, cedears, out_dir, assets_dir, template_dir, site):
    out_dir = pathlib.Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "member").mkdir(parents=True, exist_ok=True)
    (out_dir / "ticker").mkdir(parents=True, exist_ok=True)

    e = env(template_dir)
    as_of = _as_of_date(meta)
    week = _window(records, as_of, 7)

    base = {
        "site": site,
        "as_of": as_of.isoformat() if as_of else "",
        "meta": meta,
        "total_trades": len(records),
    }

    def page(template, path, **ctx):
        merged = dict(base)
        merged.update(ctx)
        text = e.get_template(template).render(**merged)
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    # ---- index -----------------------------------------------------------
    fastest = _extreme_delay(week or records, min)
    slowest = _extreme_delay(week or records, max)
    page("index.html", "index.html",
         recent=records[:50],
         kpi={
             "new_trades": (meta or {}).get("new_transactions", len(week)),
             "week_count": len(week),
             "largest": _largest(week),
             "fastest": fastest,
             "slowest": slowest,
         },
         play_of_week=_largest(week))

    # ---- members ---------------------------------------------------------
    by_member = defaultdict(list)
    for r in records:
        by_member[r["member_slug"]].append(r)

    members_index = []
    for slug in sorted(by_member):
        rows = by_member[slug]
        first = rows[0]
        stats = {
            "total": total_range(rows),
            "count": len(rows),
            "avg_delay": average_delay(rows),
            "top_tickers": top_tickers(rows, 5),
            "buys": sum(1 for r in rows if r["direction"] == "buy"),
            "sells": sum(1 for r in rows if r["direction"] == "sell"),
            "late": sum(1 for r in rows if r["late"]),
        }
        members_index.append({"slug": slug, "name": first["member"],
                              "party": first["party"], "state": first["state"],
                              "chamber": first["chamber"], "count": len(rows),
                              "total": stats["total"]})
        page("member.html", f"member/{slug}.html",
             member=first, rows=rows, stats=stats)

    # ---- tickers ---------------------------------------------------------
    by_ticker = defaultdict(list)
    for r in records:
        if r["ticker_slug"]:
            by_ticker[r["ticker_slug"]].append(r)

    tickers_index = []
    for slug in sorted(by_ticker):
        rows = by_ticker[slug]
        first = rows[0]
        stats = {
            "total": total_range(rows),
            "count": len(rows),
            "buys": sum(1 for r in rows if r["direction"] == "buy"),
            "sells": sum(1 for r in rows if r["direction"] == "sell"),
            "members": sorted({r["member"] for r in rows}),
        }
        tickers_index.append({"slug": slug, "ticker": first["ticker"],
                              "asset": first["asset"], "count": len(rows),
                              "cedear": first["cedear"]})
        page("ticker.html", f"ticker/{slug}.html",
             ticker=first, rows=rows, stats=stats)

    # ---- cedears ---------------------------------------------------------
    replicable, not_replicable = [], []
    for t in tickers_index:
        (replicable if t["cedear"] else not_replicable).append(t)
    page("cedears.html", "cedears.html",
         replicable=replicable, not_replicable=not_replicable,
         rows=[r for r in records if r["cedear"]][:60],
         no_ticker=sum(1 for r in records if not r["ticker"]))

    # ---- static pages ----------------------------------------------------
    page("methodology.html", "methodology.html")
    page("404.html", "404.html")
    page("members_index.html", "members.html", members=members_index)
    page("tickers_index.html", "tickers.html", tickers=tickers_index)

    # ---- feed, sitemap, robots ------------------------------------------
    _write_feed(out_dir, records, site)
    _write_sitemap(out_dir, members_index, tickers_index, site)
    (out_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site['url']}/sitemap.xml\n")
    (out_dir / ".nojekyll").write_text("")

    for asset in sorted(pathlib.Path(assets_dir).iterdir()):
        if asset.is_file():
            shutil.copy2(asset, out_dir / asset.name)


def _write_feed(out_dir, records, site):
    """One entry per filing day - reconstructible from data alone."""
    by_day = defaultdict(list)
    for r in records:
        if r["filed_date_sort"]:
            by_day[r["filed_date_sort"]].append(r)

    items = []
    for day in sorted(by_day, reverse=True)[:30]:
        rows = sorted(by_day[day], key=lambda r: (-(r["amount_lo"] or 0), r["id"]))
        people = sorted({r["member"] for r in rows})
        top = rows[0]
        buys = sum(1 for r in rows if r["direction"] == "buy")
        summary = (
            f"{len(rows)} trades disclosed by {len(people)} member"
            f"{'s' if len(people) != 1 else ''} ({buys} buys, "
            f"{len(rows) - buys} sells). Largest: {top['member']} — "
            f"{top['asset']}"
            f"{' (' + top['ticker'] + ')' if top['ticker'] else ''}, "
            f"{top['direction_label']}, {top['amount_display']}."
        )
        items.append(
            "    <item>\n"
            f"      <title>{html.escape(f'{len(rows)} congressional trades disclosed on {pretty_date(day)}')}</title>\n"
            f"      <link>{site['url']}/</link>\n"
            f"      <guid isPermaLink=\"false\">capitol-radar-{day}</guid>\n"
            f"      <pubDate>{rfc822(day)}</pubDate>\n"
            f"      <description>{html.escape(summary)}</description>\n"
            "    </item>"
        )

    latest = sorted(by_day, reverse=True)[:1]
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{html.escape(site['name'])}</title>\n"
        f"    <link>{site['url']}/</link>\n"
        f"    <description>{html.escape(site['tagline'])}</description>\n"
        "    <language>en</language>\n"
        f'    <atom:link href="{site["url"]}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        + (f"    <lastBuildDate>{rfc822(latest[0])}</lastBuildDate>\n" if latest else "")
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
    (out_dir / "feed.xml").write_text(feed, encoding="utf-8")


def _write_sitemap(out_dir, members_index, tickers_index, site):
    urls = ["/", "/cedears.html", "/methodology.html", "/members.html",
            "/tickers.html"]
    urls += [f"/member/{m['slug']}.html" for m in members_index]
    urls += [f"/ticker/{t['slug']}.html" for t in tickers_index]
    body = "\n".join(
        f"  <url><loc>{site['url']}{u}</loc></url>" for u in urls)
    (out_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n", encoding="utf-8")
