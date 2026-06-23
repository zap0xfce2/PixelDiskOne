#!/usr/bin/env bash
#
# Workaround in diesem Script:
#   Unbind + Rebind des PCI-Treibers fuer GENAU diesen Host-Controller
#   (0000:c6:00.3). Das resettet den USB4-Router komplett (statt nur das
#   angeschlossene Geraet) - die softwareseitige Alternative zum
#   Stromunterbrechen des PCs.
#
# Nutzung:
#   sudo ./NfcReaderReset.sh
#
#   Schreibt ein Log nach /tmp/nfc-reader-reset-<timestamp>.log - dieses
#   Log kann bei wiederholten Problemen direkt zur weiteren Diagnose
#   herangezogen werden.

set -euo pipefail

readonly PCI_ADDRESS="0000:c6:00.3"
readonly USB_VENDOR_ID="072f"
readonly USB_PRODUCT_ID="2200"
readonly UNBIND_REBIND_DELAY_SECS=2
readonly LOG_FILE="/tmp/nfc-reader-reset-$(date +%Y%m%d-%H%M%S).log"

log() {
    echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

check_running_as_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Bitte mit sudo ausfuehren: sudo $0" >&2
        exit 1
    fi
}

log_reader_status() {
    local label="$1"
    log "Status ${label}:"
    if lsusb -d "${USB_VENDOR_ID}:${USB_PRODUCT_ID}" >>"$LOG_FILE" 2>&1; then
        lsusb -d "${USB_VENDOR_ID}:${USB_PRODUCT_ID}"
    else
        log "Reader nicht sichtbar in lsusb."
    fi
}

reset_usb4_controller() {
    log "Unbind PCI-Geraet ${PCI_ADDRESS} (xhci_hcd) ..."
    echo -n "$PCI_ADDRESS" > /sys/bus/pci/drivers/xhci_hcd/unbind

    sleep "$UNBIND_REBIND_DELAY_SECS"

    log "Rebind PCI-Geraet ${PCI_ADDRESS} ..."
    echo -n "$PCI_ADDRESS" > /sys/bus/pci/drivers/xhci_hcd/bind

    sleep "$UNBIND_REBIND_DELAY_SECS"
}

check_running_as_root

log "=== NFC-Reader USB-Reset gestartet ==="
log_reader_status "vorher"

reset_usb4_controller

log_reader_status "nachher"

if lsusb -d "${USB_VENDOR_ID}:${USB_PRODUCT_ID}" >/dev/null 2>&1; then
    log "Reader wieder sichtbar - Reset erfolgreich."
else
    log "Reader weiterhin nicht sichtbar - Reset hat NICHT geholfen."
fi

log "=== Fertig. Log: ${LOG_FILE} ==="
