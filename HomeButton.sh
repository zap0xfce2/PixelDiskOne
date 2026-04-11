#!/usr/bin/env bash

# Das script sorgt dafür das der HomeButton auf der
# Tastatur nur benutzt werden kann wenn schon eine Brave instanz läuft

# Secrets aus .env laden
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  source "$SCRIPT_DIR/.env"
fi

URL="${EMBY_HOST}/web/index.html#!/home"
if pgrep -f 'Brave' >/dev/null; then
  brave-browser --kiosk "$URL"
fi
