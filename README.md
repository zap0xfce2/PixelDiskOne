# PixelDiskOne

Die PixelDiskOne ist eine Spielekonsole welche als Medium 3,5" Disketten nutzt.

## Plan of Attack

- ein Service schreiben der den updater startet
- nach dem update wird der nfc-reader gestartet

```bash
while true; do ./updater.sh; sleep 60; done
```


```bash
ls -1 ~/snap/retroarch/current/.config/retroarch/cores/*.so | xargs -n 1 basename
```
