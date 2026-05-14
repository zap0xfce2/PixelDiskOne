#!/usr/bin/env bash
set -uo pipefail

# --- Farben ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { printf "${CYAN}[INFO]${NC}  %b\n" "$*"; }
success() { printf "${GREEN}[OK]${NC}    %b\n" "$*"; }
warn()    { printf "${YELLOW}[WARN]${NC}  %b\n" "$*"; }
error()   { printf "${RED}[FEHLER]${NC} %b\n" "$*" >&2; }

# --- Usage ---
usage() {
    printf "%b\n" "${BOLD}LoudNorm.sh${NC} – MP3-Lautstärke analysieren & normalisieren"
    printf "\n"
    printf "%b\n" "${BOLD}Nutzung:${NC}"
    printf "  ./LoudNorm.sh check            Lautstärke aller MP3s analysieren (EBU R128 + volumedetect)\n"
    printf "  ./LoudNorm.sh norm             Normalisierung auf -25 LUFS (Two-Pass loudnorm)\n"
    printf "  ./LoudNorm.sh norm -l <LUFS>   Normalisierung auf gewünschten LUFS-Wert (z.B. -18)\n"
    printf "\n"
    printf "%b\n" "${BOLD}Optionen:${NC}"
    printf "  -l <LUFS>   Ziel-Lautstärke in LUFS (Default: -25)\n"
    printf "  --help       Diese Hilfe anzeigen\n"
    printf "\n"
    printf "%b\n" "${BOLD}Beispiele:${NC}"
    printf "  ./LoudNorm.sh check\n"
    printf "  ./LoudNorm.sh norm\n"
    printf "  ./LoudNorm.sh norm -l -18\n"
}

# --- Prüfungen ---
check_deps() {
    if ! command -v ffmpeg &>/dev/null; then
        error "ffmpeg nicht gefunden. Bitte installieren: brew install ffmpeg"
        exit 1
    fi
}

get_mp3s() {
    shopt -s nullglob
    MP3S=(*.mp3)
    shopt -u nullglob
    if [[ ${#MP3S[@]} -eq 0 ]]; then
        error "Keine MP3-Dateien im aktuellen Ordner gefunden."
        exit 1
    fi
}

# --- Check-Modus ---
do_check() {
    get_mp3s
    local total=${#MP3S[@]}

    info "Analysiere $total MP3-Datei(en) ..."
    printf "\n"

    # EBU R128
    printf "%b\n" "${BOLD}── EBU R128 ──${NC}"
    local i=0
    for f in "${MP3S[@]}"; do
        ((i++))
        printf "\n%b\n" "${YELLOW}[$i/$total]${NC} ${BOLD}$f${NC}"
        ffmpeg -hide_banner -nostats -i "$f" \
            -filter_complex ebur128=framelog=verbose -f null - 2>&1 \
            | awk '/I:/{print "  " $0}' || true
    done

    # volumedetect
    printf "\n%b\n" "${BOLD}── Volume Detect ──${NC}"
    i=0
    for f in "${MP3S[@]}"; do
        ((i++))
        printf "\n%b\n" "${YELLOW}[$i/$total]${NC} ${BOLD}$f${NC}"
        ffmpeg -hide_banner -nostats -i "$f" \
            -af volumedetect -f null - 2>&1 \
            | awk '/mean_volume|max_volume/{print "  " $0}' || true
    done

    printf "\n"
    success "Analyse abgeschlossen – $total Datei(en) geprüft."
}

# --- Norm-Modus ---
do_norm() {
    local target_i="$1"
    get_mp3s
    local total=${#MP3S[@]}

    info "Normalisierung auf ${BOLD}${target_i} LUFS${NC} (TP=-1.5, LRA=11)"
    info "$total MP3-Datei(en) gefunden."
    printf "\n"

    mkdir -p norm

    # Pass 1: Analyse
    printf "%b\n" "${BOLD}── Pass 1: Analyse ──${NC}"
    local i=0
    for f in "${MP3S[@]}"; do
        ((i++))
        printf "%b\n" "${YELLOW}[$i/$total]${NC} Analysiere ${BOLD}$f${NC} ..."
        ffmpeg -hide_banner -nostats -i "$f" \
            -af "loudnorm=I=${target_i}:TP=-1.5:LRA=11:print_format=json" \
            -f null - 2> "norm/${f%.mp3}.json"
    done
    success "Pass 1 abgeschlossen."
    printf "\n"

    # Pass 2: Normalisierung
    printf "%b\n" "${BOLD}── Pass 2: Normalisierung ──${NC}"
    i=0
    local ok=0
    for f in "${MP3S[@]}"; do
        ((i++))
        local j="norm/${f%.mp3}.json"

        local I TP LRA TH OFF
        I=$(awk -F': ' '/"input_i"/{gsub(/[",]/,"",$2); print $2}' "$j")
        TP=$(awk -F': ' '/"input_tp"/{gsub(/[",]/,"",$2); print $2}' "$j")
        LRA=$(awk -F': ' '/"input_lra"/{gsub(/[",]/,"",$2); print $2}' "$j")
        TH=$(awk -F': ' '/"input_thresh"/{gsub(/[",]/,"",$2); print $2}' "$j")
        OFF=$(awk -F': ' '/"target_offset"/{gsub(/[",]/,"",$2); print $2}' "$j")

        printf "%b\n" "${YELLOW}[$i/$total]${NC} Normalisiere ${BOLD}$f${NC} ..."

        if ffmpeg -hide_banner -nostats -i "$f" \
            -af "loudnorm=I=${target_i}:TP=-1.5:LRA=11:measured_I=$I:measured_TP=$TP:measured_LRA=$LRA:measured_thresh=$TH:offset=$OFF:linear=true:print_format=summary" \
            -c:a libmp3lame -q:a 2 "norm/${f%.mp3}.norm.mp3" 2>/dev/null; then
            ((ok++))
        else
            error "Fehler bei $f"
        fi
    done

    # Cleanup: JSON-Dateien entfernen
    shopt -s nullglob
    local json_files=(norm/*.json)
    shopt -u nullglob
    local json_count=${#json_files[@]}
    if [[ $json_count -gt 0 ]]; then
        rm -f norm/*.json
        info "$json_count JSON-Zwischendatei(en) aufgeräumt."
    fi

    printf "\n"
    success "Fertig – $ok/$total Datei(en) normalisiert nach norm/"
}

# --- Main ---
check_deps

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

MODE="$1"
shift

case "$MODE" in
    check)
        do_check
        ;;
    norm)
        TARGET_LUFS="-25"
        while [[ $# -gt 0 ]]; do
            case "$1" in
                -l)
                    if [[ -z "${2:-}" ]]; then
                        error "Option -l erwartet einen LUFS-Wert (z.B. -18)"
                        exit 1
                    fi
                    TARGET_LUFS="$2"
                    shift 2
                    ;;
                *)
                    error "Unbekannte Option: $1"
                    usage
                    exit 1
                    ;;
            esac
        done
        do_norm "$TARGET_LUFS"
        ;;
    --help|-h)
        usage
        ;;
    *)
        error "Unbekannter Modus: $MODE"
        usage
        exit 1
        ;;
esac
