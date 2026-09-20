"""Unit tests for tiktok_mobile mapping + fallback behavior."""

from unittest.mock import MagicMock, patch

from social_osint_lookup.platforms import tiktok_mobile as tm


def test_map_upstream_user_rich_fields():
    user = {
        "uniqueId": "demo_tt",
        "nickname": "Demo",
        "id": "123",
        "secUid": "SEC",
        "signature": "hello bio",
        "verified": False,
        "privateAccount": False,
        "region": "SA",
        "createTime": 1702543300,
        "uniqueIdModifyTime": 1788742318,
        "nickNameModifyTime": 1789634427,
        "commerceUserInfo": {"commerceUser": False},
        "uniqueIdHistory": [{"uniqueId": "old_demo", "createTime": 1600000000}],
    }
    stats = {"followerCount": 10, "followingCount": 2, "heartCount": 3, "videoCount": 1}
    mapped = tm.map_upstream_user(
        user, stats, source_url="https://example.test/api", parse_method="fixture"
    )
    assert mapped["username"] == "demo_tt"
    assert mapped["bio"] == "hello bio"
    assert mapped["location"] == "SA"
    assert mapped["account_created_at"]
    assert mapped["username_last_changed_at"]
    assert mapped["display_name_last_changed_at"]
    assert isinstance(mapped["username_history"], list)
    assert mapped["username_history"][0]["username"] == "old_demo"


def test_followers_following_status_honest():
    st = tm.followers_following_status()
    assert st["followers_list_available"] is False
    assert st["following_list_available"] is False


def test_lookup_falls_back_when_api_empty(tiktok_html: str):
    from social_osint_lookup.platforms import tiktok

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

    assert result["found"] is True
    assert result.get("fetcher") == "html_rehydration"
    assert result["username"] == "demo_tiktok"
    assert result["auth_mode"] == "public"
