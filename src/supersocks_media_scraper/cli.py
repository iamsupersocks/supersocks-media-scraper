"""CLI for supersocks-media-scraper."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from . import __version__, scrape
from .warmup import run_warmup


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supersocks-media-scraper",
        description=(
            "Scrape visible public fields from X, Instagram, Facebook, or Reddit URLs. "
            "Not exhaustive. Never automates login/MFA/CAPTCHA."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "url",
        nargs="?",
        help="HTTP(S) URL on a supported platform",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum characters for text field (default: 4000)",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=20,
        help="Maximum visible comments to include when present (default: 20)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Per-backend timeout in seconds (default: 45)",
    )
    parser.add_argument(
        "--browser-profile-dir",
        default="",
        help="Explicit Cloak profile directory (overrides MEDIA_BROWSER_PROFILES_ROOT/{platform})",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Force headed CloakBrowser (requires DISPLAY/Xvfb on Linux)",
    )
    parser.add_argument(
        "--warmup",
        metavar="PLATFORM",
        choices=("reddit", "instagram", "facebook"),
        help="Headed warm-up for reddit|instagram|facebook (never automates login)",
    )
    parser.add_argument(
        "--create-profile",
        action="store_true",
        help="Create the platform profile directory during --warmup",
    )
    parser.add_argument(
        "--warmup-seconds",
        type=float,
        default=120.0,
        help="Seconds to keep the headed warm-up page open (default: 120)",
    )
    parser.add_argument(
        "--warmup-url",
        default="",
        help="Optional URL to open during warm-up (default: platform home)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.warmup:
        result: dict[str, Any] = run_warmup(
            args.warmup,
            url=args.warmup_url or args.url or "",
            wait_seconds=float(args.warmup_seconds),
            create_profile=bool(args.create_profile),
            browser_profile_dir=args.browser_profile_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"ok", "partial"} else 1

    if not args.url:
        parser.error("url is required unless --warmup is set")

    headless = False if args.headed else None
    payload = scrape(
        args.url,
        max_chars=args.max_chars,
        max_comments=args.max_comments,
        timeout=args.timeout,
        browser_profile_dir=args.browser_profile_dir,
        headless=headless,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    status = payload.get("status")
    return 0 if status in {"ok", "partial"} else 1


if __name__ == "__main__":
    sys.exit(main())
