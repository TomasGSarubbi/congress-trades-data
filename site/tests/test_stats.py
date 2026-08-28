from lib.stats import total_range, top_tickers, average_delay


def row(lo=None, hi=None, delay=None, ticker=None):
    return {"amount_lo": lo, "amount_hi": hi, "delay": delay, "ticker": ticker}


def test_total_range_sums_both_bounds():
    rows = [row(1001, 15000), row(50001, 100000)]
    assert total_range(rows) == (51002, 115000)


def test_total_range_falls_back_to_floor_when_no_upper_bound():
    assert total_range([row(15001, None)]) == (15001, 15001)


def test_total_range_empty():
    assert total_range([]) == (0, 0)


def test_top_tickers_ignores_rows_without_a_ticker():
    rows = [row(ticker="ACN"), row(ticker="ACN"), row(ticker=None), row(ticker="LLY")]
    assert top_tickers(rows, n=2) == [("ACN", 2), ("LLY", 1)]


def test_top_tickers_is_deterministic_on_ties():
    rows = [row(ticker="ZZZ"), row(ticker="AAA")]
    assert top_tickers(rows, n=2) == [("AAA", 1), ("ZZZ", 1)]


def test_average_delay_skips_unknown_delays():
    assert average_delay([row(delay=10), row(delay=20), row(delay=None)]) == 15.0
    assert average_delay([row(delay=None)]) is None
