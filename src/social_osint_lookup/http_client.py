"""Shared HTTP helpers: session, User-Agent rotation, polite rate limiting."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

try:
    from fake_useragent import UserAgent

    _ua = UserAgent()
except Exception:  # noqa: BLE001 — fake_useragent can fail offline
    _ua = None

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

def _accept_encoding() -> str:
    """Return Accept-Encoding listing only codecs we can actually decode."""
    try:
        import brotli  # noqa: F401
    except Exception:  # noqa: BLE001
        return "gzip, deflate"
    return "gzip, deflate, br"


# Minimum seconds between requests from this process (polite default).
_MIN_INTERVAL = 1.25
_last_request_at = 0.0


def get_user_agent() -> str:
    if _ua is not None:
        try:
            return _ua.random
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_UA


def _throttle() -> None:
    global _last_request_at
    now = time.monotonic()
    wait = _MIN_INTERVAL - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def make_session(*, extra_headers: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    headers = {
        "User-Agent": get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        # Prefer encodings requests always decodes. Include br only when
        # the brotli package is installed — otherwise TikTok returns opaque
        # compressed bytes and we fall back to empty meta-only parses.
        "Accept-Encoding": _accept_encoding(),
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if extra_headers:
        headers.update(extra_headers)
    session.headers.update(headers)
    return session


def fetch_html(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 25.0,
    referer: str | None = None,
) -> tuple[str, requests.Response]:
    """GET a public page with rate limiting. Returns (html, response)."""
    own = session is None
    if own:
        session = make_session()
    try:
        if referer:
            session.headers["Referer"] = referer
        _throttle()
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text, resp
    finally:
        if own:
            session.close()


def unix_to_iso(ts: Any) -> str | None:
    """Convert a unix timestamp (int/float/str) to ISO-8601 UTC, or None."""
    if ts is None or ts == "":
        return None
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return None
    # Heuristic: ms vs seconds
    if value > 1e12:
        value = value / 1000.0
    if value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def availability_flag(value: Any, *, na: bool = False) -> str:
    if na:
        return "n/a"
    return "available" if value is not None else "unavailable"


def build_field_availability(
    *,
    location: Any = None,
    account_created_at: Any = None,
    username_history: Any = None,
    tiktok_creator_level: Any = None,
    platform: str | None = None,
) -> dict[str, str]:
    """Mark which extended public fields were present in the payload."""
    is_tiktok = (platform or "").lower() == "tiktok"
    return {
        "location": availability_flag(location),
        "account_created_at": availability_flag(account_created_at),
        "username_history": availability_flag(username_history),
        "tiktok_creator_level": availability_flag(
            tiktok_creator_level, na=not is_tiktok
        ),
    }


def extended_field_defaults(platform: str) -> dict[str, Any]:
    """Null-filled extended fields + field_availability for a platform."""
    return {
        "location": None,
        "account_created_at": None,
        "username_history": None,
        "tiktok_creator_level": None,
        "field_availability": build_field_availability(platform=platform),
    }


def apply_extended_fields(
    result: dict[str, Any],
    *,
    location: Any = None,
    account_created_at: Any = None,
    username_history: Any = None,
    tiktok_creator_level: Any = None,
    platform: str | None = None,
) -> dict[str, Any]:
    """Set extended OSINT fields and recompute field_availability."""
    plat = platform or result.get("platform") or ""
    is_tiktok = str(plat).lower() == "tiktok"
    result["location"] = location
    result["account_created_at"] = account_created_at
    result["username_history"] = username_history
    result["tiktok_creator_level"] = tiktok_creator_level if is_tiktok else None
    result["field_availability"] = build_field_availability(
        location=result["location"],
        account_created_at=result["account_created_at"],
        username_history=result["username_history"],
        tiktok_creator_level=result["tiktok_creator_level"],
        platform=plat,
    )
    return result


def base_result(
    platform: str,
    query: str,
    *,
    profile_url: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Skeleton dict shared by all platform modules."""
    out: dict[str, Any] = {
        "platform": platform,
        "query": query,
        "profile_url": profile_url,
        "found": False,
        "error": error,
        "source": "public_html",
        "fetched_at": None,
    }
    out.update(extended_field_defaults(platform))
    return out
