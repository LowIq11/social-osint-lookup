"""Facebook public profile / page lookup via public HTML metadata."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from social_osint_lookup.http_client import base_result, fetch_html


def normalize_slug(username_or_url: str) -> tuple[str, str]:
    """
    Return (slug_or_id, profile_url).

    Accepts bare username/page slug, profile.php?id=, or full facebook.com URL.
    """
    raw = (username_or_url or "").strip()
    if not raw:
        raise ValueError("empty Facebook username/URL")

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        if "facebook.com" not in host and "fb.com" not in host:
            raise ValueError(f"not a Facebook URL: {raw}")
        path = parsed.path.strip("/")
        qs = parsed.query or ""
        if path.startswith("profile.php") or path == "profile.php":
            m = re.search(r"(?:^|&)id=(\d+)", qs)
            if not m:
                raise ValueError(f"profile.php URL missing id=: {raw}")
            uid = m.group(1)
            return uid, f"https://www.facebook.com/profile.php?id={uid}"
        parts = [p for p in path.split("/") if p]
        skip_prefixes = {"people", "public", "watch", "reel", "photo", "photos", "events", "groups"}
        if not parts:
            raise ValueError(f"cannot parse Facebook slug from URL: {raw}")
        if parts[0].lower() in skip_prefixes and len(parts) > 1:
            slug = parts[1]
        else:
            slug = parts[0]
        slug = slug.split("?")[0]
        return slug, f"https://www.facebook.com/{slug}"

    # Bare id or slug
    if raw.isdigit():
        return raw, f"https://www.facebook.com/profile.php?id={raw}"
    slug = raw.lstrip("@").split("/")[0].split("?")[0]
    return slug, f"https://www.facebook.com/{slug}"


def _detect_type(soup: BeautifulSoup, html: str, slug: str) -> str | None:
    """Best-effort page vs profile detection from public HTML."""
    lower = html.lower()
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
            t = node.get("@type")
            if isinstance(t, list):
                t = t[0] if t else None
            if t in ("Organization", "LocalBusiness", "Corporation", "Brand"):
                return "page"
            if t in ("Person", "ProfilePage"):
                return "profile"

    og_type = soup.find("meta", property="og:type")
    if og_type and og_type.get("content"):
        content = og_type["content"].lower()
        if "profile" in content:
            return "profile"
        if content in ("website", "business.business", "company"):
            return "page"

    if "pages/category" in lower or '"pageID"' in html or "page_id" in lower:
        return "page"
    if "profile.php?id=" in lower or '"userID"' in html:
        return "profile"
    if slug.isdigit():
        return "profile"
    return None


def _about_snippet(soup: BeautifulSoup, desc: str | None) -> str | None:
    if desc:
        # Strip common Facebook boilerplate
        cleaned = re.sub(r"\s*\|\s*Facebook\s*$", "", desc).strip()
        cleaned = re.sub(r"^See more of .+ on Facebook\.\s*", "", cleaned).strip()
        if cleaned:
            return cleaned
    # Sometimes a description meta name=
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        return meta_desc["content"].strip()
    return None


def parse_profile_html(html: str, *, slug: str, profile_url: str) -> dict[str, Any]:
    """Parse public Facebook HTML into a structured dict."""
    soup = BeautifulSoup(html, "html.parser")

    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_url = soup.find("meta", property="og:url")
    og_image = soup.find("meta", property="og:image")

    name = og_title["content"].strip() if og_title and og_title.get("content") else None
    if name:
        name = re.sub(r"\s*\|\s*Facebook\s*$", "", name).strip()

    desc = og_desc["content"] if og_desc and og_desc.get("content") else None
    about = _about_snippet(soup, desc)
    avatar = og_image["content"] if og_image and og_image.get("content") else None
    canonical = og_url["content"] if og_url and og_url.get("content") else profile_url

    # Try title tag fallback
    if not name and soup.title and soup.title.string:
        name = re.sub(r"\s*\|\s*Facebook\s*$", "", soup.title.string).strip()

    entity_type = _detect_type(soup, html, slug)

    # Numeric id from URL or embedded
    user_id = slug if slug.isdigit() else None
    id_m = re.search(r'"userID"\s*:\s*"?(\d+)"?', html)
    if not user_id and id_m:
        user_id = id_m.group(1)
    page_m = re.search(r'"pageID"\s*:\s*"?(\d+)"?', html)
    page_id = page_m.group(1) if page_m else None
    if entity_type == "page" and page_id and not user_id:
        user_id = page_id

    return {
        "username": None if slug.isdigit() else slug,
        "display_name": name,
        "user_id": user_id,
        "about": about,
        "entity_type": entity_type,  # "page" | "profile" | None
        "avatar_url": avatar,
        "profile_url": canonical or profile_url,
        "parse_method": "meta_tags",
    }


def lookup(username_or_url: str, *, session=None, timeout: float = 25.0) -> dict[str, Any]:
    """
    Look up a public Facebook profile or page.

    Returns public name, about snippet if public, profile URL, and type
    (page/profile) when detectable from the public page. No private data.
    """
    slug, url = normalize_slug(username_or_url)
    result = base_result("facebook", username_or_url, profile_url=url)
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()

    try:
        html, resp = fetch_html(
            url,
            session=session,
            timeout=timeout,
            referer="https://www.facebook.com/",
        )
        result["http_status"] = resp.status_code
        result["final_url"] = str(resp.url)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"fetch failed: {exc}"
        return result

    lower = html.lower()
    if "content not found" in lower or "page isn't available" in lower or "this page isn't available" in lower:
        result["error"] = "profile/page not found or unavailable"
        return result

    try:
        parsed = parse_profile_html(html, slug=slug, profile_url=url)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"parse failed: {exc}"
        return result

    if not parsed.get("display_name") and not parsed.get("about"):
        # Login wall often still has generic Facebook title
        if "log in" in lower and "facebook" in (parsed.get("display_name") or "").lower():
            result["error"] = "login wall; limited public metadata"
            result.update(parsed)
            return result
        result["error"] = "no public name/about extracted"
        result.update(parsed)
        return result

    result["found"] = True
    result.update(parsed)
    result["error"] = None
    return result
