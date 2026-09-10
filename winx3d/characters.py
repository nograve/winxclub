"""The playable fairy roster and the procedural model used to represent them.

Models are assembled from primitives into a small hierarchy of NodePaths
(hips -> torso -> head, plus limbs and wings) so the animation code can pose
them directly.  That avoids shipping any skeletal animation assets while still
giving a run cycle, a flight pose and an attack pose.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from panda3d.core import (NodePath, TransparencyAttrib, Vec3, Vec4)

from .geometry import MeshBuilder, shade

SKIN = Vec4(0.99, 0.83, 0.72, 1.0)


@dataclass(frozen=True)
class Fairy:
    """Static description of one playable character."""
    key: str
    name: str
    element: str
    blurb: str
    hair: Vec4
    dress: Vec4
    accent: Vec4
    magic: Vec4
    wing: Vec4
    speed: float = 1.0        # multiplier on movement speed
    power: float = 1.0        # multiplier on damage dealt
    magic_rate: float = 1.0   # multiplier on magic regeneration
    bolts: int = 1            # projectiles per shot
    spread: float = 0.0       # degrees between projectiles
    realm: str = "magix"      # home realm
    ultimate: str = "MAGIC WINX"   # her signature spell, shown when charged
    season: int = 1           # the season she joins the Winx in
    skin: Vec4 = field(default=SKIN)


ROSTER: list[Fairy] = [
    Fairy("bloom", "Bloom", "Dragon Flame",
          "All-rounder. The Dragon Flame hits hard and hits often.",
          hair=Vec4(0.95, 0.42, 0.18, 1), dress=Vec4(0.28, 0.72, 0.95, 1),
          accent=Vec4(1.0, 0.78, 0.30, 1), magic=Vec4(1.0, 0.55, 0.15, 1),
          wing=Vec4(1.0, 0.72, 0.45, 0.55),
          speed=1.0, power=1.15, magic_rate=1.0,
          realm="domino", ultimate="DRAGON FLAME", season=1),
    Fairy("stella", "Stella", "Sun and Moon",
          "Bright, fast bolts and a generous magic pool.",
          hair=Vec4(0.98, 0.85, 0.38, 1), dress=Vec4(1.0, 0.62, 0.20, 1),
          accent=Vec4(1.0, 0.94, 0.62, 1), magic=Vec4(1.0, 0.92, 0.35, 1),
          wing=Vec4(1.0, 0.95, 0.60, 0.55),
          speed=1.05, power=0.95, magic_rate=1.25,
          realm="solaria", ultimate="SOLAR FLARE", season=1),
    Fairy("flora", "Flora", "Nature",
          "Twin vine bolts. Slower, but covers a wide arc.",
          hair=Vec4(0.65, 0.42, 0.24, 1), dress=Vec4(0.42, 0.80, 0.44, 1),
          accent=Vec4(0.95, 0.55, 0.72, 1), magic=Vec4(0.45, 0.92, 0.42, 1),
          wing=Vec4(0.70, 0.98, 0.70, 0.55),
          speed=0.92, power=0.95, magic_rate=1.0, bolts=2, spread=7.0,
          realm="lynphea", ultimate="SUMMER BLOSSOM", season=1),
    Fairy("musa", "Musa", "Music",
          "Quick on her feet, cheap sound-wave attacks.",
          hair=Vec4(0.20, 0.16, 0.30, 1), dress=Vec4(0.90, 0.28, 0.48, 1),
          accent=Vec4(0.55, 0.35, 0.85, 1), magic=Vec4(0.85, 0.40, 0.95, 1),
          wing=Vec4(0.90, 0.60, 1.0, 0.55),
          speed=1.18, power=0.90, magic_rate=1.15,
          realm="melody", ultimate="SONIC BLAST", season=1),
    Fairy("tecna", "Tecna", "Technology",
          "Three-way pulse spread. Precision over raw damage.",
          hair=Vec4(0.60, 0.25, 0.72, 1), dress=Vec4(0.30, 0.85, 0.80, 1),
          accent=Vec4(0.65, 0.95, 1.0, 1), magic=Vec4(0.40, 0.95, 0.90, 1),
          wing=Vec4(0.55, 0.95, 1.0, 0.55),
          speed=0.98, power=0.75, magic_rate=1.1, bolts=3, spread=9.0,
          realm="zenith", ultimate="FIREWALL", season=1),
    Fairy("aisha", "Aisha", "Waves",
          "The strongest single hit in the roster, and the best flyer.",
          hair=Vec4(0.28, 0.18, 0.14, 1), dress=Vec4(0.25, 0.55, 0.95, 1),
          accent=Vec4(0.45, 0.95, 0.85, 1), magic=Vec4(0.30, 0.70, 1.0, 1),
          wing=Vec4(0.50, 0.85, 1.0, 0.55),
          speed=1.10, power=1.30, magic_rate=0.85,
          skin=Vec4(0.62, 0.44, 0.32, 1),
          realm="andros", ultimate="MORPHIX WAVE", season=2),
]

BY_KEY = {f.key: f for f in ROSTER}


def get(key: str) -> Fairy:
    return BY_KEY.get(key, ROSTER[0])


def _wing_pair(color: Vec4, sign: float) -> NodePath:
    """One side's wing pair, built as flat translucent fans in the XZ plane."""
    mb = MeshBuilder()
    for (length, width, lift, tilt, alpha) in (
            (2.5, 1.05, 1.5, 0.30, 1.00),   # upper wing
            (1.7, 0.80, 0.1, -0.55, 0.85)):  # lower wing
        col = Vec4(color[0], color[1], color[2], color[3] * alpha)
        edge = shade(col, 1.25, color[3] * alpha)
        root = Vec3(0, 0, 0)
        segs = 7
        for i in range(segs):
            t0, t1 = i / segs, (i + 1) / segs
            def pt(t):
                # teardrop outline swept along the wing's long axis
                span = math.sin(math.pi * min(1.0, t * 0.9 + 0.1))
                return Vec3(sign * (0.25 + length * t) * math.cos(tilt * t),
                            0.0,
                            lift * t + span * width * (0.5 + 0.5 * t)
                            + math.sin(tilt) * t)
            a, b = pt(t0), pt(t1)
            lo_a = Vec3(a.x, 0, a.z - width * span_lo(t0) )
            lo_b = Vec3(b.x, 0, b.z - width * span_lo(t1))
            mb.add_tri(root, a, b, edge if i > segs - 3 else col)
            mb.add_tri(root, lo_b, lo_a, col)
            mb.add_tri(b, a, root, edge if i > segs - 3 else col)   # backface
            mb.add_tri(lo_a, lo_b, root, col)
    np = mb.build("wing")
    np.setTransparency(TransparencyAttrib.MAlpha)
    np.setTwoSided(True)
    return np


def span_lo(t: float) -> float:
    return 0.55 * math.sin(math.pi * min(1.0, t * 0.9 + 0.1))


def build_fairy(spec: Fairy, scale: float = 1.0) -> tuple[NodePath, dict]:
    """Build a fairy model.

    Returns the root NodePath and a dict of the parts the animator poses:
    ``hips``, ``torso``, ``head``, ``arm_l``, ``arm_r``, ``leg_l``, ``leg_r``,
    ``wing_l``, ``wing_r``, ``aura``.
    """
    root = NodePath("fairy_" + spec.key)
    parts: dict[str, NodePath] = {}

    hips = NodePath("hips")
    hips.reparentTo(root)
    hips.setZ(1.55)
    parts["hips"] = hips

    # --- legs (pivot at the hip so they can swing) -------------------------
    for side, name in ((-1, "leg_l"), (1, "leg_r")):
        pivot = NodePath(name)
        pivot.reparentTo(hips)
        pivot.setPos(side * 0.20, 0, -0.12)
        mb = MeshBuilder()
        mb.cylinder((0, 0, -1.05), 0.17, 0.13, 1.05, spec.skin, segments=8,
                    cap_bottom=False)
        mb.cylinder((0, 0, -1.45), 0.19, 0.20, 0.42, spec.accent, segments=8)
        mb.box((0, -0.07, -1.50), (0.30, 0.42, 0.18), shade(spec.accent, 0.8))
        mb.build("leg").reparentTo(pivot)
        parts[name] = pivot

    # --- torso + skirt -----------------------------------------------------
    torso = NodePath("torso")
    torso.reparentTo(hips)
    parts["torso"] = torso
    mb = MeshBuilder()
    mb.cylinder((0, 0, -0.30), 0.46, 0.30, 0.30, spec.dress, segments=12,
                cap_top=False)                                   # skirt flare
    mb.cylinder((0, 0, 0.0), 0.30, 0.34, 0.62, spec.dress, segments=12)
    mb.cylinder((0, 0, 0.62), 0.34, 0.26, 0.22, spec.skin, segments=10)
    mb.box((0, 0, 0.18), (0.72, 0.40, 0.12), spec.accent)        # belt
    mb.build("torso_mesh").reparentTo(torso)

    # --- head --------------------------------------------------------------
    head = NodePath("head")
    head.reparentTo(torso)
    head.setZ(0.92)
    parts["head"] = head
    mb = MeshBuilder()
    mb.cylinder((0, 0, -0.16), 0.10, 0.12, 0.18, spec.skin, segments=8)  # neck
    mb.sphere((0, 0, 0.26), 0.38, spec.skin, segments=14, rings=10, squash=1.08)
    # The hair sits back and up: centred on the head it would swallow the face.
    mb.sphere((0, 0.07, 0.44), 0.37, spec.hair, segments=14, rings=10,
              squash=0.92)                                        # hair cap
    mb.sphere((0, -0.25, 0.50), 0.17, spec.hair, segments=10, rings=7,
              squash=0.75)                                        # fringe
    mb.sphere((0, 0.22, 0.10), 0.34, spec.hair, segments=12, rings=8,
              squash=1.25)                                        # hair back
    for side in (-1, 1):
        mb.cylinder((side * 0.30, 0.12, 0.18), 0.11, 0.06, -0.85, spec.hair,
                    segments=7)                                   # side locks
        # eyes, drawn as small dark discs on the face
        mb.sphere((side * 0.14, -0.335, 0.235), 0.062,
                  Vec4(0.08, 0.08, 0.14, 1), segments=7, rings=5, squash=1.25)
    mb.build("head_mesh").reparentTo(head)

    # --- arms --------------------------------------------------------------
    for side, name in ((-1, "arm_l"), (1, "arm_r")):
        pivot = NodePath(name)
        pivot.reparentTo(torso)
        pivot.setPos(side * 0.36, 0, 0.72)
        mb = MeshBuilder()
        mb.sphere((0, 0, 0), 0.14, spec.dress, segments=8, rings=6)
        mb.cylinder((0, 0, -0.90), 0.10, 0.13, 0.90, spec.skin, segments=8,
                    cap_bottom=False)
        mb.sphere((0, 0, -0.96), 0.13, spec.skin, segments=8, rings=6)
        mb.build("arm").reparentTo(pivot)
        parts[name] = pivot

    # --- wings -------------------------------------------------------------
    for side, name in ((-1, "wing_l"), (1, "wing_r")):
        pivot = NodePath(name)
        pivot.reparentTo(torso)
        pivot.setPos(side * 0.16, 0.30, 0.60)
        w = _wing_pair(spec.wing, side)
        w.reparentTo(pivot)
        parts[name] = pivot

    # --- transformation aura (hidden until Enchantix) ----------------------
    mb = MeshBuilder()
    mb.sphere((0, 0, 0), 1.9, Vec4(spec.magic[0], spec.magic[1], spec.magic[2],
                                   0.22), segments=14, rings=10, squash=1.35)
    aura = mb.build("aura")
    aura.reparentTo(hips)
    aura.setZ(-0.1)
    aura.setTransparency(TransparencyAttrib.MAlpha)
    aura.setTwoSided(True)
    aura.setLightOff()
    aura.setDepthWrite(False)
    aura.hide()
    parts["aura"] = aura

    root.setScale(scale)
    root.setTwoSided(False)
    return root, parts


class FairyAnimator:
    """Poses a built fairy model. Purely procedural — no animation data."""

    def __init__(self, parts: dict) -> None:
        self.parts = parts
        self.t = 0.0
        self.attack_timer = 0.0

    def trigger_attack(self) -> None:
        self.attack_timer = 0.32

    def update(self, dt: float, speed: float, flying: bool,
               grounded: bool) -> None:
        self.t += dt
        p = self.parts
        if self.attack_timer > 0.0:
            self.attack_timer = max(0.0, self.attack_timer - dt)

        # Wings beat fast in flight, idle-flutter otherwise.
        beat_rate = 26.0 if flying else 6.0
        beat_amp = 34.0 if flying else 9.0
        beat = math.sin(self.t * beat_rate) * beat_amp
        p["wing_l"].setHpr(-18.0 - beat, 0, 12.0 + beat * 0.35)
        p["wing_r"].setHpr(18.0 + beat, 0, -12.0 - beat * 0.35)

        if flying or not grounded:
            # Flight pose: legs trail back, torso leans forward.
            lean = -18.0 if flying else -8.0
            p["torso"].setP(lean)
            p["leg_l"].setP(28.0)
            p["leg_r"].setP(16.0)
            p["hips"].setZ(1.55 + math.sin(self.t * 3.0) * 0.10)
        else:
            stride = min(1.0, speed / 12.0)
            swing = math.sin(self.t * (5.0 + speed * 0.75)) * 42.0 * stride
            p["leg_l"].setP(swing)
            p["leg_r"].setP(-swing)
            p["torso"].setP(-4.0 - 8.0 * stride)
            p["hips"].setZ(1.55 + abs(math.sin(self.t * (10.0 + speed * 1.5)))
                           * 0.07 * stride)

        if self.attack_timer > 0.0:
            # Both arms thrust forward for the cast.
            k = self.attack_timer / 0.32
            thrust = -150.0 - 40.0 * (1.0 - k)
            p["arm_l"].setHpr(0, thrust, 0)
            p["arm_r"].setHpr(0, thrust, 0)
        elif flying or not grounded:
            p["arm_l"].setHpr(0, -32.0, -22.0)
            p["arm_r"].setHpr(0, -32.0, 22.0)
        else:
            stride = min(1.0, speed / 12.0)
            swing = math.sin(self.t * (5.0 + speed * 0.75)) * 34.0 * stride
            p["arm_l"].setHpr(0, -swing, -8.0)
            p["arm_r"].setHpr(0, swing, 8.0)
