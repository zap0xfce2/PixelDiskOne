#!/usr/bin/env bash

# Secrets aus .env laden (gleiches Verzeichnis wie das Skript)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  source "$SCRIPT_DIR/.env"
fi

# Pflichtprüfung
if [[ -z "$EMBY_HOST" || -z "$API_KEY" ]]; then
  echo "Fehler: EMBY_HOST und API_KEY müssen in $SCRIPT_DIR/.env gesetzt sein."
  exit 1
fi

OPTIONS="-fs -loglevel quiet"
MUTE_FILE="$HOME/.mute"

# Hilfe-Text
show_help() {
  cat <<EOF
Nutzung: EmbyPlayer.sh <Serienname> [Optionen]

Optionen:
  -s <Staffeln>   Kommagetrennte Staffelnummern oder Bereiche (z.B. 1,2,3 oder 1-3 oder 1,3-5)
  -e [Nummer]     Episode per 1-basiertem Index; ohne Nummer = zufällig
  --unseen        Erste ungesehene/angefangene Episode abspielen
  --debug         Debug-Ausgaben aktivieren (RANDOM_ID, Ticks, Zeitmessung, HTTP-Status)
  -h, --help      Diese Hilfe anzeigen

Beispiele:
  ./EmbyPlayer.sh "Breaking Bad"
      Zufällige Episode aus allen Staffeln

  ./EmbyPlayer.sh "Breaking Bad" -s 1,2
      Zufällige Episode aus Staffel 1 oder 2

  ./EmbyPlayer.sh "Breaking Bad" -s 1-3
      Zufällige Episode aus Staffel 1, 2 oder 3

  ./EmbyPlayer.sh "Breaking Bad" -s 1,3-5
      Zufällige Episode aus Staffel 1, 3, 4 oder 5

  ./EmbyPlayer.sh "Breaking Bad" -e 5
      5. Episode (globaler Index)

  ./EmbyPlayer.sh "Breaking Bad" --unseen
      Nächste ungesehene oder angefangene Episode

  ./EmbyPlayer.sh "Breaking Bad" -s 1,2 --unseen
      Erste ungesehene Episode aus Staffel 1 oder 2
      (bei keiner ungesehenen: zufällige Auswahl)
EOF
}

# Serienname ist Pflichtargument (außer bei -h/--help als erstem Arg)
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  show_help
  exit 0
fi

SERIES_NAME="$1"
shift

if [[ -z "$SERIES_NAME" ]]; then
  echo "Nutzung: $0 <Serienname> [-s <Staffeln>] [-e [Episodennummer]] [--unseen]"
  exit 1
fi

# Defaults
MODE="episode"    # "episode" oder "season"
EPISODE_NUMBER="" # Optionaler 1-basierter Index
SEASONS=""        # Kommagetrennte Staffelnummern für -s
UNSEEN=false      # Erste ungesehene/angefangene Episode abspielen
DEBUG=false       # Debug-Ausgaben aktivieren

# Gibt Debug-Ausgabe auf stderr aus, wenn DEBUG=true
dbg() { [[ "$DEBUG" == true ]] && echo "[DEBUG] $*" >&2; }

# Führt curl aus und bricht mit Fehlermeldung ab wenn HTTP-Fehler oder Netzwerkfehler
curl_or_die() {
  local result
  result=$(curl -s --fail "$@") || {
    echo "Fehler: Emby nicht erreichbar oder ungültige Antwort (curl exit $?)." >&2
    exit 1
  }
  echo "$result"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s)
      MODE="season"
      SEASONS="$2"
      shift 2
      ;;
    -e)
      MODE="episode"
      # Nächstes Arg ist Episodennummer, falls vorhanden und keine Option
      if [[ -n "$2" && "$2" != -* ]]; then
        EPISODE_NUMBER="$2"
        shift 2
      else
        shift
      fi
      ;;
    --unseen)
      UNSEEN=true
      shift
      ;;
    --debug)
      DEBUG=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unbekannter Parameter: $1"
      echo "Nutzung: $0 <Serienname> [-s <Staffeln>] [-e [Episodennummer]] [--unseen]"
      exit 1
      ;;
  esac
done

# Validierung: --unseen und -e <Nummer> schließen sich gegenseitig aus
if [[ "$UNSEEN" == true && -n "$EPISODE_NUMBER" ]]; then
  echo "Fehler: --unseen kann nicht mit -e <Nummer> kombiniert werden."
  exit 1
fi

# USER_ID wird nur für --unseen benötigt
if [[ "$UNSEEN" == true && -z "$USER_ID" ]]; then
  echo "Fehler: USER_ID muss in $SCRIPT_DIR/.env gesetzt sein für --unseen."
  exit 1
fi

# 1. Serien-ID finden
SERIES_ID=$(curl_or_die "$EMBY_HOST/emby/Items?api_key=$API_KEY&IncludeItemTypes=Series&Recursive=true" \
  | jq -r --arg name "$SERIES_NAME" '.Items[] | select(.Name == $name) | .Id')

if [[ -z "$SERIES_ID" ]]; then
  echo "Serie '$SERIES_NAME' nicht gefunden."
  exit 1
fi

# Warnen wenn mehrere Serien gefunden, erste nehmen
SERIES_COUNT=$(echo "$SERIES_ID" | wc -l | tr -d ' ')
if [[ "$SERIES_COUNT" -gt 1 ]]; then
  echo "Warnung: $SERIES_COUNT Serien mit dem Namen '$SERIES_NAME' gefunden – nehme die erste."
  SERIES_ID=$(echo "$SERIES_ID" | head -n 1)
fi

# 2. Alle Episoden abrufen (ParentIndexNumber = Staffel, IndexNumber = Episode)
# Bei --unseen UserId anhängen → Antwort enthält dann UserData (Played, PlaybackPositionTicks)
if [[ "$UNSEEN" == true ]]; then
  ALL_EPISODES_JSON=$(curl_or_die "$EMBY_HOST/emby/Shows/$SERIES_ID/Episodes?api_key=$API_KEY&UserId=$USER_ID&Fields=RunTimeTicks")
else
  ALL_EPISODES_JSON=$(curl_or_die "$EMBY_HOST/emby/Shows/$SERIES_ID/Episodes?api_key=$API_KEY&Fields=RunTimeTicks")
fi

if [[ "$MODE" == "season" ]]; then
  # Staffeln als JSON-Array für jq aufbereiten (z.B. "1,2,3" → [1,2,3])
  # Bereiche wie "1-3" per seq expandieren, dann jq-Array bauen
  SEASON_ARRAY=$(echo "$SEASONS" | tr ',' '\n' | while IFS= read -r seg; do
    if [[ "$seg" == *-* ]]; then
      seq "${seg%-*}" "${seg#*-}"
    else
      echo "$seg"
    fi
  done | jq -R 'tonumber' | jq -s '.')
  EPISODES=$(echo "$ALL_EPISODES_JSON" \
    | jq -r --argjson s "$SEASON_ARRAY" \
      '.Items[] | select(.ParentIndexNumber as $n | $s | index($n) != null) | .Id')
else
  # Episode-Modus: alle IDs
  EPISODES=$(echo "$ALL_EPISODES_JSON" | jq -r '.Items[].Id')
fi

if [[ -z "$EPISODES" ]]; then
  echo "Keine Episoden gefunden für '$SERIES_NAME'${SEASONS:+ in Staffel(n) $SEASONS}."
  exit 1
fi

# 3. Episode wählen
if [[ "$UNSEEN" == true ]]; then
  # Priorität: angefangene (PlaybackPositionTicks > 0) vor ungesehenen,
  # jeweils sortiert nach Staffel und Episodennummer
  if [[ "$MODE" == "season" ]]; then
    UNSEEN_ID=$(echo "$ALL_EPISODES_JSON" | jq -r --argjson s "$SEASON_ARRAY" '
      [.Items[]
        | select(.UserData.Played == false)
        | select(.ParentIndexNumber as $n | $s | index($n) != null)]
      | sort_by([
          (.UserData.PlaybackPositionTicks > 0 | if . then 0 else 1 end),
          .ParentIndexNumber,
          .IndexNumber
        ])
      | .[0].Id // empty
    ')
  else
    UNSEEN_ID=$(echo "$ALL_EPISODES_JSON" | jq -r '
      [.Items[] | select(.UserData.Played == false)]
      | sort_by([
          (.UserData.PlaybackPositionTicks > 0 | if . then 0 else 1 end),
          .ParentIndexNumber,
          .IndexNumber
        ])
      | .[0].Id // empty
    ')
  fi

  if [[ -z "$UNSEEN_ID" ]]; then
    # Fallback: alle Episoden gesehen → zufällige Auswahl
    echo "Hinweis: Alle Episoden gesehen – wähle zufällig."
    RANDOM_ID=$(echo "$EPISODES" | shuf -n 1)
  else
    RANDOM_ID="$UNSEEN_ID"
  fi
elif [[ -n "$EPISODE_NUMBER" ]]; then
  # N-te Episode (1-basierter Index) wählen
  RANDOM_ID=$(echo "$EPISODES" | sed -n "${EPISODE_NUMBER}p")
else
  # Zufällige Episode
  RANDOM_ID=$(echo "$EPISODES" | shuf -n 1)
fi

if [[ -z "$RANDOM_ID" ]]; then
  echo "Konnte Episode nicht auswählen."
  exit 1
fi

# 4. Stream-URL bauen
STREAM_URL="$EMBY_HOST/emby/Videos/$RANDOM_ID/stream?static=true&api_key=$API_KEY"

# Episodendauer aus bereits abgerufenen Episodendaten extrahieren (nur bei --unseen)
DURATION_SEC=0
THRESHOLD=0
if [[ "$UNSEEN" == true ]]; then
  RUN_TIME_TICKS=$(echo "$ALL_EPISODES_JSON" \
    | jq -r --arg id "$RANDOM_ID" '.Items[] | select(.Id == $id) | .RunTimeTicks // 0')
  DURATION_SEC=$(( RUN_TIME_TICKS / 10000000 ))
  dbg "RANDOM_ID=$RANDOM_ID"
  dbg "RUN_TIME_TICKS_RAW=$(echo "$ALL_EPISODES_JSON" | jq -r --arg id "$RANDOM_ID" '.Items[] | select(.Id == $id) | .RunTimeTicks')"
  dbg "DURATION_SEC=$DURATION_SEC"

  # Schwelle VOR ffplay berechnen (wird im trap-Handler benötigt)
  if [[ "$DURATION_SEC" -gt 0 ]]; then
    THRESHOLD=$(( DURATION_SEC * 80 / 100 ))
  else
    THRESHOLD=60
  fi
fi

# Episode als gesehen markieren wenn ≥80% geschaut (nur bei --unseen)
# Feuert bei normalem Ende UND bei Script-Kill (Ctrl+C, kill) — nicht bei kill -9
_emby_mark_watched() {
  trap - EXIT INT TERM QUIT          # Einmalig ausführen (Doppel-Schutz)
  rm -f "$MUTE_FILE" 2>/dev/null || true
  [[ "$UNSEEN" != true ]] && return  # Nur relevant bei --unseen

  local elapsed=$(( $(date +%s) - PLAY_START ))
  dbg "PLAY_ELAPSED=${elapsed}s  THRESHOLD=${THRESHOLD}s  DURATION_SEC=${DURATION_SEC}s"

  if [[ "$elapsed" -ge "$THRESHOLD" ]]; then
    if [[ "$DEBUG" == true ]]; then
      # Im Debug-Modus HTTP-Statuscode mitloggen
      HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        "$EMBY_HOST/emby/Users/$USER_ID/PlayedItems/$RANDOM_ID?api_key=$API_KEY")
      dbg "POST PlayedItems → HTTP $HTTP_STATUS"
    else
      curl -s -X POST "$EMBY_HOST/emby/Users/$USER_ID/PlayedItems/$RANDOM_ID?api_key=$API_KEY" > /dev/null
    fi
  fi
}
trap '_emby_mark_watched' EXIT INT TERM QUIT

# 5. Abspielen und Laufzeit messen
touch "$MUTE_FILE"
PLAY_START=$(date +%s)
ffplay $OPTIONS "$STREAM_URL"
