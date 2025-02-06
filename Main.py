#!/usr/bin/python3
# Erstellt von Zap0xfce2 im Februar 2025

import subprocess
import time
import re
import Console
import Database
import shlex
import signal
import Notification


def read_nfc_tag():
    try:
        # Versuch, den Tag zu lesen und den Inhalt zurückzugeben
        subprocess.run(
            ["nfc-mfultralight", "r", "nfc.dump"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open("nfc.dump", "rb") as file:
            for line in file:
                if b"T" in line:
                    content = (
                        line.split(b"T", 1)[1].strip().decode("utf-8", errors="ignore")
                    )

                    # Suche nach "en" und nimm nur die 3 Zeichen danach
                    match = re.search(r"en(.{3})", content)
                    if match:
                        return match.group(1)  # Nur die drei Zeichen nach "en"

                    return content  # Falls "en" nicht existiert, gib den Originalinhalt zurück
    except subprocess.CalledProcessError:
        pass
    return None


def process_content(content):
    lines = content.split("\n")
    processed_lines = [line[2:] if line.startswith("en") else line for line in lines]
    if len(processed_lines) > 1:
        processed_lines[1] = processed_lines[1].rstrip("Q")
    return "\n".join(processed_lines)


last_content = ""
# Hier speichern wir den letzten gestarteten Prozess
last_process = None

# nfc.dump einmalig beim start entfernen

while True:
    current_content = read_nfc_tag()

    if current_content:
        processed_content = process_content(current_content)

        if processed_content != last_content:
            # Neue Diskette erkannt
            last_content = processed_content

            # Falls ein alter Prozess läuft, beende ihn
            if last_process and last_process.poll() is None:
                Console.info(f"Beende laufenden Prozess: {last_process.pid}")
                last_process.terminate()
                last_process.wait()

            # Neuen Befehl aus Datenbank abrufen und Prozess starten
            command = Database.read(processed_content)
            if command:
                try:
                    Console.info(f"Starte: {command}")
                    last_process = subprocess.Popen(shlex.split(command))
                except Exception as e:
                    Console.error(f"Fehler beim Starten: {e}")
                    Notification.send("Fehler beim Starten", f"{e}", "dialog-error")
    else:
        # Falls keine Diskette mehr erkannt wird, beende den laufenden Prozess
        if last_process and last_process.poll() is None:
            Notification.send(
                "Diskette entfernt",
                "Das Spiel wurde beendet da die Diskette entfernt wurde.",
                "/home/retro/PixelDiskOne/floppy-disk.png",
            )
            last_process.terminate()
            last_process.wait()
            last_process = None
            last_content = ""
