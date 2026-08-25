-- API keys and per-day usage counters. Deliberately minimal: no accounts,
-- no dashboard, no billing (see v2.md).

CREATE TABLE IF NOT EXISTS api_key (
    id           bigserial PRIMARY KEY,
    key          text UNIQUE NOT NULL,
    email        text,
    label        text,
    daily_limit  integer NOT NULL DEFAULT 2500,
    revoked      boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Usage is bucketed by UTC day; the primary key makes the upsert atomic.
CREATE TABLE IF NOT EXISTS api_usage (
    key_id  bigint NOT NULL REFERENCES api_key(id) ON DELETE CASCADE,
    day     date   NOT NULL,
    count   integer NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, day)
);

-- Anonymous callers get a small quota so the docs examples work without signup.
-- `ip` is text, not inet: X-Forwarded-For is attacker-controlled and a strict
-- type turns a malformed header into a 500. We never do IP arithmetic.
CREATE TABLE IF NOT EXISTS anon_usage (
    ip     text NOT NULL,
    day    date NOT NULL,
    count  integer NOT NULL DEFAULT 0,
    PRIMARY KEY (ip, day)
);

-- Issuance is throttled per IP per day to stop key farming.
CREATE TABLE IF NOT EXISTS key_issuance (
    ip     text NOT NULL,
    day    date NOT NULL,
    count  integer NOT NULL DEFAULT 0,
    PRIMARY KEY (ip, day)
);
