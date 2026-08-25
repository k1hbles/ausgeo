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

> **Status: in development.** Not deployed yet — no public API.
> Running locally against the full **15,057,532-address** G-NAF load.
> Median query **4ms**, worst observed **201ms**.

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

## API

```bash
curl "http://localhost:8000/v1/geocode?q=79 St Marys St Newtown NSW 2042&limit=1"
```

```json
{
  "query": "79 St Marys St Newtown NSW 2042",
  "parsed": {
    "unit": null, "number": "79", "street_locality": "ST MARYS ST NEWTOWN",
    "state": "NSW", "postcode": "2042", "warnings": []
  },
  "results": [{
    "gnaf_pid": "GANSW717621373",
    "address": "79 ST MARYS STREET NEWTOWN NSW 2042",
    "components": {
      "unit": null, "number": "79", "street": "ST MARYS STREET",
      "locality": "NEWTOWN", "state": "NSW", "postcode": "2042"
    },
    "location": { "lat": -33.89443499, "lon": 151.17390962 },
    "score": 0.8818,
    "match": "postcode+number"
  }],
  "took_ms": 17.86
}
```

Structured input works too, and runs through the same pipeline:

```bash
curl "http://localhost:8000/v1/geocode?number=101&street=Collins+St&locality=Melbourne&state=VIC&postcode=3000"
```

### Endpoints

| | |
|---|---|
| `GET /v1/geocode` | `q`, or any of `number` `street` `locality` `state` `postcode`; plus `limit` (1–20) |
| `POST /v1/keys` | issue a free key — `{"email": "...", "label": "..."}` |
| `GET /health` | status and row count |
| `GET /docs` | interactive OpenAPI docs |

### Rate limits

| Tier | Limit | How |
|---|---|---|
| Anonymous | 100/day per IP | no key needed — the docs examples just work |
| Free key | 2,500/day | `X-API-Key: ausgeo_...` |

Every response carries `X-RateLimit-Limit` and `X-RateLimit-Remaining`.
Limits reset at UTC midnight. Key issuance is throttled to 3 per IP per day.

### Errors

`422` bad or missing parameters · `401` unknown or revoked key ·
`429` rate limited. **A query that matches nothing returns `200` with an empty
`results` array** — not an error, and never a confident wrong answer.

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

To load the real 15.9M-address dataset instead of the fixture:

```bash
# ~2GB. See github.com/minus34/gnaf-loader for other access methods.
curl -o data/gnaf.dmp https://minus34.com/opendata/geoscape-202605-gda2020/gnaf-202605.dmp

docker exec geocoder-db psql -U geocoder -d gnaf -c "CREATE SCHEMA IF NOT EXISTS gnaf_202605_gda2020;"
docker exec geocoder-db pg_restore -U geocoder -d gnaf --no-owner --no-privileges \
  -t address_principals /data/gnaf.dmp

uv run python scripts/load_gnaf.py --truncate           # ~100s
docker exec -i geocoder-db psql -U geocoder -d gnaf -q < sql/02_indexes.sql
docker exec -i geocoder-db psql -U geocoder -d gnaf -q < sql/03_api.sql
docker exec geocoder-db psql -U geocoder -d gnaf -c \
  "ALTER DATABASE gnaf SET pg_trgm.similarity_threshold = 0.45;"
```

Then run the API:

```bash
uv run uvicorn geocoder.api:app --reload
# http://localhost:8000/docs
```

**Apple Silicon note:** `postgis/postgis` has no arm64 build; this uses
`imresamu/postgis`, which does.

## Attribution

Incorporates or developed using G-NAF © Geoscape Australia, licensed by the
Commonwealth of Australia under the
[Open Geo-coded National Address File (G-NAF) End User Licence Agreement](https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf).

Note: the open G-NAF licence prohibits using the data to compile addresses for
sending mail without verifying deliverability against a secondary source.

## Licence

MIT
