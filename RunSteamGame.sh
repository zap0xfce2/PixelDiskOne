#!/usr/bin/env bash
set -euo pipefail

APPID="$1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/Splash.sh"

MUTE_FILE="$HOME/.mute"
STARTUP_TIMEOUT_SECS=120
# Steam startet jedes Spiel als "reaper SteamLaunch AppId=<APPID> -- …"; Wortgrenze verhindert Präfix-Treffer
GAME_PATTERN="AppId=${APPID}( |$)"
# Steam setzt WM_CLASS des Spielfensters auf "steam_app_<APPID>" (Proton und nativ)
GAME_WINDOW_CLASS="steam_app_${APPID}"
STEAM_CLIENT_WINDOW_CLASS="steam"

descendant_pids() {
  local pid child
  for pid in "$@"; do
    echo "$pid"
    for child in $(pgrep -P "$pid"); do
      descendant_pids "$child"
    done
  done
}

# Ganzen Baum vorab sammeln: das Spiel läuft unter pressure-vessel in eigener Prozessgruppe ohne AppId in der cmdline
cleanup() {
  local pids
  rm -f "$MUTE_FILE" 2>/dev/null || true
  stop_splash
  mapfile -t pids < <(descendant_pids $(pgrep -f "$GAME_PATTERN"))
  (( ${#pids[@]} )) && kill -TERM "${pids[@]}" 2>/dev/null || true
}

game_running() {
  pgrep -f "$GAME_PATTERN" >/dev/null
}

game_window_visible() {
  xdotool search --onlyvisible --class "^${GAME_WINDOW_CLASS}\$" &>/dev/null
}

# Hauptfenster ist per -silent versteckt → sichtbares Steam-Fenster ist ein Dialog (Update, Bestätigung)
steam_dialog_visible() {
  xdotool search --onlyvisible --class "^${STEAM_CLIENT_WINDOW_CLASS}\$" &>/dev/null
}

# Splash darf Steam-Dialoge nicht verdecken, sonst wartet der Start unsichtbar auf eine Eingabe
wait_one_second_revealing_dialogs() {
  steam_dialog_visible && stop_splash
  interruptible_sleep
}

# sleep im Hintergrund, damit der Trap sofort greift (Main.py schickt nach 1 s SIGKILL)
interruptible_sleep() {
  sleep 1 &
  wait $!
}

trap 'exit 143' TERM INT QUIT
trap cleanup EXIT

touch "$MUTE_FILE"
# Ladesplash bleibt stehen, bis das Spielfenster erscheint (Steam-Kaltstart dauert)
start_splash

# setsid: kalt gestarteter Client überlebt das Entfernen der Diskette; -silent: kein Steam-Hauptfenster
setsid steam -silent "steam://rungameid/$APPID" &>/dev/null &

waited=0
until game_running; do
  if (( waited >= STARTUP_TIMEOUT_SECS )); then
    echo "Spiel $APPID nach ${STARTUP_TIMEOUT_SECS}s nicht gestartet." >&2
    exit 1
  fi
  wait_one_second_revealing_dialogs
  waited=$((waited + 1))
done

# Prozess läuft, Fenster evtl. noch nicht; anderes WM_CLASS → Splash endet spätestens nach Timeout
while game_running && ! game_window_visible && (( waited < STARTUP_TIMEOUT_SECS )); do
  wait_one_second_revealing_dialogs
  waited=$((waited + 1))
done
stop_splash

while game_running; do
  interruptible_sleep
done
