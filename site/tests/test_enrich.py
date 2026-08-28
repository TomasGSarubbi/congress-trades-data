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
    assert lookup_member(members, "David H Mccormick")["party"] == "R"


def test_lookup_member_matches_punctuated_name(tmp_path):
    csv = tmp_path / "m.csv"
    csv.write_text("name,party,state,chamber\nSuzan DelBene,D,WA,House\n")
    assert lookup_member(load_members(csv), "Suzan K. Delbene")["party"] == "D"


def test_lookup_member_never_guesses(tmp_path):
    csv = tmp_path / "m.csv"
    csv.write_text("name,party,state,chamber\nNancy Pelosi,D,CA,House\n")
    assert lookup_member(load_members(csv), "Some Unknown Person") is None


def test_load_cedears_skips_the_comment_header(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("# ratios change with splits\n# verify against BYMA\n"
                 "ticker_us,ratio,available,note\n"
                 "AAPL,20:1,yes,CONFIRMED\n"
                 "ZZZZ,5:1,no,VERIFY\n")
    from lib.enrich import load_cedears
    c = load_cedears(f)
    assert c["AAPL"]["ratio"] == "20:1"
    # A row not marked available must never appear as tradable.
    assert "ZZZZ" not in c
