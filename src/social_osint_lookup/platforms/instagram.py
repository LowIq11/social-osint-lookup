"""Instagram public profile lookup via public page metadata / shared data."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from social_osint_lookup.http_client import apply_extended_fields, base_result, fetch_html

SHARED_DATA_RE = re.compile(
    r"window\._sharedData\s*=\s*(\{.+?\});\s*</script>",
    re.IGNORECASE | re.DOTALL,
)

ADDITIONAL_DATA_RE = re.compile(
    r"window\.__additionalDataLoaded\s*\(\s*['\"][^'\"]+['\"]\s*,\s*(\{.+?\})\s*\)\s*;",
    re.IGNORECASE | re.DOTALL,
)

# Modern pages embed JSON in <script type="application/json"> or meta description patterns.
META_COUNTS_RE = re.compile(
    r"([\d.,]+[KkMmBb]?)\s+Followers?,\s*([\d.,]+[KkMmBb]?)\s+Following,\s*([\d.,]+[KkMmBb]?)\s+Posts?",
    re.IGNORECASE,
)


def normalize_username(username_or_url: str) -> str:
    raw = (username_or_url or "").strip()
    if not raw:
        raise ValueError("empty Instagram username/URL")
    if raw.startswith("http://") or raw.startswith("https://"):
        path = urlparse(raw).path.strip("/")
        # instagram.com/username or /p/... ignore non-profile paths
        parts = [p for p in path.split("/") if p]
        if not parts:
            raise ValueError(f"cannot parse Instagram username from URL: {raw}")
        skip = {"p", "reel", "reels", "stories", "explore", "tv", "accounts"}
        if parts[0].lower() in skip:
            raise ValueError(f"URL does not look like a profile: {raw}")
        return parts[0].split("?")[0]
    return raw.lstrip("@").split("/")[0].split("?")[0]


def profile_url_for(username: str) -> str:
    return f"https://www.instagram.com/{username}/"


def _parse_count(text: str | None) -> int | None:
    if text is None:
        return None
    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    mult = 1
    if s[-1] in "Kk":
        mult = 1_000
        s = s[:-1]
    elif s[-1] in "Mm":
        mult = 1_000_000
        s = s[:-1]
    elif s[-1] in "Bb":
        mult = 1_000_000_000
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def _extract_location(user: dict[str, Any]) -> str | None:
    """Rare public location hints from sharedData (city / business address)."""
    for key in ("city_name", "cityName", "public_email_location"):
        val = user.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    addr = user.get("business_address_json") or user.get("business_address")
    if isinstance(addr, str) and addr.strip():
        try:
            parsed = json.loads(addr)
        except json.JSONDecodeError:
            return addr.strip()
        if isinstance(parsed, dict):
            parts = [
                parsed.get(k)
                for k in ("city_name", "city", "region", "country_code", "country")
                if isinstance(parsed.get(k), str) and parsed.get(k).strip()
            ]
            if parts:
                return ", ".join(parts)
        return None
    if isinstance(addr, dict):
        parts = [
            addr.get(k)
            for k in ("city_name", "city", "region", "country_code", "country")
            if isinstance(addr.get(k), str) and addr.get(k).strip()
        ]
        if parts:
            return ", ".join(parts)
    return None


def _extended_nulls(*, location: str | None = None) -> dict[str, Any]:
    """Instagram: join date / username history not on public profile page."""
    return {
        "location": location,
        "account_created_at": None,
        "username_history": None,
        "tiktok_creator_level": None,
    }


def _from_shared_data(data: dict[str, Any]) -> dict[str, Any] | None:
    entry = (
        ((data.get("entry_data") or {}).get("ProfilePage") or [None])[0]
        if isinstance(data.get("entry_data"), dict)
        else None
    )
    if not isinstance(entry, dict):
        return None
    user = (entry.get("graphql") or {}).get("user") if isinstance(entry.get("graphql"), dict) else None
    if not isinstance(user, dict):
        # older shape
        user = entry.get("user") if isinstance(entry.get("user"), dict) else None
    if not isinstance(user, dict):
        return None
    return _map_user(user, parse_method="shared_data")


def _map_user(user: dict[str, Any], *, parse_method: str) -> dict[str, Any]:
    edge_followed = user.get("edge_followed_by") or {}
    edge_follow = user.get("edge_follow") or {}
    edge_media = user.get("edge_owner_to_timeline_media") or {}
    username = user.get("username")
    out = {
        "username": username,
        "display_name": user.get("full_name") or None,
        "user_id": str(user["id"]) if user.get("id") is not None else None,
        "bio": user.get("biography") or None,
        "external_url": user.get("external_url") or None,
        "verified": user.get("is_verified") if "is_verified" in user else None,
        "private": user.get("is_private") if "is_private" in user else None,
        "business": user.get("is_business_account") if "is_business_account" in user else None,
        "avatar_url": user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
        "follower_count": edge_followed.get("count") if isinstance(edge_followed, dict) else user.get("follower_count"),
        "following_count": edge_follow.get("count") if isinstance(edge_follow, dict) else user.get("following_count"),
        "post_count": edge_media.get("count") if isinstance(edge_media, dict) else user.get("media_count"),
        "profile_url": f"https://www.instagram.com/{username}/" if username else None,
        "parse_method": parse_method,
    }
    out.update(_extended_nulls(location=_extract_location(user)))
    return out


def _from_meta(html: str, username: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_image = soup.find("meta", property="og:image")
    title = og_title["content"] if og_title and og_title.get("content") else None
    desc = og_desc["content"] if og_desc and og_desc.get("content") else None
    avatar = og_image["content"] if og_image and og_image.get("content") else None

    display_name = None
    if title:
        # Typical: "Name (@user) • Instagram photos and videos"
        m = re.match(r"^(.+?)\s*\(@", title)
        display_name = m.group(1).strip() if m else title.split("•")[0].strip()

    followers = following = posts = None
    bio = None
    if desc:
        cm = META_COUNTS_RE.search(desc)
        if cm:
            followers = _parse_count(cm.group(1))
            following = _parse_count(cm.group(2))
            posts = _parse_count(cm.group(3))
            # Remainder after counts often is bio snippet
            after = desc[cm.end() :].lstrip(" -–—:")
            bio = after.strip() or None
        else:
            bio = desc

    # ld+json Person / ProfilePage
    verified = None
    location = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = ld if isinstance(ld, list) else [ld]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") in ("Person", "ProfilePage", "Organization"):
                if not display_name and node.get("name"):
                    display_name = node.get("name")
                if node.get("description") and not bio:
                    bio = node.get("description")
                loc = node.get("address") or node.get("location") or node.get("contentLocation")
                if isinstance(loc, str) and loc.strip():
                    location = loc.strip()
                elif isinstance(loc, dict):
                    name = loc.get("name") or loc.get("addressLocality") or loc.get("addressRegion")
                    if isinstance(name, str) and name.strip():
                        location = name.strip()

    out = {
        "username": username,
        "display_name": display_name,
        "user_id": None,
        "bio": bio,
        "external_url": None,
        "verified": verified,
        "private": None,
        "business": None,
        "avatar_url": avatar,
        "follower_count": followers,
        "following_count": following,
        "post_count": posts,
        "profile_url": profile_url_for(username),
        "parse_method": "meta_tags",
    }
    out.update(_extended_nulls(location=location))
    return out


def _try_json_blobs(html: str) -> dict[str, Any] | None:
    m = SHARED_DATA_RE.search(html or "")
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                parsed = _from_shared_data(data)
                if parsed:
                    return parsed
        except json.JSONDecodeError:
            pass

    for m in ADDITIONAL_DATA_RE.finditer(html or ""):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        # graphql.user nested variously
        user = None
        if isinstance(data.get("graphql"), dict) and isinstance(data["graphql"].get("user"), dict):
            user = data["graphql"]["user"]
        elif isinstance(data.get("user"), dict):
            user = data["user"]
        if user:
            return _map_user(user, parse_method="additional_data")
    return None


def parse_profile_html(html: str, *, username_hint: str) -> dict[str, Any]:
    """Parse public Instagram profile HTML into a structured dict."""
    from_json = _try_json_blobs(html)
    if from_json and from_json.get("username"):
        return from_json
    return _from_meta(html, username_hint)


def lookup(username_or_url: str, *, session=None, timeout: float = 25.0) -> dict[str, Any]:
    """
    Look up a public Instagram profile.

    Returns public fields only: display name, bio, follower/following/post counts
    when available from public page metadata, profile URL, verified/private flags
    if exposed publicly. Join date and username history are typically unavailable
    from the public profile page (returned as null).
    """
    username = normalize_username(username_or_url)
    url = profile_url_for(username)
    result = base_result("instagram", username_or_url, profile_url=url)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()

    try:
        html, resp = fetch_html(
            url,
            session=session,
            timeout=timeout,
            referer="https://www.instagram.com/",
        )
        result["http_status"] = resp.status_code
        result["final_url"] = str(resp.url)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"fetch failed: {exc}"
        return result

    # Login wall / empty
    lower = html.lower()
    if "login" in (resp.url or "").lower() and "instagram.com/" + username.lower() not in (resp.url or "").lower():
        result["error"] = "redirected to login; public metadata unavailable"
        return result

    try:
        parsed = parse_profile_html(html, username_hint=username)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"parse failed: {exc}"
        return result

    if not parsed.get("display_name") and not parsed.get("bio") and parsed.get("follower_count") is None:
        # Still mark found if username page returned 200 with og tags for that user
        if "sorry" in lower or "page isn't available" in lower or "page not found" in lower:
            result["error"] = "profile not found or unavailable"
            result.update(parsed)
            apply_extended_fields(
                result,
                location=parsed.get("location"),
                account_created_at=None,
                username_history=None,
                tiktok_creator_level=None,
                platform="instagram",
            )
            return result

    result["found"] = True
    result.update(parsed)
    apply_extended_fields(
        result,
        location=parsed.get("location"),
        account_created_at=parsed.get("account_created_at"),
        username_history=parsed.get("username_history"),
        tiktok_creator_level=None,
        platform="instagram",
    )
    result["error"] = None
    return result
