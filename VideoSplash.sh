#!/bin/bash
set -euo pipefail

# =========================
# Konfiguration
# =========================
APP_NAME="PixelDiskOne-Splash"
VIDEO_PATH="/home/retro/Videos/PixelDiskOne-Splash.mp4"
# Mute-File (gleiche Quelle wie Mute-bgm-and-splash.sh)
MUTE_FILE="$HOME/.mute"
SINK_INPUT_TIMEOUT=10    # Sekunden bis Subshell-Selbst-Timeout

if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "VIDEO_PATH existiert nicht: $VIDEO_PATH" >&2
  exit 1
fi

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

mpv --wid=$(xdotool search --onlyvisible --class xfdesktop) \
    --no-border --fullscreen --panscan=1 \
    --no-osd-bar --osd-level=0 --no-osc \
    --keep-open=always --no-stop-screensaver \
    --input-default-bindings=no \
    --input-vo-keyboard=no \
    --volume=95 \
    --title="$APP_NAME" \
    --audio-client-name="$APP_NAME" \
    "$VIDEO_PATH"
