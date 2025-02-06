#!/usr/bin/python3
# Erstellt von Zap0xfce2 im Februar 2025

import subprocess
import re
import time
import Console
import Database
import shlex
import Notification
import os


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
            content = file.read().decode("utf-8", errors="ignore").strip()
            return process_content(
                content
            )  # Direkt die aufbereitete Version zurückgeben
    except subprocess.CalledProcessError:
        pass
    return None


def process_content(content):
    lines = content.split("\n")
    processed_lines = []

    for line in lines:
        match = re.search(r"en(.{3})", line)
        if match:
            cleaned_line = match.group(1)
        else:
            cleaned_line = line[2:] if line.startswith("en") else line

        # Entfernt nicht-alphanumerische Zeichen
        cleaned_line = re.sub(r"\W+", "", cleaned_line)

        processed_lines.append(cleaned_line)

    if len(processed_lines) > 1:
        processed_lines[1] = processed_lines[1].rstrip(
            "Q"
        )  # Falls vorhanden, "Q" entfernen

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
            # if last_process and last_process.poll() is None:
            #     Console.info(f"Beende laufenden Prozess: {last_process.pid}")
            #     last_process.terminate()
            #     last_process.wait()

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
                "Spiel beendet",
                "Das Spiel wurde beendet da die Diskette entfernt wurde.",
                os.path.join(os.getcwd(), "floppy-disk.png"),
            )
            last_process.terminate()
            last_process.wait()
            last_process = None
            last_content = ""
