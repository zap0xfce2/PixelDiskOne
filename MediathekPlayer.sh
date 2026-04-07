#!/usr/bin/env bash
# Startet die Neuste Folge der query sonst gestern, ...
# Ignoriert die Version mit der Gebärdensprache
# Zeigt vorher sofort einen Splashscreen, bis das Video startet.
# Verwendung: MediathekPlayer.sh <QUERY> <KANAL> [--random]

set -euo pipefail

: "${1:?QUERY fehlt}"

command -v ffplay   >/dev/null || { echo "ffplay nicht gefunden"   >&2; exit 1; }
command -v feh      >/dev/null || { echo "feh nicht gefunden"      >&2; exit 1; }
command -v xdotool  >/dev/null || { echo "xdotool nicht gefunden"  >&2; exit 1; }
command -v curl     >/dev/null || { echo "curl nicht gefunden"     >&2; exit 1; }
command -v jq       >/dev/null || { echo "jq nicht gefunden"       >&2; exit 1; }

API_URL="https://mediathekviewweb.de/api/query"
SIZE=20
MAX_RANDOM_RETRIES=10

TOPIC_QUERY="$1"
CHANNEL_QUERY="${2:-KiKA}"

DEFAULT_SPLASH_PNG="/home/retro/Bilder/LoadingScreen.png"
RANDOM_MODE=0
if [[ "${3:-}" == "--random" ]]; then
  RANDOM_MODE=1
fi
SPLASH_PNG="$DEFAULT_SPLASH_PNG"

# Mute-File für Ducking
MUTE_FILE="$HOME/.mute"
touch "$MUTE_FILE"


WINDOW_TITLE="MediathekPlayer"

splash_pid=""
splash_mode=""  # "feh" | "ffplay"

cleanup() {
  rm -f "$MUTE_FILE" 2>/dev/null || true
  stop_splash
}
trap cleanup EXIT INT TERM QUIT

start_splash() {
  if [[ -n "${SPLASH_PNG}" && -f "${SPLASH_PNG}" ]]; then
    splash_mode="feh"
    feh --fullscreen --hide-pointer --auto-zoom "${SPLASH_PNG}" >/dev/null 2>&1 &
    splash_pid=$!
    return 0
  fi

  splash_mode="ffplay"
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
  splash_mode=""
}

pick_episode_before_date() {
  # Nimmt die neueste Folge deren Datum <= date_limit ist.
  # Bevorzugt: url_video_hd, sonst url_video
  # Ignoriert die Version mit der Gebärdensprache
  local date_limit="$1"

  jq -r --arg date_limit "$date_limit" '
    def day(ts):
      ts | tonumber | strftime("%Y%m%d");

    .result.results
    | map(select(.timestamp != null and (.timestamp|tonumber) > 0))
    | map(select((.title // "") | test("Gebärdensprache"; "i") | not))
    | map(. + {day: day(.timestamp)})
    | sort_by(.timestamp) | reverse
    | map(select(.day <= $date_limit))
    | .[0]
    | (.url_video_hd // .url_video // empty)
  '
}

# Splash sofort starten (instant Feedback)
start_splash

# Query: Channel + Topic (aus Args)
resp="$(
  curl -sS \
    -H 'content-type: application/json' \
    -H 'accept: application/json' \
    --data "$(jq -nc --arg t "$TOPIC_QUERY" --arg c "$CHANNEL_QUERY" --argjson size "$SIZE" '
      {
        queries: [
          { fields: ["topic"],   query: $t },
          { fields: ["channel"], query: $c }
        ],
        sortBy: "timestamp",
        sortOrder: "desc",
        future: false,
        offset: 0,
        size: $size
      }
    ')" \
    "$API_URL"
)"

mp4_url="$(printf '%s' "$resp" | pick_episode_before_date "$(date +%Y%m%d)")"

if (( RANDOM_MODE )); then
  total="$(printf '%s' "$resp" | jq '.result.queryInfo.resultCount')"

  mp4_url=""
  for _ in $(seq 1 "$MAX_RANDOM_RETRIES"); do
    random_offset=$(( (RANDOM * 32768 + RANDOM) % total ))
    mp4_url="$(
      curl -sS \
        -H 'content-type: application/json' \
        -H 'accept: application/json' \
        --data "$(jq -nc \
          --arg t "$TOPIC_QUERY" \
          --arg c "$CHANNEL_QUERY" \
          --argjson offset "$random_offset" '
          {
            queries: [
              { fields: ["topic"],   query: $t },
              { fields: ["channel"], query: $c }
            ],
            sortBy: "timestamp",
            sortOrder: "desc",
            future: false,
            offset: $offset,
            size: 1
          }
        ')" \
        "$API_URL" \
      | jq -r '
          .result.results[0]
          | select((.title // "") | test("Gebärdensprache"; "i") | not)
          | (.url_video_hd // .url_video // empty)
        '
    )"
    [[ -n "$mp4_url" ]] && break
  done
fi

if [[ -z "$mp4_url" ]]; then
  echo "Keine passende Folge gefunden für: $TOPIC_QUERY ($CHANNEL_QUERY)" >&2
  exit 1
fi

echo "Spiele: $mp4_url" >&2

# Video starten, während der Splash noch sichtbar ist (weniger Flackern)
ffplay -window_title "${WINDOW_TITLE}" -fs -loglevel quiet -nostats -hide_banner "$mp4_url" 2>/dev/null &
video_pid=$!

# Sobald das Video-Fenster existiert, Splash beenden
for _ in {1..50}; do
  xdotool search --name "^${WINDOW_TITLE}$" >/dev/null 2>&1 && break
  sleep 0.1
done

stop_splash

wait "$video_pid" 2>/dev/null || true
exit 0
