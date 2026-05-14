"""Prüft ob das Screentime-Limit verbraucht ist und steuert den Nag-Screen."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCREENTIME_DIR = Path(__file__).parent / "screentime"
sys.path.insert(0, str(_SCREENTIME_DIR))

from Screentime import _is_unlimited, load_config, load_state  # noqa: E402

_STATE_PATH = _SCREENTIME_DIR / "screentime-state.json"
_CONFIG_PATH = _SCREENTIME_DIR / "screentime.yaml"
_NAG_SCRIPT = _SCREENTIME_DIR / "Nagscreen.py"


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

    if state.cooldown_started_at is not None:
        return True
    if _is_unlimited(config, datetime.now(timezone.utc)):
        return False
    return state.used_seconds >= config.limit_seconds


def show_nag(
    nag_script: Path = _NAG_SCRIPT,
    state_path: Path = _STATE_PATH,
    config_path: Path = _CONFIG_PATH,
) -> None:
    """Startet den Nag-Screen, falls er nicht bereits läuft.

    Args:
        nag_script: Pfad zu nag_screen.py.
        state_path: Pfad zur screentime-state.json.
        config_path: Pfad zur screentime.yaml.
    """
    already_running = (
        subprocess.run(
            ["pgrep", "-f", "Nagscreen.py"],
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
    """Beendet den Nag-Screen, falls er läuft."""
    subprocess.run(["pkill", "-f", "Nagscreen.py"], capture_output=True)
