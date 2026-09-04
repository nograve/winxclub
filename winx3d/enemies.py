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


class Witch(Enemy):
    """Boss. Three phases: volleys, summons, then a homing barrage."""

    name = "witch"
    max_health = 40.0
    radius = 2.0
    speed = 8.0
    touch_damage = 2.0
    score = 2000
    hit_color = Vec4(0.55, 0.75, 1.0, 1)
    flying = True
    eye_height = 0.0
    is_boss = True

    robe = Vec4(0.30, 0.36, 0.62, 1)
    ice = Vec4(0.60, 0.85, 1.0, 1)
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
        if self.phase == 1:
            # Three-shot spread.
            self.pattern_cd = 1.9
            for i in (-1, 0, 1):
                dirn = Vec3(d)
                dirn.normalize()
                ang = math.radians(i * 10.0)
                ca, sa = math.cos(ang), math.sin(ang)
                dirn = Vec3(dirn.x * ca - dirn.y * sa,
                            dirn.x * sa + dirn.y * ca, dirn.z)
                effects.spawn_bolt(self.root.getPos(), dirn, 26.0, self.ice,
                                   1.0, True, radius=0.45, life=2.4)
        elif self.phase == 2:
            # Ring of shards plus a call for reinforcements.
            self.pattern_cd = 2.6
            for i in range(10):
                a = math.tau * i / 10
                effects.spawn_bolt(self.root.getPos(),
                                   Vec3(math.cos(a), math.sin(a), -0.15),
                                   19.0, self.ice, 1.0, True, radius=0.4,
                                   life=2.6)
            self.summon_request += 1
        else:
            # Homing barrage — the player has to keep moving.
            self.pattern_cd = 2.2
            for i in range(3):
                jitter = Vec3(_rng.uniform(-1, 1), _rng.uniform(-1, 1), 0.2)
                effects.spawn_bolt(self.root.getPos(), d + jitter * 4.0, 20.0,
                                   Vec4(0.75, 0.55, 1.0, 1), 1.0, True,
                                   radius=0.42, life=3.0, homing=1.9,
                                   target=player)
        effects.burst(self.root.getPos(), self.ice, 8, 5.0, 0.35)


KINDS = {
    "creeper": Creeper,
    "wisp": Wisp,
    "troll": Troll,
    "witch": Witch,
}


def spawn(kind: str, parent: NodePath, pos: Vec3, solids) -> Enemy:
    return KINDS[kind](parent, pos, solids)
