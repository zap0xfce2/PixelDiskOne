# PixelDiskOne

Die PixelDiskOne ist eine Spielekonsole welche als Medium 3,5" Disketten nutzt.

## Plan of Attack

- ein Service schreiben der den updater startet
- nach dem update wird der nfc-reader gestartet

```bash
while true; do ./updater.sh; sleep 60; done
```

```bash
python3 Main.py
```
