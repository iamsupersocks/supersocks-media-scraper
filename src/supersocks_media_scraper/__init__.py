"""supersocks-media-scraper — private-by-default social media post scraper.

Public surface:
- :func:`scrape` — library API returning the stable JSON contract
- CLI entry point ``supersocks-media-scraper``

Platforms in scope: X, Instagram, Facebook, Reddit.
LinkedIn public pages and YouTube stay in supersocks-url-scraper.

Portions adapted from supersocks-url-scraper (MIT).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .adapters import (
    detect_platform,
    scrape_facebook,
    scrape_instagram,
    scrape_reddit,
    scrape_x,
)
from .schema import error_result
from .sanitize import sanitize_url

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "detect_platform",
    "scrape",
    "scrape_facebook",
    "scrape_instagram",
    "scrape_reddit",
    "scrape_x",
]

CloakPageFetcher = Callable[..., Any]
CommandRunner = Callable[..., Any]


def scrape(
    url: str,
    *,
    max_chars: int = 4000,
    max_comments: int = 20,
    timeout: int = 45,
    browser_profile_dir: str = "",
    browser_post_load_wait_ms: int = 8000,
    browser_max_concurrency: int = 1,
    headless: bool | None = None,
    cloak_fetcher: CloakPageFetcher | None = None,
    twitter_runner: CommandRunner | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Scrape a supported social media URL into the stable JSON contract.

    Returns visible/public fields only. Never claims exhaustiveness. Never
    automates login/MFA/CAPTCHA. Output URLs are sanitized (no userinfo/query/
    fragment). Cookies, tokens, and profile paths are never included.
    """
    raw = (url or "").strip()
    if not raw:
        return error_result(
            platform=None,
            source_url="",
            warnings=["empty URL"],
        )

    platform = detect_platform(raw)
    if platform is None:
        return error_result(
            platform=None,
            source_url=sanitize_url(raw),
            warnings=[
                "unsupported or unsafe URL; supported platforms are x.com/twitter.com, "
                "instagram.com, facebook.com/fb.com, reddit.com. "
                "LinkedIn and YouTube remain in supersocks-url-scraper."
            ],
        )

    common_cloak = {
        "max_chars": max_chars,
        "max_comments": max_comments,
        "timeout": timeout,
        "browser_profile_dir": browser_profile_dir,
        "browser_post_load_wait_ms": browser_post_load_wait_ms,
        "browser_max_concurrency": browser_max_concurrency,
        "headless": headless,
        "cloak_fetcher": cloak_fetcher,
        "environ": environ,
    }

    result: dict[str, Any] | None
    if platform == "x":
        result = scrape_x(
            raw,
            max_chars=max_chars,
            timeout=timeout,
            runner=twitter_runner,
            environ=dict(environ) if environ is not None else None,
        )
    elif platform == "reddit":
        result = scrape_reddit(raw, **common_cloak)
    elif platform == "instagram":
        result = scrape_instagram(raw, **common_cloak)
    elif platform == "facebook":
        result = scrape_facebook(raw, **common_cloak)
    else:
        result = None

    if result is None:
        return error_result(
            platform=platform,
            source_url=sanitize_url(raw),
            warnings=[f"no adapter result for platform={platform}"],
        )
    return result
