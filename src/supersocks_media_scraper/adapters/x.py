"""X/Twitter reads via upstream twitter-cli when explicitly authenticated.

Policy:
- Resolve twitter-cli via the `twitter` executable on PATH, or via
  ``python -m twitter_cli.cli`` when the module is importable (pipx without
  ``--include-deps``).
- Require explicit TWITTER_AUTH_TOKEN + TWITTER_CT0 in the process environment.
- Never auto-read browser cookies, never print/store tokens, never invent credentials.

Adapted from supersocks-url-scraper social/twitter_x.py (MIT).
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from typing import Any, Callable
from urllib.parse import urlparse

from ..schema import build_action_required, error_result, make_result
from ..sanitize import redact_secrets, trim_text
from ._util import (
    actionable_missing_tool,
    child_env_without_browser_cookie_hints,
    detect_platform,
    is_safe_public_http_url,
    parse_json_payload,
    run_command,
    which,
)

TWITTER_CLI_INSTALL = (
    "install from GitHub/PyPI via `pipx install twitter-cli` or "
    "`uv tool install twitter-cli` (never auto-installed by this package)"
)

CommandRunner = Callable[..., Any]

_STATUS_RE = re.compile(r"/(?:i/)?status/(\d+)", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"/(?:i/)?article/(\d+)", re.IGNORECASE)
_RESERVED_USER_PATHS = frozenset(
    {
        "home",
        "explore",
        "search",
        "notifications",
        "messages",
        "settings",
        "i",
        "intent",
        "share",
        "hashtag",
        "compose",
        "login",
        "signup",
        "tos",
        "privacy",
    }
)


def _twitter_cli_module_spec():
    """Return import spec for twitter_cli.cli without importing or executing it."""
    try:
        return importlib.util.find_spec("twitter_cli.cli")
    except (ModuleNotFoundError, ValueError, ImportError):
        return None


def twitter_cli_module_available() -> bool:
    return _twitter_cli_module_spec() is not None


def twitter_cli_available() -> bool:
    return which("twitter") is not None or twitter_cli_module_available()


def build_twitter_cli_argv(subcommand_args: list[str]) -> list[str] | None:
    """Build argv for twitter-cli after the credentials gate."""
    if which("twitter") is not None:
        return ["twitter", *subcommand_args]
    if twitter_cli_module_available():
        return [sys.executable, "-m", "twitter_cli.cli", *subcommand_args]
    return None


X_LOGIN_RESUME_INSTRUCTIONS = (
    "X/Twitter requires explicit credentials. Export TWITTER_AUTH_TOKEN and TWITTER_CT0 "
    "from a manual Cookie-Editor export in your shell, then retry the scrape. "
    "This package never auto-reads browser cookies. X uses shell exports only, "
    "not a headed browser profile."
)


def twitter_login_action_required() -> dict[str, str] | None:
    return build_action_required(
        platform="x",
        reason="login",
        resume_instructions=X_LOGIN_RESUME_INSTRUCTIONS,
    )


def explicit_twitter_credentials_present(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    auth = str(env.get("TWITTER_AUTH_TOKEN") or "").strip()
    ct0 = str(env.get("TWITTER_CT0") or "").strip()
    return bool(auth and ct0)


def twitter_missing_backend_warning() -> str:
    return actionable_missing_tool("twitter-cli (`twitter`)", TWITTER_CLI_INSTALL)


def twitter_missing_credentials_warning() -> str:
    return (
        "twitter-cli is installed but TWITTER_AUTH_TOKEN and TWITTER_CT0 are not both set; "
        "export them from a manual Cookie-Editor export. This package never auto-reads browser cookies."
    )


def classify_x_url(url: str) -> tuple[str, str | None]:
    """Return (kind, identifier) for status|article|user|unknown."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    article = _ARTICLE_RE.search(path)
    if article:
        return "article", article.group(1)
    status = _STATUS_RE.search(path)
    if status:
        return "status", status.group(1)
    parts = [p for p in path.split("/") if p]
    if parts and parts[0].lower() not in _RESERVED_USER_PATHS and not parts[0].isdigit():
        handle = parts[0].lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            return "user", handle
    return "unknown", None


def _author_fields(data: dict[str, Any]) -> dict[str, str | None]:
    author = data.get("author")
    name = None
    handle = None
    url = None
    if isinstance(author, dict):
        for key in ("name",):
            value = str(author.get(key) or "").strip()
            if value:
                name = value
        for key in ("screen_name", "screenName", "username", "handle"):
            value = str(author.get(key) or "").strip().lstrip("@")
            if value:
                handle = value
                break
        for key in ("url", "profile_url", "profileUrl"):
            value = str(author.get(key) or "").strip()
            if value:
                url = value
                break
    if not handle:
        for key in ("screen_name", "screenName", "username", "handle"):
            value = str(data.get(key) or "").strip().lstrip("@")
            if value:
                handle = value
                break
    if not name:
        for key in ("name",):
            value = str(data.get(key) or "").strip()
            if value:
                name = value
    if handle and not url:
        url = f"https://x.com/{handle}"
    return {"name": name or handle, "handle": handle, "url": url}


def _tweet_text(data: dict[str, Any]) -> str:
    for key in ("articleText", "article_text", "full_text", "fullText", "text", "bio", "description"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _tweet_title(data: dict[str, Any], *, fallback_author: str | None = None) -> str | None:
    for key in ("articleTitle", "article_title", "title", "name"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    text = _tweet_text(data)
    if text:
        return trim_text(text, 80)
    if fallback_author:
        return f"@{fallback_author}" if not fallback_author.startswith("@") else fallback_author
    return None


def _unwrap_data(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("ok") is False:
        return None
    data = payload.get("data", payload)
    if isinstance(data, list):
        if not data:
            return None
        first = data[0]
        return first if isinstance(first, dict) else None
    return data if isinstance(data, dict) else None


def _error_message(payload: Any, stderr: str) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "").strip()
            message = str(err.get("message") or "").strip()
            joined = ": ".join(p for p in (code, message) if p)
            if joined:
                return redact_secrets(joined)
        if payload.get("ok") is False:
            return redact_secrets(str(payload.get("message") or "twitter-cli returned ok=false"))
    if stderr.strip():
        return redact_secrets(stderr.strip().splitlines()[0][:300])
    return "twitter-cli returned no usable data"


def _detect_rate_limit(message: str) -> bool:
    blob = (message or "").lower()
    return "429" in blob or "too many requests" in blob or "rate limit" in blob or "rate-limit" in blob


def _extract_media(data: dict[str, Any]) -> list[dict[str, Any]]:
    media_out: list[dict[str, Any]] = []
    candidates: list[Any] = []
    for key in ("media", "entities", "extended_entities"):
        value = data.get(key)
        if isinstance(value, dict) and "media" in value:
            candidates.extend(value.get("media") or [])
        elif isinstance(value, list):
            candidates.extend(value)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = str(item.get("media_url_https") or item.get("media_url") or item.get("url") or "").strip()
        if not url:
            continue
        mtype = str(item.get("type") or item.get("kind") or "photo").lower()
        kind = "video" if "video" in mtype else "image"
        alt = str(item.get("ext_alt_text") or item.get("alt") or "").strip() or None
        media_out.append({"kind": kind, "url": url, "alt": alt})
    return media_out


def _extract_metrics(data: dict[str, Any]) -> dict[str, int | None]:
    def _int(key_variants: tuple[str, ...]) -> int | None:
        for key in key_variants:
            value = data.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    return {
        "likes": _int(("favorite_count", "favoriteCount", "likes", "like_count", "likeCount")),
        "comments": _int(("reply_count", "replyCount", "comments", "comment_count")),
        "shares": _int(("retweet_count", "retweetCount", "shares", "quote_count", "quoteCount")),
        "views": _int(("view_count", "viewCount", "views", "impression_count")),
    }


def scrape_x(
    url: str,
    *,
    max_chars: int = 4000,
    timeout: int = 30,
    runner: CommandRunner | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Extract an X/Twitter URL via twitter-cli into the media JSON contract."""
    if detect_platform(url) != "x" or not is_safe_public_http_url(url):
        return None

    if not twitter_cli_available() and runner is None:
        return error_result(
            platform="x",
            source_url=url,
            warnings=[twitter_missing_backend_warning()],
            fetch_method="twitter-cli",
        )

    env = child_env_without_browser_cookie_hints(environ)
    if not explicit_twitter_credentials_present(env):
        return error_result(
            platform="x",
            source_url=url,
            warnings=[twitter_missing_credentials_warning()],
            action_required=twitter_login_action_required(),
            fetch_method="twitter-cli",
        )

    kind, ident = classify_x_url(url)
    if kind == "article":
        subcommand_args = ["article", ident or url, "--json"]
        content_kind = "post"
    elif kind == "status":
        subcommand_args = ["tweet", ident or url, "--json"]
        content_kind = "post"
    elif kind == "user" and ident:
        subcommand_args = ["user", ident, "--json"]
        content_kind = "profile"
    else:
        return make_result(
            status="partial",
            platform="x",
            content_kind="unknown",
            source_url=url,
            final_url=url,
            warnings=[
                "unsupported X/Twitter URL shape for twitter-cli; expected status, article, or profile URL"
            ],
            fetch_method="twitter-cli",
        )

    argv = build_twitter_cli_argv(subcommand_args)
    if argv is None:
        if runner is None:
            return error_result(
                platform="x",
                source_url=url,
                warnings=[twitter_missing_backend_warning()],
                fetch_method="twitter-cli",
            )
        argv = ["twitter", *subcommand_args]

    try:
        result = run_command(argv, timeout=timeout, env=env, runner=runner)
    except Exception as exc:  # noqa: BLE001
        return error_result(
            platform="x",
            source_url=url,
            warnings=[f"twitter-cli execution failed: {redact_secrets(str(exc))}"],
            fetch_method="twitter-cli",
        )

    parsed: Any = None
    try:
        parsed = parse_json_payload(result.stdout)
    except Exception:
        parsed = None

    data = _unwrap_data(parsed)
    if result.returncode != 0 or data is None:
        message = _error_message(parsed, result.stderr)
        action = None
        if _detect_rate_limit(message):
            action = build_action_required(platform="x", reason="rate-limit")
        return error_result(
            platform="x",
            source_url=url,
            warnings=[message],
            action_required=action,
            fetch_method="twitter-cli",
            content_kind=content_kind,
        )

    author = _author_fields(data)
    body = _tweet_text(data)
    title = _tweet_title(data, fallback_author=author.get("handle") or author.get("name"))
    text = trim_text(body or title or "", max(50, min(int(max_chars or 4000), 20_000)))
    published = str(data.get("created_at") or data.get("createdAt") or "").strip() or None
    media = _extract_media(data)
    metrics = _extract_metrics(data)

    return make_result(
        status="ok" if text else "partial",
        platform="x",
        content_kind=content_kind,
        source_url=url,
        final_url=url,
        title=title,
        text=text,
        author=author,
        published_at=published,
        metrics=metrics,
        media=media,
        warnings=[] if text else ["twitter-cli returned metadata without readable text"],
        fetch_method="twitter-cli",
    )
