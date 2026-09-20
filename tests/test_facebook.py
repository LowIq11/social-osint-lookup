"""Unit tests for Facebook platform module (mocked HTML)."""

from unittest.mock import MagicMock, patch

from social_osint_lookup.platforms import facebook


def test_normalize_slug_variants():
    slug, url = facebook.normalize_slug("demopage")
    assert slug == "demopage"
    assert url == "https://www.facebook.com/demopage"

    slug, url = facebook.normalize_slug("https://www.facebook.com/demopage")
    assert slug == "demopage"

    slug, url = facebook.normalize_slug("https://www.facebook.com/profile.php?id=555666777888")
    assert slug == "555666777888"
    assert "profile.php?id=555666777888" in url

    slug, url = facebook.normalize_slug("555666777888")
    assert slug == "555666777888"
    assert "profile.php?id=555666777888" in url


def test_parse_page(facebook_page_html: str):
    parsed = facebook.parse_profile_html(
        facebook_page_html,
        slug="demopage",
        profile_url="https://www.facebook.com/demopage",
    )
    assert parsed["display_name"] == "Demo Page"
    assert "demo page" in (parsed["about"] or "").lower()
    assert parsed["entity_type"] == "page"
    assert parsed["user_id"] == "111222333444"
    assert parsed["username"] == "demopage"


def test_parse_profile(facebook_profile_html: str):
    parsed = facebook.parse_profile_html(
        facebook_profile_html,
        slug="555666777888",
        profile_url="https://www.facebook.com/profile.php?id=555666777888",
    )
    assert parsed["display_name"] == "Demo Person"
    assert parsed["entity_type"] == "profile"
    assert parsed["user_id"] == "555666777888"
    assert parsed["username"] is None


def test_lookup_mocked(facebook_page_html: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://www.facebook.com/demopage"

    with patch(
        "social_osint_lookup.platforms.facebook.fetch_html",
        return_value=(facebook_page_html, mock_resp),
    ):
        result = facebook.lookup("demopage")

    assert result["platform"] == "facebook"
    assert result["found"] is True
    assert result["display_name"] == "Demo Page"
    assert result["entity_type"] == "page"
    assert result["error"] is None
