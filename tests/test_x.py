"""Unit tests for X (Twitter) platform module (mocked HTML)."""

from unittest.mock import MagicMock, patch

from social_osint_lookup.platforms import x


def test_normalize_username_variants():
    assert x.normalize_username("@demo_x") == "demo_x"
    assert x.normalize_username("demo_x") == "demo_x"
    assert x.normalize_username("https://x.com/demo_x") == "demo_x"
    assert x.normalize_username("https://twitter.com/demo_x") == "demo_x"


def test_parse_next_data(x_html: str):
    parsed = x.parse_profile_html(x_html, username_hint="demo_x")
    assert parsed["username"] == "demo_x"
    assert parsed["display_name"] == "Demo X User"
    assert parsed["user_id"] == "111222333"
    assert parsed["bio"] == "Public demo bio for X"
    assert parsed["follower_count"] == 1200
    assert parsed["following_count"] == 80
    assert parsed["location"] == "Austin, TX"
    assert parsed["account_created_at"] == "2020-01-01T00:00:00+00:00"
    assert parsed["username_history"] is None
    assert parsed["tiktok_creator_level"] is None
    assert parsed["parse_method"] == "next_data"


def test_lookup_mocked(x_html: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://x.com/demo_x"

    with patch(
        "social_osint_lookup.platforms.x.fetch_html",
        return_value=(x_html, mock_resp),
    ), patch(
        "social_osint_lookup.platforms.x._from_syndication",
        return_value=None,
    ):
        result = x.lookup("demo_x")

    assert result["platform"] == "x"
    assert result["found"] is True
    assert result["username"] == "demo_x"
    assert result["follower_count"] == 1200
    assert result["location"] == "Austin, TX"
    assert result["account_created_at"] == "2020-01-01T00:00:00+00:00"
    assert result["username_history"] is None
    assert result["error"] is None
    assert result["field_availability"]["location"] == "available"
    assert result["field_availability"]["account_created_at"] == "available"
    assert result["field_availability"]["username_history"] == "unavailable"
    assert result["field_availability"]["tiktok_creator_level"] == "n/a"
