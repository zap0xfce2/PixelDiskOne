#!/usr/bin/python3
# Erstellt von Zap0xfce2 im Februar 2025

import subprocess
import time
import re
import Console
import Database


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
                    b"[ -~]{4,}", binary_content
                )  # Sucht nach druckbaren ASCII-Zeichen
                # Dekodiere die Bytes zu Strings und füge sie zu einem großen String zusammen
                return "\n".join(
                    [string.decode("utf-8") for string in readable_strings]
                )
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
    # Console.info(Database.read("NFC-Tags.db"))
    current_content = read_nfc_tag()
    if current_content:
        processed_content = process_content(current_content)
        if processed_content != last_content:
            Console.info("Neuer Tag gefunden oder Inhalt hat sich geändert.")
            Console.info(processed_content)
            last_content = processed_content
        else:
            Console.info(
                "Der gelesene Inhalt ist identisch mit dem letzten. Warte auf ein neues Tag..."
            )
    else:
        Console.info("Kein Tag gefunden. Warte 3 Sekunden...")
    time.sleep(3)
