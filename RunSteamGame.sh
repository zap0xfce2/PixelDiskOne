#!/usr/bin/env bash
set -euo pipefail

APPID="$1"

MUTE_FILE="$HOME/.mute"
STARTUP_TIMEOUT_SECS=120
LIBRARY_FOLDERS_FILE="$HOME/.steam/steam/steamapps/libraryfolders.vdf"
# Steam startet jedes Spiel als "reaper SteamLaunch AppId=<APPID> -- …"; Wortgrenze verhindert Präfix-Treffer
GAME_PATTERN="AppId=${APPID}( |$)"
NOTIFY_ID=""

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
  close_start_toast
  mapfile -t pids < <(descendant_pids $(pgrep -f "$GAME_PATTERN"))
  (( ${#pids[@]} )) && kill -TERM "${pids[@]}" 2>/dev/null || true
}

# Start-Toast bleibt ohne Timeout stehen, bis das Spiel läuft (Steam-Kaltstart dauert)
close_start_toast() {
  [[ -n "$NOTIFY_ID" ]] || return 0
  gdbus call --session --dest org.freedesktop.Notifications \
    --object-path /org/freedesktop/Notifications \
    --method org.freedesktop.Notifications.CloseNotification "$NOTIFY_ID" &>/dev/null || true
}

game_running() {
  pgrep -f "$GAME_PATTERN" >/dev/null
}

# sleep im Hintergrund, damit der Trap sofort greift (Main.py schickt nach 1 s SIGKILL)
interruptible_sleep() {
  sleep 1 &
  wait $!
}

# Spielname aus appmanifest_<APPID>.acf aller Steam-Bibliotheken, Fallback: App-ID
game_name() {
  local library manifest name
  while read -r library; do
    manifest="$library/steamapps/appmanifest_${APPID}.acf"
    [[ -f "$manifest" ]] || continue
    name="$(sed -nE 's/^[[:space:]]*"name"[[:space:]]+"(.*)"/\1/p' "$manifest" | head -n1)"
    [[ -n "$name" ]] && { echo "$name"; return; }
  done < <(sed -nE 's/^[[:space:]]*"path"[[:space:]]+"(.*)"/\1/p' "$LIBRARY_FOLDERS_FILE" 2>/dev/null)
  echo "$APPID"
}

trap 'exit 143' TERM INT QUIT
trap cleanup EXIT

touch "$MUTE_FILE"
NOTIFY_ID="$(notify-send -p -t 0 "Diskette eingelegt" "$(game_name) wird gestartet." -i "/home/retro/PixelDiskOne/floppy-disk.png" || true)"

# setsid: kalt gestarteter Client überlebt das Entfernen der Diskette; -silent: kein Steam-Hauptfenster
setsid steam -silent "steam://rungameid/$APPID" &>/dev/null &

waited=0
until game_running; do
  if (( waited >= STARTUP_TIMEOUT_SECS )); then
    echo "Spiel $APPID nach ${STARTUP_TIMEOUT_SECS}s nicht gestartet." >&2
    exit 1
  fi
  interruptible_sleep
  waited=$((waited + 1))
done
close_start_toast

while game_running; do
  interruptible_sleep
done
