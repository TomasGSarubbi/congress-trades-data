"""Aggregates. Totals are always ranges - the law only discloses ranges."""
from collections import Counter


def total_range(rows):
    """Sum the floors and the ceilings separately, yielding an interval."""
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
    """Most-traded symbols. Ties break alphabetically so builds stay
    byte-identical run to run (Counter.most_common is insertion-ordered)."""
    counts = Counter(r["ticker"] for r in rows if r.get("ticker"))
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ordered[:n]


def average_delay(rows):
    vals = [r["delay"] for r in rows if r.get("delay") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)
