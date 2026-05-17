#!/usr/bin/env python3
"""PixelDiskOne Updater – prüft Konnektivität, aktualisiert Code und Abhängigkeiten."""

import os
import shutil
import socket
import subprocess
import sys
import types
import Notification

try:
    import Console
except ImportError:
    Console = types.SimpleNamespace(info=print, warning=print, error=print)

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
GITHUB_HOST = "github.com"
GITHUB_PORT = 443
CONNECTIVITY_TIMEOUT = 5  # Sekunden
GIT_TIMEOUT = 30  # Sekunden
PIP_TIMEOUT = 30  # Sekunden
NOTIFY_ICON = os.path.join(REPO_DIR, "floppy-disk.png")


def has_internet() -> bool:
    try:
        socket.setdefaulttimeout(CONNECTIVITY_TIMEOUT)
        with socket.create_connection((GITHUB_HOST, GITHUB_PORT)):
            return True
    except OSError:
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
    """Stellt sicher dass uv installiert ist, nutzt es dann für requirements.txt."""
    req_file = os.path.join(REPO_DIR, "requirements.txt")
    if not os.path.exists(req_file):
        return True
    if not shutil.which("uv"):
        subprocess.run(
            ["pip", "install", "uv"], timeout=30, capture_output=True, check=True
        )
    result = subprocess.run(
        ["uv", "pip", "install", "-r", req_file],
        timeout=PIP_TIMEOUT,
        capture_output=True,
    )
    return result.returncode == 0


def main() -> None:
    Console.info("PixelDiskOne Updater – prüfe Verbindung...")

    if not has_internet():
        Notification.send(
            "Update übersprungen",
            "Keine Internetverbindung – PixelDiskOne startet ohne Update.",
            NOTIFY_ICON,
        )
        Console.warning("Keine Internetverbindung – Update übersprungen.")
        sys.exit(0)

    Console.info("Prüfe auf neue Version...")

    try:
        if not fetch_remote():
            Notification.send(
                "Update-Fehler",
                "git fetch fehlgeschlagen – starte mit aktuellem Stand.",
                NOTIFY_ICON,
            )
            Console.error("git fetch fehlgeschlagen.")
            sys.exit(0)
    except subprocess.TimeoutExpired:
        Notification.send(
            "Update-Timeout",
            "GitHub nicht erreichbar – PixelDiskOne startet ohne Update.",
            NOTIFY_ICON,
        )
        Console.error("git fetch Timeout.")
        sys.exit(0)

    if not has_remote_changes():
        Console.info("Kein Update nötig – starte mit aktuellem Stand.")
        sys.exit(0)

    Console.info("Neue Version gefunden – aktualisiere...")

    if not apply_update():
        Notification.send(
            "Update fehlgeschlagen",
            "Git-Fehler – PixelDiskOne startet mit letztem Stand.",
            NOTIFY_ICON,
        )
        Console.error("apply_update fehlgeschlagen.")
        sys.exit(0)

    try:
        pip_ok = run_pip_install()
    except subprocess.TimeoutExpired:
        Notification.send(
            "pip install Timeout",
            "Abhängigkeiten konnten nicht aktualisiert werden.",
            NOTIFY_ICON,
        )
        Console.error("pip install Timeout.")
        sys.exit(0)

    if not pip_ok:
        Notification.send(
            "pip install fehlgeschlagen",
            "Bitte manuell prüfen: pip install -r requirements.txt",
            NOTIFY_ICON,
        )
        Console.error("pip install fehlgeschlagen.")
        sys.exit(0)

    Notification.send(
        "Update erfolgreich",
        "PixelDiskOne wurde aktualisiert und startet jetzt.",
        NOTIFY_ICON,
    )
    Console.info("Update abgeschlossen.")


if __name__ == "__main__":
    main()
