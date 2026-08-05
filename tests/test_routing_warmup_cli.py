"""Profiles, warm-up, CLI, and routing offline tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from supersocks_media_scraper import detect_platform, scrape
from supersocks_media_scraper.cli import main
from supersocks_media_scraper.profiles import resolve_profile_dir
from supersocks_media_scraper.warmup import run_warmup

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class FakePage:
    final_url: str
    status_code: int
    html: str
    title: str | None = None
    method: str = "cloak-profile"
    consent_action: str | None = None


def test_detect_platform() -> None:
    assert detect_platform("https://x.com/a/status/1") == "x"
    assert detect_platform("https://www.instagram.com/p/x/") == "instagram"
    assert detect_platform("https://www.facebook.com/x/posts/1") == "facebook"
    assert detect_platform("https://www.reddit.com/r/x/") == "reddit"
    assert detect_platform("https://www.youtube.com/watch?v=1") is None
    assert detect_platform("https://www.linkedin.com/in/x") is None
    assert detect_platform("https://user:pass@reddit.com/r/x/") is None


def test_resolve_profile_dir_uses_media_root(tmp_path: Path) -> None:
    root = tmp_path / "profiles"
    path = resolve_profile_dir(
        "",
        platform="reddit",
        environ={"MEDIA_BROWSER_PROFILES_ROOT": str(root)},
    )
    assert path == str(root / "reddit")


def test_warmup_missing_profile_config() -> None:
    result = run_warmup("reddit", environ={})
    assert result["status"] == "error"
    assert result["action_required"]["reason"] == "login"
    assert "MEDIA_BROWSER_PROFILES_ROOT" in result["warnings"][0]
    assert "profile_dir" not in result
    dumped = json.dumps(result)
    assert "/home/" not in dumped


def test_warmup_with_fake_fetcher(tmp_path: Path) -> None:
    root = tmp_path / "profiles"
    html = (FIXTURES / "reddit_post.html").read_text(encoding="utf-8")

    def fetcher(url, **kwargs):  # noqa: ANN001, ANN003
        assert kwargs.get("headless") is False
        return FakePage(final_url=url + "?utm=1#x", status_code=200, html=html, title="ok")

    result = run_warmup(
        "reddit",
        create_profile=True,
        environ={"MEDIA_BROWSER_PROFILES_ROOT": str(root)},
        cloak_fetcher=fetcher,
        wait_seconds=0.01,
    )
    assert result["status"] == "ok"
    assert result["profile"]["configured"] is True
    assert result["profile"]["exists"] is True
    assert "?" not in result["url"]
    assert "#" not in result["final_url"]
    assert str(root) not in json.dumps(result)


def test_scrape_cloak_via_fake_fetcher() -> None:
    html = (FIXTURES / "reddit_post.html").read_text(encoding="utf-8")

    def fetcher(url, **kwargs):  # noqa: ANN001, ANN003
        return FakePage(final_url=url, status_code=200, html=html, title="Example")

    result = scrape(
        "https://www.reddit.com/r/announcements/comments/abc/title/",
        cloak_fetcher=fetcher,
        environ={},
    )
    assert result["status"] == "ok"
    assert result["platform"] == "reddit"
    assert result["fetch_method"] == "cloak-profile" or result.get("fetch_method") == "cloak"


def test_scrape_unsupported_url() -> None:
    result = scrape("https://example.com/page")
    assert result["status"] == "error"
    assert "unsupported" in result["warnings"][0].lower() or "LinkedIn" in result["warnings"][0]


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.1.0" in capsys.readouterr().out


def test_cli_offline_unsupported(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["https://example.com/"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert "cookie" not in json.dumps(payload).lower() or "never" in json.dumps(payload).lower()
