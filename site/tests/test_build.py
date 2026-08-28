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
    assert rec["asset_detail"] == "5% · matures 2035-04-01"
    assert rec["direction"] == "sell"
    assert rec["direction_label"] == "SELL · partial"
    assert rec["amount_lo"] == 50001
    assert rec["amount_display"] == "$50,001 – $100,000"
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
    assert rec["party"] is None
    assert rec["delay"] == 151


def test_build_records_attaches_cedear_when_available():
    row = {"chamber": "House", "member": "X", "owner": "Self", "ticker": "AAPL",
           "asset": "Apple Inc", "asset_type": "ST", "tx_type": "Purchase",
           "tx_date": "01/01/2026", "filed_date": "01/10/2026",
           "amount": "$1,001 - $15,000", "source": "http://x", "id": "e"}
    cedears = {"AAPL": {"ticker_us": "AAPL", "ratio": "20:1",
                        "available": "yes", "note": "CONFIRMED"}}
    rec = build.build_records([row], {}, cedears)[0]
    assert rec["cedear"]["ratio"] == "20:1"


def test_build_records_recovers_inferred_ticker():
    row = {"chamber": "House", "member": "X", "owner": "Self", "ticker": None,
           "asset": "Shares (ACN) [ST] F\x00: New", "asset_type": "ST",
           "tx_type": "Purchase", "tx_date": "01/01/2026",
           "filed_date": "01/10/2026", "amount": "$1,001 - $15,000",
           "source": "http://x", "id": "f"}
    rec = build.build_records([row], {}, {})[0]
    assert rec["ticker"] == "ACN"
    assert rec["ticker_inferred"] is True
    assert rec["asset_stub"] is True


def test_no_wall_clock_anywhere_in_site_package():
    """Determinism guard: the build keys off meta.json, never the clock."""
    import pathlib
    src = ""
    for p in pathlib.Path(__file__).resolve().parents[1].rglob("*.py"):
        if "tests" in p.parts:
            continue
        src += p.read_text()
    for banned in ("datetime.now(", "date.today(", "time.time("):
        assert banned not in src, f"non-deterministic call {banned} found"
