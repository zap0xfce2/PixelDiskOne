#!/usr/bin/env bash

# Das script sorgt dafür das der HomeButton auf der
# Tastatur nur benutzt werden kann wenn schon eine Brave instanz läuft

URL='https://emby.zpx.sh/web/index.html#!/home'
if pgrep -f 'Brave' >/dev/null; then
  brave-browser --kiosk "$URL"
fi
