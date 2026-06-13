#!/usr/bin/env bash
# Startet zufällig ein Youtube Video aus einer Playlist.
# Lädt Playlist & Streams primär via Invidious, fällt bei Fehlern auf direktes
# YouTube (yt-dlp) zurück.
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
command -v yt-dlp  >/dev/null || { echo "yt-dlp nicht gefunden"  >&2; exit 1; }

PLAYLIST_ID="$1"

# Mute-File für Ducking
MUTE_FILE="$HOME/.mute"
touch "$MUTE_FILE"

SPLASH_PNG="/home/retro/Bilder/LoadingScreen.png"
VOLUME="${2:-100}"

INVIDIOUS_BASE_URL="${INVIDIOUS_BASE_URL:-https://inv.nadeko.net}"
YOUTUBE_BASE_URL="https://www.youtube.com"
YT_DLP_PLAYER_CLIENT="${YT_DLP_PLAYER_CLIENT:-}"   # leer = yt-dlp Standard-Clients; optional z.B. "android" für geringere Auflösung
CURL_TIMEOUT_SECONDS=10
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
  fi
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
    response=$(curl -sf --max-time "${CURL_TIMEOUT_SECONDS}" "${INVIDIOUS_BASE_URL}/api/v1/playlists/${PLAYLIST_ID}?page=${page}")
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

load_playlist_from_youtube() {
  local ids
  ids=$(yt-dlp --flat-playlist --print "%(id)s" \
    "${YOUTUBE_BASE_URL}/playlist?list=${PLAYLIST_ID}" 2>/dev/null)
  [[ -z "$ids" ]] && return

  while IFS= read -r id; do
    URLS+=("${YOUTUBE_BASE_URL}/watch?v=${id}")
  done <<< "$ids"
}

# Splash sofort starten (instant Feedback)
start_splash

# Playlist einmal einlesen
URLS=()
load_playlist_from_invidious

if (( ${#URLS[@]} == 0 )); then
  echo "Invidious liefert keine Playlist -> Fallback auf YouTube" >&2
  load_playlist_from_youtube
fi

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
  api_response="$(curl -sf --max-time "${CURL_TIMEOUT_SECONDS}" "${INVIDIOUS_BASE_URL}/api/v1/videos/${video_id}?fields=adaptiveFormats&local=true")"

  video_url="$(printf '%s' "$api_response" \
    | jq -r '[.adaptiveFormats[] | select(.type | startswith("video/"))] | sort_by(.bitrate | tonumber) | last | .url // empty')"

  audio_url="$(printf '%s' "$api_response" \
    | jq -r '[.adaptiveFormats[] | select(.type | startswith("audio/"))] | sort_by(.bitrate | tonumber) | last | .url // empty')"

  # Fallback: Stream direkt via yt-dlp von YouTube auflösen
  if [[ -z "${video_url}" || -z "${audio_url}" ]]; then
    echo "Kein Invidious-Stream verfügbar -> Fallback auf YouTube" >&2
    ytdl_args=(-g -f "bestvideo+bestaudio/best")
    if [[ -n "${YT_DLP_PLAYER_CLIENT}" ]]; then
      ytdl_args+=(--extractor-args "youtube:player_client=${YT_DLP_PLAYER_CLIENT}")
    fi
    mapfile -t stream_urls < <(yt-dlp "${ytdl_args[@]}" "${YOUTUBE_BASE_URL}/watch?v=${video_id}" 2>/dev/null)
    video_url="${stream_urls[0]:-}"
    audio_url="${stream_urls[1]:-}"
  fi

  if [[ -z "${video_url}" ]]; then
    echo "Kein Stream verfügbar (Invidious & YouTube) -> neu shufflen" >&2
    continue
  fi

  mpv_common_args=(--fs --no-osc --osd-level=0 --keep-open=yes --volume="${VOLUME}" --title="${WINDOW_TITLE}")

  # Video starten, während der Splash noch sichtbar ist; startet während Splash läuft
  if [[ -n "${audio_url}" ]]; then
    mpv "${mpv_common_args[@]}" "$video_url" --audio-file="$audio_url" 2>/dev/null &
  else
    mpv "${mpv_common_args[@]}" "$video_url" 2>/dev/null &
  fi
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
