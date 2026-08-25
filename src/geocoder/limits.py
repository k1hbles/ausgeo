"""API keys and per-day rate limiting, backed by Postgres.

No Redis: a single atomic UPSERT per request is cheap next to the geocoding
query itself, and one less service to run.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

ANON_DAILY_LIMIT = 100          # enough to try the docs examples
KEYS_PER_IP_PER_DAY = 3

KEY_PREFIX = "ausgeo_"


class RateLimited(Exception):
    def __init__(self, limit: int, scope: str) -> None:
        self.limit = limit
        self.scope = scope
        super().__init__(f"{scope} daily limit of {limit} exceeded")


class InvalidKey(Exception):
    pass


@dataclass
class Caller:
    key_id: int | None       # None for anonymous
    limit: int
    used: int
    anonymous: bool

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


def _bump(conn, sql: str, params: tuple) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def check_and_count(conn, api_key: str | None, ip: str) -> Caller:
    """Authorise a request and increment its counter. Raises on failure."""
    if api_key:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, daily_limit FROM api_key WHERE key = %s AND NOT revoked",
                (api_key,),
            )
            row = cur.fetchone()
        if row is None:
            raise InvalidKey("unknown or revoked API key")
        key_id, limit = row
        used = _bump(
            conn,
            """
            INSERT INTO api_usage (key_id, day, count) VALUES (%s, current_date, 1)
            ON CONFLICT (key_id, day) DO UPDATE SET count = api_usage.count + 1
            RETURNING count
            """,
            (key_id,),
        )
        if used > limit:
            raise RateLimited(limit, "key")
        return Caller(key_id=key_id, limit=limit, used=used, anonymous=False)

    used = _bump(
        conn,
        """
        INSERT INTO anon_usage (ip, day, count) VALUES (%s, current_date, 1)
        ON CONFLICT (ip, day) DO UPDATE SET count = anon_usage.count + 1
        RETURNING count
        """,
        (ip,),
    )
    if used > ANON_DAILY_LIMIT:
        raise RateLimited(ANON_DAILY_LIMIT, "anonymous")
    return Caller(key_id=None, limit=ANON_DAILY_LIMIT, used=used, anonymous=True)


def issue_key(conn, email: str | None, ip: str, label: str | None = None) -> str:
    """Create a key, throttled per IP per day."""
    issued = _bump(
        conn,
        """
        INSERT INTO key_issuance (ip, day, count) VALUES (%s, current_date, 1)
        ON CONFLICT (ip, day) DO UPDATE SET count = key_issuance.count + 1
        RETURNING count
        """,
        (ip,),
    )
    if issued > KEYS_PER_IP_PER_DAY:
        raise RateLimited(KEYS_PER_IP_PER_DAY, "key issuance")

    key = new_key()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_key (key, email, label) VALUES (%s, %s, %s)",
            (key, email, label),
        )
    return key
