# ausgeo

A free geocoding API for Australian addresses, built on open government data.

Australia publishes **[G-NAF](https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf)** —
the Geocoded National Address File — 15.9 million validated addresses with
coordinates, maintained by Geoscape from state and territory government data,
free under CC BY 4.0 and updated quarterly.

It ships as pipe-separated files across a dozen relational tables. So most
Australian developers pay Google roughly $5 per 1,000 requests to geocode data
their own government already gives away.

This does the annoying part once, in public.

> **Status: in development.** Not deployed yet. The search layer works against a
> fixture; the full 15.9M-row load is in progress.

## How it works

Naively trigram-matching a query against 15.9M rows is both slow and imprecise.
Instead:

```
1. Parse out what's certain          postcode, state, unit, street number
2. Narrow on indexed columns         15.9M rows -> a few hundred candidates
3. Fuzzy match the ambiguous rest    street + locality, via pg_trgm
4. Score and rank                    0.60 text + 0.28 number + 0.12 unit
```

Narrowing before fuzzy matching is what makes it fast *and* accurate.

Search escalates through tiers, most selective first, stopping at the first that
returns anything:

`postcode+number` → `postcode` → `state+number` → `state` → `unnarrowed`

### What it handles

| Input | Result |
|---|---|
| `42 Wattle St, Newtown NSW 2042` | exact match |
| `3/42 Wattle St Newtown NSW 2042` | selects unit 3 |
| `42 Wattle St Newtown NSW 2042` | prefers the row **without** a unit — absence is a signal |
| `42 wattle street newton nsw` | misspelt suburb still resolves to NEWTOWN |
| `Level 2, 100 George St Sydney 2000` | state inferred from postcode |
| `2042 Pacific Hwy Lindfield NSW 2070` | 4-digit street number ≠ postcode |
| `Unit 5, 10-12 Smith Rd Richmond VIC 3121` | unit + number range |
| `14 L'Estrange St Glenelg SA 5045` | punctuation in street names |
| `999 Nonexistent Rd Nowhere NSW 2042` | **no match** — better than a confident wrong answer |

### What it deliberately doesn't do

`Shop 12 Westfield 500 Oxford St` has a building name between the unit and the
street number. The parser does **not** guess — it keeps the text for the fuzzy
layer to resolve against real rows. Contorting the regex to handle building
names breaks ordinary addresses.

## Stack

Postgres 17 + `pg_trgm` · FastAPI · psycopg 3 · Docker.
Data loading leans on [gnaf-loader](https://github.com/minus34/gnaf-loader) —
no point rebuilding a loader that already exists.

## Running it

```bash
docker compose up -d
docker exec -i geocoder-db psql -U geocoder -d gnaf -q < sql/01_schema.sql
docker exec -i geocoder-db psql -U geocoder -d gnaf -q < tests/fixtures/seed.sql
docker exec -i geocoder-db psql -U geocoder -d gnaf -q < sql/02_indexes.sql

uv sync
uv run pytest
uv run python scripts/try_search.py "42 Wattle St Newtown NSW 2042"
```

## Attribution

Incorporates or developed using G-NAF © Geoscape Australia, licensed by the
Commonwealth of Australia under the
[Open Geo-coded National Address File (G-NAF) End User Licence Agreement](https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf).

Note: the open G-NAF licence prohibits using the data to compile addresses for
sending mail without verifying deliverability against a secondary source.

## Licence

MIT
