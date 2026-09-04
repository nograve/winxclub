"""Procedurally generated sound effects and music.

No audio files ship with the game.  Short WAVs are synthesised on first run
and cached in the user directory, then handed to Panda3D's audio manager.  If
no audio device is available the whole module degrades to silent no-ops rather
than taking the game down with it.
"""
from __future__ import annotations

import math
import os
import random
import struct
import wave

from . import config as C

RATE = 22050            # plenty for these effects, and kind to old sound cards
CACHE_VERSION = 2


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _write_wav(path: str, samples) -> None:
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(b"".join(
            struct.pack("<h", int(_clamp(s) * 32000)) for s in samples))


def _env(i: int, n: int, attack: float = 0.02, release: float = 0.5) -> float:
    """Simple attack/decay envelope, in fractions of the sound's length."""
    t = i / max(1, n - 1)
    if t < attack:
        return t / attack
    k = (t - attack) / max(1e-6, 1.0 - attack)
    return math.exp(-k / max(1e-6, release))


def _sweep(dur, f0, f1, kind="sine", release=0.4, noise=0.0, seed=1):
    n = int(RATE * dur)
    rng = random.Random(seed)
    phase = 0.0
    out = []
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        phase += 2.0 * math.pi * f / RATE
        if kind == "sine":
            v = math.sin(phase)
        elif kind == "square":
            v = 1.0 if math.sin(phase) >= 0.0 else -1.0
        elif kind == "saw":
            v = ((phase / math.pi) % 2.0) - 1.0
        else:
            v = math.sin(phase) + 0.5 * math.sin(phase * 2.02)
        if noise:
            v += rng.uniform(-1.0, 1.0) * noise
        out.append(v * _env(i, n, 0.02, release) * 0.55)
    return out


def _noise_hit(dur, release=0.25, tone=140.0, seed=2):
    n = int(RATE * dur)
    rng = random.Random(seed)
    out = []
    phase = 0.0
    for i in range(n):
        phase += 2.0 * math.pi * tone / RATE
        v = rng.uniform(-1.0, 1.0) * 0.7 + math.sin(phase) * 0.5
        out.append(v * _env(i, n, 0.005, release) * 0.6)
    return out


def _chord(dur, freqs, release=0.5, kind="sine"):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        v = 0.0
        for f in freqs:
            v += math.sin(2.0 * math.pi * f * i / RATE)
        if kind == "square":
            v = 1.0 if v >= 0 else -1.0
        out.append(v / max(1, len(freqs)) * _env(i, n, 0.03, release) * 0.55)
    return out


# --- Music -------------------------------------------------------------------
# A short loop per level, built from a scale and a simple bass/lead pattern.
NOTE = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.00,
        "A": 440.00, "B": 493.88}


def _music(scale, bass_root, tempo=112.0, bars=8, seed=5, bright=True):
    rng = random.Random(seed)
    beat = 60.0 / tempo
    total = int(RATE * beat * 4 * bars)
    out = [0.0] * total
    steps = bars * 8                    # eighth notes
    step_len = int(RATE * beat * 0.5)

    for s in range(steps):
        start = s * step_len
        # Bass: root on the downbeat, fifth halfway through the bar.
        if s % 4 == 0:
            f = bass_root * (1.5 if (s // 4) % 2 == 1 else 1.0)
            for i in range(min(step_len * 3, total - start)):
                t = i / (step_len * 3)
                v = math.sin(2.0 * math.pi * f * i / RATE)
                v += 0.4 * math.sin(4.0 * math.pi * f * i / RATE)
                out[start + i] += v * math.exp(-t * 2.6) * 0.22
        # Lead: a wandering line over the scale.
        if rng.random() < (0.75 if bright else 0.6):
            f = scale[rng.randrange(len(scale))] * (2.0 if rng.random() < 0.35
                                                    else 1.0)
            dur = step_len * rng.choice((1, 1, 2))
            for i in range(min(dur, total - start)):
                t = i / dur
                v = math.sin(2.0 * math.pi * f * i / RATE)
                v += 0.25 * math.sin(6.0 * math.pi * f * i / RATE)
                out[start + i] += v * math.exp(-t * 3.2) * 0.16
        # Percussion: kick on 1 and 3, hat on the offbeats.
        if s % 4 == 0:
            for i in range(min(int(RATE * 0.12), total - start)):
                t = i / (RATE * 0.12)
                out[start + i] += math.sin(2.0 * math.pi * (90 - 50 * t) *
                                           i / RATE) * math.exp(-t * 6) * 0.30
        if s % 2 == 1:
            for i in range(min(int(RATE * 0.05), total - start)):
                t = i / (RATE * 0.05)
                out[start + i] += rng.uniform(-1, 1) * math.exp(-t * 22) * 0.10
    return [_clamp(v) for v in out]


C_MAJOR = [NOTE["C"], NOTE["D"], NOTE["E"], NOTE["G"], NOTE["A"]]
A_MINOR = [NOTE["A"] / 2, NOTE["C"], NOTE["D"], NOTE["E"], NOTE["G"]]
D_MINOR = [NOTE["D"], NOTE["F"], NOTE["G"], NOTE["A"], NOTE["C"] * 2]

GENERATORS = {
    "shoot": lambda: _sweep(0.16, 900, 1750, "sine", 0.20),
    "shoot_big": lambda: _sweep(0.34, 320, 1100, "rich", 0.30),
    "hit": lambda: _noise_hit(0.16, 0.20, 190.0, seed=11),
    "enemy_die": lambda: _sweep(0.42, 620, 90, "square", 0.35, noise=0.18,
                                seed=13),
    "hurt": lambda: _sweep(0.34, 420, 150, "saw", 0.30, noise=0.10, seed=17),
    "jump": lambda: _sweep(0.20, 380, 820, "sine", 0.28),
    "gem": lambda: _chord(0.34, (880, 1318.5), 0.35),
    "heart": lambda: _chord(0.46, (523.25, 659.25, 783.99), 0.45),
    "transform": lambda: _chord(1.20, (392, 523.25, 659.25, 987.77), 0.9,
                                "sine"),
    "portal": lambda: _chord(1.00, (261.63, 392.0, 523.25), 0.8),
    "menu": lambda: _sweep(0.10, 700, 900, "square", 0.18),
    "victory": lambda: _chord(1.60, (523.25, 659.25, 783.99, 1046.5), 1.2),
    "defeat": lambda: _chord(1.60, (196.0, 233.08, 293.66), 1.2),
    "music_alfea": lambda: _music(C_MAJOR, 130.81, 118.0, 8, 5, True),
    "music_wood": lambda: _music(A_MINOR, 110.0, 100.0, 8, 9, False),
    "music_tower": lambda: _music(D_MINOR, 73.42, 132.0, 8, 21, False),
    "music_menu": lambda: _music(C_MAJOR, 98.0, 92.0, 4, 33, True),
}


def ensure_sounds(verbose: bool = False) -> str:
    """Synthesise any missing WAVs into the cache directory; return its path."""
    out_dir = os.path.join(C.user_dir(), "sfx-v%d" % CACHE_VERSION)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        return out_dir
    for name, gen in GENERATORS.items():
        path = os.path.join(out_dir, name + ".wav")
        if os.path.exists(path):
            continue
        if verbose:
            print("  synthesising %s.wav" % name)
        try:
            _write_wav(path, gen())
        except OSError:
            pass
    return out_dir


class Audio:
    """Thin wrapper over Panda3D's audio managers, safe when there is none."""

    def __init__(self, base, profile: dict) -> None:
        self.base = base
        self.enabled_sfx = bool(profile.get("sound", True))
        self.enabled_music = bool(profile.get("music", True))
        self.sounds: dict[str, object] = {}
        self.music: dict[str, object] = {}
        self.current_music = None
        self.dir = ensure_sounds()
        self._load()

    def _load(self) -> None:
        from panda3d.core import Filename
        for name in GENERATORS:
            path = os.path.join(self.dir, name + ".wav")
            if not os.path.exists(path):
                continue
            pf = Filename.fromOsSpecific(path)
            try:
                if name.startswith("music_"):
                    snd = self.base.loader.loadMusic(pf)
                    if snd:
                        snd.setLoop(True)
                        snd.setVolume(0.42)
                        self.music[name] = snd
                else:
                    snd = self.base.loader.loadSfx(pf)
                    if snd:
                        snd.setVolume(0.65)
                        self.sounds[name] = snd
            except Exception:
                # A missing or broken audio device must never be fatal.
                continue

    def play(self, name: str, volume: float | None = None) -> None:
        if not self.enabled_sfx:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            if volume is not None:
                snd.setVolume(volume)
            snd.play()
        except Exception:
            pass

    def play_music(self, name: str) -> None:
        if self.current_music == name:
            return
        self.stop_music()
        self.current_music = name
        if not self.enabled_music:
            return
        snd = self.music.get(name)
        if snd is not None:
            try:
                snd.play()
            except Exception:
                pass

    def stop_music(self) -> None:
        if self.current_music:
            snd = self.music.get(self.current_music)
            if snd is not None:
                try:
                    snd.stop()
                except Exception:
                    pass
        self.current_music = None

    def set_sfx(self, on: bool) -> None:
        self.enabled_sfx = on

    def set_music(self, on: bool) -> None:
        self.enabled_music = on
        if not on:
            name = self.current_music
            self.stop_music()
            self.current_music = name
        else:
            name = self.current_music
            self.current_music = None
            if name:
                self.play_music(name)
