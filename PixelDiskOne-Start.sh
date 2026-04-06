#!/bin/bash

# für einen sauberen start alle screen sessions beenden
screen -ls | grep Detached | cut -d. -f1 | awk '{print $1}' | xargs -n 1 screen -X -S quit

# Maus wegschieben
xdotool mousemove 0 $(xdpyinfo | awk '/dimensions/{print $2}' | cut -d'x' -f2)

# Maus verstecken
screen -S MouseHider -dm bash -c "unclutter -idle 0.5 -root"

# evtl. vorhandene Mutefile entfernen
rm -f "$HOME/.mute" 2>/dev/null || true

# BGM & Splash Muter starten
screen -S MuteMusicAndSplash -dm bash -c "cd $HOME/PixelDiskOne && ./MuteMusicAndSplash.sh"

# Updater & NFC Reader starten
screen -S PixelDiskOne -dm bash -c "cd $HOME/PixelDiskOne && ./PixelDiskOne-Updater.sh && ./Main.py"

# Warten so das die Diskette geladen werden kann
# somit kommt das Intro nur wenn keine Diskette beim
# booten eingesteckt ist
sleep 7

# Splash starten
screen -S VideoSplash -dm bash -c "cd $HOME/PixelDiskOne && ./VideoSplash.sh"

# Warten bis zum Musikstart
sleep 22

# Hintergrundmusik spielen
screen -S Backgroundmusic -dm bash -c "cd $HOME/PixelDiskOne && ./Backgroundmusic.sh"
