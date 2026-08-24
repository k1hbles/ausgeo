"""Ad-hoc search harness. usage: uv run python scripts/try_search.py "42 Wattle St Newtown NSW 2042" """

import sys

from geocoder.db import close_pool, open_pool, pool
from geocoder.search import geocode

DEFAULTS = [
    "42 Wattle St, Newtown NSW 2042",
    "3/42 Wattle St Newtown NSW 2042",
    "42 wattle street newton nsw",
    "Unit 5, 10-12 Smith Rd Richmond VIC 3121",
    "100 george st sydney",
    "999 Nonexistent Rd Nowhere NSW 2042",
]


def main() -> None:
    queries = sys.argv[1:] or DEFAULTS
    open_pool()
    try:
        with pool.connection() as conn:
            for q in queries:
                matches, p = geocode(conn, q, limit=3)
                print(f"\nQ: {q!r}")
                print(f"   parsed: unit={p.unit} num={p.number} rem={p.remainder!r} "
                      f"state={p.state} pc={p.postcode}")
                if not matches:
                    print("   -> NO MATCH")
                for m in matches:
                    print(f"   -> [{m.score:.3f}] {m.gnaf_pid} {m.address}  "
                          f"({m.lat:.4f},{m.lon:.4f}) tier={m.tier}")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
