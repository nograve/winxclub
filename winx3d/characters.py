"""The playable fairy roster and the procedural model used to represent them.

Models are assembled from primitives into a small hierarchy of NodePaths
(hips -> torso -> head, plus limbs and wings) so the animation code can pose
them directly.  That avoids shipping any skeletal animation assets while still
giving a run cycle, a flight pose and an attack pose.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from panda3d.core import (NodePath, TransparencyAttrib, Vec3, Vec4)

from .geometry import MeshBuilder, seg as _seg, shade

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
    realm: str = "magix"      # the realm she was born to
    # Where she actually grew up, and so where her own chapters are set.
    # These differ only for Bloom: born on Domino, raised on Earth, which is
    # the premise the first season turns on.
    home_realm: str = ""
    ultimate: str = "MAGIC WINX"   # her signature spell, shown when charged
    season: int = 1           # the season she joins the Winx in
    skin: Vec4 = field(default=SKIN)
    hair_style: str = "long"   # long | wavy | bob | bunches | ponytail | braids
    eye: Vec4 = field(default_factory=lambda: Vec4(0.20, 0.45, 0.75, 1))


ROSTER: list[Fairy] = [
    Fairy("bloom", "Bloom", "Dragon Flame",
          "All-rounder. The Dragon Flame hits hard and hits often.",
          hair=Vec4(0.95, 0.42, 0.18, 1), dress=Vec4(0.28, 0.72, 0.95, 1),
          accent=Vec4(1.0, 0.78, 0.30, 1), magic=Vec4(1.0, 0.55, 0.15, 1),
          wing=Vec4(1.0, 0.72, 0.45, 0.55),
          speed=1.0, power=1.15, magic_rate=1.0,
          realm="domino", home_realm="earth",
          ultimate="DRAGON FLAME", season=1,
          hair_style="long", eye=Vec4(0.25, 0.60, 0.85, 1)),
    Fairy("stella", "Stella", "Sun and Moon",
          "Bright, fast bolts and a generous magic pool.",
          hair=Vec4(0.98, 0.85, 0.38, 1), dress=Vec4(1.0, 0.62, 0.20, 1),
          accent=Vec4(1.0, 0.94, 0.62, 1), magic=Vec4(1.0, 0.92, 0.35, 1),
          wing=Vec4(1.0, 0.95, 0.60, 0.55),
          speed=1.05, power=0.95, magic_rate=1.25,
          realm="solaria", ultimate="SOLAR FLARE", season=1,
          hair_style="ponytail", eye=Vec4(0.55, 0.42, 0.22, 1)),
    Fairy("flora", "Flora", "Nature",
          "Twin vine bolts. Slower, but covers a wide arc.",
          hair=Vec4(0.65, 0.42, 0.24, 1), dress=Vec4(0.42, 0.80, 0.44, 1),
          accent=Vec4(0.95, 0.55, 0.72, 1), magic=Vec4(0.45, 0.92, 0.42, 1),
          wing=Vec4(0.70, 0.98, 0.70, 0.55),
          speed=0.92, power=0.95, magic_rate=1.0, bolts=2, spread=7.0,
          realm="lynphea", ultimate="SUMMER BLOSSOM", season=1,
          hair_style="wavy", eye=Vec4(0.35, 0.65, 0.40, 1)),
    Fairy("musa", "Musa", "Music",
          "Quick on her feet, cheap sound-wave attacks.",
          hair=Vec4(0.20, 0.16, 0.30, 1), dress=Vec4(0.90, 0.28, 0.48, 1),
          accent=Vec4(0.55, 0.35, 0.85, 1), magic=Vec4(0.85, 0.40, 0.95, 1),
          wing=Vec4(0.90, 0.60, 1.0, 0.55),
          speed=1.18, power=0.90, magic_rate=1.15,
          realm="melody", ultimate="SONIC BLAST", season=1,
          hair_style="bunches", eye=Vec4(0.35, 0.22, 0.45, 1)),
    Fairy("tecna", "Tecna", "Technology",
          "Three-way pulse spread. Precision over raw damage.",
          hair=Vec4(0.60, 0.25, 0.72, 1), dress=Vec4(0.30, 0.85, 0.80, 1),
          accent=Vec4(0.65, 0.95, 1.0, 1), magic=Vec4(0.40, 0.95, 0.90, 1),
          wing=Vec4(0.55, 0.95, 1.0, 0.55),
          speed=0.98, power=0.75, magic_rate=1.1, bolts=3, spread=9.0,
          realm="zenith", ultimate="FIREWALL", season=1,
          hair_style="bob", eye=Vec4(0.30, 0.75, 0.80, 1)),
    Fairy("aisha", "Aisha", "Waves",
          "The strongest single hit in the roster, and the best flyer.",
          hair=Vec4(0.28, 0.18, 0.14, 1), dress=Vec4(0.25, 0.55, 0.95, 1),
          accent=Vec4(0.45, 0.95, 0.85, 1), magic=Vec4(0.30, 0.70, 1.0, 1),
          wing=Vec4(0.50, 0.85, 1.0, 0.55),
          speed=1.10, power=1.30, magic_rate=0.85,
          skin=Vec4(0.62, 0.44, 0.32, 1),
          realm="andros", ultimate="MORPHIX WAVE", season=2,
          hair_style="braids", eye=Vec4(0.35, 0.55, 0.40, 1)),
]

# Default home_realm to the birth realm for everyone but Bloom.
ROSTER = [f if f.home_realm else replace(f, home_realm=f.realm)
          for f in ROSTER]

BY_KEY = {f.key: f for f in ROSTER}


def get(key: str) -> Fairy:
    return BY_KEY.get(key, ROSTER[0])


def _wing_pair(color: Vec4, sign: float) -> NodePath:
    """One side's wings: a large upper pane and a smaller lower one.

    Each is a tapered teardrop with a brighter rim and visible veins, built
    flat in the XZ plane and drawn two-sided.
    """
    mb = MeshBuilder()
    edge = shade(color, 1.35, min(1.0, color[3] + 0.25))
    vein = shade(color, 0.72, min(1.0, color[3] + 0.30))

    for (length, width, lift, sweep, alpha, veins) in (
            (2.25, 0.92, 1.35, 0.42, 0.92, 3),     # upper pane
            (1.45, 0.62, 0.08, -0.50, 0.78, 2)):   # lower pane
        col = Vec4(color[0], color[1], color[2], color[3] * alpha)
        segs = _seg(11)

        def spine(t):
            # The long axis curves outward and up as it goes.
            return Vec3(sign * (0.20 + length * t),
                        0.0,
                        lift * t * t + math.sin(sweep) * length * t * 0.35)

        def half_width(t):
            # Fat near the base, tapering to a point at the tip.
            return width * math.sin(math.pi * min(1.0, t * 0.88 + 0.12)) ** 0.8

        root = Vec3(0, 0, 0)
        for i in range(segs):
            t0, t1 = i / segs, (i + 1) / segs
            a, b = spine(t0), spine(t1)
            w0, w1 = half_width(t0), half_width(t1)
            up_a = Vec3(a.x, 0, a.z + w0)
            up_b = Vec3(b.x, 0, b.z + w1)
            lo_a = Vec3(a.x, 0, a.z - w0 * 0.62)
            lo_b = Vec3(b.x, 0, b.z - w1 * 0.62)
            tip = i > segs - 4
            face = edge if tip else col
            mb.add_quad(root, up_a, up_b, root, face)
            mb.add_quad(root, lo_b, lo_a, root, col)
            mb.add_tri(up_a, up_b, lo_b, face)
            mb.add_tri(up_a, lo_b, lo_a, col)
        # Veins fanning out from the joint.
        for v in range(veins):
            t_end = 0.55 + 0.42 * (v + 1) / veins
            off = (v - (veins - 1) * 0.5) * 0.22
            for i in range(_seg(7)):
                t0 = t_end * i / _seg(7)
                t1 = t_end * (i + 1) / _seg(7)
                a, b = spine(t0), spine(t1)
                mb.add_quad(Vec3(a.x, -0.01, a.z + off * half_width(t0)),
                            Vec3(b.x, -0.01, b.z + off * half_width(t1)),
                            Vec3(b.x, -0.01, b.z + off * half_width(t1) + 0.04),
                            Vec3(a.x, -0.01, a.z + off * half_width(t0) + 0.04),
                            vein)

    np = mb.build("wing")
    np.setTransparency(TransparencyAttrib.MAlpha)
    np.setTwoSided(True)
    np.setLightOff()
    np.setDepthWrite(False)
    return np


def _build_face(mb: MeshBuilder, spec: Fairy) -> None:
    """Eyes, brows, nose and mouth on the front of the head."""
    white = Vec4(0.99, 0.98, 0.98, 1)
    dark = Vec4(0.10, 0.09, 0.14, 1)
    for side in (-1, 1):
        x = side * 0.145
        # Eye: white almond, coloured iris, pupil, and a catchlight.
        mb.disc((x, -0.325, 0.265), 0.088, white, _seg(10), squash=1.25)
        mb.disc((x, -0.335, 0.258), 0.060, spec.eye, _seg(10), squash=1.15)
        mb.disc((x, -0.342, 0.252), 0.030, dark, _seg(8), squash=1.15)
        mb.disc((x - side * 0.020, -0.348, 0.285), 0.016, white, 6)
        # Lash line and brow.
        mb.box((x, -0.330, 0.335), (0.175, 0.03, 0.022), dark)
        mb.box((x, -0.318, 0.395), (0.150, 0.03, 0.026),
               shade(spec.hair, 0.75))
    # Nose and mouth, kept small - this reads at gameplay distance.
    mb.sphere((0, -0.335, 0.175), 0.030, shade(spec.skin, 0.92),
              segments=6, rings=5)
    mb.disc((0, -0.332, 0.095), 0.062, Vec4(0.80, 0.32, 0.36, 1), _seg(9),
            squash=0.42)
    for side in (-1, 1):
        mb.disc((side * 0.225, -0.318, 0.165), 0.070,
                Vec4(1.0, 0.66, 0.64, 0.38), _seg(8), squash=0.62)


def _build_hair(mb: MeshBuilder, spec: Fairy) -> None:
    """The skull cap, fringe and whatever style this fairy wears."""
    hair = spec.hair
    seg = _seg(14)
    # Skull cap, set back on the head. The face sits slightly proud of it,
    # so the features stay visible instead of being swallowed.
    mb.lathe((0, 0.105, 0.05), [(0.10, 0.36), (0.26, 0.395), (0.42, 0.395),
                                (0.52, 0.345), (0.60, 0.245), (0.66, 0.11)],
             hair, segments=seg, cap_bottom=False, squash_y=1.02)
    # Fringe: strands hanging *down* from the hairline over the brow. A
    # lathe extrudes along +Z, so the profile runs from the tip upward.
    for i in range(5):
        t = (i - 2) / 2.0
        tip = -0.30 + abs(t) * 0.05          # slightly shorter at the sides
        mb.lathe((t * 0.150, -0.250 + abs(t) * 0.045, 0.56),
                 [(tip, 0.0), (tip * 0.55, 0.085), (-0.05, 0.105),
                  (0.0, 0.085)],
                 shade(hair, 1.08), segments=_seg(7), cap_top=False)

    style = spec.hair_style
    if style == "bob":
        for side in (-1, 1):
            mb.lathe((side * 0.30, 0.06, 0.30),
                     [(0.0, 0.0), (0.08, 0.15), (0.30, 0.17), (0.44, 0.10)],
                     hair, segments=_seg(8))
        mb.lathe((0, 0.20, 0.12),
                 [(0.0, 0.16), (0.22, 0.30), (0.44, 0.26), (0.56, 0.10)],
                 hair, segments=_seg(10))
        return

    # Everything else has length down the back.
    length = {"long": 2.0, "wavy": 1.75, "ponytail": 1.6, "bunches": 1.1,
              "braids": 1.5}.get(style, 1.7)
    wave = {"wavy": 0.14, "braids": 0.0}.get(style, 0.05)
    mass = [(0.0, 0.34), (-0.30, 0.40), (-0.90, 0.36), (-1.40, 0.26)]
    prof = [(z * (length / 1.4), r) for z, r in mass]
    mb.lathe((0, 0.24, 0.30), list(reversed([(z, r) for z, r in prof])),
             hair, segments=_seg(12), cap_top=False)

    if style == "ponytail":
        mb.sphere((0, 0.34, 0.34), 0.16, shade(spec.accent, 1.0),
                  segments=_seg(8), rings=6)
    if style == "bunches":
        for side in (-1, 1):
            mb.sphere((side * 0.42, 0.22, 0.30), 0.22, hair,
                      segments=_seg(9), rings=7)
            mb.lathe((side * 0.46, 0.24, 0.24),
                     [(-0.85, 0.06), (-0.45, 0.14), (0.0, 0.17)],
                     hair, segments=_seg(8))
            mb.sphere((side * 0.42, 0.22, 0.42), 0.11, spec.accent,
                      segments=_seg(7), rings=5)
    if style == "braids":
        for side in (-1, 1):
            for k in range(5):
                z = 0.14 - k * 0.30
                mb.sphere((side * 0.34, 0.26, z), 0.115 - k * 0.010, hair,
                          segments=_seg(7), rings=5)
    # Side locks framing the face.
    for side in (-1, 1):
        drop = -0.95 if style != "bunches" else -0.55
        mb.lathe((side * 0.335, 0.03, 0.34),
                 [(drop, 0.045), (drop * 0.5, 0.095), (0.04, 0.125)],
                 hair, segments=_seg(7))
    if wave:
        for side in (-1, 1):
            for k in range(3):
                mb.sphere((side * (0.18 + k * 0.05), 0.30,
                           -0.45 - k * 0.42), 0.17 + wave, hair,
                          segments=_seg(8), rings=6)


def _build_limb(mb: MeshBuilder, skin: Vec4, upper, lower, joint_r,
                top_r, mid_r, end_r) -> None:
    """A limb as two tapered sections with a joint between them."""
    mb.lathe((0, 0, -upper), [(0.0, mid_r), (upper * 0.5, mid_r * 1.05),
                              (upper, top_r)],
             skin, segments=_seg(9), cap_top=False, cap_bottom=False)
    mb.sphere((0, 0, -upper), joint_r, shade(skin, 1.02),
              segments=_seg(8), rings=6)
    mb.lathe((0, 0, -upper - lower),
             [(0.0, end_r), (lower * 0.45, mid_r * 0.88), (lower, mid_r)],
             skin, segments=_seg(9), cap_top=False, cap_bottom=False)


def build_fairy(spec: Fairy, scale: float = 1.0) -> tuple[NodePath, dict]:
    """Build a fairy model.

    Returns the root NodePath and a dict of the parts the animator poses:
    ``hips``, ``torso``, ``head``, ``arm_l``, ``arm_r``, ``leg_l``, ``leg_r``,
    ``wing_l``, ``wing_r``, ``aura``.
    """
    root = NodePath("fairy_" + spec.key)
    parts: dict[str, NodePath] = {}
    seg = _seg(14)

    hips = NodePath("hips")
    hips.reparentTo(root)
    hips.setZ(1.62)
    parts["hips"] = hips

    # --- legs --------------------------------------------------------------
    for side, name in ((-1, "leg_l"), (1, "leg_r")):
        pivot = NodePath(name)
        pivot.reparentTo(hips)
        pivot.setPos(side * 0.19, 0, -0.14)
        mb = MeshBuilder()
        _build_limb(mb, spec.skin, 0.62, 0.60, 0.115, 0.155, 0.135, 0.095)
        # Boot with a heel.
        mb.lathe((0, 0, -1.46), [(0.0, 0.135), (0.30, 0.165), (0.44, 0.20),
                                 (0.50, 0.185)],
                 spec.accent, segments=_seg(9))
        mb.box((0, -0.09, -1.50), (0.26, 0.40, 0.13), shade(spec.accent, 0.85))
        mb.box((0, 0.10, -1.55), (0.16, 0.10, 0.09), shade(spec.accent, 0.7))
        mb.build("leg").reparentTo(pivot)
        parts[name] = pivot

    # --- torso -------------------------------------------------------------
    torso = NodePath("torso")
    torso.reparentTo(hips)
    parts["torso"] = torso
    mb = MeshBuilder()
    # Layered skirt: an under-petal and a shorter top layer.
    mb.lathe((0, 0, -0.52), [(0.0, 0.56), (0.24, 0.44), (0.52, 0.30)],
             shade(spec.dress, 0.88), segments=seg, cap_top=False)
    mb.lathe((0, 0, -0.34), [(0.0, 0.48), (0.26, 0.34), (0.40, 0.27)],
             spec.dress, segments=seg, cap_top=False)
    # Waist up to the bust and shoulders.
    mb.lathe((0, 0, -0.06),
             [(0.0, 0.255), (0.22, 0.235), (0.48, 0.285), (0.66, 0.295),
              (0.80, 0.255), (0.92, 0.150)],
             spec.dress, segments=seg, cap_bottom=False, cap_top=False,
             squash_y=0.86)
    mb.lathe((0, 0, 0.74), [(0.0, 0.16), (0.14, 0.115), (0.24, 0.105)],
             spec.skin, segments=_seg(10), cap_bottom=False, cap_top=False)
    mb.box((0, 0, -0.05), (0.56, 0.42, 0.09), spec.accent)          # belt
    mb.disc((0, -0.30, 0.36), 0.085, shade(spec.accent, 1.25), _seg(8))
    for side in (-1, 1):                                             # straps
        mb.lathe((side * 0.175, -0.075, 0.42),
                 [(0.0, 0.035), (0.30, 0.040), (0.40, 0.048)],
                 shade(spec.dress, 1.18), segments=6)
    mb.build("torso_mesh").reparentTo(torso)

    # --- head --------------------------------------------------------------
    head = NodePath("head")
    head.reparentTo(torso)
    head.setZ(0.98)
    parts["head"] = head
    mb = MeshBuilder()
    # Skull, slightly narrowed at the jaw so it is not a plain ball.
    mb.lathe((0, 0, 0.0),
             [(-0.16, 0.12), (-0.06, 0.20), (0.06, 0.30), (0.22, 0.365),
              (0.38, 0.355), (0.50, 0.27), (0.58, 0.12)],
             spec.skin, segments=seg, squash_y=0.94)
    for side in (-1, 1):                                             # ears
        mb.sphere((side * 0.335, 0.02, 0.24), 0.075, spec.skin,
                  segments=_seg(7), rings=5, squash=1.3)
    _build_face(mb, spec)
    _build_hair(mb, spec)
    mb.build("head_mesh").reparentTo(head)

    # --- arms --------------------------------------------------------------
    for side, name in ((-1, "arm_l"), (1, "arm_r")):
        pivot = NodePath(name)
        pivot.reparentTo(torso)
        pivot.setPos(side * 0.29, 0, 0.70)
        mb = MeshBuilder()
        mb.sphere((0, 0, 0), 0.115, shade(spec.dress, 1.1),
                  segments=_seg(8), rings=6)
        _build_limb(mb, spec.skin, 0.42, 0.40, 0.075, 0.095, 0.082, 0.062)
        mb.sphere((0, 0, -0.86), 0.095, spec.skin, segments=_seg(8), rings=6)
        mb.lathe((0, 0, -0.80), [(0.0, 0.088), (0.16, 0.10)],
                 spec.accent, segments=_seg(8))                      # cuff
        mb.build("arm").reparentTo(pivot)
        parts[name] = pivot

    # --- wings -------------------------------------------------------------
    for side, name in ((-1, "wing_l"), (1, "wing_r")):
        pivot = NodePath(name)
        pivot.reparentTo(torso)
        pivot.setPos(side * 0.14, 0.26, 0.62)
        _wing_pair(spec.wing, side).reparentTo(pivot)
        parts[name] = pivot

    # --- transformation aura ----------------------------------------------
    mb = MeshBuilder()
    mb.sphere((0, 0, 0), 1.9, Vec4(spec.magic[0], spec.magic[1], spec.magic[2],
                                   0.22), segments=_seg(14), rings=10,
              squash=1.35)
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
