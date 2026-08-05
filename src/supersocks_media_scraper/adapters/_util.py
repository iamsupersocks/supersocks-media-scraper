"""Shared helpers for optional upstream CLIs and HTML parsing.

Security rules:
- Never collect, print, or persist cookies/tokens/profiles.
- Never auto-read browser cookie stores.
- Warnings and errors must be actionable without leaking secrets.
"""

from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from ..sanitize import redact_secrets, trim_text

__all__ = [
    "CommandResult",
    "actionable_missing_tool",
    "child_env_without_browser_cookie_hints",
    "clean_text",
    "detect_platform",
    "host_matches_root",
    "is_http_url",
    "is_private_or_local_host",
    "is_safe_public_http_url",
    "parse_json_payload",
    "redact_secrets",
    "run_command",
    "trim_text",
    "url_has_userinfo",
    "which",
]

_PLATFORM_ROOTS: dict[str, frozenset[str]] = {
    "x": frozenset({"x.com", "twitter.com"}),
    "instagram": frozenset({"instagram.com", "instagr.am"}),
    "facebook": frozenset({"facebook.com", "fb.com", "fb.watch"}),
    "reddit": frozenset({"reddit.com", "redd.it", "redditmedia.com"}),
}


def which(command: str) -> str | None:
    return shutil.which(command)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(
    argv: Sequence[str],
    *,
    timeout: int = 30,
    env: Mapping[str, str] | None = None,
    runner: Any | None = None,
) -> CommandResult:
    if runner is not None:
        return runner(list(argv), timeout=timeout, env=dict(env) if env is not None else None)

    completed = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        timeout=max(1, int(timeout)),
        env=dict(env) if env is not None else None,
        check=False,
    )
    return CommandResult(
        returncode=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def parse_json_payload(raw: str) -> Any:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty JSON payload")
    return json.loads(text)


def child_env_without_browser_cookie_hints(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base if base is not None else os.environ)
    for key in ("TWITTER_BROWSER", "TWITTER_CHROME_PROFILE"):
        env.pop(key, None)
    return env


def actionable_missing_tool(tool: str, install_hint: str) -> str:
    return f"{tool} not available on PATH; {install_hint}"


def _normalized_host(hostname: str | None) -> str:
    host = (hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def host_matches_root(hostname: str | None, root: str) -> bool:
    host = _normalized_host(hostname)
    root = root.lower().strip(".")
    if not host or not root:
        return False
    return host == root or host.endswith("." + root)


def url_has_userinfo(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""))


def is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_private_or_local_host(hostname: str | None) -> bool:
    host = (hostname or "").lower().strip(".")
    if not host:
        return True
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost") or host.endswith(".local"):
        return True
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", candidate):
            return True
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def detect_platform(url: str) -> str | None:
    if not is_http_url(url) or url_has_userinfo(url):
        return None
    host = urlparse(url).hostname
    if is_private_or_local_host(host):
        return None
    for platform, roots in _PLATFORM_ROOTS.items():
        if any(host_matches_root(host, root) for root in roots):
            return platform
    return None


def is_safe_public_http_url(url: str) -> bool:
    if not is_http_url(url) or url_has_userinfo(url):
        return False
    parsed = urlparse(url)
    return not is_private_or_local_host(parsed.hostname)


def clean_text(value: object) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return " ".join(text.split())
