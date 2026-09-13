"""Enemy types and their AI.

Each enemy is a small state machine (idle -> chase -> attack -> hurt -> dead).
Ground enemies snap to the terrain height sampled from the level's solid
boxes; flyers hold an altitude band around the player.
"""
from __future__ import annotations

import math
import random

from panda3d.core import NodePath, TransparencyAttrib, Vec3, Vec4

from .characters import _seg
from .geometry import MeshBuilder, shade

_rng = random.Random(3)


NO_GROUND = -1.0e9


def ground_height(solids, x: float, y: float, from_z: float) -> float:
    """Highest solid top under (x, y) at or below ``from_z``.

    Returns ``NO_GROUND`` when nothing is underneath - the levels float over
    open sky, so there is no floor at z=0 to fall back on.
    """
    best = NO_GROUND
    for center, half in solids:
        if (abs(x - center.x) <= half.x and abs(y - center.y) <= half.y):
            top = center.z + half.z
            if top <= from_z + 0.6 and top > best:
                best = top
    return best


class Enemy:
    """Base enemy. Subclasses supply a model and an ``update`` behaviour."""

    name = "enemy"
    max_health = 3.0
    radius = 1.2
    speed = 5.0
    touch_damage = 1.0
    score = 100
    hit_color = Vec4(0.9, 0.5, 0.9, 1)
    flying = False
    eye_height = 1.2

    def __init__(self, parent: NodePath, pos: Vec3, solids) -> None:
        self.solids = solids
        self.alive = True
        self.health = self.max_health
        self.hurt_timer = 0.0
        self.attack_cd = _rng.uniform(0.5, 1.6)
        self.state = "idle"
        self.t = _rng.uniform(0, 10.0)
        self.vel = Vec3(0, 0, 0)
        self.touch_cd = 0.0
        self.home = Vec3(pos)
        self.root = NodePath(self.name)
        self.root.reparentTo(parent)
        self.root.setPos(pos)
        self.model = NodePath("model")
        self.model.reparentTo(self.root)
        self.parts: dict[str, NodePath] = {}
        self.build_model()

    # -- helpers ------------------------------------------------------------
    def build_model(self) -> None:      # pragma: no cover - overridden
        raise NotImplementedError

    def center(self) -> Vec3:
        return self.root.getPos() + Vec3(0, 0, self.eye_height)

    def face(self, target: Vec3, dt: float, rate: float = 360.0) -> None:
        d = target - self.root.getPos()
        if d.lengthSquared() < 1e-6:
            return
        want = math.degrees(math.atan2(-d.x, d.y))
        cur = self.root.getH()
        diff = (want - cur + 180.0) % 360.0 - 180.0
        self.root.setH(cur + max(-rate * dt, min(rate * dt, diff)))

    def move_toward(self, target: Vec3, dt: float, speed: float,
                    stop_at: float = 0.0) -> float:
        d = target - self.root.getPos()
        dist = d.length()
        if dist > stop_at and dist > 1e-4:
            d.z = 0.0 if not self.flying else d.z
            if d.lengthSquared() > 1e-6:
                d.normalize()
                self.root.setPos(self.root.getPos() + d * (speed * dt))
        return dist

    def settle(self, dt: float) -> None:
        """Keep a ground enemy standing on whatever is beneath it."""
        p = self.root.getPos()
        gz = ground_height(self.solids, p.x, p.y, p.z + 1.0)
        self.vel.z += -26.0 * dt
        z = p.z + self.vel.z * dt
        if z <= gz:
            z = gz
            self.vel.z = 0.0
        elif z < -80.0:
            # Knocked clean off the course: put it back where it started
            # rather than let it fall forever.
            self.root.setPos(self.home)
            self.vel = Vec3(0, 0, 0)
            return
        self.root.setZ(z)

    def take_damage(self, amount: float, effects) -> None:
        if not self.alive:
            return
        self.health -= amount
        self.hurt_timer = 0.22
        if self.health <= 0.0:
            self.die(effects)

    def die(self, effects) -> None:
        self.alive = False
        effects.burst(self.center(), self.hit_color, 20, 9.0, 0.5)
        effects.ring(self.center(), shade(self.hit_color, 1.3), 3.0, 12)
        self.root.removeNode()

    def flash(self, dt: float) -> None:
        if self.hurt_timer > 0.0:
            self.hurt_timer -= dt
            self.model.setColorScale(2.4, 1.4, 1.4, 1.0)
            if self.hurt_timer <= 0.0:
                self.model.clearColorScale()

    # -- per-frame ----------------------------------------------------------
    def update(self, dt: float, player, effects) -> None:  # pragma: no cover
        raise NotImplementedError

    def touch_player(self, dt: float, player) -> None:
        self.touch_cd = max(0.0, self.touch_cd - dt)
        if self.touch_cd > 0.0 or not player.alive:
            return
        if (self.center() - player.center()).length() < self.radius + player.radius:
            if player.take_damage(self.touch_damage):
                self.touch_cd = 0.9


class Creeper(Enemy):
    """Low-tier melee swarmer. Rushes, then lunges."""

    name = "creeper"
    max_health = 3.0
    radius = 1.1
    speed = 6.2
    score = 100
    hit_color = Vec4(0.55, 0.85, 0.45, 1)
    eye_height = 0.9

    body = Vec4(0.42, 0.66, 0.36, 1)
    shell = Vec4(0.30, 0.42, 0.30, 1)

    def build_model(self) -> None:
        mb = MeshBuilder()
        mb.sphere((0, 0, 0.85), 0.95, self.body, segments=10, rings=8,
                  squash=0.75)
        mb.sphere((0, 0, 1.05), 0.85, self.shell, segments=10, rings=7,
                  squash=0.62)
        mb.sphere((0, -0.75, 0.80), 0.52, self.body, segments=9, rings=7)
        for sx in (-0.22, 0.22):
            mb.sphere((sx, -1.05, 0.95), 0.16, Vec4(1.0, 0.85, 0.2, 1),
                      segments=7, rings=5)
        for sx in (-0.55, 0.55):
            mb.cylinder((sx, -0.4, 0.55), 0.10, 0.06, -0.55, self.shell,
                        segments=6)
            mb.cylinder((sx, 0.35, 0.55), 0.10, 0.06, -0.55, self.shell,
                        segments=6)
        mb.build("creeper_mesh").reparentTo(self.model)

    def update(self, dt, player, effects) -> None:
        self.t += dt
        self.flash(dt)
        self.settle(dt)
        target = player.root.getPos()
        dist = (target - self.root.getPos()).length()
        if dist < 42.0 and player.alive:
            self.state = "chase"
            self.face(target, dt, 300.0)
            # Little hop-scuttle so it does not slide like a puck.
            speed = self.speed * (1.35 if dist < 12.0 else 1.0)
            self.move_toward(target, dt, speed, stop_at=1.4)
            self.model.setZ(abs(math.sin(self.t * 11.0)) * 0.22)
            self.model.setR(math.sin(self.t * 11.0) * 7.0)
        else:
            self.state = "idle"
            self.model.setZ(math.sin(self.t * 2.0) * 0.06)
        self.touch_player(dt, player)


class Wisp(Enemy):
    """Flying ranged attacker. Circles at range and spits bolts."""

    name = "wisp"
    max_health = 2.0
    radius = 1.0
    speed = 7.5
    score = 150
    hit_color = Vec4(0.75, 0.55, 1.0, 1)
    flying = True
    eye_height = 0.0

    core = Vec4(0.72, 0.45, 0.95, 1)

    def __init__(self, parent, pos, solids) -> None:
        super().__init__(parent, pos, solids)
        self.orbit = _rng.uniform(0, math.tau)
        self.orbit_dir = _rng.choice((-1.0, 1.0))
        self.hover = pos.z

    def build_model(self) -> None:
        mb = MeshBuilder()
        mb.sphere((0, 0, 0), 0.50, self.core, segments=_seg(10), rings=8)
        mb.sphere((0, 0, 0), 0.30, Vec4(1.0, 0.94, 1.0, 1),
                  segments=_seg(9), rings=7)
        for sx in (-0.16, 0.16):                                  # two eyes
            mb.sphere((sx, -0.38, 0.10), 0.085, Vec4(0.16, 0.06, 0.24, 1),
                      segments=6, rings=5)
        halo = MeshBuilder()
        halo.sphere((0, 0, 0), 0.86, Vec4(self.core[0], self.core[1],
                                          self.core[2], 0.22),
                    segments=_seg(10), rings=7)
        h = halo.build("wisp_halo")
        h.setTransparency(TransparencyAttrib.MAlpha)
        h.setDepthWrite(False)
        h.setLightOff()
        h.reparentTo(self.model)
        for i in range(3):
            a = math.tau * i / 3
            mb.cylinder((math.cos(a) * 0.5, math.sin(a) * 0.5, -0.2),
                        0.14, 0.02, -0.9, shade(self.core, 0.8), segments=6)
        m = mb.build("wisp_mesh")
        m.setLightOff()
        m.reparentTo(self.model)

    def update(self, dt, player, effects) -> None:
        self.t += dt
        self.flash(dt)
        self.orbit += self.orbit_dir * dt * 0.85
        p = player.center()
        dist = (p - self.root.getPos()).length()
        if dist < 46.0 and player.alive:
            self.state = "chase"
            # Hold station on a circle around the player, at their altitude.
            want = Vec3(p.x + math.cos(self.orbit) * 13.0,
                        p.y + math.sin(self.orbit) * 13.0,
                        max(p.z + 3.5, ground_height(self.solids, p.x, p.y,
                                                     p.z) + 5.0))
            step = want - self.root.getPos()
            if step.lengthSquared() > 1e-6:
                step.normalize()
                self.root.setPos(self.root.getPos() + step * (self.speed * dt))
            self.face(Vec3(p.x, p.y, self.root.getZ()), dt, 260.0)
            self.attack_cd -= dt
            if self.attack_cd <= 0.0 and dist < 34.0:
                self.attack_cd = _rng.uniform(1.6, 2.6)
                d = p - self.root.getPos()
                effects.spawn_bolt(self.root.getPos(), d, 24.0,
                                   Vec4(0.85, 0.45, 1.0, 1), 1.0, True,
                                   radius=0.38, life=2.2)
        else:
            self.state = "idle"
            self.root.setPos(self.home + Vec3(math.cos(self.t * 0.6) * 3.0,
                                              math.sin(self.t * 0.6) * 3.0,
                                              math.sin(self.t) * 0.8))
        self.model.setZ(math.sin(self.t * 3.2) * 0.28)
        self.model.setH(self.model.getH() + 160.0 * dt)
        self.touch_player(dt, player)


class Troll(Enemy):
    """Heavy melee brute. Telegraphs a slam, then commits to it."""

    name = "troll"
    max_health = 9.0
    radius = 1.9
    speed = 4.2
    touch_damage = 2.0
    score = 300
    hit_color = Vec4(0.85, 0.60, 0.35, 1)
    eye_height = 1.8

    hide = Vec4(0.52, 0.42, 0.34, 1)
    cloth = Vec4(0.40, 0.28, 0.42, 1)

    def __init__(self, parent, pos, solids) -> None:
        super().__init__(parent, pos, solids)
        self.windup = 0.0
        self.slam_done = False

    def build_model(self) -> None:
        mb = MeshBuilder()
        rng = random.Random(17)
        for sx in (-0.42, 0.42):                                  # legs
            mb.lathe((sx, 0, 0.0), [(0.0, 0.30), (0.50, 0.26), (1.10, 0.34)],
                     self.hide, segments=_seg(8))
            mb.sphere((sx, -0.10, 0.06), 0.34, shade(self.hide, 0.92),
                      segments=_seg(7), rings=5, squash=0.6)
        mb.lathe((0, 0, 0.95),                                    # torso
                 [(0.0, 0.62), (0.40, 0.86), (0.95, 0.92), (1.35, 0.74),
                  (1.60, 0.56)],
                 self.hide, segments=_seg(11), squash_y=0.88)
        mb.lathe((0, 0, 0.92), [(0.0, 0.68), (0.34, 0.74)], self.cloth,
                 segments=_seg(11), cap_top=False, cap_bottom=False)
        mb.lathe((0, 0, 2.42),                                    # head
                 [(-0.24, 0.34), (-0.06, 0.58), (0.14, 0.66), (0.34, 0.56),
                  (0.46, 0.30)],
                 self.hide, segments=_seg(10), squash_y=0.94)
        mb.lathe((0, -0.44, 2.40), [(0.0, 0.24), (0.18, 0.28), (0.32, 0.18)],
                 shade(self.hide, 1.08), segments=_seg(8))         # snout
        for sx in (-0.24, 0.24):
            mb.sphere((sx, -0.44, 2.72), 0.115, Vec4(0.95, 0.30, 0.22, 1),
                      segments=_seg(7), rings=5)
            mb.box((sx, -0.38, 2.86), (0.26, 0.12, 0.07),
                   shade(self.hide, 0.6))
            mb.lathe((sx * 0.8, -0.50, 2.28), [(0.0, 0.025), (0.20, 0.065)],
                     Vec4(0.90, 0.88, 0.78, 1), segments=5, cap_top=False)
        for _ in range(10):                                       # hide bumps
            a = rng.uniform(0, math.tau)
            z = rng.uniform(1.0, 2.2)
            mb.sphere((math.cos(a) * 0.85, math.sin(a) * 0.75, z),
                      rng.uniform(0.06, 0.12), shade(self.hide, 0.86),
                      segments=6, rings=5)
        arm = MeshBuilder()
        for sx in (-1.02, 1.02):
            arm.sphere((sx, 0, 2.28), 0.44, self.hide, segments=_seg(8),
                       rings=6)
            arm.sphere((sx * 0.68, 0, 2.32), 0.36, shade(self.hide, 1.04),
                       segments=_seg(7), rings=5)
            arm.lathe((sx, 0, 0.95), [(0.0, 0.34), (0.70, 0.30), (1.33, 0.38)],
                      self.hide, segments=_seg(8))
            arm.sphere((sx, -0.04, 0.90), 0.44, shade(self.hide, 0.92),
                       segments=_seg(8), rings=6)
        mb.build("troll_mesh").reparentTo(self.model)
        arms = arm.build("troll_arms")
        arms.reparentTo(self.model)
        self.parts["arms"] = arms

    def update(self, dt, player, effects) -> None:
        self.t += dt
        self.flash(dt)
        self.settle(dt)
        target = player.root.getPos()
        dist = (target - self.root.getPos()).length()

        if self.windup > 0.0:
            # Committed to the slam: rear up, then drop a shockwave.
            self.windup -= dt
            self.face(target, dt, 90.0)
            k = max(0.0, self.windup / 0.9)
            self.parts["arms"].setP(-70.0 * (1.0 - k))
            self.parts["arms"].setZ(1.1 * (1.0 - k))
            if self.windup <= 0.0 and not self.slam_done:
                self.slam_done = True
                self.parts["arms"].setP(0)
                self.parts["arms"].setZ(0)
                effects.ring(self.root.getPos() + Vec3(0, 0, 0.3),
                             Vec4(0.9, 0.7, 0.4, 1), 5.0, 16)
                if dist < 6.5 and player.alive:
                    player.take_damage(2.0)
                self.attack_cd = 1.8
            return

        if dist < 40.0 and player.alive:
            self.state = "chase"
            self.face(target, dt, 170.0)
            self.attack_cd -= dt
            if dist < 6.0 and self.attack_cd <= 0.0:
                self.windup = 0.9
                self.slam_done = False
            else:
                self.move_toward(target, dt, self.speed, stop_at=4.2)
                sway = math.sin(self.t * 4.5)
                self.model.setR(sway * 5.0)
                self.parts["arms"].setP(sway * 18.0)
        else:
            self.state = "idle"
            self.model.setR(math.sin(self.t * 1.2) * 2.0)
        self.touch_player(dt, player)


class Trix(Enemy):
    """Base class for the three witches of Cloud Tower.

    Icy, Darcy and Stormy share a silhouette and a three-phase structure; each
    subclass supplies her own palette and her own attack for each phase.
    """

    name = "trix"
    max_health = 40.0
    radius = 2.0
    speed = 8.0
    touch_damage = 2.0
    score = 2000
    hit_color = Vec4(0.55, 0.75, 1.0, 1)
    flying = True
    eye_height = 0.0
    is_boss = True
    title = "WITCH OF CLOUD TOWER"

    robe = Vec4(0.30, 0.36, 0.62, 1)
    ice = Vec4(0.60, 0.85, 1.0, 1)      # her signature element's colour
    hair = Vec4(0.82, 0.90, 1.0, 1)

    def __init__(self, parent, pos, solids) -> None:
        super().__init__(parent, pos, solids)
        self.phase = 1
        self.orbit = 0.0
        self.pattern_cd = 2.0
        self.shield = 0.0
        self.summon_request = 0

    # Per-sister silhouette, so they are not three palette swaps.
    hair_style = "straight"      # straight | spiky | wild
    gown = "long"                # long | slim | short
    charm = "shard"              # the shape orbiting her

    def build_model(self) -> None:
        mb = MeshBuilder()
        skin = Vec4(0.93, 0.86, 0.86, 1)

        # --- gown ---------------------------------------------------------
        if self.gown == "slim":
            profile = [(-2.6, 0.62), (-1.6, 0.72), (-0.7, 0.66), (0.0, 0.52),
                       (0.55, 0.44), (0.95, 0.40)]
        elif self.gown == "short":
            profile = [(-1.15, 1.10), (-0.75, 0.86), (-0.25, 0.56),
                       (0.30, 0.46), (0.75, 0.42), (0.95, 0.38)]
        else:
            profile = [(-2.9, 1.45), (-1.8, 1.10), (-0.9, 0.74), (0.0, 0.54),
                       (0.55, 0.46), (0.95, 0.40)]
        mb.lathe((0, 0, 0), profile, self.robe, segments=_seg(13),
                 cap_top=False, squash_y=0.92)
        mb.lathe((0, 0, 0.95), [(0.0, 0.40), (0.22, 0.30), (0.34, 0.22)],
                 skin, segments=_seg(10), cap_bottom=False, cap_top=False)
        mb.box((0, 0, 0.10), (0.95, 0.70, 0.12), shade(self.ice, 0.9))
        for sx in (-1, 1):                                        # arms
            mb.lathe((sx * 0.62, 0, 0.30),
                     [(0.0, 0.09), (0.55, 0.12), (0.86, 0.17)],
                     shade(self.robe, 1.15), segments=_seg(8))
            mb.sphere((sx * 0.66, 0, 0.24), 0.10, skin, segments=6, rings=5)

        # --- head ---------------------------------------------------------
        mb.lathe((0, 0, 1.25),
                 [(-0.06, 0.16), (0.08, 0.30), (0.24, 0.38), (0.40, 0.36),
                  (0.52, 0.26), (0.60, 0.11)],
                 skin, segments=_seg(12), squash_y=0.94)
        for sx in (-1, 1):
            mb.disc((sx * 0.145, -0.345, 1.52), 0.085,
                    Vec4(0.98, 0.97, 0.98, 1), _seg(9), squash=1.1)
            mb.disc((sx * 0.145, -0.355, 1.51), 0.050, self.ice, _seg(9))
            mb.disc((sx * 0.145, -0.362, 1.50), 0.024,
                    Vec4(0.08, 0.07, 0.10, 1), 7)
            # Slanted brows: none of the three is pleased to see you.
            mb.box((sx * 0.16, -0.330, 1.63), (0.17, 0.03, 0.028),
                   shade(self.hair, 0.55))
        mb.disc((0, -0.340, 1.38), 0.050, Vec4(0.70, 0.25, 0.35, 1), 8,
                squash=0.45)

        # --- hair ---------------------------------------------------------
        mb.lathe((0, 0.10, 1.30),
                 [(0.10, 0.35), (0.26, 0.395), (0.42, 0.395), (0.52, 0.34),
                  (0.60, 0.23), (0.66, 0.10)],
                 self.hair, segments=_seg(12), cap_bottom=False)
        if self.hair_style == "spiky":
            # Icy: hair like a shattered icicle crown.
            for i in range(9):
                a = math.tau * i / 9
                mb.lathe((math.cos(a) * 0.34, 0.10 + math.sin(a) * 0.34, 1.78),
                         [(0.0, 0.13), (0.45, 0.07), (0.85, 0.0)],
                         shade(self.hair, 1.1), segments=5, cap_top=False)
            for sx in (-1, 1):
                mb.lathe((sx * 0.34, 0.16, 1.42),
                         [(-1.10, 0.0), (-0.5, 0.12), (0.0, 0.17)],
                         self.hair, segments=6)
        elif self.hair_style == "wild":
            # Stormy: a storm cloud of frizz.
            for _ in range(26):
                a = _rng.uniform(0, math.tau)
                r = _rng.uniform(0.30, 0.62)
                z = _rng.uniform(1.42, 2.05)
                mb.sphere((math.cos(a) * r, 0.10 + math.sin(a) * r * 0.9, z),
                          _rng.uniform(0.17, 0.30), self.hair,
                          segments=_seg(7), rings=5)
        else:
            # Darcy: long, straight, and very heavy.
            mb.lathe((0, 0.24, 1.52),
                     [(-2.05, 0.24), (-1.30, 0.36), (-0.55, 0.40),
                      (0.0, 0.34)],
                     self.hair, segments=_seg(11), cap_top=False)
            for sx in (-1, 1):
                mb.lathe((sx * 0.33, 0.04, 1.56),
                         [(-1.45, 0.05), (-0.7, 0.11), (0.04, 0.14)],
                         self.hair, segments=6)

        # --- her charm, orbiting ------------------------------------------
        shards = MeshBuilder()
        for i in range(6):
            a = math.tau * i / 6
            x, y = math.cos(a) * 2.6, math.sin(a) * 2.6
            col = Vec4(self.ice[0], self.ice[1], self.ice[2], 0.78)
            if self.charm == "orb":
                shards.sphere((x, y, 0.1), 0.34, col, segments=_seg(8),
                              rings=6)
            elif self.charm == "bolt":
                for k in range(3):
                    shards.box((x + (k - 1) * 0.16, y, 0.1 + (k - 1) * 0.30),
                               (0.16, 0.16, 0.34), col)
            else:
                shards.lathe((x, y, -0.5),
                             [(0.0, 0.0), (0.55, 0.26), (1.6, 0.0)],
                             col, segments=6)
        s = shards.build("trix_charm")
        s.setTransparency(TransparencyAttrib.MAlpha)
        s.setTwoSided(True)
        s.setLightOff()
        s.reparentTo(self.model)
        self.parts["shards"] = s
        mb.build("trix_mesh").reparentTo(self.model)

    def update(self, dt, player, effects) -> None:
        self.t += dt
        self.flash(dt)
        self.parts["shards"].setH(self.parts["shards"].getH() + 120.0 * dt)
        self.parts["shards"].setZ(math.sin(self.t * 1.6) * 0.4)

        frac = self.health / self.max_health
        self.phase = 1 if frac > 0.66 else (2 if frac > 0.33 else 3)

        p = player.center()
        # Hover on a slow orbit above the dais, always facing the player.
        self.orbit += dt * (0.35 + 0.12 * self.phase)
        radius = 16.0 - 2.0 * self.phase
        want = Vec3(math.cos(self.orbit) * radius,
                    math.sin(self.orbit) * radius,
                    9.0 + math.sin(self.t * 0.9) * 2.0)
        step = want - self.root.getPos()
        if step.lengthSquared() > 1e-6:
            step.normalize()
            self.root.setPos(self.root.getPos() + step * (self.speed * dt))
        self.face(Vec3(p.x, p.y, self.root.getZ()), dt, 200.0)

        if not player.alive:
            return
        self.pattern_cd -= dt
        if self.pattern_cd > 0.0:
            return

        d = p - self.root.getPos()
        self.cast(self.phase, d, player, effects)
        effects.burst(self.root.getPos(), self.ice, 8, 5.0, 0.35)

    # -- attacks ------------------------------------------------------------
    def cast(self, phase, d, player, effects) -> None:
        """Fire this witch's attack for the given phase. Overridden per Trix."""
        self.spread(d, effects, 3, 10.0, 26.0)

    def spread(self, d, effects, count, degrees, speed, color=None,
               life=2.4) -> None:
        """A fan of bolts centred on ``d``."""
        self.pattern_cd = 1.9
        base = Vec3(d)
        if base.lengthSquared() < 1e-6:
            return
        base.normalize()
        for i in range(count):
            ang = math.radians((i - (count - 1) * 0.5) * degrees)
            ca, sa = math.cos(ang), math.sin(ang)
            dirn = Vec3(base.x * ca - base.y * sa,
                        base.x * sa + base.y * ca, base.z)
            effects.spawn_bolt(self.root.getPos(), dirn, speed,
                               color or self.ice, 1.0, True, radius=0.45,
                               life=life)

    def ring_attack(self, effects, count=10, speed=19.0, color=None) -> None:
        """A full circle of shards - forces the player to move, not dodge."""
        self.pattern_cd = 2.6
        for i in range(count):
            a = math.tau * i / count
            effects.spawn_bolt(self.root.getPos(),
                               Vec3(math.cos(a), math.sin(a), -0.15), speed,
                               color or self.ice, 1.0, True, radius=0.4,
                               life=2.6)

    def homing_volley(self, d, player, effects, count=3, color=None) -> None:
        self.pattern_cd = 2.2
        for _ in range(count):
            jitter = Vec3(_rng.uniform(-1, 1), _rng.uniform(-1, 1), 0.2)
            effects.spawn_bolt(self.root.getPos(), d + jitter * 4.0, 20.0,
                               color or self.ice, 1.0, True, radius=0.42,
                               life=3.0, homing=1.9, target=player)


class Icy(Trix):
    """Eldest of the Trix. Ice: straight volleys, shard rings, homing frost."""

    name = "icy"
    title = "ICY - WITCH OF ICE"
    max_health = 40.0
    score = 2000
    robe = Vec4(0.30, 0.40, 0.66, 1)
    ice = Vec4(0.62, 0.88, 1.00, 1)
    hair = Vec4(0.85, 0.93, 1.00, 1)
    hit_color = Vec4(0.62, 0.88, 1.00, 1)
    hair_style = "spiky"
    gown = "long"
    charm = "shard"

    def cast(self, phase, d, player, effects) -> None:
        if phase == 1:
            self.spread(d, effects, 3, 10.0, 26.0)
        elif phase == 2:
            self.ring_attack(effects, 10, 19.0)
            self.summon_request += 1
        else:
            self.homing_volley(d, player, effects, 3)


class Darcy(Trix):
    """Middle sister. Darkness: wide blinding fans and illusory doubles."""

    name = "darcy"
    title = "DARCY - WITCH OF DARKNESS"
    max_health = 38.0
    score = 2000
    speed = 9.0
    robe = Vec4(0.34, 0.24, 0.46, 1)
    ice = Vec4(0.66, 0.42, 0.92, 1)
    hair = Vec4(0.34, 0.24, 0.44, 1)
    hit_color = Vec4(0.66, 0.42, 0.92, 1)
    hair_style = "straight"
    gown = "slim"
    charm = "orb"

    def cast(self, phase, d, player, effects) -> None:
        if phase == 1:
            # A wide, slow curtain of dark - easy to see, hard to walk through.
            self.spread(d, effects, 5, 14.0, 20.0, life=2.8)
        elif phase == 2:
            self.spread(d, effects, 7, 11.0, 22.0, life=2.8)
            self.summon_request += 1
        else:
            self.homing_volley(d, player, effects, 4)
            self.pattern_cd = 2.4


class Stormy(Trix):
    """Youngest. Storms: fast bolts from odd angles, then everything at once."""

    name = "stormy"
    title = "STORMY - WITCH OF STORMS"
    max_health = 36.0
    score = 2000
    speed = 9.5
    robe = Vec4(0.44, 0.24, 0.42, 1)
    ice = Vec4(0.96, 0.56, 0.88, 1)
    hair = Vec4(0.62, 0.26, 0.50, 1)
    hit_color = Vec4(0.96, 0.56, 0.88, 1)
    hair_style = "wild"
    gown = "short"
    charm = "bolt"

    def cast(self, phase, d, player, effects) -> None:
        if phase == 1:
            self.spread(d, effects, 2, 16.0, 34.0)
            self.pattern_cd = 1.4
        elif phase == 2:
            self.ring_attack(effects, 14, 24.0)
            self.pattern_cd = 2.2
        else:
            self.spread(d, effects, 5, 12.0, 34.0)
            self.homing_volley(d, player, effects, 2)
            self.pattern_cd = 1.8


class Ghoul(Enemy):
    """The Trix's foot soldiers. Fast, fragile, and they never come alone."""

    name = "ghoul"
    max_health = 2.5
    radius = 1.0
    speed = 7.0
    score = 120
    hit_color = Vec4(0.60, 0.45, 0.80, 1)
    eye_height = 1.2

    robe = Vec4(0.47, 0.41, 0.60, 1)
    bone = Vec4(0.80, 0.78, 0.70, 1)
    glow = Vec4(0.95, 0.45, 1.00, 1)

    def build_model(self) -> None:
        mb = MeshBuilder()
        # A hunched robe that flares to a ragged hem, with nothing inside the
        # hood but two lights.
        # Narrow the robe into a neck so the hood reads as a head rather
        # than the top of a sack.
        mb.lathe((0, 0, 0.0),
                 [(0.0, 0.62), (0.30, 0.50), (0.80, 0.44), (1.22, 0.48),
                  (1.50, 0.36), (1.68, 0.24)],
                 self.robe, segments=_seg(11), cap_bottom=False)
        # A pale mantle over the shoulders, for contrast against the robe.
        mb.lathe((0, 0, 1.14),
                 [(0.0, 0.58), (0.16, 0.46), (0.30, 0.30)],
                 shade(self.robe, 1.45), segments=_seg(11), cap_top=False)
        # Ragged hem: spikes of cloth hanging past the bottom ring.
        for i in range(_seg(11)):
            a = math.tau * i / _seg(11)
            r = 0.60
            mb.lathe((math.cos(a) * r, math.sin(a) * r, 0.05),
                     [(-0.28 - (i % 3) * 0.09, 0.0), (0.0, 0.11)],
                     shade(self.robe, 0.8), segments=5, cap_top=False)
        # Hood.
        # The hood is set back so the hollow inside it, and the two lights
        # in that hollow, stay visible from the front.
        mb.lathe((0, 0.16, 1.76),
                 [(0.0, 0.30), (0.14, 0.42), (0.32, 0.42), (0.46, 0.30),
                  (0.54, 0.11)],
                 shade(self.robe, 0.80), segments=_seg(10), cap_bottom=False,
                 squash_y=1.06)
        mb.sphere((0, 0.02, 1.96), 0.30, Vec4(0.06, 0.05, 0.09, 1),
                  segments=_seg(9), rings=7)
        for sx in (-0.135, 0.135):
            mb.sphere((sx, -0.16, 1.99), 0.125, self.glow,
                      segments=_seg(8), rings=6)
            mb.sphere((sx, -0.24, 1.99), 0.065,
                      Vec4(1.0, 0.96, 1.0, 1), segments=6, rings=5)
        # Arms ending in bony claws.
        for sx in (-1, 1):
            mb.lathe((sx * 0.40, 0, 0.50),
                     [(0.0, 0.055), (0.55, 0.085), (0.95, 0.13)],
                     self.robe, segments=_seg(7))
            mb.sphere((sx * 0.46, -0.04, 0.46), 0.10, self.bone,
                      segments=_seg(7), rings=5)
            for k in range(3):
                ka = -0.5 + k * 0.5
                mb.lathe((sx * 0.46 + math.sin(ka) * 0.09, -0.06,
                          0.20),
                         [(0.0, 0.012), (0.18, 0.028), (0.26, 0.034)],
                         self.bone, segments=5, cap_top=False)
        mb.build("ghoul_mesh").reparentTo(self.model)

    def update(self, dt, player, effects) -> None:
        self.t += dt
        self.flash(dt)
        self.settle(dt)
        target = player.root.getPos()
        dist = (target - self.root.getPos()).length()
        if dist < 45.0 and player.alive:
            self.state = "chase"
            self.face(target, dt, 280.0)
            self.move_toward(target, dt,
                             self.speed * (1.25 if dist < 14.0 else 1.0),
                             stop_at=1.5)
            # A loping, lurching gait rather than a smooth glide.
            self.model.setZ(abs(math.sin(self.t * 7.0)) * 0.18)
            self.model.setR(math.sin(self.t * 3.5) * 9.0)
        else:
            self.state = "idle"
            self.model.setZ(math.sin(self.t * 1.8) * 0.05)
        self.touch_player(dt, player)


class Knut(Enemy):
    """The ogre. A boss in Chapter 1, ordinary muscle for the Trix later."""

    name = "knut"
    title = "KNUT - OGRE"
    max_health = 22.0
    radius = 2.3
    speed = 5.0
    touch_damage = 2.0
    score = 800
    hit_color = Vec4(0.80, 0.62, 0.40, 1)
    eye_height = 2.2
    is_boss = True

    hide = Vec4(0.56, 0.48, 0.34, 1)
    cloth = Vec4(0.46, 0.26, 0.28, 1)
    tusk = Vec4(0.92, 0.90, 0.80, 1)

    def __init__(self, parent, pos, solids) -> None:
        super().__init__(parent, pos, solids)
        self.windup = 0.0
        self.slam_done = False
        self.charge = 0.0
        self.summon_request = 0

    def build_model(self) -> None:
        mb = MeshBuilder()
        rng = _rng
        # Stumpy legs under a heavy gut.
        for sx in (-0.62, 0.62):
            mb.lathe((sx, 0, 0.0),
                     [(0.0, 0.46), (0.55, 0.40), (1.25, 0.48)],
                     self.hide, segments=_seg(9))
            mb.sphere((sx, -0.16, 0.10), 0.50, shade(self.hide, 0.92),
                      segments=_seg(8), rings=6, squash=0.6)
        # Belly, chest and the loincloth over them.
        mb.lathe((0, 0, 1.05),
                 [(0.0, 1.05), (0.45, 1.32), (1.00, 1.24), (1.50, 1.00),
                  (1.80, 0.78)],
                 self.hide, segments=_seg(12), squash_y=0.86)
        mb.lathe((0, 0, 1.02), [(0.0, 1.10), (0.40, 1.16)], self.cloth,
                 segments=_seg(12), cap_top=False, cap_bottom=False)
        mb.box((0, -0.62, 1.20), (0.9, 0.5, 1.0), shade(self.cloth, 0.85))
        # Head: low brow, heavy jaw, snout and tusks.
        mb.lathe((0, 0, 2.85),
                 [(-0.30, 0.55), (-0.12, 0.86), (0.10, 1.00), (0.34, 0.92),
                  (0.52, 0.62), (0.62, 0.24)],
                 self.hide, segments=_seg(11), squash_y=0.95)
        mb.lathe((0, -0.62, 2.78),
                 [(0.0, 0.42), (0.22, 0.50), (0.40, 0.36)],
                 shade(self.hide, 1.08), segments=_seg(9), squash_y=0.8)
        for sx in (-0.26, 0.26):                                  # nostrils
            mb.sphere((sx, -0.92, 2.98), 0.075, Vec4(0.24, 0.18, 0.14, 1),
                      segments=6, rings=5)
        for sx in (-0.34, 0.34):                                  # eyes
            mb.sphere((sx, -0.62, 3.30), 0.16, Vec4(0.94, 0.88, 0.62, 1),
                      segments=_seg(8), rings=6)
            mb.sphere((sx, -0.72, 3.30), 0.075, Vec4(0.12, 0.08, 0.06, 1),
                      segments=6, rings=5)
            mb.box((sx, -0.56, 3.50), (0.34, 0.16, 0.09),
                   shade(self.hide, 0.6))                         # brow
        for sx in (-0.30, 0.30):                                  # tusks
            mb.lathe((sx, -0.70, 2.62),
                     [(0.0, 0.03), (0.30, 0.09), (0.52, 0.13)],
                     self.tusk, segments=6, cap_top=False)
        for sx in (-1, 1):                                        # ears
            mb.lathe((sx * 0.92, 0.16, 3.05),
                     [(0.0, 0.06), (0.22, 0.22), (0.44, 0.10)],
                     shade(self.hide, 0.88), segments=6)
        # Warts, because an ogre should not be smooth.
        for _ in range(14):
            a = rng.uniform(0, math.tau)
            z = rng.uniform(1.2, 2.6)
            r = 1.18 if z < 2.2 else 0.9
            mb.sphere((math.cos(a) * r, math.sin(a) * r * 0.86, z),
                      rng.uniform(0.07, 0.14), shade(self.hide, 0.86),
                      segments=6, rings=5)
        arm = MeshBuilder()
        for sx in (-1.42, 1.42):
            arm.sphere((sx, 0, 2.62), 0.62, self.hide, segments=_seg(9),
                       rings=7)
            arm.sphere((sx * 0.72, 0, 2.66), 0.50, shade(self.hide, 1.04),
                       segments=_seg(8), rings=6)
            arm.lathe((sx, 0, 1.00),
                      [(0.0, 0.52), (0.85, 0.44), (1.62, 0.56)],
                      self.hide, segments=_seg(9))
            arm.sphere((sx, -0.05, 0.92), 0.62, shade(self.hide, 0.94),
                       segments=_seg(9), rings=7)
            for k in range(4):                                    # knuckles
                arm.sphere((sx + (k - 1.5) * 0.24, -0.44, 0.88), 0.16,
                           shade(self.hide, 1.06), segments=6, rings=5)
        mb.build("knut_mesh").reparentTo(self.model)
        arms = arm.build("knut_arms")
        arms.reparentTo(self.model)
        self.parts["arms"] = arms

    def update(self, dt, player, effects) -> None:
        self.t += dt
        self.flash(dt)
        self.settle(dt)
        target = player.root.getPos()
        dist = (target - self.root.getPos()).length()

        if self.windup > 0.0:
            self.windup -= dt
            self.face(target, dt, 80.0)
            k = max(0.0, self.windup / 1.0)
            self.parts["arms"].setP(-80.0 * (1.0 - k))
            self.parts["arms"].setZ(1.3 * (1.0 - k))
            if self.windup <= 0.0 and not self.slam_done:
                self.slam_done = True
                self.parts["arms"].setP(0)
                self.parts["arms"].setZ(0)
                effects.ring(self.root.getPos() + Vec3(0, 0, 0.3),
                             Vec4(0.90, 0.72, 0.45, 1), 7.0, 20)
                effects.burst(self.root.getPos(), self.hit_color, 14, 8.0, 0.5)
                if dist < 8.0 and player.alive:
                    player.take_damage(2.0)
                self.attack_cd = 2.0
                # Below half health he starts whistling for ghouls.
                if self.health < self.max_health * 0.5:
                    self.summon_request += 1
            return

        if dist < 45.0 and player.alive:
            self.state = "chase"
            self.face(target, dt, 150.0)
            self.attack_cd -= dt
            if dist < 7.5 and self.attack_cd <= 0.0:
                self.windup = 1.0
                self.slam_done = False
            else:
                self.move_toward(target, dt, self.speed, stop_at=5.0)
                sway = math.sin(self.t * 3.8)
                self.model.setR(sway * 6.0)
                self.parts["arms"].setP(sway * 20.0)
        else:
            self.state = "idle"
            self.model.setR(math.sin(self.t * 1.1) * 2.5)
        self.touch_player(dt, player)


class DecayBeast(Enemy):
    """Army of Decay. Slow, heavy, and it rots the ground it stands on."""

    name = "decay"
    max_health = 12.0
    radius = 1.8
    speed = 4.6
    touch_damage = 2.0
    score = 400
    hit_color = Vec4(0.55, 0.62, 0.35, 1)
    eye_height = 1.6

    rot = Vec4(0.46, 0.48, 0.32, 1)
    bile = Vec4(0.74, 0.86, 0.34, 1)

    def build_model(self) -> None:
        mb = MeshBuilder()
        rng = random.Random(5)
        # Deliberately lopsided: nothing in the Army of Decay is symmetrical.
        mb.lathe((0, 0, 0.0),
                 [(0.0, 0.80), (0.45, 1.00), (1.20, 1.18), (1.95, 1.05),
                  (2.45, 0.72), (2.70, 0.40)],
                 self.rot, segments=_seg(11), squash_y=0.88)
        mb.sphere((0.38, -0.22, 2.30), 0.66, shade(self.rot, 1.12),
                  segments=_seg(9), rings=7)
        # A maw rather than a face.
        mb.sphere((0.30, -0.62, 2.18), 0.34, Vec4(0.12, 0.14, 0.08, 1),
                  segments=_seg(8), rings=6)
        for k in range(6):
            ka = -0.7 + k * 0.28
            mb.lathe((0.30 + math.sin(ka) * 0.26, -0.70,
                      2.32 - abs(k - 2.5) * 0.02),
                     [(-0.20, 0.0), (0.0, 0.045)],
                     Vec4(0.85, 0.86, 0.72, 1), segments=5, cap_top=False)
        # Sores and bile blisters over the body.
        for _ in range(16):
            a = rng.uniform(0, math.tau)
            z = rng.uniform(0.5, 2.5)
            r = (1.10 if z < 2.0 else 0.7) * rng.uniform(0.85, 1.0)
            mb.sphere((math.cos(a) * r, math.sin(a) * r * 0.88, z),
                      rng.uniform(0.10, 0.26),
                      self.bile if rng.random() < 0.45
                      else shade(self.rot, 0.82),
                      segments=6, rings=5)
        # Mismatched limbs: one long arm, one stump, uneven feet.
        mb.lathe((-1.08, 0.05, 1.85),
                 [(-1.45, 0.13), (-0.70, 0.22), (0.0, 0.30)],
                 shade(self.rot, 0.88), segments=_seg(8))
        mb.sphere((-1.12, 0.0, 0.42), 0.26, shade(self.rot, 0.8),
                  segments=6, rings=5)
        mb.lathe((1.02, 0.05, 1.90),
                 [(-0.80, 0.18), (-0.30, 0.26), (0.0, 0.30)],
                 shade(self.rot, 0.88), segments=_seg(8))
        for sx, rr in ((-0.48, 0.34), (0.52, 0.28)):
            mb.sphere((sx, -0.10, 0.05), rr, shade(self.rot, 0.78),
                      segments=6, rings=5, squash=0.55)
        mb.build("decay_mesh").reparentTo(self.model)

    def update(self, dt, player, effects) -> None:
        self.t += dt
        self.flash(dt)
        self.settle(dt)
        target = player.root.getPos()
        dist = (target - self.root.getPos()).length()
        if dist < 50.0 and player.alive:
            self.state = "chase"
            self.face(target, dt, 130.0)
            self.move_toward(target, dt, self.speed, stop_at=2.4)
            self.model.setR(math.sin(self.t * 3.0) * 7.0)
            self.model.setZ(abs(math.sin(self.t * 3.0)) * 0.12)
            # It sheds constantly, which is how you spot one in the dark.
            if _rng.random() < dt * 3.0:
                effects.burst(self.root.getPos() + Vec3(0, 0, 1.2),
                              self.bile, 1, 1.6, 0.18, gravity=-6.0)
        else:
            self.state = "idle"
            self.model.setR(math.sin(self.t * 1.0) * 3.0)
        self.touch_player(dt, player)


KINDS = {
    "creeper": Creeper,
    "ghoul": Ghoul,
    "wisp": Wisp,
    "troll": Troll,
    "decay": DecayBeast,
    "knut": Knut,
    "icy": Icy,
    "darcy": Darcy,
    "stormy": Stormy,
}


def spawn(kind: str, parent: NodePath, pos: Vec3, solids) -> Enemy:
    return KINDS[kind](parent, pos, solids)
