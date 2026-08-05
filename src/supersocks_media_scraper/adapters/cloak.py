"""Cloak-first adapter shared by Reddit, Instagram, and Facebook."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping

from ..browser import cloakbrowser_available
from ..profiles import resolve_profile_dir
from ..sanitize import sanitize_browser_error
from ..schema import build_action_required, error_result
from ._util import detect_platform, is_safe_public_http_url
from .cloak_html import CLOAK_PLATFORMS, parse_cloak_html

CloakPageFetcher = Callable[..., Any]


def _truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in {"", "0", "false", "no", "off", "none"}


def resolve_cloak_headless(
    headless: bool | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool | None:
    if headless is not None:
        return bool(headless)
    env = environ if environ is not None else os.environ
    for key in ("MEDIA_CLOAK_HEADLESS", "CLOAK_HEADLESS", "BROWSER_HEADLESS"):
        raw = str(env.get(key) or "").strip().lower()
        if not raw:
            continue
        if raw in {"headed", "headful"}:
            return False
        return raw not in {"0", "false", "no", "off", "none"}
    return None


def extract_cloak(
    url: str,
    *,
    platform: str | None = None,
    max_chars: int = 4000,
    max_comments: int = 20,
    timeout: int = 45,
    browser_profile_dir: str = "",
    browser_post_load_wait_ms: int = 8000,
    browser_max_concurrency: int = 1,
    headless: bool | None = None,
    cloak_fetcher: CloakPageFetcher | None = None,
    environ: Mapping[str, str] | None = None,
    require_existing_profile: bool = True,
) -> dict[str, Any] | None:
    detected = detect_platform(url)
    platform_id = platform or detected
    if platform_id not in CLOAK_PLATFORMS:
        return None
    if detected != platform_id or not is_safe_public_http_url(url):
        return None

    if cloak_fetcher is None and not cloakbrowser_available():
        return error_result(
            platform=platform_id,
            source_url=url,
            warnings=[
                "cloakbrowser not installed; install the browser extra: "
                "pip install 'supersocks-media-scraper[browser]'"
            ],
            fetch_method="cloak",
        )

    profile_dir = resolve_profile_dir(
        browser_profile_dir,
        platform=platform_id,
        environ=environ,
    )
    if profile_dir and require_existing_profile and not Path(profile_dir).expanduser().exists():
        return error_result(
            platform=platform_id,
            source_url=url,
            warnings=[
                "configured media Cloak profile is absent; "
                "initialize once with supersocks-media-scraper --warmup "
                f"{platform_id} --create-profile under an existing display (Linux) "
                "or native GUI (macOS/Windows), then retry. Cookies stay inside "
                "the operator-provided profile only."
            ],
            action_required=build_action_required(platform=platform_id, reason="login"),
            fetch_method="cloak-profile",
        )

    resolved_headless = resolve_cloak_headless(headless, environ=environ)
    fetch = cloak_fetcher
    if fetch is None:
        from ..browser import fetch_with_cloak

        fetch = fetch_with_cloak

    try:
        page = fetch(
            url,
            timeout_seconds=float(timeout),
            post_load_wait_ms=int(browser_post_load_wait_ms),
            profile_dir=profile_dir,
            max_concurrency=max(1, int(browser_max_concurrency or 1)),
            headless=resolved_headless,
        )
    except Exception as exc:  # noqa: BLE001
        return error_result(
            platform=platform_id,
            source_url=url,
            warnings=[sanitize_browser_error(exc, context="render")],
            fetch_method="cloak-profile" if profile_dir else "cloak",
        )

    method = getattr(page, "method", None) or ("cloak-profile" if profile_dir else "cloak")
    html_text = getattr(page, "html", "") or ""
    page_title = getattr(page, "title", None)
    final_url = getattr(page, "final_url", url) or url
    http_status = getattr(page, "status_code", None)
    extra: list[str] = []
    consent = getattr(page, "consent_action", None)
    if consent:
        extra.append(f"browser consent dismissed via: {consent}")
    return parse_cloak_html(
        html_text,
        platform=platform_id,
        source_url=url,
        final_url=final_url,
        page_title=page_title,
        max_chars=max_chars,
        fetch_method=str(method),
        extra_warnings=extra,
        http_status=int(http_status) if http_status is not None else None,
        max_comments=max_comments,
    )
