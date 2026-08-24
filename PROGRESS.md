# Progress — ship #1 geocoder

Build log for the ship-1 geocoder. Three-week scope, hard stop.

## Session 1 — 2026-08-24

### Done
- **Scaffold**: uv project, Postgres 17 in Docker (OrbStack), ruff, pytest
- **`parse.py`** — the hard part of week 2, done early. Peels off postcode,
  state, unit, street number; leaves street+locality as `remainder` for fuzzy
  matching. Handles: `3/42`, `Unit 3/42`, `U3 42`, `Apartment 7,`, `Level 2,`,
  number ranges `10-12`, alpha suffixes `42A`, long state names, missing state
  inferred from postcode, and a 4-digit street number correctly distinguished
  from a postcode.
- **`sql/01_schema.sql`** — clean denormalised `address` table (deliberately not
  G-NAF's shape), `sql/02_indexes.sql` — narrowing btrees + GIN trigram.
- **`search.py`** — narrow-then-fuzzy with tier escalation:
  `postcode+number → postcode → state+number → state → unnarrowed`.
  Composite score: 0.60 text similarity + 0.28 number + 0.12 unit.
- **35 tests passing** (25 parser, 10 search integration against a 20-row fixture).

### Bugs found and fixed during the session
1. **`Unit 3/42` didn't parse** — prefix regex demanded whitespace after the unit
   number, but a slash follows. Made the separator space/comma/dash/slash.
2. **Broad tiers had no trigram predicate** — `state = 'NSW'` would have sorted
   millions of rows by `similarity()`. Added the GIN-indexed predicate to every
   tier except `postcode+number`, where the set is tiny and we deliberately want
   all candidates even if the street is badly misspelt.
3. **Unit absence wasn't a signal** — a query with no unit couldn't distinguish
   `42 Wattle St` from `3/42 Wattle St`. Now `unit IS NOT DISTINCT FROM %(unit)s`,
   so absence matches absence.
4. Illegible scoring expression (`W_TEXT * x / W_TEXT * 0.85`) rewritten.

### Deliberate non-goal
`Shop 12 Westfield 500 Oxford St` — a building name between unit and street
number. The parser does **not** guess; it keeps the text in `remainder` for the
fuzzy layer. Contorting the regex to handle building names would break ordinary
addresses. Documented as a test.

### In flight
- Downloading `gnaf-202605-gda2020.dmp` (~2.0GB) from minus34.com. Background.

### Next session
1. `pg_restore` the dump into a staging database
2. Inspect the source schema — find the table holding addresses + coordinates
3. Write `scripts/load_gnaf.py`: staging → our `address` table, building
   `search_text` and `number_int`
4. Rebuild indexes on 15.9M rows, measure query time
5. **Build the 100-address test set by hand** and measure top-1 accuracy.
   Target ≥90%. This is week 2's real deliverable.

### Notes
- Postgres on host port **5433** (not 5432) to avoid clashing with anything local.
- Handy: `uv run python scripts/try_search.py "some address"`

## Session 2 — 2026-08-25 · real data

**15,057,532 addresses loaded.** Median query 4ms, worst 201ms.

### Timings
| Step | Time |
|---|---|
| `pg_restore` of `address_principals` | ~30s |
| ETL into `address` | **100.8s** (149,422 rows/s), 0 dropped |
| All indexes incl. GIN trigram | ~62s |
| Table + indexes on disk | 3.6 GB |

### Environment
- Apple Silicon: `postgis/postgis` has **no arm64 build**. Using
  `imresamu/postgis:17-3.5`, which does.
- Reusing a data volume across base images caused a **collation version
  mismatch** (glibc 2.41 vs 2.36) — genuine correctness risk for text indexes,
  so the volume was recreated clean.

### Bugs only real data could expose
1. **`flat_number` is `'UNIT 1'`, not `'1'`.** The parser yields a bare `1`, so
   exact unit matching could never have succeeded — 4.3M rows affected. ETL now
   strips the leading word.
2. **Broad tiers took 11.6 seconds.** `EXPLAIN` showed the GIN trigram index is
   *lossy*: it returned 522,878 candidates of which 509,551 failed recheck, then
   heap-scanned 138,851 blocks to reach 15 rows. Two fixes:
   - added `(state, number_int)` index;
   - **removed the trigram predicate from narrowed tiers entirely** — on a
     selective tier the `BitmapAnd` still scans the whole GIN index (~920ms) and
     costs more than it saves. Only `state`-only and `unnarrowed` use it now.
   - raised `pg_trgm.similarity_threshold` 0.3 → **0.45** (db default): cuts
     candidates from ~13,300 to ~51. The misspelt-suburb case scores 0.583, so
     it still passes.
   - **11,595ms → 34ms.**
3. **`1 Macquarie Street` returned `1E` and `1A`.** `number_int` strips alpha
   suffixes so 1/1A/1E collide. Added an exact-number-string bonus (0.14).
4. **Scoring moved from Python into SQL.** Rows on one street share an identical
   `search_text`, so ordering by similarity alone was arbitrary among them and
   `LIMIT cap` could truncate correct answers before scoring. Latent, real.

### Investigated, not a bug
`200 George St Sydney 2000` returns only unit addresses. There is no plain
"200 GEORGE STREET" in G-NAF — the two non-unit rows are `200A` and `200B`.
All 104 candidates were scored; nothing was truncated. Ranking `29/200` (exact
number `200`) above `200A` is correct.

### Tests
37 passing, 10 skipped. `test_search.py` (fixture) auto-skips once real data is
loaded; `test_search_real.py` asserts against the full dataset including a
500ms latency ceiling.

### Next
1. FastAPI endpoint + API keys + rate limiting
2. **Hand-build the 100-address test set; measure top-1 accuracy. Target ≥90%.**
3. Deploy behind Caddy on a VPS, real domain
4. Docs page, then launch
