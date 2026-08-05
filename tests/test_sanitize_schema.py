"""Sanitize and schema contract tests."""

from __future__ import annotations

from supersocks_media_scraper.sanitize import redact_secrets, sanitize_url, scrub_result
from supersocks_media_scraper.schema import build_action_required, make_result


def test_sanitize_url_strips_userinfo_query_fragment() -> None:
    assert (
        sanitize_url("https://user:pass@www.reddit.com/r/announcements/?utm=1#section")
        == "https://www.reddit.com/r/announcements/"
    )


def test_redact_secrets_masks_tokens_and_profile_hints() -> None:
    raw = "TWITTER_AUTH_TOKEN=abc123 ct0=xyz MEDIA_BROWSER_PROFILES_ROOT=/home/me/profiles"
    cleaned = redact_secrets(raw)
    assert "abc123" not in cleaned
    assert "xyz" not in cleaned
    assert "[REDACTED]" in cleaned


def test_make_result_stable_keys_and_scrub() -> None:
    result = make_result(
        status="ok",
        platform="reddit",
        content_kind="post",
        source_url="https://www.reddit.com/r/x/?q=1#y",
        final_url="https://user:tok@www.reddit.com/r/x/",
        title="T",
        text="hello world",
        author={"name": "u", "handle": None, "url": "https://reddit.com/u/u?ref=1"},
        media=[{"kind": "image", "url": "https://i.redd.it/a.png?width=1", "alt": "a"}],
        warnings=["TWITTER_CT0=should-redact"],
    )
    assert set(result) >= {
        "status",
        "platform",
        "content_kind",
        "source_url",
        "final_url",
        "title",
        "text",
        "author",
        "published_at",
        "metrics",
        "media",
        "comments",
        "warnings",
        "action_required",
    }
    assert "?" not in result["source_url"]
    assert "#" not in result["source_url"]
    assert "@" not in result["final_url"]
    assert "should-redact" not in result["warnings"][0]
    assert result["media"][0]["url"] == "https://i.redd.it/a.png"
    assert "profile_dir" not in result


def test_action_required_needs_human() -> None:
    action = build_action_required(platform="instagram", reason="login")
    assert action is not None
    assert action["code"] == "needs-human"
    assert action["reason"] == "login"
    assert "warmup" in action["resume_instructions"].lower() or "warm-up" in action["resume_instructions"].lower()
