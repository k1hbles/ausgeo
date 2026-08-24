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
