import pytest

from geocoder.parse import parse, state_from_postcode


def test_state_from_postcode():
    assert state_from_postcode("2042") == "NSW"
    assert state_from_postcode(3121) == "VIC"
    assert state_from_postcode("0800") == "NT"
    assert state_from_postcode("2600") == "ACT"
    assert state_from_postcode("9999") == "QLD"
    assert state_from_postcode("0000") is None
    assert state_from_postcode("abcd") is None
    assert state_from_postcode(None) is None


# (input, unit, number, remainder, state, postcode)
CASES = [
    # --- plain ---
    ("42 Wattle St, Newtown NSW 2042", None, "42", "WATTLE ST NEWTOWN", "NSW", "2042"),
    ("42 Wattle Street Newtown", None, "42", "WATTLE STREET NEWTOWN", None, None),
    # --- unit forms ---
    ("3/42 Wattle Street, Newtown, New South Wales 2042",
     "3", "42", "WATTLE STREET NEWTOWN", "NSW", "2042"),
    ("Unit 5, 10-12 Smith Rd Richmond VIC 3121",
     "5", "10-12", "SMITH RD RICHMOND", "VIC", "3121"),
    ("U3 42 Wattle St Newtown NSW 2042",
     "3", "42", "WATTLE ST NEWTOWN", "NSW", "2042"),
    ("Unit 3/42 Wattle St Newtown NSW 2042",
     "3", "42", "WATTLE ST NEWTOWN", "NSW", "2042"),
    ("Apt 12, 5 Hay Street Perth WA 6000",
     "12", "5", "HAY STREET PERTH", "WA", "6000"),
    # --- messy / lowercase / misspelt suburb (fuzzy layer's job, not the parser's) ---
    ("42a wattle st newton nsw", None, "42A", "WATTLE ST NEWTON", "NSW", None),
    ("  42   wattle   st,,  newtown   nsw   2042  ",
     None, "42", "WATTLE ST NEWTOWN", "NSW", "2042"),
    # --- long state names ---
    ("1 Queen St Brisbane Queensland 4000", None, "1", "QUEEN ST BRISBANE", "QLD", "4000"),
    ("9 Elder St Adelaide South Australia 5000", None, "9", "ELDER ST ADELAIDE", "SA", "5000"),
    # --- number ranges and alpha suffixes ---
    ("100-102 Collins St Melbourne VIC 3000",
     None, "100-102", "COLLINS ST MELBOURNE", "VIC", "3000"),
    ("7B Short St Hobart TAS 7000", None, "7B", "SHORT ST HOBART", "TAS", "7000"),
    # --- a 4-digit street number AND a postcode: last valid one wins ---
    ("2042 Pacific Highway Lindfield NSW 2070",
     None, "2042", "PACIFIC HIGHWAY LINDFIELD", "NSW", "2070"),
]


@pytest.mark.parametrize("raw,unit,number,remainder,state,postcode", CASES)
def test_parse(raw, unit, number, remainder, state, postcode):
    p = parse(raw)
    assert p.unit == unit, f"unit: {p}"
    assert p.number == number, f"number: {p}"
    assert p.remainder == remainder, f"remainder: {p}"
    assert p.state == state, f"state: {p}"
    assert p.postcode == postcode, f"postcode: {p}"


def test_postcode_beats_conflicting_state_text():
    p = parse("42 Wattle St Newtown VIC 2042")
    assert p.state == "NSW"          # postcode is authoritative
    assert any("conflicts" in w for w in p.warnings)


def test_narrowable():
    assert parse("42 Wattle St Newtown NSW 2042").is_narrowable
    assert parse("42 Wattle St Newtown NSW").is_narrowable
    assert not parse("42 Wattle Street Newtown").is_narrowable


def test_empty_and_junk():
    assert parse("").warnings
    assert parse("   ").warnings
    p = parse("NSW 2042")
    assert p.remainder == ""
    assert "no street/locality text found" in p.warnings


def test_apostrophes_are_not_unit_prefixes():
    # "L'Estrange" normalises to "L ESTRANGE" - must not read L as a level prefix
    p = parse("14 L'Estrange St Glenelg SA 5045")
    assert p.number == "14"
    assert p.unit is None
    assert "ESTRANGE" in p.remainder


@pytest.mark.parametrize("raw,unit,number", [
    ("Unit 3/42 Wattle St Newtown NSW 2042", "3", "42"),
    ("Apartment 7, 200 Bourke St Melbourne VIC 3000", "7", "200"),
    ("Level 2, 100 George St Sydney NSW 2000", "2", "100"),
    ("Suite 4/16 Barrack St Sydney NSW 2000", "4", "16"),
])
def test_unit_separator_forms(raw, unit, number):
    p = parse(raw)
    assert (p.unit, p.number) == (unit, number), p


def test_building_name_before_number_is_left_to_the_fuzzy_layer():
    """A building name between unit and street number is genuinely ambiguous.

    The parser deliberately does NOT guess: it keeps the text in `remainder`
    so trigram matching can resolve it against real G-NAF rows. Contorting the
    regex to handle building names would break ordinary addresses.
    """
    p = parse("Shop 12 Westfield 500 Oxford St Bondi Junction NSW 2022")
    assert p.unit == "12"
    assert p.number is None                    # not guessed
    assert "500 OXFORD ST" in p.remainder      # preserved for fuzzy matching
    assert p.postcode == "2022"
    assert p.is_narrowable


def test_unity_street_is_not_a_unit():
    p = parse("5 Unity Place Parramatta NSW 2150")
    assert p.unit is None
    assert p.number == "5"
    assert "UNITY PLACE" in p.remainder
