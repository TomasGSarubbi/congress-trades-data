import pytest
from lib.amounts import parse_amount, format_range, bucket_index


@pytest.mark.parametrize("raw,expected", [
    ("$1,001 - $15,000", (1001, 15000)),
    ("$50,001 - $100,000", (50001, 100000)),
    ("$1,000,001 - $5,000,000", (1000001, 5000000)),
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
