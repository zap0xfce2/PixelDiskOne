"""Aktiviert das projekteigene venv beim Skriptaufruf.

Dieses Modul wird als Side-Effect-Import ganz oben in jedem Einstiegsskript
importiert. Es prüft, ob ein .venv im übergeordneten Verzeichnis existiert
und ob der aktuelle Interpreter NICHT der venv-Python ist. Falls beides
zutrifft, wird der Prozess via os.execv() mit dem venv-Python neu gestartet
(kein Return — os.execv ersetzt den laufenden Prozess).

Nutzt ausschließlich os und sys — nie Drittanbieter-Imports — damit das
Modul selbst ohne aktive venv importierbar bleibt.
"""

import os
import sys

_venv_python = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".venv", "bin", "python3"
)
if os.path.exists(_venv_python) and os.path.realpath(
    sys.executable
) != os.path.realpath(_venv_python):
    os.execv(_venv_python, [_venv_python] + sys.argv)
