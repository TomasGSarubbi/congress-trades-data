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
    raw = "Asset acquired through a S&P Global (SPGI) spinoff."
    assert recover_ticker(raw) is None


def test_slugify():
    assert slugify("David H Mccormick") == "david-h-mccormick"
    assert slugify("Suzan K. Delbene") == "suzan-k-delbene"
    assert slugify("BRK.B") == "brk-b"
