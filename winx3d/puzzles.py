"""Interactive objects: puzzles, readable inscriptions and hidden caches.

Everything here is an :class:`Interactable` — something the player can walk up
to and use with the interact key, or in some cases shoot.  Levels declare them
as data (see :class:`winx3d.world.PuzzleSpec`) and the game instantiates them
alongside the enemies.

Puzzle objects that block progress do it by owning an entry in the level's
list of collision boxes.  That list is the single source of truth the player,
the enemies and the projectiles all test against, so a gate that removes its
box is genuinely open for everything at once.
"""
from __future__ import annotations

import math

from panda3d.core import NodePath, TransparencyAttrib, Vec3, Vec4

from .geometry import MeshBuilder, seg as _seg_fn, shade

_SEG = _seg_fn(12)

RUNE_DIM = Vec4(0.30, 0.30, 0.38, 1)


class PuzzleState:
    """Flags and counters shared by every puzzle in the current level."""

    def __init__(self) -> None:
        self.flags: set[str] = set()
        self.counters: dict[str, int] = {}
        self.secrets_found = 0
        self.secrets_total = 0
        self.chests_opened = 0
        self.chests_total = 0
        self.tablets_read = 0
        self.tablets_total = 0

    def set(self, name: str) -> None:
        self.flags.add(name)

    def has(self, name: str) -> bool:
        return name in self.flags

    def count(self, name: str) -> int:
        return self.counters.get(name, 0)


class Interactable:
    """Base class. Subclasses build a model and define what using it does."""

    prompt = "Use"
    use_radius = 4.0
    shootable = False          # can a player's magic bolt trigger it?
    one_shot = True            # can it only be used once?
    blocks = False             # does it own a collision box?

    def __init__(self, parent: NodePath, spec, game) -> None:
        self.spec = spec
        self.group = spec.group
        self.pos = Vec3(spec.pos)
        self.solved = False
        self.enabled = True
        self.t = 0.0
        self.root = NodePath(self.__class__.__name__.lower())
        self.root.reparentTo(parent)
        self.root.setPos(self.pos)
        self.build(game)

    # -- overridables -------------------------------------------------------
    def build(self, game) -> None:
        raise NotImplementedError

    def can_use(self, game) -> bool:
        return self.enabled and not (self.one_shot and self.solved)

    def use(self, game) -> None:
        self.solved = True

    def on_shot(self, game) -> None:
        self.use(game)

    def update(self, dt: float, game) -> None:
        self.t += dt

    def center(self) -> Vec3:
        return self.root.getPos() + Vec3(0, 0, 1.0)

    def prompt_text(self, game) -> str:
        return self.prompt

    def destroy(self) -> None:
        self.root.removeNode()


# ---------------------------------------------------------------------------
# Inscriptions - the exploration and hint layer
# ---------------------------------------------------------------------------
class Tablet(Interactable):
    """A readable stone. Carries lore, and usually the hint for a puzzle."""

    prompt = "Read the inscription"
    use_radius = 4.5

    def build(self, game) -> None:
        stone = Vec4(0.62, 0.60, 0.58, 1)
        mb = MeshBuilder()
        mb.box((0, 0, 0.15), (2.2, 1.4, 0.3), shade(stone, 0.8))
        mb.box((0, 0.25, 1.5), (1.9, 0.45, 2.6), stone, shade(stone, 1.1))
        # A carved panel, tilted toward the reader.
        mb.box((0, -0.02, 1.6), (1.4, 0.16, 2.0), shade(stone, 0.62))
        for i in range(4):
            mb.box((0, -0.12, 2.3 - i * 0.42), (1.0, 0.06, 0.09),
                   Vec4(0.80, 0.78, 0.62, 1))
        mb.build("tablet").reparentTo(self.root)
        glow = MeshBuilder()
        glow.sphere((0, -0.35, 1.6), 0.85, Vec4(1.0, 0.92, 0.55, 0.22),
                    segments=9, rings=6)
        g = glow.build("tablet_glow")
        g.setTransparency(TransparencyAttrib.MAlpha)
        g.setDepthWrite(False)
        g.setLightOff()
        g.reparentTo(self.root)
        self.glow = g
        game.puzzle.tablets_total += 1

    def use(self, game) -> None:
        if not self.solved:
            self.solved = True
            game.puzzle.tablets_read += 1
            self.glow.setColorScale(0.35, 0.35, 0.35, 1)
        game.show_reading(self.spec.title, self.spec.text)

    def can_use(self, game) -> bool:
        return True                      # always re-readable

    def prompt_text(self, game) -> str:
        return "Read the inscription" if not self.solved else "Read it again"

    def update(self, dt, game) -> None:
        self.t += dt
        if not self.solved:
            self.glow.setScale(1.0 + math.sin(self.t * 2.2) * 0.12)


# ---------------------------------------------------------------------------
# Runes - lit by a magic bolt, opening whatever their group controls
# ---------------------------------------------------------------------------
class Rune(Interactable):
    """A rune stone. Shoot it, or touch it, to light it."""

    prompt = "Light the rune"
    shootable = True
    use_radius = 3.5

    def build(self, game) -> None:
        color = self.spec.color or Vec4(0.55, 0.85, 1.0, 1)
        self.lit_color = color
        mb = MeshBuilder()
        mb.cylinder((0, 0, 0), 1.1, 0.9, 0.5, Vec4(0.34, 0.32, 0.40, 1),
                    segments=8)
        mb.cylinder((0, 0, 0.5), 0.55, 0.42, 3.0, Vec4(0.42, 0.40, 0.50, 1),
                    segments=7)
        mb.build("rune_post").reparentTo(self.root)
        disc = MeshBuilder()
        disc.sphere((0, 0, 0), 0.85, RUNE_DIM, segments=10, rings=7,
                    squash=0.35)
        d = disc.build("rune_disc")
        d.setZ(3.6)
        d.setP(90)
        d.setLightOff()
        d.reparentTo(self.root)
        self.disc = d

    def use(self, game) -> None:
        if self.solved:
            return
        self.solved = True
        self.disc.setColorScale(self.lit_color)
        game.effects.burst(self.center() + Vec3(0, 0, 2.6), self.lit_color,
                           14, 6.0, 0.35, gravity=-3.0)
        game.audio.play("gem")
        game.on_puzzle_progress(self.group)

    def update(self, dt, game) -> None:
        self.t += dt
        self.disc.setH(self.disc.getH() + (110.0 if self.solved else 25.0) * dt)
        if self.solved:
            self.disc.setScale(1.0 + math.sin(self.t * 3.0) * 0.08)


# ---------------------------------------------------------------------------
# Sequence pedestals - activate in the order an inscription gives you
# ---------------------------------------------------------------------------
class Pedestal(Interactable):
    """One note of a sequence. Out of order, the whole sequence resets."""

    prompt = "Sound the note"
    use_radius = 4.0
    one_shot = False

    def build(self, game) -> None:
        color = self.spec.color or Vec4(0.85, 0.70, 1.0, 1)
        self.lit_color = color
        mb = MeshBuilder()
        mb.cylinder((0, 0, 0), 1.5, 1.2, 1.8, Vec4(0.52, 0.50, 0.58, 1),
                    segments=10)
        mb.cylinder((0, 0, 1.8), 1.3, 1.1, 0.3, Vec4(0.40, 0.38, 0.46, 1),
                    segments=10)
        mb.build("pedestal").reparentTo(self.root)
        orb = MeshBuilder()
        orb.sphere((0, 0, 0), 0.75, RUNE_DIM, segments=10, rings=8)
        o = orb.build("pedestal_orb")
        o.setZ(2.7)
        o.setLightOff()
        o.reparentTo(self.root)
        self.orb = o

    def can_use(self, game) -> bool:
        return self.enabled and not game.puzzle.has(self.group)

    def light(self, on: bool) -> None:
        self.solved = on
        self.orb.setColorScale(self.lit_color if on else Vec4(1, 1, 1, 1))
        if not on:
            self.orb.setColorScale(0.45, 0.45, 0.52, 1)

    def use(self, game) -> None:
        progress = game.puzzle.count(self.group)
        # Only the pedestals count: the group also holds the gate they open.
        notes = [m for m in game.groups.get(self.group, [])
                 if isinstance(m, Pedestal)]
        if self.spec.order == progress:
            self.light(True)
            game.puzzle.counters[self.group] = progress + 1
            game.effects.burst(self.center() + Vec3(0, 0, 1.7), self.lit_color,
                               10, 5.0, 0.3, gravity=-3.0)
            game.audio.play("gem")
            if game.puzzle.counters[self.group] >= len(notes):
                game.on_puzzle_progress(self.group)
        else:
            # Wrong note: the sequence goes dark and you start again.
            game.puzzle.counters[self.group] = 0
            for m in notes:
                m.light(False)
            game.effects.burst(self.center() + Vec3(0, 0, 1.7),
                               Vec4(0.9, 0.35, 0.35, 1), 12, 5.0, 0.3)
            game.audio.play("hurt")
            game.hud.show_banner("", "Wrong order - the sequence resets", 1.6)

    def update(self, dt, game) -> None:
        self.t += dt
        self.orb.setZ(2.7 + math.sin(self.t * 2.0 + self.spec.order) * 0.12)


# ---------------------------------------------------------------------------
# Gates and bridges - the things puzzles actually move
# ---------------------------------------------------------------------------
class Gate(Interactable):
    """A barrier that sinks into the ground when its group is solved."""

    blocks = True
    use_radius = 0.0           # never hand-used; it listens to its group

    def build(self, game) -> None:
        size = self.spec.size or (10.0, 2.0, 9.0)
        self.size = size
        color = self.spec.color or Vec4(0.55, 0.52, 0.62, 1)
        mb = MeshBuilder()
        mb.box((0, 0, size[2] * 0.5), size, color, shade(color, 1.12))
        for i in range(3):
            mb.box((0, -size[1] * 0.5 - 0.06, size[2] * (0.25 + i * 0.25)),
                   (size[0] * 0.7, 0.16, 0.5),
                   Vec4(0.70, 0.55, 0.95, 1))
        mb.build("gate").reparentTo(self.root)
        self.closed_z = self.pos.z
        self.open_z = self.pos.z - size[2] - 1.0
        self.box_index = game.add_solid(
            Vec3(self.pos.x, self.pos.y, self.pos.z + size[2] * 0.5),
            Vec3(size[0] * 0.5, size[1] * 0.5, size[2] * 0.5))
        self.opening = False

    def can_use(self, game) -> bool:
        return False

    def open(self, game) -> None:
        if self.opening:
            return
        self.opening = True
        self.solved = True
        game.remove_solid(self.box_index)
        game.audio.play("portal")
        game.effects.ring(self.pos + Vec3(0, 0, 0.4),
                          Vec4(0.70, 0.60, 1.0, 1), 6.0, 18)

    def update(self, dt, game) -> None:
        self.t += dt
        if self.opening and self.root.getZ() > self.open_z:
            self.root.setZ(max(self.open_z, self.root.getZ() - dt * 5.5))


class Bridge(Interactable):
    """A span that extends into place when its group is solved."""

    blocks = True
    use_radius = 0.0

    def build(self, game) -> None:
        size = self.spec.size or (6.0, 22.0, 1.0)
        self.size = size
        color = self.spec.color or Vec4(0.62, 0.56, 0.48, 1)
        mb = MeshBuilder()
        mb.box((0, 0, 0), size, color, shade(color, 1.12))
        for sx in (-1, 1):
            mb.box((sx * size[0] * 0.5, 0, 0.7),
                   (0.3, size[1], 1.2), shade(color, 0.85))
        mb.build("bridge").reparentTo(self.root)
        # Starts retracted: pulled back along its own length and hidden below.
        self.travel = Vec3(*(self.spec.travel or (0, -size[1], -6.0)))
        self.stowed = self.pos + self.travel
        self.root.setPos(self.stowed)
        self.box_index = game.add_solid(
            Vec3(self.stowed), Vec3(size[0] * 0.5, size[1] * 0.5,
                                    size[2] * 0.5))
        self.extending = False

    def can_use(self, game) -> bool:
        return False

    def open(self, game) -> None:
        if self.extending:
            return
        self.extending = True
        self.solved = True
        game.audio.play("portal")

    def update(self, dt, game) -> None:
        self.t += dt
        if not self.extending:
            return
        cur = self.root.getPos()
        step = self.pos - cur
        if step.length() < 0.05:
            return
        if step.length() > 1e-4:
            move = min(step.length(), dt * 9.0)
            step.normalize()
            cur = cur + step * move
            self.root.setPos(cur)
            # Keep its collision box with it, or you would fall through.
            game.move_solid(self.box_index, cur)


# ---------------------------------------------------------------------------
# Levers, blocks and plates
# ---------------------------------------------------------------------------
class Lever(Interactable):
    """Pulled by hand. Drives whatever shares its group."""

    prompt = "Pull the lever"
    use_radius = 4.0

    def build(self, game) -> None:
        mb = MeshBuilder()
        mb.box((0, 0, 0.3), (2.0, 2.0, 0.6), Vec4(0.44, 0.42, 0.48, 1))
        mb.cylinder((0, 0, 0.6), 0.34, 0.30, 1.0, Vec4(0.36, 0.34, 0.40, 1),
                    segments=7)
        mb.build("lever_base").reparentTo(self.root)
        arm = MeshBuilder()
        arm.cylinder((0, 0, 0), 0.18, 0.15, 2.2, Vec4(0.60, 0.56, 0.62, 1),
                     segments=6)
        arm.sphere((0, 0, 2.4), 0.42, Vec4(0.95, 0.45, 0.55, 1), segments=9,
                   rings=7)
        a = arm.build("lever_arm")
        a.setZ(1.5)
        a.reparentTo(self.root)
        self.arm = a
        self.arm.setP(-28.0)

    def use(self, game) -> None:
        self.solved = True
        game.audio.play("menu")
        game.effects.burst(self.center() + Vec3(0, 0, 2.0),
                           Vec4(0.95, 0.55, 0.65, 1), 10, 5.0, 0.3)
        game.on_puzzle_progress(self.group)

    def update(self, dt, game) -> None:
        self.t += dt
        want = 34.0 if self.solved else -28.0
        cur = self.arm.getP()
        self.arm.setP(cur + max(-260.0 * dt, min(260.0 * dt, want - cur)))


class PushBlock(Interactable):
    """A crate the player shoves by walking into it."""

    blocks = True
    use_radius = 0.0

    def build(self, game) -> None:
        s = self.spec.size or (4.0, 4.0, 4.0)
        self.size = s
        color = self.spec.color or Vec4(0.60, 0.46, 0.32, 1)
        mb = MeshBuilder()
        mb.box((0, 0, s[2] * 0.5), s, color, shade(color, 1.15))
        for sx in (-1, 1):
            mb.box((sx * s[0] * 0.5, 0, s[2] * 0.5), (0.2, s[1] * 1.02,
                                                      s[2] * 0.3),
                   shade(color, 0.7))
        mb.box((0, 0, s[2] * 0.5), (s[0] * 1.02, 0.2, s[2] * 0.3),
               shade(color, 0.7))
        mb.build("block").reparentTo(self.root)
        self.half = Vec3(s[0] * 0.5, s[1] * 0.5, s[2] * 0.5)
        self.box_index = game.add_solid(
            Vec3(self.pos.x, self.pos.y, self.pos.z + self.half.z), self.half)

    def can_use(self, game) -> bool:
        return False

    def update(self, dt, game) -> None:
        self.t += dt
        p = game.player
        if p is None or not p.alive:
            return
        here = self.root.getPos()
        d = p.root.getPos() - here
        d.z = 0.0
        reach = self.half.x + p.radius + 1.2
        if d.length() > reach or abs(p.root.getZ() - here.z) > self.size[2]:
            return
        vel = Vec3(p.vel.x, p.vel.y, 0)
        if vel.length() < 1.2:
            return
        # Push along whichever axis the player is leaning on hardest.
        axis = Vec3(math.copysign(1.0, vel.x), 0, 0) if abs(vel.x) > abs(vel.y) \
            else Vec3(0, math.copysign(1.0, vel.y), 0)
        if axis.dot(d) > 0:              # only push away from the player
            return
        step = axis * (dt * 3.2)
        dest = here + step
        if game.solid_at(Vec3(dest.x, dest.y, dest.z + self.half.z),
                         self.half, ignore=self.box_index):
            return
        self.root.setPos(dest)
        game.move_solid(self.box_index,
                        Vec3(dest.x, dest.y, dest.z + self.half.z))


class Plate(Interactable):
    """A pressure plate. Held down by a block, or by the player standing on it."""

    blocks = False
    use_radius = 0.0

    def build(self, game) -> None:
        color = self.spec.color or Vec4(0.70, 0.62, 0.90, 1)
        self.lit_color = color
        mb = MeshBuilder()
        mb.box((0, 0, 0.12), (5.4, 5.4, 0.25), Vec4(0.34, 0.32, 0.40, 1))
        mb.build("plate_frame").reparentTo(self.root)
        top = MeshBuilder()
        top.box((0, 0, 0), (4.6, 4.6, 0.28), shade(color, 0.55))
        t = top.build("plate_top")
        t.setZ(0.32)
        t.setLightOff()
        t.reparentTo(self.root)
        self.top = t
        self.pressed = False

    def can_use(self, game) -> bool:
        return False

    def update(self, dt, game) -> None:
        self.t += dt
        held = False
        p = game.player
        if p is not None and p.alive:
            d = p.root.getPos() - self.root.getPos()
            if abs(d.x) < 2.6 and abs(d.y) < 2.6 and 0.0 <= d.z < 3.0:
                held = True
        if not held:
            for other in game.interactables:
                if isinstance(other, PushBlock):
                    d = other.root.getPos() - self.root.getPos()
                    if abs(d.x) < 2.8 and abs(d.y) < 2.8 and abs(d.z) < 3.0:
                        held = True
                        break
        if held != self.pressed:
            self.pressed = held
            self.solved = held
            self.top.setZ(0.16 if held else 0.32)
            self.top.setColorScale(self.lit_color if held
                                   else Vec4(1, 1, 1, 1))
            game.audio.play("menu" if held else "hit", 0.4)
            game.on_puzzle_progress(self.group)


# ---------------------------------------------------------------------------
# Hidden caches - the reward for looking around
# ---------------------------------------------------------------------------
class Cache(Interactable):
    """A hidden stash. Finding one is worth score, health or magic."""

    prompt = "Open the cache"
    use_radius = 4.0

    def build(self, game) -> None:
        color = Vec4(0.85, 0.70, 0.35, 1)
        mb = MeshBuilder()
        mb.box((0, 0, 0.9), (3.0, 2.2, 1.8), Vec4(0.46, 0.34, 0.24, 1),
               shade(color, 0.9))
        mb.box((0, 0, 1.9), (3.1, 2.3, 0.35), color)
        for sx in (-1, 1):
            mb.box((sx * 1.2, 0, 0.9), (0.22, 2.3, 1.9), color)
        mb.build("cache").reparentTo(self.root)
        glow = MeshBuilder()
        glow.sphere((0, 0, 1.4), 1.9, Vec4(1.0, 0.88, 0.45, 0.18),
                    segments=9, rings=6)
        g = glow.build("cache_glow")
        g.setTransparency(TransparencyAttrib.MAlpha)
        g.setDepthWrite(False)
        g.setLightOff()
        g.reparentTo(self.root)
        self.glow = g
        game.puzzle.secrets_total += 1

    def use(self, game) -> None:
        self.solved = True
        game.puzzle.secrets_found += 1
        p = game.player
        reward = self.spec.reward
        if reward == "health":
            p.health = min(p.health + 2.0, game.max_health)
        elif reward == "magic":
            p.magic = game.max_magic
        p.score += 250
        game.effects.burst(self.center() + Vec3(0, 0, 1.0),
                           Vec4(1.0, 0.85, 0.40, 1), 22, 8.0, 0.42)
        game.effects.ring(self.center(), Vec4(1.0, 0.90, 0.50, 1), 4.0, 14)
        game.audio.play("heart")
        game.hud.show_banner("SECRET FOUND",
                             "%d of %d" % (game.puzzle.secrets_found,
                                           game.puzzle.secrets_total), 2.2)
        self.glow.hide()
        self.root.setColorScale(0.6, 0.6, 0.6, 1)
        game.on_puzzle_progress(self.group)

    def update(self, dt, game) -> None:
        self.t += dt
        if not self.solved:
            self.glow.setScale(1.0 + math.sin(self.t * 2.6) * 0.14)
            self.root.setH(self.root.getH() + 18.0 * dt)


class Chest(Interactable):
    """A chest beside the path. Opens with a hinged lid and pays out."""

    prompt = "Open the chest"
    use_radius = 4.2

    REWARDS = {
        "score":  (Vec4(0.95, 0.80, 0.35, 1), "500 points"),
        "health": (Vec4(1.00, 0.42, 0.52, 1), "Health restored"),
        "magic":  (Vec4(0.45, 0.85, 1.00, 1), "Magic restored"),
        "life":   (Vec4(1.00, 0.70, 0.85, 1), "Extra life"),
        "gems":   (Vec4(0.60, 0.95, 0.85, 1), "A handful of crystals"),
    }

    def build(self, game) -> None:
        reward = self.spec.reward
        trim, _ = self.REWARDS.get(reward, self.REWARDS["score"])
        wood = Vec4(0.46, 0.30, 0.19, 1)
        self.trim = trim

        base = MeshBuilder()
        base.box((0, 0, 0.62), (2.5, 1.7, 1.25), wood, shade(wood, 1.12))
        for sx in (-1, 1):                                    # corner bands
            base.box((sx * 1.15, 0, 0.62), (0.22, 1.78, 1.30), trim)
        base.box((0, 0, 0.30), (2.58, 1.78, 0.20), trim)
        for sx in (-1, 1):                                    # feet
            for sy in (-1, 1):
                base.box((sx * 1.0, sy * 0.65, 0.10), (0.32, 0.32, 0.22),
                         shade(wood, 0.7))
        base.build("chest_base").reparentTo(self.root)

        lid = MeshBuilder()
        # A barrel lid, hinged along its back edge.
        lid.lathe((0, 0, 0), [(0.0, 0.0), (0.30, 0.62), (0.62, 0.80),
                              (0.95, 0.62), (1.25, 0.0)],
                  wood, segments=9, squash_y=1.0)
        lid.box((0, 0, 0.62), (2.5, 0.30, 1.24), trim)
        lid_np = lid.build("chest_lid")
        lid_np.setR(90)
        lid_np.setScale(1.0, 2.02, 1.0)
        hinge = self.root.attachNewNode("hinge")
        hinge.setPos(0, 0.85, 1.24)
        lid_np.reparentTo(hinge)
        lid_np.setPos(0, -0.85, 0)
        self.hinge = hinge

        glow = MeshBuilder()
        glow.sphere((0, 0, 1.3), 1.7, Vec4(trim[0], trim[1], trim[2], 0.16),
                    segments=9, rings=6)
        g = glow.build("chest_glow")
        g.setTransparency(TransparencyAttrib.MAlpha)
        g.setDepthWrite(False)
        g.setLightOff()
        g.reparentTo(self.root)
        self.glow = g
        self.open_angle = 0.0
        game.puzzle.chests_total += 1

    def use(self, game) -> None:
        self.solved = True
        game.puzzle.chests_opened += 1
        p = game.player
        reward = self.spec.reward
        _, label = self.REWARDS.get(reward, self.REWARDS["score"])
        if reward == "health":
            p.health = min(p.health + 3.0, game.max_health)
        elif reward == "magic":
            p.magic = game.max_magic
        elif reward == "life":
            p.lives += 1
        elif reward == "gems":
            p.gems += 3
            p.score += 150
        p.score += 500
        game.effects.burst(self.center() + Vec3(0, 0, 1.4), self.trim,
                           24, 8.0, 0.42)
        game.effects.ring(self.center() + Vec3(0, 0, 0.6),
                          shade(self.trim, 1.3), 4.0, 16)
        game.audio.play("heart")
        game.hud.show_banner("", label, 1.8)
        self.glow.hide()
        game.on_puzzle_progress(self.group)

    def update(self, dt, game) -> None:
        self.t += dt
        if self.solved:
            if self.open_angle < 105.0:
                self.open_angle = min(105.0, self.open_angle + dt * 260.0)
                self.hinge.setP(-self.open_angle)
        else:
            self.glow.setScale(1.0 + math.sin(self.t * 2.4) * 0.12)
            self.root.setZ(self.pos.z + math.sin(self.t * 1.6) * 0.04)


class Spring(Interactable):
    """A pad that throws the player upward when she lands on it."""

    use_radius = 0.0          # never hand-used; it fires on contact

    def build(self, game) -> None:
        self.power = float(self.spec.power or 26.0)
        body = MeshBuilder()
        body.lathe((0, 0, 0), [(0.0, 2.0), (0.30, 1.85), (0.45, 1.70)],
                   Vec4(0.86, 0.82, 0.30, 1), segments=_SEG)
        body.build("spring_base").reparentTo(self.root)
        top = MeshBuilder()
        top.lathe((0, 0, 0), [(0.0, 1.70), (0.34, 1.80), (0.52, 1.55)],
                  Vec4(0.95, 0.28, 0.34, 1), segments=_SEG)
        for i in range(_SEG):
            a = math.tau * i / _SEG
            top.sphere((math.cos(a) * 1.35, math.sin(a) * 1.35, 0.58), 0.16,
                       Vec4(1.0, 0.92, 0.45, 1), segments=6, rings=4)
        t = top.build("spring_top")
        t.setZ(0.45)
        t.reparentTo(self.root)
        self.top = t
        self.cooldown = 0.0

    def can_use(self, game) -> bool:
        return False

    def update(self, dt, game) -> None:
        self.t += dt
        self.cooldown = max(0.0, self.cooldown - dt)
        squash = 1.0 - max(0.0, self.cooldown - 0.25) * 1.6
        self.top.setSz(max(0.25, squash))
        p = game.player
        if p is None or not p.alive or self.cooldown > 0.0:
            return
        d = p.root.getPos() - self.root.getPos()
        if abs(d.x) < 2.4 and abs(d.y) < 2.4 and -0.5 < d.z < 3.0 \
                and p.vel.z <= 0.5:
            p.vel.z = self.power
            p.grounded = False
            self.cooldown = 0.55
            game.audio.play("jump")
            game.effects.burst(self.center(), Vec4(1.0, 0.85, 0.35, 1),
                               14, 7.0, 0.34, gravity=-6.0)


KINDS = {
    "tablet": Tablet,
    "chest": Chest,
    "spring": Spring,
    "rune": Rune,
    "pedestal": Pedestal,
    "gate": Gate,
    "bridge": Bridge,
    "lever": Lever,
    "block": PushBlock,
    "plate": Plate,
    "cache": Cache,
}

# Puzzle objects that a group opens rather than reports to.
OPENERS = (Gate, Bridge)


def spawn(spec, parent: NodePath, game) -> Interactable:
    return KINDS[spec.kind](parent, spec, game)
