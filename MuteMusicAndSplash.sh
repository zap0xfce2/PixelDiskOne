#!/bin/bash
set -euo pipefail

# =========================
# Konfiguration
# =========================
# Prozesse, die das Ducking auslösen (exakte Namen für pgrep -x)
TARGET_PROCS=("retroarch" "brave-browser" "firefox" "xfce4-terminal" "steam" "zelda3")

# Optionales Mute-File im Home-Verzeichnis
MUTE_FILE="$HOME/.mute"

# Sink-Input application.names die geduckt werden sollen
DUCK_NAMES=("Backgroundmusic" "PixelDiskOne-Splash")

DUCK_PERCENT=0     # Lautstärke bei aktivem Trigger (in %)
FADE_DOWN_MS=100   # Fade-Down Gesamtdauer in Millisekunden
FADE_UP_MS=3000    # Fade-Up Gesamtdauer in Millisekunden
DUCK_VOL=$(( DUCK_PERCENT * 655 ))   # Pre-cached Pulse-Wert

# FIFO für event-basierte Erkennung
FIFO="/tmp/mute-bgm-fifo"
# Adaptiver Fallback-Timeout (Sekunden) – Events kommen sofort via FIFO
FALLBACK_TIMEOUT_IDLE=2    # kein Trigger aktiv, Events decken alles ab
FALLBACK_TIMEOUT_ACTIVE=0.3  # Trigger aktiv, moderates Polling für Trigger-Ende

# =========================
# Helfer
# =========================

# prüft, ob einer der Trigger-Prozesse läuft (Zombie-Prozesse werden ignoriert)
any_trigger_proc() {
  for p in "${TARGET_PROCS[@]}"; do
    while IFS= read -r pid; do
      state=$(awk '/^State:/{print $2; exit}' /proc/"$pid"/status 2>/dev/null) || true
      [[ -n "$state" && "$state" != "Z" ]] && return 0
    done < <(pgrep -x "$p" 2>/dev/null)
  done
  return 1
}

# prüft, ob Ducking durch Prozesse, Sink-Inputs ODER Mute-File aktiv ist
ducking_active() {
  [[ -e "$MUTE_FILE" ]] && return 0
  is_target_sink_input && return 0
  any_trigger_proc && return 0
  return 1
}

# listet Sink-Input-IDs anhand von DUCK_NAMES (application.name Matching)
list_duck_sink_inputs() {
  local names_pattern
  names_pattern=$(printf '|%s' "${DUCK_NAMES[@]}")
  names_pattern="${names_pattern:1}"  # führendes | entfernen
  pacmd list-sink-inputs | awk -v pattern="$names_pattern" '
    /index:/ {id=$2}
    /application.name = / {
      gsub(/"/, "", $NF)
      if ($NF ~ "^(" pattern ")$") { if (id!="") print id }
    }
  ' | sort -u
}

# Merker für bereits geduckte Sink-Inputs (damit wir nicht dauernd pacmd feuern)
declare -A SEEN_DUCK_IDS=()

# setzt Lautstärke nur für NEUE Duck-Streams (IDs, die wir noch nicht gesehen haben)
set_vol_new_only() {
  local vol="$1"
  local id
  while read -r id; do
    [[ -z "$id" ]] && continue
    if [[ -z "${SEEN_DUCK_IDS[$id]+x}" ]]; then
      pacmd set-sink-input-volume "$id" "$vol" 2>/dev/null || true
      SEEN_DUCK_IDS[$id]=1
    fi
  done < <(list_duck_sink_inputs)
}

# Cache resetten (z.B. beim Wechsel von aktiv <-> inaktiv), damit wir neu entdecken können
reset_seen_cache() {
  SEEN_DUCK_IDS=()
}

# setzt Lautstärke aller Duck-Streams auf Pulse-Wert (0..65536)
set_vol_all() {
  local vol="$1"
  local id
  while read -r id; do
    [[ -n "$id" ]] && pacmd set-sink-input-volume "$id" "$vol" 2>/dev/null || true
  done < <(list_duck_sink_inputs)
}

# Prozent -> Pulse-Wert
pct_to_pulse() {
  local pct="$1"
  # 100% ≈ 65536 → 1% ≈ 655
  echo $(( pct * 655 ))
}

# sanftes Fading aller Duck-Streams von start% nach end% über total_ms
# interruptible=1: prüft ducking_active() vor jedem Schritt; return 1 wenn abgebrochen
fade_all_pct() {
  local start_pct="$1" end_pct="$2" total_ms="$3" interruptible="${4:-0}"
  local steps=10
  local sleep_s
  sleep_s=$(awk -v ms="$total_ms" -v st="$steps" 'BEGIN{printf "%.3f", (ms/1000)/st}')
  local i v pct
  for i in $(seq 0 $steps); do
    if [[ "$interruptible" -eq 1 ]] && ducking_active; then
      return 1  # Fade-Up abgebrochen – Ducking wieder aktiv
    fi
    pct=$(awk -v a="$start_pct" -v b="$end_pct" -v i="$i" -v n="$steps" 'BEGIN{printf "%.0f", a + (b-a)*i/n}')
    v=$(pct_to_pulse "$pct")
    set_vol_all "$v"
    sleep "$sleep_s"
  done
  return 0
}

# prüft ob ein TARGET_PROC als Sink-Input registriert ist
is_target_sink_input() {
  local binaries
  binaries=$(pacmd list-sink-inputs 2>/dev/null | awk -F'"' '/application.process.binary/ {print $2}')
  [[ -z "$binaries" ]] && return 1
  local p
  for p in "${TARGET_PROCS[@]}"; do
    echo "$binaries" | grep -qxF "$p" && return 0
  done
  return 1
}

# =========================
# FIFO + Hintergrund-Watcher
# =========================

# Aufräumen bei EXIT
BG_PIDS=()
cleanup() {
  for pid in "${BG_PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  exec 3>&- 2>/dev/null || true
  rm -f "$FIFO"
}
trap cleanup EXIT

# FIFO erstellen
rm -f "$FIFO"
mkfifo "$FIFO"
exec 3<>"$FIFO"   # Persistenter FD: verhindert open()-Blockierung auf FIFO

# Watcher 1: PulseAudio Sink-Input Events
#   Erkennt wenn ein Programm einen Audio-Stream öffnet oder schließt
(
  while true; do
    pactl subscribe 2>/dev/null | while IFS= read -r line; do
      case "$line" in
        *"'new' on sink-input"*)
          idx="${line##*#}"
          echo "DUCK_CHECK:$idx" > "$FIFO" ;;
        *"'remove' on sink-input"*)
          echo "DUCK_CHECK" > "$FIFO" ;;
      esac
    done
    # pactl subscribe hat sich beendet (PulseAudio Neustart?) → kurz warten, erneut versuchen
    sleep 2
  done
) &
BG_PIDS+=($!)

# Watcher 2: inotifywait auf ~/.mute (CREATE/DELETE)
if command -v inotifywait >/dev/null 2>&1; then
  (
    while true; do
      inotifywait -m -e create -e delete --include '\.mute$' "$HOME" 2>/dev/null | while IFS= read -r _; do
        echo "MUTE_FILE_CHANGED" > "$FIFO"
      done
      # inotifywait beendet → kurz warten, erneut versuchen
      sleep 2
    done
  ) &
  BG_PIDS+=($!)
else
  echo "WARNUNG: inotifywait nicht gefunden – ~/.mute wird nur per pgrep-Fallback geprüft"
fi

# =========================
# Ablauf
# =========================

echo "Trigger-Prozesse: ${TARGET_PROCS[*]}"
echo "Mute-File: $MUTE_FILE (existiert = Ducking aktiv)"
echo "Ducking: ${DUCK_PERCENT}% bei aktivem Trigger/Mute-File, Fade-Up zurück auf 100%."
echo "Duck-Names: ${DUCK_NAMES[*]}"
echo "Event-basiert: pactl subscribe + inotifywait + pgrep-Fallback (idle=${FALLBACK_TIMEOUT_IDLE}s/aktiv=${FALLBACK_TIMEOUT_ACTIVE}s)"

# Merker: aktueller Zustand (0=kein Trigger, 1=Trigger aktiv)
state=0

while true; do
  # Adaptiver Timeout: im Idle länger warten, bei aktivem Ducking kürzer
  if [[ "$state" -eq 0 ]]; then
    timeout="$FALLBACK_TIMEOUT_IDLE"
  else
    timeout="$FALLBACK_TIMEOUT_ACTIVE"
  fi
  event=""
  read -t "$timeout" event <&3 2>/dev/null || true

  # Aggressive Fast-Path: neuen Sink-Input sofort blind muten (~5ms statt ~20ms)
  # Prüfung ob Duck-Name erfolgt danach über set_vol_new_only()
  if [[ "$state" -eq 1 && "$event" == DUCK_CHECK:* ]]; then
    pacmd set-sink-input-volume "${event#DUCK_CHECK:}" "$DUCK_VOL" 2>/dev/null || true
  fi

  if ducking_active; then
    if [[ "$state" -eq 0 ]]; then
      # Übergang: kein Trigger -> Trigger/Mute aktiv -> Fade-Down
      echo "Trigger oder $MUTE_FILE aktiv → Duck auf ${DUCK_PERCENT}%"
      fade_all_pct 100 "$DUCK_PERCENT" "$FADE_DOWN_MS"
      # Nach dem Fade: Ziel-Level setzen (und Cache füllen)
      set_vol_all "$DUCK_VOL"
      reset_seen_cache
      set_vol_new_only "$DUCK_VOL"
      state=1
    else
      # Trigger/Mute bleibt aktiv → nur NEUE Duck-Streams ducken (CPU freundlich)
      set_vol_new_only "$DUCK_VOL"
    fi
  else
    if [[ "$state" -eq 1 ]]; then
      # Übergang: Trigger/Mute -> nichts aktiv -> Fade-Up
      echo "Kein Trigger und $MUTE_FILE weg → Fade auf 100%"
      if fade_all_pct "$DUCK_PERCENT" 100 "$FADE_UP_MS" 1; then
        # Fade vollständig abgeschlossen
        reset_seen_cache
        state=0
      else
        # Fade abgebrochen – Ducking wieder aktiv → sofort auf Duck-Lautstärke zurück
        echo "Fade-Up abgebrochen – Ducking wieder aktiv"
        set_vol_all "$DUCK_VOL"
        reset_seen_cache
        set_vol_new_only "$DUCK_VOL"
        # state bleibt 1
      fi
    fi
    # Ruhemodus: nichts tun – read wartet auf nächstes Event/Timeout
  fi
done
