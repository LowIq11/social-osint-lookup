"""TikTok webapp / mobile API profile fetcher (Omar-free).

Design
------
* Talk to real TikTok hosts only (no omar-thing.site / for.omar-thing.site /
  worker.* proxies, no paid keys).
* Do **not** invent X-Gorgon / X-Khronos. Unsigned aweme calls currently return
  ``status_msg: "url doesn't match"``; unsigned webapp ``/api/user/detail/``
  returns empty bodies or empty ``userInfo`` without a working mssdk session
  (msToken + X-Bogus / X-Gnarly). Open signers we tried here still yielded
  empty ``userInfo``.
* When upstream JSON actually contains a user object, map it. Otherwise return
  ``None`` so ``tiktok.lookup`` can fall back to HTML rehydration.
* History arrays are filled only when present in the JSON (never fabricated
  from modify-time fields alone).

Probe notes (2026-09-21 Asia/Riyadh)
------------------------------------
Working without signing:
  * ``GET https://www.tiktok.com/@{user}`` HTML rehydration (``tiktok.py``)
  * ``GET https://www.tiktok.com/oembed?url=...`` (author name/url only)

Failed / needs signing:
  * ``https://www.tiktok.com/api/user/detail/?uniqueId=`` → 200 empty or
    ``userInfo: {}`` / ``statusCode: -1``
  * ``https://t.tiktok.com/api/user/detail/`` → 200 empty
  * ``https://m.tiktok.com/api/user/detail/`` → 403
  * ``https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/user/detail/``
    (+ api19 / api22 / api.tiktokv.com) → 200 ``"url doesn't match"``
  * Follower / following list endpoints → unavailable without login/signing
"""

from __future__ import annotations

import random
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from social_osint_lookup.http_client import (
    apply_extended_fields,
    base_result,
    get_user_agent,
    unix_to_iso,
)

# ---------------------------------------------------------------------------
# Discovered endpoints
# ---------------------------------------------------------------------------

WEBAPP_DETAIL_URLS: tuple[str, ...] = (
    "https://www.tiktok.com/api/user/detail/",
    "https://t.tiktok.com/api/user/detail/",
    "https://m.tiktok.com/api/user/detail/",
)

MOBILE_DETAIL_URLS: tuple[str, ...] = (
    "https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/user/detail/",
    "https://api19-normal-c-useast1a.tiktokv.com/aweme/v1/user/detail/",
    "https://api22-normal-c-useast1a.tiktokv.com/aweme/v1/user/detail/",
    "https://api.tiktokv.com/aweme/v1/user/detail/",
    "https://api16-normal-c-useast1a.musical.ly/aweme/v1/user/detail/",
)

# Documented; not publicly callable without login/signing.
FOLLOWER_LIST_URLS: tuple[str, ...] = (
    "https://www.tiktok.com/api/user/list/",  # not a real follower list
    "https://www.tiktok.com/api/user/following/list/",
    "https://www.tiktok.com/api/user/follower/list/",
    "https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/user/follower/list/",
    "https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/user/following/list/",
)

MOBILE_UA_POOL: tuple[str, ...] = (
    "com.zhiliaoapp.musically/2023504030 (Linux; U; Android 13; en_US; Pixel 7; Build/TQ3A.230901.001; Cronet/58.0.2991.0)",
    "com.zhiliaoapp.musically/2023405030 (Linux; U; Android 12; en_US; SM-G991B; Build/SP1A.210812.016; Cronet/58.0.2991.0)",
    "com.ss.android.ugc.trill/350403 (Linux; U; Android 13; en_US; Pixel 6; Build/TQ3A.230805.001; Cronet/58.0.2991.0)",
)

WEB_UA_FALLBACK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_CACHE_TTL_SEC = 300.0

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
_LAST_PROBE: list[dict[str, Any]] = []


def get_last_probe_log() -> list[dict[str, Any]]:
    """Return a copy of recent upstream probe attempts (no secrets)."""
    return list(_LAST_PROBE)


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def followers_following_status() -> dict[str, Any]:
    """Honest status: follower/following *lists* are not public."""
    return {
        "followers_list_available": False,
        "following_list_available": False,
        "reason": (
            "TikTok follower/following list APIs require login and/or request "
            "signing (X-Gorgon / web mssdk). Unsigned probes return empty bodies "
            "or 'url doesn't match'. This library does not scrape private lists."
        ),
        "endpoints_documented": list(FOLLOWER_LIST_URLS),
    }


# ----- cache helpers -------------------------------------------------------


def _cache_get(key: str) -> dict[str, Any] | None:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        expires, value = item
        if time.monotonic() > expires:
            _CACHE.pop(key, None)
            return None
        return dict(value)


def _cache_set(key: str, value: dict[str, Any], ttl: float) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic() + ttl, dict(value))


def _record_probe(entry: dict[str, Any]) -> None:
    _LAST_PROBE.append(entry)
    if len(_LAST_PROBE) > 100:
        del _LAST_PROBE[:-50]


# ----- device / params -----------------------------------------------------


def _random_device() -> dict[str, str]:
    did = str(random.randint(10**18, 10**19 - 1))
    iid = str(random.randint(10**18, 10**19 - 1))
    return {
        "device_id": did,
        "iid": iid,
        "openudid": uuid.uuid4().hex[:16],
        "cdid": str(uuid.uuid4()),
    }


def _webapp_params(
    unique_id: str | None, user_id: str | None, device_id: str
) -> dict[str, str]:
    params: dict[str, str] = {
        "aid": "1988",
        "app_language": "en",
        "app_name": "tiktok_web",
        "browser_language": "en-US",
        "browser_name": "Mozilla",
        "browser_online": "true",
        "browser_platform": "Win32",
        "browser_version": "5.0 (Windows)",
        "channel": "tiktok_web",
        "cookie_enabled": "true",
        "device_id": device_id,
        "device_platform": "web_pc",
        "focus_state": "true",
        "from_page": "user",
        "history_len": "3",
        "is_fullscreen": "false",
        "is_page_visible": "true",
        "os": "windows",
        "priority_region": "",
        "referer": "",
        "region": "US",
        "screen_height": "1080",
        "screen_width": "1920",
        "tz_name": "UTC",
        "user_is_login": "false",
        "webcast_language": "en",
    }
    if unique_id:
        params["uniqueId"] = unique_id
    if user_id:
        params["userId"] = user_id
    return params


def _mobile_params(
    unique_id: str | None, user_id: str | None, device: dict[str, str]
) -> dict[str, str]:
    params: dict[str, str] = {
        "aid": "1233",
        "app_name": "musical_ly",
        "channel": "googleplay",
        "device_platform": "android",
        "version_code": "350403",
        "version_name": "35.4.3",
        "manifest_version_code": "2023504030",
        "update_version_code": "2023504030",
        "ab_version": "35.4.3",
        "resolution": "1080*2400",
        "dpi": "420",
        "device_type": "Pixel 7",
        "device_brand": "Google",
        "language": "en",
        "os_api": "33",
        "os_version": "13",
        "ac": "wifi",
        "ssmix": "a",
        "timezone_name": "UTC",
        "timezone_offset": "0",
        **device,
    }
    if unique_id:
        params["unique_id"] = unique_id
    if user_id:
        params["user_id"] = user_id
    return params


# ----- JSON extraction / mapping -------------------------------------------


def _pick(obj: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in obj and obj.get(key) not in (None, ""):
            return obj.get(key)
    for key in keys:
        if key in obj:
            return obj.get(key)
    return None


def _extract_user_bundle(
    payload: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Return (user, stats, root) from webapp or aweme-shaped JSON."""
    if not isinstance(payload, dict):
        return None

    user_info = payload.get("userInfo")
    if isinstance(user_info, dict):
        user = user_info.get("user")
        stats = user_info.get("stats") if isinstance(user_info.get("stats"), dict) else {}
        if isinstance(user, dict) and (
            user.get("uniqueId") or user.get("id") or user.get("unique_id")
        ):
            # Reject empty placeholder objects TikTok returns unsigned.
            if user.get("uniqueId") or user.get("id") or user.get("unique_id"):
                if any(user.get(k) not in (None, "", {}, []) for k in user):
                    return user, stats, payload

    user = payload.get("user")
    if isinstance(user, dict) and (
        user.get("unique_id")
        or user.get("uid")
        or user.get("uniqueId")
        or user.get("nickname")
    ):
        stats: dict[str, Any] = {}
        for key in (
            "follower_count",
            "following_count",
            "aweme_count",
            "total_favorited",
            "favoriting_count",
        ):
            if key in user:
                stats[key] = user.get(key)
        return user, stats, payload

    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_user_bundle(data)
    return None


def _extract_location(user: dict[str, Any]) -> str | None:
    for key in (
        "region",
        "user_region",
        "account_region",
        "store_region",
        "storeRegion",
        "iso_country_code",
        "isoCountryCode",
        "location",
        "regionName",
        "accountRegion",
    ):
        val = user.get(key)
        if isinstance(val, str) and val.strip() and val.strip().upper() not in {
            "N/A",
            "NA",
            "NONE",
        }:
            return val.strip()
    return None


def _extract_location_at_creation(user: dict[str, Any]) -> str | None:
    for key in (
        "create_region",
        "createRegion",
        "creation_region",
        "creationRegion",
        "region_at_creation",
        "regionAtCreation",
        "account_create_region",
        "accountCreateRegion",
        "register_region",
        "registerRegion",
        "user_region_code",
        "userRegionCode",
    ):
        val = user.get(key)
        if isinstance(val, str) and val.strip() and val.strip().upper() not in {
            "N/A",
            "NA",
            "NONE",
        }:
            return val.strip()
    return None


def _history_from_user(
    user: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    current_uid = _pick(user, "uniqueId", "unique_id")
    current_nick = _pick(user, "nickname", "nickName")

    uname_hist: list[dict[str, Any]] = []
    for key in (
        "uniqueIdHistory",
        "unique_id_history",
        "uniqueIdHistories",
        "previousUniqueIds",
        "usernameHistory",
        "handleHistory",
    ):
        val = user.get(key)
        if not (isinstance(val, list) and val):
            continue
        for item in val:
            if isinstance(item, str) and item.strip() and item.strip() != current_uid:
                uname_hist.append(
                    {
                        "username": item.strip(),
                        "changed_at": None,
                        "location_at_change": None,
                    }
                )
            elif isinstance(item, dict):
                uid = (
                    item.get("uniqueId")
                    or item.get("unique_id")
                    or item.get("username")
                    or item.get("value")
                )
                if isinstance(uid, str) and uid.strip() and uid.strip() != current_uid:
                    changed = (
                        item.get("changedAt")
                        or item.get("changeTime")
                        or item.get("createTime")
                        or item.get("timestamp")
                    )
                    loc = item.get("location") or item.get("region")
                    uname_hist.append(
                        {
                            "username": uid.strip(),
                            "changed_at": unix_to_iso(changed)
                            if not isinstance(changed, str)
                            else (changed.strip() or None),
                            "location_at_change": loc.strip()
                            if isinstance(loc, str) and loc.strip()
                            else None,
                        }
                    )
        break

    dname_hist: list[dict[str, Any]] = []
    for key in (
        "nickNameHistory",
        "nicknameHistory",
        "nickname_history",
        "previousNicknames",
        "displayNameHistory",
    ):
        val = user.get(key)
        if not (isinstance(val, list) and val):
            continue
        for item in val:
            if isinstance(item, str) and item.strip() and item.strip() != current_nick:
                dname_hist.append(
                    {
                        "display_name": item.strip(),
                        "changed_at": None,
                        "location_at_change": None,
                    }
                )
            elif isinstance(item, dict):
                nm = (
                    item.get("nickname")
                    or item.get("nickName")
                    or item.get("displayName")
                    or item.get("value")
                    or item.get("name")
                )
                if isinstance(nm, str) and nm.strip() and nm.strip() != current_nick:
                    changed = (
                        item.get("changedAt")
                        or item.get("changeTime")
                        or item.get("createTime")
                        or item.get("timestamp")
                        or item.get("nickNameModifyTime")
                    )
                    loc = item.get("location") or item.get("region")
                    dname_hist.append(
                        {
                            "display_name": nm.strip(),
                            "changed_at": unix_to_iso(changed)
                            if not isinstance(changed, str)
                            else (changed.strip() or None),
                            "location_at_change": loc.strip()
                            if isinstance(loc, str) and loc.strip()
                            else None,
                        }
                    )
        break

    return (uname_hist or None, dname_hist or None)


def _creator_level(
    user: dict[str, Any], root: dict[str, Any] | None = None
) -> str | None:
    scopes: list[dict[str, Any]] = [user]
    if isinstance(root, dict):
        ui = root.get("userInfo")
        if isinstance(ui, dict):
            scopes.append(ui)
            commerce = ui.get("commerceUserInfo")
            if isinstance(commerce, dict):
                scopes.append(commerce)
    commerce_u = user.get("commerceUserInfo") or user.get("commerce_user_info")
    if isinstance(commerce_u, dict):
        scopes.append(commerce_u)

    for scope in scopes:
        for key in (
            "creatorLevel",
            "creator_level",
            "supportLevel",
            "support_level",
            "engagementLevel",
            "badgeLevel",
            "creatorBadge",
            "analyticsLevel",
        ):
            val = scope.get(key)
            if isinstance(val, (str, int, float)) and str(val).strip():
                return str(val).strip()
        for key in ("badgeName", "badge", "label"):
            val = scope.get(key)
            if isinstance(val, str) and val.strip() and key != "label":
                return val.strip()
    return None


def map_upstream_user(
    user: dict[str, Any],
    stats: dict[str, Any] | None = None,
    *,
    root: dict[str, Any] | None = None,
    source_url: str | None = None,
    parse_method: str = "webapp_api",
) -> dict[str, Any]:
    """Map webapp/aweme user JSON into the shared profile field shape."""
    stats = stats or {}
    username = _pick(user, "uniqueId", "unique_id")
    user_id = _pick(user, "id", "uid", "user_id")
    if user_id is not None:
        user_id = str(user_id)

    def _stat(*keys: str) -> Any:
        for key in keys:
            if key in stats and stats.get(key) is not None:
                val = stats.get(key)
                if isinstance(val, str) and val.isdigit():
                    return int(val)
                return val
            if key in user and user.get(key) is not None:
                val = user.get(key)
                if isinstance(val, str) and val.isdigit():
                    return int(val)
                return val
        return None

    bio = _pick(user, "signature", "bio", "desc")
    if isinstance(bio, str) and not bio.strip():
        bio = None

    uname_hist, dname_hist = _history_from_user(user)
    location = _extract_location(user)
    location_at_creation = _extract_location_at_creation(user)

    is_mobile = bool(source_url and "aweme" in source_url)
    return {
        "username": username if isinstance(username, str) else None,
        "display_name": _pick(user, "nickname", "nickName"),
        "user_id": user_id,
        "sec_uid": _pick(user, "secUid", "sec_uid", "sec_user_id"),
        "bio": bio,
        "verified": user.get("verified")
        if "verified" in user
        else user.get("is_verified"),
        "private": (
            user.get("privateAccount")
            if "privateAccount" in user
            else user.get("secret")
            if "secret" in user
            else user.get("private_account")
        ),
        "avatar_url": _pick(
            user,
            "avatarLarger",
            "avatar_larger",
            "avatarMedium",
            "avatar_medium",
            "avatarThumb",
            "avatar_thumb",
        ),
        "follower_count": _stat("followerCount", "follower_count"),
        "following_count": _stat("followingCount", "following_count"),
        "likes_count": _stat("heartCount", "heart", "total_favorited", "diggCount"),
        "video_count": _stat("videoCount", "video_count", "aweme_count"),
        "profile_url": f"https://www.tiktok.com/@{username}"
        if isinstance(username, str)
        else None,
        "parse_method": parse_method,
        "source": "tiktok_mobile_api" if is_mobile else "tiktok_webapp_api",
        "location": location,
        "location_at_creation": location_at_creation,
        "account_created_at": unix_to_iso(_pick(user, "createTime", "create_time")),
        "username_history": uname_hist,
        "display_name_history": dname_hist,
        "username_last_changed_at": unix_to_iso(
            _pick(user, "uniqueIdModifyTime", "unique_id_modify_time")
        ),
        "display_name_last_changed_at": unix_to_iso(
            _pick(
                user,
                "nickNameModifyTime",
                "nicknameModifyTime",
                "nick_name_modify_time",
                "nickname_modify_time",
            )
        ),
        "tiktok_creator_level": _creator_level(user, root),
        "upstream_url": source_url,
        "followers_list": None,
        "following_list": None,
        "followers_list_available": False,
        "following_list_available": False,
    }


# ----- HTTP ----------------------------------------------------------------


def _request_json(
    url: str,
    *,
    params: dict[str, str],
    headers: dict[str, str],
    timeout: float,
    session: requests.Session | None,
) -> tuple[int | None, Any, str | None]:
    own = session is None
    sess = session or requests.Session()
    try:
        resp = sess.get(
            url, params=params, headers=headers, timeout=timeout, allow_redirects=True
        )
        status = resp.status_code
        text = resp.text or ""
        payload: Any = None
        if text.strip():
            try:
                payload = resp.json()
            except Exception:  # noqa: BLE001
                payload = None
        return status, payload, None
    except Exception as exc:  # noqa: BLE001
        return None, None, str(exc)
    finally:
        if own:
            sess.close()


def try_webapp_detail(
    *,
    unique_id: str | None = None,
    user_id: str | None = None,
    session: requests.Session | None = None,
    timeout: float = 20.0,
    max_hosts: int | None = None,
) -> dict[str, Any] | None:
    """Attempt unsigned webapp ``/api/user/detail/`` across hosts."""
    if not unique_id and not user_id:
        return None
    device_id = str(random.randint(10**18, 10**19 - 1))
    params = _webapp_params(unique_id, user_id, device_id)
    try:
        ua = get_user_agent()
    except Exception:  # noqa: BLE001
        ua = WEB_UA_FALLBACK
    referer = f"https://www.tiktok.com/@{unique_id}" if unique_id else "https://www.tiktok.com/"
    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }
    hosts = WEBAPP_DETAIL_URLS[: max_hosts or len(WEBAPP_DETAIL_URLS)]
    for base in hosts:
        status, payload, err = _request_json(
            base, params=params, headers=headers, timeout=timeout, session=session
        )
        bundle = _extract_user_bundle(payload) if payload is not None else None
        # Treat completely empty user dict as a miss.
        if bundle is not None:
            user, _stats, _root = bundle
            if not (user.get("uniqueId") or user.get("id") or user.get("unique_id")):
                bundle = None
        _record_probe(
            {
                "kind": "webapp",
                "url": base,
                "status": status,
                "error": err,
                "has_user": bundle is not None,
                "signing_required_likely": bundle is None and status in (200, 403),
            }
        )
        if bundle is None:
            continue
        user, stats, root = bundle
        mapped = map_upstream_user(
            user,
            stats,
            root=root,
            source_url=f"{base}?{urlencode({'uniqueId': unique_id or ''})}",
            parse_method="webapp_api",
        )
        if mapped.get("username") or mapped.get("user_id"):
            return mapped
    return None


def try_mobile_detail(
    *,
    unique_id: str | None = None,
    user_id: str | None = None,
    session: requests.Session | None = None,
    timeout: float = 20.0,
    retries: int = 2,
    max_hosts: int | None = None,
) -> dict[str, Any] | None:
    """Attempt unsigned aweme ``/aweme/v1/user/detail/`` with device rotation."""
    if not unique_id and not user_id:
        return None
    hosts = MOBILE_DETAIL_URLS[: max_hosts or len(MOBILE_DETAIL_URLS)]
    for attempt in range(max(1, retries)):
        device = _random_device()
        params = _mobile_params(unique_id, user_id, device)
        ua = random.choice(MOBILE_UA_POOL)
        headers = {
            "User-Agent": ua,
            "Accept": "application/json",
            "sdk-version": "2",
            "x-ss-dp": "1233",
        }
        for base in hosts:
            status, payload, err = _request_json(
                base, params=params, headers=headers, timeout=timeout, session=session
            )
            status_msg = None
            if isinstance(payload, dict):
                status_msg = payload.get("status_msg") or payload.get("message")
            bundle = _extract_user_bundle(payload) if payload is not None else None
            _record_probe(
                {
                    "kind": "mobile",
                    "url": base,
                    "status": status,
                    "error": err,
                    "status_msg": status_msg,
                    "has_user": bundle is not None,
                    "attempt": attempt,
                    "signing_required_likely": bundle is None,
                }
            )
            if bundle is None:
                continue
            user, stats, root = bundle
            mapped = map_upstream_user(
                user,
                stats,
                root=root,
                source_url=base,
                parse_method="mobile_api",
            )
            if mapped.get("username") or mapped.get("user_id"):
                return mapped
    return None


def fetch_profile_api(
    username_or_id: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 20.0,
    cache_ttl: float = DEFAULT_CACHE_TTL_SEC,
    use_cache: bool = True,
) -> dict[str, Any] | None:
    """
    Try webapp then mobile detail endpoints. Return mapped profile or None.

    None means "no usable upstream JSON" — caller should fall back to HTML.
    """
    raw = (username_or_id or "").strip().lstrip("@")
    if not raw:
        return None

    cache_key = f"ttapi:{raw.lower()}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            out = dict(cached)
            out["cache_hit"] = True
            return out

    unique_id = None if raw.isdigit() else raw
    user_id = raw if raw.isdigit() else None

    mapped = try_webapp_detail(
        unique_id=unique_id, user_id=user_id, session=session, timeout=timeout
    )
    if mapped is None:
        mapped = try_mobile_detail(
            unique_id=unique_id, user_id=user_id, session=session, timeout=timeout
        )

    if mapped is None:
        return None

    mapped["cache_hit"] = False
    if use_cache:
        _cache_set(cache_key, mapped, cache_ttl)
    return mapped


def lookup_profile(
    username_or_url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 20.0,
    cache_ttl: float = DEFAULT_CACHE_TTL_SEC,
) -> dict[str, Any] | None:
    """
    High-level API lookup returning a full result dict, or None to signal fallback.
    """
    from social_osint_lookup.platforms.tiktok import normalize_username, profile_url_for

    try:
        key = normalize_username(username_or_url)
    except ValueError:
        key = (username_or_url or "").strip().lstrip("@")

    mapped = fetch_profile_api(
        key, session=session, timeout=timeout, cache_ttl=cache_ttl
    )
    if not mapped:
        return None

    url = mapped.get("profile_url") or profile_url_for(key)
    result = base_result("tiktok", username_or_url, profile_url=url)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    result["auth_mode"] = "public_api"
    result["found"] = True
    result["error"] = None
    result["http_status"] = 200

    for field in (
        "username",
        "display_name",
        "user_id",
        "sec_uid",
        "bio",
        "verified",
        "private",
        "avatar_url",
        "follower_count",
        "following_count",
        "likes_count",
        "video_count",
        "profile_url",
        "parse_method",
        "source",
        "followers_list",
        "following_list",
        "followers_list_available",
        "following_list_available",
        "upstream_url",
        "cache_hit",
    ):
        if field in mapped:
            result[field] = mapped[field]

    apply_extended_fields(
        result,
        location=mapped.get("location"),
        location_at_creation=mapped.get("location_at_creation"),
        account_created_at=mapped.get("account_created_at"),
        username_history=mapped.get("username_history"),
        display_name_history=mapped.get("display_name_history"),
        username_last_changed_at=mapped.get("username_last_changed_at"),
        display_name_last_changed_at=mapped.get("display_name_last_changed_at"),
        tiktok_creator_level=mapped.get("tiktok_creator_level"),
        platform="tiktok",
    )
    return result
