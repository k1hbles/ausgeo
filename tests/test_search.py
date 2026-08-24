"""Integration tests for the narrow-then-fuzzy search.

Requires the Postgres container and the fixture:
    docker compose up -d
    docker exec -i geocoder-db psql -U geocoder -d gnaf -q < sql/01_schema.sql
    docker exec -i geocoder-db psql -U geocoder -d gnaf -q < tests/fixtures/seed.sql
    docker exec -i geocoder-db psql -U geocoder -d gnaf -q < sql/02_indexes.sql

Skipped automatically when the database isn't reachable.
"""

from __future__ import annotations

import pytest

psycopg = pytest.importorskip("psycopg")

from geocoder.db import DATABASE_URL  # noqa: E402
from geocoder.search import geocode  # noqa: E402


@pytest.fixture(scope="module")
def conn():
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database unavailable: {exc}")
    with c:
        n = c.execute("select count(*) from address").fetchone()[0]
        if n == 0:
            pytest.skip("address table is empty - seed the fixture first")
        yield c


def top(conn, q):
    matches, _ = geocode(conn, q, limit=5)
    return matches


def test_exact_match_wins(conn):
    m = top(conn, "42 Wattle St, Newtown NSW 2042")
    assert m[0].gnaf_pid == "FIX0002"
    assert m[0].tier == "postcode+number"
    assert m[0].score == pytest.approx(1.0, abs=1e-6)


def test_no_unit_in_query_prefers_row_without_unit(conn):
    """Absence of a unit is a signal: must outrank 3/42 and 7/42."""
    m = top(conn, "42 Wattle St, Newtown NSW 2042")
    assert m[0].unit is None
    assert m[0].score > m[1].score


def test_unit_in_query_selects_that_unit(conn):
    m = top(conn, "3/42 Wattle St Newtown NSW 2042")
    assert m[0].gnaf_pid == "FIX0003"
    assert m[0].unit == "3"


def test_misspelt_suburb_still_beats_exact_street_in_wrong_suburb(conn):
    """'newton' should resolve to NEWTOWN, above an exact 'WATTLE STREET' in PUNCHBOWL."""
    m = top(conn, "42 wattle street newton nsw")
    assert m[0].locality == "NEWTOWN"
    localities = [x.locality for x in m]
    assert "PUNCHBOWL" in localities
    assert localities.index("NEWTOWN") < localities.index("PUNCHBOWL")


def test_four_digit_street_number_not_confused_with_postcode(conn):
    m = top(conn, "2042 Pacific Hwy Lindfield NSW 2070")
    assert m[0].gnaf_pid == "FIX0019"
    assert m[0].number == "2042"
    assert m[0].postcode == "2070"


def test_number_range_and_unit(conn):
    m = top(conn, "Unit 5, 10-12 Smith Rd Richmond VIC 3121")
    assert m[0].gnaf_pid == "FIX0013"


def test_locality_disambiguates_same_street_name(conn):
    assert top(conn, "42 Wattle St Ultimo NSW 2007")[0].locality == "ULTIMO"
    assert top(conn, "42 Wattle St Newtown NSW 2042")[0].locality == "NEWTOWN"


def test_tier_escalation_when_no_postcode_or_state(conn):
    m = top(conn, "100 george st sydney")
    assert m[0].gnaf_pid == "FIX0008"
    assert m[0].tier == "unnarrowed"


def test_nonsense_returns_nothing_rather_than_a_confident_wrong_answer(conn):
    assert top(conn, "999 Nonexistent Rd Nowhere NSW 2042") == []


def test_apostrophe_street(conn):
    assert top(conn, "14 L'Estrange St Glenelg SA 5045")[0].gnaf_pid == "FIX0020"
