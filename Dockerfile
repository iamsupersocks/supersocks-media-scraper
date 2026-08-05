# Official runtime image for supersocks-media-scraper.
# Honest container: no automated login/CAPTCHA, no fake healthcheck.
# Headless cold profiles are supported; headed warm-up needs a display
# attached outside this standard headless image.

FROM python:3.12-slim

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
