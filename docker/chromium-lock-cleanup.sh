#!/usr/bin/env bash
# Scoped Chromium stale-lock cleanup for the warmup container.
#
# Chromium leaves three top-level entries in a profile dir when it is killed or
# the container stops: SingletonLock, SingletonSocket, SingletonCookie. Those
# persist as symlinks pointing at a dead socket, so the next Cloak launch fails
# with "browser session closed". This helper removes ONLY those three known
# entries from the ONE allowlisted platform profile dir under
# MEDIA_BROWSER_PROFILES_ROOT.
#
# Safety contract (enforced and covered by tests):
#   - Deletes only SingletonLock / SingletonSocket / SingletonCookie at the
#     top level of the scoped profile dir.
#   - Operates only inside the single allowlisted platform profile dir.
#   - Never inspects or deletes cookies, databases, or any other file.
#   - Empty/missing root or invalid/empty platform => no-op (safe).
#
# Usable two ways:
#   * Sourced by warmup-entrypoint.sh (functions defined, nothing runs).
#   * Standalone:
#       MEDIA_BROWSER_PROFILES_ROOT=/x WARMUP_PLATFORM=reddit \
#         ./chromium-lock-cleanup.sh
set -euo pipefail

ALLOWED_PLATFORMS="reddit instagram facebook"
CHROMIUM_LOCK_ENTRIES=(SingletonLock SingletonSocket SingletonCookie)

is_allowed_platform() {
  local candidate="$1" item
  for item in ${ALLOWED_PLATFORMS}; do
    if [[ "${item}" == "${candidate}" ]]; then
      return 0
    fi
  done
  return 1
}

# Resolve the scoped platform profile dir, or empty string when unsafe/unset.
scoped_profile_dir() {
  local root platform
  root="$(printf '%s' "${MEDIA_BROWSER_PROFILES_ROOT:-}" | tr -d '[:space:]')"
  platform="$(printf '%s' "${WARMUP_PLATFORM:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  if [[ -z "${root}" ]] || ! is_allowed_platform "${platform}"; then
    printf ''
    return 0
  fi
  printf '%s/%s' "${root%/}" "${platform}"
}

# Remove only the three known Chromium lock entries from the scoped profile
# dir. No-op when the dir cannot be safely scoped or does not exist. Never
# touches any other file.
remove_stale_chromium_locks() {
  local dir entry
  dir="$(scoped_profile_dir)"
  if [[ -z "${dir}" ]] || [[ ! -d "${dir}" ]]; then
    return 0
  fi
  for entry in "${CHROMIUM_LOCK_ENTRIES[@]}"; do
    if [[ -L "${dir}/${entry}" ]] || [[ -e "${dir}/${entry}" ]]; then
      rm -f -- "${dir}/${entry}" || true
    fi
  done
}

# Standalone CLI entrypoint.
if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  remove_stale_chromium_locks
fi