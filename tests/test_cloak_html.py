"""Cloak HTML parsing and gate detection against synthetic fixtures."""

from __future__ import annotations

from pathlib import Path

from supersocks_media_scraper.adapters.cloak_html import detect_gate, parse_cloak_html

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_reddit_post_fixture() -> None:
    html = _load("reddit_post.html")
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/announcements/comments/abc/title/?utm=1",
        final_url="https://www.reddit.com/r/announcements/comments/abc/title/",
        fetch_method="cloak",
    )
    assert result["status"] == "ok"
    assert result["platform"] == "reddit"
    assert result["content_kind"] == "post"
    assert "Example Reddit Post" in (result["title"] or "")
    assert "Visible public body" in result["text"]
    assert result["author"]["name"]
    assert result["published_at"]
    assert result["media"]
    assert result["media"][0]["kind"] == "image"
    assert "?" not in result["source_url"]
    assert result["metrics"]["likes"] == 42
    assert result["metrics"]["comments"] == 7
    assert result["comments"]
    assert result["action_required"] is None


def test_instagram_login_gate() -> None:
    html = _load("instagram_login.html")
    assert detect_gate(html, platform="instagram") == "login"
    result = parse_cloak_html(
        html,
        platform="instagram",
        source_url="https://www.instagram.com/p/EXAMPLE/",
    )
    assert result["status"] == "error"
    assert result["action_required"]["code"] == "needs-human"
    assert result["action_required"]["reason"] == "login"
    assert result["text"] == ""
    assert result["media"] == []


def test_reddit_challenge_and_rate_limit() -> None:
    challenge = _load("reddit_challenge.html")
    assert detect_gate(challenge, platform="reddit") in {"challenge", "captcha"}
    rate = _load("rate_limit.html")
    assert detect_gate(rate, platform="reddit") == "rate-limit"
    assert detect_gate("<html></html>", platform="reddit", http_status=429) == "rate-limit"


def test_facebook_consent_gate() -> None:
    html = _load("facebook_consent.html")
    assert detect_gate(html, platform="facebook") == "consent"
