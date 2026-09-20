"""Unit tests for TikTok platform module (mocked HTML)."""

from unittest.mock import MagicMock, patch

from social_osint_lookup.platforms import tiktok


def test_normalize_username_variants():
    assert tiktok.normalize_username("@demo_tiktok") == "demo_tiktok"
    assert tiktok.normalize_username("demo_tiktok") == "demo_tiktok"
    assert tiktok.normalize_username("https://www.tiktok.com/@demo_tiktok") == "demo_tiktok"
    assert tiktok.normalize_username("https://www.tiktok.com/@demo_tiktok/video/1") == "demo_tiktok"
    assert tiktok.normalize_username("https://www.tiktok.com/share/user/1234567890123456789") == "1234567890123456789"


def test_parse_rehydration(tiktok_html: str):
    parsed = tiktok.parse_profile_html(tiktok_html, username_hint="demo_tiktok")
    assert parsed["username"] == "demo_tiktok"
    assert parsed["display_name"] == "Demo TikTok User"
    assert parsed["user_id"] == "1234567890123456789"
    assert parsed["bio"] == "Public demo bio"
    assert parsed["follower_count"] == 1500
    assert parsed["following_count"] == 120
    assert parsed["likes_count"] == 9900
    assert parsed["video_count"] == 25
    assert parsed["verified"] is False
    assert parsed["private"] is False
    assert parsed["parse_method"] == "rehydration"
    assert parsed["profile_url"] == "https://www.tiktok.com/@demo_tiktok"
    assert parsed["location"] == "US"
    assert parsed["account_created_at"] == "2021-01-01T00:00:00+00:00"
    assert parsed["tiktok_creator_level"] == "level2"
    assert isinstance(parsed["username_history"], list)
    assert parsed["username_history"][0]["username"] == "old_demo_tt"
    assert parsed["username_history"][0]["changed_at"] == "2020-03-01T00:00:00+00:00"
    assert parsed["username_history"][0]["location_at_change"] is None


def test_lookup_mocked(tiktok_html: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://www.tiktok.com/@demo_tiktok"

    with patch(
        "social_osint_lookup.platforms.tiktok.fetch_html",
        return_value=(tiktok_html, mock_resp),
    ):
        result = tiktok.lookup("demo_tiktok")

    assert result["platform"] == "tiktok"
    assert result["found"] is True
    assert result["username"] == "demo_tiktok"
    assert result["follower_count"] == 1500
    assert result["error"] is None
    assert result["location"] == "US"
    assert result["account_created_at"] == "2021-01-01T00:00:00+00:00"
    assert result["tiktok_creator_level"] == "level2"
    assert result["field_availability"]["location"] == "available"
    assert result["field_availability"]["account_created_at"] == "available"
    assert result["field_availability"]["username_history"] == "available"
    assert result["field_availability"]["tiktok_creator_level"] == "available"
