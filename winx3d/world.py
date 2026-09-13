"""Level geometry, collision and level definitions.

Static level art is merged into a handful of Geoms and every solid gets a
matching ``CollisionBox``.  Boxes are the cheapest solid Panda3D offers and
they answer both of the queries the player needs: sphere-vs-solid pushback for
walls, and ray-vs-solid for finding the floor.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from panda3d.core import (BitMask32, CollisionBox, CollisionNode, NodePath,
                          Point3, TransparencyAttrib, Vec3, Vec4)

from .course import Course, Theme
from .geometry import MeshBuilder, shade

# Collision masks.  Solids are "into" only; the player and projectiles are the
# "from" objects that test against them.
MASK_SOLID = BitMask32.bit(1)
MASK_ENEMY = BitMask32.bit(2)
MASK_PICKUP = BitMask32.bit(3)


@dataclass
class PuzzleSpec:
    """Declarative placement of one interactive object.

    ``group`` ties a puzzle's parts together: runes that open the same gate,
    pedestals in one sequence, a lever and the bridge it extends.
    """
    kind: str
    pos: Vec3
    group: str = ""
    order: int = 0                     # position in a sequence puzzle
    size: tuple = None
    travel: tuple = None               # how far a bridge is stowed
    color: Vec4 = None
    title: str = ""                    # tablet heading
    text: str = ""                     # tablet body
    reward: str = "score"              # what a cache or chest gives up
    power: float = 0.0                 # spring launch speed


@dataclass
class Objective:
    """One line of the level's to-do list, shown in the HUD."""
    key: str
    text: str
    kind: str = "flag"                 # flag | clear | collect | secrets
    target: str = ""                   # flag name, for kind="flag"
    count: int = 0
    required: bool = True


def obj_clear(text="Clear out the enemies") -> Objective:
    return Objective("clear", text, "clear")


def obj_collect(n, text) -> Objective:
    return Objective("collect", text, "collect", count=n)


def obj_flag(key, text) -> Objective:
    return Objective(key, text, "flag", target=key)


def obj_secrets(text="Find the hidden caches") -> Objective:
    return Objective("secrets", text, "secrets", required=False)


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
    puzzles: list = field(default_factory=list)
    objectives: list = field(default_factory=list)
    checkpoints: list = field(default_factory=list)
    fall_z: float = -25.0
    course_length: float = 0.0


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
def _scatter(b: WorldBuilder, rng, count, inner, outer, kind, colors,
             z=0.0, avoid=None) -> None:
    """Surface clutter - tufts, pebbles, flowers, sparks.

    Visual only and never collidable: it exists to stop the ground reading
    as one flat plane.
    """
    mesh = b.decor()
    for _ in range(count):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(inner, outer)
        x, y = math.cos(a) * r, math.sin(a) * r
        if avoid and avoid(x, y):
            continue
        col = colors[rng.randrange(len(colors))]
        if kind == "tuft":
            for _b in range(rng.randint(3, 5)):
                hh = rng.uniform(0.35, 0.85)
                mesh.lathe((x + rng.uniform(-0.3, 0.3),
                            y + rng.uniform(-0.3, 0.3), z),
                           [(0.0, 0.055), (hh * 0.6, 0.03), (hh, 0.0)],
                           shade(col, rng.uniform(0.85, 1.15)), segments=4)
        elif kind == "pebble":
            mesh.sphere((x, y, z + 0.04), rng.uniform(0.12, 0.34),
                        shade(col, rng.uniform(0.8, 1.2)), segments=6,
                        rings=4, squash=0.45)
        elif kind == "flower":
            hh = rng.uniform(0.3, 0.6)
            mesh.lathe((x, y, z), [(0.0, 0.035), (hh, 0.025)],
                       Vec4(0.34, 0.58, 0.30, 1), segments=4)
            mesh.sphere((x, y, z + hh + 0.06), rng.uniform(0.09, 0.16), col,
                        segments=6, rings=4, squash=0.6)
        elif kind == "crack":
            ang = rng.uniform(0, math.tau)
            for k in range(rng.randint(2, 4)):
                mesh.box((x + math.cos(ang) * k * 0.9,
                          y + math.sin(ang) * k * 0.9, z + 0.02),
                         (rng.uniform(0.8, 1.8), 0.10, 0.04), col)
        else:                                   # "spark" - tiny glowing motes
            mesh.sphere((x, y, z + rng.uniform(0.3, 1.6)),
                        rng.uniform(0.05, 0.11), col, segments=5, rings=4)


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
# Themes - the look of each realm's course
# ---------------------------------------------------------------------------
GRASS_TUFT = [Vec4(0.34, 0.62, 0.30, 1), Vec4(0.42, 0.70, 0.34, 1),
              Vec4(0.30, 0.55, 0.28, 1)]
PETALS = [Vec4(0.98, 0.72, 0.82, 1), Vec4(0.98, 0.92, 0.60, 1),
          Vec4(0.92, 0.60, 0.80, 1)]


def _pillar_stone(mb, x, y, z, t) -> None:
    mb.lathe((x, y, z), [(0.0, 1.0), (0.5, 0.85), (7.0, 0.80), (7.6, 1.05)],
             t.wall, segments=9)


def _pillar_gothic(mb, x, y, z, t) -> None:
    mb.lathe((x, y, z), [(0.0, 1.2), (0.6, 0.95), (9.0, 0.80)],
             shade(t.wall, 0.9), segments=8)
    mb.lathe((x, y, z + 9.0), [(0.0, 1.1), (2.6, 0.0)], shade(t.wall, 0.75),
             segments=8)
    mb.sphere((x, y, z + 11.8), 0.45, t.accent, segments=7, rings=5)


def _pillar_tree(mb, x, y, z, t) -> None:
    mb.lathe((x, y, z), [(0.0, 0.7), (6.0, 0.45)], Vec4(0.42, 0.30, 0.20, 1),
             segments=8)
    for k in range(3):
        mb.lathe((x, y, z + 5.0 + k * 1.7), [(0.0, 3.0 - k * 0.7), (2.2, 0.0)],
                 shade(t.floor_a, 0.85 + 0.12 * k), segments=9)


def _pillar_coral(mb, x, y, z, t) -> None:
    mb.lathe((x, y, z), [(0.0, 1.3), (4.0, 0.9), (7.5, 0.4)],
             t.accent, segments=8)
    for k in range(3):
        a = k * 2.1
        mb.lathe((x + math.cos(a) * 0.8, y + math.sin(a) * 0.8, z + 3.0 + k),
                 [(0.0, 0.5), (2.2, 0.0)], shade(t.accent, 1.15), segments=6)


def _pillar_server(mb, x, y, z, t) -> None:
    mb.box((x, y, z + 5.0), (3.4, 3.4, 10.0), t.wall, shade(t.wall, 1.2))
    for k in range(4):
        mb.box((x, y - 1.8, z + 1.6 + k * 2.2), (2.2, 0.2, 0.6), t.accent)


def _pillar_lamp(mb, x, y, z, t) -> None:
    mb.lathe((x, y, z), [(0.0, 0.28), (4.4, 0.18)], Vec4(0.24, 0.24, 0.28, 1),
             segments=7)
    mb.sphere((x, y, z + 4.8), 0.5, t.accent, segments=8, rings=6)


def _pillar_drum(mb, x, y, z, t) -> None:
    mb.lathe((x, y, z), [(0.0, 1.9), (3.4, 1.9)], t.wall, segments=11,
             shade_fn=lambda s: shade(t.wall, 1.0 + s * 0.1))
    mb.lathe((x, y, z + 3.4), [(0.0, 1.95), (0.2, 1.9)],
             Vec4(0.94, 0.90, 0.82, 1), segments=11)
    for k in range(8):
        a = math.tau * k / 8
        mb.sphere((x + math.cos(a) * 1.9, y + math.sin(a) * 1.9, z + 1.7),
                  0.22, t.accent, segments=6, rings=4)


def _pillar_ice(mb, x, y, z, t) -> None:
    mb.lathe((x, y, z), [(0.0, 1.4), (3.0, 1.0), (8.0, 0.0)],
             Vec4(0.70, 0.86, 0.96, 1), segments=7)


THEMES = {
    "gardenia": Theme(
        Vec4(0.46, 0.70, 0.36, 1), Vec4(0.40, 0.64, 0.33, 1),
        wall=Vec4(0.74, 0.68, 0.56, 1), rail=Vec4(0.52, 0.36, 0.24, 1),
        accent=Vec4(1.0, 0.92, 0.62, 1), step=4.0, jitter=0.14, relief=0.08,
        scatter=(("tuft", GRASS_TUFT, 3.0), ("flower", PETALS, 1.0)),
        pillar=_pillar_lamp),
    "alfea": Theme(
        Vec4(0.88, 0.85, 0.78, 1), Vec4(0.82, 0.79, 0.72, 1),
        wall=Vec4(0.80, 0.77, 0.70, 1), rail=Vec4(0.90, 0.62, 0.72, 1),
        accent=Vec4(0.62, 0.82, 1.0, 1), step=3.5, jitter=0.07,
        scatter=(("pebble", [Vec4(0.78, 0.75, 0.68, 1)], 0.5),),
        pillar=_pillar_stone),
    "swamp": Theme(
        Vec4(0.32, 0.34, 0.22, 1), Vec4(0.26, 0.29, 0.19, 1),
        wall=Vec4(0.34, 0.26, 0.18, 1), rail=Vec4(0.28, 0.22, 0.16, 1),
        accent=Vec4(0.60, 0.95, 0.55, 1), step=4.5, jitter=0.18, relief=0.12,
        scatter=(("tuft", [Vec4(0.34, 0.40, 0.22, 1),
                           Vec4(0.28, 0.34, 0.20, 1)], 3.5),
                 ("mote", [Vec4(0.60, 0.95, 0.55, 0.85)], 1.2)),
        pillar=_pillar_tree),
    "cloudtower": Theme(
        Vec4(0.32, 0.28, 0.42, 1), Vec4(0.26, 0.22, 0.36, 1),
        wall=Vec4(0.21, 0.18, 0.30, 1), rail=Vec4(0.44, 0.34, 0.60, 1),
        accent=Vec4(0.72, 0.38, 0.96, 1), step=4.0, jitter=0.10,
        scatter=(("crack", [Vec4(0.14, 0.12, 0.20, 1)], 1.2),
                 ("mote", [Vec4(0.72, 0.38, 0.96, 0.9)], 1.0)),
        pillar=_pillar_gothic),
    "roccaluce": Theme(
        Vec4(0.82, 0.87, 0.93, 1), Vec4(0.74, 0.80, 0.89, 1),
        wall=Vec4(0.62, 0.70, 0.80, 1), rail=Vec4(0.70, 0.86, 0.96, 1),
        accent=Vec4(0.95, 0.92, 0.72, 1), step=4.5, jitter=0.09, relief=0.10,
        scatter=(("pebble", [Vec4(0.90, 0.93, 0.97, 1)], 1.6),
                 ("mote", [Vec4(0.85, 0.95, 1.0, 0.9)], 1.4)),
        pillar=_pillar_ice),
    "redfountain": Theme(
        Vec4(0.58, 0.50, 0.38, 1), Vec4(0.51, 0.44, 0.34, 1),
        wall=Vec4(0.70, 0.34, 0.29, 1), rail=Vec4(0.92, 0.78, 0.38, 1),
        accent=Vec4(0.95, 0.82, 0.42, 1), step=4.0, jitter=0.14, relief=0.06,
        scatter=(("pebble", [Vec4(0.58, 0.52, 0.42, 1)], 1.8),),
        pillar=_pillar_stone),
    "pixievillage": Theme(
        Vec4(0.46, 0.76, 0.42, 1), Vec4(0.40, 0.70, 0.38, 1),
        wall=Vec4(0.56, 0.42, 0.28, 1), rail=Vec4(0.92, 0.55, 0.62, 1),
        accent=Vec4(0.98, 0.78, 0.35, 1), step=3.5, jitter=0.15, relief=0.07,
        scatter=(("tuft", GRASS_TUFT, 4.0), ("flower", PETALS, 2.5)),
        pillar=_pillar_tree),
    "solaria": Theme(
        Vec4(0.94, 0.90, 0.80, 1), Vec4(0.88, 0.83, 0.72, 1),
        wall=Vec4(0.92, 0.88, 0.80, 1), rail=Vec4(0.96, 0.78, 0.32, 1),
        accent=Vec4(1.0, 0.86, 0.36, 1), step=4.0, jitter=0.08,
        scatter=(("pebble", [Vec4(0.90, 0.82, 0.62, 1)], 0.8),),
        pillar=_pillar_stone),
    "lynphea": Theme(
        Vec4(0.34, 0.62, 0.32, 1), Vec4(0.28, 0.55, 0.29, 1),
        wall=Vec4(0.44, 0.32, 0.22, 1), rail=Vec4(0.36, 0.58, 0.32, 1),
        accent=Vec4(0.98, 0.55, 0.72, 1), step=4.0, jitter=0.16, relief=0.10,
        scatter=(("tuft", GRASS_TUFT, 4.5), ("flower", PETALS, 2.0)),
        pillar=_pillar_tree),
    "melody": Theme(
        Vec4(0.80, 0.68, 0.64, 1), Vec4(0.73, 0.61, 0.58, 1),
        wall=Vec4(0.78, 0.26, 0.30, 1), rail=Vec4(0.92, 0.76, 0.36, 1),
        accent=Vec4(0.92, 0.76, 0.36, 1), step=4.0, jitter=0.11, relief=0.05,
        scatter=(("pebble", [Vec4(0.70, 0.58, 0.54, 1)], 1.0),),
        pillar=_pillar_drum),
    "zenith": Theme(
        Vec4(0.16, 0.24, 0.28, 1), Vec4(0.12, 0.19, 0.24, 1),
        wall=Vec4(0.40, 0.46, 0.54, 1), rail=Vec4(0.25, 0.90, 0.85, 1),
        accent=Vec4(0.25, 0.90, 0.85, 1), step=3.0, jitter=0.16,
        scatter=(("mote", [Vec4(0.25, 0.90, 0.85, 0.9)], 1.6),),
        pillar=_pillar_server),
    "andros": Theme(
        Vec4(0.72, 0.78, 0.80, 1), Vec4(0.64, 0.72, 0.76, 1),
        wall=Vec4(0.60, 0.68, 0.72, 1), rail=Vec4(0.45, 0.82, 0.92, 1),
        accent=Vec4(0.95, 0.52, 0.58, 1), step=4.0, jitter=0.10,
        scatter=(("pebble", [Vec4(0.80, 0.84, 0.86, 1)], 1.2),
                 ("mote", [Vec4(0.55, 0.90, 1.0, 0.8)], 1.0)),
        pillar=_pillar_coral),
}


def _darken(theme: Theme, tint=Vec4(0.62, 0.58, 0.52, 1)) -> Theme:
    """A besieged version of a theme: drained, with the trim gone sour."""
    def d(c, k=0.62):
        return Vec4(c[0] * k * tint[0] * 1.6, c[1] * k * tint[1] * 1.6,
                    c[2] * k * tint[2] * 1.6, c[3])
    return Theme(d(theme.floor_a), d(theme.floor_b), wall=d(theme.wall),
                 rail=d(theme.rail), accent=Vec4(0.72, 0.82, 0.34, 1),
                 step=theme.step, jitter=theme.jitter + 0.04,
                 relief=theme.relief,
                 scatter=(("crack", [Vec4(0.16, 0.14, 0.12, 1)], 1.6),
                          ("pebble", [Vec4(0.34, 0.32, 0.26, 1)], 1.2)),
                 pillar=theme.pillar)


# ---------------------------------------------------------------------------
# Landmarks placed beside the path
# ---------------------------------------------------------------------------
def _lm_school(b, x, y, z, h, t) -> None:
    """Alfea's facade, seen from the courtyard."""
    stone = Vec4(0.86, 0.83, 0.76, 1)
    roof = Vec4(0.85, 0.42, 0.55, 1)
    b.solid((x, y, z + 9.0), (48, 16, 18.0), stone, shade(stone, 1.06))
    b.mesh.prism((x, y, z + 20.0), (48, 16, 8.0), roof)
    for sx in (-26, 26):
        b.tower(x + sx, y, 5.5, 26.0, shade(stone, 0.94), roof)
    for wx in range(-20, 21, 8):
        for wz in (6.0, 12.0):
            b.decor().box((x + wx, y - 8.15, z + wz), (3.0, 0.3, 4.0),
                          Vec4(0.35, 0.55, 0.85, 1))


def _lm_fountain(b, x, y, z, h, t) -> None:
    stone = shade(t.wall, 1.05)
    b.solid((x, y, z + 0.5), (9, 9, 1.0), stone)
    b.solid((x, y, z + 1.6), (5.5, 5.5, 1.4), shade(stone, 0.95))
    b.mesh.lathe((x, y, z + 2.3), [(0.0, 0.8), (3.2, 0.5)], stone,
                 segments=10)
    b.glass().sphere((x, y, z + 6.0), 1.5, Vec4(0.45, 0.78, 1.0, 0.55),
                     segments=12, rings=8)


def _lm_hut(b, x, y, z, h, t) -> None:
    """Knut's hut, up on stilts."""
    hut = Vec4(0.38, 0.28, 0.20, 1)
    for sx in (-3.4, 3.4):
        for sy in (-3.4, 3.4):
            b.mesh.lathe((x + sx, y + sy, z), [(0.0, 0.4), (3.0, 0.34)],
                         Vec4(0.26, 0.21, 0.16, 1), segments=6)
    b.solid((x, y, z + 3.2), (10, 10, 0.5), hut, shade(hut, 1.12))
    b.solid((x, y + 4.6, z + 5.4), (10, 0.6, 4.0), hut)
    for sx in (-4.6, 4.6):
        b.solid((x + sx, y, z + 5.4), (0.6, 10, 4.0), hut)
    b.mesh.prism((x, y, z + 8.2), (11, 11, 3.0), Vec4(0.30, 0.26, 0.18, 1))
    b.decor().sphere((x, y, z + 6.4), 0.7, Vec4(0.95, 0.62, 0.25, 1),
                     segments=8, rings=6)


def _lm_shrine(b, x, y, z, h, t) -> None:
    """Daphne's shrine at the heart of the lake."""
    rock = shade(t.wall, 1.0)
    for i, r in enumerate((11.0, 8.0, 5.5)):
        b.solid((x, y, z + 0.5 + i * 1.1), (r * 2, r * 2, 1.1),
                shade(rock, 1.0 + i * 0.05))
    for i in range(8):
        a = math.tau * i / 8
        px, py = x + math.cos(a) * 7.0, y + math.sin(a) * 7.0
        b.mesh.lathe((px, py, z + 3.8), [(0.0, 0.42), (6.0, 0.34)],
                     shade(rock, 1.1), segments=7)
        b.boxes.append((Vec3(px, py, z + 6.8), Vec3(0.5, 0.5, 3.0)))
        b.decor().sphere((px, py, z + 10.2), 0.5, Vec4(0.95, 0.92, 0.72, 1),
                         segments=7, rings=5)
    b.glass().sphere((x, y, z + 7.0), 3.0, Vec4(0.95, 0.90, 0.70, 0.32),
                     segments=12, rings=8)


def _lm_greattree(b, x, y, z, h, t) -> None:
    b.mesh.lathe((x, y, z), [(0.0, 4.6), (12.0, 3.2)],
                 Vec4(0.46, 0.34, 0.24, 1), segments=14)
    b.boxes.append((Vec3(x, y, z + 6.0), Vec3(4.2, 4.2, 6.0)))
    for k in range(4):
        b.mesh.lathe((x, y, z + 11.0 + k * 2.6),
                     [(0.0, 11.0 - k * 2.2), (4.2 + k * 0.4, 0.0)],
                     shade(Vec4(0.36, 0.68, 0.36, 1), 0.86 + 0.10 * k),
                     segments=13)


def _lm_toadstool(b, x, y, z, h, t) -> None:
    caps = [Vec4(0.95, 0.42, 0.48, 1), Vec4(0.98, 0.72, 0.30, 1),
            Vec4(0.60, 0.55, 0.95, 1), Vec4(0.45, 0.85, 0.90, 1)]
    cap = caps[int(abs(x + y)) % len(caps)]
    hh = 2.6 + (int(abs(x * 3 + y)) % 4) * 0.8
    b.mesh.lathe((x, y, z), [(0.0, 1.15), (hh, 0.95)],
                 Vec4(0.92, 0.90, 0.80, 1), segments=9)
    b.mesh.lathe((x, y, z + hh), [(0.0, 2.9), (2.4, 0.0)], cap, segments=11)
    b.mesh.box((x, y - 0.98, z + 0.7), (0.9, 0.3, 1.4),
               Vec4(0.42, 0.30, 0.22, 1))
    b.boxes.append((Vec3(x, y, z + hh * 0.5), Vec3(1.2, 1.2, hh * 0.5)))


def _lm_sunpalace(b, x, y, z, h, t) -> None:
    marble, gold = t.wall, t.accent
    for i, (wd, ht) in enumerate(((46, 4.0), (36, 4.0), (26, 4.0))):
        b.solid((x, y, z + 2.0 + i * 4.0), (wd, 26 - i * 5, ht), marble,
                shade(marble, 1.06))
    b.solid((x, y, z + 15.0), (18, 16, 8.0), shade(marble, 1.04), gold)
    b.mesh.lathe((x, y, z + 19.0), [(0.0, 7.0), (9.0, 0.0)], gold,
                 segments=14)
    b.decor().sphere((x, y, z + 31.0), 3.4, Vec4(1.0, 0.92, 0.45, 1),
                     segments=14, rings=10)


def _lm_harp(b, x, y, z, h, t) -> None:
    b.solid((x + 11, y, z + 14.0), (3.2, 3.2, 28.0), t.wall)
    b.solid((x - 11, y, z + 9.0), (3.2, 3.2, 18.0), t.wall)
    b.solid((x, y, z + 27.0), (25, 3.0, 3.0), t.accent)
    for k in range(10):
        b.decor().lathe((x - 9.5 + k * 2.0, y, z + 1.0),
                        [(0.0, 0.10), (24.0 - k * 1.6, 0.08)],
                        Vec4(0.95, 0.92, 0.80, 1), segments=4)


def _lm_core(b, x, y, z, h, t) -> None:
    for i, r in enumerate((14.0, 11.0, 8.0)):
        b.mesh.lathe((x, y, z + i * 2.0), [(0.0, r), (2.0, r * 0.92)],
                     t.wall, segments=6)
        b.boxes.append((Vec3(x, y, z + i * 2.0 + 1.0), Vec3(r, r, 1.0)))
    b.decor().lathe((x, y, z + 6.0), [(0.0, 5.0), (14.0, 3.0)],
                    Vec4(t.accent[0], t.accent[1], t.accent[2], 1),
                    segments=6)
    b.glass().lathe((x, y, z + 6.0), [(0.0, 7.0), (16.0, 5.0)],
                    Vec4(t.accent[0], t.accent[1], t.accent[2], 0.28),
                    segments=10, cap_top=False, cap_bottom=False)


def _lm_dome(b, x, y, z, h, t) -> None:
    b.mesh.lathe((x, y, z), [(0.0, 3.2), (4.5, 3.0)], t.wall, segments=10)
    b.mesh.sphere((x, y, z + 5.0), 3.3, Vec4(0.40, 0.72, 0.85, 1),
                  segments=11, rings=7, squash=0.72)
    b.boxes.append((Vec3(x, y, z + 2.5), Vec3(3.2, 3.2, 2.5)))


def _lm_spire(b, x, y, z, h, t) -> None:
    _spire(b, x, y, 3.4, 22.0, shade(t.wall, 0.9), t.accent)


def _lm_house(b, x, y, z, h, t) -> None:
    i = int(abs(x + y * 3)) % 2
    _house(b, x, y, 14, 12, 8.0 + i * 2.0,
           (Vec4(0.86, 0.82, 0.74, 1), Vec4(0.80, 0.76, 0.82, 1))[i],
           (Vec4(0.60, 0.30, 0.26, 1), Vec4(0.42, 0.36, 0.40, 1))[i])


def _lm_bandstand(b, x, y, z, h, t) -> None:
    b.solid((x, y, z + 0.45), (16, 16, 0.9), shade(t.wall, 1.06))
    for i in range(8):
        a = math.tau * i / 8
        px, py = x + math.cos(a) * 5.6, y + math.sin(a) * 5.6
        b.mesh.lathe((px, py, z + 1.0), [(0.0, 0.26), (3.6, 0.22)],
                     Vec4(0.90, 0.88, 0.82, 1), segments=7)
        b.boxes.append((Vec3(px, py, z + 2.8), Vec3(0.3, 0.3, 1.8)))
    b.mesh.lathe((x, y, z + 4.6), [(0.0, 7.2), (2.6, 0.0)],
                 Vec4(0.35, 0.52, 0.60, 1), segments=10)


# ---------------------------------------------------------------------------
# Routes - each chapter laid out as a stage from start pad to goal
# ---------------------------------------------------------------------------
def route_gardenia(c: Course):
    """Through the park: the lawn, the bandstand, the pond path, the ogre."""
    c.run(30, 16, rings=5).tablet(
        "A Note on the Fridge",
        "  'Bloom - gone to the shop, back by six. There is a casserole. Do "
        "NOT let Kiko into the greenhouse again. Love, Mum.'\n\n"
        "Sixteen years of a life that was never quite the whole story.")
    c.prop(_lm_house, 24, -30).prop(_lm_house, 24, 30)
    c.checkpoint()
    c.run(34, 16, rings=6).foe("ghoul", 2).chest("gems", side=6)
    c.corner(90, 22).prop(_lm_bandstand, 0, 0)
    c.run(28, 14, rings=5).foe("ghoul", 2).puzzle("rune", side=-6,
                                                  group="realmlights")
    c.checkpoint()
    c.gap(30, 3, 8).foe("wisp", 2, back=16).heart(side=0, back=14)
    c.cache("health", side=-15, back=10)
    c.run(26, 16, rings=6).puzzle("rune", side=6, group="realmlights")
    c.corner(-90, 22).spring(24.0)
    c.stairs(22, 8, 6, 14).chest("health", side=-7)
    c.run(24, 14, rings=4).puzzle("rune", side=0, group="realmlights")
    c.checkpoint()
    c.arena(46).foe("knut", 1, back=22).foe("ghoul", 3, back=16, spread=12)
    c.chest("life", side=-16, back=30)
    return c.finish()


def route_alfea(c: Course):
    """Griselda's field exercise, run as a circuit of the courtyard."""
    c.run(28, 18, rings=5).tablet(
        "The Barrier Stones",
        "Four stones carry Alfea's barrier. When the school is threatened "
        "they go dark, and only a fairy's magic will wake them. Strike each "
        "one - the barrier will do the rest.")
    c.checkpoint()
    c.run(30, 18, rings=6).foe("ghoul", 2).puzzle("rune", side=-7,
                                                  group="barrier")
    c.corner(90, 24).prop(_lm_fountain, 0, 0)
    c.run(30, 16, rings=5).foe("ghoul", 2).puzzle("rune", side=7,
                                                  group="barrier")
    c.chest("gems", side=-7)
    c.checkpoint()
    c.stairs(20, 7, 5, 14).foe("wisp", 2, back=10, up=6)
    c.cache("magic", side=15, back=8)
    c.run(26, 16, rings=5).puzzle("rune", side=0, group="barrier")
    c.corner(90, 24).spring(25.0)
    c.gap(26, 2, 9).heart(back=12)
    c.run(28, 16, rings=6).foe("ghoul", 2).puzzle("rune", side=6,
                                                  group="barrier")
    c.chest("health", side=8)
    c.checkpoint()
    c.arena(48).prop(_lm_school, 30, 0).foe("ghoul", 3, back=20, spread=13)
    c.foe("wisp", 2, back=14, spread=16, up=7)
    return c.finish()


def route_swamp(c: Course):
    """Out over the bog on duckboards to Knut's hut."""
    c.run(26, 13, rings=4).tablet(
        "Knut's Tally",
        "Scratched into a post at the edge of the bog: a count of "
        "deliveries, and three marks that are not a count at all. Someone "
        "was paying him, and paying him well.")
    c.checkpoint()
    c.bridge(30, 8, rings=6).foe("ghoul", 2)
    c.gap(28, 3, 7).chest("magic", side=0, back=14)
    c.bridge(26, 7, rings=5).foe("wisp", 2)
    c.lever("span", side=-6).lever("span", side=6)
    c.drawbridge(26, "span", 8.0)
    c.corner(-90, 20)
    c.checkpoint()
    c.run(28, 14, rings=5).foe("troll", 1).puzzle("rune", side=-7,
                                                  group="marshlights")
    c.gap(30, 3, 7, lift=2.0).heart(back=16)
    c.cache("score", side=-16, back=12)
    c.run(24, 13, rings=4).puzzle("rune", side=7, group="marshlights")
    c.corner(90, 20).spring(27.0)
    c.bridge(28, 8, rings=5).foe("ghoul", 3).chest("gems", side=-6)
    c.checkpoint()
    c.run(22, 14, rings=4).puzzle("rune", side=0, group="marshlights")
    c.arena(44).prop(_lm_hut, 6, 0).foe("knut", 1, back=20)
    c.foe("troll", 2, back=14, spread=18).chest("life", side=16, back=30)
    return c.finish()


def route_cloudtower(c: Course):
    """Up through a school whose corridors do not stay put."""
    c.run(26, 14, rings=5).tablet(
        "A Page of the Book of Fate",
        "The lock on the inner hall answers to a verse, not a key:\n\n"
        "  'First dusk, and then the storm;\n"
        "   after the storm, silence;\n"
        "   and only then, the dawn.'\n\n"
        "Sound the four chimes in that order. Sound them wrongly and the "
        "hall will forget you were ever here.")
    c.checkpoint()
    c.stairs(26, 10, 7, 13).foe("ghoul", 2)
    c.corner(90, 20).prop(_lm_spire, 0, 16)
    c.bridge(30, 7, rings=6).foe("wisp", 2).chest("magic", side=0, back=15)
    c.checkpoint()
    c.run(24, 14, rings=4).puzzle("pedestal", side=-7, group="verse", order=0,
                                  color=Vec4(0.85, 0.45, 0.35, 1))
    c.gap(26, 2, 8).puzzle("pedestal", side=0, group="verse", order=1,
                           color=Vec4(0.60, 0.55, 0.95, 1), back=13)
    c.stairs(22, 9, 6, 13).foe("ghoul", 2)
    c.cache("magic", side=-15, back=8)
    c.run(24, 14, rings=5).puzzle("pedestal", side=7, group="verse", order=2,
                                  color=Vec4(0.45, 0.45, 0.55, 1))
    c.corner(-90, 20).spring(26.0)
    c.checkpoint()
    c.run(26, 14, rings=5).puzzle("pedestal", side=0, group="verse", order=3,
                                  color=Vec4(1.0, 0.88, 0.50, 1))
    c.chest("health", side=-8).heart(side=8)
    c.puzzle("gate", side=0, back=2, group="verse", size=(14.0, 2.0, 11.0))
    c.arena(44).prop(_lm_spire, 18, -16).prop(_lm_spire, 18, 16)
    c.foe("darcy", 1, back=20, up=9).foe("ghoul", 3, back=14, spread=13)
    return c.finish()


def route_roccaluce(c: Course):
    """Across the frozen lake to the shrine, then out onto thin ice."""
    c.run(28, 16, rings=5).tablet(
        "Daphne's Marker",
        "Set at the lake's edge, in a hand that has not written anything "
        "for sixteen years:\n\n"
        "  'Four lights stood over Domino the night it fell. Wake them and "
        "I will hear you, wherever I am now.'")
    c.checkpoint()
    c.run(30, 15, rings=6).foe("ghoul", 2).puzzle("rune", side=-7,
                                                  group="lights")
    c.gap(30, 3, 8).chest("gems", side=0, back=15)
    c.corner(90, 22)
    c.bridge(28, 8, rings=5).foe("wisp", 2).puzzle("rune", side=6,
                                                   group="lights")
    c.checkpoint()
    c.stairs(20, 7, 5, 14).heart(side=-6)
    c.cache("health", side=15, back=8)
    c.run(26, 15, rings=5).puzzle("rune", side=7, group="lights")
    c.corner(-90, 22).spring(25.0)
    c.gap(28, 3, 7, lift=3.0).chest("magic", side=0, back=14)
    c.run(24, 15, rings=4).foe("troll", 1).puzzle("rune", side=0,
                                                  group="lights")
    c.checkpoint()
    c.arena(46).prop(_lm_shrine, 4, 0).foe("icy", 1, back=22, up=10)
    c.foe("ghoul", 3, back=14, spread=13).chest("life", side=-17, back=30)
    return c.finish()


def route_redfountain(c: Course):
    """Up the rails and into the arena while the school is under attack."""
    c.run(26, 16, rings=5).tablet(
        "Vault Protocol",
        "Posted beside the arena, in Codatorta's handwriting:\n\n"
        "  'The vault does not open to magic - that is the point of it. Two "
        "counterweights onto the two floor plates, and it opens to anyone "
        "strong enough to push them.'")
    c.checkpoint()
    c.run(30, 16, rings=6).foe("ghoul", 3, spread=11)
    c.corner(90, 22).spring(24.0)
    c.stairs(24, 9, 6, 14).chest("magic", side=-8)
    c.bridge(30, 8, rings=6).foe("wisp", 2)
    c.cache("score", side=-15, back=12)
    c.checkpoint()
    # The run is widened here and the counterweights sit well inboard:
    # a block flush against a rail has nowhere to be pushed.
    c.run(30, 24, rings=5).foe("troll", 1)
    c.puzzle("plate", side=-5, group="vault").puzzle("plate", side=5,
                                                     group="vault")
    c.puzzle("block", side=-5, back=24, size=(4.0, 4.0, 4.0))
    c.puzzle("block", side=5, back=24, size=(4.0, 4.0, 4.0))
    c.puzzle("gate", side=0, back=1, group="vault", size=(15.0, 2.0, 10.0),
             color=Vec4(0.66, 0.40, 0.34, 1))
    c.corner(-90, 22).heart(side=0)
    c.run(26, 16, rings=5).foe("ghoul", 2).chest("health", side=8)
    c.checkpoint()
    c.arena(48).foe("stormy", 1, back=22, up=10)
    c.foe("troll", 2, back=15, spread=18).chest("life", side=17, back=30)
    return c.finish()


def route_pixievillage(c: Course):
    """Through the toadstools and up the roots of the great tree."""
    c.run(26, 15, rings=5).tablet(
        "The Pixies' Rhyme",
        "Painted around the base of the great tree, small enough that you "
        "have to kneel:\n\n"
        "  'Green wakes, then blue,\n"
        "   gold after, red too,\n"
        "   and violet last of all -\n"
        "   then the roots let you through.'")
    for s in (-11, 11):
        c.prop(_lm_toadstool, -14, s)
    c.checkpoint()
    c.run(28, 15, rings=6).foe("ghoul", 2)
    c.puzzle("pedestal", side=-7, group="rhyme", order=0,
             color=Vec4(0.45, 0.92, 0.45, 1))
    c.prop(_lm_toadstool, -8, 13)
    c.corner(90, 22)
    c.run(26, 14, rings=5).puzzle("pedestal", side=7, group="rhyme", order=1,
                                  color=Vec4(0.40, 0.70, 1.00, 1))
    c.chest("gems", side=-7)
    c.gap(26, 2, 8).heart(back=13)
    c.cache("magic", side=16, back=10)
    c.checkpoint()
    c.stairs(24, 10, 6, 14).foe("wisp", 2, up=6)
    c.run(24, 14, rings=4).puzzle("pedestal", side=0, group="rhyme", order=2,
                                  color=Vec4(1.00, 0.85, 0.35, 1))
    c.corner(-90, 22).spring(27.0)
    c.run(26, 14, rings=5).puzzle("pedestal", side=-7, group="rhyme", order=3,
                                  color=Vec4(0.95, 0.35, 0.40, 1))
    c.chest("health", side=8)
    c.checkpoint()
    c.run(22, 14, rings=4).puzzle("pedestal", side=7, group="rhyme", order=4,
                                  color=Vec4(0.72, 0.45, 0.95, 1))
    c.arena(46).prop(_lm_greattree, 4, 0).foe("darcy", 1, back=22, up=10)
    c.foe("ghoul", 3, back=14, spread=13).chest("life", side=-16, back=30)
    return c.finish()


# --- Home realms: one route shape per realm, reused for its siege ----------
def _home_route(c: Course, landmark, lore_title, lore_text, boss,
                mob="ghoul", besieged=False):
    """A realm's stage: out from the gate, around, and back to the landmark.

    Calm and besieged runs share the layout so the return visit is
    recognisably the same place; only the theme, the enemies and the
    objectives differ.
    """
    c.run(28, 16, rings=5).tablet(lore_title, lore_text)
    c.checkpoint()
    c.run(30, 16, rings=6).foe(mob, 2)
    if not besieged:
        c.puzzle("rune", side=-7, group="realmlights")
    c.chest("gems", side=7)
    c.corner(90, 22).prop(landmark, 2, 20)
    c.run(28, 15, rings=5).foe(mob, 2)
    if not besieged:
        c.puzzle("rune", side=7, group="realmlights")
    c.checkpoint()
    c.gap(28, 3, 8).heart(back=14)
    c.cache("health" if not besieged else "magic", side=-15, back=12)
    c.stairs(22, 8, 6, 14).chest("magic", side=-8)
    c.run(26, 15, rings=5).foe("wisp", 2)
    if not besieged:
        c.puzzle("rune", side=0, group="realmlights")
    c.corner(-90, 22).spring(26.0)
    c.run(28, 15, rings=6).foe(mob, 2).chest("health", side=8)
    c.checkpoint()
    c.arena(46).prop(landmark, 4, 0)
    c.foe(boss, 1, back=22, up=0 if boss == "knut" else 10)
    c.foe(mob, 3, back=14, spread=13).chest("life", side=-16, back=30)
    return c.finish()


# ---------------------------------------------------------------------------
# Level assembly
# ---------------------------------------------------------------------------
def course_level(key, name, subtitle, theme, route, sky, fog, sun, ambient,
                 gem_name="crystal", objectives=(), gem_goal=0,
                 seed=7) -> Level:
    """Run a route once to collect its content, and keep it as a Level.

    The route is deterministic, so rebuilding the geometry at load time
    reproduces exactly the layout these anchors were taken from.
    """
    probe = WorldBuilder()
    anchors = route(Course(probe, theme, seed=seed))

    lv = Level(
        key=key, name=name, subtitle=subtitle,
        sky=sky, fog=fog, sun=sun, ambient=ambient,
        start=Vec3(anchors.start), portal=Vec3(anchors.goal),
        build=(lambda b, _r=route, _t=theme, _s=seed:
               _r(Course(b, _t, seed=_s))),
        gem_name=gem_name, gem_goal=gem_goal,
        enemies=[Spawn(Vec3(p), kind) for kind, p in anchors.enemies],
        gems=[Vec3(p) for p in anchors.gems],
        hearts=[Vec3(p) for p in anchors.hearts],
        checkpoints=[Vec3(p) for p in anchors.checkpoints],
        course_length=anchors.length,
        objectives=list(objectives),
    )
    lv.puzzles = [PuzzleSpec(kind=kind, pos=Vec3(p), **kw)
                  for kind, p, kw in anchors.puzzles]
    return lv


def _obj_pack(flag_key, flag_text, clear_text, gem_goal, gem_text):
    out = []
    if flag_key:
        out.append(obj_flag(flag_key, flag_text))
    out.append(obj_clear(clear_text))
    if gem_goal:
        out.append(obj_collect(gem_goal, gem_text))
    out.append(Objective("chests", "Open the chests along the way", "chests",
                         required=False))
    return out


SKIES = {
    "gardenia": (Vec4(0.56, 0.78, 0.95, 1), Vec4(0.76, 0.87, 0.97, 1),
                 Vec4(1.0, 0.98, 0.92, 1), Vec4(0.58, 0.60, 0.66, 1)),
    "alfea": (Vec4(0.53, 0.76, 0.96, 1), Vec4(0.72, 0.85, 0.97, 1),
              Vec4(1.0, 0.97, 0.88, 1), Vec4(0.55, 0.57, 0.66, 1)),
    "swamp": (Vec4(0.30, 0.34, 0.28, 1), Vec4(0.34, 0.38, 0.30, 1),
              Vec4(0.86, 0.90, 0.76, 1), Vec4(0.42, 0.46, 0.40, 1)),
    "cloudtower": (Vec4(0.15, 0.11, 0.22, 1), Vec4(0.22, 0.17, 0.32, 1),
                   Vec4(0.80, 0.72, 1.0, 1), Vec4(0.40, 0.36, 0.52, 1)),
    "roccaluce": (Vec4(0.62, 0.72, 0.86, 1), Vec4(0.80, 0.87, 0.95, 1),
                  Vec4(0.92, 0.95, 1.0, 1), Vec4(0.60, 0.64, 0.74, 1)),
    "redfountain": (Vec4(0.42, 0.34, 0.44, 1), Vec4(0.56, 0.44, 0.46, 1),
                    Vec4(1.0, 0.86, 0.70, 1), Vec4(0.52, 0.46, 0.50, 1)),
    "pixievillage": (Vec4(0.60, 0.82, 0.92, 1), Vec4(0.78, 0.90, 0.90, 1),
                     Vec4(1.0, 0.98, 0.86, 1), Vec4(0.60, 0.62, 0.62, 1)),
    "solaria": (Vec4(0.42, 0.68, 0.95, 1), Vec4(0.86, 0.90, 0.98, 1),
                Vec4(1.0, 0.98, 0.88, 1), Vec4(0.66, 0.66, 0.68, 1)),
    "lynphea": (Vec4(0.52, 0.76, 0.86, 1), Vec4(0.74, 0.88, 0.84, 1),
                Vec4(1.0, 0.98, 0.86, 1), Vec4(0.58, 0.62, 0.58, 1)),
    "melody": (Vec4(0.86, 0.60, 0.58, 1), Vec4(0.92, 0.78, 0.72, 1),
               Vec4(1.0, 0.92, 0.82, 1), Vec4(0.62, 0.56, 0.56, 1)),
    "zenith": (Vec4(0.10, 0.16, 0.22, 1), Vec4(0.16, 0.26, 0.32, 1),
               Vec4(0.80, 0.94, 1.0, 1), Vec4(0.44, 0.52, 0.56, 1)),
    "andros": (Vec4(0.36, 0.66, 0.86, 1), Vec4(0.66, 0.84, 0.92, 1),
               Vec4(1.0, 0.98, 0.92, 1), Vec4(0.58, 0.64, 0.68, 1)),
}
DARK_SKY = (Vec4(0.20, 0.14, 0.18, 1), Vec4(0.32, 0.22, 0.24, 1),
            Vec4(1.0, 0.70, 0.58, 1), Vec4(0.44, 0.36, 0.40, 1))


# --- The eight shared chapters --------------------------------------------
LEVEL_ALFEA = course_level(
    "alfea", "Alfea College", "Magix. Your first field exercise.",
    THEMES["alfea"], route_alfea, *SKIES["alfea"],
    gem_name="magic crystal", gem_goal=14, seed=11,
    objectives=_obj_pack("barrier", "Wake the four barrier stones",
                         "Drive the ghouls out of the courtyard",
                         14, "Gather the loose magic crystals"))

LEVEL_SWAMP = course_level(
    "swamp", "Black Mud Swamp", "Knut's hideout. And its landlords.",
    THEMES["swamp"], route_swamp, *SKIES["swamp"],
    gem_name="swamp crystal", gem_goal=12, seed=13,
    objectives=_obj_pack("marshlights", "Light the marsh lights",
                         "Clear Knut's hideout",
                         12, "Gather the swamp crystals"))

LEVEL_CLOUDTOWER = course_level(
    "cloudtower", "Cloud Tower", "The corridors move. The Book of Fate does not.",
    THEMES["cloudtower"], route_cloudtower, *SKIES["cloudtower"],
    gem_name="page", gem_goal=12, seed=17,
    objectives=_obj_pack("verse", "Sound the four chimes in the verse's order",
                         "Deal with what the noise brings",
                         12, "Recover the loose pages"))

LEVEL_ROCCALUCE = course_level(
    "roccaluce", "Lake Roccaluce", "Daphne is waiting. So is Icy.",
    THEMES["roccaluce"], route_roccaluce, *SKIES["roccaluce"],
    gem_name="frozen tear", gem_goal=13, seed=19,
    objectives=_obj_pack("lights", "Wake the four lights above the lake",
                         "Hold the ice against Icy",
                         13, "Gather the frozen tears"))

LEVEL_REDFOUNTAIN = course_level(
    "redfountain", "Red Fountain",
    "School of Heroics and Bravery. Under attack.",
    THEMES["redfountain"], route_redfountain, *SKIES["redfountain"],
    gem_name="codex shard", gem_goal=12, seed=23,
    objectives=_obj_pack("vault", "Push both counterweights onto the plates",
                         "Hold Red Fountain",
                         12, "Secure the loose Codex shards"))

LEVEL_PIXIEVILLAGE = course_level(
    "pixievillage", "Pixie Village", "The last piece of the Codex.",
    THEMES["pixievillage"], route_pixievillage, *SKIES["pixievillage"],
    gem_name="pixie", gem_goal=14, seed=29,
    objectives=_obj_pack("rhyme", "Wake the chimes in the rhyme's order",
                         "Get the pixies clear",
                         14, "Carry the pixies to safety"))

LEVEL_SIEGE_CLOUDTOWER = course_level(
    "siege_cloudtower", "Cloud Tower Has Fallen",
    "The Army of Decay holds the school.",
    _darken(THEMES["cloudtower"]),
    lambda c: _home_route(c, _lm_spire, "Griffin's Order",
                          "Nailed to the dormitory door, in a hurry:\n\n"
                          "  'Every witch to her room and the door held "
                          "shut. Whatever is in the corridors is not a "
                          "student and it is not alive. - G.'",
                          "icy", mob="decay", besieged=True),
    *DARK_SKY, gem_name="page", seed=31,
    objectives=_obj_pack(None, None, "Cut through the Army of Decay", 0, None))

LEVEL_BATTLE_ALFEA = course_level(
    "battle_alfea", "The Battle of Alfea",
    "All three of them. Every student in the courtyard.",
    _darken(THEMES["alfea"]),
    lambda c: _home_route(c, _lm_school, "Faragonda's Last Order",
                          "Chalked on the courtyard flags, in a hand that "
                          "did not have time to be neat:\n\n"
                          "  'Every student to the courtyard. Nobody fights "
                          "alone today.'",
                          "icy", mob="decay", besieged=True),
    *DARK_SKY, gem_name="crystal", seed=37,
    objectives=_obj_pack(None, None, "Hold the courtyard, then finish the Trix",
                         0, None))

# The finale fields all three sisters.
LEVEL_BATTLE_ALFEA.enemies += [Spawn(LEVEL_BATTLE_ALFEA.portal +
                                     Vec3(-16, -26, 10), "darcy"),
                               Spawn(LEVEL_BATTLE_ALFEA.portal +
                                     Vec3(16, -26, 10), "stormy")]


# --- The six home realms, calm and besieged -------------------------------
_HOME_SPEC = {
    #          theme key      landmark        boss     mob       gem name
    "bloom":  ("gardenia",    _lm_bandstand,  "knut",  "ghoul", "spark"),
    "stella": ("solaria",     _lm_sunpalace,  "knut",  "ghoul", "sunstone"),
    "flora":  ("lynphea",     _lm_greattree,  "knut",  "ghoul", "seed"),
    "musa":   ("melody",      _lm_harp,       "knut",  "ghoul", "note"),
    "tecna":  ("zenith",      _lm_core,       "knut",  "ghoul", "data node"),
    "aisha":  ("andros",      _lm_dome,       "knut",  "ghoul", "pearl"),
}
_HOME_LORE = {
    "bloom": ("A Note on the Fridge",
              "  'Bloom - gone to the shop, back by six. There is a "
              "casserole. Do NOT let Kiko into the greenhouse again. Love, "
              "Mum.'\n\nSixteen years of a life that was never quite the "
              "whole story."),
    "stella": ("The Ring's Inventory",
               "Carved above the treasury door:\n\n  'The Ring of Solaria "
               "answers to the blood of Solaria and to nothing else. Whoever "
               "takes it will find they have stolen a very heavy piece of "
               "jewellery and nothing more.'"),
    "flora": ("The Grove's Own Record",
              "Grown into the bark, letter by letter, over centuries:\n\n"
              "  'What is planted here is not owned here. Take a seed, leave "
              "a seed. Anyone who takes without leaving will be shown the "
              "way out by the roots themselves.'"),
    "musa": ("The Valley's First Score",
             "Cut into the stage where the valley's first piece was "
             "played:\n\n  'Melody is not the sound. Melody is the silence "
             "you put it into. Guard both.'"),
    "tecna": ("Realm Log, Entry 44,912",
              "  'Anomaly logged: an unregistered mass crossed the perimeter "
              "at 03:14 and was not detected by any of nine independent "
              "systems. Probability of simultaneous failure: 1 in 4.1 "
              "billion. Conclusion: this was not a failure.'"),
    "aisha": ("The Tide Tables",
              "Set into the causeway, worn almost smooth:\n\n  'Andros keeps "
              "no walls. The sea is the wall. When the sea stops answering, "
              "that is when you should be afraid.'"),
}
_SIEGE_BOSS = {"bloom": "stormy", "stella": "stormy", "flora": "darcy",
               "musa": "icy", "tecna": "darcy", "aisha": "icy"}

HOME_LEVELS = {}
for _i, (_key, (_tk, _lm, _boss, _mob, _gem)) in enumerate(_HOME_SPEC.items()):
    _title, _text = _HOME_LORE[_key]
    _realm_name = {"gardenia": "Gardenia Park", "solaria": "Solaria",
                   "lynphea": "Lynphea", "melody": "Melody",
                   "zenith": "Zenith", "andros": "Andros"}[_tk]
    _calm_route = (route_gardenia if _key == "bloom" else
                   (lambda c, _l=_lm, _t=_title, _x=_text, _b=_boss, _m=_mob:
                    _home_route(c, _l, _t, _x, _b, _m)))
    _calm = course_level(
        "home_" + _key, _realm_name,
        {"bloom": "Earth. No magic here. Usually."}.get(
            _key, "Home, and something has followed you to it."),
        THEMES[_tk], _calm_route, *SKIES[_tk],
        gem_name=_gem, gem_goal=12, seed=101 + _i * 7,
        objectives=_obj_pack("realmlights", "Wake the realm lights",
                             "Drive them off your own doorstep",
                             12, "Gather what was scattered"))
    _siege = course_level(
        "siege_" + _key, _realm_name, "They followed you home.",
        _darken(THEMES[_tk]),
        (lambda c, _l=_lm, _t=_title, _x=_text, _b=_SIEGE_BOSS[_key]:
         _home_route(c, _l, _t, _x, _b, "decay", besieged=True)),
        *DARK_SKY, gem_name=_gem, seed=211 + _i * 7,
        objectives=_obj_pack(None, None, "Break the siege", 0, None))
    HOME_LEVELS[_key] = (_calm, _siege)


# ---------------------------------------------------------------------------
# The campaign
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Placement snapping
# ---------------------------------------------------------------------------
# Collectibles and puzzle objects are authored at roughly the right spot and
# then snapped onto the geometry that is actually there.  Hand-written Z
# values drift the moment a builder changes, and an object floating out of
# reach - or buried inside a pillar - is invisible in the level data.
def _top_at(boxes, x, y, ceiling, default=0.0):
    """Highest surface at (x, y) at or below ``ceiling``; ``default`` if none.

    "Found nothing" is tracked separately from the value, so a surface that
    happens to sit below the default still wins over it.
    """
    best_z = None
    for c, h in boxes:
        if abs(x - c.x) <= h.x and abs(y - c.y) <= h.y:
            top = c.z + h.z
            if top <= ceiling and (best_z is None or top > best_z):
                best_z = top
    return default if best_z is None else best_z


def _surface_under(boxes, x, y, want_z, search=9.0):
    """Find the surface an object at (x, y, want_z) should rest on.

    Prefers a nearby raised platform whose top is close to the intended
    height, snapping the object onto it; falls back to the ground.
    Returns (x, y, z).
    """
    best = None
    best_score = 1e9
    for c, h in boxes:
        top = c.z + h.z
        if top < 0.5 or abs(top - want_z) > 3.5:
            continue
        # Posts, lamps and tree trunks are not platforms - nothing should end
        # up balanced on one.
        if h.x < 1.8 or h.y < 1.8:
            continue
        px = max(c.x - h.x + 0.9, min(c.x + h.x - 0.9, x))
        py = max(c.y - h.y + 0.9, min(c.y + h.y - 0.9, y))
        d = math.hypot(px - x, py - y)
        if d > search:
            continue
        score = d + abs(top - want_z) * 0.5
        if score < best_score:
            best, best_score = (px, py), score
    if best is not None:
        px, py = best
        # Take the exposed surface there, not the box we happened to match:
        # on stacked terraces the nearest box is often the step below.
        return (px, py, _top_at(boxes, px, py, want_z + 3.5, want_z))
    # Nothing underneath at all: leave it where the course put it.
    return (x, y, _top_at(boxes, x, y, want_z + 1.5, want_z))


def _nudge_clear(boxes, x, y, z, radius=1.1):
    """Slide a point out of any solid it landed inside.

    Snapping to a surface can still drop something into a lamp post or a
    tree trunk standing on that surface; this pushes it out along whichever
    axis needs the least movement.
    """
    for _ in range(4):
        moved = False
        for c, h in boxes:
            if not (c.z - h.z < z + 0.6 and z < c.z + h.z):
                continue
            dx, dy = x - c.x, y - c.y
            ox = h.x + radius - abs(dx)
            oy = h.y + radius - abs(dy)
            if ox <= 0.0 or oy <= 0.0:
                continue
            if ox < oy:
                x = c.x + math.copysign(h.x + radius, dx or 1.0)
            else:
                y = c.y + math.copysign(h.y + radius, dy or 1.0)
            moved = True
        if not moved:
            break
    return x, y


def _snap_level(level: Level) -> None:
    wb = WorldBuilder()
    level.build(wb)
    boxes = wb.boxes

    def snap(v, lift=0.0):
        x, y, z = _surface_under(boxes, v.x, v.y, v.z)
        # Alternate nudging clear of obstructions with re-settling onto
        # whatever is under the new spot, until both agree.
        for _ in range(4):
            nx, ny = _nudge_clear(boxes, x, y, z + lift)
            if abs(nx - x) < 1e-6 and abs(ny - y) < 1e-6:
                break
            x, y = nx, ny
            z = _top_at(boxes, x, y, z + 2.0, z)
        return Vec3(x, y, z + lift)

    # Pickups hover a little above their surface so they read as collectible.
    level.gems = [snap(g, 1.4) for g in level.gems]
    level.hearts = [snap(h, 1.4) for h in level.hearts]
    for spec in level.puzzles:
        if spec.kind == "bridge":
            continue                      # placed deliberately, stows below
        spec.pos = snap(spec.pos)
    # Enemies stand on the ground; the AI settles them, but starting them
    # inside a wall looks broken for the first frame.
    for sp in level.enemies:
        if sp.kind in ("wisp", "icy", "darcy", "stormy"):
            continue                      # these fly
        sp.pos = snap(sp.pos, 0.2)


for _lv in list(SHARED_LEVELS.values()):
    _snap_level(_lv)
for _calm, _siege in HOME_LEVELS.values():
    _snap_level(_calm)
    _snap_level(_siege)
