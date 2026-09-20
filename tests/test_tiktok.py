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
    assert isinstance(parsed["display_name_history"], list)
    assert parsed["display_name_history"][0]["display_name"] == "Old Demo Name"
    assert parsed["display_name_history"][0]["changed_at"] == "2021-02-01T00:00:00+00:00"
    assert parsed["username_last_changed_at"] == "2021-02-01T00:00:00+00:00"
    assert parsed["display_name_last_changed_at"] == "2021-03-01T00:00:00+00:00"
    assert parsed["location_at_creation"] is None


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
    assert result["field_availability"]["display_name_history"] == "available"
    assert result["field_availability"]["username_last_changed_at"] == "available"
    assert result["field_availability"]["display_name_last_changed_at"] == "available"
    assert result["field_availability"]["location_at_creation"] == "unavailable"
    assert result["field_availability"]["tiktok_creator_level"] == "available"
    assert result["username_last_changed_at"] == "2021-02-01T00:00:00+00:00"
    assert result["display_name_last_changed_at"] == "2021-03-01T00:00:00+00:00"


def test_parse_no_history_exposes_last_modify_only(tiktok_html_no_history: str):
    """Public payloads often have modify timestamps but no history arrays."""
    parsed = tiktok.parse_profile_html(tiktok_html_no_history, username_hint="2iolex")
    assert parsed["username"] == "2iolex"
    assert parsed["user_id"] == "7312367669997503489"
    assert parsed["account_created_at"] == "2023-12-14T08:41:40+00:00"
    assert parsed["username_last_changed_at"] == "2026-09-07T00:51:58+00:00"
    assert parsed["display_name_last_changed_at"] == "2026-09-17T08:40:27+00:00"
    assert parsed["username_history"] is None
    assert parsed["display_name_history"] is None
    assert parsed["location"] is None
    assert parsed["location_at_creation"] is None
    # language=ar must not become location
    assert parsed.get("location") is None


def test_lookup_no_history_field_availability(tiktok_html_no_history: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://www.tiktok.com/@2iolex"

    with patch(
        "social_osint_lookup.platforms.tiktok.fetch_html",
        return_value=(tiktok_html_no_history, mock_resp),
    ):
        result = tiktok.lookup("2iolex")

    assert result["found"] is True
    assert result["username_history"] is None
    assert result["display_name_history"] is None
    assert result["location_at_creation"] is None
    assert result["field_availability"]["username_history"] == "unavailable"
    assert result["field_availability"]["display_name_history"] == "unavailable"
    assert result["field_availability"]["location_at_creation"] == "unavailable"
    assert result["field_availability"]["username_last_changed_at"] == "available"
    assert result["field_availability"]["display_name_last_changed_at"] == "available"
    assert result["username_last_changed_at"] == "2026-09-07T00:51:58+00:00"


def test_normalize_cookie_header_variants():
    from social_osint_lookup.http_client import normalize_cookie_header, redact_secrets

    assert normalize_cookie_header(None) is None
    assert normalize_cookie_header("") is None
    assert normalize_cookie_header("  ") is None
    assert normalize_cookie_header("rawvalue") == "sessionid=rawvalue"
    assert normalize_cookie_header("sessionid=abc") == "sessionid=abc"
    assert normalize_cookie_header("sessionid=abc; sid_guard=xyz") == "sessionid=abc; sid_guard=xyz"


def test_redact_secrets_hides_cookie():
    from social_osint_lookup.http_client import redact_secrets

    secret = "sessionid=SUPERSECRETVALUE123"
    msg = f"HTTPError for cookie {secret} in request"
    out = redact_secrets(msg, secret)
    assert "SUPERSECRETVALUE123" not in out
    assert "[REDACTED]" in out


def test_lookup_attaches_cookie_without_leaking(tiktok_html: str):
    """Cookie is sent on the request; never appears in the result dict."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://www.tiktok.com/@demo_tiktok"
    captured = {}

    def fake_fetch(url, *, session=None, timeout=25.0, referer=None, cookie=None):
        captured["cookie"] = cookie
        return tiktok_html, mock_resp

    with patch("social_osint_lookup.platforms.tiktok.fetch_html", side_effect=fake_fetch):
        result = tiktok.lookup("demo_tiktok", session_cookie="sessionid=TESTCOOKIE_DO_NOT_LEAK")

    assert captured["cookie"] == "sessionid=TESTCOOKIE_DO_NOT_LEAK"
    assert result["auth_mode"] == "session_cookie"
    dumped = str(result)
    assert "TESTCOOKIE_DO_NOT_LEAK" not in dumped
    assert result.get("session_cookie") is None


def test_lookup_public_auth_mode_without_cookie(tiktok_html: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://www.tiktok.com/@demo_tiktok"

    with patch(
        "social_osint_lookup.platforms.tiktok_mobile.lookup_profile",
        return_value=None,
    ), patch(
        "social_osint_lookup.platforms.tiktok.resolve_tiktok_session_cookie",
        return_value=None,
    ), patch(
        "social_osint_lookup.platforms.tiktok.fetch_html",
        return_value=(tiktok_html, mock_resp),
    ):
        result = tiktok.lookup("demo_tiktok")

    assert result["auth_mode"] == "public"
    assert result.get("fetcher") == "html_rehydration"
