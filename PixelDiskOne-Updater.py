#!/usr/bin/env python3
"""PixelDiskOne Updater – prüft Konnektivität, aktualisiert Code und Abhängigkeiten."""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import types
import Notification

try:
    import Console
except ImportError:
    Console = types.SimpleNamespace(info=print, warning=print, error=print)

_venv_python = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python3"
)
if os.path.exists(_venv_python) and os.path.realpath(
    sys.executable
) != os.path.realpath(_venv_python):
    os.execv(_venv_python, [_venv_python] + sys.argv)

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
GITHUB_HOST = "github.com"
GITHUB_PORT = 443
CONNECTIVITY_TIMEOUT = 5  # Sekunden – Socket-Timeout pro Versuch
INTERNET_WAIT_TIMEOUT = 10  # Sekunden – wie lange beim Boot auf Netzwerk gewartet wird
GIT_TIMEOUT = 10  # Sekunden
PIP_TIMEOUT = 15  # Sekunden
NOTIFY_ICON = os.path.join(REPO_DIR, "floppy-disk.png")  # Update erfolgreich
NOTIFY_ICON_NETWORK = "network-offline"  # keine Internetverbindung
NOTIFY_ICON_TIMEOUT = "network-error"  # Netzwerk-Timeout
NOTIFY_ICON_ERROR = "dialog-error"  # Git- / pip-Fehler
NOTIFY_ICON_WARNING = "dialog-warning"  # pip-Timeout / Warnungen
VENV_DIR = os.path.join(REPO_DIR, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")


def has_internet() -> bool:
    try:
        socket.setdefaulttimeout(CONNECTIVITY_TIMEOUT)
        with socket.create_connection((GITHUB_HOST, GITHUB_PORT)):
            return True
    except OSError:
        return False


def wait_for_internet() -> bool:
    """Wartet bis zu INTERNET_WAIT_TIMEOUT Sekunden auf eine Internetverbindung."""
    for _ in range(INTERNET_WAIT_TIMEOUT):
        if has_internet():
            return True
        time.sleep(1)
    return False


def fetch_remote() -> bool:
    """Holt Remote-Metadaten ohne lokale Änderung."""
    result = subprocess.run(
        ["git", "-C", REPO_DIR, "fetch", "origin", "dev"],
        timeout=GIT_TIMEOUT,
        capture_output=True,
    )
    return result.returncode == 0


def has_remote_changes() -> bool:
    """Vergleicht lokalen HEAD mit origin/dev. Nur lokale git-Operationen, instant."""
    local = subprocess.run(
        ["git", "-C", REPO_DIR, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    remote = subprocess.run(
        ["git", "-C", REPO_DIR, "rev-parse", "origin/dev"],
        capture_output=True,
        text=True,
    )
    return local.stdout.strip() != remote.stdout.strip()


def apply_update() -> bool:
    """Bereinigt Worktree und setzt lokalen Stand auf origin/dev."""
    commands = [
        ["git", "-C", REPO_DIR, "clean", "-df"],
        ["git", "-C", REPO_DIR, "reset", "--hard", "origin/dev"],
    ]
    for cmd in commands:
        result = subprocess.run(cmd, timeout=GIT_TIMEOUT, capture_output=True)
        if result.returncode != 0:
            return False
    return True


def run_pip_install() -> bool:
    """Erstellt Venv falls nötig und installiert requirements.txt via uv."""
    req_file = os.path.join(REPO_DIR, "requirements.txt")
    if not os.path.exists(req_file):
        return True
    if not shutil.which("uv"):
        subprocess.run(
            ["pip", "install", "--user", "uv"],
            timeout=30,
            capture_output=True,
            check=True,
        )
    if not os.path.exists(VENV_PYTHON):
        subprocess.run(
            ["uv", "venv", VENV_DIR], timeout=30, capture_output=True, check=True
        )
    result = subprocess.run(
        ["uv", "pip", "install", "--python", VENV_PYTHON, "-r", req_file],
        timeout=PIP_TIMEOUT,
        capture_output=True,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update erzwingen, auch ohne Remote-Änderungen",
    )
    args = parser.parse_args()

    Console.info("PixelDiskOne Updater – prüfe Verbindung...")

    if not wait_for_internet():
        Notification.send(
            "Update übersprungen",
            "Keine Internetverbindung – starte ohne Update.",
            NOTIFY_ICON_NETWORK,
        )
        Console.warning("Keine Internetverbindung – Update übersprungen.")
        sys.exit(0)

    Console.info("Prüfe auf neue Version...")

    try:
        if not fetch_remote():
            Notification.send(
                "Update-Fehler",
                "git fetch fehlgeschlagen – starte mit aktuellem Stand.",
                NOTIFY_ICON_ERROR,
            )
            Console.error("git fetch fehlgeschlagen.")
            sys.exit(0)
    except subprocess.TimeoutExpired:
        Notification.send(
            "Update-Timeout",
            "GitHub nicht erreichbar – starte ohne Update.",
            NOTIFY_ICON_TIMEOUT,
        )
        Console.error("git fetch Timeout.")
        sys.exit(0)

    if not args.force and not has_remote_changes():
        Console.info("Kein Update nötig – starte mit aktuellem Stand.")
        sys.exit(0)

    Console.info("Neue Version gefunden – aktualisiere...")

    if not apply_update():
        Notification.send(
            "Update fehlgeschlagen",
            "Git-Fehler – starte mit letztem Stand.",
            NOTIFY_ICON_ERROR,
        )
        Console.error("apply_update fehlgeschlagen.")
        sys.exit(0)

    try:
        pip_ok = run_pip_install()
    except subprocess.TimeoutExpired:
        Notification.send(
            "pip install Timeout",
            "Abhängigkeiten konnten nicht aktualisiert werden.",
            NOTIFY_ICON_WARNING,
        )
        Console.error("pip install Timeout.")
        sys.exit(0)

    if not pip_ok:
        Notification.send(
            "pip install fehlgeschlagen",
            "Bitte manuell prüfen: pip install -r requirements.txt",
            NOTIFY_ICON_ERROR,
        )
        Console.error("pip install fehlgeschlagen.")
        sys.exit(0)

    Notification.send(
        "Update erfolgreich",
        "PixelDiskOne wurde aktualisiert.",
        NOTIFY_ICON,
    )
    Console.info("Update abgeschlossen.")


if __name__ == "__main__":
    main()
