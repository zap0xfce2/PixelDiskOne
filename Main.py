#!/usr/bin/python3
# Erstellt von Zap0xfce2 im Februar 2025

import subprocess
import re
import Console
import Database
import shlex
import Notification
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
                env = os.environ.copy()
                env.setdefault("DISPLAY", ":0")
                env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
                _current_proc = subprocess.Popen(shlex.split(command), env=env)
            except Exception as e:
                Console.error(f"Fehler beim Starten: {e}")
                Notification.send("Fehler beim Starten", f"{e}", "dialog-error")
    else:
        pass


def stop_process():
    global _current_proc
    if _current_proc:
        Console.info("Diskette entfernt → beende Prozess …")
        Notification.send(
            "Spiel beendet",
            "Das Spiel wurde beendet da die Diskette entfernt wurde.",
            os.path.join(os.getcwd(), "floppy-disk.png"),
        )
        _current_proc.terminate()
        try:
            _current_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _current_proc.kill()
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
