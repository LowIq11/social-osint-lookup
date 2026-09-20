from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def tiktok_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "tiktok_profile.html").read_text(encoding="utf-8")


@pytest.fixture
def instagram_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "instagram_profile.html").read_text(encoding="utf-8")


@pytest.fixture
def facebook_page_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "facebook_page.html").read_text(encoding="utf-8")


@pytest.fixture
def facebook_profile_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "facebook_profile.html").read_text(encoding="utf-8")
