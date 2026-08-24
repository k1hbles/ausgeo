-- Built AFTER bulk load: index creation on a populated table is far faster.

-- Narrowing predicates: these turn 15.9M rows into a handful.
CREATE INDEX addr_postcode_idx      ON address (postcode);
CREATE INDEX addr_pc_num_idx        ON address (postcode, number_int);
CREATE INDEX addr_state_locality_idx ON address (state, locality);

-- Fuzzy matching on the ambiguous middle (street + locality).
CREATE INDEX addr_search_trgm_idx   ON address USING gin (search_text gin_trgm_ops);

ANALYZE address;
