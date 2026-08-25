"""Free Australian geocoding API.

GET  /v1/geocode?q=42 Wattle St, Newtown NSW 2042
GET  /v1/geocode?number=42&street=Wattle St&locality=Newtown&state=NSW&postcode=2042
POST /v1/keys
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from .db import close_pool, open_pool, pool
from .limits import InvalidKey, RateLimited, check_and_count, issue_key
from .search import geocode

MAX_QUERY_LEN = 200


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    open_pool()
    yield
    close_pool()


app = FastAPI(
    title="ausgeo",
    version="0.1.0",
    summary="Free geocoding for Australian addresses, built on G-NAF open government data.",
    description=(
        "Turns an Australian address string into coordinates.\n\n"
        "Anonymous callers get 100 requests/day. "
        "`POST /v1/keys` issues a free key with 2,500/day.\n\n"
        "Data: G-NAF © Geoscape Australia, licensed by the Commonwealth of Australia."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- models ----
class Location(BaseModel):
    lat: float
    lon: float


class Components(BaseModel):
    unit: str | None = None
    number: str | None = None
    street: str
    locality: str
    state: str
    postcode: str | None = None


class Result(BaseModel):
    gnaf_pid: str = Field(description="G-NAF persistent identifier")
    address: str
    components: Components
    location: Location
    score: float = Field(ge=0, le=1, description="0-1 confidence in this match")
    match: str = Field(description="which narrowing strategy produced the match")


class Parsed(BaseModel):
    unit: str | None = None
    number: str | None = None
    street_locality: str
    state: str | None = None
    postcode: str | None = None
    warnings: list[str] = []


class GeocodeResponse(BaseModel):
    query: str
    parsed: Parsed
    results: list[Result]
    took_ms: float


class KeyRequest(BaseModel):
    email: EmailStr | None = None
    label: str | None = Field(default=None, max_length=80)


class KeyResponse(BaseModel):
    key: str
    daily_limit: int
    note: str


# ------------------------------------------------------------ dependency ----
MAX_IP_LEN = 45  # longest valid IPv6 textual form


def client_ip(request: Request) -> str:
    """Identify the caller for anonymous quota purposes.

    X-Forwarded-For is attacker-controlled, so the value is only ever used as
    an opaque bucket key and is truncated. It is never parsed as an address.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:MAX_IP_LEN] or "unknown"
    host = request.client.host if request.client else "unknown"
    return host[:MAX_IP_LEN]


def authorise(
    response: Response,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    ip = client_ip(request)
    with pool.connection() as conn:
        try:
            caller = check_and_count(conn, x_api_key, ip)
        except InvalidKey as exc:
            raise HTTPException(401, str(exc)) from exc
        except RateLimited as exc:
            raise HTTPException(
                429,
                detail=(
                    f"{exc}. "
                    + ("Get a free key at POST /v1/keys for 2,500/day."
                       if exc.scope == "anonymous" else "Limits reset at UTC midnight.")
                ),
            ) from exc
    response.headers["X-RateLimit-Limit"] = str(caller.limit)
    response.headers["X-RateLimit-Remaining"] = str(caller.remaining)
    return caller


# --------------------------------------------------------------- routes ----
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"])
def health() -> dict:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM address")
        n = cur.fetchone()[0]
    return {"status": "ok", "addresses": n}


@app.get("/v1/geocode", response_model=GeocodeResponse, tags=["geocoding"])
def geocode_endpoint(
    q: str | None = Query(
        default=None,
        max_length=MAX_QUERY_LEN,
        description="Free-text address",
        examples=["42 Wattle St, Newtown NSW 2042"],
    ),
    number: str | None = Query(default=None, max_length=20),
    street: str | None = Query(default=None, max_length=100),
    locality: str | None = Query(default=None, max_length=100),
    state: str | None = Query(default=None, max_length=40),
    postcode: str | None = Query(default=None, max_length=4),
    limit: int = Query(default=5, ge=1, le=20),
    _caller=Depends(authorise),
) -> GeocodeResponse:
    # Structured params are composed into a string and run through the same
    # pipeline: the parser handles well-formed input trivially, and there is
    # one code path to reason about rather than two.
    if q is None:
        composed = " ".join(p for p in (number, street, locality, state, postcode) if p)
        if not composed:
            raise HTTPException(
                422, "provide q, or at least one of number/street/locality/state/postcode"
            )
        q = composed[:MAX_QUERY_LEN]

    t0 = time.perf_counter()
    with pool.connection() as conn:
        matches, parsed = geocode(conn, q, limit=limit)
    took = (time.perf_counter() - t0) * 1000

    return GeocodeResponse(
        query=q,
        parsed=Parsed(
            unit=parsed.unit,
            number=parsed.number,
            street_locality=parsed.remainder,
            state=parsed.state,
            postcode=parsed.postcode,
            warnings=parsed.warnings,
        ),
        results=[
            Result(
                gnaf_pid=m.gnaf_pid,
                address=m.address,
                components=Components(
                    unit=m.unit, number=m.number, street=m.street,
                    locality=m.locality, state=m.state, postcode=m.postcode,
                ),
                location=Location(lat=m.lat, lon=m.lon),
                score=m.score,
                match=m.tier,
            )
            for m in matches
        ],
        took_ms=round(took, 2),
    )


@app.post("/v1/keys", response_model=KeyResponse, status_code=201, tags=["meta"])
def create_key(body: KeyRequest, request: Request) -> KeyResponse:
    ip = client_ip(request)
    with pool.connection() as conn:
        try:
            key = issue_key(conn, body.email, ip, body.label)
        except RateLimited as exc:
            raise HTTPException(429, str(exc)) from exc
    return KeyResponse(
        key=key,
        daily_limit=2500,
        note="Send as the X-API-Key header. Store it now; it is not shown again.",
    )
