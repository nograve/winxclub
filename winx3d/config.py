"""Tunables, key bindings and the on-disk player profile.

Distances are in world units where 1 unit ~= 1 metre and Panda3D's default
Z-up coordinate system applies (X right, Y forward, Z up).
"""
from __future__ import annotations

import json
import os
import sys

TITLE = "Winx Club: Magic of Alfea"
VERSION = "1.0"

# --- Player movement ---------------------------------------------------------
WALK_SPEED = 7.0
RUN_SPEED = 12.5
FLY_SPEED = 13.0
TURN_RATE = 520.0          # degrees/sec the model turns toward its heading
GRAVITY = -26.0
JUMP_SPEED = 10.5
FLY_LIFT = 7.0             # upward speed while holding jump in fairy form
FLY_FALL_CLAMP = -3.0      # terminal velocity while gliding
COYOTE_TIME = 0.12
JUMP_BUFFER = 0.14
PLAYER_RADIUS = 0.75
PLAYER_HEIGHT = 2.6

# --- Camera ------------------------------------------------------------------
CAM_DISTANCE = 14.0
CAM_HEIGHT = 5.0
CAM_PITCH = -8.0
CAM_MIN_PITCH, CAM_MAX_PITCH = -55.0, 25.0
CAM_LAG = 8.0              # higher = snappier
MOUSE_SENS = 22.0
KEY_TURN_SPEED = 130.0

# --- Combat ------------------------------------------------------------------
MAX_HEALTH = 6
MAX_MAGIC = 100.0
MAGIC_REGEN = 11.0         # per second
BOLT_COST = 7.0            # sustainable fire; flying is the drain
BOLT_SPEED = 46.0
BOLT_LIFE = 1.6
BOLT_DAMAGE = 1.0
CHARGE_COST = 38.0
CHARGE_DAMAGE = 3.0
CHARGE_RADIUS = 9.0
FLY_DRAIN = 14.0           # magic per second while airborne under power
TRANSFORM_COST = 100.0
TRANSFORM_TIME = 14.0
INVULN_TIME = 1.1
START_LIVES = 3

# --- Presentation ------------------------------------------------------------
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1024, 768
LOW_WIDTH, LOW_HEIGHT = 640, 480


def _base_dir() -> str:
    if sys.platform.startswith("win"):
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, "winx-magic-of-alfea")


def user_dir() -> str:
    """Writable per-user directory for the profile and generated sounds."""
    path = _base_dir()
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.path.abspath("userdata")
        os.makedirs(path, exist_ok=True)
    return path


DEFAULTS = {
    "high_score": 0,
    "levels_cleared": 0,
    "last_fairy": "bloom",
    "sound": True,
    "music": True,
    "invert_y": False,
    "mouse_look": True,
}


def load_profile() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(os.path.join(user_dir(), "profile.json"), encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return data


def save_profile(data: dict) -> None:
    try:
        with open(os.path.join(user_dir(), "profile.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    except OSError:
        pass
