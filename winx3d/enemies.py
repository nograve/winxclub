"""Enemy types and their AI.

Each enemy is a small state machine (idle -> chase -> attack -> hurt -> dead).
Ground enemies snap to the terrain height sampled from the level's solid
boxes; flyers hold an altitude band around the player.
"""
from __future__ import annotations

import math
import random

from panda3d.core import NodePath, TransparencyAttrib, Vec3, Vec4

from .geometry import MeshBuilder, shade

_rng = random.Random(3)


def ground_height(solids, x: float, y: float, from_z: float) -> float:
    """Highest solid top under (x, y) at or below ``from_z``; else 0."""
    best = 0.0
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
        mb.sphere((0, 0, 0), 0.62, self.core, segments=10, rings=8)
        halo = MeshBuilder()
        halo.sphere((0, 0, 0), 1.05, Vec4(self.core[0], self.core[1],
                                          self.core[2], 0.30),
                    segments=10, rings=7)
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
        mb.cylinder((0, 0, 0.0), 0.55, 0.42, 1.25, self.hide, segments=9)
        mb.box((0, 0, 1.05), (1.1, 0.8, 0.5), self.cloth)
        mb.sphere((0, 0, 2.05), 1.15, self.hide, segments=11, rings=8,
                  squash=0.9)
        mb.sphere((0, 0, 3.05), 0.72, self.hide, segments=10, rings=7)
        for sx in (-0.26, 0.26):
            mb.sphere((sx, -0.60, 3.10), 0.13, Vec4(0.95, 0.25, 0.2, 1),
                      segments=6, rings=5)
        mb.cylinder((0, -0.55, 2.85), 0.28, 0.20, 0.45, shade(self.hide, 0.85),
                    segments=7)
        arm = MeshBuilder()
        for sx in (-1.35, 1.35):
            arm.sphere((sx, 0, 2.35), 0.42, self.hide, segments=8, rings=6)
            arm.cylinder((sx, 0, 1.0), 0.34, 0.42, 1.35, self.hide, segments=8)
            arm.sphere((sx, 0, 0.95), 0.48, shade(self.hide, 0.9),
                       segments=8, rings=6)
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

    def build_model(self) -> None:
        mb = MeshBuilder()
        mb.cylinder((0, 0, -2.4), 0.0, 1.5, 2.6, self.robe, segments=14,
                    cap_top=False)                                 # trailing gown
        mb.cylinder((0, 0, 0.2), 0.75, 0.55, 0.9, shade(self.robe, 1.15),
                    segments=12)
        mb.sphere((0, 0, 1.55), 0.55, Vec4(0.92, 0.86, 0.88, 1), segments=12,
                  rings=9)
        mb.sphere((0, 0.1, 1.75), 0.60, self.hair, segments=12, rings=9,
                  squash=1.05)
        for sx in (-1, 1):
            mb.cylinder((sx * 0.42, 0.18, 1.55), 0.16, 0.05, -1.5, self.hair,
                        segments=7)
            mb.sphere((sx * 0.21, -0.45, 1.58), 0.10,
                      Vec4(0.15, 0.35, 0.6, 1), segments=6, rings=5)
            mb.cylinder((sx * 0.72, 0, 1.05), 0.16, 0.12, -1.0,
                        shade(self.robe, 1.2), segments=7)
        # Ice shards orbiting her — the boss's silhouette read.
        shards = MeshBuilder()
        for i in range(6):
            a = math.tau * i / 6
            shards.cylinder((math.cos(a) * 2.6, math.sin(a) * 2.6, -0.4),
                            0.30, 0.0, 1.6, Vec4(self.ice[0], self.ice[1],
                                                 self.ice[2], 0.75),
                            segments=6)
        s = shards.build("witch_shards")
        s.setTransparency(TransparencyAttrib.MAlpha)
        s.setLightOff()
        s.reparentTo(self.model)
        self.parts["shards"] = s
        mb.build("witch_mesh").reparentTo(self.model)

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
    hair = Vec4(0.48, 0.34, 0.62, 1)
    hit_color = Vec4(0.66, 0.42, 0.92, 1)

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
    hair = Vec4(0.70, 0.30, 0.55, 1)
    hit_color = Vec4(0.96, 0.56, 0.88, 1)

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

    robe = Vec4(0.26, 0.22, 0.34, 1)
    bone = Vec4(0.72, 0.70, 0.62, 1)
    glow = Vec4(0.85, 0.35, 0.95, 1)

    def build_model(self) -> None:
        mb = MeshBuilder()
        # Hooded, hunched, and deliberately taller than it is wide.
        mb.cylinder((0, 0, 0.0), 0.30, 0.52, 1.55, self.robe, segments=9)
        mb.cylinder((0, 0, 1.55), 0.52, 0.30, 0.45, shade(self.robe, 1.15),
                    segments=9)
        mb.sphere((0, 0, 1.92), 0.34, self.bone, segments=9, rings=7)
        mb.sphere((0, -0.06, 2.02), 0.37, shade(self.robe, 0.85), segments=10,
                  rings=7, squash=0.95)                       # hood
        for sx in (-0.13, 0.13):
            mb.sphere((sx, -0.26, 1.92), 0.075, self.glow, segments=6, rings=5)
        for sx in (-1, 1):
            mb.cylinder((sx * 0.40, 0, 1.45), 0.12, 0.07, -0.95, self.robe,
                        segments=6)
            mb.sphere((sx * 0.46, 0, 0.50), 0.13, self.bone, segments=6,
                      rings=5)
        m = mb.build("ghoul_mesh")
        m.reparentTo(self.model)

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
        for sx in (-0.55, 0.55):
            mb.cylinder((sx, 0, 0.0), 0.42, 0.36, 1.30, self.hide, segments=8)
            mb.sphere((sx, -0.1, 0.05), 0.44, shade(self.hide, 0.9),
                      segments=8, rings=6, squash=0.7)
        mb.cylinder((0, 0, 1.15), 1.25, 1.05, 1.45, self.hide, segments=11)
        mb.box((0, 0, 1.35), (2.7, 1.5, 0.42), self.cloth)         # belt
        mb.sphere((0, 0, 2.75), 1.05, self.hide, segments=11, rings=8,
                  squash=0.92)
        mb.sphere((0, -0.35, 2.60), 0.62, shade(self.hide, 1.06), segments=9,
                  rings=7, squash=0.8)                             # snout
        for sx in (-0.3, 0.3):
            mb.sphere((sx, -0.72, 2.82), 0.15, Vec4(0.95, 0.80, 0.25, 1),
                      segments=6, rings=5)
            mb.cylinder((sx, -0.62, 2.42), 0.11, 0.0, 0.55, self.tusk,
                        segments=6)                                # tusks
            mb.cylinder((sx * 0.9, 0.5, 3.35), 0.16, 0.0, 0.5,
                        shade(self.hide, 0.8), segments=6)         # ears
        arm = MeshBuilder()
        for sx in (-1.7, 1.7):
            arm.sphere((sx, 0, 2.60), 0.52, self.hide, segments=8, rings=6)
            arm.cylinder((sx, 0, 1.05), 0.40, 0.50, 1.60, self.hide,
                         segments=8)
            arm.sphere((sx, 0, 0.98), 0.58, shade(self.hide, 0.92),
                       segments=8, rings=6)
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

    rot = Vec4(0.34, 0.36, 0.24, 1)
    bile = Vec4(0.62, 0.72, 0.30, 1)

    def build_model(self) -> None:
        mb = MeshBuilder()
        # Lopsided on purpose: nothing in the Army of Decay is symmetrical.
        mb.cylinder((0, 0, 0.0), 0.70, 0.95, 1.20, self.rot, segments=9)
        mb.sphere((0, 0, 1.75), 1.15, self.rot, segments=10, rings=8,
                  squash=0.85)
        mb.sphere((0.35, -0.2, 2.35), 0.62, shade(self.rot, 1.15), segments=9,
                  rings=7)
        for sx, sz, r in ((-0.75, 2.15, 0.30), (0.55, 2.75, 0.22),
                          (-0.30, 2.60, 0.26)):
            mb.sphere((sx, -0.35, sz), r, self.bile, segments=7, rings=5)
        for sx in (-1, 1):
            mb.cylinder((sx * 1.05, 0.1, 1.70), 0.26, 0.10, -1.30,
                        shade(self.rot, 0.88), segments=7)
            mb.cylinder((sx * 0.45, 0, 0.0), 0.26, 0.20, -0.05,
                        shade(self.rot, 0.8), segments=6)
        m = mb.build("decay_mesh")
        m.reparentTo(self.model)

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
