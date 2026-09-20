"""Tests for output formatters."""

from social_osint_lookup.formatters import to_json, to_pretty


def test_to_json_roundtrip():
    data = {"platform": "tiktok", "found": True, "username": "x"}
    text = to_json(data)
    assert '"platform": "tiktok"' in text
    assert text.endswith("\n")


def test_to_pretty_contains_labels():
    data = {
        "platform": "instagram",
        "found": True,
        "username": "demo",
        "display_name": "Demo",
        "follower_count": 10,
        "error": None,
    }
    text = to_pretty(data)
    assert "INSTAGRAM" in text
    assert "Username" in text
    assert "demo" in text
    assert "Found" in text
    assert "yes" in text
