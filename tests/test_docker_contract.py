"""Static contract checks for Docker runtime, warmup target, and Compose."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"
ENTRYPOINT = ROOT / "docker" / "warmup-entrypoint.sh"
PROFILE_ROOT = "/home/scraper/media-browser-profiles"
ALLOWED_PLATFORMS = ("reddit", "instagram", "facebook")
DEFAULT_VOLUME_NAME = "sms-media-profiles"


def test_dockerfile_has_runtime_and_warmup_targets() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")

    assert "FROM python:3.12-slim AS runtime" in text
    assert "FROM runtime AS warmup" in text
    # Default build stays lean runtime (final stage re-exports runtime).
    assert text.strip().endswith("FROM runtime")

    assert "USER scraper" in text
    assert 'ENTRYPOINT ["supersocks-media-scraper"]' in text
    assert 'ENTRYPOINT ["/usr/local/bin/warmup-entrypoint.sh"]' in text
    assert "from cloakbrowser import ensure_binary; ensure_binary()" in text

    for platform in ALLOWED_PLATFORMS:
        assert f"{PROFILE_ROOT}/{platform}" in text
    assert f'VOLUME ["{PROFILE_ROOT}"]' in text

    for pkg in ("xvfb", "openbox", "x11vnc", "novnc", "websockify"):
        assert pkg.lower() in text.lower()
    assert "NOVNC_VERSION" in text or "/usr/share/novnc" in text
    assert "nodejs" not in text.lower()


def test_compose_parse_shared_volume_and_loopback_novnc() -> None:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

    services = data["services"]
    assert set(services) >= {"scraper", "warmup"}

    scraper = services["scraper"]
    warmup = services["warmup"]

    assert scraper["build"]["target"] == "runtime"
    assert warmup["build"]["target"] == "warmup"

    assert scraper["volumes"] == ["media-browser-profiles:/home/scraper/media-browser-profiles"]
    assert warmup["volumes"] == ["media-browser-profiles:/home/scraper/media-browser-profiles"]

    volumes = data["volumes"]
    assert "media-browser-profiles" in volumes
    assert volumes["media-browser-profiles"]["name"] == "${MEDIA_PROFILES_VOLUME:-sms-media-profiles}"

    ports = warmup["ports"]
    assert ports == ["127.0.0.1:6080:6080"]
    assert "6080:6080" not in ports
    assert not any(isinstance(p, str) and p.startswith("0.0.0.0:") for p in ports)

    env = warmup["environment"]
    assert env["WARMUP_PLATFORM"] == "${WARMUP_PLATFORM:-reddit}"
    assert "600" in str(env["WARMUP_SECONDS"])

    # X credentials are host env pass-through only on the scraper service.
    scraper_env = scraper["environment"]
    assert "TWITTER_AUTH_TOKEN" in scraper_env
    assert "TWITTER_CT0" in scraper_env


def _run_compose_config(extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("WARMUP_PLATFORM", "MEDIA_PROFILES_VOLUME")}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_compose_config_validates_without_warmup_platform() -> None:
    try:
        proc = _run_compose_config()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"docker compose unavailable: {exc}")

    if proc.returncode != 0:
        combined = (proc.stdout or "") + (proc.stderr or "")
        if "permission denied" in combined.lower() or "cannot connect" in combined.lower():
            pytest.skip(f"docker daemon unavailable: {combined.strip()[:200]}")
        pytest.fail(f"docker compose config failed without WARMUP_PLATFORM:\n{combined}")

    rendered = yaml.safe_load(proc.stdout)
    warmup_env = rendered["services"]["warmup"]["environment"]
    assert warmup_env["WARMUP_PLATFORM"] == "reddit"

    port_entries = rendered["services"]["warmup"]["ports"]
    serialized = yaml.safe_dump(port_entries)
    assert "127.0.0.1" in serialized
    assert "6080" in serialized

    assert rendered["volumes"]["media-browser-profiles"]["name"] == DEFAULT_VOLUME_NAME
    assert rendered["services"]["scraper"]["volumes"] == rendered["services"]["warmup"]["volumes"]


def test_compose_config_volume_override() -> None:
    try:
        proc = _run_compose_config({"MEDIA_PROFILES_VOLUME": "sms-media-profiles-qa"})
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"docker compose unavailable: {exc}")

    if proc.returncode != 0:
        combined = (proc.stdout or "") + (proc.stderr or "")
        if "permission denied" in combined.lower() or "cannot connect" in combined.lower():
            pytest.skip(f"docker daemon unavailable: {combined.strip()[:200]}")
        pytest.fail(f"docker compose config failed with volume override:\n{combined}")

    rendered = yaml.safe_load(proc.stdout)
    assert rendered["volumes"]["media-browser-profiles"]["name"] == "sms-media-profiles-qa"


def test_warmup_entrypoint_allowlist_and_invalid_platform_exit() -> None:
    script = ENTRYPOINT.read_text(encoding="utf-8")
    assert "ALLOWED_PLATFORMS=" in script
    for platform in ALLOWED_PLATFORMS:
        assert platform in script
    assert "invalid WARMUP_PLATFORM" in script
    assert "never" in script.lower() and "password" in script.lower()
    assert "localhost" in script
    assert "supersocks-media-scraper" in script
    assert "--create-profile" in script
    assert "trap" in script

    assert ENTRYPOINT.stat().st_mode & 0o111, "entrypoint must be executable"

    proc = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "WARMUP_PLATFORM": "tiktok",
            "HOME": str(ROOT / ".pytest_warmup_home"),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert proc.returncode != 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "invalid WARMUP_PLATFORM" in combined
    assert "tiktok" in combined


def test_warmup_entrypoint_defaults_to_reddit_when_unset() -> None:
    proc = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(ROOT / ".pytest_warmup_home"),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert proc.returncode != 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "platform=reddit" in combined
    assert "invalid WARMUP_PLATFORM" not in combined


@pytest.mark.parametrize("seconds", ["0", "0.0"])
def test_warmup_entrypoint_rejects_non_positive_warmup_seconds(seconds: str) -> None:
    proc = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "WARMUP_PLATFORM": "reddit",
            "WARMUP_SECONDS": seconds,
            "HOME": str(ROOT / ".pytest_warmup_home"),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert proc.returncode != 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "WARMUP_SECONDS must be a positive number" in combined
