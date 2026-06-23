#!/bin/bash

# X-Display für alle screen-Sessions sicherstellen
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
# Venv-Python für alle nachfolgenden Prozesse priorisieren
export PATH="$HOME/PixelDiskOne/.venv/bin:$PATH"

# für einen sauberen start alle screen sessions beenden
screen -ls | grep -oP '\d+\.\S+' | xargs -I{} screen -S {} -X quit

# Maus wegschieben
xdotool mousemove 0 $(xdpyinfo | awk '/dimensions/{print $2}' | cut -d'x' -f2)

# Maus verstecken
screen -S MouseHider -dm bash -c "unclutter -idle 0.5 -root"

# evtl. vorhandene Mutefile entfernen
rm -f "$HOME/.mute" 2>/dev/null || true

# Updater blockierend ausführen
(cd "$HOME/PixelDiskOne" && ./PixelDiskOne-Updater.py)

# NFC-Reader-Reset: USB4-Router vor Start zurücksetzen
sudo "$HOME/PixelDiskOne/NfcReaderReset.sh"

# BGM & Splash Muter starten
screen -S MuteMusicAndSplash -dm bash -c "cd $HOME/PixelDiskOne && ./MuteMusicAndSplash.sh"

# NFC Reader starten
screen -S PixelDiskOne -dm bash -c "cd $HOME/PixelDiskOne && ./Main.py"

# Screentime starten
screen -S ScreenTime -dm bash -c "cd $HOME/PixelDiskOne/ScreenTime && ./ScreenTimeTracker.py"

# Warten so das die Diskette geladen werden kann
# somit kommt das Intro nur wenn keine Diskette beim
# booten eingesteckt ist
echo "Warte auf Diskette ..."
sleep 7

# Splash starten
screen -S VideoSplash -dm bash -c "cd $HOME/PixelDiskOne && ./VideoSplash.sh"

# Warten bis zum Musikstart
echo "Warte auf Musikstart ..."
sleep 22

# Hintergrundmusik spielen
screen -S Backgroundmusic -dm bash -c "cd $HOME/PixelDiskOne && ./Backgroundmusic.sh"
