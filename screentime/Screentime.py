#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import VenvBootstrap  # type: ignore # noqa: F401, E402

"""Screentime-Daemon für Linux/XFCE.

Trackt die Laufzeit konfigurierter Anwendungen und erzwingt Limits
per Benachrichtigung, Nag-Screen und ggf. Prozess-Terminierung.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from enum import Enum
from pathlib import Path
from typing import NoReturn

import yaml

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

POLL_INTERVAL = 5  # Sekunden zwischen jedem Poll-Durchlauf
FAST_POLL_INTERVAL = (
    0.5  # Verkürzt wenn Soft-Limit aktiv (schnelles Erkennen von Neustarts)
)
MAX_ELAPSED_FACTOR = 2  # Cap für elapsed-Zeit: max. 2× POLL_INTERVAL
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "screentime.yaml"
STATE_PATH = SCRIPT_DIR / "screentime-state.json"
NAG_SCREEN_SCRIPT = SCRIPT_DIR / "Nagscreen.py"

NOTIFY_SEND_CMD = "notify-send"
PROC_DIR = Path("/proc")

_DAY_NAME_TO_WEEKDAY: dict[str, int] = {
    "mo": 0,
    "di": 1,
    "mi": 2,
    "do": 3,
    "fr": 4,
    "sa": 5,
    "so": 6,
}


class LimitMode(str, Enum):
    """Verhalten beim Erreichen des Zeitlimits."""

    HARD = "hard"
    SOFT = "soft"


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------


@dataclass
class AppConfig:
    """Konfiguration einer zu trackenden Anwendung.

    Attributes:
        name: Prozessname (entspricht /proc/PID/comm).
        limit_mode: Reaktion beim Limit-Erreichen (hard = sofort killen, soft = Warnung).
        title_blacklist: Titelbestandteile, die diese App-Instanz vom Tracking ausschließen.
    """

    name: str
    limit_mode: LimitMode
    title_blacklist: list[str] = field(default_factory=list)


@dataclass
class UnlimitedWindow:
    """Tägliches Zeitfenster, in dem das Nutzungslimit nicht gilt.

    Attributes:
        start: Beginn des Fensters (inklusive, lokale Uhrzeit).
        end: Ende des Fensters (exklusive, lokale Uhrzeit).
        days: Wochentage als Integer (0=Mo … 6=So). None = gilt täglich.
    """

    start: dtime
    end: dtime
    days: list[int] | None = None


@dataclass
class Config:
    """Gesamtkonfiguration aus screentime.yaml.

    Attributes:
        limit_minutes: Nutzungslimit in Minuten.
        cooldown_minutes: Pflichtpause nach Limit-Erreichen in Minuten.
        notify_thresholds_remaining_percent: Schwellwerte (% verbleibend) für Benachrichtigungen.
        apps: Liste der getrackten Anwendungen.
        notification_icon: Icon-Name oder Pfad für Desktop-Benachrichtigungen.
        unlimited_windows: Tägliche Zeitfenster, in denen das Limit nicht gilt.
    """

    limit_minutes: float
    cooldown_minutes: float
    notify_thresholds_remaining_percent: list[float]
    apps: list[AppConfig]
    notification_icon: str = "appointment-soon"
    unlimited_windows: list[UnlimitedWindow] = field(default_factory=list)

    @property
    def limit_seconds(self) -> float:
        """Limit in Sekunden."""
        return self.limit_minutes * 60

    @property
    def cooldown_seconds(self) -> float:
        """Cooldown-Dauer in Sekunden."""
        return self.cooldown_minutes * 60

    @property
    def smallest_threshold(self) -> float:
        """Kleinster konfigurierter Schwellwert (für Critical-Urgency)."""
        return min(self.notify_thresholds_remaining_percent)


@dataclass
class State:
    """Laufzeit-Zustand des Daemons (wird in screentime-state.json persistiert).

    Attributes:
        used_seconds: Bisher aufgelaufene Nutzungszeit in Sekunden.
        cooldown_started_at: Startzeitpunkt der aktuellen Cooldown-Phase (UTC).
        soft_allowed_pids: PIDs, die nach Limit-Erreichen (soft) noch laufen dürfen.
        notifications_sent: Schwellwerte, für die bereits eine Benachrichtigung gesendet wurde.
        last_poll_at: Zeitpunkt des letzten Poll-Durchlaufs (UTC).
        nag_proc: Popen-Objekt des laufenden Nagscreen.py-Prozesses (nur im Arbeitsspeicher, nicht persistiert).
    """

    used_seconds: float = 0.0
    cooldown_started_at: datetime | None = None
    soft_allowed_pids: list[int] = field(default_factory=list)
    notifications_sent: list[float] = field(default_factory=list)
    last_poll_at: datetime | None = None
    nag_proc: subprocess.Popen | None = field(default=None, init=False, repr=False)


# ---------------------------------------------------------------------------
# Config & State I/O
# ---------------------------------------------------------------------------


def load_config(path: Path) -> Config:
    """Lädt und validiert die YAML-Konfigurationsdatei.

    Args:
        path: Pfad zur screentime.yaml.

    Returns:
        Geparstes Config-Objekt.

    Raises:
        FileNotFoundError: Wenn die Config-Datei nicht existiert.
        KeyError: Wenn ein Pflichtfeld fehlt.
    """
    raw = yaml.safe_load(path.read_text())
    apps = [
        AppConfig(
            name=app["name"],
            limit_mode=LimitMode(app["limit_mode"]),
            title_blacklist=app.get("title_blacklist", []),
        )
        for app in raw["apps"]
    ]
    raw_icon = raw.get("notification_icon")
    notification_icon = "appointment-soon"
    if raw_icon:
        icon_path = (path.parent / raw_icon).resolve()
        notification_icon = str(icon_path) if icon_path.exists() else str(raw_icon)

    unlimited_windows = [
        UnlimitedWindow(
            start=dtime.fromisoformat(w["from"]),
            end=dtime.fromisoformat(w["to"]),
            days=(
                [_DAY_NAME_TO_WEEKDAY[d.lower()] for d in w["days"]]
                if "days" in w
                else None
            ),
        )
        for w in raw.get("unlimited", [])
    ]

    return Config(
        limit_minutes=float(raw["limit_minutes"]),
        cooldown_minutes=float(raw["cooldown_minutes"]),
        notify_thresholds_remaining_percent=[
            float(t) for t in raw["notify_thresholds_remaining_percent"]
        ],
        apps=apps,
        notification_icon=notification_icon,
        unlimited_windows=unlimited_windows,
    )


def _parse_optional_datetime(value: str | None) -> datetime | None:
    """Parst einen ISO-8601-String in ein UTC-aware datetime oder gibt None zurück."""
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_state(path: Path) -> State:
    """Lädt den persistierten Zustand oder gibt einen frischen State zurück.

    Args:
        path: Pfad zur screentime-state.json.

    Returns:
        State-Objekt mit gespeicherten oder Standard-Werten.
    """
    if not path.exists():
        return State()

    raw = json.loads(path.read_text())
    return State(
        used_seconds=float(raw.get("used_seconds", 0.0)),
        cooldown_started_at=_parse_optional_datetime(raw.get("cooldown_started_at")),
        soft_allowed_pids=list(raw.get("soft_allowed_pids", [])),
        notifications_sent=list(raw.get("notifications_sent", [])),
        last_poll_at=_parse_optional_datetime(raw.get("last_poll_at")),
    )


def _build_state_dict(state: State) -> dict[str, object]:
    """Serialisiert den State in ein JSON-kompatibles Dict."""
    return {
        "used_seconds": state.used_seconds,
        "cooldown_started_at": (
            state.cooldown_started_at.isoformat() if state.cooldown_started_at else None
        ),
        "soft_allowed_pids": state.soft_allowed_pids,
        "notifications_sent": state.notifications_sent,
        "last_poll_at": (
            state.last_poll_at.isoformat() if state.last_poll_at else None
        ),
    }


def save_state(state: State, path: Path) -> None:
    """Schreibt den aktuellen Zustand atomar in die State-Datei.

    Verwendet tempfile + os.replace() für atomares Schreiben,
    damit kein korrupter Zwischenzustand entsteht.

    Args:
        state: Aktueller Daemon-Zustand.
        path: Zielpfad der State-Datei.
    """
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(_build_state_dict(state), f, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        os.unlink(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Prozess-Scanning
# ---------------------------------------------------------------------------


def get_mpv_title(pid: int) -> str | None:
    """Liest den --title-Parameter aus der mpv-Kommandozeile.

    Args:
        pid: PID des mpv-Prozesses.

    Returns:
        Titelwert oder None, wenn kein --title angegeben wurde.
    """
    cmdline_path = PROC_DIR / str(pid) / "cmdline"
    try:
        raw = cmdline_path.read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None

    args = raw.split(b"\x00")
    str_args = [a.decode("utf-8", errors="replace") for a in args]

    for i, arg in enumerate(str_args):
        if arg.startswith("--title="):
            return arg.split("=", 1)[1]
        if arg == "--title" and i + 1 < len(str_args):
            return str_args[i + 1]
    return None


def _is_title_blacklisted(title: str | None, blacklist: list[str]) -> bool:
    """Prüft ob ein Titel einen der Blacklist-Einträge enthält (Substring-Match)."""
    if title is None:
        return False
    title_lower = title.lower()
    return any(entry.lower() in title_lower for entry in blacklist)


def _get_comm(pid: int) -> str | None:
    """Liest den Prozessnamen aus /proc/PID/comm."""
    comm_path = PROC_DIR / str(pid) / "comm"
    try:
        return comm_path.read_text().strip()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None


def find_app_pids(app: AppConfig) -> set[int]:
    """Findet alle PIDs einer getrackten Anwendung in /proc.

    Bei mpv: Ignoriert Instanzen, deren --title einen Blacklist-Eintrag enthält.

    Args:
        app: Konfiguration der gesuchten Anwendung.

    Returns:
        Menge der gefundenen PIDs.
    """
    pids: set[int] = set()
    for entry in PROC_DIR.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if _get_comm(pid) != app.name:
            continue
        if app.title_blacklist and _is_title_blacklisted(
            get_mpv_title(pid), app.title_blacklist
        ):
            continue
        pids.add(pid)
    return pids


def is_pid_alive(pid: int) -> bool:
    """Prüft ob eine PID noch im /proc-Verzeichnis existiert.

    Args:
        pid: Zu prüfende Prozess-ID.

    Returns:
        True wenn der Prozess noch läuft.
    """
    return (PROC_DIR / str(pid)).exists()


def kill_pids(pids: set[int]) -> None:
    """Sendet SIGTERM an alle angegebenen PIDs.

    Ignoriert Fehler für bereits beendete Prozesse.

    Args:
        pids: Menge der zu terminierenden PIDs.
    """
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # Prozess bereits beendet
        except PermissionError:
            print(f"Keine Berechtigung: PID {pid} konnte nicht beendet werden.")


# ---------------------------------------------------------------------------
# Nag-Screen
# ---------------------------------------------------------------------------


def ensure_nag_visible(state: State) -> None:
    """Stellt sicher, dass der Nag-Screen sichtbar ist.

    Startet Nagscreen.py neu, falls der Prozess nicht mehr läuft.
    poll() statt is_pid_alive() verwenden, damit Zombie-Prozesse (ESC-geschlossen)
    korrekt erkannt und aufgeräumt werden — /proc/PID existiert für Zombies weiterhin.

    Args:
        state: Aktueller Daemon-Zustand (nag_proc wird ggf. aktualisiert).
    """
    if state.nag_proc is not None and state.nag_proc.poll() is None:
        return
    subprocess.run(["pkill", "-f", "Nagscreen.py"], capture_output=True)
    if not NAG_SCREEN_SCRIPT.exists():
        print(f"Warnung: Nag-Screen-Skript nicht gefunden: {NAG_SCREEN_SCRIPT}")
        return
    state.nag_proc = subprocess.Popen(
        [
            sys.executable,
            str(NAG_SCREEN_SCRIPT),
            "--state-file",
            str(STATE_PATH),
            "--config-file",
            str(CONFIG_PATH),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# Benachrichtigungen
# ---------------------------------------------------------------------------


def send_notification(
    message: str,
    urgency: str = "normal",
    icon: str = "appointment-soon",
    timeout_ms: int = 5000,
) -> None:
    """Sendet eine Desktop-Benachrichtigung via notify-send.

    Args:
        message: Anzeigetext der Benachrichtigung.
        urgency: notify-send-Urgency ("low", "normal", "critical").
        icon: Themed icon name oder absoluter Pfad zur Icon-Datei.
        timeout_ms: Anzeigedauer in Millisekunden; erzwingt Verschwinden auch bei critical-Urgency.
    """
    subprocess.Popen(
        [
            NOTIFY_SEND_CMD,
            "-u",
            urgency,
            "-t",
            str(timeout_ms),
            "-i",
            icon,
            "Bildschirmzeit",
            message,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _format_remaining_time(seconds: float) -> str:
    """Formatiert Sekunden als lesbare deutsche Zeitangabe (z.B. '5 Minuten 30 Sekunden')."""
    total = int(seconds)
    hours = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60
    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours} {'Stunde' if hours == 1 else 'Stunden'}")
        if mins > 0:
            parts.append(f"{mins} {'Minute' if mins == 1 else 'Minuten'}")
        return " ".join(parts)
    if mins > 0:
        parts.append(f"{mins} {'Minute' if mins == 1 else 'Minuten'}")
        if secs > 0:
            parts.append(f"{secs} {'Sekunde' if secs == 1 else 'Sekunden'}")
        return " ".join(parts)
    return f"{secs} {'Sekunde' if secs == 1 else 'Sekunden'}"


def _build_notification_message(remaining_percent: float, limit_seconds: float) -> str:
    """Erstellt den Benachrichtigungstext mit verbleibender Zeit."""
    clamped = max(0.0, remaining_percent)
    remaining_seconds = (clamped / 100.0) * limit_seconds
    return (
        f"Noch {clamped:.0f}% verbleibend ({_format_remaining_time(remaining_seconds)})"
    )


def check_notifications(config: Config, state: State, remaining_percent: float) -> None:
    """Sendet Benachrichtigungen für noch nicht ausgelöste Schwellwerte.

    Args:
        config: Daemon-Konfiguration.
        state: Aktueller Daemon-Zustand.
        remaining_percent: Verbleibende Nutzungszeit in Prozent.
    """
    sorted_thresholds = sorted(config.notify_thresholds_remaining_percent, reverse=True)
    for threshold in sorted_thresholds:
        if remaining_percent > threshold or threshold in state.notifications_sent:
            continue
        urgency = "normal"
        message = _build_notification_message(remaining_percent, config.limit_seconds)
        send_notification(message, urgency, config.notification_icon)
        state.notifications_sent.append(threshold)


# ---------------------------------------------------------------------------
# Kern-Logik
# ---------------------------------------------------------------------------


def _reset_state(state: State) -> None:
    """Setzt den Daemon-Zustand nach Cooldown-Ende zurück."""
    state.used_seconds = 0.0
    state.cooldown_started_at = None
    state.soft_allowed_pids = []
    state.notifications_sent = []


def _needs_fast_polling(state: State) -> bool:
    """Gibt True zurück wenn Soft-Limit aktiv ist und Neustarts sofort erkannt werden sollen."""
    return bool(state.soft_allowed_pids) or state.cooldown_started_at is not None


def _handle_waiting_for_soft_close(config: Config, state: State) -> None:
    """Wartet auf Schließung aller Soft-Apps, dann startet den Cooldown.

    Wird aufgerufen wenn das Limit erreicht wurde aber noch Soft-App-PIDs
    laufen. Neue Startversuche werden sofort beendet.

    Args:
        config: Daemon-Konfiguration.
        state: Aktueller Daemon-Zustand.
    """
    still_alive = [pid for pid in state.soft_allowed_pids if is_pid_alive(pid)]

    if still_alive:
        new_pids: set[int] = set()
        for app in config.apps:
            new_pids |= find_app_pids(app) - set(state.soft_allowed_pids)
        if new_pids:
            state.soft_allowed_pids = still_alive + list(new_pids)
            send_notification(
                "Bildschirmzeit abgelaufen – App-Start registriert.",
                "normal",
                config.notification_icon,
            )
        else:
            state.soft_allowed_pids = still_alive
        return

    state.soft_allowed_pids = []
    state.cooldown_started_at = datetime.now(timezone.utc)
    send_notification(
        f"Cooldown gestartet – noch {_format_remaining_time(config.cooldown_seconds)} verbleibend.",
        "normal",
        config.notification_icon,
    )
    print(
        f"Soft-Apps geschlossen – Cooldown gestartet. ({datetime.now().strftime('%H:%M:%S')})"
    )


def handle_cooldown(config: Config, state: State) -> bool:
    """Verarbeitet die Cooldown-Phase.

    Args:
        config: Daemon-Konfiguration.
        state: Aktueller Daemon-Zustand.

    Returns:
        True wenn gerade Cooldown aktiv ist (Loop-Iteration soll enden).
    """
    if state.cooldown_started_at is None and state.soft_allowed_pids:
        _handle_waiting_for_soft_close(config, state)
        return True

    if state.cooldown_started_at is None:
        return False

    now = datetime.now(timezone.utc)
    elapsed = (now - state.cooldown_started_at).total_seconds()

    if elapsed >= config.cooldown_seconds:
        state.nag_proc = None
        _reset_state(state)
        print(
            f"Cooldown beendet – Zustand zurückgesetzt. ({datetime.now().strftime('%H:%M:%S')})"
        )
        return True

    # Cooldown läuft: getrackte Prozesse per Notification melden (kein Kill)
    any_new = False
    for app in config.apps:
        if find_app_pids(app) - set(state.soft_allowed_pids):
            any_new = True
            break
    if any_new:
        remaining = config.cooldown_seconds - elapsed
        send_notification(
            f"Cooldown läuft – noch {_format_remaining_time(remaining)} verbleibend.",
            "critical",
            config.notification_icon,
        )

    return True


def _calculate_elapsed(state: State) -> float:
    """Berechnet die vergangene Zeit seit dem letzten Poll (gecappt)."""
    if state.last_poll_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    raw_elapsed = (now - state.last_poll_at).total_seconds()
    return min(raw_elapsed, POLL_INTERVAL * MAX_ELAPSED_FACTOR)


def _handle_hard_app_at_limit(app_pids: set[int]) -> None:
    """Terminiert alle PIDs einer Hard-App."""
    if not app_pids:
        return
    kill_pids(app_pids)


def _handle_soft_app_at_limit(app_pids: set[int], state: State) -> None:
    """Merkt aktuelle Soft-App-PIDs als erlaubt (dürfen weiterlaufen)."""
    new_pids = app_pids - set(state.soft_allowed_pids)
    if new_pids:
        state.soft_allowed_pids.extend(new_pids)


def handle_limit_action(
    config: Config, state: State, app_pids: dict[str, set[int]]
) -> None:
    """Führt die Limit-Aktion aus wenn used_seconds >= limit_seconds.

    Args:
        config: Daemon-Konfiguration.
        state: Aktueller Daemon-Zustand.
        app_pids: Mapping von App-Name → aktuell laufende PIDs.
    """
    now = datetime.now(timezone.utc)
    any_hard_app_killed = False

    for app in config.apps:
        pids = app_pids.get(app.name, set())
        if app.limit_mode == LimitMode.HARD:
            if pids:
                any_hard_app_killed = True
            _handle_hard_app_at_limit(pids)
        else:
            _handle_soft_app_at_limit(pids, state)

    if state.cooldown_started_at is None:
        if state.soft_allowed_pids:
            # Soft-Apps laufen noch – Cooldown beginnt erst nach ihrer Schließung
            print(
                f"Limit erreicht – Warte auf Schließung der Soft-Apps. ({datetime.now().strftime('%H:%M:%S')})"
            )
        else:
            state.cooldown_started_at = now
            if any_hard_app_killed:
                ensure_nag_visible(state)
            print(
                f"Limit erreicht – Cooldown gestartet. ({datetime.now().strftime('%H:%M:%S')})"
            )


def _is_unlimited(config: Config, now: datetime) -> bool:
    """Gibt True zurück wenn die aktuelle Uhrzeit in einem unlimited-Fenster liegt.

    Args:
        config: Daemon-Konfiguration.
        now: Aktueller Zeitpunkt (timezone-aware, wird in lokale Zeit umgewandelt).

    Returns:
        True wenn das Limit gerade deaktiviert ist.
    """
    local = now.astimezone()
    current = local.time().replace(tzinfo=None)
    weekday = local.weekday()
    return any(
        w.start <= current < w.end and (w.days is None or weekday in w.days)
        for w in config.unlimited_windows
    )


def poll(config: Config, state: State) -> State:
    """Führt einen einzelnen Poll-Durchlauf durch.

    Args:
        config: Daemon-Konfiguration.
        state: Zustand vor diesem Durchlauf.

    Returns:
        Aktualisierter Zustand nach diesem Durchlauf.
    """
    if handle_cooldown(config, state):
        state.last_poll_at = datetime.now(timezone.utc)
        return state

    app_pids: dict[str, set[int]] = {
        app.name: find_app_pids(app) for app in config.apps
    }
    any_tracked_running = any(pids for pids in app_pids.values())

    now_local = datetime.now(timezone.utc)
    unlimited = _is_unlimited(config, now_local)

    elapsed = _calculate_elapsed(state)
    if not unlimited and any_tracked_running:
        state.used_seconds += elapsed

    remaining_percent = (1.0 - state.used_seconds / config.limit_seconds) * 100.0
    if not unlimited and state.used_seconds < config.limit_seconds:
        check_notifications(config, state, remaining_percent)

    if not unlimited and state.used_seconds >= config.limit_seconds:
        handle_limit_action(config, state, app_pids)

    state.last_poll_at = datetime.now(timezone.utc)
    return state


# ---------------------------------------------------------------------------
# Signal-Handling & Einstiegspunkt
# ---------------------------------------------------------------------------


def _setup_signal_handlers(config: Config, state_ref: list[State]) -> None:
    """Registriert Signal-Handler für sauberen Exit.

    Args:
        config: Daemon-Konfiguration (für State-Speichern).
        state_ref: Einelementige Liste, die den aktuellen State hält (Mutable-Referenz).
    """

    def _shutdown(signum: int, frame: object) -> NoReturn:
        print(f"\nSignal {signum} empfangen – Daemon wird beendet.")
        save_state(state_ref[0], STATE_PATH)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)


def main() -> None:
    """Startet den Screentime-Daemon und führt die Poll-Schleife aus."""
    print(f"Screentime-Daemon gestartet (Poll-Intervall: {POLL_INTERVAL}s).")
    print(f"Config: {CONFIG_PATH}")
    print(f"State:  {STATE_PATH}")

    config = load_config(CONFIG_PATH)
    state = load_state(STATE_PATH)

    state_ref: list[State] = [state]
    _setup_signal_handlers(config, state_ref)

    while True:
        state = poll(config, state)
        state_ref[0] = state
        save_state(state, STATE_PATH)
        sleep_interval = (
            FAST_POLL_INTERVAL if _needs_fast_polling(state) else POLL_INTERVAL
        )
        time.sleep(sleep_interval)


if __name__ == "__main__":
    main()
