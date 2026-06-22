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
command -v yt-dlp  >/dev/null || { echo "yt-dlp nicht gefunden"  >&2; exit 1; }
command -v deno    >/dev/null || { echo "deno nicht gefunden"    >&2; exit 1; }

PLAYLIST_ID="$1"

# Mute-File für Ducking
MUTE_FILE="$HOME/.mute"
touch "$MUTE_FILE"

SPLASH_PNG="/home/retro/Bilder/LoadingScreen.png"
VOLUME="${2:-100}"

INVIDIOUS_BASE_URL="${INVIDIOUS_BASE_URL:-https://inv.nadeko.net}"
WINDOW_TITLE="YoutubePlayer"

splash_pid=""
ytdlp_pid=""
ytdlp_outfile=""

cleanup() {
  rm -f "$MUTE_FILE" 2>/dev/null || true
  stop_splash
  stop_ytdlp_resolve
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

stop_ytdlp_resolve() {
  if [[ -n "${ytdlp_pid}" ]] && kill -0 "${ytdlp_pid}" 2>/dev/null; then
    kill "${ytdlp_pid}" 2>/dev/null || true
    wait "${ytdlp_pid}" 2>/dev/null || true
  fi
  ytdlp_pid=""
  rm -f "${ytdlp_outfile}" 2>/dev/null || true
  ytdlp_outfile=""
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
  if (( ${#URLS[@]} > 0 )); then
    mapfile -t URLS < <(printf '%s\n' "${URLS[@]}" | awk '!seen[$0]++')
  fi
}

# Fallback wenn Invidious keine Playlist-Videos liefert (z.B. leeres .videos-Array).
load_playlist_from_ytdlp() {
  while IFS= read -r id; do
    URLS+=("https://www.youtube.com/watch?v=${id}")
  done < <(yt-dlp --flat-playlist --print "%(id)s" "https://www.youtube.com/playlist?list=${PLAYLIST_ID}" 2>/dev/null)
}

# Kopfstart-Fallback: yt-dlp parallel zur Invidious-Anfrage starten, damit dessen
# Anlaufzeit (inkl. deno-Start für den JS-Challenge-Solver) bei einem Invidious-Fehlschlag
# (z.B. HTTP 403 bei adaptiveFormats) nicht erst sequenziell anfällt.
start_ytdlp_resolve_async() {
  local id="$1"
  ytdlp_outfile="$(mktemp)"
  yt-dlp -f "bestvideo+bestaudio" -g --remote-components ejs:github "https://www.youtube.com/watch?v=${id}" >"${ytdlp_outfile}" 2>/dev/null &
  ytdlp_pid=$!
}

# Wartet auf das bereits laufende yt-dlp aus start_ytdlp_resolve_async und setzt
# video_url/audio_url, oder lässt sie leer wenn yt-dlp ebenfalls scheitert.
collect_ytdlp_resolve() {
  wait "${ytdlp_pid}" 2>/dev/null
  video_url="$(sed -n '1p' "${ytdlp_outfile}")"
  audio_url="$(sed -n '2p' "${ytdlp_outfile}")"
  rm -f "${ytdlp_outfile}"
  ytdlp_pid=""
  ytdlp_outfile=""
}

# Splash sofort starten (instant Feedback)
start_splash

# Playlist einmal einlesen
URLS=()
load_playlist_from_invidious

if (( ${#URLS[@]} == 0 )); then
  echo "Invidious liefert keine Playlist-Videos -> Fallback auf yt-dlp" >&2
  load_playlist_from_ytdlp
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

  # yt-dlp-Fallback per Kopfstart sofort parallel anstoßen, falls Invidious scheitert
  start_ytdlp_resolve_async "$video_id"

  api_response="$(curl -sf "${INVIDIOUS_BASE_URL}/api/v1/videos/${video_id}?fields=adaptiveFormats&local=true")"

  video_url="$(printf '%s' "$api_response" \
    | jq -r '[.adaptiveFormats[] | select(.type | startswith("video/"))] | sort_by(.bitrate | tonumber) | last | .url // empty')"

  audio_url="$(printf '%s' "$api_response" \
    | jq -r '[.adaptiveFormats[] | select(.type | startswith("audio/"))] | sort_by(.bitrate | tonumber) | last | .url // empty')"

  if [[ -n "${video_url}" && -n "${audio_url}" ]]; then
    stop_ytdlp_resolve
  else
    echo "Invidious liefert keine Stream-URLs -> Fallback auf (bereits laufendes) yt-dlp" >&2
    collect_ytdlp_resolve
  fi

  if [[ -z "${video_url}" || -z "${audio_url}" ]]; then
    echo "Keine Stream-URLs gefunden -> neu shufflen" >&2
    continue
  fi

  # Video starten, während der Splash noch sichtbar ist; startet während Splash läuft
  mpv --fs --no-osc --osd-level=0 --keep-open=yes --volume="${VOLUME}" --title="${WINDOW_TITLE}" "$video_url" --audio-file="$audio_url" 2>/dev/null &
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
