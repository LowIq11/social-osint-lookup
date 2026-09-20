"""Shared HTTP helpers: session, User-Agent rotation, polite rate limiting."""

from __future__ import annotations

import time
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
        "Accept-Encoding": "gzip, deflate, br",
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


def base_result(
    platform: str,
    query: str,
    *,
    profile_url: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Skeleton dict shared by all platform modules."""
    return {
        "platform": platform,
        "query": query,
        "profile_url": profile_url,
        "found": False,
        "error": error,
        "source": "public_html",
        "fetched_at": None,
    }
