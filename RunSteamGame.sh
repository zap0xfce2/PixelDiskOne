#!/usr/bin/env bash
set -euo pipefail

APPID="$1"

MUTE_FILE="$HOME/.mute"
STARTUP_TIMEOUT_SECS=120
LIBRARY_FOLDERS_FILE="$HOME/.steam/steam/steamapps/libraryfolders.vdf"
# Steam startet jedes Spiel als "reaper SteamLaunch AppId=<APPID> -- …"; Wortgrenze verhindert Präfix-Treffer
GAME_PATTERN="AppId=${APPID}( |$)"

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
  move_mouse_bottom_left
  mapfile -t pids < <(descendant_pids $(pgrep -f "$GAME_PATTERN"))
  (( ${#pids[@]} )) && kill -TERM "${pids[@]}" 2>/dev/null || true
}

# Steam lässt die Maus oben links über der XFCE-Leiste stehen; wie in PixelDiskOne-Start.sh nach unten links
move_mouse_bottom_left() {
  xdotool mousemove 0 "$(xdpyinfo | awk '/dimensions/{print $2}' | cut -d'x' -f2)" 2>/dev/null || true
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
notify-send "Diskette eingelegt" "$(game_name) wird gestartet." -i "/home/retro/PixelDiskOne/floppy-disk.png" -t "5000"

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

while game_running; do
  interruptible_sleep
done
