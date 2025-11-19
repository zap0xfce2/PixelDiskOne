#!/usr/bin/python3
# Erstellt von Zap0xfce2 im Februar 2025

import subprocess
import re
import Console
import Database
import shlex
import Notification
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
    if _current_proc:
        Console.info("Diskette entfernt → beende Prozessgruppe …")
        try:
            pgid = os.getpgid(_current_proc.pid)
        except ProcessLookupError:
            _current_proc = None
            return

        Notification.send(
            "Diskette entfernt",
            "Das Programm wurde beendet da die Diskette entfernt wurde.",
            os.path.join(os.getcwd(), "floppy-disk.png"),
        )

        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            _current_proc = None
            return

        try:
            _current_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        _current_proc = None


def on_connect(tag):
    global _tag_present
    if _tag_present:
        return True
    _tag_present = True
    start_process(tag)
    return True


def on_release(tag):
    global _tag_present
    _tag_present = False
    stop_process()
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
