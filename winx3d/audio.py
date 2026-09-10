"""Procedurally generated sound effects and music.

No audio files ship with the game.  Short WAVs are synthesised on first run
and cached in the user directory, then handed to Panda3D's audio manager.  If
no audio device is available the whole module degrades to silent no-ops rather
than taking the game down with it.
"""
from __future__ import annotations

import array
import math
import os
import random
import wave

from . import config as C

RATE = 22050            # plenty for these effects, and kind to old sound cards
AMBIENT_RATE = 11025    # ambience is a quiet bed; half rate is inaudible here
CACHE_VERSION = 3


def _clamp(v: float) -> float:
    return -1.0 if v < -1.0 else (1.0 if v > 1.0 else v)


def _write_wav(path: str, samples, rate=RATE) -> None:
    """Write a mono 16-bit WAV. Uses array() rather than per-sample packing,
    which is what keeps first-run generation to a few seconds."""
    buf = array.array("h", (int(_clamp(s) * 31000) for s in samples))
    if os.sys.byteorder == "big":
        buf.byteswap()
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(buf.tobytes())


# ---------------------------------------------------------------------------
# Oscillators and instrument voices
# ---------------------------------------------------------------------------
def _wave(kind: str, phase: float) -> float:
    if kind == "sine":
        return math.sin(phase)
    if kind == "square":
        return 1.0 if math.sin(phase) >= 0.0 else -1.0
    if kind == "pulse":
        return 1.0 if (phase % TAU) < TAU * 0.25 else -1.0
    if kind == "saw":
        return ((phase / math.pi) % 2.0) - 1.0
    if kind == "tri":
        return 2.0 / math.pi * math.asin(max(-1.0, min(1.0, math.sin(phase))))
    return math.sin(phase)


TAU = math.pi * 2.0

# Each voice is a wave shape, a set of harmonics (multiplier, gain), an
# attack in seconds, a decay rate, and an optional vibrato (rate, depth).
VOICES = {
    "bell":  ("sine", ((1.0, 1.0), (2.76, 0.36), (5.40, 0.16)), 0.004, 2.6, None),
    "pluck": ("saw", ((1.0, 0.75), (2.0, 0.28), (3.0, 0.12)), 0.003, 5.0, None),
    "flute": ("sine", ((1.0, 1.0), (2.0, 0.14)), 0.070, 0.9, (5.2, 0.006)),
    "pad":   ("sine", ((1.0, 0.8), (1.005, 0.7), (2.0, 0.18)), 0.22, 0.5, (3.0, 0.003)),
    "brass": ("saw", ((1.0, 0.7), (2.0, 0.40), (3.0, 0.20), (4.0, 0.10)),
              0.035, 1.1, (5.5, 0.004)),
    "chip":  ("square", ((1.0, 0.8),), 0.002, 3.2, None),
    "glass": ("sine", ((1.0, 1.0), (3.0, 0.25), (7.2, 0.08)), 0.006, 1.8, None),
    "bass":  ("sine", ((1.0, 1.0), (0.5, 0.45), (2.0, 0.22)), 0.006, 2.4, None),
    "subsaw": ("saw", ((1.0, 0.6), (0.5, 0.5), (2.0, 0.2)), 0.02, 1.6, None),
}


def _note(buf, rate, start: int, dur: int, freq: float, voice: str,
          gain: float) -> None:
    """Render one note additively into ``buf``."""
    shape, harmonics, attack, decay, vib = VOICES[voice]
    n = min(dur, len(buf) - start)
    if n <= 0:
        return
    atk = max(1, int(attack * rate))
    for i in range(n):
        t = i / rate
        if i < atk:
            env = i / atk
        else:
            env = math.exp(-(t - attack) * decay)
            # Stop once the tail is inaudible - but only after the attack,
            # which necessarily starts at zero.
            if env < 0.0008:
                break
        f = freq
        if vib:
            f *= 1.0 + math.sin(TAU * vib[0] * t) * vib[1]
        v = 0.0
        for mult, amp in harmonics:
            v += _wave(shape, TAU * f * mult * t) * amp
        buf[start + i] += v * env * gain


def _perc(buf, rate, start: int, kind: str, gain: float, rng) -> None:
    dur = {"kick": 0.16, "hat": 0.05, "snare": 0.13, "tom": 0.18}[kind]
    n = min(int(dur * rate), len(buf) - start)
    for i in range(max(0, n)):
        t = i / dur / rate
        if kind == "kick":
            f = 105.0 - 62.0 * t
            v = math.sin(TAU * f * i / rate) * math.exp(-t * 5.5)
        elif kind == "tom":
            f = 190.0 - 90.0 * t
            v = math.sin(TAU * f * i / rate) * math.exp(-t * 4.0)
        elif kind == "hat":
            v = rng.uniform(-1, 1) * math.exp(-t * 20.0)
        else:
            v = (rng.uniform(-1, 1) * 0.7 +
                 math.sin(TAU * 190.0 * i / rate) * 0.4) * math.exp(-t * 11.0)
        buf[start + i] += v * gain


# ---------------------------------------------------------------------------
# Scales
# ---------------------------------------------------------------------------
def _scale(root: float, steps) -> list:
    return [root * (2.0 ** (s / 12.0)) for s in steps]


MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)
PENT_MAJ = (0, 2, 4, 7, 9)
PENT_MIN = (0, 3, 5, 7, 10)
DORIAN = (0, 2, 3, 5, 7, 9, 10)
LYDIAN = (0, 2, 4, 6, 7, 9, 11)

# Note names to frequencies, octave 3.
N = {"C": 130.81, "D": 146.83, "E": 164.81, "F": 174.61, "G": 196.00,
     "A": 220.00, "B": 246.94}


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------
class Track:
    """A realm's theme. Rendered once on first run and cached as a WAV."""

    def __init__(self, root, steps, tempo, lead, bass, *, bars=8, seed=1,
                 perc="light", density=0.72, arp=False, lead_octave=2.0,
                 chords=False, gain=1.0):
        self.root = root
        self.steps = steps
        self.tempo = tempo
        self.lead = lead
        self.bass = bass
        self.bars = bars
        self.seed = seed
        self.perc = perc
        self.density = density
        self.arp = arp
        self.lead_octave = lead_octave
        self.chords = chords
        self.gain = gain

    def render(self):
        rng = random.Random(self.seed)
        notes = _scale(self.root, self.steps)
        beat = 60.0 / self.tempo
        step_len = int(RATE * beat * 0.5)          # eighth notes
        steps = self.bars * 8
        buf = [0.0] * (steps * step_len + int(RATE * 1.2))

        # Bass: root on the downbeat, fifth in the second half of each bar.
        for s in range(0, steps, 4):
            degree = 0 if (s // 4) % 2 == 0 else 4
            _note(buf, RATE, s * step_len, step_len * 4,
                  notes[degree % len(notes)] * 0.5, self.bass, 0.30 * self.gain)

        # Pad chords under the whole bar, for the tracks that want them.
        if self.chords:
            for s in range(0, steps, 8):
                for degree in (0, 2, 4):
                    _note(buf, RATE, s * step_len, step_len * 8,
                          notes[degree % len(notes)], "pad", 0.10 * self.gain)

        # Lead: an arpeggio, or a wandering line over the scale.
        if self.arp:
            pattern = [0, 2, 4, 2, 4, 6, 4, 2]
            for s in range(steps):
                degree = pattern[s % len(pattern)] + (2 if (s // 16) % 2 else 0)
                _note(buf, RATE, s * step_len, step_len,
                      notes[degree % len(notes)] * self.lead_octave,
                      self.lead, 0.17 * self.gain)
        else:
            degree = 0
            for s in range(steps):
                if rng.random() > self.density:
                    continue
                degree = max(0, min(len(notes) - 1,
                                    degree + rng.choice((-2, -1, -1, 1, 1, 2))))
                octave = self.lead_octave * (2.0 if rng.random() < 0.18 else 1.0)
                dur = step_len * rng.choice((1, 1, 2, 3))
                _note(buf, RATE, s * step_len, dur,
                      notes[degree] * octave, self.lead, 0.18 * self.gain)

        # Percussion.
        if self.perc != "none":
            heavy = self.perc == "heavy"
            for s in range(steps):
                if s % 4 == 0:
                    _perc(buf, RATE, s * step_len, "kick",
                          0.34 if heavy else 0.24, rng)
                elif heavy and s % 8 == 4:
                    _perc(buf, RATE, s * step_len, "snare", 0.26, rng)
                if s % 2 == 1:
                    _perc(buf, RATE, s * step_len, "hat",
                          0.13 if heavy else 0.08, rng)
                if heavy and s % 16 == 14:
                    _perc(buf, RATE, s * step_len, "tom", 0.22, rng)
        return buf


# One theme per realm and per shared location, plus the two siege moods.
TRACKS = {
    # --- menus and Magix ----------------------------------------------------
    "menu": Track(N["C"], PENT_MAJ, 90, "pad", "bass", perc="none",
                  density=0.45, chords=True, seed=3),
    "alfea": Track(N["C"], MAJOR, 118, "bell", "bass", seed=5, density=0.75),
    "swamp": Track(N["D"], MINOR, 92, "pluck", "subsaw", perc="light",
                   density=0.5, seed=9, gain=0.95),
    "cloudtower": Track(N["D"], MINOR, 132, "subsaw", "bass", perc="heavy",
                        density=0.8, seed=21),
    "roccaluce": Track(N["A"], MINOR, 78, "glass", "pad", perc="none",
                       density=0.45, chords=True, seed=27, lead_octave=4.0),
    "redfountain": Track(N["G"], MINOR, 124, "brass", "bass", perc="heavy",
                         density=0.8, seed=31),
    "pixievillage": Track(N["G"], PENT_MAJ, 140, "bell", "pluck",
                          density=0.85, seed=37, lead_octave=4.0),
    # --- home realms --------------------------------------------------------
    "gardenia": Track(N["C"], MAJOR, 104, "pluck", "bass", density=0.65,
                      seed=41),
    "solaria": Track(N["D"], LYDIAN, 116, "brass", "bass", perc="heavy",
                     density=0.75, chords=True, seed=43),
    "lynphea": Track(N["F"], PENT_MAJ, 84, "flute", "pad", perc="light",
                     density=0.55, chords=True, seed=47),
    "melody": Track(N["A"], DORIAN, 126, "pluck", "bass", perc="heavy",
                    density=0.9, chords=True, seed=53, bars=12),
    "zenith": Track(N["E"], MINOR, 144, "chip", "subsaw", perc="heavy",
                    arp=True, seed=59),
    "andros": Track(N["G"], MAJOR, 96, "pad", "bass", perc="light",
                    density=0.6, chords=True, seed=61, lead_octave=3.0),
    # --- the war ------------------------------------------------------------
    "siege": Track(N["D"], MINOR, 88, "brass", "subsaw", perc="heavy",
                   density=0.55, chords=True, seed=67),
    "battle": Track(N["D"], MINOR, 150, "subsaw", "bass", perc="heavy",
                    density=0.9, seed=71),
}


# ---------------------------------------------------------------------------
# Ambience - a quiet looping bed under each kind of place
# ---------------------------------------------------------------------------
def _ambience(kind: str, seconds=8.0, seed=1):
    rng = random.Random(seed)
    rate = AMBIENT_RATE
    n = int(rate * seconds)
    buf = [0.0] * n
    # A slow filtered-noise bed, shaped differently per environment.
    smooth = 0.0
    for i in range(n):
        t = i / rate
        target = rng.uniform(-1, 1)
        smooth += (target - smooth) * (0.02 if kind != "machine" else 0.4)
        env = 0.5 + 0.5 * math.sin(TAU * 0.12 * t + seed)
        if kind == "day":
            buf[i] = smooth * 0.10 * env
        elif kind == "forest":
            buf[i] = smooth * 0.13 * env
        elif kind == "swamp":
            buf[i] = smooth * 0.09 + math.sin(TAU * 47.0 * t) * 0.05
        elif kind == "ice":
            buf[i] = smooth * 0.07 * env + math.sin(TAU * 880.0 * t) * 0.012 * env
        elif kind == "machine":
            buf[i] = (math.sin(TAU * 60.0 * t) * 0.07 +
                      math.sin(TAU * 120.0 * t) * 0.03 + smooth * 0.03)
        elif kind == "water":
            buf[i] = smooth * 0.14 * (0.4 + 0.6 * abs(math.sin(TAU * 0.22 * t)))
        else:                                    # dark halls
            buf[i] = (math.sin(TAU * 55.0 * t) * 0.06 +
                      math.sin(TAU * 82.5 * t) * 0.03 + smooth * 0.04)

    # Occasional incidents on top: birds, drips, beeps, distant tones.
    events = {"day": ("bird", 9), "forest": ("bird", 12), "swamp": ("drip", 10),
              "ice": ("creak", 6), "machine": ("beep", 14),
              "water": ("drip", 7), "dark": ("moan", 5)}
    kind_ev, count = events.get(kind, ("drip", 6))
    for _ in range(count):
        at = int(rng.uniform(0.2, seconds - 1.0) * rate)
        if kind_ev == "bird":
            f0, f1, dur, gain = rng.uniform(1800, 2900), rng.uniform(2200, 3400), 0.09, 0.10
        elif kind_ev == "beep":
            f0 = f1 = rng.choice((880.0, 1320.0, 1760.0))
            dur, gain = 0.05, 0.07
        elif kind_ev == "creak":
            f0, f1, dur, gain = rng.uniform(200, 320), rng.uniform(120, 200), 0.5, 0.06
        elif kind_ev == "moan":
            f0, f1, dur, gain = rng.uniform(70, 110), rng.uniform(50, 80), 1.2, 0.09
        else:
            f0, f1, dur, gain = rng.uniform(700, 1300), rng.uniform(300, 600), 0.18, 0.08
        m = int(dur * rate)
        for i in range(m):
            if at + i >= n:
                break
            k = i / m
            f = f0 + (f1 - f0) * k
            buf[at + i] += (math.sin(TAU * f * i / rate) *
                            math.exp(-k * 3.0) * gain)

    # Cross-fade the tail into the head so the loop does not click.
    fade = int(rate * 0.35)
    for i in range(fade):
        k = i / fade
        buf[i] = buf[i] * k + buf[n - fade + i] * (1.0 - k)
    return buf[:n - fade]


AMBIENCE = ("day", "forest", "swamp", "ice", "machine", "water", "dark")


# ---------------------------------------------------------------------------
# Elemental sound effects - each fairy's magic sounds like her element
# ---------------------------------------------------------------------------
ELEMENTS = {
    #          wave      f0     f1   dur   noise
    "bloom":  ("saw",    260,  1150, 0.30, 0.30),   # dragon flame
    "stella": ("sine",   900,  2100, 0.24, 0.02),   # sunlight
    "flora":  ("tri",    420,   760, 0.28, 0.10),   # a growing vine
    "musa":   ("square", 640,  1280, 0.22, 0.03),   # a sound wave
    "tecna":  ("pulse", 1500,   700, 0.16, 0.02),   # a data pulse
    "aisha":  ("sine",   300,   980, 0.30, 0.08),   # rising water
}


def _element_shot(key: str):
    shape, f0, f1, dur, noise = ELEMENTS[key]
    rng = random.Random(abs(hash(key)) & 0xffff)
    n = int(RATE * dur)
    out = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        phase += TAU * f / RATE
        v = _wave(shape, phase) + _wave("sine", phase * 2.01) * 0.3
        if noise:
            v += rng.uniform(-1, 1) * noise * (1.0 - t)
        out[i] = v * math.exp(-t * 3.4) * 0.5
    return out


def _element_hit(key: str):
    shape, f0, f1, dur, noise = ELEMENTS[key]
    rng = random.Random((abs(hash(key)) >> 8) & 0xffff)
    n = int(RATE * dur * 0.75)
    out = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / n
        # Impacts fall rather than rise - the mirror of the shot.
        f = f1 * 0.7 + (f0 * 0.5 - f1 * 0.7) * t
        phase += TAU * f / RATE
        v = _wave(shape, phase) * 0.7 + rng.uniform(-1, 1) * (0.25 + noise)
        out[i] = v * math.exp(-t * 6.0) * 0.55
    return out


# ---------------------------------------------------------------------------
# Generic cues
# ---------------------------------------------------------------------------
def _sweep(dur, f0, f1, kind="sine", release=0.4, noise=0.0, seed=1):
    n = int(RATE * dur)
    rng = random.Random(seed)
    phase = 0.0
    out = []
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        phase += TAU * f / RATE
        v = _wave(kind, phase)
        if noise:
            v += rng.uniform(-1.0, 1.0) * noise
        out.append(v * math.exp(-t / max(1e-6, release)) * 0.5)
    return out


def _chord(dur, freqs, release=0.5, voice="bell"):
    n = int(RATE * dur)
    buf = [0.0] * n
    for f in freqs:
        _note(buf, RATE, 0, n, f, voice, 0.8 / max(1, len(freqs)))
    return buf


def _noise_hit(dur, release=0.25, tone=140.0, seed=2):
    rng = random.Random(seed)
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / n
        v = rng.uniform(-1.0, 1.0) * 0.7 + math.sin(TAU * tone * i / RATE) * 0.5
        out.append(v * math.exp(-t / max(1e-6, release)) * 0.55)
    return out


GENERATORS = {
    "shoot": lambda: _sweep(0.16, 900, 1750, "sine", 0.20),
    "shoot_big": lambda: _sweep(0.34, 320, 1100, "saw", 0.30, noise=0.15),
    "hit": lambda: _noise_hit(0.16, 0.20, 190.0, seed=11),
    "enemy_die": lambda: _sweep(0.42, 620, 90, "square", 0.35, noise=0.18,
                                seed=13),
    "hurt": lambda: _sweep(0.34, 420, 150, "saw", 0.30, noise=0.10, seed=17),
    "jump": lambda: _sweep(0.20, 380, 820, "sine", 0.28),
    "gem": lambda: _chord(0.34, (880, 1318.5), 0.35, "bell"),
    "heart": lambda: _chord(0.46, (523.25, 659.25, 783.99), 0.45, "bell"),
    "transform": lambda: _chord(1.20, (392, 523.25, 659.25, 987.77), 0.9,
                                "glass"),
    "portal": lambda: _chord(1.00, (261.63, 392.0, 523.25), 0.8, "pad"),
    "menu": lambda: _sweep(0.10, 700, 900, "square", 0.18),
    "victory": lambda: _chord(1.60, (523.25, 659.25, 783.99, 1046.5), 1.2,
                              "bell"),
    "defeat": lambda: _chord(1.60, (196.0, 233.08, 293.66), 1.2, "pad"),
}

for _k in ELEMENTS:                       # each fairy's magic, and its impact
    GENERATORS["shoot_" + _k] = (lambda k: lambda: _element_shot(k))(_k)
    GENERATORS["hit_" + _k] = (lambda k: lambda: _element_hit(k))(_k)
for _k, _track in TRACKS.items():         # one theme per realm
    GENERATORS["music_" + _k] = (lambda t: lambda: t.render())(_track)
for _k in AMBIENCE:                       # one bed per kind of place
    GENERATORS["ambience_" + _k] = (
        lambda k: lambda: _ambience(k, seed=abs(hash(k)) & 0xff))(_k)


def is_stream(name: str) -> bool:
    """Music and ambience stream and loop; everything else is a one-shot."""
    return name.startswith("music_") or name.startswith("ambience_")


def rate_for(name: str) -> int:
    return AMBIENT_RATE if name.startswith("ambience_") else RATE


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
            _write_wav(path, gen(), rate_for(name))
        except OSError:
            pass
    return out_dir


class Audio:
    """Thin wrapper over Panda3D's audio managers, safe when there is none.

    Three channels: one-shot effects, a music track, and a quiet ambient bed
    that runs underneath it.
    """

    def __init__(self, base, profile: dict) -> None:
        self.base = base
        self.enabled_sfx = bool(profile.get("sound", True))
        self.enabled_music = bool(profile.get("music", True))
        self.sounds: dict[str, object] = {}
        self.streams: dict[str, object] = {}
        self.current_music = None
        self.current_ambience = None
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
                if is_stream(name):
                    snd = self.base.loader.loadMusic(pf)
                    if snd:
                        snd.setLoop(True)
                        snd.setVolume(0.20 if name.startswith("ambience_")
                                      else 0.42)
                        self.streams[name] = snd
                else:
                    snd = self.base.loader.loadSfx(pf)
                    if snd:
                        snd.setVolume(0.65)
                        self.sounds[name] = snd
            except Exception:
                # A missing or broken audio device must never be fatal.
                continue

    # -- one-shots ----------------------------------------------------------
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

    def play_variant(self, base_name: str, key: str,
                     volume: float | None = None) -> None:
        """Play ``base_key`` if it exists, else fall back to ``base``."""
        if ("%s_%s" % (base_name, key)) in self.sounds:
            self.play("%s_%s" % (base_name, key), volume)
        else:
            self.play(base_name, volume)

    # -- streams ------------------------------------------------------------
    def _swap(self, attr: str, name: str | None) -> None:
        current = getattr(self, attr)
        if current == name:
            return
        if current:
            snd = self.streams.get(current)
            if snd is not None:
                try:
                    snd.stop()
                except Exception:
                    pass
        setattr(self, attr, name)
        if name and self.enabled_music:
            snd = self.streams.get(name)
            if snd is not None:
                try:
                    snd.play()
                except Exception:
                    pass

    def play_music(self, name: str) -> None:
        self._swap("current_music", name)

    def play_ambience(self, name: str | None) -> None:
        self._swap("current_ambience", name)

    def stop_music(self) -> None:
        self._swap("current_music", None)

    def stop_all_streams(self) -> None:
        self.stop_music()
        self.play_ambience(None)

    # -- toggles ------------------------------------------------------------
    def set_sfx(self, on: bool) -> None:
        self.enabled_sfx = on

    def set_music(self, on: bool) -> None:
        self.enabled_music = on
        music, ambience = self.current_music, self.current_ambience
        for attr, name in (("current_music", music),
                           ("current_ambience", ambience)):
            setattr(self, attr, None)
            if on and name:
                self._swap(attr, name)
            elif name:
                snd = self.streams.get(name)
                if snd is not None:
                    try:
                        snd.stop()
                    except Exception:
                        pass
                setattr(self, attr, name)
