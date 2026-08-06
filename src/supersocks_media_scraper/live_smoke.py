"""Honest live smoke harness for the four supported platforms.

Invokes the installed/current scraper safely (subprocess by default), classifies
each case without treating needs-human as extraction success, and emits a
sanitized machine-readable aggregate summary. Never prints env secrets, cookie
values, profile paths/contents, or raw browser dumps.

X credentials remain explicit TWITTER_AUTH_TOKEN / TWITTER_CT0 only; this harness
never inspects browser cookie stores.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from . import __version__
from .adapters._util import detect_platform, is_safe_public_http_url
from .sanitize import redact_secrets, sanitize_url, scrub_public_warning
from .schema import (
    CONTENT_KINDS,
    GATE_REASONS,
    NEEDS_HUMAN_CODE,
    PLATFORMS,
    STATUSES,
)

SUPPORTED_PLATFORMS: tuple[str, ...] = ("x", "reddit", "instagram", "facebook")

# Operator-overridable public smoke URLs. Live results vary by auth/profile state.
DEFAULT_PUBLIC_URLS: dict[str, str] = {
    "x": "https://x.com/X/status/20",
    "reddit": (
        "https://www.reddit.com/r/ModSupport/comments/1rshtk3/"
        "how_do_i_post_an_announcement_i_dont_see_anywhere/"
    ),
    "instagram": "https://www.instagram.com/instagram/",
    "facebook": "https://www.facebook.com/facebook/",
}

CLASSIFICATIONS = frozenset(
    {
        "content-success",
        "needs-human",
        "runtime-error",
        "unsupported/invalid",
        "schema-error",
    }
)

REQUIRED_RESULT_KEYS = frozenset(
    {
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
)

ScraperInvoker = Callable[..., dict[str, Any]]


def env_flag_present(name: str, environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    value = env.get(name)
    return bool(value and str(value).strip())


def auth_presence(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Presence-only auth/profile hints — never values or paths."""
    env = environ if environ is not None else os.environ
    return {
        "x_env_present": {
            "TWITTER_AUTH_TOKEN": env_flag_present("TWITTER_AUTH_TOKEN", env),
            "TWITTER_CT0": env_flag_present("TWITTER_CT0", env),
        },
        "media_browser_profiles_root_configured": env_flag_present(
            "MEDIA_BROWSER_PROFILES_ROOT", env
        ),
        "media_browser_profile_dir_configured": env_flag_present(
            "MEDIA_BROWSER_PROFILE_DIR", env
        )
        or env_flag_present("BROWSER_PROFILE_DIR", env),
    }


def has_useful_content(payload: Mapping[str, Any] | None) -> bool:
    """True when the payload contains non-empty useful scraped fields."""
    if not isinstance(payload, Mapping):
        return False
    text = str(payload.get("text") or "").strip()
    title = str(payload.get("title") or "").strip()
    if text or title:
        return True
    author = payload.get("author")
    if isinstance(author, Mapping):
        if str(author.get("name") or "").strip() or str(author.get("handle") or "").strip():
            return True
    media = payload.get("media")
    if isinstance(media, list):
        for item in media:
            if isinstance(item, Mapping) and str(item.get("url") or "").strip():
                return True
    comments = payload.get("comments")
    if isinstance(comments, list):
        for item in comments:
            if isinstance(item, Mapping) and str(item.get("text") or "").strip():
                return True
    return False


def _is_needs_human(payload: Mapping[str, Any]) -> bool:
    action = payload.get("action_required")
    if not isinstance(action, Mapping):
        return False
    return str(action.get("code") or "") == NEEDS_HUMAN_CODE


def _looks_unsupported(payload: Mapping[str, Any], *, requested_platform: str) -> bool:
    platform = payload.get("platform")
    warnings = payload.get("warnings") or []
    joined = " ".join(str(w).lower() for w in warnings) if isinstance(warnings, list) else ""
    if platform is None and (
        "unsupported" in joined or "unsafe url" in joined or "empty url" in joined
    ):
        return True
    if platform is not None and platform not in PLATFORMS:
        return True
    if requested_platform and platform not in (None, requested_platform):
        # Unexpected platform mismatch on a known route — treat as schema/contract issue upstream.
        return False
    if "unsupported" in joined or "unsafe url" in joined:
        return True
    return False


def validate_result_schema(payload: Any) -> tuple[bool, list[str]]:
    """Validate stable outbound scraper JSON shape. Returns (ok, issues)."""
    issues: list[str] = []
    if not isinstance(payload, dict):
        return False, ["payload is not a JSON object"]

    missing = sorted(REQUIRED_RESULT_KEYS - set(payload))
    if missing:
        issues.append(f"missing keys: {', '.join(missing)}")

    status = payload.get("status")
    if status not in STATUSES:
        issues.append(f"invalid status: {status!r}")

    platform = payload.get("platform")
    if platform is not None and platform not in PLATFORMS:
        issues.append(f"invalid platform: {platform!r}")

    kind = payload.get("content_kind")
    if kind not in CONTENT_KINDS:
        issues.append(f"invalid content_kind: {kind!r}")

    for url_key in ("source_url", "final_url"):
        value = payload.get(url_key)
        if value is None:
            issues.append(f"{url_key} must be a string")
        elif not isinstance(value, str):
            issues.append(f"{url_key} must be a string")
        elif "@" in value or "?" in value or "#" in value:
            issues.append(f"{url_key} is not sanitized")

    author = payload.get("author")
    if not isinstance(author, dict):
        issues.append("author must be an object")
    else:
        for key in ("name", "handle", "url"):
            if key not in author:
                issues.append(f"author missing {key}")

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        issues.append("metrics must be an object")
    else:
        for key in ("likes", "comments", "shares", "views"):
            if key not in metrics:
                issues.append(f"metrics missing {key}")

    for list_key in ("media", "comments", "warnings"):
        if not isinstance(payload.get(list_key), list):
            issues.append(f"{list_key} must be a list")

    action = payload.get("action_required")
    if action is not None:
        if not isinstance(action, dict):
            issues.append("action_required must be an object or null")
        else:
            if action.get("code") != NEEDS_HUMAN_CODE:
                issues.append(f"action_required.code must be {NEEDS_HUMAN_CODE!r}")
            reason = action.get("reason")
            if reason not in GATE_REASONS:
                issues.append(f"invalid action_required.reason: {reason!r}")
            for key in ("platform", "resume_instructions"):
                if key not in action:
                    issues.append(f"action_required missing {key}")

    # Banned secret/path fields must never appear.
    for banned in ("profile_dir", "profile_path", "cookies", "auth_token", "ct0", "cookie"):
        if banned in payload:
            issues.append(f"banned field present: {banned}")

    return (not issues), issues


def classify_case(
    *,
    requested_platform: str,
    url: str,
    payload: Mapping[str, Any] | None,
    invoke_error: str | None = None,
    schema_ok: bool | None = None,
    schema_issues: Sequence[str] | None = None,
) -> str:
    """Classify one smoke case. needs-human is never content-success."""
    if invoke_error:
        return "runtime-error"
    if payload is None:
        return "runtime-error"

    ok = schema_ok
    issues = list(schema_issues or ())
    if ok is None:
        ok, issues = validate_result_schema(payload)
    if not ok:
        return "schema-error"

    if not url or not is_safe_public_http_url(url):
        return "unsupported/invalid"
    detected = detect_platform(url)
    if detected is None:
        return "unsupported/invalid"
    if requested_platform and detected != requested_platform:
        return "unsupported/invalid"

    if _is_needs_human(payload):
        return "needs-human"

    if _looks_unsupported(payload, requested_platform=requested_platform):
        return "unsupported/invalid"

    status = payload.get("status")
    if status in {"ok", "partial"} and has_useful_content(payload):
        return "content-success"

    # Valid JSON but no useful content and no honest human gate.
    return "runtime-error"


def scrub_case_payload(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Compact sanitized view of scraper JSON for aggregate output."""
    if payload is None:
        return None
    action = payload.get("action_required")
    action_out: dict[str, Any] | None = None
    if isinstance(action, Mapping):
        action_out = {
            "code": action.get("code"),
            "reason": action.get("reason"),
            "platform": action.get("platform"),
            # resume_instructions can be long; keep scrubbed short form
            "resume_instructions": scrub_public_warning(
                str(action.get("resume_instructions") or "")
            )[:240]
            or None,
        }
    warnings_out: list[str] = []
    raw_warnings = payload.get("warnings")
    if isinstance(raw_warnings, list):
        for warning in raw_warnings[:5]:
            warnings_out.append(scrub_public_warning(str(warning))[:240])

    text = str(payload.get("text") or "")
    title = str(payload.get("title") or "") if payload.get("title") is not None else None
    return {
        "status": payload.get("status"),
        "platform": payload.get("platform"),
        "content_kind": payload.get("content_kind"),
        "source_url": sanitize_url(str(payload.get("source_url") or "")),
        "final_url": sanitize_url(str(payload.get("final_url") or "")),
        "title": (title[:120] + "…") if title and len(title) > 120 else title,
        "text_len": len(text.strip()),
        "has_useful_content": has_useful_content(payload),
        "warnings": warnings_out,
        "action_required": action_out,
        "fetch_method": payload.get("fetch_method"),
    }


def build_scraper_argv(
    url: str,
    *,
    timeout: int = 45,
    max_chars: int = 4000,
    max_comments: int = 20,
    browser_profile_dir: str = "",
    headed: bool = False,
    python_executable: str | None = None,
) -> list[str]:
    """Build argv to invoke the installed/current scraper CLI safely."""
    exe = shutil.which("supersocks-media-scraper")
    if exe:
        argv = [exe]
    else:
        py = python_executable or sys.executable
        argv = [py, "-m", "supersocks_media_scraper.cli"]
    argv.extend(
        [
            url,
            "--timeout",
            str(int(timeout)),
            "--max-chars",
            str(int(max_chars)),
            "--max-comments",
            str(int(max_comments)),
        ]
    )
    if browser_profile_dir:
        argv.extend(["--browser-profile-dir", browser_profile_dir])
    if headed:
        argv.append("--headed")
    return argv


def invoke_scraper_subprocess(
    url: str,
    *,
    timeout: int = 45,
    max_chars: int = 4000,
    max_comments: int = 20,
    browser_profile_dir: str = "",
    headed: bool = False,
    environ: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Run the scraper CLI and return {payload, exit_code, error, stderr_redacted}."""
    argv = build_scraper_argv(
        url,
        timeout=timeout,
        max_chars=max_chars,
        max_comments=max_comments,
        browser_profile_dir=browser_profile_dir,
        headed=headed,
        python_executable=python_executable,
    )
    env = dict(environ if environ is not None else os.environ)
    # Never force browser cookie auto-read helpers into the child.
    env.pop("TWITTER_BROWSER", None)
    env.pop("TWITTER_CHROME_PROFILE", None)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=max(5, int(timeout) + 30),
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "payload": None,
            "exit_code": None,
            "error": f"scraper subprocess timed out after {exc.timeout}s",
            "stderr_redacted": "",
            "argv_kind": "console" if shutil.which("supersocks-media-scraper") else "module",
        }
    except OSError as exc:
        return {
            "payload": None,
            "exit_code": None,
            "error": scrub_public_warning(f"scraper subprocess failed to start: {exc}"),
            "stderr_redacted": "",
            "argv_kind": "console" if shutil.which("supersocks-media-scraper") else "module",
        }

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    payload: dict[str, Any] | None = None
    error: str | None = None
    try:
        payload = json.loads(stdout.strip() or "null")
        if payload is None:
            error = "scraper returned empty/null JSON"
    except json.JSONDecodeError:
        error = "scraper stdout was not valid JSON"
        payload = None

    return {
        "payload": payload if isinstance(payload, dict) else None,
        "exit_code": int(completed.returncode),
        "error": error,
        "stderr_redacted": scrub_public_warning(redact_secrets(stderr))[:400],
        "argv_kind": "console" if argv and not argv[0].endswith("python") and "supersocks_media_scraper.cli" not in " ".join(argv) else "module",
    }


def run_platform_case(
    platform: str,
    url: str,
    *,
    timeout: int = 45,
    max_chars: int = 4000,
    max_comments: int = 20,
    browser_profile_dir: str = "",
    headed: bool = False,
    environ: Mapping[str, str] | None = None,
    invoker: ScraperInvoker | None = None,
) -> dict[str, Any]:
    """Execute and classify one platform smoke case."""
    started = time.monotonic()
    safe_url = sanitize_url(url)
    invoke_error: str | None = None
    payload: dict[str, Any] | None = None
    exit_code: int | None = None
    stderr_redacted = ""
    argv_kind = "injected"

    if not url.strip() or not is_safe_public_http_url(url) or detect_platform(url) != platform:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        classification = "unsupported/invalid"
        return {
            "platform": platform,
            "url": safe_url,
            "classification": classification,
            "schema_ok": False,
            "schema_issues": ["url is unsupported or does not match platform"],
            "scraper_status": None,
            "action_required_reason": None,
            "has_useful_content": False,
            "exit_code": None,
            "elapsed_ms": elapsed_ms,
            "invoke_error": None,
            "stderr_redacted": "",
            "argv_kind": argv_kind,
            "result": None,
        }

    try:
        if invoker is not None:
            raw = invoker(
                url,
                timeout=timeout,
                max_chars=max_chars,
                max_comments=max_comments,
                browser_profile_dir=browser_profile_dir,
                headed=headed,
                environ=environ,
            )
            if isinstance(raw, dict) and "payload" in raw:
                payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else None
                exit_code = raw.get("exit_code")  # type: ignore[assignment]
                invoke_error = raw.get("error")  # type: ignore[assignment]
                stderr_redacted = str(raw.get("stderr_redacted") or "")
                argv_kind = str(raw.get("argv_kind") or "injected")
            elif isinstance(raw, dict):
                payload = raw
                exit_code = 0 if raw.get("status") in {"ok", "partial"} else 1
            else:
                invoke_error = "invoker returned non-object"
        else:
            raw = invoke_scraper_subprocess(
                url,
                timeout=timeout,
                max_chars=max_chars,
                max_comments=max_comments,
                browser_profile_dir=browser_profile_dir,
                headed=headed,
                environ=environ,
            )
            payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else None
            exit_code = raw.get("exit_code")  # type: ignore[assignment]
            invoke_error = raw.get("error")  # type: ignore[assignment]
            stderr_redacted = str(raw.get("stderr_redacted") or "")
            argv_kind = str(raw.get("argv_kind") or "module")
    except Exception as exc:  # noqa: BLE001 — smoke harness must never crash the aggregate
        invoke_error = scrub_public_warning(f"runtime exception: {type(exc).__name__}")

    schema_ok = False
    schema_issues: list[str] = []
    if payload is not None and not invoke_error:
        schema_ok, schema_issues = validate_result_schema(payload)
    elif invoke_error and payload is None:
        schema_issues = [invoke_error]

    classification = classify_case(
        requested_platform=platform,
        url=url,
        payload=payload,
        invoke_error=invoke_error,
        schema_ok=schema_ok if payload is not None else False,
        schema_issues=schema_issues,
    )

    action_reason = None
    if isinstance(payload, dict) and isinstance(payload.get("action_required"), dict):
        action_reason = payload["action_required"].get("reason")

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "platform": platform,
        "url": safe_url,
        "classification": classification,
        "schema_ok": bool(schema_ok),
        "schema_issues": [scrub_public_warning(i) for i in schema_issues[:8]],
        "scraper_status": payload.get("status") if isinstance(payload, dict) else None,
        "action_required_reason": action_reason,
        "has_useful_content": has_useful_content(payload),
        "exit_code": exit_code,
        "elapsed_ms": elapsed_ms,
        "invoke_error": scrub_public_warning(invoke_error) if invoke_error else None,
        "stderr_redacted": scrub_public_warning(stderr_redacted)[:400] if stderr_redacted else "",
        "argv_kind": argv_kind,
        "result": scrub_case_payload(payload),
    }


def default_mode_case_passes(classification: str) -> bool:
    """Default verify mode: valid route outcome including honest needs-human."""
    return classification in {"content-success", "needs-human"}


def require_success_case_passes(classification: str) -> bool:
    """Strict mode: only non-empty useful extraction counts as success."""
    return classification == "content-success"


def aggregate_summary(
    cases: Sequence[Mapping[str, Any]],
    *,
    require_success: bool = False,
    platforms: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    profiles_root_configured_override: bool | None = None,
) -> dict[str, Any]:
    """Build sanitized machine-readable aggregate summary."""
    requested = list(platforms or [c.get("platform") for c in cases])
    counts: dict[str, int] = {key: 0 for key in sorted(CLASSIFICATIONS)}
    for case in cases:
        label = str(case.get("classification") or "runtime-error")
        if label not in counts:
            counts[label] = 0
        counts[label] += 1

    checker = require_success_case_passes if require_success else default_mode_case_passes
    case_pass = [bool(checker(str(c.get("classification")))) for c in cases]
    passed = bool(cases) and all(case_pass)

    auth = auth_presence(environ)
    if profiles_root_configured_override is not None:
        auth["media_browser_profiles_root_configured"] = bool(profiles_root_configured_override)

    return {
        "tool": "supersocks-media-scraper-live-smoke",
        "version": __version__,
        "mode": "require-success" if require_success else "verify",
        "platforms_requested": requested,
        "pass": passed,
        "counts": counts,
        "auth_hints": auth,
        "cases": [dict(c) for c in cases],
        "notes": [
            "needs-human is never treated as content-success / successful extraction",
            "auth_hints report presence only; values and profile paths are omitted",
            "default verify mode accepts content-success or honest needs-human per platform",
            "require-success fails unless every requested platform has non-empty useful content",
        ],
    }


def resolve_urls(
    *,
    platforms: Sequence[str],
    url_overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    overrides = {k: v.strip() for k, v in dict(url_overrides or {}).items() if v and str(v).strip()}
    out: dict[str, str] = {}
    for platform in platforms:
        out[platform] = overrides.get(platform) or DEFAULT_PUBLIC_URLS[platform]
    return out


def run_smoke(
    *,
    platforms: Sequence[str] | None = None,
    url_overrides: Mapping[str, str] | None = None,
    require_success: bool = False,
    timeout: int = 45,
    max_chars: int = 4000,
    max_comments: int = 20,
    browser_profile_dir: str = "",
    profiles_root: str = "",
    headed: bool = False,
    environ: MutableMapping[str, str] | Mapping[str, str] | None = None,
    invoker: ScraperInvoker | None = None,
) -> dict[str, Any]:
    """Run smoke cases and return the aggregate summary."""
    selected = tuple(platforms or SUPPORTED_PLATFORMS)
    for platform in selected:
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported smoke platform: {platform}")

    env: dict[str, str] = dict(environ if environ is not None else os.environ)
    profiles_override: bool | None = None
    if profiles_root.strip():
        # Pass root to child via env; never echo the path in the summary.
        env["MEDIA_BROWSER_PROFILES_ROOT"] = profiles_root.strip()
        profiles_override = True

    urls = resolve_urls(platforms=selected, url_overrides=url_overrides)
    cases: list[dict[str, Any]] = []
    for platform in selected:
        cases.append(
            run_platform_case(
                platform,
                urls[platform],
                timeout=timeout,
                max_chars=max_chars,
                max_comments=max_comments,
                browser_profile_dir=browser_profile_dir,
                headed=headed,
                environ=env,
                invoker=invoker,
            )
        )
    return aggregate_summary(
        cases,
        require_success=require_success,
        platforms=selected,
        environ=env,
        profiles_root_configured_override=profiles_override,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supersocks-media-scraper-smoke",
        description=(
            "Honest live smoke harness for x, reddit, instagram, and facebook. "
            "Default verify mode accepts valid JSON including needs-human gates; "
            "--require-success demands non-empty useful content per platform."
        ),
    )
    parser.add_argument(
        "--platforms",
        default=",".join(SUPPORTED_PLATFORMS),
        help=f"Comma-separated platforms (default: {','.join(SUPPORTED_PLATFORMS)})",
    )
    parser.add_argument("--url-x", default="", help="Override public X/Twitter smoke URL")
    parser.add_argument("--url-reddit", default="", help="Override public Reddit smoke URL")
    parser.add_argument("--url-instagram", default="", help="Override public Instagram smoke URL")
    parser.add_argument("--url-facebook", default="", help="Override public Facebook smoke URL")
    parser.add_argument(
        "--require-success",
        action="store_true",
        help="Fail unless every requested platform returns non-empty useful content",
    )
    parser.add_argument("--timeout", type=int, default=45, help="Per-platform scraper timeout seconds")
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument("--max-comments", type=int, default=20)
    parser.add_argument(
        "--profiles-root",
        default="",
        help="Sets MEDIA_BROWSER_PROFILES_ROOT for child scrapes (path never printed)",
    )
    parser.add_argument(
        "--browser-profile-dir",
        default="",
        help="Optional explicit Cloak profile directory passed to the scraper",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Force headed CloakBrowser for browser platforms",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    platforms = tuple(p.strip().lower() for p in str(args.platforms).split(",") if p.strip())
    unknown = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
    if unknown:
        parser.error(f"unsupported platforms: {', '.join(unknown)}")
    if not platforms:
        parser.error("at least one platform is required")

    overrides = {
        "x": args.url_x,
        "reddit": args.url_reddit,
        "instagram": args.url_instagram,
        "facebook": args.url_facebook,
    }
    summary = run_smoke(
        platforms=platforms,
        url_overrides=overrides,
        require_success=bool(args.require_success),
        timeout=int(args.timeout),
        max_chars=int(args.max_chars),
        max_comments=int(args.max_comments),
        browser_profile_dir=str(args.browser_profile_dir or ""),
        profiles_root=str(args.profiles_root or ""),
        headed=bool(args.headed),
    )
    # Final defense: redact any accidental secret-looking substrings before print.
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(redact_secrets(text))
    return 0 if summary.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
