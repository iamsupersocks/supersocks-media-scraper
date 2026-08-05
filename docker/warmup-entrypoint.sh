#!/usr/bin/env bash
# Guided noVNC warm-up entrypoint for Reddit / Instagram / Facebook.
# Starts Xvfb + lightweight WM + x11vnc + websockify/noVNC, then runs headed
# supersocks-media-scraper --warmup. Never automates login/MFA/CAPTCHA and never
# inspects browser cookies.
set -euo pipefail

ALLOWED_PLATFORMS="reddit instagram facebook"
PLATFORM="$(printf '%s' "${WARMUP_PLATFORM:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
WARMUP_SECONDS="${WARMUP_SECONDS:-600}"
DISPLAY_NUM="${DISPLAY_NUM:-99}"
export DISPLAY=":${DISPLAY_NUM}"
NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
SCREEN_GEOM="${SCREEN_GEOM:-1280x800x24}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-45}"

CHILD_PIDS=()
SCRAPER_PID=""

log() {
  printf '[warmup] %s\n' "$*" >&2
}

die() {
  log "ERROR: $*"
  exit 1
}

is_allowed_platform() {
  local candidate="$1"
  local item
  for item in ${ALLOWED_PLATFORMS}; do
    if [[ "${item}" == "${candidate}" ]]; then
      return 0
    fi
  done
  return 1
}

cleanup_children() {
  local pid
  if [[ -n "${SCRAPER_PID}" ]]; then
    kill -TERM "${SCRAPER_PID}" 2>/dev/null || true
  fi
  for pid in "${CHILD_PIDS[@]:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill -TERM "${pid}" 2>/dev/null || true
    fi
  done
  sleep 0.5
  for pid in "${CHILD_PIDS[@]:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}

on_signal() {
  log "received signal; shutting down child processes"
  cleanup_children
  exit 143
}

trap on_signal INT TERM
trap cleanup_children EXIT

if [[ -z "${PLATFORM}" ]]; then
  die "WARMUP_PLATFORM is required (allowed: ${ALLOWED_PLATFORMS})"
fi
if ! is_allowed_platform "${PLATFORM}"; then
  die "invalid WARMUP_PLATFORM='${PLATFORM}' (allowed: ${ALLOWED_PLATFORMS})"
fi
if ! [[ "${WARMUP_SECONDS}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  die "WARMUP_SECONDS must be a positive number (got '${WARMUP_SECONDS}')"
fi

# Security posture: VNC has no password. Acceptable only because x11vnc binds
# localhost inside the container and Compose must publish 127.0.0.1:6080 only.
# Never expose noVNC on a public interface.
log "WARNING: noVNC has no password; keep it on loopback (127.0.0.1:6080) only — never publish publicly"
log "platform=${PLATFORM} warmup_seconds=${WARMUP_SECONDS} display=${DISPLAY}"

command -v Xvfb >/dev/null || die "Xvfb not installed in warmup image"
command -v openbox >/dev/null || die "openbox not installed in warmup image"
command -v x11vnc >/dev/null || die "x11vnc not installed in warmup image"
command -v websockify >/dev/null || die "websockify not installed in warmup image"
[[ -d "${NOVNC_WEB}" ]] || die "noVNC web root missing at ${NOVNC_WEB}"

log "starting Xvfb on ${DISPLAY}"
Xvfb "${DISPLAY}" -screen 0 "${SCREEN_GEOM}" -ac -nolisten tcp &
CHILD_PIDS+=("$!")

for _ in $(seq 1 "${READY_TIMEOUT_SECONDS}"); do
  if [[ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]]; then
    break
  fi
  sleep 0.25
done
[[ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]] || die "Xvfb failed to become ready on ${DISPLAY}"

log "starting openbox"
openbox >/tmp/openbox.log 2>&1 &
CHILD_PIDS+=("$!")

log "starting x11vnc (localhost-only, no password)"
x11vnc \
  -display "${DISPLAY}" \
  -rfbport "${VNC_PORT}" \
  -localhost \
  -nopw \
  -forever \
  -shared \
  -quiet \
  -bg \
  -o /tmp/x11vnc.log
# x11vnc -bg forks; recover the listener pid from the log or pgrep.
sleep 0.5
X11VNC_PID="$(pgrep -n -x x11vnc || true)"
[[ -n "${X11VNC_PID}" ]] || die "x11vnc failed to start (see /tmp/x11vnc.log)"
CHILD_PIDS+=("${X11VNC_PID}")

log "starting websockify/noVNC on 0.0.0.0:${NOVNC_PORT} -> localhost:${VNC_PORT}"
websockify \
  --web="${NOVNC_WEB}" \
  "0.0.0.0:${NOVNC_PORT}" \
  "localhost:${VNC_PORT}" \
  >/tmp/websockify.log 2>&1 &
CHILD_PIDS+=("$!")

ready=0
for _ in $(seq 1 "${READY_TIMEOUT_SECONDS}"); do
  if (echo >/dev/tcp/127.0.0.1/"${NOVNC_PORT}") >/dev/null 2>&1; then
    ready=1
    break
  fi
  # Fallback when /dev/tcp is unavailable.
  if command -v python3 >/dev/null; then
    if python3 - <<PY >/dev/null 2>&1
import socket
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", int("${NOVNC_PORT}")))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
    then
      ready=1
      break
    fi
  fi
  sleep 0.25
done
[[ "${ready}" -eq 1 ]] || die "noVNC/websockify failed to become ready on port ${NOVNC_PORT}"

log "noVNC ready: http://127.0.0.1:${NOVNC_PORT}/vnc.html?autoconnect=1&resize=scale"
log "complete login/consent/challenge manually in the browser, then stop this service"
log "starting headed warm-up: supersocks-media-scraper --warmup ${PLATFORM} --create-profile"

supersocks-media-scraper \
  --warmup "${PLATFORM}" \
  --create-profile \
  --warmup-seconds "${WARMUP_SECONDS}" &
SCRAPER_PID=$!

set +e
wait "${SCRAPER_PID}"
exit_code=$?
set -e
SCRAPER_PID=""

log "warm-up process exited with code ${exit_code}"
cleanup_children
trap - EXIT INT TERM
exit "${exit_code}"
