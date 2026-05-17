"""Aktiviert das projekteigene venv beim Skriptaufruf."""

import os
import sys

_venv_python = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python3"
)
if os.path.exists(_venv_python) and os.path.realpath(
    sys.executable
) != os.path.realpath(_venv_python):
    os.execv(_venv_python, [_venv_python] + sys.argv)
