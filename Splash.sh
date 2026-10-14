# shellcheck shell=bash
# Vollbild-Ladesplash (feh) als Lade-Feedback; wird per "source" eingebunden.
# Voraussetzung: feh

SPLASH_PNG="${SPLASH_PNG:-/home/retro/Bilder/LoadingScreen.png}"
splash_pid=""

start_splash() {
  if [[ -n "${SPLASH_PNG}" && -f "${SPLASH_PNG}" ]]; then
    feh --fullscreen --hide-pointer --auto-zoom "${SPLASH_PNG}" >/dev/null 2>&1 &
    splash_pid=$!
  fi
}

stop_splash() {
  if [[ -n "${splash_pid}" ]] && kill -0 "${splash_pid}" 2>/dev/null; then
    kill "${splash_pid}" 2>/dev/null || true
    wait "${splash_pid}" 2>/dev/null || true
  fi
  splash_pid=""
}
