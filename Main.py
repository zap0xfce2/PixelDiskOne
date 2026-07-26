#!/usr/bin/env python3
# Erstellt von Zap0xfce2 im Februar 2025

import argparse
import os
import sys
from pathlib import Path
import VenvBootstrap  # type: ignore # noqa: F401

sys.path.insert(0, str(Path(__file__).parent / "ScreenTime"))

import subprocess
import re
import Console
import Database
import shlex
import Notification
import ScreenTimeChecker  # type: ignore
import signal
import nfc  # type: ignore
import time

BACKEND = "usb:072f:2200"
NFC_VENDOR_ID = 0x072F
NFC_PRODUCT_ID = 0x2200
_USB_RE_ENUM_WAIT_SECS = 1.5

_arg_parser = argparse.ArgumentParser()
_arg_parser.add_argument(
    "--pre-script",
    default=None,
    help="Befehl, der vor jedem Programmstart synchron ausgeführt wird (z.B. SetScreenResolution.sh)",
)
_args = _arg_parser.parse_args()

_current_proc = None
_tag_present = False


def reset_nfc_device() -> None:
    """USB-Reset des ACR122U, damit kein veralteter Gerätezustand nach Neustart bleibt."""
    try:
        import usb.core  # type: ignore

        dev = usb.core.find(idVendor=NFC_VENDOR_ID, idProduct=NFC_PRODUCT_ID)
        if dev is None:
            Console.info("NFC-Reader nicht gefunden, kein Reset nötig.")
            return
        Console.info("Führe USB-Reset des NFC-Readers durch …")
        dev.reset()
        time.sleep(_USB_RE_ENUM_WAIT_SECS)
        Console.info("NFC-Reader erfolgreich zurückgesetzt.")
    except Exception as e:
        Console.info(f"USB-Reset nicht möglich (wird ignoriert): {e}")


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
            if _args.pre_script:
                try:
                    Console.info(f"Führe Pre-Script aus: {_args.pre_script}")
                    subprocess.run(shlex.split(_args.pre_script), check=False)
                except Exception as e:
                    Console.error(f"Pre-Script fehlgeschlagen: {e}")
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
    if ScreenTimeChecker.is_blocked():
        ScreenTimeChecker.show_nag()
        return True
    start_process(tag)
    return True


def on_release(tag):
    global _tag_present
    _tag_present = False
    stop_process()
    ScreenTimeChecker.close_nag()
    return True


_RECONNECT_WAIT_SECS = 3.0

Console.info("PixelDiskOne gestartet, warte auf Disketten!")
reset_nfc_device()
while True:
    try:
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
                    raise
                except Exception as e:
                    Console.error(f"Polling-Fehler: {e}")
                    Notification.send("Fehler", f"{e}", "dialog-error")
                    stop_process()
                    time.sleep(0.2)
    except KeyboardInterrupt:
        break
    except Exception as e:
        Console.error(
            f"Reader-Initialisierung fehlgeschlagen: {e} — Neuversuch in {_RECONNECT_WAIT_SECS}s"
        )
        stop_process()
        time.sleep(_RECONNECT_WAIT_SECS)
        reset_nfc_device()
