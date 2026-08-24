"""Transform G-NAF's address_principals into our search-shaped `address` table.

Source (from gnaf-loader's dump) carries far more than geocoding needs: census
boundaries, legal parcel ids, aliases, PostGIS geometry. We take only the
columns that serve the narrow-then-fuzzy search and precompute the two derived
fields it depends on: `number_int` (for cheap equality narrowing) and
`search_text` (the trigram target).

Run AFTER pg_restore of the source schema, and BEFORE sql/02_indexes.sql --
building indexes on an already-populated table is far faster.
"""

from __future__ import annotations

import argparse
import time

import psycopg

from geocoder.db import DATABASE_URL

# Street number: number_first, optionally a range with number_last.
# Unit: flat_number, falling back to level_number for "Level 2" style addresses.
TRANSFORM = """
INSERT INTO address (
    gnaf_pid, unit, number, number_int,
    street, locality, state, postcode,
    lat, lon, reliability, search_text
)
SELECT
    gnaf_pid,
    -- G-NAF stores flat_number as 'UNIT 1' and level_number as 'LEVEL 2',
    -- i.e. with the prefix word included. The parser yields a bare '1', so we
    -- strip the leading word here or exact unit matching can never succeed.
    NULLIF(regexp_replace(
        COALESCE(flat_number, level_number, ''), '^\s*[A-Za-z]+\s+', ''), '')  AS unit,
    NULLIF(
        CASE
            WHEN number_last IS NOT NULL AND number_last <> ''
                THEN number_first || '-' || number_last
            ELSE number_first
        END, '')                                                       AS number,
    NULLIF(regexp_replace(COALESCE(number_first, ''), '\\D', '', 'g'), '')::bigint
        AS number_int,
    btrim(regexp_replace(
        upper(concat_ws(' ', street_name, street_type, street_suffix)),
        '\\s+', ' ', 'g'))                                             AS street,
    upper(locality_name)                                               AS locality,
    upper(state)                                                       AS state,
    NULLIF(COALESCE(postcode, locality_postcode), '')                  AS postcode,
    latitude::double precision                                         AS lat,
    longitude::double precision                                        AS lon,
    reliability,
    btrim(regexp_replace(
        upper(concat_ws(' ', street_name, street_type, street_suffix, locality_name)),
        '\\s+', ' ', 'g'))                                             AS search_text
FROM {src}.address_principals
WHERE latitude IS NOT NULL
  AND longitude IS NOT NULL
  AND street_name IS NOT NULL
  AND locality_name IS NOT NULL
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-schema", default="gnaf_202605_gda2020")
    ap.add_argument("--truncate", action="store_true",
                    help="clear the address table first (drops the dev fixture)")
    args = ap.parse_args()

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT to_regclass(%s) IS NOT NULL",
            (f"{args.src_schema}.address_principals",),
        ).fetchone()[0]
        if not exists:
            raise SystemExit(
                f"{args.src_schema}.address_principals not found. "
                "Restore the dump first."
            )

        src_n = conn.execute(
            f"SELECT count(*) FROM {args.src_schema}.address_principals"
        ).fetchone()[0]
        print(f"source rows: {src_n:,}")

        if args.truncate:
            conn.execute("TRUNCATE address RESTART IDENTITY")
            print("truncated address")

        # number_int is bigint in the source expression but smallint-safe here;
        # widen the column if an earlier schema created it as integer.
        conn.execute("ALTER TABLE address ALTER COLUMN number_int TYPE bigint")

        t0 = time.perf_counter()
        conn.execute(TRANSFORM.format(src=args.src_schema))
        dt = time.perf_counter() - t0

        out_n = conn.execute("SELECT count(*) FROM address").fetchone()[0]
        print(f"loaded {out_n:,} rows in {dt:,.1f}s ({out_n / max(dt, 1e-9):,.0f} rows/s)")
        print(f"dropped {src_n - out_n:,} rows lacking coords/street/locality")
        print("\nnext: docker exec -i geocoder-db psql -U geocoder -d gnaf -q < sql/02_indexes.sql")


if __name__ == "__main__":
    main()
