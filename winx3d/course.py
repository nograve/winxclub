"""Linear stage construction.

Levels are laid out as a course: a path that runs from a start pad to a goal,
turning in ninety-degree corners, climbing stairs, crossing gaps and opening
out into arenas along the way.  That is the shape the era's action-adventure
stages used, and it reads far better than an open arena with props scattered
around it - there is always a way forward, and always a reason to look off to
the side.

Keeping every heading on a ninety-degree increment is what lets the collision
stay exact: each slab of floor is an axis-aligned box, the same primitive the
player, the enemies and the projectiles already test against.

Off the path there is no floor at all.  Falling is real, and the course drops
checkpoints as it goes so a fall costs a little health and a little progress
rather than the level.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from panda3d.core import Vec3, Vec4

from .geometry import shade

# Heading 0 points along +Y; the world stays axis-aligned.
DIRS = {0: (0.0, 1.0), 90: (1.0, 0.0), 180: (0.0, -1.0), 270: (-1.0, 0.0)}


@dataclass
class Theme:
    """The look of one realm: palette, trim, and what litters the floor."""
    floor_a: Vec4
    floor_b: Vec4
    wall: Vec4
    rail: Vec4
    accent: Vec4
    step: float = 4.5                # floor tile size
    jitter: float = 0.12
    relief: float = 0.0              # >0 gives natural, noise-shaded ground
    scatter: tuple = ()              # (kind, colors, per-100-sq-units)
    edging: str = "rail"             # rail | kerb | none
    pillar: object = None            # optional callable(mb, x, y, z, theme)
    backdrop: object = None          # optional callable(course) run once


@dataclass
class Anchors:
    """Everything the course wants the level to populate it with."""
    enemies: list = field(default_factory=list)     # (kind, Vec3)
    gems: list = field(default_factory=list)
    hearts: list = field(default_factory=list)
    puzzles: list = field(default_factory=list)     # (kind, Vec3, dict)
    checkpoints: list = field(default_factory=list)
    start: Vec3 = None
    goal: Vec3 = None
    length: float = 0.0


class Course:
    """A cursor that walks forward laying down floor, scenery and content."""

    def __init__(self, builder, theme: Theme, start=(0.0, -40.0, 0.0),
                 heading: int = 0, seed: int = 1) -> None:
        self.b = builder
        self.theme = theme
        self.pos = Vec3(*start)
        self.heading = heading % 360
        self.rng = random.Random(seed)
        self.a = Anchors()
        self.a.start = Vec3(self.pos) + Vec3(0, 0, 2.0)
        self._travelled = 0.0
        self.width = 14.0        # width of the stretch just laid
        self._safe_back = 0.0    # how far back from the cursor is solid

    # -- frame ---------------------------------------------------------
    def fwd(self) -> Vec3:
        d = DIRS[self.heading]
        return Vec3(d[0], d[1], 0.0)

    def right(self) -> Vec3:
        d = DIRS[(self.heading + 90) % 360]
        return Vec3(d[0], d[1], 0.0)

    def at(self, forward=0.0, side=0.0, up=0.0) -> Vec3:
        """A world point in the path's own frame."""
        return self.pos + self.fwd() * forward + self.right() * side \
            + Vec3(0, 0, up)

    def back_limit(self, d: float) -> float:
        """Clamp a backward offset to floor that actually exists.

        Content is placed relative to the cursor after a segment is laid.
        Straight after a gap or a drawbridge there is nothing behind the
        cursor but open sky, so an item asked for ten units back would hang
        in the void.
        """
        return max(0.0, min(d, self._safe_back))

    def side(self, s: float) -> float:
        """Clamp a side offset to the stretch just laid.

        Content is authored in path-relative terms, and a route can narrow
        without its content noticing; without this a chest asked for eight
        units out on a seven-wide bridge ends up in the void.
        """
        limit = max(0.0, self.width * 0.5 - 2.2)
        return max(-limit, min(limit, s))

    def _span(self, length, width):
        """Axis-aligned (size_x, size_y) for a slab of this run."""
        if self.heading in (0, 180):
            return (width, length)
        return (length, width)

    # -- floor ---------------------------------------------------------
    def slab(self, length, width, thickness=1.4, color=None, top=None,
             rise=0.0) -> None:
        """Lay floor forward from the cursor and move the cursor onto it."""
        t = self.theme
        sx, sy = self._span(length, width)
        centre = self.at(length * 0.5, 0.0, rise * 0.5 - thickness * 0.5)
        self.b.solid((centre.x, centre.y, centre.z),
                     (sx, sy, thickness + abs(rise)),
                     color or t.wall, top or t.floor_a)
        # Tiled top surface, drawn just above the slab.
        deck = self.at(length * 0.5, 0.0, rise + 0.01)
        self.b.mesh.grid_ground(sx, sy, t.floor_a, t.floor_b, step=t.step,
                                center=(deck.x, deck.y, deck.z),
                                jitter=t.jitter, relief=t.relief,
                                seed=int(abs(deck.x) + abs(deck.y)) % 997)
        self._scatter_deck(length, width, rise)
        self.pos = self.at(length, 0.0, rise)
        self._travelled += length
        self.a.length = self._travelled
        self._safe_back = length

    def _scatter_deck(self, length, width, rise=0.0) -> None:
        t = self.theme
        if not t.scatter:
            return
        area = length * width / 100.0
        for kind, colors, density in t.scatter:
            for _ in range(int(area * density)):
                f = self.rng.uniform(1.0, max(1.1, length - 1.0))
                s = self.rng.uniform(-width * 0.46, width * 0.46)
                p = self.at(f, s, rise + 0.02)
                self._clutter(kind, colors, p)

    def _clutter(self, kind, colors, p) -> None:
        mesh = self.b.decor()
        rng = self.rng
        col = colors[rng.randrange(len(colors))]
        if kind == "tuft":
            for _ in range(rng.randint(3, 5)):
                h = rng.uniform(0.35, 0.8)
                mesh.lathe((p.x + rng.uniform(-0.3, 0.3),
                            p.y + rng.uniform(-0.3, 0.3), p.z),
                           [(0.0, 0.055), (h * 0.6, 0.03), (h, 0.0)],
                           shade(col, rng.uniform(0.85, 1.15)), segments=4)
        elif kind == "pebble":
            mesh.sphere((p.x, p.y, p.z + 0.04), rng.uniform(0.12, 0.32),
                        shade(col, rng.uniform(0.8, 1.2)), segments=6,
                        rings=4, squash=0.45)
        elif kind == "flower":
            h = rng.uniform(0.3, 0.6)
            mesh.lathe((p.x, p.y, p.z), [(0.0, 0.035), (h, 0.025)],
                       Vec4(0.34, 0.58, 0.30, 1), segments=4)
            mesh.sphere((p.x, p.y, p.z + h + 0.06), rng.uniform(0.09, 0.16),
                        col, segments=6, rings=4, squash=0.6)
        elif kind == "crack":
            a = rng.uniform(0, math.tau)
            for k in range(rng.randint(2, 4)):
                mesh.box((p.x + math.cos(a) * k * 0.9,
                          p.y + math.sin(a) * k * 0.9, p.z + 0.02),
                         (rng.uniform(0.8, 1.7), 0.10, 0.04), col)
        else:                                    # drifting motes
            mesh.sphere((p.x, p.y, p.z + rng.uniform(0.4, 1.8)),
                        rng.uniform(0.05, 0.11), col, segments=5, rings=4)

    def _edge(self, length, width, rise=0.0) -> None:
        """Rails or a kerb down both sides of the run just laid."""
        t = self.theme
        if t.edging == "none":
            return
        back = self.pos - self.fwd() * length
        for side in (-1, 1):
            if t.edging == "kerb":
                sx, sy = self._span(length, 0.9)
                c = back + self.fwd() * (length * 0.5) \
                    + self.right() * (side * width * 0.5) + Vec3(0, 0, 0.22)
                self.b.solid((c.x, c.y, c.z), (sx, sy, 0.55),
                             shade(t.wall, 1.12))
                continue
            # Posts with a top rail between them.
            n = max(2, int(length / 5.0))
            for i in range(n + 1):
                p = back + self.fwd() * (length * i / n) \
                    + self.right() * (side * width * 0.5)
                self.b.mesh.lathe((p.x, p.y, p.z),
                                  [(0.0, 0.16), (1.25, 0.13)], t.rail,
                                  segments=6)
            sx, sy = self._span(length, 0.22)
            c = back + self.fwd() * (length * 0.5) \
                + self.right() * (side * width * 0.5) + Vec3(0, 0, 1.28)
            self.b.mesh.box((c.x, c.y, c.z), (sx, sy, 0.22),
                            shade(t.rail, 1.15))
            self.b.clip((c.x, c.y, c.z + 0.4), (sx, sy, 2.4))

    # -- segments ------------------------------------------------------
    def run(self, length, width=14.0, rails=True, rings=0) -> "Course":
        """A straight stretch of path."""
        self.width = width
        self.slab(length, width)
        if rails:
            self._edge(length, width)
        if rings:
            self.ring_line(rings, length)
        return self

    def bridge(self, length, width=7.0, rings=0) -> "Course":
        """A narrow span with a drop either side."""
        self.width = width
        self.slab(length, width, thickness=0.9)
        self._edge(length, width)
        if rings:
            self.ring_line(rings, length)
        return self

    def stairs(self, length, rise, count=6, width=12.0) -> "Course":
        """A flight climbing to a new height."""
        self.width = width
        step_len = length / count
        step_rise = rise / count
        for _ in range(count):
            self.slab(step_len, width, thickness=1.2, rise=step_rise)
        return self

    def gap(self, length, count=3, width=7.0, lift=0.0) -> "Course":
        """A void crossed on stepping platforms - the fall is real."""
        self.width = width
        span = length / (count + 1)
        for i in range(count):
            self.pos = self.at(span, 0.0, 0.0)
            side = 0.0 if count < 3 else (i - (count - 1) * 0.5) * width * 0.55
            top = self.at(0.0, side, lift)
            self.b.solid((top.x, top.y, top.z - 0.6), (width, width, 1.2),
                         self.theme.wall, self.theme.floor_a)
            self.b.decor().lathe((top.x, top.y, top.z - 1.2),
                                 [(-4.0, 0.3), (0.0, width * 0.30)],
                                 shade(self.theme.wall, 0.8), segments=7)
        # Land the gap on a pad, so the cursor is never left over open sky
        # and anything placed just after the jump has floor under it.
        self.pos = self.at(span, 0.0, lift)
        pad_w = width * 1.5
        self.b.solid((self.pos.x, self.pos.y, self.pos.z - 0.7),
                     (pad_w, pad_w, 1.4), self.theme.wall, self.theme.floor_a)
        self.width = pad_w
        self._safe_back = pad_w * 0.3
        return self

    def drawbridge(self, length, group, width=8.0) -> "Course":
        """A span that is not there yet.

        The cursor crosses the gap, but no floor is laid: a Bridge puzzle
        keyed to ``group`` fills it once whatever drives that group is done.
        Pair it with levers on the near side.
        """
        centre = self.at(length * 0.5, 0.0, 0.0)
        sx, sy = self._span(length, width)
        travel = (-self.fwd().x * length, -self.fwd().y * length, -8.0)
        self.a.puzzles.append(("bridge", Vec3(centre.x, centre.y,
                                              centre.z - 0.5),
                               {"group": group, "size": (sx, sy, 1.0),
                                "travel": travel}))
        self.pos = self.at(length, 0.0, 0.0)
        self._travelled += length
        self.width = width
        self._safe_back = 0.0
        return self

    def lever(self, group, side=0.0, back=8.0) -> "Course":
        self.a.puzzles.append(("lever",
                               self.at(-self.back_limit(back),
                                       self.side(side), 0.0),
                               {"group": group}))
        return self

    def cache(self, reward="score", side=14.0, back=10.0, up=0.0) -> "Course":
        """A hidden stash, set off the path where you have to look for it."""
        p = self.at(-self.back_limit(back), side, up)
        # A small ledge to stand it on, since it hangs off the main run.
        self.b.solid((p.x, p.y, p.z - 0.7), (8.0, 8.0, 1.4),
                     shade(self.theme.wall, 0.9), self.theme.floor_b)
        self.a.puzzles.append(("cache", Vec3(p), {"reward": reward}))
        return self

    def corner(self, turn, size=20.0) -> "Course":
        """A square landing, then a ninety-degree change of direction."""
        self.width = size
        half = size * 0.5
        self.pos = self.at(half, 0.0, 0.0)
        c = self.at(0.0, 0.0, -0.7)
        self.b.solid((c.x, c.y, c.z), (size, size, 1.4), self.theme.wall,
                     self.theme.floor_a)
        deck = self.at(0.0, 0.0, 0.01)
        self.b.mesh.grid_ground(size, size, self.theme.floor_a,
                                self.theme.floor_b, step=self.theme.step,
                                center=(deck.x, deck.y, deck.z),
                                jitter=self.theme.jitter,
                                relief=self.theme.relief, seed=41)
        self.heading = (self.heading + turn) % 360
        self.pos = self.at(half, 0.0, 0.0) - self.fwd() * size
        self.pos = self.at(half, 0.0, 0.0)
        self._safe_back = half
        return self

    def arena(self, size=40.0, walls=True) -> "Course":
        """A wide room - where the fights and the set pieces happen."""
        self.width = size
        half = size * 0.5
        self.pos = self.at(half, 0.0, 0.0)
        c = self.at(0.0, 0.0, -0.7)
        self.b.solid((c.x, c.y, c.z), (size, size, 1.4), self.theme.wall,
                     self.theme.floor_a)
        deck = self.at(0.0, 0.0, 0.01)
        self.b.mesh.grid_ground(size, size, self.theme.floor_a,
                                self.theme.floor_b, step=self.theme.step,
                                center=(deck.x, deck.y, deck.z),
                                jitter=self.theme.jitter,
                                relief=self.theme.relief, seed=53)
        if walls and self.theme.pillar:
            for i in range(8):
                a = math.tau * i / 8
                p = self.at(math.cos(a) * half * 0.86,
                            math.sin(a) * half * 0.86, 0.0)
                self.theme.pillar(self.b.mesh, p.x, p.y, p.z, self.theme)
        self.arena_half = half
        self.pos = self.at(half, 0.0, 0.0)
        self._safe_back = half
        return self

    # -- content -------------------------------------------------------
    def back(self, forward=0.0, side=0.0, up=0.0) -> Vec3:
        """A point measured back from the cursor, for filling the last run."""
        return self.at(-forward, side, up)

    def ring_line(self, count, length, side=0.0, up=1.5) -> "Course":
        """A line of collectibles along the stretch just laid."""
        for i in range(count):
            f = -length + length * (i + 0.5) / count
            self.a.gems.append(self.at(f, self.side(side), up))
        return self

    def ring_arc(self, count, radius=6.0, up=1.5) -> "Course":
        for i in range(count):
            a = math.pi * (i + 0.5) / count
            self.a.gems.append(self.at(-radius * math.cos(a) * 0.0,
                                       math.cos(a) * radius,
                                       up + math.sin(a) * 3.0))
        return self

    def heart(self, side=0.0, back=6.0) -> "Course":
        self.a.hearts.append(self.at(-self.back_limit(back),
                                     self.side(side), 1.5))
        return self

    def foe(self, kind, count=1, spread=9.0, back=10.0, up=1.0) -> "Course":
        for i in range(count):
            s = 0.0 if count == 1 else (i - (count - 1) * 0.5) * spread
            self.a.enemies.append(
                (kind, self.at(-self.back_limit(back), self.side(s), up)))
        return self

    def chest(self, reward="score", side=0.0, back=8.0, up=0.0) -> "Course":
        self.a.puzzles.append(("chest",
                               self.at(-self.back_limit(back),
                                       self.side(side), up),
                               {"reward": reward}))
        return self

    def spring(self, power=26.0, side=0.0, back=8.0) -> "Course":
        self.a.puzzles.append(("spring",
                               self.at(-self.back_limit(back),
                                       self.side(side), 0.0),
                               {"power": power}))
        return self

    def tablet(self, title, text, side=-8.0, back=8.0) -> "Course":
        self.a.puzzles.append(("tablet",
                               self.at(-self.back_limit(back),
                                       self.side(side), 0.0),
                               {"title": title, "text": text}))
        return self

    def puzzle(self, kind, side=0.0, back=8.0, up=0.0, **kw) -> "Course":
        self.a.puzzles.append(
            (kind, self.at(-self.back_limit(back), self.side(side), up), kw))
        return self

    def checkpoint(self, back=2.0) -> "Course":
        p = self.at(-self.back_limit(back), 0.0, 0.0)
        self.a.checkpoints.append(p)
        t = self.theme
        for side in (-1, 1):
            self.b.mesh.lathe((p.x + self.right().x * side * 7.0,
                               p.y + self.right().y * side * 7.0, p.z),
                              [(0.0, 0.34), (4.2, 0.26)], t.accent, segments=7)
            self.b.mesh.sphere((p.x + self.right().x * side * 7.0,
                                p.y + self.right().y * side * 7.0, p.z + 4.5),
                               0.55, shade(t.accent, 1.4), segments=8, rings=6)
        return self

    def prop(self, fn, forward=0.0, side=0.0, up=0.0) -> "Course":
        """Drop a landmark next to the path."""
        p = self.at(forward, side, up)
        fn(self.b, p.x, p.y, p.z, self.heading, self.theme)
        return self

    def finish(self, up=1.2) -> Anchors:
        """Goal pad at the end of the course."""
        t = self.theme
        self.slab(22.0, 22.0, thickness=1.6)
        c = self.back(11.0, 0.0, 0.0)
        for i, r in enumerate((10.0, 7.0, 4.5)):
            self.b.solid((c.x, c.y, 0.4 + i * 0.5 + c.z),
                         (r * 2, r * 2, 0.5), shade(t.accent, 0.9 + i * 0.08))
        self.a.goal = Vec3(c.x, c.y, c.z + 1.5 + up)
        self.a.checkpoints.append(Vec3(c.x, c.y, c.z + 1.5))
        return self.a
