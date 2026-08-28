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
