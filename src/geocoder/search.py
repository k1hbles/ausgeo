"""Narrow, then fuzzy match.

The whole performance and accuracy story is here. Trigram-matching 15.9M rows
directly is slow and imprecise. Instead we use the components the parser is
confident about (postcode, state, street number) as cheap indexed filters,
which cuts the candidate set to at most a few hundred rows, and only then run
similarity scoring on the ambiguous street+locality text.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from psycopg.rows import dict_row

from .parse import ParsedAddress, parse

# Weights for the composite score. Tuned against tests/fixtures/addresses.csv.
W_TEXT = 0.52
W_NUMBER = 0.22        # leading digits match (1 == 1A == 1E)
W_NUMBER_EXACT = 0.14  # full string match ("1" beats "1A")
W_UNIT = 0.12

# Below this, we'd rather return nothing than a confident wrong answer.
MIN_SCORE = 0.35


@dataclass
class Match:
    gnaf_pid: str
    address: str
    unit: str | None
    number: str | None
    street: str
    locality: str
    state: str
    postcode: str | None
    lat: float
    lon: float
    score: float
    tier: str          # which narrowing strategy produced it

    def as_dict(self) -> dict:
        return asdict(self)


def _number_int(number: str | None) -> int | None:
    if not number:
        return None
    m = re.match(r"\d+", number)
    return int(m.group()) if m else None


def _tiers(p: ParsedAddress) -> list[tuple[str, str, dict]]:
    """Narrowing strategies, most selective first."""
    n = _number_int(p.number)
    out: list[tuple[str, str, dict]] = []

    # TRGM is the GIN-indexed trigram predicate. It is required on any tier whose
    # candidate set is large, otherwise Postgres sorts millions of rows by
    # similarity(). It is deliberately OMITTED from postcode+number: that set is
    # tiny, and we want every candidate even when the street is badly misspelt.
    # Only the broad tiers below can afford the trigram index, and only
    # because pg_trgm.similarity_threshold is raised to 0.45 (set on the
    # database) which cuts candidates from ~13k to ~50 for a typical query.
    TRGM = "search_text %% %(q)s"

    if p.postcode and n is not None:
        out.append(("postcode+number",
                    "postcode = %(postcode)s AND number_int = %(n)s",
                    {"postcode": p.postcode, "n": n}))
    if p.postcode:
        # ~5,700 rows per postcode on average: cheaper to score them all than
        # to make Postgres scan the (lossy) GIN index.
        out.append(("postcode",
                    "postcode = %(postcode)s",
                    {"postcode": p.postcode}))
    if p.state and n is not None:
        out.append(("state+number",
                    "state = %(state)s AND number_int = %(n)s",
                    {"state": p.state, "n": n}))
    if p.state:
        out.append(("state",
                    f"state = %(state)s AND {TRGM}",
                    {"state": p.state}))
    # Last resort: no narrowing at all. Relies entirely on the trigram index.
    out.append(("unnarrowed", TRGM, {}))
    return out


# Scoring happens in SQL, not Python. Rows on one street share an identical
# search_text, so ordering by similarity alone is arbitrary among them and
# `LIMIT cap` silently truncated correct answers before they could be scored.
SQL = """
WITH scored AS (
    SELECT gnaf_pid, unit, number, street, locality, state, postcode, lat, lon,
           similarity(search_text, %(q)s)                    AS text_sim,
           (number_int IS NOT NULL AND number_int = %(n)s)   AS number_hit,
           -- number_int strips alpha suffixes, so 1 / 1A / 1E collide. An exact
           -- string match on the full number must outrank them.
           (number IS NOT DISTINCT FROM %(number_raw)s)      AS number_exact,
           -- absence of a unit is itself a match: a query with no unit should
           -- prefer "42 Wattle St" over "3/42 Wattle St"
           (unit IS NOT DISTINCT FROM %(unit)s)              AS unit_hit
    FROM address
    WHERE {where}
)
SELECT *,
       LEAST(1.0,
           CASE WHEN %(n)s IS NULL
                -- no street number supplied: text carries the score, discounted
                THEN 0.85 * text_sim + {w_unit} * unit_hit::int
                ELSE {w_text} * text_sim
                   + {w_number} * number_hit::int
                   + {w_exact} * number_exact::int
                   + {w_unit} * unit_hit::int
           END) AS score
FROM scored
ORDER BY score DESC
LIMIT %(cap)s
"""


def geocode(conn, raw: str, limit: int = 5, cap: int = 400) -> tuple[list[Match], ParsedAddress]:
    """Geocode one address string. Returns (matches, parse result)."""
    p = parse(raw)
    if not p.remainder:
        return [], p

    n = _number_int(p.number)
    sql_weights = {
        "w_text": W_TEXT, "w_number": W_NUMBER,
        "w_exact": W_NUMBER_EXACT, "w_unit": W_UNIT,
    }

    for tier_name, where, extra in _tiers(p):
        params = {"q": p.remainder, "n": n, "number_raw": p.number,
                  "unit": p.unit, "cap": cap, **extra}
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(SQL.format(where=where, **sql_weights), params)
            rows = cur.fetchall()

        matches = [
            Match(
                gnaf_pid=r["gnaf_pid"],
                address=_format(r),
                unit=r["unit"], number=r["number"], street=r["street"],
                locality=r["locality"], state=r["state"], postcode=r["postcode"],
                lat=r["lat"], lon=r["lon"],
                score=round(float(r["score"]), 4), tier=tier_name,
            )
            for r in rows
            if float(r["score"]) >= MIN_SCORE
        ]
        if matches:
            return matches[:limit], p

    return [], p


def _format(r: dict) -> str:
    head = f"{r['unit']}/{r['number']}" if r["unit"] else (r["number"] or "")
    parts = [p for p in (head, r["street"], r["locality"], r["state"], r["postcode"]) if p]
    return " ".join(parts)
