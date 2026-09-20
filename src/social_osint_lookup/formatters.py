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
    ("verified", "Verified"),
    ("private", "Private"),
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
    ("http_status", "HTTP"),
    ("final_url", "Final URL"),
    ("error", "Error"),
    ("fetched_at", "Fetched at"),
]


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
        lines.append(f"  {label:14} {val}")
    lines.append("")
    return "\n".join(lines)
