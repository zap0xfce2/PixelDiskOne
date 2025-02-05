#!/usr/bin/python3
# Erstellt von Zap0xfce2 im Februar 2025

import subprocess
import time
import re
import Console
import Database
import shlex


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
    # Entferne 'en' am Anfang und ein spezifisches 'Q' am Ende der zweiten Zeile
    lines = content.split("\n")
    processed_lines = [line[2:] if line.startswith("en") else line for line in lines]
    if len(processed_lines) > 1:
        processed_lines[1] = processed_lines[1].rstrip("Q")
    return "\n".join(processed_lines)


last_content = ""
while True:
    current_content = read_nfc_tag()
    if current_content:
        processed_content = process_content(current_content)
        if processed_content != last_content:
            Console.info("Neuer Tag gefunden oder Inhalt hat sich geändert.")
            last_content = processed_content

            command = Database.read(processed_content)
            if command:
                try:
                    Console.info(f"Führe Befehl aus: {command}")
                    subprocess.run(shlex.split(command), check=True)
                except subprocess.CalledProcessError as e:
                    Console.error(f"Fehler beim Ausführen: {e}")
        else:
            Console.info(
                "Der gelesene Inhalt ist identisch mit dem letzten. Warte auf ein neues Tag..."
            )
            # subprocess.run(shlex.split("killall retroarch"), check=True)
    else:
        Console.info("Kein Tag gefunden. Warte 1 Sekunde...")
    time.sleep(1)
