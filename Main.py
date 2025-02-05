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
        result = subprocess.run(
            ["nfc-mfultralight", "r", "nfc.dump"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            with open("nfc.dump", "rb") as file:  # Lese im Binärmodus
                binary_content = file.read()
                # Extrahiere lesbare Zeichenketten aus den Binärdaten
                readable_strings = re.findall(
                    b"[ -~]{1,}", binary_content
                )  # Sucht nach druckbaren ASCII-Zeichen
                # Dekodiere die Bytes zu Strings und füge sie zu einem großen String zusammen
                return "\n".join(
                    [string.decode("utf-8") for string in readable_strings]
                )
    except subprocess.CalledProcessError:
        pass
    return None


def process_content(content):
    lines = content.split("\n")
    for line in lines:
        if line.startswith("T"):
            return line[1:].strip()  # Alles nach "T" zurückgeben
    return None  # Falls kein "T" gefunden wird


def process_content(content):
    # Entferne 'en' am Anfang und ein spezifisches 'Q' am Ende der zweiten Zeile
    lines = content.split("\n")
    processed_lines = [line[2:] if line.startswith("en") else line for line in lines]
    if len(processed_lines) > 1:
        processed_lines[1] = processed_lines[1].rstrip("Q")
    return "\n".join(processed_lines)


last_content = ""
while True:
    # Console.info(Database.read(1))
    current_content = read_nfc_tag()
    if current_content:
        processed_content = process_content(current_content)
        if processed_content != last_content:
            Console.info("Neuer Tag gefunden oder Inhalt hat sich geändert.")
            # Console.info(processed_content)
            last_content = processed_content

            Console.info(process_content(processed_content))
            # command = Database.read(
            #     processed_content
            # )  # Datenbank gibt einen Befehl zurück
            # if command:
            #     try:
            #         Console.info(f"Führe Befehl aus: {command}")
            #         subprocess.run(shlex.split(command), check=True)  # Befehl ausführen
            #     except subprocess.CalledProcessError as e:
            #         Console.error(f"Fehler beim Ausführen: {e}")
        else:
            Console.info(
                "Der gelesene Inhalt ist identisch mit dem letzten. Warte auf ein neues Tag..."
            )
    else:
        Console.info("Kein Tag gefunden. Warte 3 Sekunden...")
    time.sleep(3)
