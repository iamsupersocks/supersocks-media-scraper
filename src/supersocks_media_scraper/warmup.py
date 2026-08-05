"""Headed media profile warm-up via CloakBrowser.

Opens an operator-owned persistent profile for Reddit/Instagram/Facebook so a
human can complete login/consent/challenge manually. Never automates
login/MFA/CAPTCHA and never echoes cookies, tokens, or absolute profile paths.

Adapted from supersocks-url-scraper social/warmup.py (MIT).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Mapping

from .adapters.cloak_html import CLOAK_PLATFORMS, detect_gate
from .browser import cloakbrowser_available
from .profiles import (
    default_warmup_url,
    ensure_profile_dir,
    profile_status,
    resolve_profile_dir,
)
from .sanitize import sanitize_browser_error, sanitize_url, scrub_public_warning
from .schema import build_action_required


WarmupFetcher = Callable[..., Any]


def _native_gui_platform() -> bool:
    return sys.platform in {"darwin", "win32", "cygwin"}


def _public_warnings(warnings: list[str]) -> list[str]:
    return [scrub_public_warning(str(w)) for w in warnings]


def run_warmup(
    platform: str,
    *,
    url: str = "",
    wait_seconds: float = 120.0,
    create_profile: bool = False,
    browser_profile_dir: str = "",
    environ: Mapping[str, str] | None = None,
    cloak_fetcher: WarmupFetcher | None = None,
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    """Run headed Cloak warm-up for one Cloak-first media platform."""
    platform_id = str(platform or "").strip().lower()
    warnings: list[str] = []
    if platform_id not in CLOAK_PLATFORMS:
        return {
            "status": "error",
            "platform": platform_id or None,
            "headed": True,
            "wait_seconds": float(wait_seconds),
            "profile": profile_status(""),
            "profile_created": False,
            "warnings": _public_warnings(
                [f"unsupported warm-up platform: {platform_id or '(empty)'}"]
            ),
            "action_required": None,
        }

    navigation_url = (url or "").strip() or default_warmup_url(platform_id)
    public_url = sanitize_url(navigation_url)
    profile_dir = resolve_profile_dir(
        browser_profile_dir,
        platform=platform_id,
        environ=environ,
    )
    if not profile_dir:
        return {
            "status": "error",
            "platform": platform_id,
            "url": public_url,
            "headed": True,
            "wait_seconds": float(wait_seconds),
            "profile": profile_status(""),
            "profile_created": False,
            "warnings": _public_warnings(
                [
                    "no media profile configured; set MEDIA_BROWSER_PROFILES_ROOT "
                    f"(uses {{root}}/{platform_id}), MEDIA_BROWSER_PROFILE_DIR, "
                    "BROWSER_PROFILE_DIR, or pass --browser-profile-dir"
                ]
            ),
            "action_required": build_action_required(platform=platform_id, reason="login"),
            "instructions": (
                "Configure an operator-owned profile directory, re-run with --create-profile, "
                "then complete any login/consent manually. Never automate MFA/CAPTCHA."
            ),
        }

    created = False
    if create_profile:
        profile_dir, created = ensure_profile_dir(profile_dir, create=True)
    elif not os.path.isdir(profile_dir):
        return {
            "status": "error",
            "platform": platform_id,
            "url": public_url,
            "headed": True,
            "wait_seconds": float(wait_seconds),
            "profile": profile_status(profile_dir),
            "profile_created": False,
            "warnings": _public_warnings(
                [
                    "media Cloak profile directory is absent; re-run with --create-profile "
                    "to create it explicitly, then complete login/consent manually"
                ]
            ),
            "action_required": build_action_required(platform=platform_id, reason="login"),
            "instructions": (
                "Create the platform profile explicitly, open headed warm-up, "
                "complete gates manually, then retry reads headless."
            ),
        }

    if cloak_fetcher is None and not cloakbrowser_available():
        return {
            "status": "error",
            "platform": platform_id,
            "url": public_url,
            "headed": True,
            "wait_seconds": float(wait_seconds),
            "profile": profile_status(profile_dir),
            "profile_created": created,
            "warnings": _public_warnings(
                [
                    "cloakbrowser not installed; install the browser extra: "
                    "pip install 'supersocks-media-scraper[browser]'"
                ]
            ),
            "action_required": None,
        }

    fetch = cloak_fetcher
    if fetch is None:
        from .browser import fetch_with_cloak

        fetch = fetch_with_cloak

    post_load_wait_ms = max(0, int(float(wait_seconds) * 1000))
    try:
        page = fetch(
            navigation_url,
            timeout_seconds=float(timeout_seconds),
            post_load_wait_ms=post_load_wait_ms,
            profile_dir=profile_dir,
            max_concurrency=1,
            headless=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "platform": platform_id,
            "url": public_url,
            "headed": True,
            "wait_seconds": float(wait_seconds),
            "native_gui": _native_gui_platform(),
            "linux_display_required": not _native_gui_platform(),
            "profile": profile_status(profile_dir),
            "profile_created": created,
            "warnings": _public_warnings([sanitize_browser_error(exc, context="warmup")]),
            "action_required": build_action_required(platform=platform_id, reason="challenge"),
            "instructions": (
                "On Linux, attach an existing DISPLAY/Xvfb before headed warm-up. "
                "On macOS/Windows, use the native GUI. Never automate login/MFA/CAPTCHA."
            ),
        }

    html_text = getattr(page, "html", "") or ""
    page_title = getattr(page, "title", None)
    final_navigation_url = getattr(page, "final_url", navigation_url) or navigation_url
    public_final_url = sanitize_url(final_navigation_url)
    gate = detect_gate(html_text, platform=platform_id, page_title=page_title)
    action = build_action_required(platform=platform_id, reason=gate) if gate else None
    if gate:
        warnings.append(
            f"{platform_id} still shows a {gate} gate after warm-up wait; "
            "complete it manually in the browser if still open, then retry"
        )
        status = "partial"
    else:
        status = "ok"
        warnings.append(
            "warm-up session finished; reuse the platform profile headless for subsequent reads"
        )

    return {
        "status": status,
        "platform": platform_id,
        "url": public_url,
        "final_url": public_final_url,
        "page_title": page_title,
        "headed": True,
        "wait_seconds": float(wait_seconds),
        "native_gui": _native_gui_platform(),
        "linux_display_required": not _native_gui_platform(),
        "fetch_method": getattr(page, "method", None) or "cloak-profile",
        "profile": profile_status(profile_dir),
        "profile_created": created,
        "gate_detected": gate,
        "action_required": action,
        "warnings": _public_warnings(warnings),
        "instructions": (
            "Complete any login, MFA, CAPTCHA, consent, or challenge manually in the "
            "headed browser. This tool never automates those steps and never prints "
            "cookies, tokens, or profile paths."
        ),
    }
