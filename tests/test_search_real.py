"""Assertions against the real G-NAF load (15M rows).

Skipped unless the address table actually holds the full dataset. These encode
behaviour verified by hand during the first real-data session, including three
bugs that only real data exposed.
"""

from __future__ import annotations

import time

import pytest

psycopg = pytest.importorskip("psycopg")

from geocoder.db import DATABASE_URL  # noqa: E402
from geocoder.search import geocode  # noqa: E402

MIN_REAL_ROWS = 1_000_000


@pytest.fixture(scope="module")
def conn():
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception as exc:  # noqa: BLE001  # pragma: no cover
        pytest.skip(f"database unavailable: {exc}")
    with c:
        n = c.execute("select count(*) from address").fetchone()[0]
        if n < MIN_REAL_ROWS:
            pytest.skip(f"only {n:,} rows; real G-NAF not loaded")
        yield c


def top(conn, q, limit=5):
    matches, _ = geocode(conn, q, limit=limit)
    return matches


def test_exact_address(conn):
    m = top(conn, "79 St Marys Street Newtown NSW 2042")
    assert m[0].number == "79"
    assert m[0].street == "ST MARYS STREET"
    assert m[0].locality == "NEWTOWN"
    assert m[0].unit is None
    assert m[0].score == pytest.approx(1.0, abs=1e-6)
    assert -34 < m[0].lat < -33 and 150 < m[0].lon < 152


def test_abbreviated_street_type_still_matches(conn):
    """G-NAF stores 'STREET'; users type 'St'. Trigram must bridge it."""
    m = top(conn, "79 St Marys St Newtown NSW 2042")
    assert m[0].street == "ST MARYS STREET"
    assert m[0].number == "79"


def test_unit_prefix_stripped_from_gnaf(conn):
    """G-NAF stores flat_number as 'UNIT 1'; the ETL must strip it to '1'."""
    m = top(conn, "unit 1/79 st marys st newtown nsw 2042")
    assert m[0].unit == "1"
    assert m[0].number == "79"


def test_misspelt_suburb_without_postcode(conn):
    m = top(conn, "79 st marys st newton nsw")
    assert m[0].locality == "NEWTOWN"
    assert m[0].unit is None


def test_exact_number_beats_alpha_suffix(conn):
    """number_int collapses 1 / 1A / 1E, so plain '1' must win on exact string."""
    m = top(conn, "1 Macquarie Street Sydney NSW 2000")
    assert m[0].number == "1"
    assert m[0].unit is None


def test_no_state_supplied(conn):
    m = top(conn, "101 Collins St Melbourne VIC 3000")
    assert m[0].locality == "MELBOURNE"
    assert m[0].number == "101"


def test_nonsense_returns_nothing(conn):
    assert top(conn, "999999 Fakename Rd Nowhere NSW 2042") == []


@pytest.mark.parametrize("q", [
    "79 St Marys Street Newtown NSW 2042",
    "101 Collins St Melbourne VIC 3000",
    "1 Macquarie Street Sydney NSW 2000",
    "79 st marys st newton nsw",
    "999999 Fakename Rd Nowhere NSW 2042",
])
def test_latency_under_500ms(conn, q):
    geocode(conn, q)                       # warm
    t0 = time.perf_counter()
    geocode(conn, q)
    ms = (time.perf_counter() - t0) * 1000
    assert ms < 500, f"{q!r} took {ms:.0f}ms"
