"""X (Twitter) public profile lookup via public HTML / syndication."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from social_osint_lookup.http_client import (
    apply_extended_fields,
    base_result,
    fetch_html,
    make_session,
)

NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

JOINED_RE = re.compile(
    r"Joined\s+([A-Za-z]+\s+\d{4})",
    re.IGNORECASE,
)

FOLLOWERS_RE = re.compile(
    r'([\d.,]+[KkMmBb]?)\s+Followers?',
    re.IGNORECASE,
)
FOLLOWING_RE = re.compile(
    r'([\d.,]+[KkMmBb]?)\s+Following',
    re.IGNORECASE,
)

SYNDICATION_URL = (
    "https://cdn.syndication.twimg.com/widgets/followbutton/info.json"
)


def normalize_username(username_or_url: str) -> str:
    raw = (username_or_url or "").strip()
    if not raw:
        raise ValueError("empty X/Twitter username/URL")
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        if "twitter.com" not in host and "x.com" not in host:
            raise ValueError(f"not an X/Twitter URL: {raw}")
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        skip = {"i", "home", "explore", "search", "intent", "share", "hashtag"}
        if not parts or parts[0].lower() in skip:
            raise ValueError(f"cannot parse X username from URL: {raw}")
        return parts[0].lstrip("@").split("?")[0]
    return raw.lstrip("@").split("/")[0].split("?")[0]


def profile_url_for(username: str) -> str:
    return f"https://x.com/{username}"


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


def _parse_created_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # ms or seconds
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    # Twitter classic: "Wed Oct 04 12:00:00 +0000 2011"
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    # ISO already
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    # "Joined Month Year" → first of month UTC
    m = JOINED_RE.search(s) if "Joined" in s else re.match(
        r"^([A-Za-z]+\s+\d{4})$", s
    )
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%B %Y").replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            try:
                dt = datetime.strptime(m.group(1), "%b %Y").replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                return None
    return None


def _deep_find_user(obj: Any, username: str, depth: int = 0) -> dict[str, Any] | None:
    if depth > 12 or obj is None:
        return None
    if isinstance(obj, dict):
        screen = obj.get("screen_name") or obj.get("screenName") or obj.get("username")
        if isinstance(screen, str) and screen.lower() == username.lower():
            # Prefer objects that look like user cores
            if any(k in obj for k in ("followers_count", "followersCount", "legacy", "description", "name")):
                return obj
        legacy = obj.get("legacy")
        if isinstance(legacy, dict):
            screen = legacy.get("screen_name")
            if isinstance(screen, str) and screen.lower() == username.lower():
                merged = {**legacy, "rest_id": obj.get("rest_id") or obj.get("id")}
                if obj.get("is_blue_verified") is not None:
                    merged["is_blue_verified"] = obj.get("is_blue_verified")
                if obj.get("verification") is not None:
                    merged["verification"] = obj.get("verification")
                return merged
        for v in obj.values():
            found = _deep_find_user(v, username, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_find_user(item, username, depth + 1)
            if found:
                return found
    return None


def _map_user(user: dict[str, Any], *, parse_method: str) -> dict[str, Any]:
    username = (
        user.get("screen_name")
        or user.get("screenName")
        or user.get("username")
    )
    location = user.get("location")
    if isinstance(location, str):
        location = location.strip() or None
    else:
        location = None

    created = _parse_created_at(
        user.get("created_at") or user.get("createdAt") or user.get("joined_at")
    )

    verified = user.get("verified")
    if verified is None:
        verified = user.get("is_blue_verified")
    if verified is None and isinstance(user.get("verification"), dict):
        verified = bool(user["verification"].get("verified"))

    followers = user.get("followers_count", user.get("followersCount"))
    following = user.get("friends_count", user.get("friendsCount", user.get("following_count", user.get("followingCount"))))

    return {
        "username": username,
        "display_name": user.get("name") or user.get("display_name") or user.get("displayName"),
        "user_id": str(user["id"]) if user.get("id") is not None else (
            str(user["rest_id"]) if user.get("rest_id") is not None else None
        ),
        "bio": user.get("description") or user.get("bio") or None,
        "verified": verified if verified is not None else None,
        "protected": user.get("protected") if "protected" in user else None,
        "avatar_url": user.get("profile_image_url_https")
        or user.get("profile_image_url")
        or user.get("avatar_url"),
        "follower_count": followers,
        "following_count": following,
        "profile_url": f"https://x.com/{username}" if username else None,
        "parse_method": parse_method,
        "location": location,
        "account_created_at": created,
        "username_history": None,  # not exposed on public profile endpoints
        "tiktok_creator_level": None,
    }


def _from_next_data(html: str, username: str) -> dict[str, Any] | None:
    m = NEXT_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    user = _deep_find_user(data, username)
    if not user:
        return None
    return _map_user(user, parse_method="next_data")


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
        # "Name (@user) / X" or "Name (@user) on X"
        m = re.match(r"^(.+?)\s*\(@", title)
        display_name = m.group(1).strip() if m else title.split("/")[0].strip()

    followers = following = None
    bio = desc
    if desc:
        fm = FOLLOWERS_RE.search(desc)
        if fm:
            followers = _parse_count(fm.group(1))
        gm = FOLLOWING_RE.search(desc)
        if gm:
            following = _parse_count(gm.group(1))

    location = None
    created = None
    # Visible "Joined …" text
    joined_m = JOINED_RE.search(html or "")
    if joined_m:
        created = _parse_created_at(joined_m.group(0))

    # ld+json
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
                    display_name = node["name"]
                if node.get("description") and not bio:
                    bio = node["description"]
                loc = node.get("address") or node.get("homeLocation") or node.get("location")
                if isinstance(loc, str) and loc.strip():
                    location = loc.strip()
                elif isinstance(loc, dict):
                    name = loc.get("name") or loc.get("addressLocality")
                    if isinstance(name, str) and name.strip():
                        location = name.strip()

    return {
        "username": username,
        "display_name": display_name,
        "user_id": None,
        "bio": bio,
        "verified": None,
        "protected": None,
        "avatar_url": avatar,
        "follower_count": followers,
        "following_count": following,
        "profile_url": profile_url_for(username),
        "parse_method": "meta_tags",
        "location": location,
        "account_created_at": created,
        "username_history": None,
        "tiktok_creator_level": None,
    }


def _from_syndication(username: str, *, session=None, timeout: float = 25.0) -> dict[str, Any] | None:
    """Public unauthenticated follow-button syndication JSON (counts/name)."""
    own = session is None
    if own:
        session = make_session()
    try:
        from social_osint_lookup.http_client import _throttle

        _throttle()
        resp = session.get(
            SYNDICATION_URL,
            params={"screen_names": username},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        row = data[0]
        if not isinstance(row, dict):
            return None
        return _map_user(row, parse_method="syndication")
    except Exception:  # noqa: BLE001
        return None
    finally:
        if own:
            session.close()


def parse_profile_html(html: str, *, username_hint: str) -> dict[str, Any]:
    nxt = _from_next_data(html, username_hint)
    if nxt and nxt.get("username"):
        return nxt
    return _from_meta(html, username_hint)


def lookup(username_or_url: str, *, session=None, timeout: float = 25.0) -> dict[str, Any]:
    """
    Look up a public X (Twitter) profile.

    Public HTML / __NEXT_DATA__ / syndication only. Username history is not
    available from public profile endpoints (null + unavailable).
    """
    username = normalize_username(username_or_url)
    url = profile_url_for(username)
    result = base_result("x", username_or_url, profile_url=url)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()

    html = ""
    try:
        html, resp = fetch_html(
            url,
            session=session,
            timeout=timeout,
            referer="https://x.com/",
        )
        result["http_status"] = resp.status_code
        result["final_url"] = str(resp.url)
    except Exception as exc:  # noqa: BLE001
        # Fall back to syndication-only
        synd = _from_syndication(username, session=session, timeout=timeout)
        if synd:
            result["found"] = True
            result.update(synd)
            apply_extended_fields(
                result,
                location=synd.get("location"),
                account_created_at=synd.get("account_created_at"),
                username_history=None,
                tiktok_creator_level=None,
                platform="x",
            )
            result["error"] = None
            result["http_status"] = result.get("http_status") or 200
            return result
        result["error"] = f"fetch failed: {exc}"
        return result

    lower = html.lower()
    try:
        parsed = parse_profile_html(html, username_hint=username)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"parse failed: {exc}"
        return result

    # Enrich thin meta parses with syndication counts when useful
    if parsed.get("follower_count") is None or parsed.get("display_name") is None:
        synd = _from_syndication(username, session=session, timeout=timeout)
        if synd:
            for key in (
                "display_name",
                "follower_count",
                "following_count",
                "user_id",
                "protected",
                "avatar_url",
            ):
                if parsed.get(key) is None and synd.get(key) is not None:
                    parsed[key] = synd[key]
            if parsed.get("parse_method") == "meta_tags" and synd.get("parse_method"):
                parsed["parse_method"] = f"meta_tags+{synd['parse_method']}"

    if not parsed.get("display_name") and not parsed.get("bio") and parsed.get("follower_count") is None:
        if "account suspended" in lower or "doesn't exist" in lower or "page doesn’t exist" in lower:
            result["error"] = "profile not found or unavailable"
            result.update(parsed)
            apply_extended_fields(
                result,
                location=parsed.get("location"),
                account_created_at=parsed.get("account_created_at"),
                username_history=None,
                tiktok_creator_level=None,
                platform="x",
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
        platform="x",
    )
    result["error"] = None
    return result
