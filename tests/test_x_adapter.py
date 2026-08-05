"""X adapter offline tests with mocked twitter-cli."""

from __future__ import annotations

import json
from pathlib import Path

from supersocks_media_scraper.adapters._util import CommandResult
from supersocks_media_scraper.adapters.x import classify_x_url, scrape_x
from supersocks_media_scraper import scrape

FIXTURES = Path(__file__).parent / "fixtures"


def test_classify_x_url() -> None:
    assert classify_x_url("https://x.com/foo/status/123")[0] == "status"
    assert classify_x_url("https://twitter.com/foo")[0] == "user"
    assert classify_x_url("https://x.com/i/article/9")[0] == "article"


def test_scrape_x_missing_credentials() -> None:
    def runner(argv, timeout=30, env=None):  # noqa: ANN001
        raise AssertionError("runner must not be called without credentials")

    result = scrape_x(
        "https://x.com/example/status/1",
        runner=runner,
        environ={},
    )
    assert result is not None
    assert result["status"] == "error"
    assert result["action_required"]["reason"] == "login"
    assert "TWITTER_AUTH_TOKEN" in result["warnings"][0]
    assert "auto-reads" in result["warnings"][0].lower() or "never" in result["warnings"][0].lower()


def test_scrape_x_never_auto_reads_browser_cookies() -> None:
    """Protect the security contract: even with browser-cookie hints present,
    the adapter refuses to call twitter-cli without explicit TWITTER_AUTH_TOKEN
    + TWITTER_CT0, and strips browser auto-read hints from the child env.
    """

    def runner(argv, timeout=30, env=None):  # noqa: ANN001
        raise AssertionError("runner must not be called without explicit credentials")

    # twitter-cli is installed and knows how to auto-read browser cookies,
    # but our package must still refuse until the operator exports both vars.
    result = scrape_x(
        "https://x.com/example/status/1",
        runner=runner,
        environ={
            # browser auto-read hints that twitter-cli would honor:
            "TWITTER_BROWSER": "chrome",
            "TWITTER_CHROME_PROFILE": "/home/user/.config/google-chrome",
            # no TWITTER_AUTH_TOKEN / TWITTER_CT0 -> must refuse
        },
    )
    assert result is not None
    assert result["status"] == "error"
    assert result["action_required"]["reason"] == "login"
    assert "TWITTER_AUTH_TOKEN" in result["warnings"][0]

    # With credentials present, browser hints must be stripped from the child env.
    captured: dict[str, str] = {}

    def runner2(argv, timeout=30, env=None):  # noqa: ANN001
        captured.update(env or {})
        return CommandResult(returncode=1, stdout="", stderr="nope")

    scrape_x(
        "https://x.com/example/status/1",
        runner=runner2,
        environ={
            "TWITTER_AUTH_TOKEN": "tok",
            "TWITTER_CT0": "ct",
            "TWITTER_BROWSER": "chrome",
            "TWITTER_CHROME_PROFILE": "/home/user/Default",
        },
    )
    assert "TWITTER_BROWSER" not in captured
    assert "TWITTER_CHROME_PROFILE" not in captured
    assert captured.get("TWITTER_AUTH_TOKEN") == "tok"
    assert captured.get("TWITTER_CT0") == "ct"


def test_scrape_x_success_sanitizes_urls() -> None:
    payload = json.loads((FIXTURES / "twitter_tweet.json").read_text(encoding="utf-8"))

    def runner(argv, timeout=30, env=None):  # noqa: ANN001
        assert argv[0] == "twitter"
        assert "TWITTER_BROWSER" not in (env or {})
        assert env.get("TWITTER_AUTH_TOKEN") == "tok"
        return CommandResult(returncode=0, stdout=json.dumps(payload), stderr="")

    result = scrape_x(
        "https://x.com/example/status/1?s=20",
        runner=runner,
        environ={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct"},
    )
    assert result is not None
    assert result["status"] == "ok"
    assert result["platform"] == "x"
    assert result["content_kind"] == "post"
    assert "Synthetic tweet" in result["text"]
    assert result["author"]["handle"] == "example"
    assert "?" not in (result["author"]["url"] or "")
    assert "#" not in (result["author"]["url"] or "")
    assert result["media"][0]["url"] == "https://pbs.twimg.com/media/EXAMPLE.jpg"
    assert result["metrics"]["likes"] == 10
    dumped = json.dumps(result)
    assert "tok" not in dumped
    assert "TWITTER_CT0" not in dumped
    assert "ct0" not in dumped.lower()


def test_scrape_x_rate_limit() -> None:
    def runner(argv, timeout=30, env=None):  # noqa: ANN001
        return CommandResult(
            returncode=1,
            stdout=json.dumps({"ok": False, "error": {"code": "429", "message": "Too Many Requests"}}),
            stderr="",
        )

    result = scrape_x(
        "https://x.com/example/status/1",
        runner=runner,
        environ={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct"},
    )
    assert result is not None
    assert result["status"] == "error"
    assert result["action_required"]["reason"] == "rate-limit"


def test_public_scrape_routes_x() -> None:
    def runner(argv, timeout=30, env=None):  # noqa: ANN001
        return CommandResult(
            returncode=0,
            stdout=json.dumps(
                {"ok": True, "data": {"full_text": "hi", "author": {"screen_name": "a"}}}
            ),
            stderr="",
        )

    result = scrape(
        "https://twitter.com/a/status/99",
        twitter_runner=runner,
        environ={"TWITTER_AUTH_TOKEN": "tok", "TWITTER_CT0": "ct"},
    )
    assert result["platform"] == "x"
    assert result["status"] == "ok"
