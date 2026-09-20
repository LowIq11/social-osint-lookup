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
def x_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "x_profile.html").read_text(encoding="utf-8")


@pytest.fixture
def tiktok_html_no_history(fixtures_dir: Path) -> str:
    return (fixtures_dir / "tiktok_profile_no_history.html").read_text(encoding="utf-8")
