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
        "location": "NYC",
        "account_created_at": None,
        "username_history": [
            {"username": "old_demo", "changed_at": None, "location_at_change": None}
        ],
        "error": None,
    }
    text = to_pretty(data)
    assert "INSTAGRAM" in text
    assert "Username" in text
    assert "demo" in text
    assert "Found" in text
    assert "yes" in text
    assert "Location" in text
    assert "Username history" in text
    assert "old_demo" in text
