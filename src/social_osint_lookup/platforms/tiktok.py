"""TikTok public profile lookup via page HTML rehydration JSON."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from social_osint_lookup.http_client import (
    apply_extended_fields,
    base_result,
    fetch_html,
    redact_secrets,
    resolve_tiktok_session_cookie,
    unix_to_iso,
)

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


def _extract_location(user: dict[str, Any]) -> str | None:
    """Prefer human-readable region/location keys when present in public JSON.

    Note: TikTok's public `language` field is UI locale, not a geographic
    location — never treat it as location.
    """
    for key in (
        "region",
        "location",
        "isoCountryCode",
        "country",
        "storeRegion",
        "regionName",
        "accountRegion",
    ):
        val = user.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _history_entry(
    username: str,
    *,
    changed_at: Any = None,
    location_at_change: Any = None,
) -> dict[str, Any]:
    return {
        "username": username,
        "changed_at": unix_to_iso(changed_at) if changed_at is not None and not isinstance(changed_at, str)
        else (changed_at if isinstance(changed_at, str) and changed_at.strip() else unix_to_iso(changed_at) if changed_at is not None else None),
        "location_at_change": location_at_change.strip()
        if isinstance(location_at_change, str) and location_at_change.strip()
        else None,
    }


def _extract_username_history(user: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Prior uniqueIds only if a real list/field exists in the public payload.

    Each entry is {username, changed_at, location_at_change}. Timestamps/locations
    are filled only when present in the public JSON — never invented.
    """
    current = user.get("uniqueId")
    out: list[dict[str, Any]] = []

    def _append(uname: Any, changed_at: Any = None, loc: Any = None) -> None:
        if not isinstance(uname, str) or not uname.strip():
            return
        uname = uname.strip()
        if isinstance(current, str) and uname == current:
            return
        if any(e["username"] == uname for e in out):
            return
        # Normalize changed_at
        if isinstance(changed_at, (int, float)) or (isinstance(changed_at, str) and changed_at.isdigit()):
            changed_iso = unix_to_iso(changed_at)
        elif isinstance(changed_at, str) and changed_at.strip():
            changed_iso = changed_at.strip()
        else:
            changed_iso = None
        loc_str = loc.strip() if isinstance(loc, str) and loc.strip() else None
        out.append(
            {
                "username": uname,
                "changed_at": changed_iso,
                "location_at_change": loc_str,
            }
        )

    for key in ("uniqueIdHistory", "uniqueIdHistories", "previousUniqueIds", "nicknames", "usernameHistory", "handleHistory"):
        val = user.get(key)
        if isinstance(val, list) and val:
            for item in val:
                if isinstance(item, str):
                    _append(item)
                elif isinstance(item, dict):
                    uid = item.get("uniqueId") or item.get("nickname") or item.get("value") or item.get("username")
                    _append(
                        uid,
                        changed_at=item.get("changedAt")
                        or item.get("changeTime")
                        or item.get("createTime")
                        or item.get("timestamp"),
                        loc=item.get("location")
                        or item.get("region")
                        or item.get("location_at_change"),
                    )
            break

    if not out:
        prev = user.get("previousUniqueId") or user.get("oldUniqueId")
        if isinstance(prev, str) and prev.strip():
            _append(prev)

    return out or None



def _extract_display_name_history(user: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Prior nicknames only if a real list/field exists in the public payload.

    Each entry is {display_name, changed_at, location_at_change}. Never invents
    history from nickNameModifyTime alone (that is last-change time only).
    """
    current = user.get("nickname") or user.get("nickName")
    out: list[dict[str, Any]] = []

    def _append(name: Any, changed_at: Any = None, loc: Any = None) -> None:
        if not isinstance(name, str) or not name.strip():
            return
        name = name.strip()
        if isinstance(current, str) and name == current:
            return
        if any(e["display_name"] == name for e in out):
            return
        if isinstance(changed_at, (int, float)) or (
            isinstance(changed_at, str) and changed_at.isdigit()
        ):
            changed_iso = unix_to_iso(changed_at)
        elif isinstance(changed_at, str) and changed_at.strip():
            changed_iso = changed_at.strip()
        else:
            changed_iso = None
        loc_str = loc.strip() if isinstance(loc, str) and loc.strip() else None
        out.append(
            {
                "display_name": name,
                "changed_at": changed_iso,
                "location_at_change": loc_str,
            }
        )

    for key in (
        "nickNameHistory",
        "nicknameHistory",
        "previousNicknames",
        "displayNameHistory",
        "nicknames",
    ):
        val = user.get(key)
        if isinstance(val, list) and val:
            for item in val:
                if isinstance(item, str):
                    _append(item)
                elif isinstance(item, dict):
                    nm = (
                        item.get("nickname")
                        or item.get("nickName")
                        or item.get("displayName")
                        or item.get("value")
                        or item.get("name")
                    )
                    _append(
                        nm,
                        changed_at=item.get("changedAt")
                        or item.get("changeTime")
                        or item.get("createTime")
                        or item.get("timestamp")
                        or item.get("nickNameModifyTime"),
                        loc=item.get("location")
                        or item.get("region")
                        or item.get("location_at_change"),
                    )
            break

    if not out:
        prev = (
            user.get("previousNickname")
            or user.get("oldNickname")
            or user.get("previousNickName")
        )
        if isinstance(prev, str) and prev.strip():
            _append(prev)

    return out or None


def _extract_creator_level(user: dict[str, Any], user_info: dict[str, Any] | None = None) -> str | None:
    """
    Creator/support/engagement badge if present in public JSON.

    Never invents values — only returns strings found under known keys.
    """
    scopes: list[dict[str, Any]] = [user]
    if isinstance(user_info, dict):
        scopes.append(user_info)
        commerce = user_info.get("commerceUserInfo") or user.get("commerceUserInfo")
        if isinstance(commerce, dict):
            scopes.append(commerce)
        analytics = user_info.get("analytics") or user.get("analytics")
        if isinstance(analytics, dict):
            scopes.append(analytics)

    for scope in scopes:
        for key in (
            "creatorLevel",
            "supportLevel",
            "creator_level",
            "support_level",
            "engagementLevel",
            "badgeLevel",
            "creatorBadge",
            "profileBadge",
            "analyticsLevel",
            "level",
        ):
            val = scope.get(key)
            if isinstance(val, (str, int, float)) and str(val).strip() != "":
                # Avoid generic numeric "level" that is not clearly a creator badge
                if key == "level" and not any(
                    k in scope for k in ("creatorLevel", "supportLevel", "commerceUserInfo")
                ):
                    # Only accept bare "level" when sibling badge context exists
                    if "creator" not in str(scope.keys()).lower() and "support" not in str(
                        scope.keys()
                    ).lower():
                        continue
                return str(val).strip()
        # commerce category / badge label strings
        for key in ("category", "badgeName", "badge", "label"):
            val = scope.get(key)
            if isinstance(val, str) and val.strip() and key != "category":
                return val.strip()
            if key == "category" and isinstance(val, str) and val.strip():
                # Only treat as creator level when under commerceUserInfo
                if scope is not user:
                    return val.strip()
    return None


def _extended_from_user(
    user: dict[str, Any], *, user_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    location = _extract_location(user)
    # location_at_creation: only if a dedicated public field exists — never
    # invent from language= or current region alone.
    location_at_creation = None
    for key in (
        "createRegion",
        "creationRegion",
        "regionAtCreation",
        "accountCreateRegion",
        "registerRegion",
        "locationAtCreation",
    ):
        val = user.get(key)
        if isinstance(val, str) and val.strip():
            location_at_creation = val.strip()
            break
    created = unix_to_iso(user.get("createTime") or user.get("create_time"))
    history = _extract_username_history(user)
    display_history = _extract_display_name_history(user)
    # Last-modify timestamps only (NOT full history of prior values).
    username_last_changed_at = unix_to_iso(
        user.get("uniqueIdModifyTime") or user.get("unique_id_modify_time")
    )
    display_name_last_changed_at = unix_to_iso(
        user.get("nickNameModifyTime")
        or user.get("nicknameModifyTime")
        or user.get("nick_name_modify_time")
    )
    creator_level = _extract_creator_level(user, user_info)
    return {
        "location": location,
        "location_at_creation": location_at_creation,
        "account_created_at": created,
        "username_history": history,
        "display_name_history": display_history,
        "username_last_changed_at": username_last_changed_at,
        "display_name_last_changed_at": display_name_last_changed_at,
        "tiktok_creator_level": creator_level,
    }


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
    stats_v2 = user_info.get("statsV2") if isinstance(user_info.get("statsV2"), dict) else {}
    if not user:
        return None

    def _stat(*keys: str) -> Any:
        for key in keys:
            if key in stats and stats.get(key) is not None:
                return stats.get(key)
            if key in stats_v2 and stats_v2.get(key) is not None:
                val = stats_v2.get(key)
                # statsV2 sometimes stores counts as strings
                if isinstance(val, str) and val.isdigit():
                    return int(val)
                return val
        return None

    username = user.get("uniqueId") or user.get("unique_id")
    out = {
        "username": username,
        "display_name": user.get("nickname") or user.get("nickName"),
        "user_id": str(user["id"]) if user.get("id") is not None else None,
        "sec_uid": user.get("secUid") or user.get("sec_uid"),
        "bio": (user.get("signature") or user.get("bio") or None) or None,
        "verified": user.get("verified") if "verified" in user else None,
        "private": user.get("privateAccount")
        if "privateAccount" in user
        else user.get("private") if "private" in user else None,
        "avatar_url": (
            user.get("avatarLarger")
            or user.get("avatarMedium")
            or user.get("avatarThumb")
            or user.get("avatarLarger")
            or user.get("avatarMedium")
        ),
        "follower_count": _stat("followerCount", "follower_count"),
        "following_count": _stat("followingCount", "following_count"),
        "likes_count": _stat("heartCount", "heart", "diggCount"),
        "video_count": _stat("videoCount", "video_count"),
        "profile_url": f"https://www.tiktok.com/@{username}" if username else None,
        "parse_method": "rehydration",
    }
    # Empty bio string -> None
    if isinstance(out.get("bio"), str) and not out["bio"].strip():
        out["bio"] = None
    out.update(_extended_from_user(user, user_info=user_info))
    return out


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
    out = {
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
    out.update(_extended_from_user(user))
    return out


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
        "location": None,
        "location_at_creation": None,
        "account_created_at": None,
        "username_history": None,
        "display_name_history": None,
        "username_last_changed_at": None,
        "display_name_last_changed_at": None,
        "tiktok_creator_level": None,
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


def lookup(
    username_or_url: str,
    *,
    session=None,
    timeout: float = 25.0,
    session_cookie: str | None = None,
) -> dict[str, Any]:
    """
    Look up a TikTok profile from public HTML (optionally with a session cookie).

    Without a cookie: unauthenticated public scrape only.
    With ``session_cookie`` or env ``TIKTOK_SESSION_COOKIE``: Cookie header is
    attached so richer fields may appear in the same rehydration JSON when TikTok
    exposes them to logged-in browsers. The cookie is never logged, printed, or
    written to disk by this library.

    Always returns last-modify timestamps (uniqueIdModifyTime / nickNameModifyTime)
    when present; full history arrays only when actually in the payload.
    """
    username = normalize_username(username_or_url)
    url = profile_url_for(username)
    result = base_result("tiktok", username_or_url, profile_url=url)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()

    cookie = resolve_tiktok_session_cookie(session_cookie)
    result["auth_mode"] = "session_cookie" if cookie else "public"
    # Never put the cookie (or any secret) on the result dict.

    try:
        html, resp = fetch_html(
            url,
            session=session,
            timeout=timeout,
            referer="https://www.tiktok.com/",
            cookie=cookie,
        )
        result["http_status"] = resp.status_code
        result["final_url"] = str(resp.url)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"fetch failed: {redact_secrets(str(exc), cookie, session_cookie)}"
        return result

    try:
        parsed = parse_profile_html(html, username_hint=username)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"parse failed: {redact_secrets(str(exc), cookie, session_cookie)}"
        return result

    # Detect empty / not found pages
    if not parsed.get("username") and not parsed.get("user_id") and not parsed.get("display_name"):
        result["error"] = "profile not found or page blocked public scrape"
        result.update(parsed)
        apply_extended_fields(
            result,
            location=parsed.get("location"),
            location_at_creation=parsed.get("location_at_creation"),
            account_created_at=parsed.get("account_created_at"),
            username_history=parsed.get("username_history"),
            display_name_history=parsed.get("display_name_history"),
            username_last_changed_at=parsed.get("username_last_changed_at"),
            display_name_last_changed_at=parsed.get("display_name_last_changed_at"),
            tiktok_creator_level=parsed.get("tiktok_creator_level"),
            platform="tiktok",
        )
        return result

    result["found"] = True
    result.update(parsed)
    apply_extended_fields(
        result,
        location=parsed.get("location"),
        location_at_creation=parsed.get("location_at_creation"),
        account_created_at=parsed.get("account_created_at"),
        username_history=parsed.get("username_history"),
        display_name_history=parsed.get("display_name_history"),
        username_last_changed_at=parsed.get("username_last_changed_at"),
        display_name_last_changed_at=parsed.get("display_name_last_changed_at"),
        tiktok_creator_level=parsed.get("tiktok_creator_level"),
        platform="tiktok",
    )
    if not result.get("profile_url"):
        result["profile_url"] = url
    result["error"] = None
    return result
