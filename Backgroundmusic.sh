#!/bin/bash
set -euo pipefail

MUSIC_DIR="$HOME/Musik"
# wird application.name
APP_NAME="Backgroundmusic"
# wird media.name
TITLE_NAME="Backgroundmusic"
# Playlistpfad
PLAYLIST_FILE="/tmp/backgroundmusic.m3u"
# Mute-File (gleiche Quelle wie Mute-bgm-and-splash.sh)
MUTE_FILE="$HOME/.mute"
SINK_INPUT_TIMEOUT=10    # Sekunden bis Subshell-Selbst-Timeout

if [[ ! -d "$MUSIC_DIR" ]]; then
  echo "MUSIC_DIR existiert nicht: $MUSIC_DIR" >&2
  exit 1
fi

# m3u-Datei erzeugen
find "$MUSIC_DIR" -type f \( -iname '*.mp3' -o -iname '*.flac' -o -iname '*.ogg' -o -iname '*.m4a' \) \
  -print > "$PLAYLIST_FILE"

if [[ ! -s "$PLAYLIST_FILE" ]]; then
  echo "Keine Audiodateien gefunden in: $MUSIC_DIR" >&2
  exit 1
fi

echo "Starte zufällige Endlos-Wiedergabe aus $MUSIC_DIR..."
echo "Playlist: $PLAYLIST_FILE"

# Wenn .mute beim Start aktiv ist: Sink-Input nach Registrierung sofort auf 0 setzen
if [[ -e "$MUTE_FILE" ]]; then
  (
    WATCHER_PID=$BASHPID
    (sleep "$SINK_INPUT_TIMEOUT"; kill "$WATCHER_PID") 2>/dev/null &
    TIMEOUT_PID=$!

    pactl subscribe 2>/dev/null | while IFS= read -r line; do
      case "$line" in
        *"'new' on sink-input"*)
          # Bis zu 3 Versuche – Sink-Input ggf. noch nicht vollständig registriert
          for _ in 1 2 3; do
            sink_id=$(pacmd list-sink-inputs 2>/dev/null | awk '
              /index:/                               { id = $2 }
              /application\.name = "'"$APP_NAME"'"/ { print id; exit }
            ')
            [[ -n "$sink_id" ]] && break
            sleep 0.05
          done
          if [[ -n "$sink_id" ]]; then
            pacmd set-sink-input-volume "$sink_id" 0 2>/dev/null || true
            kill "$TIMEOUT_PID" 2>/dev/null
            exit 0
          fi
          ;;
      esac
    done
  ) &
fi

exec mpv \
  --volume=50 \
  --no-video \
  --audio-client-name="$APP_NAME" \
  --title="$TITLE_NAME" \
  --quiet \
  --shuffle \
  --loop-playlist=inf \
  --idle=yes \
  --no-resume-playback \
  --playlist="$PLAYLIST_FILE"
