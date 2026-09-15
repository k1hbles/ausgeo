# Resume here

Everything needed to pick this up cold. Last worked on **2026-08-25**.

---

## Get back to a running state

```bash
open -a OrbStack                      # docker backend (not Docker Desktop)
cd ~/openint/geocoder
docker compose up -d                  # postgres+postgis on host port 5433
uv sync
uv run pytest                         # expect 47 passed, 10 skipped
uv run uvicorn geocoder.api:app --reload
open http://localhost:8000/docs
```

**If the `pgdata` volume is gone**, the 15M rows must be reloaded — see
"Loading the real dataset" in [README.md](README.md). Budget ~5 minutes:
~30s restore, ~100s ETL, ~62s indexes. The 2GB `.dmp` lives in `data/`
(gitignored); re-download if missing.

Verify with: `curl -s localhost:8000/health` → should report **15,057,532**.

---

## Where it stands

**Done** — parser, narrow-then-fuzzy search, full 15,057,532-address load,
API with keys and rate limiting, 47 tests, 3 commits pushed to
[github.com/k1hbles/ausgeo](https://github.com/k1hbles/ausgeo) (public).

Median query **4ms**, worst observed **~400ms** (the no-match path).

**Definition of done — 5 of 7 met:**

| | |
|---|---|
| ✅ | `GET /v1/geocode` returns lat/lng + confidence + components |
| ✅ | Handles the messy input patterns (see README table) |
| ✅ | p95 < 200ms |
| ✅ | Free tier, API keys, rate limiting |
| ✅ | Docs page (generated OpenAPI at `/docs`) |
| ❌ | **Deployed, real domain, HTTPS** |
| ✅ | Public repo with README explaining the method |

---

## The next thing, and it's the gate

**Hand-build a 100-address test set and measure top-1 accuracy. Target ≥90%.**

This is the one task that cannot be delegated, because it needs addresses *you*
choose — ideally ones you'd type badly, from places you know. Everything else is
plumbing that already works.

Method:
1. Put 100 real addresses in `tests/fixtures/accuracy.csv` as
   `query,expected_gnaf_pid` — write the query the way a *user* would type it
   (abbreviations, lowercase, missing postcode, misspelt suburb), not the way
   G-NAF stores it.
2. Find each expected PID by querying the DB for the canonical form.
3. Script it: run each query, check whether `results[0].gnaf_pid` matches.
4. Report top-1 and top-3 accuracy. Iterate on the weights in `search.py`
   (`W_TEXT`, `W_NUMBER`, `W_NUMBER_EXACT`, `W_UNIT`) and on
   `pg_trgm.similarity_threshold`.

Then: deploy behind Caddy on a VPS with a real domain, and launch.

---

## Environment gotchas (all cost time once already)

- **Docker backend is OrbStack**, not Docker Desktop. `open -a OrbStack`.
- **Apple Silicon:** `postgis/postgis` has **no arm64 build**. Use
  `imresamu/postgis:17-3.5` (already in `docker-compose.yml`).
- **Postgres is on host port 5433**, not 5432.
- **Never reuse a `pgdata` volume across different base images** — it caused a
  glibc collation version mismatch, which is a real correctness risk for text
  indexes. Recreate the volume instead.
- `pg_trgm.similarity_threshold` is **0.45**, set as a database default. It is
  load-bearing: at 0.3 a typical query matches ~13,300 rows, at 0.45 about 51.
  Changing it changes both latency and accuracy.

---

## Things learned the hard way (don't re-derive)

1. **G-NAF stores `flat_number` as `'UNIT 1'`, not `'1'`.** The ETL strips the
   leading word. Without it, exact unit matching fails across 4.3M rows.
2. **The GIN trigram index is lossy** — it returned 522,878 candidates of which
   509,551 failed recheck. On a *narrowed* tier the `BitmapAnd` still scans the
   whole GIN index (~920ms) and costs more than it saves, so narrowed tiers use
   no trigram predicate at all. This took broad queries 11,595ms → 34ms.
3. **`number_int` collapses `1`/`1A`/`1E`**, hence the separate exact-string
   bonus.
4. **Scoring must happen in SQL, not Python.** Rows on one street share an
   identical `search_text`, so ordering by similarity alone is arbitrary among
   them and `LIMIT` truncates correct answers before they can be scored.
5. **`X-Forwarded-For` is attacker-controlled.** The usage tables use `text`,
   not `inet`; a malformed header against an `inet` column is a 500.
6. **`200 George St Sydney` returning only unit addresses is not a bug** — there
   is no plain "200 GEORGE STREET" in G-NAF; the non-unit rows are `200A`/`200B`.
   Check the data before "fixing" a ranking.

---

## Scope discipline

`v2.md` holds everything deliberately deferred: reverse geocoding, batch CSV
(the monetisation path), autocomplete, libpostal, boundary enrichment, billing,
accounts, other countries, a designed landing page.

**Nothing from that list goes into v1.** The documented failure mode on this
project is scope creep, not capability.

---

## Honest note on timing

The plan in `../docs/13-ship1-geocoder.md` set a **three-week hard stop** with
the instruction to ship even if imperfect. Work happened on 24–25 August; this
file was written 15 September. The build is ~85% done and stalled one task short
of the accuracy gate.

That is the exact pattern the plan was written to interrupt. The remaining work
is one afternoon: the test set, a $20 VPS, and a DNS record.
