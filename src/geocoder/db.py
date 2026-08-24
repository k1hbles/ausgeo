"""Connection pool."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://geocoder:geocoder@localhost:5433/gnaf"
)

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False)


def open_pool() -> None:
    if pool.closed:
        pool.open()


def close_pool() -> None:
    if not pool.closed:
        pool.close()
