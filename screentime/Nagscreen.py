#!/usr/bin/env python3
"""Cooldown Nag-Screen für Screentime-Daemon.

Zeigt ein Charakter-Sprite das auf ein Ziel zusteuert.
Die Position entspricht der verstrichenen Cooldown-Zeit.
Startet via: python nag_screen.py --state-file PATH --config-file PATH
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import tkinter as tk

    _TKINTER_AVAILABLE = True
except ModuleNotFoundError:
    _TKINTER_AVAILABLE = False

try:
    from PIL import Image, ImageSequence, ImageTk  # type: ignore[import]

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

TRACK_START_X_RATIO = 0.10
TRACK_END_X_RATIO = 0.88
TRACK_Y_RATIO = 0.45
TEXT_Y_RATIO = 0.88
UPDATE_INTERVAL_MS = 500
GIF_FRAME_INTERVAL_MS = 100
DEFAULT_ITEM_COUNT = 8
SUPPORTED_NATIVE_FORMATS: frozenset[str] = frozenset({".png", ".gif"})
FALLBACK_CHAR_COLOR = "red"
FALLBACK_GOAL_COLOR = "blue"
FALLBACK_ITEM_COLOR = "yellow"
CHAR_SPRITE_SIZE: tuple[int, int] = (64, 64)
GOAL_SPRITE_SIZE: tuple[int, int] = (90, 110)
ITEM_SPRITE_SIZE: tuple[int, int] = (36, 36)
READY_SPRITE_SIZE: tuple[int, int] = (200, 200)


@dataclass
class NagScreenConfig:
    """Sprite-Konfiguration aus dem nag_screen:-Abschnitt der screentime.yaml.

    Attributes:
        character_sprite: Pfad zum Charakter-Sprite. None → rotes Fallback-Rechteck.
        goal_sprite: Pfad zum Ziel-Sprite. None → blaues Fallback-Rechteck.
        item_sprite: Pfad zum Item-Sprite. None → gelbe Fallback-Kreise.
        item_count: Anzahl der Items auf der Strecke.
        character_size: Zielgröße des Charakter-Sprites in Pixeln.
        goal_size: Zielgröße des Ziel-Sprites in Pixeln.
        item_size: Zielgröße der Item-Sprites in Pixeln.
        character_offset_y: Vertikaler Versatz des Charakter-Sprites in Pixeln (positiv = nach unten).
        goal_offset_y: Vertikaler Versatz des Ziel-Sprites in Pixeln.
        item_offset_y: Vertikaler Versatz der Item-Sprites in Pixeln.
    """

    character_sprite: Path | None
    goal_sprite: Path | None
    item_sprite: Path | None
    item_count: int = field(default=DEFAULT_ITEM_COUNT)
    character_size: tuple[int, int] = field(default=CHAR_SPRITE_SIZE)
    goal_size: tuple[int, int] = field(default=GOAL_SPRITE_SIZE)
    item_size: tuple[int, int] = field(default=ITEM_SPRITE_SIZE)
    character_offset_y: int = 0
    goal_offset_y: int = 0
    item_offset_y: int = 0
    ready_sprite: Path | None = None
    ready_sprite_size: tuple[int, int] = field(default=READY_SPRITE_SIZE)
    ready_sprite_offset_y: int = 0


@dataclass
class _SpriteAnim:
    """Kapselt Frames und Zustand einer Sprite-Animation.

    Attributes:
        frames: Geladene PhotoImage-Objekte. Länge 1 = statisch, >1 = animiert.
    """

    frames: list[tk.PhotoImage]
    _idx: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("frames darf nicht leer sein")

    @property
    def current(self) -> tk.PhotoImage:
        """Gibt das aktuelle Frame zurück."""
        return self.frames[self._idx]

    @property
    def is_animated(self) -> bool:
        """True wenn mehr als ein Frame vorhanden."""
        return len(self.frames) > 1

    def advance(self) -> None:
        """Wechselt zum nächsten Frame (wraparound)."""
        self._idx = (self._idx + 1) % len(self.frames)


def _pluralize(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def format_remaining(remaining: float) -> str:
    """Formatiert verbleibende Sekunden als lesbare deutsche Zeitangabe.

    Args:
        remaining: Verbleibende Zeit in Sekunden (> 0).

    Returns:
        Z.B. "Noch 1 Stunde 30 Minuten", "Noch 5 Minuten", "Noch 1 Sekunde".
        Nullwerte werden nicht angezeigt; bei Stunden werden Sekunden weggelassen.
    """
    total = int(remaining)
    if total == 0:
        return ""
    hours = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60

    if hours > 0:
        parts = [_pluralize(hours, "Stunde", "Stunden")]
        if mins > 0:
            parts.append(_pluralize(mins, "Minute", "Minuten"))
        return "Noch " + " ".join(parts)

    if mins > 0:
        parts = [_pluralize(mins, "Minute", "Minuten")]
        if secs > 0:
            parts.append(_pluralize(secs, "Sekunde", "Sekunden"))
        return "Noch " + " ".join(parts)

    return "Noch " + _pluralize(secs, "Sekunde", "Sekunden")


def calculate_progress(elapsed_seconds: float, cooldown_seconds: float) -> float:
    """Berechnet den Fortschritt als Wert zwischen 0.0 (Start) und 1.0 (fertig).

    Args:
        elapsed_seconds: Bisher vergangene Cooldown-Zeit.
        cooldown_seconds: Gesamte Cooldown-Dauer.

    Returns:
        Fortschritt zwischen 0.0 und 1.0 (gecappt).
    """
    if cooldown_seconds <= 0:
        return 1.0
    return min(1.0, max(0.0, elapsed_seconds / cooldown_seconds))


def read_cooldown_remaining(state_path: Path, cooldown_seconds: float) -> float | None:
    """Liest die verbleibende Cooldown-Zeit aus der State-Datei.

    Args:
        state_path: Pfad zur screentime-state.json.
        cooldown_seconds: Konfigurierte Gesamtdauer des Cooldowns.

    Returns:
        Verbleibende Sekunden (>= 0.0) oder None wenn kein aktiver Cooldown.
    """
    try:
        raw = json.loads(state_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    started_str: str | None = raw.get("cooldown_started_at")
    if not started_str:
        return None

    started = datetime.fromisoformat(started_str)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return max(0.0, cooldown_seconds - elapsed)


def parse_nag_screen_config(config_path: Path) -> NagScreenConfig:
    """Liest die NagScreenConfig aus dem nag_screen:-Abschnitt der YAML-Datei.

    Args:
        config_path: Pfad zur screentime.yaml.

    Returns:
        NagScreenConfig mit aufgelösten Sprite-Pfaden (relativ zum config_path-Verzeichnis).
        Fehlende Felder erhalten Standardwerte.
    """
    try:
        raw = yaml.safe_load(config_path.read_text())
    except (FileNotFoundError, PermissionError, yaml.YAMLError) as e:
        print(f"Warnung: Config konnte nicht gelesen werden ({config_path}): {e}")
        return NagScreenConfig(
            character_sprite=None, goal_sprite=None, item_sprite=None
        )
    nag = (raw or {}).get("nag_screen") or {}
    base = config_path.parent

    def resolve(key: str) -> Path | None:
        val = nag.get(key)
        return (base / val) if val else None

    def resolve_size(key: str, default: tuple[int, int]) -> tuple[int, int]:
        val = nag.get(key)
        if val and len(val) == 2:
            return (int(val[0]), int(val[1]))
        return default

    return NagScreenConfig(
        character_sprite=resolve("character_sprite"),
        goal_sprite=resolve("goal_sprite"),
        item_sprite=resolve("item_sprite"),
        item_count=int(nag.get("item_count", DEFAULT_ITEM_COUNT)),
        character_size=resolve_size("character_size", CHAR_SPRITE_SIZE),
        goal_size=resolve_size("goal_size", GOAL_SPRITE_SIZE),
        item_size=resolve_size("item_size", ITEM_SPRITE_SIZE),
        character_offset_y=int(nag.get("character_offset_y", 0)),
        goal_offset_y=int(nag.get("goal_offset_y", 0)),
        item_offset_y=int(nag.get("item_offset_y", 0)),
        ready_sprite=resolve("ready_sprite"),
        ready_sprite_size=resolve_size("ready_sprite_size", READY_SPRITE_SIZE),
        ready_sprite_offset_y=int(nag.get("ready_sprite_offset_y", 0)),
    )


def _load_frames(path: Path | None, target_size: tuple[int, int]) -> _SpriteAnim | None:
    """Lädt alle Frames eines Sprites und gibt eine _SpriteAnim zurück.

    Unterstützt animierte und statische GIFs sowie alle Pillow-Formate.
    Ohne Pillow werden nur .gif und .png über tkinter native geladen.

    Args:
        path: Pfad zur Sprite-Datei oder None.
        target_size: Zielgröße (width, height) in Pixeln.

    Returns:
        _SpriteAnim mit einem oder mehreren Frames, oder None bei Fehler.
    """
    if path is None or not path.exists():
        return None

    if _PIL_AVAILABLE:
        return _load_frames_with_pil(path, target_size)

    if path.suffix.lower() in SUPPORTED_NATIVE_FORMATS:
        return _load_frames_native(path, target_size)

    print(f"Warnung: {path.suffix} nicht unterstützt ohne Pillow (pip install Pillow)")
    return None


def _load_frames_with_pil(
    path: Path, target_size: tuple[int, int]
) -> _SpriteAnim | None:
    """Lädt Frames via Pillow. Unterstützt animierte GIFs, APNG, WebP und alle Pillow-Formate."""
    try:
        img = Image.open(path)
        frames = [
            ImageTk.PhotoImage(frame.convert("RGBA").resize(target_size, Image.LANCZOS))
            for frame in ImageSequence.Iterator(img)
        ]
    except (OSError, SyntaxError) as e:
        print(f"Warnung: Sprite konnte nicht geladen werden ({path}): {e}")
        return None

    if not frames:
        return None
    return _SpriteAnim(frames=frames)


def _load_frames_native(path: Path, target_size: tuple[int, int]) -> _SpriteAnim | None:
    """Lädt Frames via tkinter native (nur .gif und .png, kein Pillow)."""
    if path.suffix.lower() == ".gif":
        return _load_gif_frames_native(path, target_size)

    try:
        photo = tk.PhotoImage(file=str(path))
        factor = max(
            1, min(photo.width() // target_size[0], photo.height() // target_size[1])
        )
        scaled = photo.subsample(factor) if factor > 1 else photo
        return _SpriteAnim(frames=[scaled])
    except tk.TclError:
        return None


def _load_gif_frames_native(
    path: Path, target_size: tuple[int, int]
) -> _SpriteAnim | None:
    """Extrahiert alle GIF-Frames via tkinter (gif -index N)."""
    frames: list[tk.PhotoImage] = []
    i = 0
    while True:
        try:
            frame = tk.PhotoImage(file=str(path), format=f"gif -index {i}")
            factor = max(
                1,
                min(frame.width() // target_size[0], frame.height() // target_size[1]),
            )
            frames.append(frame.subsample(factor) if factor > 1 else frame)
            i += 1
        except tk.TclError:
            if i == 0:
                return None  # Erster Frame fehlgeschlagen — kein Display oder ungültige Datei
            break  # TclError nach mindestens einem Frame = keine weiteren Frames

    if not frames:
        return None
    return _SpriteAnim(frames=frames)


class NagScreen:
    """Vollbild-tkinter-Fenster: Charakter gleitet auf Ziel zu, Items verschwinden beim Passieren."""

    def __init__(
        self,
        nag_config: NagScreenConfig,
        state_path: Path,
        cooldown_seconds: float,
        debug: bool = False,
    ) -> None:
        self._nag_config = nag_config
        self._debug = debug
        self._state_path = state_path
        self._cooldown_seconds = cooldown_seconds

        self._root = tk.Tk()
        self._root.attributes("-fullscreen", True)
        self._root.configure(bg="black")
        self._root.protocol(
            "WM_DELETE_WINDOW", lambda: None
        )  # Schließen per Button blockieren
        self._root.bind("<Escape>", self._on_escape)
        self._root.bind("<Alt-F4>", lambda e: "break")
        self._root.focus_force()

        self._root.update_idletasks()
        self._width = self._root.winfo_screenwidth()
        self._height = self._root.winfo_screenheight()

        self._canvas = tk.Canvas(
            self._root,
            width=self._width,
            height=self._height,
            bg="black",
            highlightthickness=0,
        )
        self._canvas.pack()

        self._char_anim = _load_frames(
            nag_config.character_sprite, nag_config.character_size
        )
        self._goal_anim = _load_frames(nag_config.goal_sprite, nag_config.goal_size)
        self._item_anim = _load_frames(nag_config.item_sprite, nag_config.item_size)
        self._ready_anim = _load_frames(
            nag_config.ready_sprite, nag_config.ready_sprite_size
        )
        self._is_ready: bool = False

        self._track_y = int(self._height * TRACK_Y_RATIO)
        self._char_y = self._track_y + nag_config.character_offset_y
        self._goal_y = self._track_y + nag_config.goal_offset_y
        self._item_y = self._track_y + nag_config.item_offset_y
        self._track_start_x = int(self._width * TRACK_START_X_RATIO)
        self._track_end_x = int(self._width * TRACK_END_X_RATIO)

        self._item_ids: list[int] = self._draw_items()
        self._char_id: int = self._draw_character(self._track_start_x)
        self._char_is_image = self._char_anim is not None
        self._goal_id: int = self._draw_goal()  # Goal zuletzt → liegt über Character
        self._text_id = self._canvas.create_text(
            self._width // 2,
            int(self._height * TEXT_Y_RATIO),
            text="",
            fill="white",
            font=("Arial", 36, "bold"),
        )
        self._ready_id: int = self._draw_ready()

        signal.signal(signal.SIGTERM, lambda *_: self._root.destroy())
        self._update()
        if any(
            a and a.is_animated
            for a in (
                self._char_anim,
                self._goal_anim,
                self._item_anim,
                self._ready_anim,
            )
        ):
            self._root.after(GIF_FRAME_INTERVAL_MS, self._tick_anims)

    def _track_x(self, ratio: float) -> int:
        return self._track_start_x + int(
            (self._track_end_x - self._track_start_x) * ratio
        )

    def _draw_goal(self) -> int:
        gx = self._track_end_x
        if self._goal_anim:
            return self._canvas.create_image(
                gx, self._goal_y, image=self._goal_anim.current, anchor="center"
            )
        return self._canvas.create_rectangle(
            gx - 30,
            self._goal_y - 40,
            gx + 30,
            self._goal_y + 40,
            fill=FALLBACK_GOAL_COLOR,
            outline="",
        )

    def _draw_items(self) -> list[int]:
        ids: list[int] = []
        n = self._nag_config.item_count
        for i in range(n):
            ratio = (i + 1) / (n + 1)
            x = self._track_x(ratio)
            if self._item_anim:
                item_id = self._canvas.create_image(
                    x, self._item_y, image=self._item_anim.current, anchor="center"
                )
            else:
                item_id = self._canvas.create_oval(
                    x - 10,
                    self._item_y - 10,
                    x + 10,
                    self._item_y + 10,
                    fill=FALLBACK_ITEM_COLOR,
                    outline="",
                )
            ids.append(item_id)
        return ids

    def _draw_character(self, x: int) -> int:
        if self._char_anim:
            return self._canvas.create_image(
                x, self._char_y, image=self._char_anim.current, anchor="center"
            )
        return self._canvas.create_rectangle(
            x - 20,
            self._char_y - 30,
            x + 20,
            self._char_y + 30,
            fill=FALLBACK_CHAR_COLOR,
            outline="",
        )

    def _draw_ready(self) -> int:
        """Erzeugt das Ready-Canvas-Element zentriert auf dem Bildschirm (initial versteckt)."""
        cx = self._width // 2
        cy = self._height // 2 + self._nag_config.ready_sprite_offset_y
        if self._ready_anim:
            return self._canvas.create_image(
                cx,
                cy,
                image=self._ready_anim.current,
                anchor="center",
                state="hidden",
            )
        return self._canvas.create_text(
            cx,
            cy,
            text="✓",
            fill="green",
            font=("Arial", 200, "bold"),
            state="hidden",
        )

    def _on_escape(self, _: tk.Event) -> None:
        """Schließt das Fenster per ESC – nur wenn der Cooldown noch läuft."""
        if not self._is_ready:
            self._root.destroy()

    def _show_ready(self) -> None:
        """Blendet Charakter, Ziel und Items aus und zeigt das Ready-Symbol."""
        self._is_ready = True
        self._canvas.itemconfigure(self._char_id, state="hidden")
        self._canvas.itemconfigure(self._goal_id, state="hidden")
        for item_id in self._item_ids:
            self._canvas.itemconfigure(item_id, state="hidden")
        self._canvas.itemconfigure(self._text_id, state="hidden")
        self._canvas.itemconfigure(self._ready_id, state="normal")

    def _tick_anims(self) -> None:
        """Cyclet animierte Sprite-Frames. Läuft als eigener after()-Timer."""
        try:
            if not self._root.winfo_exists():
                return
        except tk.TclError:
            return

        if self._char_anim and self._char_anim.is_animated:
            self._char_anim.advance()
            self._canvas.itemconfigure(self._char_id, image=self._char_anim.current)

        if self._goal_anim and self._goal_anim.is_animated:
            self._goal_anim.advance()
            self._canvas.itemconfigure(self._goal_id, image=self._goal_anim.current)

        if self._item_anim and self._item_anim.is_animated:
            self._item_anim.advance()
            for item_id in self._item_ids:
                if self._canvas.itemcget(item_id, "state") != "hidden":
                    self._canvas.itemconfigure(item_id, image=self._item_anim.current)

        if self._ready_anim and self._ready_anim.is_animated and self._is_ready:
            self._ready_anim.advance()
            self._canvas.itemconfigure(self._ready_id, image=self._ready_anim.current)

        self._root.after(GIF_FRAME_INTERVAL_MS, self._tick_anims)

    def _item_x(self, index: int) -> int:
        n = self._nag_config.item_count
        ratio = (index + 1) / (n + 1)
        return self._track_x(ratio)

    def _update(self) -> None:
        remaining = read_cooldown_remaining(self._state_path, self._cooldown_seconds)
        if self._debug:
            print(f"[nag_screen] update: remaining={remaining}", flush=True)
        if remaining is None or remaining <= 0:
            if self._debug:
                print(f"[nag_screen] ready: remaining={remaining}", flush=True)
            self._show_ready()
            return

        elapsed = self._cooldown_seconds - remaining
        progress = calculate_progress(elapsed, self._cooldown_seconds)
        char_x = self._track_x(progress)

        if self._char_is_image:
            self._canvas.coords(self._char_id, char_x, self._char_y)
        else:
            self._canvas.coords(
                self._char_id,
                char_x - 20,
                self._char_y - 30,
                char_x + 20,
                self._char_y + 30,
            )

        # Items bleiben dauerhaft verborgen — Progress ist monoton (0 → 1)
        for i, item_id in enumerate(self._item_ids):
            if char_x >= self._item_x(i):
                self._canvas.itemconfigure(item_id, state="hidden")

        self._canvas.itemconfigure(self._text_id, text=format_remaining(remaining))

        self._root.after(UPDATE_INTERVAL_MS, self._update)

    def run(self) -> None:
        """Startet die tkinter-Event-Loop (blockierend)."""
        self._root.mainloop()
        if self._debug:
            print("[nag_screen] mainloop beendet", flush=True)


def main() -> None:
    """Einstiegspunkt: parst Argumente und startet den Nag-Screen."""
    if not _TKINTER_AVAILABLE:
        print(
            "Fehler: tkinter nicht verfügbar. Bitte python3-tk installieren.",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Screentime Cooldown Nag-Screen")
    parser.add_argument(
        "--state-file", required=True, type=Path, help="Pfad zur screentime-state.json"
    )
    parser.add_argument(
        "--config-file", required=True, type=Path, help="Pfad zur screentime.yaml"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug-Ausgabe: zeigt remaining-Wert bei jedem Update",
    )
    args = parser.parse_args()

    try:
        raw = yaml.safe_load(args.config_file.read_text())
        cooldown_seconds = float(raw["cooldown_minutes"]) * 60
    except (FileNotFoundError, KeyError, TypeError, yaml.YAMLError) as e:
        print(f"Fehler: Config konnte nicht gelesen werden: {e}", file=sys.stderr)
        sys.exit(1)

    nag_config = parse_nag_screen_config(args.config_file)
    screen = NagScreen(nag_config, args.state_file, cooldown_seconds, debug=args.debug)
    screen.run()


if __name__ == "__main__":
    main()
