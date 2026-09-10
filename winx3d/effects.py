"""Projectiles, impact bursts and pickups.

These use analytic sphere/box tests rather than Panda3D's collision traverser.
There are only ever a few dozen of them and the maths is trivial, so this
avoids paying traverser overhead every frame on slow CPUs.
"""
from __future__ import annotations

import math
import random

from panda3d.core import (NodePath, TransparencyAttrib, Vec3, Vec4)

from .geometry import MeshBuilder, shade

_rng = random.Random(7)


def _glow_model(color: Vec4, radius: float) -> NodePath:
    """A bolt: solid core inside a translucent halo."""
    mb = MeshBuilder()
    mb.sphere((0, 0, 0), radius * 0.55, Vec4(
        min(1.0, color[0] + 0.35), min(1.0, color[1] + 0.35),
        min(1.0, color[2] + 0.35), 1.0), segments=8, rings=6)
    core = mb.build("bolt_core")
    mb2 = MeshBuilder()
    mb2.sphere((0, 0, 0), radius, Vec4(color[0], color[1], color[2], 0.45),
               segments=8, rings=6)
    halo = mb2.build("bolt_halo")
    halo.setTransparency(TransparencyAttrib.MAlpha)
    halo.setDepthWrite(False)
    halo.setTwoSided(True)
    root = NodePath("bolt")
    core.reparentTo(root)
    halo.reparentTo(root)
    root.setLightOff()
    return root


class Projectile:
    __slots__ = ("np", "vel", "life", "damage", "radius", "hostile", "dead",
                 "spin", "homing", "target")

    def __init__(self, np: NodePath, vel: Vec3, life: float, damage: float,
                 radius: float, hostile: bool) -> None:
        self.np = np
        self.vel = vel
        self.life = life
        self.damage = damage
        self.radius = radius
        self.hostile = hostile
        self.dead = False
        self.spin = _rng.uniform(180, 520)
        self.homing = 0.0
        self.target = None


class Particle:
    __slots__ = ("np", "vel", "life", "max_life", "scale0", "gravity", "spin")

    def __init__(self, np, vel, life, scale0, gravity, spin) -> None:
        self.np = np
        self.vel = vel
        self.life = life
        self.max_life = life
        self.scale0 = scale0
        self.gravity = gravity
        self.spin = spin


class EffectSystem:
    """Owns every projectile and particle in the scene."""

    MAX_PARTICLES = 160

    def __init__(self, parent: NodePath) -> None:
        self.root = parent.attachNewNode("effects")
        self.projectiles: list[Projectile] = []
        self.particles: list[Particle] = []
        self._bolt_cache: dict[tuple, NodePath] = {}
        self._spark_cache: dict[tuple, NodePath] = {}
        self.solids: list[tuple[Vec3, Vec3]] = []
        # Interactables hit by a bolt this frame; the game applies them after
        # the projectile pass so a puzzle cannot mutate the list mid-iteration.
        self.pending_shots: list = []

    # -- construction -------------------------------------------------------
    def set_solids(self, boxes) -> None:
        self.solids = boxes

    def _bolt_proto(self, color: Vec4, radius: float) -> NodePath:
        key = (round(color[0], 2), round(color[1], 2), round(color[2], 2),
               round(radius, 2))
        proto = self._bolt_cache.get(key)
        if proto is None:
            proto = _glow_model(color, radius)
            self._bolt_cache[key] = proto
        return proto

    def _spark_proto(self, color: Vec4) -> NodePath:
        key = (round(color[0], 2), round(color[1], 2), round(color[2], 2))
        proto = self._spark_cache.get(key)
        if proto is None:
            mb = MeshBuilder()
            mb.box((0, 0, 0), (0.34, 0.34, 0.34), color)
            proto = mb.build("spark")
            proto.setLightOff()
            self._spark_cache[key] = proto
        return proto

    # -- spawning -----------------------------------------------------------
    def spawn_bolt(self, pos: Vec3, direction: Vec3, speed: float,
                   color: Vec4, damage: float, hostile: bool,
                   radius: float = 0.45, life: float = 1.6,
                   homing: float = 0.0, target=None) -> Projectile:
        np = self._bolt_proto(color, radius).copyTo(self.root)
        np.setPos(pos)
        d = Vec3(direction)
        if d.lengthSquared() < 1e-8:
            d = Vec3(0, 1, 0)
        d.normalize()
        p = Projectile(np, d * speed, life, damage, radius, hostile)
        p.homing = homing
        p.target = target
        self.projectiles.append(p)
        return p

    def burst(self, pos: Vec3, color: Vec4, count: int = 10,
              speed: float = 7.0, scale: float = 0.5,
              gravity: float = -14.0) -> None:
        room = self.MAX_PARTICLES - len(self.particles)
        if room <= 0:
            return
        proto = self._spark_proto(color)
        for _ in range(min(count, room)):
            np = proto.copyTo(self.root)
            np.setPos(pos)
            s = scale * _rng.uniform(0.6, 1.4)
            np.setScale(s)
            v = Vec3(_rng.uniform(-1, 1), _rng.uniform(-1, 1),
                     _rng.uniform(-0.2, 1.2))
            if v.lengthSquared() < 1e-6:
                v = Vec3(0, 0, 1)
            v.normalize()
            self.particles.append(Particle(
                np, v * (speed * _rng.uniform(0.5, 1.3)),
                _rng.uniform(0.35, 0.8), s, gravity,
                _rng.uniform(-700, 700)))

    def ring(self, pos: Vec3, color: Vec4, radius: float, count: int = 20)\
            -> None:
        """Flat expanding ring — used for the charged blast and transforming."""
        room = self.MAX_PARTICLES - len(self.particles)
        proto = self._spark_proto(color)
        for i in range(min(count, max(0, room))):
            a = math.tau * i / count
            np = proto.copyTo(self.root)
            np.setPos(pos)
            np.setScale(0.6)
            self.particles.append(Particle(
                np, Vec3(math.cos(a), math.sin(a), 0.15) * (radius * 1.6),
                0.5, 0.6, -2.0, 0.0))

    # -- simulation ---------------------------------------------------------
    def _hits_solid(self, pos: Vec3, radius: float) -> bool:
        for center, half in self.solids:
            if (abs(pos.x - center.x) < half.x + radius and
                    abs(pos.y - center.y) < half.y + radius and
                    abs(pos.z - center.z) < half.z + radius):
                return True
        return False

    def update(self, dt: float, player, enemies, interactables=()) -> None:
        self._update_projectiles(dt, player, enemies, interactables)
        self._update_particles(dt)

    def _update_projectiles(self, dt, player, enemies,
                            interactables=()) -> None:
        alive = []
        for p in self.projectiles:
            p.life -= dt
            if p.life <= 0.0 or p.dead:
                p.np.removeNode()
                continue
            if p.homing > 0.0 and p.target is not None and p.target.alive:
                want = p.target.center() - p.np.getPos()
                if want.lengthSquared() > 1e-6:
                    want.normalize()
                    speed = p.vel.length()
                    p.vel = p.vel + want * (p.homing * dt * speed)
                    p.vel.normalize()
                    p.vel *= speed
            pos = p.np.getPos() + p.vel * dt
            p.np.setPos(pos)
            p.np.setH(p.np.getH() + p.spin * dt)

            if self._hits_solid(pos, p.radius * 0.5):
                self.burst(pos, Vec4(0.9, 0.9, 0.95, 1), 5, 4.0, 0.28)
                p.np.removeNode()
                continue

            hit = False
            if p.hostile:
                if player is not None and player.alive and \
                        (pos - player.center()).length() < p.radius + player.radius:
                    player.take_damage(p.damage)
                    self.burst(pos, Vec4(1.0, 0.4, 0.4, 1), 8, 6.0, 0.32)
                    hit = True
            else:
                for e in enemies:
                    if not e.alive:
                        continue
                    if (pos - e.center()).length() < p.radius + e.radius:
                        e.take_damage(p.damage, self)
                        self.burst(pos, e.hit_color, 9, 6.5, 0.34)
                        hit = True
                        break
                if not hit:
                    # Some puzzle objects are lit by hitting them with magic.
                    for it in interactables:
                        if not it.shootable or it.solved:
                            continue
                        if (pos - it.center()).length() < p.radius + 2.2:
                            self.pending_shots.append(it)
                            hit = True
                            break
            if hit:
                p.np.removeNode()
                continue
            alive.append(p)
        self.projectiles = alive

    def _update_particles(self, dt) -> None:
        alive = []
        for q in self.particles:
            q.life -= dt
            if q.life <= 0.0:
                q.np.removeNode()
                continue
            q.vel.z += q.gravity * dt
            q.np.setPos(q.np.getPos() + q.vel * dt)
            if q.spin:
                q.np.setHpr(q.np.getH() + q.spin * dt,
                            q.np.getP() + q.spin * 0.7 * dt, 0)
            k = q.life / q.max_life
            q.np.setScale(max(0.02, q.scale0 * k))
            alive.append(q)
        self.particles = alive

    def clear(self) -> None:
        for p in self.projectiles:
            p.np.removeNode()
        for q in self.particles:
            q.np.removeNode()
        self.projectiles.clear()
        self.particles.clear()


class Pickup:
    """A collectible gem or heart that bobs and spins in place."""

    def __init__(self, parent: NodePath, pos: Vec3, kind: str) -> None:
        self.kind = kind
        self.taken = False
        self.base_z = pos.z
        self.phase = _rng.uniform(0, math.tau)
        mb = MeshBuilder()
        if kind == "gem":
            self.color = Vec4(0.55, 0.85, 1.0, 1)
            mb.cylinder((0, 0, -0.45), 0.0, 0.42, 0.45, self.color, segments=8,
                        cap_top=False)
            mb.cylinder((0, 0, 0.0), 0.42, 0.0, 0.62, shade(self.color, 1.2),
                        segments=8, cap_bottom=False)
            self.radius = 1.2
        else:
            self.color = Vec4(1.0, 0.38, 0.52, 1)
            for sx in (-0.22, 0.22):
                mb.sphere((sx, 0, 0.22), 0.32, self.color, segments=8, rings=6)
            mb.cylinder((0, 0, -0.55), 0.0, 0.42, 0.62,
                        shade(self.color, 0.9), segments=8, cap_top=False)
            self.radius = 1.3
        self.np = mb.build("pickup_" + kind)
        self.np.reparentTo(parent)
        self.np.setPos(pos)
        self.np.setLightOff()

    def update(self, dt: float, t: float) -> None:
        if self.taken:
            return
        self.np.setZ(self.base_z + math.sin(t * 2.4 + self.phase) * 0.35)
        self.np.setH(self.np.getH() + 110.0 * dt)

    def collect(self) -> None:
        self.taken = True
        self.np.removeNode()
