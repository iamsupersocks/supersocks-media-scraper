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


def test_parse_instagram_post_og_metrics_and_author() -> None:
    html = _load("instagram_post.html")
    result = parse_cloak_html(
        html,
        platform="instagram",
        source_url="https://www.instagram.com/p/EXAMPLE/",
    )
    assert result["status"] == "ok"
    assert result["metrics"]["likes"] == 268_000
    assert result["metrics"]["comments"] == 11_000
    assert result["author"]["handle"] == "example_creator"
    assert result["author"]["name"] == "Example Creator"
    assert "Public caption text from smoke render" in result["text"]


def test_parse_facebook_post_metrics_and_comments() -> None:
    html = _load("facebook_post.html")
    result = parse_cloak_html(
        html,
        platform="facebook",
        source_url="https://www.facebook.com/example/posts/123",
    )
    assert result["status"] == "ok"
    assert result["metrics"]["likes"] == 9400
    assert result["metrics"]["comments"] == 120
    assert result["metrics"]["shares"] == 32
    assert "Visible Facebook post body from metadata" in result["text"]
    assert len(result["comments"]) == 2
    assert result["comments"][0]["author"] == "Alice Dupont"
    assert "Alice comment text visible" in (result["comments"][0]["text"] or "")
    assert result["comments"][1]["author"] == "Bob Smith"
    assert "J'aime" not in (result["comments"][0]["text"] or "")


def test_parse_reddit_shreddit_post_by_url_id() -> None:
    html = _load("reddit_shreddit_post.html")
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/announcements/comments/abc123/title/",
        final_url="https://www.reddit.com/r/announcements/comments/abc123/title/",
    )
    assert result["status"] == "ok"
    assert result["title"] != "Wrong cached title"
    assert "Example Reddit Post" in (result["title"] or "")
    assert "Visible public body from shreddit slot=text-body only" in result["text"]
    assert "Wrong post body" not in result["text"]
    assert result["author"]["name"] == "example_user"
    assert result["published_at"] == "2026-01-15T12:00:00Z"
    assert result["metrics"]["likes"] == 42
    assert result["metrics"]["comments"] == 7
    assert len(result["comments"]) == 1
    assert result["comments"][0]["author"] == "commenter1"
    assert "Continuer ce fil" not in str(result["comments"])


def test_reddit_post_with_429_text_not_rate_limited() -> None:
    html = _load("reddit_post_with_429_text.html")
    assert detect_gate(html, platform="reddit") is None
    result = parse_cloak_html(
        html,
        platform="reddit",
        source_url="https://www.reddit.com/r/api/comments/doc429/title/",
    )
    assert result["status"] == "ok"
    assert result["action_required"] is None
    assert "HTTP 429" in result["text"]
