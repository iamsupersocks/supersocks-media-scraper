"""Static contract checks for the supported Docker runtime."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docker_runtime_initializes_non_root_platform_profiles() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "USER scraper" in dockerfile
    assert 'ENTRYPOINT ["supersocks-media-scraper"]' in dockerfile
    assert "from cloakbrowser import ensure_binary; ensure_binary()" in dockerfile

    profile_root = "/home/scraper/media-browser-profiles"
    for platform in ("reddit", "instagram", "facebook"):
        assert f"{profile_root}/{platform}" in dockerfile

    assert f'VOLUME ["{profile_root}"]' in dockerfile
