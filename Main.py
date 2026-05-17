#!/usr/bin/env python3
# Erstellt von Zap0xfce2 im Februar 2025

import subprocess
import re
import Console
import Database
import shlex
import Notification
import ScreentimeGate
import signal
import os
import nfc  # type: ignore
import time

BACKEND = "usb:072f:2200"
_current_proc = None
_tag_present = False


def start_process(tag):
    global _current_proc
    # Tag-Info auslesen
    tag_uid = getattr(tag, "identifier", b"").hex()
    tag_value = None

    if getattr(tag, "ndef", None):
        for rec in tag.ndef.records:
            if hasattr(rec, "text"):
                text = rec.text.strip()
                m = re.search(r"\d+", text)
                tag_value = m.group(0) if m else text
                break

    Console.info(f"Diskette erkannt → UID: {tag_uid}, Wert: {tag_value}")

    if _current_proc is None:
        command = Database.read(tag_value)
        if command:
            try:
                Console.info(f"Starte: {command}")
                _current_proc = subprocess.Popen(
                    shlex.split(command), preexec_fn=os.setsid
                )
                Console.info(
                    f"Gestartet: PID={_current_proc.pid}, PGID={os.getpgid(_current_proc.pid)}"
                )
            except Exception as e:
                Console.error(f"Fehler beim Starten: {e}")
                Notification.send("Fehler beim Starten", f"{e}", "dialog-error")
    else:
        pass


def stop_process():
    global _current_proc
    if not _current_proc:
        return

    try:
        pgid = os.getpgid(_current_proc.pid)
    except ProcessLookupError:
        Console.info("Prozessgruppe existiert nicht mehr, nichts zu tun.")
        _current_proc = None
        return

    Console.info(f"Diskette entfernt → beende Prozessgruppe {pgid} …")

    # Notification.send(
    #     "Diskette entfernt",
    #     "Das Programm wurde beendet da die Diskette entfernt wurde.",
    #     os.path.join(os.getcwd(), "floppy-disk.png"),
    # )

    # Erst freundlich, dann brutal, immer mit Logging
    for sig, name in ((signal.SIGTERM, "SIGTERM"), (signal.SIGKILL, "SIGKILL")):
        try:
            Console.info(f"Sende {name} an Prozessgruppe {pgid} …")
            os.killpg(pgid, sig)
        except ProcessLookupError:
            Console.info(f"Prozessgruppe {pgid} existiert nicht mehr.")
            break

        # kurz warten, ob sich was erledigt
        try:
            _current_proc.wait(timeout=1)
            Console.info("Hauptprozess ist beendet.")
            break
        except subprocess.TimeoutExpired:
            Console.info(
                f"Hauptprozess lebt nach {name} noch, versuche nächsten Schritt …"
            )

    _current_proc = None


def on_connect(tag):
    global _tag_present
    if _tag_present:
        return True
    _tag_present = True
    if ScreentimeGate.is_blocked():
        ScreentimeGate.show_nag()
        return True
    start_process(tag)
    return True


def on_release(tag):
    global _tag_present
    _tag_present = False
    stop_process()
    ScreentimeGate.close_nag()
    return True


Console.info("PixelDiskOne gestartet, warte auf Disketten!")
with nfc.ContactlessFrontend(BACKEND) as clf:
    while True:
        try:
            clf.connect(
                rdwr={
                    "on-connect": on_connect,
                    "on-release": on_release,
                    "beep-on-connect": False,
                }
            )
            time.sleep(0.05)
        except KeyboardInterrupt:
            stop_process()
            break
        except Exception as e:
            Console.error(f"Fehler: {e}")
            Notification.send("Fehler", f"{e}", "dialog-error")
            stop_process()
            time.sleep(0.2)
