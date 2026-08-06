"""Deterministic tests for the live smoke harness (no network)."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from supersocks_media_scraper.live_smoke import (
    CLASSIFICATIONS,
    DEFAULT_PUBLIC_URLS,
    aggregate_summary,
    auth_presence,
    classify_case,
    default_mode_case_passes,
    has_useful_content,
    main,
    require_success_case_passes,
    resolve_urls,
    run_smoke,
    scrub_case_payload,
    validate_result_schema,
)
from supersocks_media_scraper.schema import build_action_required, make_result


def _ok_reddit(**kwargs: Any) -> dict[str, Any]:
    base = make_result(
        status="ok",
        platform="reddit",
        content_kind="post",
        source_url="https://www.reddit.com/r/announcements/comments/abc/title/",
        final_url="https://www.reddit.com/r/announcements/comments/abc/title/",
        title="Example",
        text="Visible post body for smoke classification.",
        author={"name": "u", "handle": "u", "url": "https://www.reddit.com/user/u"},
        warnings=[],
    )
    base.update(kwargs)
    return base


def test_default_urls_cover_four_platforms() -> None:
    assert set(DEFAULT_PUBLIC_URLS) == {"x", "reddit", "instagram", "facebook"}
    for url in DEFAULT_PUBLIC_URLS.values():
        assert url.startswith("https://")


def test_has_useful_content_requires_non_empty_fields() -> None:
    assert has_useful_content(_ok_reddit()) is True
    empty = make_result(
        status="ok",
        platform="reddit",
        source_url="https://www.reddit.com/r/x/",
        text="",
        title=None,
        author={"name": None, "handle": None, "url": None},
        media=[],
        comments=[],
    )
    assert has_useful_content(empty) is False
    media_only = make_result(
        status="ok",
        platform="instagram",
        source_url="https://www.instagram.com/p/x/",
        text="",
        media=[{"kind": "image", "url": "https://example.com/a.jpg", "alt": None}],
    )
    assert has_useful_content(media_only) is True


def test_validate_result_schema_accepts_stable_contract() -> None:
    ok, issues = validate_result_schema(_ok_reddit())
    assert ok is True
    assert issues == []


def test_validate_result_schema_rejects_missing_and_banned() -> None:
    bad = {"status": "ok"}
    ok, issues = validate_result_schema(bad)
    assert ok is False
    assert any("missing keys" in i for i in issues)

    leaky = _ok_reddit()
    leaky["profile_dir"] = "/home/me/profiles/reddit"
    ok2, issues2 = validate_result_schema(leaky)
    assert ok2 is False
    assert any("banned field" in i for i in issues2)

    unsanitized = _ok_reddit()
    unsanitized["source_url"] = "https://www.reddit.com/r/x/?utm=1"
    ok3, issues3 = validate_result_schema(unsanitized)
    assert ok3 is False
    assert any("not sanitized" in i for i in issues3)


def test_classify_needs_human_never_content_success() -> None:
    payload = make_result(
        status="error",
        platform="instagram",
        source_url="https://www.instagram.com/instagram/",
        warnings=["login wall"],
        action_required=build_action_required(platform="instagram", reason="login"),
    )
    label = classify_case(
        requested_platform="instagram",
        url="https://www.instagram.com/instagram/",
        payload=payload,
    )
    assert label == "needs-human"
    assert label != "content-success"
    assert default_mode_case_passes(label) is True
    assert require_success_case_passes(label) is False


def test_classify_content_success() -> None:
    label = classify_case(
        requested_platform="reddit",
        url="https://www.reddit.com/r/announcements/comments/abc/title/",
        payload=_ok_reddit(),
    )
    assert label == "content-success"


def test_classify_schema_error_and_runtime_error() -> None:
    assert (
        classify_case(
            requested_platform="reddit",
            url="https://www.reddit.com/r/x/",
            payload={"status": "ok"},
        )
        == "schema-error"
    )
    assert (
        classify_case(
            requested_platform="reddit",
            url="https://www.reddit.com/r/x/",
            payload=None,
            invoke_error="boom",
        )
        == "runtime-error"
    )


def test_classify_unsupported_invalid() -> None:
    payload = make_result(
        status="error",
        platform=None,
        source_url="https://example.com/",
        warnings=["unsupported or unsafe URL; supported platforms are x.com/twitter.com"],
    )
    assert (
        classify_case(
            requested_platform="reddit",
            url="https://example.com/",
            payload=payload,
        )
        == "unsupported/invalid"
    )
    assert (
        classify_case(
            requested_platform="x",
            url="https://www.reddit.com/r/x/",
            payload=_ok_reddit(),
        )
        == "unsupported/invalid"
    )


def test_classify_empty_ok_without_gate_is_runtime_error() -> None:
    empty = make_result(
        status="ok",
        platform="reddit",
        source_url="https://www.reddit.com/r/announcements/comments/abc/title/",
        text="",
        title=None,
    )
    assert (
        classify_case(
            requested_platform="reddit",
            url="https://www.reddit.com/r/announcements/comments/abc/title/",
            payload=empty,
        )
        == "runtime-error"
    )


def test_auth_presence_reports_booleans_only() -> None:
    hints = auth_presence(
        {
            "TWITTER_AUTH_TOKEN": "secret-token-value",
            "TWITTER_CT0": "",
            "MEDIA_BROWSER_PROFILES_ROOT": "/home/me/secret-profiles",
        }
    )
    dumped = json.dumps(hints)
    assert "secret-token-value" not in dumped
    assert "/home/me" not in dumped
    assert hints["x_env_present"]["TWITTER_AUTH_TOKEN"] is True
    assert hints["x_env_present"]["TWITTER_CT0"] is False
    assert hints["media_browser_profiles_root_configured"] is True


def test_scrub_case_payload_redacts_and_omits_secrets() -> None:
    payload = _ok_reddit(
        warnings=["TWITTER_AUTH_TOKEN=abc123 should never leak"],
    )
    scrubbed = scrub_case_payload(payload)
    assert scrubbed is not None
    assert "abc123" not in json.dumps(scrubbed)
    assert "text" not in scrubbed
    assert scrubbed["text_len"] > 0
    assert scrubbed["has_useful_content"] is True


def test_aggregate_exit_modes() -> None:
    cases = [
        {
            "platform": "reddit",
            "classification": "needs-human",
            "url": "https://www.reddit.com/r/x/",
        },
        {
            "platform": "x",
            "classification": "content-success",
            "url": "https://x.com/a/status/1",
        },
    ]
    verify = aggregate_summary(cases, require_success=False)
    assert verify["pass"] is True
    assert verify["mode"] == "verify"
    assert set(verify["counts"]) >= CLASSIFICATIONS

    strict = aggregate_summary(cases, require_success=True)
    assert strict["pass"] is False
    assert strict["mode"] == "require-success"

    all_success = aggregate_summary(
        [
            {"platform": "reddit", "classification": "content-success"},
            {"platform": "x", "classification": "content-success"},
        ],
        require_success=True,
    )
    assert all_success["pass"] is True


def test_resolve_urls_overrides() -> None:
    urls = resolve_urls(
        platforms=("reddit", "x"),
        url_overrides={"reddit": "https://www.reddit.com/r/announcements/comments/zz/t/"},
    )
    assert urls["reddit"].endswith("/t/")
    assert urls["x"] == DEFAULT_PUBLIC_URLS["x"]


def test_run_smoke_injected_invoker_verify_and_require_success() -> None:
    def invoker(url: str, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN003
        if "reddit.com" in url:
            return {
                "payload": make_result(
                    status="error",
                    platform="reddit",
                    source_url=url.split("?")[0],
                    warnings=["consent wall"],
                    action_required=build_action_required(platform="reddit", reason="consent"),
                ),
                "exit_code": 1,
                "error": None,
                "stderr_redacted": "",
                "argv_kind": "injected",
            }
        if "x.com" in url or "twitter.com" in url:
            return {
                "payload": make_result(
                    status="ok",
                    platform="x",
                    content_kind="post",
                    source_url=url.split("?")[0],
                    text="Hello from X smoke fixture.",
                    author={"name": "X", "handle": "X", "url": "https://x.com/X"},
                ),
                "exit_code": 0,
                "error": None,
                "stderr_redacted": "",
                "argv_kind": "injected",
            }
        if "instagram.com" in url:
            return {
                "payload": make_result(
                    status="error",
                    platform="instagram",
                    source_url=url.split("?")[0],
                    warnings=["login"],
                    action_required=build_action_required(platform="instagram", reason="login"),
                ),
                "exit_code": 1,
                "error": None,
                "stderr_redacted": "",
                "argv_kind": "injected",
            }
        return {
            "payload": make_result(
                status="error",
                platform="facebook",
                source_url=url.split("?")[0],
                warnings=["login"],
                action_required=build_action_required(platform="facebook", reason="login"),
            ),
            "exit_code": 1,
            "error": None,
            "stderr_redacted": "",
            "argv_kind": "injected",
        }

    summary = run_smoke(
        platforms=("x", "reddit", "instagram", "facebook"),
        require_success=False,
        invoker=invoker,
        environ={},
    )
    assert summary["pass"] is True
    by_platform = {c["platform"]: c["classification"] for c in summary["cases"]}
    assert by_platform["x"] == "content-success"
    assert by_platform["reddit"] == "needs-human"
    assert by_platform["instagram"] == "needs-human"
    assert by_platform["facebook"] == "needs-human"
    dumped = json.dumps(summary)
    assert "/home/" not in dumped

    strict = run_smoke(
        platforms=("x", "reddit"),
        require_success=True,
        invoker=invoker,
        environ={},
    )
    assert strict["pass"] is False


def test_run_smoke_runtime_error_fails_verify() -> None:
    def invoker(url: str, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN003
        return {
            "payload": None,
            "exit_code": None,
            "error": "scraper stdout was not valid JSON",
            "stderr_redacted": "Traceback (most recent call last): /home/me/secret",
            "argv_kind": "injected",
        }

    summary = run_smoke(platforms=("reddit",), invoker=invoker, environ={})
    assert summary["pass"] is False
    assert summary["cases"][0]["classification"] == "runtime-error"
    assert "/home/me" not in json.dumps(summary)


def test_cli_main_help_and_bad_platform() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0

    with pytest.raises(SystemExit) as exc2:
        main(["--platforms", "youtube"])
    assert exc2.value.code == 2


def test_profiles_root_sets_env_but_not_printed() -> None:
    seen_env: dict[str, str] = {}

    def invoker(url: str, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN003
        environ = kwargs.get("environ") or {}
        seen_env.update(dict(environ))
        return {
            "payload": make_result(
                status="error",
                platform="reddit",
                source_url=url.split("?")[0],
                action_required=build_action_required(platform="reddit", reason="login"),
                warnings=["gate"],
            ),
            "exit_code": 1,
            "error": None,
            "stderr_redacted": "",
            "argv_kind": "injected",
        }

    summary = run_smoke(
        platforms=("reddit",),
        profiles_root="/tmp/secret-media-profiles-xyz",
        invoker=invoker,
        environ={},
    )
    assert seen_env.get("MEDIA_BROWSER_PROFILES_ROOT") == "/tmp/secret-media-profiles-xyz"
    assert "/tmp/secret-media-profiles-xyz" not in json.dumps(summary)
    assert summary["auth_hints"]["media_browser_profiles_root_configured"] is True


def test_output_contract_never_echoes_cookie_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "super-secret-auth")
    monkeypatch.setenv("TWITTER_CT0", "super-secret-ct0")

    def invoker(url: str, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN003
        return {
            "payload": make_result(
                status="error",
                platform="x",
                source_url="https://x.com/X/status/20",
                warnings=["TWITTER_AUTH_TOKEN=super-secret-auth leaked?"],
                action_required=build_action_required(platform="x", reason="login"),
            ),
            "exit_code": 1,
            "error": None,
            "stderr_redacted": "",
            "argv_kind": "injected",
        }

    summary = run_smoke(platforms=("x",), invoker=invoker, environ=dict(os.environ))
    dumped = json.dumps(summary)
    assert "super-secret-auth" not in dumped
    assert "super-secret-ct0" not in dumped
    assert summary["auth_hints"]["x_env_present"]["TWITTER_AUTH_TOKEN"] is True
    assert summary["auth_hints"]["x_env_present"]["TWITTER_CT0"] is True
