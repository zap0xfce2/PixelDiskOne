#!/usr/bin/env bash
# Startet zufällig ein Youtube Video aus einer Playlist.
# Zeigt vorher sofort einen Splashscreen, bis das Video startet.
# Verwendung: YoutubePlayer.sh <PLAYLIST> [LAUTSTÄRKE]

set -ou pipefail

# Secrets aus .env laden
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  source "$SCRIPT_DIR/.env"
fi

: "${1:?Playlist-ID fehlt}"

command -v mpv     >/dev/null || { echo "mpv nicht gefunden"     >&2; exit 1; }
command -v feh     >/dev/null || { echo "feh nicht gefunden"     >&2; exit 1; }
command -v xdotool >/dev/null || { echo "xdotool nicht gefunden" >&2; exit 1; }
command -v curl    >/dev/null || { echo "curl nicht gefunden"    >&2; exit 1; }
command -v jq      >/dev/null || { echo "jq nicht gefunden"      >&2; exit 1; }
command -v ffmpeg  >/dev/null || { echo "ffmpeg nicht gefunden"  >&2; exit 1; }

PLAYLIST_ID="$1"

# Mute-File für Ducking
MUTE_FILE="$HOME/.mute"
touch "$MUTE_FILE"

SPLASH_PNG="/home/retro/Bilder/LoadingScreen.png"
VOLUME="${2:-100}"

INVIDIOUS_BASE_URL="${INVIDIOUS_BASE_URL:-https://inv.nadeko.net}"
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

  mpv --fs --no-input-default-bindings --title="${WINDOW_TITLE}-splash" \
    "av://lavfi:color=c=black:s=1920x1080:r=1" --loop-file=inf 2>/dev/null &
  splash_pid=$!
}

stop_splash() {
  if [[ -n "${splash_pid}" ]] && kill -0 "${splash_pid}" 2>/dev/null; then
    kill "${splash_pid}" 2>/dev/null || true
    wait "${splash_pid}" 2>/dev/null || true
  fi
  splash_pid=""
}

load_playlist_from_invidious() {
  local page=1
  local total_count=0
  while true; do
    local response
    response=$(curl -sf "${INVIDIOUS_BASE_URL}/api/v1/playlists/${PLAYLIST_ID}?page=${page}")
    [[ -z "$response" ]] && break

    if (( page == 1 )); then
      total_count=$(printf '%s' "$response" | jq -r '.videoCount // 0')
    fi

    local ids
    ids=$(printf '%s' "$response" | jq -r '.videos[].videoId // empty')
    [[ -z "$ids" ]] && break

    while IFS= read -r id; do
      URLS+=("${INVIDIOUS_BASE_URL}/watch?v=${id}")
    done <<< "$ids"

    (( ${#URLS[@]} >= total_count )) && break
    (( page++ ))
  done

  # Duplikate entfernen (Reihenfolge beibehalten)
  mapfile -t URLS < <(printf '%s\n' "${URLS[@]}" | awk '!seen[$0]++')
}

# Splash sofort starten (instant Feedback)
start_splash

# Playlist einmal einlesen
URLS=()
load_playlist_from_invidious

if (( ${#URLS[@]} == 0 )); then
  echo "Keine Videos gefunden (Playlist leer / privat / Fehler beim Laden)." >&2
  exit 1
fi

echo "Playlist geladen: ${#URLS[@]} Videos" >&2

while true; do
  url="${URLS[RANDOM % ${#URLS[@]}]}"
  echo "Versuche: $url" >&2

  # Video- und Audio-Stream via Invidious adaptiveFormats auflösen
  video_id="${url##*v=}"
  api_response="$(curl -sf "${INVIDIOUS_BASE_URL}/api/v1/videos/${video_id}?fields=adaptiveFormats&local=true")"

  video_url="$(printf '%s' "$api_response" \
    | jq -r '[.adaptiveFormats[] | select(.type | startswith("video/"))] | sort_by(.bitrate | tonumber) | last | .url // empty')"

  audio_url="$(printf '%s' "$api_response" \
    | jq -r '[.adaptiveFormats[] | select(.type | startswith("audio/"))] | sort_by(.bitrate | tonumber) | last | .url // empty')"

  video_type="$(printf '%s' "$api_response" \
    | jq -r '[.adaptiveFormats[] | select(.type | startswith("video/"))] | sort_by(.bitrate | tonumber) | last | .encoding // empty')"

  bsf_args=()
  [[ "$video_type" == "h264" ]] && bsf_args=(-bsf:v h264_mp4toannexb)

  if [[ -z "${video_url}" || -z "${audio_url}" ]]; then
    echo "Keine Stream-URLs gefunden -> neu shufflen" >&2
    continue
  fi

  # ffmpeg merged Video+Audio zu einem Stream (verhindert Desync); startet während Splash läuft
  ffmpeg -i "$video_url" -i "$audio_url" -map 0:v -map 1:a -c copy "${bsf_args[@]}" -f matroska - 2>/tmp/ffmpeg.log \
    | mpv --fs --no-osc --osd-level=0 --keep-open=yes --volume="${VOLUME}" --title="${WINDOW_TITLE}" - 2>/tmp/mpv.log &
  video_pid=$!

  # Sobald das Video-Fenster existiert, Splash beenden
  window_found=false
  for _ in {1..50}; do
    if xdotool search --name "^${WINDOW_TITLE}$" >/dev/null 2>&1; then
      window_found=true
      break
    fi
    sleep 0.1
  done

  stop_splash

  # Auf den Player warten; mpv bleibt am Ende stehen bis du schließt
  wait "$video_pid" 2>/dev/null

  # Fenster war sichtbar → User hat geschlossen → fertig
  if [[ "${window_found}" == true ]]; then
    exit 0
  fi

  # Fenster nie erschienen → Ladefehler → nächstes Video versuchen
  echo "Stream konnte nicht gestartet werden -> neu shufflen" >&2
  start_splash
done
