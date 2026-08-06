# Official images for supersocks-media-scraper.
# Targets:
#   runtime (default) — lean headless scraper
#   warmup            — guided noVNC headed warm-up (Xvfb + openbox + x11vnc + noVNC)
# Honest containers: no automated login/CAPTCHA, no fake healthcheck.
# Cloak Chromium is pre-cached at build time (no runtime download).

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CLOAKBROWSER_SUPPRESS_FONT_WARNING=1 \
    HOME=/home/scraper \
    CLOAKBROWSER_CACHE_DIR=/home/scraper/.cloakbrowser \
    XDG_CACHE_HOME=/home/scraper/.cache \
    MEDIA_BROWSER_PROFILES_ROOT=/home/scraper/media-browser-profiles

WORKDIR /app

# CloakBrowser / Chromium shared libraries on Debian slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime with writable Cloak cache + persistent media profiles.
RUN useradd --create-home --home-dir /home/scraper --uid 10001 --shell /usr/sbin/nologin scraper \
    && mkdir -p \
        /home/scraper/.cloakbrowser \
        /home/scraper/.cache \
        /home/scraper/media-browser-profiles/reddit \
        /home/scraper/media-browser-profiles/instagram \
        /home/scraper/media-browser-profiles/facebook \
    && chown -R scraper:scraper /home/scraper

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Install the local package with all optional backends (no pip cache retained).
RUN pip install --no-cache-dir '.[all]' \
    && rm -rf /root/.cache /tmp/*

# Pre-cache CloakBrowser/Chromium under the runtime user's writable home.
USER scraper
RUN python -c "from cloakbrowser import ensure_binary; ensure_binary()"

# Persist Reddit / Instagram / Facebook operator-owned profiles across runs.
VOLUME ["/home/scraper/media-browser-profiles"]

ENTRYPOINT ["supersocks-media-scraper"]

# ---------------------------------------------------------------------------
# Guided warm-up image: virtual display + noVNC for one-time operator login.
# Runs as the same non-root scraper user. Never automates gates.
# ---------------------------------------------------------------------------
FROM runtime AS warmup

USER root
# Static noVNC assets (avoid the Debian novnc package, which pulls Node.js).
ARG NOVNC_VERSION=1.5.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        openbox \
        procps \
        websockify \
        wget \
        x11vnc \
        xvfb \
    && wget -qO /tmp/novnc.tgz \
        "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz" \
    && mkdir -p /usr/share/novnc \
    && tar -xzf /tmp/novnc.tgz -C /tmp \
    && cp -a "/tmp/noVNC-${NOVNC_VERSION}/." /usr/share/novnc/ \
    && rm -rf /tmp/novnc.tgz "/tmp/noVNC-${NOVNC_VERSION}" /var/lib/apt/lists/*

COPY docker/warmup-entrypoint.sh /usr/local/bin/warmup-entrypoint.sh
COPY docker/chromium-lock-cleanup.sh /usr/local/bin/chromium-lock-cleanup.sh
RUN chmod 0755 /usr/local/bin/warmup-entrypoint.sh \
    && chown scraper:scraper /usr/local/bin/warmup-entrypoint.sh \
    && chmod 0755 /usr/local/bin/chromium-lock-cleanup.sh \
    && chown scraper:scraper /usr/local/bin/chromium-lock-cleanup.sh \
    && mkdir -p /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix \
    && chown root:root /tmp/.X11-unix

ENV DISPLAY=:99 \
    WARMUP_SECONDS=600 \
    NOVNC_WEB=/usr/share/novnc

USER scraper
EXPOSE 6080
ENTRYPOINT ["/usr/local/bin/warmup-entrypoint.sh"]

# Default `docker build` target remains the lean headless runtime.
FROM runtime
