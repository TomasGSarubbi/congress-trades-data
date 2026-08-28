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


def test_load_roster_reads_vendored_legislators(tmp_path):
    from lib.enrich import load_roster
    leg = tmp_path / "leg.csv"
    leg.write_text("# comment\nlast_name,first_name,full_name,type,state,party\n"
                   "Pelosi,Nancy,Nancy Pelosi,rep,CA,Democrat\n"
                   "Boozman,John,John Boozman,sen,AR,Republican\n")
    index, people = load_roster(leg)
    assert len(people) == 2
    p = {x["name"]: x for x in people}
    assert p["Nancy Pelosi"]["party"] == "D"
    assert p["Nancy Pelosi"]["chamber"] == "House"
    assert p["John Boozman"]["chamber"] == "Senate"
    assert p["Nancy Pelosi"]["slug"] == "nancy-pelosi"


def test_roster_overrides_take_precedence(tmp_path):
    """members.csv carries former members and manual corrections."""
    from lib.enrich import load_roster, lookup_member
    leg = tmp_path / "leg.csv"
    leg.write_text("last_name,first_name,full_name,type,state,party\n"
                   "Pelosi,Nancy,Nancy Pelosi,rep,CA,Democrat\n")
    ov = tmp_path / "m.csv"
    ov.write_text("name,party,state,chamber\nEarl Blumenauer,D,OR,House\n")
    index, people = load_roster(leg, ov)
    assert len(people) == 2
    assert lookup_member(index, "Earl Blumenauer")["state"] == "OR"
    assert lookup_member(index, "Nancy Pelosi")["state"] == "CA"


def test_roster_gives_one_canonical_slug_per_person(tmp_path):
    """A filing name variant must resolve to the roster's slug, not its own."""
    from lib.enrich import load_roster, lookup_member
    leg = tmp_path / "leg.csv"
    leg.write_text("last_name,first_name,full_name,type,state,party\n"
                   "McCormick,David,David McCormick,sen,PA,Republican\n")
    index, _ = load_roster(leg)
    assert lookup_member(index, "David H Mccormick")["slug"] == "david-mccormick"


def test_short_key_ignores_generational_suffix():
    """'Angus S. King, Jr.' must key on King, not on Jr."""
    from lib.enrich import _short
    assert _short("Angus S. King, Jr.") == "angus king"
    assert _short("Thomas H. Kean, Jr.") == "thomas kean"
    assert _short("Gilbert Ray Cisneros, Jr.") == "gilbert cisneros"
    assert _short("John Smith III") == "john smith"


def test_roster_matches_nickname_and_formal_first_name(tmp_path):
    from lib.enrich import load_roster, lookup_member
    leg = tmp_path / "leg.csv"
    leg.write_text(
        "last_name,first_name,nickname,full_name,type,state,party\n"
        "Coons,Christopher,Chris,Christopher A. Coons,sen,DE,Democrat\n"
        "Steube,Gregory,Greg,W. Gregory Steube,rep,FL,Republican\n")
    index, people = load_roster(leg)
    assert lookup_member(index, "Chris Coons")["state"] == "DE"
    assert lookup_member(index, "Greg Steube")["state"] == "FL"


def test_roster_does_not_duplicate_a_person_spelled_differently(tmp_path):
    """An override naming a sitting member must update, not duplicate, them."""
    from lib.enrich import load_roster
    leg = tmp_path / "leg.csv"
    leg.write_text("last_name,first_name,nickname,full_name,type,state,party\n"
                   "King,Angus,,\"Angus S. King, Jr.\",sen,ME,Independent\n")
    ov = tmp_path / "m.csv"
    ov.write_text("name,party,state,chamber\nAngus King,I,ME,Senate\n")
    index, people = load_roster(leg, ov)
    assert len(people) == 1, [p["name"] for p in people]


def test_alias_row_points_at_a_roster_person_without_duplicating(tmp_path):
    """Filings use informal names ('Chris Coons'); aliases link them
    explicitly rather than by guessing at first-name variants."""
    from lib.enrich import load_roster, lookup_member
    leg = tmp_path / "leg.csv"
    leg.write_text("last_name,first_name,nickname,full_name,type,state,party\n"
                   "Coons,Christopher,,Christopher A. Coons,sen,DE,Democrat\n")
    ov = tmp_path / "m.csv"
    ov.write_text("name,party,state,chamber,same_as\n"
                  "Chris Coons,,,,Christopher A. Coons\n")
    index, people = load_roster(leg, ov)
    assert len(people) == 1, [p["name"] for p in people]
    got = lookup_member(index, "Chris Coons")
    assert got["name"] == "Christopher A. Coons"
    assert got["state"] == "DE"
    assert got["slug"] == "christopher-a-coons"


def test_alias_to_unknown_person_is_ignored_not_invented(tmp_path):
    from lib.enrich import load_roster, lookup_member
    leg = tmp_path / "leg.csv"
    leg.write_text("last_name,first_name,nickname,full_name,type,state,party\n"
                   "Coons,Christopher,,Christopher A. Coons,sen,DE,Democrat\n")
    ov = tmp_path / "m.csv"
    ov.write_text("name,party,state,chamber,same_as\n"
                  "Ghost Person,,,,Nobody At All\n")
    index, people = load_roster(leg, ov)
    assert len(people) == 1
    assert lookup_member(index, "Ghost Person") is None
