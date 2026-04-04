#!/usr/bin/env bash
# Startet zufällig ein Youtube Video aus einer Playlist.
# Zeigt vorher sofort einen Splashscreen, bis das Video startet.
# Verwendung: YoutubePlayer.sh <PLAYLIST> <SPLASHGRAFIK>

set -ou pipefail

: "${1:?Playlist-ID fehlt}"

command -v ffplay  >/dev/null || { echo "ffplay nicht gefunden"  >&2; exit 1; }
command -v yt-dlp  >/dev/null || { echo "yt-dlp nicht gefunden"  >&2; exit 1; }
command -v feh     >/dev/null || { echo "feh nicht gefunden"     >&2; exit 1; }
command -v xdotool >/dev/null || { echo "xdotool nicht gefunden" >&2; exit 1; }

PLAYLIST_ID="$1"

# Mute-File für Ducking
MUTE_FILE="$HOME/.mute"
touch "$MUTE_FILE"

# Default Splash-Grafik (kann optional als 2. Argument überschrieben werden)
DEFAULT_SPLASH_PNG="/home/retro/Bilder/LoadingScreen.png"
SPLASH_PNG="${2:-$DEFAULT_SPLASH_PNG}"

PLAYLIST_URL="https://www.youtube.com/playlist?list=${PLAYLIST_ID}"
WINDOW_TITLE="YoutubePlayer"

splash_pid=""

cleanup() {
  rm -f "$MUTE_FILE" 2>/dev/null || true
  stop_splash
}
trap cleanup EXIT INT TERM QUIT

start_splash() {
  if [[ -n "${SPLASH_PNG}" && -f "${SPLASH_PNG}" ]]; then
    feh --fullscreen --hide-pointer --auto-zoom "${SPLASH_PNG}" >/dev/null 2>&1 &
    splash_pid=$!
    return 0
  fi

  ffplay -window_title "${WINDOW_TITLE}-splash" -fs -loglevel quiet -nostats -hide_banner \
    -f lavfi -i "color=c=black" >/dev/null 2>&1 &
  splash_pid=$!
}

stop_splash() {
  if [[ -n "${splash_pid}" ]] && kill -0 "${splash_pid}" 2>/dev/null; then
    kill "${splash_pid}" 2>/dev/null || true
    wait "${splash_pid}" 2>/dev/null || true
  fi
  splash_pid=""
}

# Splash sofort starten (instant Feedback)
start_splash

# Playlist einmal einlesen
mapfile -t URLS < <(yt-dlp --flat-playlist --print url "$PLAYLIST_URL" 2>/dev/null | sed '/^$/d')

if (( ${#URLS[@]} == 0 )); then
  echo "Keine Videos gefunden (Playlist leer / privat / Fehler beim Laden)." >&2
  exit 1
fi

echo "Playlist geladen: ${#URLS[@]} Videos" >&2

while true; do
  url="${URLS[RANDOM % ${#URLS[@]}]}"
  echo "Versuche: $url" >&2

  # Stream-URL via Android-Client (kein Login nötig)
  direct_url="$(yt-dlp --extractor-args "youtube:player_client=android" \
    -f 'best[acodec!=none][vcodec!=none]/best[acodec!=none]/best' \
    -g "$url" 2>/dev/null | head -n 1 || true)"

  if [[ -z "${direct_url}" ]]; then
    echo "Keine Stream-URL gefunden -> neu shufflen" >&2
    continue
  fi

  # Video starten, während der Splash noch sichtbar ist (weniger Flackern)
  ffplay -window_title "${WINDOW_TITLE}" -fs -loglevel quiet -nostats -hide_banner "$direct_url" 2>/dev/null &
  video_pid=$!

  # Sobald das Video-Fenster existiert, Splash beenden
  for _ in {1..50}; do
    xdotool search --name "^${WINDOW_TITLE}$" >/dev/null 2>&1 && break
    sleep 0.05
  done

  stop_splash

  # Auf den Player warten; ffplay bleibt am Ende stehen bis du schließt
  wait "$video_pid" 2>/dev/null
  video_exit=$?

  # Normales Beenden (User hat Fenster geschlossen) → fertig
  if (( video_exit == 0 )); then
    exit 0
  fi

  # Fehler → nächstes Video versuchen
  echo "Wiedergabe fehlgeschlagen (Exit ${video_exit}) -> neu shufflen" >&2
  start_splash
done
