# PixelDiskOne

Die PixelDiskOne ist eine Spielekonsole welche als Medium 3,5" Disketten nutzt. Das Diskettenlaufwerk wurde mit einem NFC-Reader modifiziert.

Auf dem Gerät läuft Ubuntu 22.04.5 LTS es wird ein ACR122U als NFC-Reader verwendet. Der NFC-Reader wurde wie unter https://www.jamesridgway.co.uk/install-acr122u-drivers-on-linux-mint-and-kubuntu beschrieben eingerichtet.

Um die Zeit für Kinder zu begrenzen wurde Timekpr-nExT installiert. Eine Anleitung findet sich unter: https://mjasnik.gitlab.io/timekpr-next/#installation

## Neues Spiel hinzufügen

### Core ermitteln

```bash
ls -1 ~/.config/retroarch/cores/*.so | xargs -n 1 basename
```

### Datenbankeintrag erstellen

Erstelle nun einen Datenbankeintrag in die SQLite Datei `NFC-Tags.db`.
Ein Beispieleintrag für das NES sieht so aus:

```text
retroarch -L "mesen_libretro.so" "/home/retro/Roms/nes/Super Mario Bros. + Tetris + Nintendo World Cup (E) [!].nes""
```

Ein Eintrag für ein Steam Spiel sieht dann z.B. so aus:

```text
/home/retro/PixelDiskOne/RunProtonGame.sh "/home/retro/Games/Subnautica/Subnautica.exe" "Proton 9.0 (Beta)"
```

Es können auch andere Emulatoren oder Scripte hinzugefügt um diese via Diskette zu starten.

### NFC-Tag erstellen

Nun schreibt man die DatensatzID auf das NFC-Tag in einen Texteintrag. Hierfür kann man die App "NFC Tools" auf seinem Handy verwenden.

## Erleuterung der Scripte

Anbei eine unsortierte Kurzerläuterung der Scripte und Ihrer Funktion.

### Backgroundmusic

Aus einem Verzeichnis wird eine Playliste erstellt und anschließend die Musik zufällig abgespielt.

### EmbyPlayer

Steuert eine Emby Instanz an und Spielt deren Inhalte ab. Mit --help kann die Hilfe so wie Beispiele für den Aufruf angezeigt werden.

### HomeButton

Dient dazu eine URL auf den Homebutton der Fernbedienung zu legen.

### MediathekPlayer

Ein Script um Inhalte von https://mediathekviewweb.de abzuspielen.

### MutMusicAndSplash

Läuft im Hintergrund und fadet den Splash oder die Backgroundmusic ein oder aus. Je nachdem ob ein Content läuft oder nicht.

### PixelDiskOne-Start

Das Startscript für die PixelDiskOne. Von hier aus geht alles los.

### RunProtonGame

Dient zum starten von Windows Spielen via Proton.

### PixelDiskOne-Updater

Zieht die letze Version des Repos von Github.

### VideoSplash

Startet ein Video als Splashscreen indem es das Video auf den Desktophintergrund legt und im letzen Frame anhält.

### YoutubePlayer

Spielt ein Video oder eine Playlist (zufällige Videoauswahl) von YouTube ab.

### Extras/LoudNom

Dient zum Normalisieren der Backgroundmusic MP3's, so das alle Musikstücke die gleiche Lautstärke haben. Wenn man das Script ohne Parameter aufruft wird eine Hilfe ausgegeben.
