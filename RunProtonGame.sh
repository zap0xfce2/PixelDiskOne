#!/usr/bin/env bash
set -euo pipefail

EXE="$1"
PROTON_VERSION="$2"

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

# Notification senden da der Start ein wenig dauern kann
notify-send "Diskette eingelegt" "$EXE_STEM wird gestartet." -i "/home/retro/PixelDiskOne/floppy-disk.png" -t "5000"

cleanup() {
  echo "cleanup: beende Proton/Wine für $EXE_BASENAME" >&2

  # Mute-File aufräumen
  rm -f "$MUTE_FILE" 2>/dev/null || true

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

cd "$EXE_DIR"

# wichtig: KEIN exec, damit das Script selbst das Signal bekommt
"$PROTON" run "$EXE" &
child=$!

wait "$child"
