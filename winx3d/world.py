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
    kind: str = "creeper"
    extra: dict = field(default_factory=dict)


@dataclass
class Level:
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
# Level 1 — Alfea Courtyard
# ---------------------------------------------------------------------------
def _build_alfea(b: WorldBuilder) -> None:
    rng = random.Random(11)
    grass_a = Vec4(0.42, 0.68, 0.36, 1)
    grass_b = Vec4(0.36, 0.61, 0.32, 1)
    stone = Vec4(0.86, 0.83, 0.76, 1)
    roof = Vec4(0.85, 0.42, 0.55, 1)

    b.mesh.grid_ground(200, 200, grass_a, grass_b, step=10.0)
    b.clip((0, 0, -2.0), (240, 240, 4.0))          # the floor itself
    b.bounds(92, 92)

    # Central plaza and fountain.
    b.mesh.grid_ground(56, 56, shade(stone, 0.98), shade(stone, 0.90),
                       step=7.0, center=(0, 0, 0.06))
    b.solid((0, 0, 0.5), (9, 9, 1.0), shade(stone, 1.02))
    b.solid((0, 0, 1.6), (5.5, 5.5, 1.4), shade(stone, 0.95))
    b.mesh.cylinder((0, 0, 2.3), 0.8, 0.5, 3.2, shade(stone, 1.05), segments=10)
    b.glass().sphere((0, 0, 6.0), 1.5, Vec4(0.45, 0.78, 1.0, 0.55),
                     segments=12, rings=8)

    # The school: a long hall flanked by towers.
    b.solid((0, 46, 9.0), (48, 16, 18.0), stone, shade(stone, 1.06))
    b.mesh.prism((0, 46, 20.0), (48, 16, 8.0), roof)
    for x in (-26, 26):
        b.tower(x, 46, 5.5, 26.0, shade(stone, 0.94), roof)
    b.arch(0, 37.5, 9.0, 9.0, shade(stone, 1.04))
    # Windows, drawn as recessed panels.
    for x in range(-20, 21, 8):
        for z in (6.0, 12.0):
            b.decor().box((x, 37.85, z), (3.0, 0.3, 4.0),
                          Vec4(0.35, 0.55, 0.85, 1))

    # Terraces — reachable only by flying, which is where the gems live.
    for (tx, ty, tz, tw) in ((-38, 8, 6.0, 14), (38, 8, 9.0, 14),
                             (0, -34, 12.0, 16), (-30, -26, 5.0, 10),
                             (30, -26, 5.0, 10)):
        b.solid((tx, ty, tz), (tw, tw, 1.4), shade(stone, 1.0),
                Vec4(0.62, 0.78, 0.95, 1))
        for sx in (-1, 1):
            for sy in (-1, 1):
                b.decor().cylinder((tx + sx * (tw / 2 - 1), ty + sy * (tw / 2 - 1),
                                    tz + 0.7), 0.4, 0.32, 2.4,
                                   shade(stone, 1.08), segments=8)

    # Stepping platforms so a grounded player can still climb.
    for i, (px, py) in enumerate(((-14, -14), (-22, -20), (-30, -24))):
        b.solid((px, py, 1.4 + i * 1.6), (5, 5, 1.0), shade(stone, 0.92))

    # Hedges and trees around the lawn.
    for _ in range(26):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(38, 82)
        b.tree(math.cos(a) * r, math.sin(a) * r, 0, rng.uniform(3.5, 5.5),
               Vec4(0.42, 0.30, 0.20, 1), Vec4(0.30, 0.60, 0.32, 1), rng)
    for x in range(-30, 31, 12):
        b.solid((x, 18, 0.9), (7, 1.6, 1.8), Vec4(0.28, 0.55, 0.30, 1))


LEVEL_ALFEA = Level(
    key="alfea", name="Alfea Courtyard",
    subtitle="Something has crawled in past the barrier.",
    sky=Vec4(0.53, 0.76, 0.96, 1), fog=Vec4(0.72, 0.85, 0.97, 1),
    sun=Vec4(1.0, 0.97, 0.88, 1), ambient=Vec4(0.55, 0.57, 0.66, 1),
    start=Vec3(0, -20, 2.0), portal=Vec3(0, 30, 1.2),
    build=_build_alfea,
    hint="Clear the courtyard, then step into the portal by the school.",
    gem_goal=6,
    enemies=[Spawn(Vec3(-20, 6, 2), "creeper"), Spawn(Vec3(22, 4, 2), "creeper"),
             Spawn(Vec3(-8, 24, 2), "creeper"), Spawn(Vec3(14, 26, 2), "creeper"),
             Spawn(Vec3(-34, -18, 2), "creeper"), Spawn(Vec3(34, -16, 2), "creeper"),
             Spawn(Vec3(0, -44, 2), "wisp"), Spawn(Vec3(-40, 30, 8), "wisp")],
    gems=[Vec3(-38, 8, 8.2), Vec3(38, 8, 11.2), Vec3(0, -34, 14.2),
          Vec3(-30, -26, 7.2), Vec3(30, -26, 7.2), Vec3(0, 0, 4.6),
          Vec3(-18, -8, 1.4), Vec3(18, -8, 1.4)],
    hearts=[Vec3(-46, 46, 1.4), Vec3(46, 46, 1.4)],
)


# ---------------------------------------------------------------------------
# Level 2 — Whispering Wood
# ---------------------------------------------------------------------------
def _build_wood(b: WorldBuilder) -> None:
    rng = random.Random(29)
    moss_a = Vec4(0.26, 0.44, 0.28, 1)
    moss_b = Vec4(0.21, 0.38, 0.25, 1)
    bark = Vec4(0.34, 0.24, 0.18, 1)
    leaf = Vec4(0.24, 0.52, 0.30, 1)
    rock = Vec4(0.48, 0.46, 0.50, 1)

    b.mesh.grid_ground(200, 200, moss_a, moss_b, step=10.0)
    b.clip((0, 0, -2.0), (240, 240, 4.0))
    b.bounds(88, 88)

    # A ruined stone circle in the clearing.
    for i in range(9):
        a = math.tau * i / 9
        x, y = math.cos(a) * 15.0, math.sin(a) * 15.0
        h = rng.uniform(4.0, 7.5)
        b.solid((x, y, h * 0.5), (2.0, 2.0, h), shade(rock, rng.uniform(0.85, 1.1)))
    b.mesh.grid_ground(26, 26, shade(rock, 1.05), shade(rock, 0.95), step=6.5,
                       center=(0, 0, 0.06))

    # Floating platforms climbing toward the far end of the wood.
    ladder = [(-24, -18, 5), (-32, -4, 9), (-22, 12, 13), (-4, 20, 17),
              (16, 26, 21), (34, 16, 25), (30, -6, 22), (12, -18, 16)]
    for i, (px, py, pz) in enumerate(ladder):
        w = 8.0 if i % 2 == 0 else 6.5
        b.solid((px, py, pz), (w, w, 1.2), shade(rock, 1.0),
                shade(leaf, 1.25))
        b.decor().cylinder((px, py, pz - 0.6), w * 0.28, 0.1, -3.0,
                           shade(bark, 0.9), segments=8)

    # Dense forest ring.
    for _ in range(70):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(30, 80)
        b.tree(math.cos(a) * r, math.sin(a) * r, 0, rng.uniform(4.0, 8.0),
               bark, shade(leaf, rng.uniform(0.8, 1.2)), rng)
    for _ in range(18):
        x, y = rng.uniform(-70, 70), rng.uniform(-70, 70)
        if abs(x) < 20 and abs(y) < 20:
            continue
        s = rng.uniform(1.6, 4.0)
        b.solid((x, y, s * 0.4), (s, s * 1.2, s * 0.8),
                shade(rock, rng.uniform(0.8, 1.1)))

    # Glowing pond — pure decoration, but it anchors the far corner.
    b.glass().grid_ground(30, 30, Vec4(0.30, 0.70, 0.85, 0.60),
                          Vec4(0.24, 0.60, 0.80, 0.60), step=7.5,
                          center=(-52, 52, 0.25))


LEVEL_WOOD = Level(
    key="wood", name="Whispering Wood",
    subtitle="Trolls in the ruins. Wisps in the canopy.",
    sky=Vec4(0.24, 0.34, 0.40, 1), fog=Vec4(0.30, 0.42, 0.42, 1),
    sun=Vec4(0.85, 0.92, 0.80, 1), ambient=Vec4(0.42, 0.48, 0.48, 1),
    start=Vec3(0, -34, 2.0), portal=Vec3(34, 16, 26.5),
    build=_build_wood,
    hint="The portal sits on the highest platform. You will have to fly.",
    gem_goal=6,
    enemies=[Spawn(Vec3(-12, 6, 2), "troll"), Spawn(Vec3(14, -4, 2), "troll"),
             Spawn(Vec3(0, 30, 2), "troll"),
             Spawn(Vec3(-24, -18, 8), "wisp"), Spawn(Vec3(-22, 12, 16), "wisp"),
             Spawn(Vec3(16, 26, 24), "wisp"), Spawn(Vec3(30, -6, 25), "wisp"),
             Spawn(Vec3(-40, -40, 3), "creeper"), Spawn(Vec3(40, -40, 3), "creeper"),
             Spawn(Vec3(40, 40, 3), "creeper")],
    gems=[Vec3(-24, -18, 7.0), Vec3(-32, -4, 11.0), Vec3(-22, 12, 15.0),
          Vec3(-4, 20, 19.0), Vec3(16, 26, 23.0), Vec3(30, -6, 24.0),
          Vec3(0, 0, 1.6), Vec3(-52, 52, 1.6)],
    hearts=[Vec3(-32, -4, 11.0), Vec3(12, -18, 18.0)],
)


# ---------------------------------------------------------------------------
# Level 3 — Cloud Tower (boss)
# ---------------------------------------------------------------------------
def _build_tower(b: WorldBuilder) -> None:
    rng = random.Random(47)
    slab_a = Vec4(0.30, 0.26, 0.40, 1)
    slab_b = Vec4(0.25, 0.21, 0.35, 1)
    obsidian = Vec4(0.19, 0.16, 0.28, 1)
    rune = Vec4(0.70, 0.35, 0.95, 1)

    # A circular arena floating in the storm.
    b.mesh.grid_ground(90, 90, slab_a, slab_b, step=9.0)
    b.clip((0, 0, -2.0), (100, 100, 4.0))
    b.bounds(45, 45, height=80)

    # Buttressed outer wall with rune lights.
    segs = 24
    for i in range(segs):
        a = math.tau * i / segs
        x, y = math.cos(a) * 44.0, math.sin(a) * 44.0
        h = 12.0 + (3.0 if i % 3 == 0 else 0.0)
        b.solid((x, y, h * 0.5), (6.0, 6.0, h), shade(obsidian, 0.9 + 0.2 * (i % 2)))
        if i % 3 == 0:
            b.decor().sphere((x * 0.86, y * 0.86, h + 1.2), 0.8, rune,
                             segments=8, rings=6)

    # Stepped dais at the centre where the boss waits.
    for i, r in enumerate((16.0, 12.0, 8.0)):
        b.solid((0, 0, 0.6 + i * 1.2), (r * 2, r * 2, 1.2),
                shade(slab_a, 1.0 + i * 0.06))
    b.decor().cylinder((0, 0, 4.2), 3.0, 2.2, 1.0, shade(rune, 0.6), segments=14)

    # Four floating pillars to break line of sight and reward flying.
    for i in range(4):
        a = math.tau * i / 4 + math.pi / 4
        x, y = math.cos(a) * 26.0, math.sin(a) * 26.0
        b.solid((x, y, 9.0), (7, 7, 1.4), shade(slab_a, 1.1), rune)
        b.decor().cylinder((x, y, 0), 1.4, 1.0, 8.3, obsidian, segments=9)

    # Storm clouds overhead — visual only, they sell the altitude.
    for _ in range(30):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(6, 46)
        b.glass().sphere((math.cos(a) * r, math.sin(a) * r,
                          rng.uniform(28, 40)), rng.uniform(4, 9),
                         Vec4(0.34, 0.30, 0.46, 0.45), segments=8, rings=5,
                         squash=0.45)


LEVEL_TOWER = Level(
    key="tower", name="Cloud Tower",
    subtitle="The witch is waiting. Do not fight her on the ground.",
    sky=Vec4(0.13, 0.10, 0.20, 1), fog=Vec4(0.20, 0.16, 0.30, 1),
    sun=Vec4(0.80, 0.72, 1.0, 1), ambient=Vec4(0.40, 0.36, 0.52, 1),
    start=Vec3(0, -36, 2.0), portal=Vec3(0, 0, 5.4),
    build=_build_tower,
    hint="Defeat the witch. The portal home opens on the dais.",
    gem_goal=0,
    enemies=[Spawn(Vec3(0, 12, 8), "witch"),
             Spawn(Vec3(-26, 26, 11), "wisp"), Spawn(Vec3(26, 26, 11), "wisp"),
             Spawn(Vec3(-26, -26, 11), "wisp"), Spawn(Vec3(26, -26, 11), "wisp"),
             Spawn(Vec3(-16, 0, 3), "troll"), Spawn(Vec3(16, 0, 3), "troll")],
    gems=[Vec3(-26, 26, 11.5), Vec3(26, 26, 11.5), Vec3(-26, -26, 11.5),
          Vec3(26, -26, 11.5)],
    hearts=[Vec3(0, -30, 1.6), Vec3(0, 30, 1.6)],
)


LEVELS = [LEVEL_ALFEA, LEVEL_WOOD, LEVEL_TOWER]
