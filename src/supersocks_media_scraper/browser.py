"""Optional CloakBrowser rendering for Reddit / Instagram / Facebook.

Dependency-light by default. Only imported when the ``browser`` extra is
installed. Headed mode never installs or starts Xvfb; Linux requires an
existing DISPLAY/WAYLAND_DISPLAY. Adapted from supersocks-url-scraper (MIT).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import re
import sys
import threading
from dataclasses import dataclass
from typing import Any


class BrowserFetchError(RuntimeError):
    """Raised when optional browser rendering cannot retrieve usable HTML."""


_SEMAPHORE_LOCK = threading.Lock()
_SEMAPHORES: dict[int, threading.BoundedSemaphore] = {}


def _browser_semaphore(max_concurrency: int) -> threading.BoundedSemaphore:
    limit = max(1, int(max_concurrency or 1))
    with _SEMAPHORE_LOCK:
        semaphore = _SEMAPHORES.get(limit)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(limit)
            _SEMAPHORES[limit] = semaphore
        return semaphore


def _truthy_env(name: str, *, environ: dict[str, str] | None = None) -> bool | None:
    env = environ if environ is not None else os.environ
    raw = env.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip().lower() not in {"0", "false", "no", "off", "none"}


def resolve_headless(
    headless: bool | None = None,
    *,
    environ: dict[str, str] | None = None,
) -> bool:
    """Resolve headless vs headed Cloak launch.

    Precedence: explicit argument → ``CLOAK_HEADLESS`` / ``BROWSER_HEADLESS`` →
    default headless True.
    """
    if headless is not None:
        return bool(headless)
    env = environ if environ is not None else os.environ
    for key in ("CLOAK_HEADLESS", "BROWSER_HEADLESS"):
        parsed = _truthy_env(key, environ=dict(env))
        if parsed is not None:
            raw = str(env.get(key) or "").strip().lower()
            if raw in {"headed", "headful"}:
                return False
            return parsed
    return True


def cloakbrowser_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("cloakbrowser") is not None
    except Exception:
        return False


def _native_gui_platform() -> bool:
    return sys.platform in {"darwin", "win32", "cygwin"}


def _ensure_display_for_headed(headless: bool) -> None:
    if headless:
        return
    if _native_gui_platform():
        return
    if os.environ.get("DISPLAY", "").strip() or os.environ.get("WAYLAND_DISPLAY", "").strip():
        return
    raise BrowserFetchError(
        "headed CloakBrowser on Linux requires DISPLAY or WAYLAND_DISPLAY; "
        "attach an existing X11/Wayland/Xvfb session yourself "
        "(this package never installs or starts Xvfb)"
    )


@dataclass(frozen=True)
class BrowserRenderedPage:
    final_url: str
    status_code: int
    html: str
    title: str | None = None
    method: str = "cloak"
    consent_action: str | None = None


_CONSENT_REJECTION_LABELS = (
    "Continuer sans accepter",
    "Tout refuser",
    "Refuser et continuer",
    "Je refuse",
    "Refuser",
    "Continue without accepting",
    "Reject all",
    "Decline all",
    "Reject",
)


def _looks_like_consent_wall(text: str) -> bool:
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return False
    strong_markers = (
        "contenu de la fenêtre de consentement",
        "contenu de la fenetre de consentement",
        "continuer sans accepter",
        "continue without accepting",
        "centre de préférences de la confidentialité",
        "privacy preference center",
    )
    if any(marker in normalized for marker in strong_markers):
        return True
    marker_groups = (
        ("nous utilisons des cookies", "personnaliser", "accepter"),
        ("utilisation de cookies", "personnaliser", "refuser"),
        ("we use cookies", "customize", "accept"),
        ("we use cookies", "manage preferences", "reject"),
    )
    return any(all(marker in normalized for marker in group) for group in marker_groups)


async def _dismiss_consent_wall(page: Any) -> str | None:
    try:
        visible_text = await page.locator("body").inner_text(timeout=5000)
    except Exception:
        visible_text = ""
    if not _looks_like_consent_wall(visible_text):
        return None

    for label in _CONSENT_REJECTION_LABELS:
        try:
            button = page.get_by_role(
                "button",
                name=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I),
            )
            count = await button.count()
        except Exception:
            continue
        for index in range(min(count, 5)):
            candidate = button.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                await candidate.click(timeout=5000)
                await page.wait_for_timeout(1500)
                return label
            except Exception:
                continue
    return None


async def fetch_with_cloak_async(
    url: str,
    *,
    timeout_seconds: float = 60.0,
    post_load_wait_ms: int = 8000,
    profile_dir: str = "",
    headless: bool | None = None,
) -> BrowserRenderedPage:
    os.environ.setdefault("CLOAKBROWSER_SUPPRESS_FONT_WARNING", "1")
    resolved_headless = resolve_headless(headless)
    _ensure_display_for_headed(resolved_headless)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from cloakbrowser import ensure_binary, launch_context_async, launch_persistent_context_async
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise BrowserFetchError(
            "Install the browser extra: pip install 'supersocks-media-scraper[browser]'"
        ) from exc

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        await asyncio.to_thread(ensure_binary)
    launch_kwargs: dict[str, Any] = {
        "headless": resolved_headless,
        "locale": "fr-FR",
        "timezone": "Europe/Paris",
        "humanize": True,
        "stealth_args": True,
        "viewport": {"width": 1366, "height": 768},
    }
    if profile_dir.strip():
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            context: Any = await launch_persistent_context_async(profile_dir.strip(), **launch_kwargs)
        method = "cloak-profile"
    else:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            context = await launch_context_async(**launch_kwargs)
        method = "cloak"
    try:
        page = await context.new_page()
        response = await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
        if post_load_wait_ms > 0:
            await page.wait_for_timeout(post_load_wait_ms)
        consent_action = await _dismiss_consent_wall(page)
        html = await page.content()
        if not html.strip():
            raise BrowserFetchError("cloak rendered an empty page")
        return BrowserRenderedPage(
            final_url=page.url,
            status_code=response.status if response is not None else 0,
            html=html,
            title=(await page.title()) or None,
            method=method,
            consent_action=consent_action,
        )
    finally:
        await context.close()


def fetch_with_cloak(
    url: str,
    *,
    timeout_seconds: float = 60.0,
    post_load_wait_ms: int = 8000,
    profile_dir: str = "",
    max_concurrency: int = 1,
    headless: bool | None = None,
) -> BrowserRenderedPage:
    semaphore = _browser_semaphore(max_concurrency)
    acquired = semaphore.acquire(timeout=max(1.0, float(timeout_seconds)))
    if not acquired:
        raise BrowserFetchError(f"browser concurrency limit reached ({max_concurrency})")
    try:
        try:
            return asyncio.run(
                fetch_with_cloak_async(
                    url,
                    timeout_seconds=timeout_seconds,
                    post_load_wait_ms=post_load_wait_ms,
                    profile_dir=profile_dir,
                    headless=headless,
                )
            )
        except BrowserFetchError:
            raise
        except RuntimeError as exc:
            raise BrowserFetchError(str(exc)) from exc
    finally:
        semaphore.release()
