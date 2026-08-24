"""Extract the certain parts of an Australian address string.

Strategy: peel off what we can be confident about (postcode, state, unit,
street number), leave the ambiguous middle (street + locality) as `remainder`
for trigram matching. Narrowing on postcode/state before fuzzy matching is what
makes search both fast and accurate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STATES: dict[str, str] = {
    "NSW": "NSW", "NEW SOUTH WALES": "NSW",
    "VIC": "VIC", "VICTORIA": "VIC",
    "QLD": "QLD", "QUEENSLAND": "QLD",
    "SA": "SA", "SOUTH AUSTRALIA": "SA",
    "WA": "WA", "WESTERN AUSTRALIA": "WA",
    "TAS": "TAS", "TASMANIA": "TAS",
    "NT": "NT", "NORTHERN TERRITORY": "NT",
    "ACT": "ACT", "AUSTRALIAN CAPITAL TERRITORY": "ACT",
}

# Australia Post allocations. Used to validate a postcode and to infer state.
POSTCODE_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "NSW": ((1000, 2599), (2619, 2899), (2921, 2999)),
    "ACT": ((200, 299), (2600, 2618), (2900, 2920)),
    "VIC": ((3000, 3999), (8000, 8999)),
    "QLD": ((4000, 4999), (9000, 9999)),
    "SA": ((5000, 5999),),
    "WA": ((6000, 6999),),
    "TAS": ((7000, 7999),),
    "NT": ((800, 999),),
}

# Sub-dwelling prefixes: "Unit 3", "U3", "Apt 3", "Shop 5", "Level 2"
_UNIT_WORDS = (
    r"UNIT|U|APT|APARTMENT|FLAT|F|SUITE|STE|SHOP|OFFICE|ROOM|LEVEL|LVL|L|SE|TOWNHOUSE|VILLA"
)

_UNIT_PREFIX_RE = re.compile(rf"^(?:{_UNIT_WORDS})\s*[:.]?\s*(\d+[A-Z]?)\b", re.IGNORECASE)
_UNIT_SLASH_RE = re.compile(r"^(\d+[A-Z]?)\s*/\s*(?=\d)", re.IGNORECASE)
# 42, 42A, 42-44, 42A-44B
_NUMBER_RE = re.compile(r"^(\d+[A-Z]?(?:\s*-\s*\d+[A-Z]?)?)\s+", re.IGNORECASE)
_POSTCODE_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def state_from_postcode(postcode: str | int) -> str | None:
    """Infer the state from a postcode, or None if it isn't a valid allocation."""
    try:
        pc = int(postcode)
    except (TypeError, ValueError):
        return None
    for state, ranges in POSTCODE_RANGES.items():
        if any(lo <= pc <= hi for lo, hi in ranges):
            return state
    return None


@dataclass
class ParsedAddress:
    raw: str
    unit: str | None = None
    number: str | None = None
    remainder: str = ""          # street + locality; goes to trigram matching
    state: str | None = None
    postcode: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_narrowable(self) -> bool:
        """True when we can filter candidates before fuzzy matching."""
        return bool(self.postcode or self.state)


def normalise(s: str) -> str:
    """Uppercase, strip punctuation we don't need, collapse whitespace."""
    s = s.upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9\-/\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse(raw: str) -> ParsedAddress:
    """Peel the certain components off an Australian address string."""
    out = ParsedAddress(raw=raw)
    s = normalise(raw)
    if not s:
        out.warnings.append("empty input")
        return out

    # --- postcode: last valid 4-digit group wins (street numbers can be 4 digits) ---
    candidates = [m for m in _POSTCODE_RE.finditer(s)]
    for m in reversed(candidates):
        if state_from_postcode(m.group(1)):
            out.postcode = m.group(1)
            s = (s[: m.start()] + " " + s[m.end() :]).strip()
            s = re.sub(r"\s+", " ", s)
            break

    # --- state: match longest form first, anchored near the end ---
    for name in sorted(STATES, key=len, reverse=True):
        m = re.search(rf"(?<![A-Z]){re.escape(name)}(?![A-Z])", s)
        if m:
            out.state = STATES[name]
            s = (s[: m.start()] + " " + s[m.end() :]).strip()
            s = re.sub(r"\s+", " ", s)
            break

    # Cross-check: postcode is authoritative, state text is often wrong/stale.
    if out.postcode:
        inferred = state_from_postcode(out.postcode)
        if out.state and inferred and out.state != inferred:
            out.warnings.append(
                f"state {out.state} conflicts with postcode {out.postcode}; trusting postcode"
            )
            out.state = inferred
        out.state = out.state or inferred

    # --- unit / sub-dwelling ---
    if m := _UNIT_SLASH_RE.match(s):          # "3/42 Wattle St"
        out.unit = m.group(1)
        s = s[m.end() :].strip()
    elif m := _UNIT_PREFIX_RE.match(s):       # "Unit 3, 42" / "Unit 3/42" / "U3 42"
        out.unit = m.group(1)
        # separator after the unit number may be space, comma, dash or slash
        s = s[m.end() :].lstrip(" ,/-").strip()

    # --- street number ---
    if out.number is None and (m := _NUMBER_RE.match(s)):
        out.number = re.sub(r"\s*-\s*", "-", m.group(1))
        s = s[m.end() :].strip()

    out.remainder = re.sub(r"\s+", " ", s).strip(" ,-")
    if not out.remainder:
        out.warnings.append("no street/locality text found")
    return out
