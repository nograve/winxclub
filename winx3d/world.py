"""Level geometry, collision and level definitions.

Static level art is merged into a handful of Geoms and every solid gets a
matching ``CollisionBox``.  Boxes are the cheapest solid Panda3D offers and
they answer both of the queries the player needs: sphere-vs-solid pushback for
walls, and ray-vs-solid for finding the floor.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from panda3d.core import (BitMask32, CollisionBox, CollisionNode, NodePath,
                          Point3, TransparencyAttrib, Vec3, Vec4)

from .geometry import MeshBuilder, shade

# Collision masks.  Solids are "into" only; the player and projectiles are the
# "from" objects that test against them.
MASK_SOLID = BitMask32.bit(1)
MASK_ENEMY = BitMask32.bit(2)
MASK_PICKUP = BitMask32.bit(3)


@dataclass
class Spawn:
    pos: Vec3
    kind: str = "ghoul"
    extra: dict = field(default_factory=dict)


@dataclass
class Level:
    """One playable level. ``key`` matches a chapter key in :mod:`winx3d.lore`."""
    key: str
    name: str
    subtitle: str
    sky: Vec4
    fog: Vec4
    sun: Vec4
    ambient: Vec4
    start: Vec3
    portal: Vec3
    build: object                     # callable(WorldBuilder) -> None
    enemies: list = field(default_factory=list)
    gems: list = field(default_factory=list)
    hearts: list = field(default_factory=list)
    gem_goal: int = 0
    hint: str = ""
    gem_name: str = "gem"      # what the collectibles are called in this level


class WorldBuilder:
    """Collects level geometry: visuals into one mesh, solids into collision."""

    def __init__(self) -> None:
        self.mesh = MeshBuilder()
        self.alpha_mesh = MeshBuilder()
        self.boxes: list[tuple[Vec3, Vec3]] = []   # (center, half-extents)

    # -- adders -------------------------------------------------------------
    def solid(self, center, size, color, top_color=None) -> None:
        """A box that is both drawn and collidable."""
        self.mesh.box(center, size, color, top_color)
        c = Vec3(*center) if not isinstance(center, Vec3) else center
        self.boxes.append((c, Vec3(size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)))

    def clip(self, center, size) -> None:
        """Invisible collision box (arena bounds, ceilings)."""
        c = Vec3(*center) if not isinstance(center, Vec3) else center
        self.boxes.append((c, Vec3(size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)))

    def decor(self):
        """Mesh for visual-only geometry (no collision)."""
        return self.mesh

    def glass(self):
        """Mesh for translucent visual-only geometry, drawn after everything."""
        return self.alpha_mesh

    # -- composite props ----------------------------------------------------
    def tower(self, x, y, radius, height, wall, roof, segments=12) -> None:
        mb = self.mesh
        mb.cylinder((x, y, 0), radius, radius * 0.92, height, wall,
                    segments=segments)
        mb.cylinder((x, y, height), radius * 1.12, radius * 1.12, 0.5,
                    shade(wall, 0.85), segments=segments)
        mb.cylinder((x, y, height + 0.5), radius * 1.12, 0.0, radius * 1.5,
                    roof, segments=segments)
        # Crenellations read well even untextured.
        for i in range(segments):
            a = math.tau * i / segments
            mb.box((x + math.cos(a) * radius, y + math.sin(a) * radius,
                    height + 0.75), (0.5, 0.5, 0.5), shade(wall, 1.05))
        self.boxes.append((Vec3(x, y, height * 0.5),
                           Vec3(radius, radius, height * 0.5)))

    def tree(self, x, y, z, height, trunk, leaf, rng) -> None:
        mb = self.mesh
        mb.cylinder((x, y, z), 0.36, 0.24, height, trunk, segments=7)
        for i in range(3):
            r = 2.4 - i * 0.55
            h = z + height + i * 1.5
            mb.cylinder((x, y, h - 0.4), r, r * 0.25, 2.1 + i * 0.2,
                        shade(leaf, 0.85 + 0.12 * i), segments=9)
        mb.sphere((x, y, z + height + 4.2), 1.1, shade(leaf, 1.1),
                  segments=8, rings=6)
        self.boxes.append((Vec3(x, y, z + height * 0.5),
                           Vec3(0.5, 0.5, height * 0.5)))
        # A couple of bushes at the base for silhouette variety.
        for _ in range(rng.randint(0, 2)):
            bx = x + rng.uniform(-2.4, 2.4)
            by = y + rng.uniform(-2.4, 2.4)
            mb.sphere((bx, by, z + 0.4), rng.uniform(0.6, 1.0),
                      shade(leaf, rng.uniform(0.7, 1.0)), segments=7, rings=5)

    def arch(self, x, y, width, height, color) -> None:
        self.solid((x - width * 0.5, y, height * 0.5), (1.2, 1.6, height), color)
        self.solid((x + width * 0.5, y, height * 0.5), (1.2, 1.6, height), color)
        self.solid((x, y, height + 0.6), (width + 1.2, 1.6, 1.2),
                   shade(color, 1.1))

    def bounds(self, half_x, half_y, height=60.0, thickness=4.0) -> None:
        """Invisible walls so the player cannot leave the arena."""
        for sx, sy, w, d in ((half_x + thickness * 0.5, 0, thickness,
                              half_y * 2 + thickness * 2),
                             (-half_x - thickness * 0.5, 0, thickness,
                              half_y * 2 + thickness * 2),
                             (0, half_y + thickness * 0.5,
                              half_x * 2 + thickness * 2, thickness),
                             (0, -half_y - thickness * 0.5,
                              half_x * 2 + thickness * 2, thickness)):
            self.clip((sx, sy, height * 0.5), (w, d, height))

    # -- baking -------------------------------------------------------------
    def attach(self, parent: NodePath, name: str) -> NodePath:
        root = NodePath(name)
        root.reparentTo(parent)
        if not self.mesh.is_empty():
            self.mesh.build(name + "_geom").reparentTo(root)
        if not self.alpha_mesh.is_empty():
            g = self.alpha_mesh.build(name + "_glass")
            g.reparentTo(root)
            g.setTransparency(TransparencyAttrib.MAlpha)
            g.setTwoSided(True)
            g.setBin("transparent", 10)
            g.setDepthWrite(False)
        cnode = CollisionNode(name + "_solids")
        cnode.setIntoCollideMask(MASK_SOLID)
        cnode.setFromCollideMask(BitMask32.allOff())
        for center, half in self.boxes:
            cnode.addSolid(CollisionBox(Point3(center), half.x, half.y, half.z))
        root.attachNewNode(cnode)
        # Static geometry never moves, so let Panda pre-transform it.
        root.flattenStrong()
        return root




# ---------------------------------------------------------------------------
# Shared props
# ---------------------------------------------------------------------------
def _lamp(b: WorldBuilder, x, y, color=Vec4(1.0, 0.92, 0.65, 1)) -> None:
    b.mesh.cylinder((x, y, 0), 0.22, 0.16, 4.2, Vec4(0.22, 0.22, 0.26, 1),
                    segments=7)
    b.mesh.sphere((x, y, 4.5), 0.45, color, segments=8, rings=6)
    b.boxes.append((Vec3(x, y, 2.0), Vec3(0.3, 0.3, 2.0)))


def _bench(b: WorldBuilder, x, y, h=0.0) -> None:
    wood = Vec4(0.52, 0.34, 0.22, 1)
    b.solid((x, y, h + 0.55), (3.0, 0.9, 0.22), wood)
    b.mesh.box((x, y + 0.42, h + 0.95), (3.0, 0.22, 0.7), shade(wood, 1.1))
    for sx in (-1.2, 1.2):
        b.mesh.box((x + sx, y, h + 0.27), (0.2, 0.8, 0.55),
                   Vec4(0.25, 0.25, 0.28, 1))


def _house(b: WorldBuilder, x, y, w, d, h, wall, roof) -> None:
    b.solid((x, y, h * 0.5), (w, d, h), wall, shade(wall, 1.05))
    b.mesh.prism((x, y, h + w * 0.22), (w * 1.06, d * 1.06, w * 0.45), roof)
    for wx in (-w * 0.25, w * 0.25):
        b.mesh.box((x + wx, y - d * 0.5 - 0.05, h * 0.55),
                   (w * 0.18, 0.2, h * 0.3), Vec4(0.45, 0.62, 0.85, 1))
    b.mesh.box((x, y - d * 0.5 - 0.05, h * 0.30), (w * 0.16, 0.2, h * 0.6),
               Vec4(0.40, 0.26, 0.18, 1))


def _dead_tree(b: WorldBuilder, x, y, z, height, bark, rng) -> None:
    b.mesh.cylinder((x, y, z), 0.42, 0.18, height, bark, segments=7)
    for _ in range(rng.randint(2, 4)):
        a = rng.uniform(0, math.tau)
        zz = z + height * rng.uniform(0.45, 0.95)
        b.mesh.cylinder((x, y, zz), 0.16, 0.03,
                        rng.uniform(1.8, 3.4), shade(bark, 0.9), segments=5)
        b.mesh.box((x + math.cos(a) * 1.2, y + math.sin(a) * 1.2, zz + 0.6),
                   (2.2, 0.22, 0.22), shade(bark, 0.85))
    b.boxes.append((Vec3(x, y, z + height * 0.5), Vec3(0.5, 0.5, height * 0.5)))


def _spire(b: WorldBuilder, x, y, radius, height, wall, rune, segments=10)\
        -> None:
    """A twisted Cloud Tower spire - wider at the top than the base."""
    b.mesh.cylinder((x, y, 0), radius * 0.7, radius, height, wall,
                    segments=segments)
    b.mesh.cylinder((x, y, height), radius * 1.15, 0.0, radius * 2.6,
                    shade(wall, 0.8), segments=segments)
    b.mesh.sphere((x, y, height + radius * 2.7), radius * 0.30, rune,
                  segments=7, rings=5)
    b.boxes.append((Vec3(x, y, height * 0.5),
                    Vec3(radius, radius, height * 0.5)))


# ---------------------------------------------------------------------------
# Chapter 1 - Gardenia Park (Earth)
# ---------------------------------------------------------------------------
def _build_gardenia(b: WorldBuilder, besieged: bool = False) -> None:
    """Bloom's home is Earth, not Domino - she was raised in Gardenia."""
    rng = random.Random(101)
    grass_a = Vec4(0.46, 0.70, 0.36, 1)
    grass_b = Vec4(0.40, 0.64, 0.33, 1)
    path = Vec4(0.78, 0.72, 0.60, 1)
    if besieged:
        grass_a = Vec4(0.34, 0.33, 0.21, 1)
        grass_b = Vec4(0.29, 0.28, 0.18, 1)
        path = Vec4(0.52, 0.48, 0.42, 1)

    b.mesh.grid_ground(170, 170, grass_a, grass_b, step=11.0)
    b.clip((0, 0, -2.0), (200, 200, 4.0))
    b.bounds(64, 64)

    # Crossing paths, with the bandstand where they meet.
    b.mesh.grid_ground(14, 150, shade(path, 1.0), shade(path, 0.94),
                       step=7.0, center=(0, 0, 0.05))
    b.mesh.grid_ground(150, 14, shade(path, 1.0), shade(path, 0.94),
                       step=7.0, center=(0, 0, 0.05))

    # Bandstand: raised, open-sided, a good place to be cornered.
    b.solid((0, 0, 0.45), (16, 16, 0.9), shade(path, 1.06))
    b.solid((0, 0, 1.15), (13, 13, 0.5), Vec4(0.62, 0.46, 0.32, 1))
    for i in range(8):
        a = math.tau * i / 8
        px, py = math.cos(a) * 5.6, math.sin(a) * 5.6
        b.mesh.cylinder((px, py, 1.4), 0.26, 0.22, 3.6, Vec4(0.90, 0.88, 0.82, 1),
                        segments=7)
        b.boxes.append((Vec3(px, py, 3.2), Vec3(0.3, 0.3, 1.8)))
    b.mesh.cylinder((0, 0, 5.0), 7.2, 0.0, 2.6, Vec4(0.35, 0.52, 0.60, 1),
                    segments=10)

    # Pond in the north-east corner.
    b.glass().grid_ground(26, 26, Vec4(0.32, 0.62, 0.80, 0.62),
                          Vec4(0.26, 0.55, 0.74, 0.62), step=6.5,
                          center=(34, 34, 0.30))
    for i in range(12):
        a = math.tau * i / 12
        b.mesh.box((34 + math.cos(a) * 14, 34 + math.sin(a) * 14, 0.25),
                   (3.0, 3.0, 0.5), Vec4(0.62, 0.60, 0.56, 1))

    # Park furniture along the paths.
    for y in (-34, -20, 20, 34):
        _bench(b, -9.5, y)
        _bench(b, 9.5, y)
    for (lx, ly) in ((-22, -22), (22, -22), (-22, 22), (22, 22),
                     (-42, 0), (42, 0)):
        _lamp(b, lx, ly)

    # Trees, and hedges boxing in the lawn.
    for _ in range(30):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(24, 56)
        x, y = math.cos(a) * r, math.sin(a) * r
        if abs(x) < 9 or abs(y) < 9:
            continue
        b.tree(x, y, 0, rng.uniform(3.8, 6.0), Vec4(0.44, 0.32, 0.22, 1),
               Vec4(0.32, 0.58, 0.30, 1), rng)
    for x in range(-40, 41, 16):
        b.solid((x, -46, 0.8), (11, 1.8, 1.6), Vec4(0.30, 0.52, 0.30, 1))

    # Gardenia's houses beyond the railings - Earth, seen from the park.
    for i, x in enumerate(range(-48, 49, 24)):
        _house(b, x, 60, 14, 12, 8.0 + (i % 2) * 2.0,
               (Vec4(0.86, 0.82, 0.74, 1), Vec4(0.80, 0.76, 0.82, 1))[i % 2],
               (Vec4(0.60, 0.30, 0.26, 1), Vec4(0.42, 0.36, 0.40, 1))[i % 2])
    for x in range(-56, 57, 4):
        b.mesh.cylinder((x, 50, 0), 0.10, 0.10, 2.2, Vec4(0.28, 0.28, 0.32, 1),
                        segments=5)
    b.clip((0, 50, 2.0), (120, 0.8, 4.0))
    if besieged:
        _blight(b, rng, 20, Vec4(0.66, 0.62, 0.56, 1), radius=(16, 56))


LEVEL_GARDENIA = Level(
    key="gardenia", name="Gardenia Park", subtitle="Earth. No magic here. Usually.",
    sky=Vec4(0.56, 0.78, 0.95, 1), fog=Vec4(0.76, 0.87, 0.97, 1),
    sun=Vec4(1.0, 0.98, 0.92, 1), ambient=Vec4(0.58, 0.60, 0.66, 1),
    start=Vec3(0, -40, 2.0), portal=Vec3(0, 40, 1.2),
    build=_build_gardenia, gem_goal=0, gem_name="spark",
    enemies=[Spawn(Vec3(0, 8, 2), "knut"),
             Spawn(Vec3(-16, 2, 2), "ghoul"), Spawn(Vec3(16, 2, 2), "ghoul"),
             Spawn(Vec3(-10, 20, 2), "ghoul"), Spawn(Vec3(10, 20, 2), "ghoul"),
             Spawn(Vec3(0, 30, 2), "ghoul")],
    gems=[Vec3(-22, -22, 1.4), Vec3(22, -22, 1.4), Vec3(0, 0, 2.6),
          Vec3(34, 34, 1.6)],
    hearts=[Vec3(-34, 0, 1.4), Vec3(34, 0, 1.4)],
)


# ---------------------------------------------------------------------------
# Chapters 2 and 9 - Alfea College for Fairies
# ---------------------------------------------------------------------------
def _build_alfea(b: WorldBuilder, besieged: bool = False) -> None:
    """Alfea's courtyard. ``besieged`` is the Chapter 9 state: the Army of
    Decay is inside the barrier, so the lawns are blighted and the walls are
    broken open."""
    rng = random.Random(11)
    grass_a = Vec4(0.42, 0.68, 0.36, 1)
    grass_b = Vec4(0.36, 0.61, 0.32, 1)
    stone = Vec4(0.86, 0.83, 0.76, 1)
    roof = Vec4(0.85, 0.42, 0.55, 1)
    if besieged:
        grass_a = Vec4(0.34, 0.34, 0.22, 1)
        grass_b = Vec4(0.28, 0.29, 0.19, 1)
        stone = Vec4(0.56, 0.52, 0.50, 1)
        roof = Vec4(0.45, 0.22, 0.30, 1)

    b.mesh.grid_ground(200, 200, grass_a, grass_b, step=10.0)
    b.clip((0, 0, -2.0), (240, 240, 4.0))
    b.bounds(92, 92)

    b.mesh.grid_ground(56, 56, shade(stone, 0.98), shade(stone, 0.90),
                       step=7.0, center=(0, 0, 0.06))
    b.solid((0, 0, 0.5), (9, 9, 1.0), shade(stone, 1.02))
    b.solid((0, 0, 1.6), (5.5, 5.5, 1.4), shade(stone, 0.95))
    b.mesh.cylinder((0, 0, 2.3), 0.8, 0.5, 3.2, shade(stone, 1.05), segments=10)
    b.glass().sphere((0, 0, 6.0), 1.5,
                     Vec4(0.45, 0.78, 1.0, 0.55) if not besieged
                     else Vec4(0.70, 0.35, 0.35, 0.55), segments=12, rings=8)

    # The school building itself.
    b.solid((0, 46, 9.0), (48, 16, 18.0), stone, shade(stone, 1.06))
    b.mesh.prism((0, 46, 20.0), (48, 16, 8.0), roof)
    for x in (-26, 26):
        b.tower(x, 46, 5.5, 26.0, shade(stone, 0.94), roof)
    b.arch(0, 37.5, 9.0, 9.0, shade(stone, 1.04))
    for x in range(-20, 21, 8):
        for z in (6.0, 12.0):
            b.decor().box((x, 37.85, z), (3.0, 0.3, 4.0),
                          Vec4(0.35, 0.55, 0.85, 1) if not besieged
                          else Vec4(0.20, 0.16, 0.20, 1))

    # Terraces - the gems sit up here, so you have to fly for them.
    for (tx, ty, tz, tw) in ((-38, 8, 6.0, 14), (38, 8, 9.0, 14),
                             (0, -34, 12.0, 16), (-30, -26, 5.0, 10),
                             (30, -26, 5.0, 10)):
        b.solid((tx, ty, tz), (tw, tw, 1.4), shade(stone, 1.0),
                Vec4(0.62, 0.78, 0.95, 1) if not besieged
                else Vec4(0.44, 0.42, 0.38, 1))
        for sx in (-1, 1):
            for sy in (-1, 1):
                b.decor().cylinder((tx + sx * (tw / 2 - 1),
                                    ty + sy * (tw / 2 - 1), tz + 0.7),
                                   0.4, 0.32, 2.4, shade(stone, 1.08),
                                   segments=8)

    for i, (px, py) in enumerate(((-14, -14), (-22, -20), (-30, -24))):
        b.solid((px, py, 1.4 + i * 1.6), (5, 5, 1.0), shade(stone, 0.92))

    leaf = Vec4(0.30, 0.60, 0.32, 1) if not besieged else Vec4(0.34, 0.30, 0.18, 1)
    for _ in range(26):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(38, 82)
        if besieged and rng.random() < 0.45:
            _dead_tree(b, math.cos(a) * r, math.sin(a) * r, 0,
                       rng.uniform(4.0, 6.5), Vec4(0.30, 0.26, 0.20, 1), rng)
        else:
            b.tree(math.cos(a) * r, math.sin(a) * r, 0, rng.uniform(3.5, 5.5),
                   Vec4(0.42, 0.30, 0.20, 1), leaf, rng)
    for x in range(-30, 31, 12):
        b.solid((x, 18, 0.9), (7, 1.6, 1.8),
                Vec4(0.28, 0.55, 0.30, 1) if not besieged
                else Vec4(0.30, 0.28, 0.18, 1))

    if besieged:
        # Rubble where the barrier gave way, and fires in the wreckage.
        for _ in range(22):
            a = rng.uniform(0, math.tau)
            r = rng.uniform(20, 70)
            s = rng.uniform(1.4, 3.6)
            b.solid((math.cos(a) * r, math.sin(a) * r, s * 0.35),
                    (s, s * 1.3, s * 0.7), shade(stone, rng.uniform(0.6, 0.9)))
        for _ in range(10):
            a = rng.uniform(0, math.tau)
            r = rng.uniform(24, 66)
            b.glass().sphere((math.cos(a) * r, math.sin(a) * r,
                              rng.uniform(0.8, 2.2)), rng.uniform(1.2, 2.4),
                             Vec4(0.95, 0.45, 0.20, 0.45), segments=7, rings=5)


LEVEL_ALFEA = Level(
    key="alfea", name="Alfea College", subtitle="Magix. Your first field exercise.",
    sky=Vec4(0.53, 0.76, 0.96, 1), fog=Vec4(0.72, 0.85, 0.97, 1),
    sun=Vec4(1.0, 0.97, 0.88, 1), ambient=Vec4(0.55, 0.57, 0.66, 1),
    start=Vec3(0, -20, 2.0), portal=Vec3(0, 30, 1.2),
    build=_build_alfea, gem_goal=5, gem_name="magic crystal",
    enemies=[Spawn(Vec3(-20, 6, 2), "ghoul"), Spawn(Vec3(22, 4, 2), "ghoul"),
             Spawn(Vec3(-8, 24, 2), "ghoul"), Spawn(Vec3(14, 26, 2), "ghoul"),
             Spawn(Vec3(-34, -18, 2), "ghoul"), Spawn(Vec3(34, -16, 2), "ghoul"),
             Spawn(Vec3(0, -44, 2), "wisp"), Spawn(Vec3(-40, 30, 8), "wisp")],
    gems=[Vec3(-38, 8, 8.2), Vec3(38, 8, 11.2), Vec3(0, -34, 14.2),
          Vec3(-30, -26, 7.2), Vec3(30, -26, 7.2), Vec3(0, 0, 4.6),
          Vec3(-18, -8, 1.4), Vec3(18, -8, 1.4)],
    hearts=[Vec3(-46, 46, 1.4), Vec3(46, 46, 1.4)],
)

LEVEL_BATTLE_ALFEA = Level(
    key="battle_alfea", name="The Battle of Alfea",
    subtitle="All three of them. Every student in the courtyard.",
    sky=Vec4(0.22, 0.13, 0.18, 1), fog=Vec4(0.32, 0.20, 0.24, 1),
    sun=Vec4(1.0, 0.72, 0.60, 1), ambient=Vec4(0.44, 0.36, 0.40, 1),
    start=Vec3(0, -40, 2.0), portal=Vec3(0, 0, 3.6),
    build=lambda b: _build_alfea(b, besieged=True), gem_goal=0,
    enemies=[Spawn(Vec3(-14, 20, 10), "icy"), Spawn(Vec3(14, 20, 10), "darcy"),
             Spawn(Vec3(0, 32, 10), "stormy"),
             Spawn(Vec3(-24, 0, 2), "decay"), Spawn(Vec3(24, 0, 2), "decay"),
             Spawn(Vec3(0, -14, 2), "decay"), Spawn(Vec3(-34, 24, 2), "decay"),
             Spawn(Vec3(34, 24, 2), "decay"),
             Spawn(Vec3(-40, -30, 2), "ghoul"), Spawn(Vec3(40, -30, 2), "ghoul")],
    gems=[Vec3(-38, 8, 8.2), Vec3(38, 8, 11.2), Vec3(0, -34, 14.2)],
    hearts=[Vec3(-30, -26, 7.2), Vec3(30, -26, 7.2), Vec3(0, -50, 1.6)],
)


# ---------------------------------------------------------------------------
# Chapter 3 - Black Mud Swamp
# ---------------------------------------------------------------------------
def _build_swamp(b: WorldBuilder) -> None:
    rng = random.Random(29)
    mud_a = Vec4(0.30, 0.30, 0.20, 1)
    mud_b = Vec4(0.25, 0.26, 0.17, 1)
    bark = Vec4(0.26, 0.21, 0.16, 1)
    water = Vec4(0.24, 0.34, 0.26, 0.66)
    rock = Vec4(0.40, 0.40, 0.36, 1)

    b.mesh.grid_ground(200, 200, mud_a, mud_b, step=12.0)
    b.clip((0, 0, -2.0), (240, 240, 4.0))
    b.bounds(80, 80)

    # Standing water everywhere, with dry hummocks to cross on.
    for _ in range(16):
        x, y = rng.uniform(-66, 66), rng.uniform(-66, 66)
        r = rng.uniform(9, 18)
        b.glass().grid_ground(r, r, water, shade(water, 0.86, 0.66),
                              step=r * 0.5, center=(x, y, 0.22))
    for _ in range(30):
        x, y = rng.uniform(-64, 64), rng.uniform(-64, 64)
        s = rng.uniform(3.0, 7.0)
        b.solid((x, y, 0.35), (s, s * 0.8, 0.7), shade(mud_a, 1.18))

    # Knut's hut, up on stilts in the middle of the bog.
    hut = Vec4(0.38, 0.28, 0.20, 1)
    for sx in (-3.4, 3.4):
        for sy in (-3.4, 3.4):
            b.mesh.cylinder((sx, sy, 0), 0.4, 0.34, 3.0, bark, segments=6)
            b.boxes.append((Vec3(sx, sy, 1.5), Vec3(0.5, 0.5, 1.5)))
    b.solid((0, 0, 3.2), (10, 10, 0.5), hut, shade(hut, 1.12))
    b.solid((0, 4.6, 5.4), (10, 0.6, 4.0), hut)
    b.solid((-4.6, 0, 5.4), (0.6, 10, 4.0), hut)
    b.solid((4.6, 0, 5.4), (0.6, 10, 4.0), hut)
    b.mesh.prism((0, 0, 8.2), (11, 11, 3.0), Vec4(0.30, 0.26, 0.18, 1))
    for i in range(5):     # ramp up to the doorway
        b.solid((0, -6.0 - i * 2.2, 3.0 - i * 0.55), (4.0, 2.4, 0.4),
                shade(hut, 0.9))
    b.decor().sphere((0, 0, 6.4), 0.7, Vec4(0.95, 0.62, 0.25, 1), segments=8,
                     rings=6)

    # Dead trees and hanging moss.
    for _ in range(60):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(16, 74)
        x, y = math.cos(a) * r, math.sin(a) * r
        _dead_tree(b, x, y, 0, rng.uniform(5.0, 11.0), bark, rng)
        if rng.random() < 0.4:
            b.glass().sphere((x + rng.uniform(-1, 1), y + rng.uniform(-1, 1),
                              rng.uniform(4.0, 8.0)), rng.uniform(1.0, 2.2),
                             Vec4(0.34, 0.44, 0.28, 0.55), segments=7, rings=5,
                             squash=1.8)

    # Stepping stones out to the far corners, where the gems are.
    for i, (px, py, pz) in enumerate(((-20, -20, 2.0), (-32, -30, 3.4),
                                      (-44, -40, 4.8), (24, -24, 2.0),
                                      (36, -34, 3.4), (30, 30, 2.6),
                                      (-28, 34, 3.0))):
        b.solid((px, py, pz), (7, 7, 1.0), shade(rock, 1.0),
                shade(Vec4(0.36, 0.52, 0.34, 1), 1.1))

    for _ in range(14):
        x, y = rng.uniform(-70, 70), rng.uniform(-70, 70)
        s = rng.uniform(2.0, 4.5)
        b.solid((x, y, s * 0.35), (s, s * 1.2, s * 0.7),
                shade(rock, rng.uniform(0.75, 1.0)))


LEVEL_SWAMP = Level(
    key="swamp", name="Black Mud Swamp", subtitle="Knut's hideout. And its landlords.",
    sky=Vec4(0.30, 0.34, 0.28, 1), fog=Vec4(0.34, 0.38, 0.30, 1),
    sun=Vec4(0.86, 0.90, 0.76, 1), ambient=Vec4(0.42, 0.46, 0.40, 1),
    start=Vec3(0, -46, 2.0), portal=Vec3(0, 0, 4.0),
    build=_build_swamp, gem_goal=4, gem_name="swamp crystal",
    enemies=[Spawn(Vec3(0, 6, 4), "knut"),
             Spawn(Vec3(-14, -6, 2), "ghoul"), Spawn(Vec3(14, -6, 2), "ghoul"),
             Spawn(Vec3(-10, 16, 2), "ghoul"), Spawn(Vec3(12, 18, 2), "ghoul"),
             Spawn(Vec3(-30, 0, 2), "troll"), Spawn(Vec3(30, 4, 2), "troll"),
             Spawn(Vec3(-24, 30, 6), "wisp"), Spawn(Vec3(26, 28, 6), "wisp")],
    gems=[Vec3(-44, -40, 6.4), Vec3(36, -34, 5.0), Vec3(30, 30, 4.2),
          Vec3(-28, 34, 4.6), Vec3(0, 0, 4.6), Vec3(-20, -20, 3.6)],
    hearts=[Vec3(-32, -30, 5.0), Vec3(24, -24, 3.6)],
)


# ---------------------------------------------------------------------------
# Chapters 4 and 8 - Cloud Tower School for Witches
# ---------------------------------------------------------------------------
def _build_cloudtower(b: WorldBuilder, fallen: bool = False) -> None:
    """Cloud Tower. ``fallen`` is Chapter 8: the Trix hold the school and the
    Army of Decay is loose in it, so the rune lights have gone rotten."""
    rng = random.Random(47)
    slab_a = Vec4(0.30, 0.26, 0.40, 1)
    slab_b = Vec4(0.25, 0.21, 0.35, 1)
    obsidian = Vec4(0.19, 0.16, 0.28, 1)
    rune = Vec4(0.70, 0.35, 0.95, 1)
    if fallen:
        slab_a = Vec4(0.28, 0.26, 0.26, 1)
        slab_b = Vec4(0.23, 0.22, 0.22, 1)
        rune = Vec4(0.55, 0.72, 0.28, 1)     # decay green, not witch violet

    b.mesh.grid_ground(110, 110, slab_a, slab_b, step=9.0)
    b.clip((0, 0, -2.0), (130, 130, 4.0))
    b.bounds(52, 52, height=90)

    # Outer ring of buttresses, each capped with a rune light.
    segs = 24
    for i in range(segs):
        a = math.tau * i / segs
        x, y = math.cos(a) * 48.0, math.sin(a) * 48.0
        h = 14.0 + (4.0 if i % 3 == 0 else 0.0)
        b.solid((x, y, h * 0.5), (6.0, 6.0, h),
                shade(obsidian, 0.9 + 0.2 * (i % 2)))
        if i % 3 == 0:
            b.decor().sphere((x * 0.86, y * 0.86, h + 1.2), 0.85, rune,
                             segments=8, rings=6)

    # The tower proper: a stack of twisted spires around a central hall.
    for i in range(6):
        a = math.tau * i / 6
        _spire(b, math.cos(a) * 22.0, math.sin(a) * 22.0, 3.4,
               20.0 + (i % 3) * 6.0, obsidian, rune)
    b.solid((0, 26, 11.0), (26, 12, 22.0), shade(obsidian, 1.1),
            shade(slab_a, 1.1))
    _spire(b, 0, 26, 7.0, 34.0, shade(obsidian, 1.05), rune, segments=12)
    b.arch(0, 19.0, 8.0, 10.0, shade(slab_a, 1.15))

    # Stepped dais at the centre, and the floating stairs up to it.
    for i, r in enumerate((17.0, 13.0, 9.0)):
        b.solid((0, 0, 0.6 + i * 1.4), (r * 2, r * 2, 1.4),
                shade(slab_a, 1.0 + i * 0.06))
    b.decor().cylinder((0, 0, 4.8), 3.2, 2.4, 1.0, shade(rune, 0.6),
                       segments=14)

    # Four floating platforms - the fight goes vertical fast.
    for i in range(4):
        a = math.tau * i / 4 + math.pi / 4
        x, y = math.cos(a) * 30.0, math.sin(a) * 30.0
        b.solid((x, y, 10.0), (8, 8, 1.4), shade(slab_a, 1.1), rune)
        b.decor().cylinder((x, y, 0), 1.5, 1.0, 9.3, obsidian, segments=9)
    # A spiral of steps so a grounded player can still get up there.
    for i in range(10):
        a = math.tau * i / 10 * 1.6
        b.solid((math.cos(a) * 21.0, math.sin(a) * 21.0, 2.0 + i * 0.95),
                (5.5, 5.5, 0.9), shade(slab_b, 1.15))

    for _ in range(30):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(6, 50)
        b.glass().sphere((math.cos(a) * r, math.sin(a) * r,
                          rng.uniform(30, 44)), rng.uniform(4, 10),
                         Vec4(0.34, 0.30, 0.46, 0.45) if not fallen
                         else Vec4(0.32, 0.34, 0.24, 0.50),
                         segments=8, rings=5, squash=0.45)


LEVEL_CLOUDTOWER = Level(
    key="cloudtower", name="Cloud Tower", subtitle="The corridors move. The Book of Fate does not.",
    sky=Vec4(0.15, 0.11, 0.22, 1), fog=Vec4(0.22, 0.17, 0.32, 1),
    sun=Vec4(0.80, 0.72, 1.0, 1), ambient=Vec4(0.40, 0.36, 0.52, 1),
    start=Vec3(0, -40, 2.0), portal=Vec3(0, 0, 5.8),
    build=_build_cloudtower, gem_goal=4, gem_name="page",
    enemies=[Spawn(Vec3(0, 14, 10), "darcy"),
             Spawn(Vec3(-30, 30, 12), "wisp"), Spawn(Vec3(30, 30, 12), "wisp"),
             Spawn(Vec3(-30, -30, 12), "wisp"), Spawn(Vec3(30, -30, 12), "wisp"),
             Spawn(Vec3(-18, 0, 3), "ghoul"), Spawn(Vec3(18, 0, 3), "ghoul"),
             Spawn(Vec3(0, -20, 3), "ghoul")],
    gems=[Vec3(-30, 30, 12.5), Vec3(30, 30, 12.5), Vec3(-30, -30, 12.5),
          Vec3(30, -30, 12.5), Vec3(0, 0, 6.2)],
    hearts=[Vec3(0, -34, 1.6), Vec3(0, 34, 1.6)],
)

LEVEL_SIEGE_CLOUDTOWER = Level(
    key="siege_cloudtower", name="Cloud Tower Has Fallen",
    subtitle="The Army of Decay holds the school.",
    sky=Vec4(0.14, 0.14, 0.11, 1), fog=Vec4(0.22, 0.22, 0.16, 1),
    sun=Vec4(0.86, 0.90, 0.66, 1), ambient=Vec4(0.40, 0.42, 0.34, 1),
    start=Vec3(0, -40, 2.0), portal=Vec3(0, 0, 5.8),
    build=lambda b: _build_cloudtower(b, fallen=True), gem_goal=0,
    enemies=[Spawn(Vec3(0, 14, 10), "icy"),
             Spawn(Vec3(-20, 0, 3), "decay"), Spawn(Vec3(20, 0, 3), "decay"),
             Spawn(Vec3(0, -18, 3), "decay"), Spawn(Vec3(-14, 24, 3), "decay"),
             Spawn(Vec3(14, 24, 3), "decay"),
             Spawn(Vec3(-30, 30, 12), "wisp"), Spawn(Vec3(30, 30, 12), "wisp"),
             Spawn(Vec3(-34, -30, 3), "ghoul"), Spawn(Vec3(34, -30, 3), "ghoul")],
    gems=[Vec3(-30, 30, 12.5), Vec3(30, 30, 12.5)],
    hearts=[Vec3(0, -34, 1.6), Vec3(0, 34, 1.6), Vec3(0, 0, 6.2)],
)


# ---------------------------------------------------------------------------
# Chapter 5 - Lake Roccaluce
# ---------------------------------------------------------------------------
def _build_roccaluce(b: WorldBuilder) -> None:
    rng = random.Random(67)
    snow_a = Vec4(0.82, 0.86, 0.92, 1)
    snow_b = Vec4(0.75, 0.80, 0.88, 1)
    ice = Vec4(0.66, 0.84, 0.95, 1)
    rock = Vec4(0.48, 0.50, 0.56, 1)
    pine = Vec4(0.22, 0.36, 0.34, 1)

    b.mesh.grid_ground(200, 200, snow_a, snow_b, step=12.0)
    b.clip((0, 0, -2.0), (240, 240, 4.0))
    b.bounds(78, 78)

    # The frozen lake: a broad sheet of ice in the middle of the bowl.
    b.mesh.grid_ground(84, 84, shade(ice, 1.04), shade(ice, 0.94), step=10.5,
                       center=(0, 0, 0.08))
    b.glass().grid_ground(84, 84, Vec4(0.70, 0.88, 1.0, 0.30),
                          Vec4(0.62, 0.82, 0.98, 0.30), step=10.5,
                          center=(0, 0, 0.30))

    # Ice shards pushed up through the surface - cover, and something to fly over.
    for _ in range(34):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(10, 40)
        x, y = math.cos(a) * r, math.sin(a) * r
        h = rng.uniform(3.0, 9.0)
        b.solid((x, y, h * 0.42), (rng.uniform(1.6, 3.4),
                                   rng.uniform(1.6, 3.4), h),
                Vec4(ice[0], ice[1], ice[2], 1))
        b.decor().cylinder((x, y, h * 0.9), rng.uniform(0.8, 1.6), 0.0,
                           rng.uniform(2.0, 4.5), shade(ice, 1.15), segments=6)

    # Daphne's shrine at the heart of the lake, where the water never froze.
    for i, r in enumerate((11.0, 8.0, 5.5)):
        b.solid((0, 0, 0.5 + i * 1.1), (r * 2, r * 2, 1.1),
                shade(rock, 1.0 + i * 0.05))
    for i in range(8):
        a = math.tau * i / 8
        px, py = math.cos(a) * 7.0, math.sin(a) * 7.0
        b.mesh.cylinder((px, py, 3.8), 0.42, 0.34, 6.0, shade(rock, 1.1),
                        segments=7)
        b.boxes.append((Vec3(px, py, 6.8), Vec3(0.5, 0.5, 3.0)))
        b.decor().sphere((px, py, 10.2), 0.5, Vec4(0.95, 0.92, 0.72, 1),
                         segments=7, rings=5)
    b.glass().sphere((0, 0, 7.0), 3.0, Vec4(0.95, 0.90, 0.70, 0.32),
                     segments=12, rings=8)

    # Frozen shelves stepping up to the ridge, and pines on the shore.
    for i, (px, py, pz) in enumerate(((-26, -22, 4.0), (-38, -30, 7.0),
                                      (26, -22, 4.0), (38, -30, 7.0),
                                      (-30, 28, 6.0), (30, 28, 6.0),
                                      (0, 42, 9.0))):
        b.solid((px, py, pz), (9, 9, 1.2), Vec4(ice[0], ice[1], ice[2], 1),
                shade(ice, 1.18))
    for _ in range(46):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(46, 74)
        x, y = math.cos(a) * r, math.sin(a) * r
        h = rng.uniform(5.0, 9.0)
        b.mesh.cylinder((x, y, 0), 0.42, 0.30, h * 0.4, Vec4(0.32, 0.26, 0.22, 1),
                        segments=6)
        for k in range(3):
            b.mesh.cylinder((x, y, h * 0.35 + k * h * 0.22),
                            2.2 - k * 0.6, 0.0, h * 0.40,
                            shade(pine, 0.9 + 0.1 * k), segments=8)
        b.boxes.append((Vec3(x, y, h * 0.4), Vec3(0.6, 0.6, h * 0.4)))
    for _ in range(16):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(44, 70)
        s = rng.uniform(2.5, 6.0)
        b.solid((math.cos(a) * r, math.sin(a) * r, s * 0.4),
                (s, s * 1.2, s * 0.8), shade(rock, rng.uniform(0.8, 1.1)))


LEVEL_ROCCALUCE = Level(
    key="roccaluce", name="Lake Roccaluce", subtitle="Daphne is waiting. So is Icy.",
    sky=Vec4(0.62, 0.72, 0.86, 1), fog=Vec4(0.80, 0.87, 0.95, 1),
    sun=Vec4(0.92, 0.95, 1.0, 1), ambient=Vec4(0.60, 0.64, 0.74, 1),
    start=Vec3(0, -50, 2.0), portal=Vec3(0, 0, 4.2),
    build=_build_roccaluce, gem_goal=4, gem_name="frozen tear",
    enemies=[Spawn(Vec3(0, 16, 10), "icy"),
             Spawn(Vec3(-20, -6, 3), "ghoul"), Spawn(Vec3(20, -6, 3), "ghoul"),
             Spawn(Vec3(-14, 22, 3), "ghoul"), Spawn(Vec3(14, 22, 3), "ghoul"),
             Spawn(Vec3(-32, 8, 8), "wisp"), Spawn(Vec3(32, 8, 8), "wisp"),
             Spawn(Vec3(0, -30, 3), "troll")],
    gems=[Vec3(-38, -30, 9.0), Vec3(38, -30, 9.0), Vec3(-30, 28, 8.0),
          Vec3(30, 28, 8.0), Vec3(0, 42, 11.0), Vec3(0, 0, 4.6)],
    hearts=[Vec3(-26, -22, 6.0), Vec3(26, -22, 6.0)],
)


# ---------------------------------------------------------------------------
# Chapter 6 - Red Fountain School for Heroics and Bravery
# ---------------------------------------------------------------------------
def _build_redfountain(b: WorldBuilder) -> None:
    rng = random.Random(83)
    ground_a = Vec4(0.52, 0.46, 0.36, 1)
    ground_b = Vec4(0.46, 0.41, 0.32, 1)
    wall = Vec4(0.72, 0.36, 0.30, 1)
    trim = Vec4(0.92, 0.78, 0.38, 1)
    steel = Vec4(0.60, 0.62, 0.68, 1)

    b.mesh.grid_ground(190, 190, ground_a, ground_b, step=11.0)
    b.clip((0, 0, -2.0), (230, 230, 4.0))
    b.bounds(84, 84)

    # The training arena: a sunken oval ringed by tiered seating.
    b.mesh.grid_ground(60, 60, shade(ground_a, 1.12), shade(ground_a, 1.04),
                       step=10.0, center=(0, 0, 0.06))
    for i, r in enumerate((34.0, 38.0, 42.0)):
        segs = 28
        for k in range(segs):
            a = math.tau * k / segs
            b.solid((math.cos(a) * r, math.sin(a) * r, 0.7 + i * 1.4),
                    (6.5, 6.5, 1.4 + i * 1.4), shade(wall, 0.85 + i * 0.08))

    # The main hall, with the launch rails the Specialists' ships run on.
    b.solid((0, 58, 12.0), (44, 18, 24.0), wall, shade(wall, 1.1))
    b.mesh.prism((0, 58, 27.0), (46, 19, 8.0), trim)
    for x in (-24, 24):
        b.tower(x, 58, 6.0, 30.0, shade(wall, 0.92), trim)
    b.arch(0, 48.0, 10.0, 11.0, shade(trim, 0.9))
    for x in range(-16, 17, 8):
        b.decor().box((x, 48.4, 9.0), (3.4, 0.3, 5.0), Vec4(0.95, 0.85, 0.45, 1))
    for sx in (-14, 14):
        b.solid((sx, 34, 14.0), (3.0, 26, 0.8), steel)
        b.decor().cylinder((sx, 22, 14.4), 1.5, 1.1, 4.0, shade(steel, 1.15),
                           segments=8)

    # Weapon racks and training dummies around the arena floor.
    for i in range(10):
        a = math.tau * i / 10
        x, y = math.cos(a) * 24.0, math.sin(a) * 24.0
        b.solid((x, y, 1.0), (2.4, 1.0, 2.0), Vec4(0.42, 0.32, 0.24, 1))
        for k in (-0.6, 0.0, 0.6):
            b.decor().cylinder((x + k, y, 2.0), 0.09, 0.06, 2.6, steel,
                               segments=5)
    for i in range(6):
        a = math.tau * i / 6 + 0.4
        x, y = math.cos(a) * 15.0, math.sin(a) * 15.0
        b.mesh.cylinder((x, y, 0), 0.30, 0.26, 2.2, Vec4(0.40, 0.30, 0.22, 1),
                        segments=6)
        b.mesh.sphere((x, y, 2.7), 0.60, Vec4(0.66, 0.58, 0.46, 1),
                      segments=8, rings=6)
        b.boxes.append((Vec3(x, y, 1.4), Vec3(0.5, 0.5, 1.4)))

    # Watchtowers and outer walls - the Trix came straight over these.
    for i in range(8):
        a = math.tau * i / 8
        x, y = math.cos(a) * 66.0, math.sin(a) * 66.0
        b.tower(x, y, 4.0, 16.0, shade(wall, 0.88), trim, segments=9)
    for i in range(6):
        b.solid((-40 + i * 16, -70, 4.0), (16, 3.0, 8.0), shade(wall, 0.8))

    for _ in range(18):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(50, 78)
        b.tree(math.cos(a) * r, math.sin(a) * r, 0, rng.uniform(4.0, 6.0),
               Vec4(0.40, 0.30, 0.20, 1), Vec4(0.34, 0.48, 0.28, 1), rng)


LEVEL_REDFOUNTAIN = Level(
    key="redfountain", name="Red Fountain", subtitle="School of Heroics and Bravery. Under attack.",
    sky=Vec4(0.42, 0.34, 0.44, 1), fog=Vec4(0.56, 0.44, 0.46, 1),
    sun=Vec4(1.0, 0.86, 0.70, 1), ambient=Vec4(0.52, 0.46, 0.50, 1),
    start=Vec3(0, -46, 2.0), portal=Vec3(0, 40, 1.4),
    build=_build_redfountain, gem_goal=4, gem_name="codex shard",
    enemies=[Spawn(Vec3(0, 16, 11), "stormy"),
             Spawn(Vec3(-18, 0, 2), "ghoul"), Spawn(Vec3(18, 0, 2), "ghoul"),
             Spawn(Vec3(-10, 24, 2), "ghoul"), Spawn(Vec3(10, 24, 2), "ghoul"),
             Spawn(Vec3(0, -20, 2), "ghoul"),
             Spawn(Vec3(-26, -18, 2), "troll"), Spawn(Vec3(26, -18, 2), "troll"),
             Spawn(Vec3(-34, 26, 9), "wisp"), Spawn(Vec3(34, 26, 9), "wisp")],
    gems=[Vec3(-14, 34, 15.6), Vec3(14, 34, 15.6), Vec3(-40, 0, 7.0),
          Vec3(40, 0, 7.0), Vec3(0, 0, 1.6)],
    hearts=[Vec3(-24, -24, 4.0), Vec3(24, -24, 4.0)],
)


# ---------------------------------------------------------------------------
# Chapter 7 - Pixie Village
# ---------------------------------------------------------------------------
def _build_pixievillage(b: WorldBuilder) -> None:
    rng = random.Random(97)
    grass_a = Vec4(0.44, 0.74, 0.42, 1)
    grass_b = Vec4(0.38, 0.68, 0.38, 1)
    stalk = Vec4(0.92, 0.90, 0.80, 1)

    b.mesh.grid_ground(180, 180, grass_a, grass_b, step=9.0)
    b.clip((0, 0, -2.0), (220, 220, 4.0))
    b.bounds(72, 72)

    # Toadstool houses: caps in pixie colours, doors at pixie scale.
    caps = [Vec4(0.95, 0.42, 0.48, 1), Vec4(0.98, 0.72, 0.30, 1),
            Vec4(0.60, 0.55, 0.95, 1), Vec4(0.45, 0.85, 0.90, 1),
            Vec4(0.95, 0.60, 0.85, 1), Vec4(0.75, 0.92, 0.45, 1)]
    for i in range(22):
        a = math.tau * i / 22 + rng.uniform(-0.1, 0.1)
        r = rng.uniform(14, 44)
        x, y = math.cos(a) * r, math.sin(a) * r
        h = rng.uniform(2.6, 5.2)
        cap = caps[i % len(caps)]
        b.mesh.cylinder((x, y, 0), 1.15, 0.95, h, stalk, segments=9)
        b.mesh.cylinder((x, y, h), 2.9, 0.0, 2.4, cap, segments=11)
        b.mesh.box((x, y - 0.98, 0.7), (0.9, 0.3, 1.4),
                   Vec4(0.42, 0.30, 0.22, 1))
        for _ in range(3):     # spots on the cap
            sa = rng.uniform(0, math.tau)
            b.decor().sphere((x + math.cos(sa) * 1.5, y + math.sin(sa) * 1.5,
                              h + 0.9), 0.32, shade(cap, 1.4), segments=6,
                             rings=5)
        b.boxes.append((Vec3(x, y, h * 0.5), Vec3(1.2, 1.2, h * 0.5)))

    # The great tree at the centre, with the Codex vault in its roots.
    b.mesh.cylinder((0, 0, 0), 4.6, 3.2, 12.0, Vec4(0.46, 0.34, 0.24, 1),
                    segments=14)
    b.boxes.append((Vec3(0, 0, 6.0), Vec3(4.2, 4.2, 6.0)))
    for k in range(4):
        b.mesh.cylinder((0, 0, 11.0 + k * 2.6), 11.0 - k * 2.2, 0.0,
                        4.2 + k * 0.4, shade(Vec4(0.36, 0.68, 0.36, 1),
                                             0.86 + 0.10 * k), segments=13)
    # Broad roots you can run up to reach the canopy platforms.
    for i in range(6):
        a = math.tau * i / 6
        for k in range(4):
            rr = 6.0 + k * 3.6
            b.solid((math.cos(a) * rr, math.sin(a) * rr, 0.6 + k * 1.5),
                    (5.0, 5.0, 1.1), Vec4(0.50, 0.38, 0.26, 1),
                    Vec4(0.42, 0.70, 0.40, 1))
    # Canopy platforms - leaf pads held up on stems.
    for i in range(6):
        a = math.tau * i / 6 + 0.5
        x, y = math.cos(a) * 20.0, math.sin(a) * 20.0
        z = 9.0 + (i % 3) * 3.5
        b.solid((x, y, z), (8, 8, 0.9), Vec4(0.40, 0.72, 0.40, 1),
                Vec4(0.52, 0.85, 0.48, 1))
        b.decor().cylinder((x, y, 0), 0.7, 0.5, z - 0.5,
                           Vec4(0.40, 0.56, 0.32, 1), segments=7)

    # Flowers and fireflies - it should read as the friendliest place so far.
    for _ in range(70):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(8, 62)
        x, y = math.cos(a) * r, math.sin(a) * r
        h = rng.uniform(0.8, 2.0)
        b.mesh.cylinder((x, y, 0), 0.10, 0.08, h, Vec4(0.34, 0.60, 0.32, 1),
                        segments=5)
        b.mesh.sphere((x, y, h + 0.25), rng.uniform(0.30, 0.55),
                      caps[rng.randrange(len(caps))], segments=7, rings=5)
    for _ in range(26):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(10, 58)
        b.glass().sphere((math.cos(a) * r, math.sin(a) * r,
                          rng.uniform(2.0, 7.0)), rng.uniform(0.4, 0.8),
                         Vec4(1.0, 0.95, 0.55, 0.60), segments=6, rings=5)
    for _ in range(20):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(50, 68)
        b.tree(math.cos(a) * r, math.sin(a) * r, 0, rng.uniform(4.5, 7.0),
               Vec4(0.44, 0.32, 0.22, 1), Vec4(0.34, 0.66, 0.34, 1), rng)


LEVEL_PIXIEVILLAGE = Level(
    key="pixievillage", name="Pixie Village", subtitle="The last piece of the Codex.",
    sky=Vec4(0.60, 0.82, 0.92, 1), fog=Vec4(0.78, 0.90, 0.90, 1),
    sun=Vec4(1.0, 0.98, 0.86, 1), ambient=Vec4(0.60, 0.62, 0.62, 1),
    start=Vec3(0, -50, 2.0), portal=Vec3(0, 0, 12.6),
    build=_build_pixievillage, gem_goal=5, gem_name="pixie",
    enemies=[Spawn(Vec3(0, 18, 12), "darcy"),
             Spawn(Vec3(-16, 4, 2), "ghoul"), Spawn(Vec3(16, 4, 2), "ghoul"),
             Spawn(Vec3(-8, 26, 2), "ghoul"), Spawn(Vec3(8, 26, 2), "ghoul"),
             Spawn(Vec3(0, -22, 2), "ghoul"), Spawn(Vec3(-30, -14, 2), "ghoul"),
             Spawn(Vec3(30, -14, 2), "ghoul"),
             Spawn(Vec3(-26, 26, 10), "wisp"), Spawn(Vec3(26, 26, 10), "wisp"),
             Spawn(Vec3(0, 40, 2), "troll")],
    gems=[Vec3(20.0, 0.0, 11.0), Vec3(-10.0, 17.3, 14.5),
          Vec3(-10.0, -17.3, 11.0), Vec3(10.0, 17.3, 18.0),
          Vec3(-20.0, 0.0, 11.0), Vec3(10.0, -17.3, 14.5)],
    hearts=[Vec3(-34, -30, 1.6), Vec3(34, -30, 1.6)],
)


# ---------------------------------------------------------------------------
# Home realms - one per fairy, each with a peacetime and a besieged state
# ---------------------------------------------------------------------------
def _in_approach(x: float, y: float, half_width: float = 9.0) -> bool:
    """True inside the corridor the player spawns in, looking north.

    Ring-placed props are skipped here so the first thing a chapter shows is
    its landmark, not the back of a pillar.
    """
    return y < -6.0 and abs(x) < half_width


def _blight(b: WorldBuilder, rng, count: int, rubble: Vec4,
            radius=(20, 70)) -> None:
    """Rubble and burning wreckage, shared by every besieged variant."""
    for _ in range(count):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(*radius)
        s = rng.uniform(1.4, 3.8)
        b.solid((math.cos(a) * r, math.sin(a) * r, s * 0.35),
                (s, s * 1.3, s * 0.7), shade(rubble, rng.uniform(0.55, 0.9)))
    for _ in range(count // 2):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(*radius)
        b.glass().sphere((math.cos(a) * r, math.sin(a) * r,
                          rng.uniform(0.8, 2.4)), rng.uniform(1.2, 2.6),
                         Vec4(0.95, 0.45, 0.20, 0.45), segments=7, rings=5)


# --- Solaria (Stella) ------------------------------------------------------
def _build_solaria(b: WorldBuilder, besieged: bool = False) -> None:
    """The Sun Palace: white marble and gold under a permanent noon."""
    rng = random.Random(211)
    marble = Vec4(0.94, 0.91, 0.84, 1)
    gold = Vec4(0.96, 0.78, 0.32, 1)
    sand = Vec4(0.90, 0.82, 0.62, 1)
    if besieged:
        marble = Vec4(0.62, 0.58, 0.56, 1)
        gold = Vec4(0.66, 0.52, 0.26, 1)
        sand = Vec4(0.58, 0.52, 0.42, 1)

    b.mesh.grid_ground(190, 190, sand, shade(sand, 0.94), step=12.0)
    b.clip((0, 0, -2.0), (230, 230, 4.0))
    b.bounds(80, 80)

    # A vast tiled plaza in front of the palace steps.
    b.mesh.grid_ground(76, 76, shade(marble, 1.0), shade(marble, 0.92),
                       step=9.5, center=(0, 0, 0.06))

    # The palace: a stepped ziggurat crowned with the sun disc.
    for i, (w, h) in enumerate(((46, 4.0), (36, 4.0), (26, 4.0))):
        b.solid((0, 44, 2.0 + i * 4.0), (w, 26 - i * 5, h), marble,
                shade(marble, 1.06))
    b.solid((0, 44, 15.0), (18, 16, 8.0), shade(marble, 1.04), gold)
    b.mesh.cylinder((0, 44, 19.0), 7.0, 0.0, 9.0, gold, segments=14)
    b.decor().sphere((0, 44, 31.0), 3.4, Vec4(1.0, 0.92, 0.45, 1),
                     segments=14, rings=10)
    for sx in (-1, 1):
        b.tower(sx * 26, 44, 5.0, 24.0, shade(marble, 0.96), gold)

    # Colonnade around the plaza - gold pillars, and something to fly between.
    for i in range(20):
        a = math.tau * i / 20
        x, y = math.cos(a) * 34.0, math.sin(a) * 34.0
        if _in_approach(x, y):
            continue
        b.mesh.cylinder((x, y, 0), 1.3, 1.1, 11.0, marble, segments=9)
        b.mesh.cylinder((x, y, 11.0), 1.7, 1.5, 1.2, gold, segments=9)
        b.boxes.append((Vec3(x, y, 6.0), Vec3(1.4, 1.4, 6.0)))

    # Floating sun terraces - Solaria's rings, in miniature.
    for i in range(6):
        a = math.tau * i / 6 + 0.4
        x, y = math.cos(a) * 22.0, math.sin(a) * 22.0
        z = 13.0 + (i % 3) * 4.0
        b.solid((x, y, z), (9, 9, 1.2), shade(marble, 1.05), gold)
        b.decor().cylinder((x, y, z + 0.7), 0.6, 0.0, 3.0, gold, segments=8)

    # Obelisks and reflecting pools out on the sand.
    for i in range(8):
        a = math.tau * i / 8 + 0.2
        x, y = math.cos(a) * 58.0, math.sin(a) * 58.0
        if _in_approach(x, y):
            continue
        h = rng.uniform(10.0, 16.0)
        b.solid((x, y, h * 0.5), (3.0, 3.0, h), shade(gold, 0.9))
        b.decor().cylinder((x, y, h), 2.1, 0.0, 4.0, gold, segments=6)
    if not besieged:
        for (px, py) in ((-38, -14), (38, -14)):
            b.glass().grid_ground(20, 20, Vec4(0.55, 0.82, 0.95, 0.55),
                                  Vec4(0.48, 0.76, 0.92, 0.55), step=10.0,
                                  center=(px, py, 0.28))
    else:
        _blight(b, rng, 20, marble, radius=(18, 62))


# --- Lynphea (Flora) -------------------------------------------------------
def _build_lynphea(b: WorldBuilder, besieged: bool = False) -> None:
    """A world grown past human scale: flowers taller than the fairies."""
    rng = random.Random(223)
    moss = Vec4(0.32, 0.58, 0.30, 1)
    moss_b = Vec4(0.27, 0.51, 0.27, 1)
    bark = Vec4(0.42, 0.31, 0.22, 1)
    petal = [Vec4(0.98, 0.55, 0.72, 1), Vec4(0.95, 0.72, 0.35, 1),
             Vec4(0.72, 0.55, 0.95, 1), Vec4(0.98, 0.92, 0.55, 1)]
    if besieged:
        moss = Vec4(0.36, 0.34, 0.20, 1)
        moss_b = Vec4(0.30, 0.29, 0.17, 1)
        petal = [shade(p, 0.45) for p in petal]

    b.mesh.grid_ground(190, 190, moss, moss_b, step=11.0)
    b.clip((0, 0, -2.0), (230, 230, 4.0))
    b.bounds(80, 80)

    # Colossal flowers: a stem you can walk around and a petal disc on top.
    for i in range(14):
        a = math.tau * i / 14 + rng.uniform(-0.15, 0.15)
        r = rng.uniform(18, 52)
        x, y = math.cos(a) * r, math.sin(a) * r
        if _in_approach(x, y, 11.0):
            continue
        h = rng.uniform(8.0, 18.0)
        col = petal[i % len(petal)]
        b.mesh.cylinder((x, y, 0), 1.0, 0.7, h, Vec4(0.34, 0.56, 0.30, 1),
                        segments=8)
        b.boxes.append((Vec3(x, y, h * 0.5), Vec3(1.0, 1.0, h * 0.5)))
        # The petal disc doubles as a platform.
        b.solid((x, y, h), (11, 11, 0.9), col, shade(col, 1.15))
        for k in range(7):
            pa = math.tau * k / 7
            b.decor().cylinder((x + math.cos(pa) * 5.4, y + math.sin(pa) * 5.4,
                                h + 0.4), 2.2, 0.0, 2.0, shade(col, 1.1),
                               segments=6)
        b.decor().sphere((x, y, h + 1.2), 1.8, Vec4(0.98, 0.88, 0.40, 1),
                         segments=9, rings=6, squash=0.5)

    # The heart of the grove: one enormous tree with a spiral of broad roots.
    b.mesh.cylinder((0, 0, 0), 6.0, 4.0, 20.0, bark, segments=16)
    b.boxes.append((Vec3(0, 0, 10.0), Vec3(5.4, 5.4, 10.0)))
    for k in range(5):
        b.mesh.cylinder((0, 0, 18.0 + k * 3.0), 16.0 - k * 3.0, 0.0,
                        5.0 + k * 0.5, shade(moss, 0.80 + 0.12 * k),
                        segments=14)
    for i in range(10):
        a = math.tau * i / 10 * 1.8
        b.solid((math.cos(a) * (8.0 + i * 0.9), math.sin(a) * (8.0 + i * 0.9),
                 1.0 + i * 1.7), (6.0, 6.0, 1.1), bark, shade(moss, 1.2))

    # Vines, ferns and mushrooms filling the floor.
    for _ in range(80):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(10, 72)
        x, y = math.cos(a) * r, math.sin(a) * r
        kind = rng.random()
        if kind < 0.45:
            hh = rng.uniform(1.4, 3.2)
            for k in range(3):
                b.mesh.cylinder((x, y, hh * 0.3 * k), 2.0 - k * 0.5, 0.2,
                                hh * 0.5, shade(moss, 0.9 + 0.15 * k),
                                segments=7)
        elif kind < 0.75:
            hh = rng.uniform(1.0, 2.6)
            b.mesh.cylinder((x, y, 0), 0.30, 0.26, hh,
                            Vec4(0.88, 0.86, 0.76, 1), segments=6)
            b.mesh.cylinder((x, y, hh), 1.5, 0.0, 1.2,
                            petal[rng.randrange(len(petal))], segments=8)
        else:
            b.mesh.cylinder((x, y, 0), 0.14, 0.10, rng.uniform(1.0, 2.2),
                            Vec4(0.34, 0.58, 0.30, 1), segments=5)
            b.mesh.sphere((x, y, rng.uniform(1.2, 2.4)), rng.uniform(0.3, 0.6),
                          petal[rng.randrange(len(petal))], segments=6, rings=5)
    for _ in range(24):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(56, 76)
        b.tree(math.cos(a) * r, math.sin(a) * r, 0, rng.uniform(6.0, 10.0),
               bark, shade(moss, rng.uniform(0.85, 1.15)), rng)
    if besieged:
        _blight(b, rng, 22, Vec4(0.40, 0.34, 0.24, 1))


# --- Melody (Musa) ---------------------------------------------------------
def _build_melody(b: WorldBuilder, besieged: bool = False) -> None:
    """The realm of music: a valley built as one enormous instrument."""
    rng = random.Random(233)
    stone = Vec4(0.86, 0.74, 0.70, 1)
    lacquer = Vec4(0.80, 0.24, 0.28, 1)
    gold = Vec4(0.92, 0.76, 0.36, 1)
    jade = Vec4(0.42, 0.68, 0.60, 1)
    if besieged:
        stone = Vec4(0.56, 0.50, 0.48, 1)
        lacquer = Vec4(0.46, 0.18, 0.20, 1)
        gold = Vec4(0.58, 0.50, 0.30, 1)
        jade = Vec4(0.30, 0.42, 0.38, 1)

    b.mesh.grid_ground(190, 190, shade(stone, 0.86), shade(stone, 0.80),
                       step=12.0)
    b.clip((0, 0, -2.0), (230, 230, 4.0))
    b.bounds(78, 78)

    # Concentric amphitheatre steps down to a central stage.
    for i, r in enumerate((40.0, 33.0, 26.0, 19.0)):
        segs = 30
        for k in range(segs):
            a = math.tau * k / segs
            x, y = math.cos(a) * r, math.sin(a) * r
            if _in_approach(x, y, 10.0):
                continue          # the entrance aisle down to the stage
            b.solid((x, y, 0.7 + (3 - i) * 1.5),
                    (7.0, 7.0, 1.4 + (3 - i) * 1.5),
                    shade(stone, 0.88 + i * 0.05))
    b.mesh.grid_ground(26, 26, shade(lacquer, 1.05), shade(lacquer, 0.94),
                       step=6.5, center=(0, 0, 0.10))

    # Giant drums around the stage - solid, and you can stand on them.
    for i in range(6):
        a = math.tau * i / 6
        x, y = math.cos(a) * 13.0, math.sin(a) * 13.0
        h = rng.uniform(3.0, 5.0)
        b.mesh.cylinder((x, y, 0), 2.6, 2.6, h, lacquer, segments=12,
                        top_color=Vec4(0.94, 0.90, 0.82, 1))
        for k in range(8):
            ka = math.tau * k / 8
            b.decor().sphere((x + math.cos(ka) * 2.6, y + math.sin(ka) * 2.6,
                              h * 0.5), 0.28, gold, segments=6, rings=5)
        b.boxes.append((Vec3(x, y, h * 0.5), Vec3(2.6, 2.6, h * 0.5)))

    # A harp frame at the back of the valley: strings you can fly between.
    b.solid((0, 46, 14.0), (3.2, 3.2, 28.0), lacquer)
    b.solid((-22, 46, 9.0), (3.2, 3.2, 18.0), lacquer)
    b.solid((-11, 46, 27.0), (25, 3.0, 3.0), gold)
    for k in range(10):
        sx = -20.5 + k * 2.0
        b.decor().cylinder((sx, 46, 1.0), 0.10, 0.10, 24.0 - k * 1.6,
                           Vec4(0.95, 0.92, 0.80, 1), segments=4)
    # ...and a rank of organ pipes along the east wall, clear of the aisle.
    for k in range(12):
        py = -13.0 + k * 2.4
        h = 10.0 + abs(6 - k) * 2.2
        b.solid((46, py, h * 0.5), (2.0, 2.0, h), shade(gold, 0.95))

    # Pagoda pavilions on the ridge - Melody's architecture.
    for i in range(5):
        a = math.tau * i / 5 + 0.6
        x, y = math.cos(a) * 58.0, math.sin(a) * 58.0
        if _in_approach(x, y, 12.0):
            continue
        b.solid((x, y, 4.0), (14, 14, 8.0), stone, shade(stone, 1.06))
        for k in range(3):
            b.mesh.cylinder((x, y, 8.0 + k * 3.2), 11.0 - k * 2.6, 0.2,
                            2.0, shade(lacquer, 0.95 + 0.08 * k), segments=4)
        b.decor().cylinder((x, y, 17.0), 0.5, 0.0, 3.0, gold, segments=6)

    # Floating gongs - the platforms for this level.
    for i in range(6):
        a = math.tau * i / 6 + 0.3
        x, y = math.cos(a) * 30.0, math.sin(a) * 30.0
        z = 11.0 + (i % 3) * 4.0
        b.solid((x, y, z), (9, 9, 0.8), gold, shade(gold, 1.2))
        b.decor().cylinder((x, y, z + 0.5), 3.2, 3.0, 0.4, shade(jade, 1.1),
                           segments=14)
    if besieged:
        _blight(b, rng, 22, stone)


# --- Zenith (Tecna) --------------------------------------------------------
def _build_zenith(b: WorldBuilder, besieged: bool = False) -> None:
    """The technological realm: everything on a grid, nothing organic."""
    rng = random.Random(241)
    board = Vec4(0.13, 0.20, 0.24, 1)
    board_b = Vec4(0.10, 0.16, 0.20, 1)
    trace = Vec4(0.25, 0.90, 0.85, 1)
    plate = Vec4(0.42, 0.48, 0.55, 1)
    if besieged:
        trace = Vec4(0.90, 0.45, 0.25, 1)     # every indicator gone to alarm
        board = Vec4(0.18, 0.16, 0.16, 1)
        board_b = Vec4(0.14, 0.12, 0.12, 1)

    b.mesh.grid_ground(190, 190, board, board_b, step=8.0)
    b.clip((0, 0, -2.0), (230, 230, 4.0))
    b.bounds(78, 78)

    # Circuit traces etched across the floor.
    for i in range(26):
        if i % 2:
            x = rng.uniform(-70, 70)
            b.decor().box((x, 0, 0.10), (0.9, 150, 0.06), trace)
            b.decor().sphere((x, rng.uniform(-60, 60), 0.30), 0.7, trace,
                             segments=6, rings=5, squash=0.35)
        else:
            y = rng.uniform(-70, 70)
            b.decor().box((0, y, 0.10), (150, 0.9, 0.06), trace)
            b.decor().sphere((rng.uniform(-60, 60), y, 0.30), 0.7, trace,
                             segments=6, rings=5, squash=0.35)

    # The data core: stacked hexagonal drums at the centre.
    for i, (r, h) in enumerate(((14.0, 2.0), (11.0, 2.0), (8.0, 2.0))):
        b.mesh.cylinder((0, 0, i * 2.0), r, r * 0.92, h, plate, segments=6,
                        top_color=shade(plate, 1.15))
        b.boxes.append((Vec3(0, 0, i * 2.0 + h * 0.5), Vec3(r, r, h * 0.5)))
    b.decor().cylinder((0, 0, 6.0), 5.0, 3.0, 14.0,
                       Vec4(trace[0], trace[1], trace[2], 1), segments=6)
    b.glass().cylinder((0, 0, 6.0), 7.0, 5.0, 16.0,
                       Vec4(trace[0], trace[1], trace[2], 0.28), segments=10,
                       cap_top=False, cap_bottom=False)

    # Server towers on the grid, lit down one face.
    for i in range(12):
        a = math.tau * i / 12
        r = 30.0 + (i % 3) * 9.0
        x, y = math.cos(a) * r, math.sin(a) * r
        if _in_approach(x, y, 10.0):
            continue
        h = rng.uniform(14.0, 30.0)
        b.solid((x, y, h * 0.5), (7, 7, h), plate, shade(plate, 1.2))
        for k in range(int(h // 3)):
            b.decor().box((x, y - 3.6, 2.0 + k * 3.0), (4.2, 0.3, 0.9), trace)

    # Floating hexagonal pads, arranged as a lattice to fly through.
    for ring, (rr, zz) in enumerate(((20.0, 9.0), (30.0, 15.0), (40.0, 21.0))):
        for i in range(6):
            a = math.tau * i / 6 + ring * 0.5
            x, y = math.cos(a) * rr, math.sin(a) * rr
            b.solid((x, y, zz), (9, 9, 1.0), plate, trace)
            b.decor().cylinder((x, y, zz - 0.6), 3.2, 2.6, -2.4,
                               shade(plate, 0.8), segments=6)

    # Antenna masts on the perimeter.
    for i in range(8):
        a = math.tau * i / 8 + 0.4
        x, y = math.cos(a) * 62.0, math.sin(a) * 62.0
        b.mesh.cylinder((x, y, 0), 0.9, 0.35, 26.0, plate, segments=6)
        b.decor().sphere((x, y, 27.0), 1.2, trace, segments=7, rings=5)
        b.boxes.append((Vec3(x, y, 13.0), Vec3(1.0, 1.0, 13.0)))
    if besieged:
        _blight(b, rng, 22, plate)


# --- Andros (Aisha) --------------------------------------------------------
def _build_andros(b: WorldBuilder, besieged: bool = False) -> None:
    """An ocean realm: causeways and coral over open water."""
    rng = random.Random(251)
    sea = Vec4(0.16, 0.42, 0.58, 1)
    sea_b = Vec4(0.13, 0.36, 0.52, 1)
    coral = [Vec4(0.95, 0.48, 0.55, 1), Vec4(0.98, 0.68, 0.35, 1),
             Vec4(0.55, 0.85, 0.80, 1), Vec4(0.72, 0.55, 0.92, 1)]
    stone = Vec4(0.74, 0.78, 0.78, 1)
    if besieged:
        sea = Vec4(0.18, 0.26, 0.30, 1)
        sea_b = Vec4(0.14, 0.22, 0.26, 1)
        coral = [shade(c, 0.45) for c in coral]
        stone = Vec4(0.52, 0.52, 0.50, 1)

    # The sea is the floor: solid enough to stand on, visually translucent.
    b.mesh.grid_ground(200, 200, sea, sea_b, step=13.0)
    b.clip((0, 0, -2.0), (240, 240, 4.0))
    b.bounds(82, 82)
    b.glass().grid_ground(200, 200, Vec4(0.30, 0.62, 0.82, 0.42),
                          Vec4(0.24, 0.55, 0.78, 0.42), step=13.0,
                          center=(0, 0, 0.45))

    # The island city: a ringed platform reached by four causeways.
    for i, r in enumerate((22.0, 17.0, 12.0)):
        b.solid((0, 0, 0.8 + i * 1.5), (r * 2, r * 2, 1.5),
                shade(stone, 0.94 + i * 0.05))
    for i in range(4):
        a = math.tau * i / 4
        for k in range(9):
            rr = 24.0 + k * 5.0
            b.solid((math.cos(a) * rr, math.sin(a) * rr, 0.8),
                    (7.0, 7.0, 1.4), shade(stone, 0.90))
    # Domed halls on the island.
    for i in range(5):
        a = math.tau * i / 5 + 0.3
        x, y = math.cos(a) * 8.0, math.sin(a) * 8.0
        b.mesh.cylinder((x, y, 4.3), 3.2, 3.0, 4.5, stone, segments=10)
        b.mesh.sphere((x, y, 9.2), 3.3, shade(Vec4(0.40, 0.72, 0.85, 1), 1.0),
                      segments=11, rings=7, squash=0.72)
        b.boxes.append((Vec3(x, y, 6.5), Vec3(3.2, 3.2, 3.0)))

    # Coral towers rising out of the water - cover and platforms.
    for i in range(20):
        a = math.tau * i / 20 + rng.uniform(-0.12, 0.12)
        r = rng.uniform(30, 68)
        x, y = math.cos(a) * r, math.sin(a) * r
        if _in_approach(x, y, 10.0):
            continue
        h = rng.uniform(6.0, 20.0)
        col = coral[i % len(coral)]
        b.mesh.cylinder((x, y, 0), 3.0, 1.8, h, col, segments=9)
        b.boxes.append((Vec3(x, y, h * 0.5), Vec3(2.6, 2.6, h * 0.5)))
        for k in range(rng.randint(2, 4)):
            ka = rng.uniform(0, math.tau)
            bz = h * rng.uniform(0.45, 0.9)
            b.mesh.cylinder((x + math.cos(ka) * 1.4, y + math.sin(ka) * 1.4, bz),
                            1.2, 0.4, rng.uniform(2.5, 5.0), shade(col, 1.12),
                            segments=7)
        if h > 11.0:
            b.solid((x, y, h), (7, 7, 0.9), shade(col, 1.2),
                    Vec4(0.85, 0.95, 0.95, 1))

    # Standing waves, frozen mid-curl - Aisha's element, made into terrain.
    for i in range(9):
        a = math.tau * i / 9 + 0.25
        x, y = math.cos(a) * 46.0, math.sin(a) * 46.0
        for k in range(4):
            b.glass().sphere((x + k * 1.2, y, 1.0 + k * 1.6),
                             4.2 - k * 0.7,
                             Vec4(0.45, 0.80, 0.95, 0.45), segments=9, rings=6,
                             squash=0.55)
    if besieged:
        _blight(b, rng, 20, stone, radius=(24, 66))


# --- Home-realm level definitions ------------------------------------------
def _home(key, name, subtitle, builder, sky, fog, sun, ambient, start, portal,
          gem_name, gems, hearts, enemies, gem_goal, besieged=False) -> Level:
    return Level(key=key, name=name, subtitle=subtitle,
                 sky=sky, fog=fog, sun=sun, ambient=ambient,
                 start=start, portal=portal,
                 build=(lambda b, _f=builder: _f(b, besieged)),
                 gem_name=gem_name, gems=gems, hearts=hearts,
                 enemies=enemies, gem_goal=gem_goal)


# Peacetime enemy sets are light: these chapters introduce a realm.  The
# besieged versions field the Army of Decay and a Trix.
def _home_pair(fairy, name, builder, gem_name, palette, layout, boss) -> tuple:
    sky, fog, sun, amb = palette["calm"]
    dsky, dfog, dsun, damb = palette["dark"]
    start, portal, gems, hearts = layout
    calm = _home(
        "home_" + fairy, name, palette["sub_calm"], builder,
        sky, fog, sun, amb, start, portal, gem_name, gems, hearts,
        enemies=[Spawn(Vec3(0, 10, 3), "knut")] +
                [Spawn(p, "ghoul") for p in palette["mobs"]],
        gem_goal=min(4, len(gems)))
    siege = _home(
        "siege_" + fairy, name, palette["sub_dark"], builder,
        dsky, dfog, dsun, damb, start, portal, gem_name, gems, hearts,
        enemies=[Spawn(Vec3(0, 14, 11), boss)] +
                [Spawn(p, "decay") for p in palette["mobs"][:4]] +
                [Spawn(p, "ghoul") for p in palette["mobs"][4:]],
        gem_goal=0, besieged=True)
    return calm, siege


_MOBS_WIDE = [Vec3(-18, 4, 3), Vec3(18, 4, 3), Vec3(-12, 24, 3),
              Vec3(12, 24, 3), Vec3(0, 32, 3), Vec3(-28, -14, 3),
              Vec3(28, -14, 3)]

HOME_LEVELS = {}

# Bloom - Gardenia Park, Earth (already built above as chapter 1's setting)
HOME_LEVELS["bloom"] = (
    _home("home_bloom", "Gardenia Park", "Earth. No magic here. Usually.",
          _build_gardenia,
          Vec4(0.56, 0.78, 0.95, 1), Vec4(0.76, 0.87, 0.97, 1),
          Vec4(1.0, 0.98, 0.92, 1), Vec4(0.58, 0.60, 0.66, 1),
          Vec3(0, -40, 2.0), Vec3(0, 40, 1.2), "spark",
          [Vec3(-22, -22, 1.4), Vec3(22, -22, 1.4), Vec3(0, 0, 2.6),
           Vec3(34, 34, 1.6)],
          [Vec3(-34, 0, 1.4), Vec3(34, 0, 1.4)],
          [Spawn(Vec3(0, 8, 2), "knut"),
           Spawn(Vec3(-16, 2, 2), "ghoul"), Spawn(Vec3(16, 2, 2), "ghoul"),
           Spawn(Vec3(-10, 20, 2), "ghoul"), Spawn(Vec3(10, 20, 2), "ghoul"),
           Spawn(Vec3(0, 30, 2), "ghoul")], 0),
    _home("siege_bloom", "Gardenia Park", "They followed you home.",
          _build_gardenia,
          Vec4(0.20, 0.14, 0.18, 1), Vec4(0.32, 0.22, 0.24, 1),
          Vec4(1.0, 0.70, 0.58, 1), Vec4(0.44, 0.36, 0.40, 1),
          Vec3(0, -40, 2.0), Vec3(0, 40, 1.2), "spark",
          [Vec3(-22, -22, 1.4), Vec3(22, -22, 1.4), Vec3(0, 0, 2.6)],
          [Vec3(-34, 0, 1.4), Vec3(34, 0, 1.4)],
          [Spawn(Vec3(0, 14, 11), "stormy"),
           Spawn(Vec3(-18, 4, 2), "decay"), Spawn(Vec3(18, 4, 2), "decay"),
           Spawn(Vec3(-12, 24, 2), "decay"), Spawn(Vec3(12, 24, 2), "decay"),
           Spawn(Vec3(0, 32, 2), "ghoul"), Spawn(Vec3(-28, -14, 2), "ghoul"),
           Spawn(Vec3(28, -14, 2), "ghoul")], 0, besieged=True),
)

HOME_LEVELS["stella"] = _home_pair(
    "stella", "Solaria", _build_solaria, "sunstone",
    {"calm": (Vec4(0.42, 0.68, 0.95, 1), Vec4(0.86, 0.90, 0.98, 1),
              Vec4(1.0, 0.98, 0.88, 1), Vec4(0.66, 0.66, 0.68, 1)),
     "dark": (Vec4(0.26, 0.18, 0.22, 1), Vec4(0.40, 0.28, 0.26, 1),
              Vec4(1.0, 0.74, 0.58, 1), Vec4(0.46, 0.40, 0.42, 1)),
     "sub_calm": "The Sun Palace. Home, and she is late again.",
     "sub_dark": "They put out the sun.",
     "mobs": _MOBS_WIDE},
    layout=(Vec3(0, -46, 2.0), Vec3(0, 30, 1.4),
            [Vec3(-19.0, 11.0, 15.0), Vec3(19.0, 11.0, 19.0),
             Vec3(-19.0, -11.0, 19.0), Vec3(19.0, -11.0, 15.0),
             Vec3(0, 22, 15.0), Vec3(0, -22, 19.0)],
            [Vec3(-30, -30, 1.6), Vec3(30, -30, 1.6)]),
    boss="stormy")

HOME_LEVELS["flora"] = _home_pair(
    "flora", "Lynphea", _build_lynphea, "seed",
    {"calm": (Vec4(0.52, 0.76, 0.86, 1), Vec4(0.74, 0.88, 0.84, 1),
              Vec4(1.0, 0.98, 0.86, 1), Vec4(0.58, 0.62, 0.58, 1)),
     "dark": (Vec4(0.20, 0.20, 0.14, 1), Vec4(0.30, 0.30, 0.20, 1),
              Vec4(0.92, 0.86, 0.60, 1), Vec4(0.42, 0.42, 0.34, 1)),
     "sub_calm": "Everything here grew past its own scale.",
     "sub_dark": "The Army of Decay is in the grove.",
     "mobs": _MOBS_WIDE},
    layout=(Vec3(0, -50, 2.0), Vec3(0, 0, 18.4),
            [Vec3(-30.0, 12.0, 13.0), Vec3(30.0, 12.0, 17.0),
             Vec3(-24.0, -30.0, 11.0), Vec3(24.0, -30.0, 15.0),
             Vec3(0, 36, 13.0), Vec3(0, -36, 11.0)],
            [Vec3(-40, -40, 1.6), Vec3(40, -40, 1.6)]),
    boss="darcy")

HOME_LEVELS["musa"] = _home_pair(
    "musa", "Melody", _build_melody, "note",
    {"calm": (Vec4(0.86, 0.60, 0.58, 1), Vec4(0.92, 0.78, 0.72, 1),
              Vec4(1.0, 0.92, 0.82, 1), Vec4(0.62, 0.56, 0.56, 1)),
     "dark": (Vec4(0.22, 0.14, 0.18, 1), Vec4(0.34, 0.22, 0.26, 1),
              Vec4(0.96, 0.70, 0.70, 1), Vec4(0.44, 0.36, 0.40, 1)),
     "sub_calm": "The whole valley is built to be played.",
     "sub_dark": "Every string in the valley has been cut.",
     "mobs": _MOBS_WIDE},
    layout=(Vec3(0, -52, 2.0), Vec3(0, 0, 1.0),
            [Vec3(-30.0, 0.0, 13.0), Vec3(15.0, 26.0, 17.0),
             Vec3(-15.0, 26.0, 13.0), Vec3(15.0, -26.0, 15.0),
             Vec3(-15.0, -26.0, 19.0), Vec3(30.0, 0.0, 15.0)],
            [Vec3(-44, -20, 6.0), Vec3(44, -20, 6.0)]),
    boss="icy")

HOME_LEVELS["tecna"] = _home_pair(
    "tecna", "Zenith", _build_zenith, "data node",
    {"calm": (Vec4(0.10, 0.16, 0.22, 1), Vec4(0.16, 0.26, 0.32, 1),
              Vec4(0.80, 0.94, 1.0, 1), Vec4(0.44, 0.52, 0.56, 1)),
     "dark": (Vec4(0.20, 0.11, 0.09, 1), Vec4(0.30, 0.18, 0.14, 1),
              Vec4(1.0, 0.76, 0.60, 1), Vec4(0.46, 0.38, 0.36, 1)),
     "sub_calm": "Zenith. Everything measured, everything on a grid.",
     "sub_dark": "Every system in the realm is reading red.",
     "mobs": _MOBS_WIDE},
    layout=(Vec3(0, -50, 2.0), Vec3(0, 0, 7.0),
            [Vec3(20.0, 0.0, 10.5), Vec3(-10.0, 17.3, 10.5),
             Vec3(-10.0, -17.3, 10.5), Vec3(0.0, 30.0, 16.5),
             Vec3(-26.0, -15.0, 16.5), Vec3(26.0, -15.0, 16.5)],
            [Vec3(-40, -40, 1.6), Vec3(40, -40, 1.6)]),
    boss="darcy")

HOME_LEVELS["aisha"] = _home_pair(
    "aisha", "Andros", _build_andros, "pearl",
    {"calm": (Vec4(0.36, 0.66, 0.86, 1), Vec4(0.66, 0.84, 0.92, 1),
              Vec4(1.0, 0.98, 0.92, 1), Vec4(0.58, 0.64, 0.68, 1)),
     "dark": (Vec4(0.14, 0.18, 0.24, 1), Vec4(0.22, 0.28, 0.32, 1),
              Vec4(0.82, 0.88, 1.0, 1), Vec4(0.40, 0.44, 0.48, 1)),
     "sub_calm": "Andros. Nine tenths of it is water.",
     "sub_dark": "Something has poisoned the sea.",
     "mobs": _MOBS_WIDE},
    layout=(Vec3(0, -56, 2.0), Vec3(0, 0, 5.2),
            [Vec3(-44.0, 12.0, 13.0), Vec3(44.0, 12.0, 13.0),
             Vec3(-30.0, -38.0, 13.0), Vec3(30.0, -38.0, 13.0),
             Vec3(0.0, 48.0, 13.0), Vec3(0, 0, 6.0)],
            [Vec3(-36, 36, 2.4), Vec3(36, 36, 2.4)]),
    boss="icy")


# ---------------------------------------------------------------------------
# The campaign
# ---------------------------------------------------------------------------
# "home" and "siege" are filled in from the chosen fairy's realm; everything
# else is the shared Season 1 arc.
CAMPAIGN_TEMPLATE = ["home", "alfea", "swamp", "cloudtower", "roccaluce",
                     "redfountain", "pixievillage", "siege",
                     "siege_cloudtower", "battle_alfea"]

SHARED_LEVELS = {lv.key: lv for lv in (
    LEVEL_ALFEA, LEVEL_SWAMP, LEVEL_CLOUDTOWER, LEVEL_ROCCALUCE,
    LEVEL_REDFOUNTAIN, LEVEL_PIXIEVILLAGE, LEVEL_SIEGE_CLOUDTOWER,
    LEVEL_BATTLE_ALFEA)}

CAMPAIGN_LENGTH = len(CAMPAIGN_TEMPLATE)


def campaign_for(fairy_key: str) -> list:
    """The ten chapters this fairy plays, with her own realm in slots 1 and 8."""
    home, siege = HOME_LEVELS.get(fairy_key, HOME_LEVELS["bloom"])
    out = []
    for slot in CAMPAIGN_TEMPLATE:
        if slot == "home":
            out.append(home)
        elif slot == "siege":
            out.append(siege)
        else:
            out.append(SHARED_LEVELS[slot])
    return out
