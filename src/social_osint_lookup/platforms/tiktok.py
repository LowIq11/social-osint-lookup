"""TikTok public profile lookup via page HTML rehydration JSON."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from social_osint_lookup.http_client import base_result, fetch_html

REHYDRATION_RE = re.compile(
    r'<script[^>]+id=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

SIGI_RE = re.compile(
    r'<script[^>]+id=["\']SIGI_STATE["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def normalize_username(username_or_url: str) -> str:
    """Extract TikTok uniqueId from @user, URL, or bare username."""
    raw = (username_or_url or "").strip()
    if not raw:
        raise ValueError("empty TikTok username/URL")
    if raw.startswith("http://") or raw.startswith("https://"):
        path = urlparse(raw).path.strip("/")
        # @user or share/user/id
        if path.startswith("@"):
            return path.split("/")[0].lstrip("@").split("?")[0]
        parts = path.split("/")
        if "share" in parts and "user" in parts:
            # numeric id path — keep as-is for URL building, but username unknown
            idx = parts.index("user")
            if idx + 1 < len(parts):
                return parts[idx + 1].split("?")[0]
        if parts and parts[0].startswith("@"):
            return parts[0].lstrip("@")
        raise ValueError(f"cannot parse TikTok username from URL: {raw}")
    return raw.lstrip("@").split("/")[0].split("?")[0]


def profile_url_for(username: str) -> str:
    if username.isdigit():
        return f"https://www.tiktok.com/share/user/{username}"
    return f"https://www.tiktok.com/@{username}"


def _extract_json_script(html: str, pattern: re.Pattern[str]) -> dict[str, Any] | None:
    m = pattern.search(html or "")
    if not m:
        return None
    raw = m.group(1).strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _from_rehydration(data: dict[str, Any]) -> dict[str, Any] | None:
    scope = data.get("__DEFAULT_SCOPE__") or {}
    detail = scope.get("webapp.user-detail")
    if not isinstance(detail, dict):
        return None
    user_info = detail.get("userInfo")
    if not isinstance(user_info, dict):
        return None
    user = user_info.get("user") if isinstance(user_info.get("user"), dict) else {}
    stats = user_info.get("stats") if isinstance(user_info.get("stats"), dict) else {}
    if not user:
        return None
    username = user.get("uniqueId")
    return {
        "username": username,
        "display_name": user.get("nickname"),
        "user_id": str(user["id"]) if user.get("id") is not None else None,
        "sec_uid": user.get("secUid"),
        "bio": user.get("signature") or None,
        "verified": user.get("verified") if "verified" in user else None,
        "private": user.get("privateAccount") if "privateAccount" in user else None,
        "avatar_url": user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb"),
        "follower_count": stats.get("followerCount"),
        "following_count": stats.get("followingCount"),
        "likes_count": stats.get("heartCount", stats.get("heart")),
        "video_count": stats.get("videoCount"),
        "profile_url": f"https://www.tiktok.com/@{username}" if username else None,
        "parse_method": "rehydration",
    }


def _from_sigi(data: dict[str, Any]) -> dict[str, Any] | None:
    user_module = data.get("UserModule") or {}
    users = user_module.get("users") if isinstance(user_module, dict) else None
    stats_mod = user_module.get("stats") if isinstance(user_module, dict) else None
    if not isinstance(users, dict) or not users:
        return None
    # First user entry
    user = next(iter(users.values()))
    if not isinstance(user, dict):
        return None
    username = user.get("uniqueId")
    stats: dict[str, Any] = {}
    if isinstance(stats_mod, dict) and username and username in stats_mod:
        stats = stats_mod[username] if isinstance(stats_mod[username], dict) else {}
    return {
        "username": username,
        "display_name": user.get("nickname"),
        "user_id": str(user["id"]) if user.get("id") is not None else None,
        "sec_uid": user.get("secUid"),
        "bio": user.get("signature") or None,
        "verified": user.get("verified") if "verified" in user else None,
        "private": user.get("privateAccount") if "privateAccount" in user else None,
        "avatar_url": user.get("avatarLarger") or user.get("avatarMedium"),
        "follower_count": stats.get("followerCount"),
        "following_count": stats.get("followingCount"),
        "likes_count": stats.get("heartCount", stats.get("heart")),
        "video_count": stats.get("videoCount"),
        "profile_url": f"https://www.tiktok.com/@{username}" if username else None,
        "parse_method": "sigi_state",
    }


def _from_meta(html: str, username: str) -> dict[str, Any]:
    """Fallback: Open Graph / meta tags only."""
    soup = BeautifulSoup(html, "html.parser")
    title = None
    desc = None
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]
    return {
        "username": username if not username.isdigit() else None,
        "display_name": title,
        "user_id": username if username.isdigit() else None,
        "sec_uid": None,
        "bio": desc,
        "verified": None,
        "private": None,
        "avatar_url": None,
        "follower_count": None,
        "following_count": None,
        "likes_count": None,
        "video_count": None,
        "profile_url": profile_url_for(username),
        "parse_method": "meta_tags",
    }


def parse_profile_html(html: str, *, username_hint: str | None = None) -> dict[str, Any]:
    """Parse public TikTok profile HTML into a structured dict."""
    rehyd = _extract_json_script(html, REHYDRATION_RE)
    if rehyd:
        parsed = _from_rehydration(rehyd)
        if parsed and (parsed.get("username") or parsed.get("user_id")):
            return parsed

    sigi = _extract_json_script(html, SIGI_RE)
    if sigi:
        parsed = _from_sigi(sigi)
        if parsed and (parsed.get("username") or parsed.get("user_id")):
            return parsed

    return _from_meta(html, username_hint or "")


def lookup(username_or_url: str, *, session=None, timeout: float = 25.0) -> dict[str, Any]:
    """
    Look up a public TikTok profile.

    Returns public fields only: username, display name, bio, follower/following/likes
    counts when present in page JSON, profile URL, id if public.
    """
    username = normalize_username(username_or_url)
    url = profile_url_for(username)
    result = base_result("tiktok", username_or_url, profile_url=url)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()

    try:
        html, resp = fetch_html(
            url,
            session=session,
            timeout=timeout,
            referer="https://www.tiktok.com/",
        )
        result["http_status"] = resp.status_code
        result["final_url"] = str(resp.url)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"fetch failed: {exc}"
        return result

    try:
        parsed = parse_profile_html(html, username_hint=username)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"parse failed: {exc}"
        return result

    # Detect empty / not found pages
    if not parsed.get("username") and not parsed.get("user_id") and not parsed.get("display_name"):
        result["error"] = "profile not found or page blocked public scrape"
        result.update(parsed)
        return result

    result["found"] = True
    result.update(parsed)
    if not result.get("profile_url"):
        result["profile_url"] = url
    result["error"] = None
    return result
