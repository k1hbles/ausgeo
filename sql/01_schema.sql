-- Clean, denormalised target schema. Deliberately NOT G-NAF's shape:
-- we only keep what geocoding needs, arranged for the narrow-then-fuzzy search.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS address;
CREATE TABLE address (
    id          bigserial PRIMARY KEY,
    gnaf_pid    text UNIQUE NOT NULL,       -- G-NAF persistent identifier
    unit        text,
    number      text,                       -- street number, may be a range "10-12"
    number_int  integer,                    -- leading digits, for cheap equality
    street      text NOT NULL,              -- "WATTLE ST"
    locality    text NOT NULL,              -- "NEWTOWN"
    state       text NOT NULL,
    postcode    text,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    reliability smallint,                   -- G-NAF geocode reliability code
    search_text text NOT NULL               -- "WATTLE ST NEWTOWN", trigram target
);
