"""Pretty text + JSON output helpers."""

from __future__ import annotations

import json
from typing import Any


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


_LABELS = [
    ("platform", "Platform"),
    ("found", "Found"),
    ("username", "Username"),
    ("display_name", "Display name"),
    ("user_id", "ID"),
    ("sec_uid", "Sec UID"),
    ("bio", "Bio"),
    ("about", "About"),
    ("external_url", "External URL"),
    ("location", "Location"),
    ("account_created_at", "Created at"),
    ("username_history", "Username history"),
    ("tiktok_creator_level", "TikTok creator level"),
    ("verified", "Verified"),
    ("private", "Private"),
    ("protected", "Protected"),
    ("business", "Business"),
    ("entity_type", "Type"),
    ("follower_count", "Followers"),
    ("following_count", "Following"),
    ("likes_count", "Likes"),
    ("video_count", "Videos"),
    ("post_count", "Posts"),
    ("profile_url", "Profile URL"),
    ("avatar_url", "Avatar"),
    ("parse_method", "Parse method"),
    ("field_availability", "Field availability"),
    ("http_status", "HTTP"),
    ("final_url", "Final URL"),
    ("error", "Error"),
    ("fetched_at", "Fetched at"),
]


def _fmt_history(val: Any) -> str:
    if not isinstance(val, list):
        return str(val)
    parts = []
    for item in val:
        if isinstance(item, dict):
            u = item.get("username", "?")
            ca = item.get("changed_at") or "—"
            loc = item.get("location_at_change") or "—"
            parts.append(f"{u} (changed_at={ca}, location_at_change={loc})")
        else:
            parts.append(str(item))
    return "; ".join(parts)


def to_pretty(data: dict[str, Any]) -> str:
    lines: list[str] = []
    platform = str(data.get("platform") or "result").upper()
    lines.append(f"══ {platform} ══")
    for key, label in _LABELS:
        if key not in data:
            continue
        val = data[key]
        if val is None and key not in ("error", "found"):
            continue
        if key == "found":
            val = "yes" if val else "no"
        elif key == "username_history":
            val = _fmt_history(val)
        elif key == "field_availability" and isinstance(val, dict):
            val = ", ".join(f"{k}={v}" for k, v in val.items())
        lines.append(f"  {label:22} {val}")
    lines.append("")
    return "\n".join(lines)
