"""Regression tests: Cloak/Playwright failures never leak unsafe details."""

from __future__ import annotations

import json
from pathlib import Path

from supersocks_media_scraper import scrape
from supersocks_media_scraper.sanitize import sanitize_browser_error, scrub_public_warning
from supersocks_media_scraper.warmup import run_warmup

FORBIDDEN_SUBSTRINGS = (
    "/root/.cloakbrowser",
    "/home/scraper/",
    "/home/me/",
    "TWITTER_AUTH_TOKEN=secret",
    "auth_token=abc",
    "ct0=xyz",
    "--user-data-dir",
    "--disable-field-trial-config",
    "Traceback (most recent call last)",
    "Call log:",
    "/usr/bin/google-chrome",
)


RAW_PLAYWRIGHT_ERRORS = (
    """BrowserType.launch: Executable doesn't exist at /root/.cloakbrowser/chromium-1.2.3/chrome-linux/chrome
╔════════════════════════════════════════════════════════════╗
║ Looks like Playwright was just installed or updated.       ║
╚════════════════════════════════════════════════════════════╝
""",
    """browserType.launchPersistentContext: Failed to launch: error while loading shared libraries: libnss3.so: cannot open shared object file: No such file or directory
""",
    """Timeout 30000ms exceeded.
=========================== logs ===========================
  /usr/bin/google-chrome --disable-field-trial-config --user-data-dir=/tmp/playwright_chrome_profile --no-sandbox
============================================================
TWITTER_AUTH_TOKEN=secret ct0=xyz
""",
    """Target page, context or browser has been closed
Call log:
  - navigating to "https://www.reddit.com/"
  - waiting for navigation
""",
    """RuntimeError: unexpected cloak dump with path /home/me/media-browser-profiles/reddit and cookie auth_token=abc123
""",
)


def _assert_safe(text: str) -> None:
    lowered = text.lower()
    for banned in FORBIDDEN_SUBSTRINGS:
        assert banned.lower() not in lowered, f"leaked {banned!r} in {text!r}"
    assert "/root/" not in text
    assert "Traceback" not in text
    assert "Call log" not in text


def test_sanitize_browser_error_classifies_representative_dumps() -> None:
    classified = [sanitize_browser_error(raw, context="render") for raw in RAW_PLAYWRIGHT_ERRORS]
    assert any("missing Chromium system libraries" in msg for msg in classified)
    assert any("binary unavailable" in msg or "could not start" in msg for msg in classified)
    assert any("timed out" in msg for msg in classified)
    assert any("session closed" in msg for msg in classified)
    for msg in classified:
        assert msg.startswith("cloak media render failed:")
        _assert_safe(msg)
        assert "chromium-1.2.3" not in msg
        assert "libnss3.so" not in msg


def test_sanitize_browser_error_warmup_prefix() -> None:
    msg = sanitize_browser_error(RAW_PLAYWRIGHT_ERRORS[1], context="warmup")
    assert msg.startswith("media warm-up failed:")
    assert "missing Chromium system libraries" in msg
    _assert_safe(msg)


def test_scrub_public_warning_strips_paths_and_commands() -> None:
    cleaned = scrub_public_warning(
        "fail at /root/.cloakbrowser/x chrome --user-data-dir=/tmp/p TWITTER_CT0=leak"
    )
    _assert_safe(cleaned)
    assert "leak" not in cleaned
    assert "[REDACTED]" in cleaned or "[path-redacted]" in cleaned or "omitted" in cleaned.lower()


def test_scrape_cloak_injects_raw_playwright_error_safely() -> None:
    def boom(url, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError(RAW_PLAYWRIGHT_ERRORS[0])

    result = scrape(
        "https://www.reddit.com/r/announcements/comments/abc/title/",
        cloak_fetcher=boom,
        environ={},
    )
    assert result["status"] == "error"
    assert result["platform"] == "reddit"
    dumped = json.dumps(result)
    _assert_safe(dumped)
    assert "cloak media render failed" in dumped
    assert "binary unavailable" in dumped or "could not start" in dumped
    # needs-human gates are unrelated to launch failures; keep action_required null here
    assert result.get("action_required") is None


def test_scrape_cloak_shared_library_error_is_actionable() -> None:
    def boom(url, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError(RAW_PLAYWRIGHT_ERRORS[1])

    result = scrape(
        "https://www.instagram.com/p/example/",
        cloak_fetcher=boom,
        environ={},
    )
    warning = result["warnings"][0]
    assert "missing Chromium system libraries" in warning
    assert "Docker" in warning or "Linux packages" in warning
    _assert_safe(json.dumps(result))


def test_warmup_injects_raw_playwright_error_safely(tmp_path: Path) -> None:
    root = tmp_path / "profiles"
    root.mkdir()

    def boom(url, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError(RAW_PLAYWRIGHT_ERRORS[2])

    result = run_warmup(
        "facebook",
        create_profile=True,
        environ={"MEDIA_BROWSER_PROFILES_ROOT": str(root)},
        cloak_fetcher=boom,
        wait_seconds=0.01,
    )
    assert result["status"] == "error"
    assert result["action_required"]["code"] == "needs-human"
    assert result["action_required"]["reason"] == "challenge"
    dumped = json.dumps(result)
    _assert_safe(dumped)
    assert str(root) not in dumped
    assert "media warm-up failed" in dumped
    assert "timed out" in dumped


def test_needs_human_gate_still_preserved() -> None:
    """Launch sanitization must not erase login/consent needs-human behavior."""
    html = (
        Path(__file__).parent / "fixtures" / "instagram_login.html"
    ).read_text(encoding="utf-8")

    class Page:
        final_url = "https://www.instagram.com/accounts/login/"
        status_code = 200
        title = "Login"
        method = "cloak"
        consent_action = None

        def __init__(self) -> None:
            self.html = html

    def fetcher(url, **kwargs):  # noqa: ANN001, ANN003
        return Page()

    result = scrape(
        "https://www.instagram.com/p/example/",
        cloak_fetcher=fetcher,
        environ={},
    )
    assert result["action_required"] is not None
    assert result["action_required"]["code"] == "needs-human"
    assert result["action_required"]["reason"] == "login"
