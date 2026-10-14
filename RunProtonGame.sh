#!/usr/bin/env bash
set -euo pipefail

EXE="$1"
PROTON_VERSION="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/Splash.sh"

EXE_DIR="$(dirname "$EXE")"
APPID_FILE="$EXE_DIR/steam_appid.txt"
APPID="$(head -n1 "$APPID_FILE" | tr -d '\r\n ')"

STEAM_ROOT="$HOME/.steam/steam"
PROTON_ROOT="$STEAM_ROOT/steamapps/common"
PROTON="$PROTON_ROOT/$PROTON_VERSION/proton"

export STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT"
export STEAM_COMPAT_DATA_PATH="$STEAM_ROOT/steamapps/compatdata/$APPID"

# reine Namenslogik, generisch aus der EXE abgeleitet
EXE_BASENAME="$(basename "$EXE")"       # z.B. Dispatch.exe
EXE_STEM="${EXE_BASENAME%.*}"           # z.B. Dispatch

# Mute-File für Ducking
MUTE_FILE="$HOME/.mute"
touch "$MUTE_FILE"

STARTUP_TIMEOUT_SECS=120
PROTON_WINDOW_CLASS="steam_proton"

# Proton setzt WM_CLASS ohne SteamAppId-Env fest auf "steam_proton" (nicht auf den EXE-Namen)
game_window_visible() {
  xdotool search --onlyvisible --class "^${PROTON_WINDOW_CLASS}\$" &>/dev/null
}

cleanup() {
  echo "cleanup: beende Proton/Wine für $EXE_BASENAME" >&2

  # Mute-File aufräumen
  rm -f "$MUTE_FILE" 2>/dev/null || true
  stop_splash

  # erst höflich: wineserver zu diesem Prefix beenden
  WINEPREFIX="$STEAM_COMPAT_DATA_PATH/pfx" wineserver -k 2>/dev/null || true

  # dann alles killen, was zur EXE gehört
  # matcht z.B. 'Dispatch.exe'
  pkill "$EXE_BASENAME" 2>/dev/null || true

  # matcht z.B. 'Dispatch-Win64-' usw.
  pkill "$EXE_STEM" 2>/dev/null || true

  # falls das nicht reicht, noch mal mit kompletter cmdline
  pkill -f "$EXE_BASENAME" 2>/dev/null || true
  pkill -f "$EXE_STEM" 2>/dev/null || true
}

# Signals vom Python-Prozess (SIGTERM) abfangen
trap cleanup TERM INT QUIT

# Ladesplash bleibt stehen, bis das Spielfenster erscheint (Proton-Start dauert)
start_splash

cd "$EXE_DIR"

# wichtig: KEIN exec, damit das Script selbst das Signal bekommt
"$PROTON" run "$EXE" &
child=$!

# sleep im Hintergrund, damit der Trap sofort greift (Main.py schickt nach 1 s SIGKILL)
waited=0
while kill -0 "$child" 2>/dev/null && ! game_window_visible && (( waited < STARTUP_TIMEOUT_SECS )); do
  sleep 1 &
  wait $!
  waited=$((waited + 1))
done
stop_splash

wait "$child"
