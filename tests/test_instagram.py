"""Unit tests for Instagram platform module (mocked HTML)."""

from unittest.mock import MagicMock, patch

from social_osint_lookup.platforms import instagram


def test_normalize_username_variants():
    assert instagram.normalize_username("@demo_ig") == "demo_ig"
    assert instagram.normalize_username("demo_ig") == "demo_ig"
    assert instagram.normalize_username("https://www.instagram.com/demo_ig/") == "demo_ig"
    assert instagram.normalize_username("https://instagram.com/demo_ig") == "demo_ig"


def test_parse_shared_data(instagram_html: str):
    parsed = instagram.parse_profile_html(instagram_html, username_hint="demo_ig")
    assert parsed["username"] == "demo_ig"
    assert parsed["display_name"] == "Demo IG User"
    assert parsed["user_id"] == "9876543210"
    assert parsed["bio"] == "Public demo bio for Instagram"
    assert parsed["follower_count"] == 1234
    assert parsed["following_count"] == 56
    assert parsed["post_count"] == 78
    assert parsed["verified"] is False
    assert parsed["private"] is False
    assert parsed["parse_method"] == "shared_data"


def test_parse_meta_only_counts():
    html = """
    <html><head>
      <meta property="og:title" content="Meta Only (@meta_user)" />
      <meta property="og:description" content="2.5K Followers, 10 Following, 3 Posts - Hello world" />
    </head><body></body></html>
    """
    parsed = instagram.parse_profile_html(html, username_hint="meta_user")
    assert parsed["username"] == "meta_user"
    assert parsed["display_name"] == "Meta Only"
    assert parsed["follower_count"] == 2500
    assert parsed["following_count"] == 10
    assert parsed["post_count"] == 3
    assert parsed["parse_method"] == "meta_tags"
    assert "Hello world" in (parsed["bio"] or "")


def test_lookup_mocked(instagram_html: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://www.instagram.com/demo_ig/"

    with patch(
        "social_osint_lookup.platforms.instagram.fetch_html",
        return_value=(instagram_html, mock_resp),
    ):
        result = instagram.lookup("demo_ig")

    assert result["platform"] == "instagram"
    assert result["found"] is True
    assert result["username"] == "demo_ig"
    assert result["follower_count"] == 1234
    assert result["error"] is None
