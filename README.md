# PixelDiskOne

Die PixelDiskOne ist eine Spielekonsole welche als Medium 3,5" Disketten nutzt. Das Diskettenlaufwerk wurde mit einem NFC-Reader modifiziert.

Auf dem Gerät läuft Ubuntu 22.04.5 LTS es wird ein ACR122U als NFC-Reader verwendet. Der NFC-Reader wurde wie unter https://www.jamesridgway.co.uk/install-acr122u-drivers-on-linux-mint-and-kubuntu beschrieben eingerichtet.

Um die Zeit für Kinder zu begrenzen wurde Timekpr-nExT installiert. Eine Anleitung findet sich unter: https://mjasnik.gitlab.io/timekpr-next/#installation

## Neues Spiel hinzufügen

### Core ermitteln

```bash
ls -1 ~/snap/retroarch/current/.config/retroarch/cores/*.so | xargs -n 1 basename
```

### Datenbankeintrag erstellen

Erstelle nun einen Datenbankeintrag in die Datei `NFC-Tags.db`.
Ein Beispieleintrag für das NES sieht so aus:

```text
retroarch -L "mesen_libretro.so" "/home/retro/Roms/rom.nes"
```

Hier könnte man auch andere Emulatoren oder Steam Spiele hinzufügen um diese zu starten.

### NFC-Tag erstellen

Nun schreibt man die DatensatzID auf das NFC-Tag in einen Texteintrag. Hierfür kann man die App "NFC Tools" auf seinem Handy verwenden.
