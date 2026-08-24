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
W_TEXT = 0.60
W_NUMBER = 0.28
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
    TRGM = "search_text %% %(q)s"

    if p.postcode and n is not None:
        out.append(("postcode+number",
                    "postcode = %(postcode)s AND number_int = %(n)s",
                    {"postcode": p.postcode, "n": n}))
    if p.postcode:
        out.append(("postcode",
                    f"postcode = %(postcode)s AND {TRGM}",
                    {"postcode": p.postcode}))
    if p.state and n is not None:
        out.append(("state+number",
                    f"state = %(state)s AND number_int = %(n)s AND {TRGM}",
                    {"state": p.state, "n": n}))
    if p.state:
        out.append(("state",
                    f"state = %(state)s AND {TRGM}",
                    {"state": p.state}))
    # Last resort: no narrowing at all. Relies entirely on the trigram index.
    out.append(("unnarrowed", TRGM, {}))
    return out


SQL = """
SELECT gnaf_pid, unit, number, street, locality, state, postcode, lat, lon,
       similarity(search_text, %(q)s) AS text_sim,
       (number_int IS NOT NULL AND number_int = %(n)s) AS number_hit,
       -- absence of a unit is itself a match: a query with no unit should
       -- prefer "42 Wattle St" over "3/42 Wattle St"
       (unit IS NOT DISTINCT FROM %(unit)s) AS unit_hit
FROM address
WHERE {where}
ORDER BY similarity(search_text, %(q)s) DESC
LIMIT %(cap)s
"""


def geocode(conn, raw: str, limit: int = 5, cap: int = 400) -> tuple[list[Match], ParsedAddress]:
    """Geocode one address string. Returns (matches, parse result)."""
    p = parse(raw)
    if not p.remainder:
        return [], p

    n = _number_int(p.number)

    for tier_name, where, extra in _tiers(p):
        params = {"q": p.remainder, "n": n, "unit": p.unit, "cap": cap, **extra}
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(SQL.format(where=where), params)
            rows = cur.fetchall()
        if not rows:
            continue

        matches = []
        for r in rows:
            text_sim = float(r["text_sim"] or 0.0)
            if n is None:
                # No street number supplied, so nothing to match it against.
                # Text similarity carries the whole score, discounted because
                # we are working from less evidence.
                score = 0.85 * text_sim
            else:
                score = (
                    W_TEXT * text_sim
                    + W_NUMBER * (1.0 if r["number_hit"] else 0.0)
                    + W_UNIT * (1.0 if r["unit_hit"] else 0.0)
                )
            if score < MIN_SCORE:
                continue
            matches.append(
                Match(
                    gnaf_pid=r["gnaf_pid"],
                    address=_format(r),
                    unit=r["unit"], number=r["number"], street=r["street"],
                    locality=r["locality"], state=r["state"], postcode=r["postcode"],
                    lat=r["lat"], lon=r["lon"],
                    score=round(min(score, 1.0), 4), tier=tier_name,
                )
            )
        if matches:
            matches.sort(key=lambda m: m.score, reverse=True)
            return matches[:limit], p

    return [], p


def _format(r: dict) -> str:
    head = f"{r['unit']}/{r['number']}" if r["unit"] else (r["number"] or "")
    parts = [p for p in (head, r["street"], r["locality"], r["state"], r["postcode"]) if p]
    return " ".join(parts)
