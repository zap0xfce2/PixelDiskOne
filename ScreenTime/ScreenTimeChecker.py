"""Prüft ob das Screentime-Limit verbraucht ist und steuert den NagScreen."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCREENTIME_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCREENTIME_DIR))

from ScreenTimeTracker import (  # noqa: E402
    _is_cooldown_active,
    _is_unlimited,
    load_config,
    load_state,
)

_STATE_PATH = _SCREENTIME_DIR / "screentime-state.json"
_CONFIG_PATH = _SCREENTIME_DIR / "screentime.yaml"
_NAG_SCRIPT = _SCREENTIME_DIR / "NagScreen.py"


def is_blocked(
    state_path: Path = _STATE_PATH,
    config_path: Path = _CONFIG_PATH,
) -> bool:
    """Gibt True zurück wenn das Screentime-Limit verbraucht oder ein Cooldown aktiv ist.

    Args:
        state_path: Pfad zur screentime-state.json.
        config_path: Pfad zur screentime.yaml.

    Returns:
        True wenn Inhalte geblockt werden sollen.
    """
    config = load_config(config_path)
    state = load_state(state_path)
    now = datetime.now(timezone.utc)

    if _is_unlimited(config, now):
        return False
    if state.cooldown_started_at is not None:
        # Ein gesetzter Cooldown ersetzt die used_seconds-Prüfung: Ist er
        # abgelaufen, entspricht das einem _reset_state() im Daemon – auch
        # wenn der Daemon diesen Reset noch nicht selbst nachvollzogen hat.
        return _is_cooldown_active(config, state, now)
    return state.used_seconds >= config.limit_seconds


def show_nag(
    nag_script: Path = _NAG_SCRIPT,
    state_path: Path = _STATE_PATH,
    config_path: Path = _CONFIG_PATH,
) -> None:
    """Startet den NagScreen, falls er nicht bereits läuft.

    Args:
        nag_script: Pfad zu NagScreen.py.
        state_path: Pfad zur screentime-state.json.
        config_path: Pfad zur screentime.yaml.
    """
    already_running = (
        subprocess.run(
            ["pgrep", "-f", "NagScreen.py"],
            capture_output=True,
        ).returncode
        == 0
    )
    if already_running:
        return
    _env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    subprocess.Popen(
        [
            sys.executable,
            str(nag_script),
            "--state-file",
            str(state_path),
            "--config-file",
            str(config_path),
        ],
        env=_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def close_nag() -> None:
    """Beendet den NagScreen, falls er läuft."""
    subprocess.run(["pkill", "-f", "NagScreen.py"], capture_output=True)
