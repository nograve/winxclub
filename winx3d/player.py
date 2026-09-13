"""The player fairy: movement, flight, combat and the third-person camera.

Collision is resolved analytically against the level's axis-aligned solid
boxes.  Vertical motion is resolved first (so landing on a platform is exact),
then horizontal overlaps are pushed out along the shallowest axis.  This is
both simpler and cheaper than running Panda3D's traverser every frame.
"""
from __future__ import annotations

import math

from panda3d.core import NodePath, Vec3

from . import config as C
from .characters import Fairy, FairyAnimator, build_fairy

STEP_UP = 0.6          # how tall a lip the player can walk straight over


class Player:
    def __init__(self, parent: NodePath, spec: Fairy, solids,
                 start: Vec3) -> None:
        self.spec = spec
        self.solids = solids
        self.radius = C.PLAYER_RADIUS
        self.height = C.PLAYER_HEIGHT

        self.root = NodePath("player")
        self.root.reparentTo(parent)
        self.root.setPos(start)
        model, parts = build_fairy(spec, scale=0.95)
        model.reparentTo(self.root)
        self.model = model
        self.parts = parts
        self.anim = FairyAnimator(parts)

        # State
        self.vel = Vec3(0, 0, 0)
        self.heading = 0.0
        self.grounded = False
        self.flying = False
        self.alive = True
        self.health = C.MAX_HEALTH
        self.magic = C.MAX_MAGIC
        self.lives = C.START_LIVES
        self.score = 0
        self.gems = 0
        self.invuln = 0.0
        self.shoot_cd = 0.0
        self.charge_cd = 0.0
        self.transform_time = 0.0
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.was_flying = False
        self.blink_t = 0.0

        # Camera rig: yaw pivot -> pitch pivot -> camera mount.
        self.cam_yaw = 0.0
        self.cam_pitch = C.CAM_PITCH
        # The camera's real position and view direction, refreshed every
        # frame. Aiming needs the actual ray, not just the orbit angles.
        self.cam_pos = Vec3(start) + Vec3(0, -C.CAM_DISTANCE, C.CAM_HEIGHT)
        self.cam_dir = Vec3(0, 1, 0)
        self.lock_target = None
        self.audio = None          # set by the game once it owns the player
        # Where a fall puts you back. The game moves this forward as you
        # pass the course's checkpoints.
        self.respawn_point = Vec3(start)
        self.fall_z = -25.0
        self.focus = NodePath("cam_focus")
        self.focus.reparentTo(parent)
        self.focus.setPos(start + Vec3(0, 0, 2.2))

    # -- queries ------------------------------------------------------------
    def center(self) -> Vec3:
        return self.root.getPos() + Vec3(0, 0, self.height * 0.5)

    @property
    def transformed(self) -> bool:
        return self.transform_time > 0.0

    @property
    def damage_mult(self) -> float:
        return self.spec.power * (1.7 if self.transformed else 1.0)

    # -- collision ----------------------------------------------------------
    NO_GROUND = -1.0e9

    def _support_height(self, x: float, y: float, from_z: float) -> float:
        """Top of the highest solid under the player's circle, at/below head.

        Returns ``NO_GROUND`` when there is nothing underfoot.  Defaulting to
        zero would put an invisible floor at z=0 across the whole world, which
        on a course floating over open sky means you never actually fall.
        """
        best = self.NO_GROUND
        r = self.radius
        for center, half in self.solids:
            if (abs(x - center.x) <= half.x + r and
                    abs(y - center.y) <= half.y + r):
                top = center.z + half.z
                if top <= from_z + STEP_UP and top > best:
                    best = top
        return best

    def _ceiling(self, x: float, y: float, z: float) -> float | None:
        """Bottom of the lowest solid directly above the player's head."""
        best = None
        r = self.radius
        head = z + self.height
        for center, half in self.solids:
            if (abs(x - center.x) <= half.x + r and
                    abs(y - center.y) <= half.y + r):
                bottom = center.z - half.z
                if bottom >= head - 0.05 and (best is None or bottom < best):
                    best = bottom
        return best

    def _push_out(self, pos: Vec3) -> Vec3:
        """Resolve XY overlap with any solid whose height band we occupy."""
        r = self.radius
        lo, hi = pos.z + 0.35, pos.z + self.height
        for center, half in self.solids:
            if center.z + half.z <= lo or center.z - half.z >= hi:
                continue
            dx = pos.x - center.x
            dy = pos.y - center.y
            ox = half.x + r - abs(dx)
            oy = half.y + r - abs(dy)
            if ox <= 0.0 or oy <= 0.0:
                continue
            # Push along whichever axis needs the least correction.
            if ox < oy:
                pos.x = center.x + math.copysign(half.x + r, dx or 1.0)
            else:
                pos.y = center.y + math.copysign(half.y + r, dy or 1.0)
        return pos

    # -- input handling -----------------------------------------------------
    def update(self, dt: float, keys: dict, effects, enemies) -> None:
        if not self.alive:
            return
        self.invuln = max(0.0, self.invuln - dt)
        self.shoot_cd = max(0.0, self.shoot_cd - dt)
        self.charge_cd = max(0.0, self.charge_cd - dt)
        if self.transform_time > 0.0:
            self.transform_time = max(0.0, self.transform_time - dt)
            if self.transform_time == 0.0:
                self.end_transform(effects)

        self._move(dt, keys)
        self._combat(dt, keys, effects, enemies)

        speed = Vec3(self.vel.x, self.vel.y, 0).length()
        self.anim.update(dt, speed, self.flying, self.grounded)
        self._blink(dt)

    def _move(self, dt: float, keys: dict) -> None:
        # Desired direction in world space, relative to where the camera looks.
        fx = (1.0 if keys.get("forward") else 0.0) - \
             (1.0 if keys.get("back") else 0.0)
        sx = (1.0 if keys.get("right") else 0.0) - \
             (1.0 if keys.get("left") else 0.0)
        yaw = math.radians(self.cam_yaw)
        fwd = Vec3(-math.sin(yaw), math.cos(yaw), 0)
        rgt = Vec3(math.cos(yaw), math.sin(yaw), 0)
        wish = fwd * fx + rgt * sx
        if wish.lengthSquared() > 1e-6:
            wish.normalize()
            self.heading = math.degrees(math.atan2(-wish.x, wish.y))

        running = bool(keys.get("run"))
        base = C.FLY_SPEED if self.flying else (
            C.RUN_SPEED if running else C.WALK_SPEED)
        target = wish * (base * self.spec.speed *
                         (1.15 if self.transformed else 1.0))

        # Ground movement is snappy; air control is deliberately looser.
        blend = min(1.0, dt * (14.0 if self.grounded else 6.0))
        self.vel.x += (target.x - self.vel.x) * blend
        self.vel.y += (target.y - self.vel.y) * blend

        # --- vertical: jump, flight, gravity -------------------------------
        self.jump_buffer = max(0.0, self.jump_buffer - dt)
        if keys.get("jump_pressed"):
            self.jump_buffer = C.JUMP_BUFFER
            keys["jump_pressed"] = False

        holding_jump = bool(keys.get("jump"))
        can_fly = self.transformed or self.magic > 0.0

        if self.grounded:
            self.coyote = C.COYOTE_TIME
            self.flying = False
        else:
            self.coyote = max(0.0, self.coyote - dt)

        if self.jump_buffer > 0.0 and (self.grounded or self.coyote > 0.0):
            if self.audio is not None:
                self.audio.play("jump", 0.5)
            self.vel.z = C.JUMP_SPEED
            self.grounded = False
            self.coyote = 0.0
            self.jump_buffer = 0.0
        elif holding_jump and not self.grounded and can_fly:
            # Wings out: hold to climb, release to glide.
            self.flying = True
            self.vel.z += (C.FLY_LIFT - self.vel.z) * min(1.0, dt * 7.0)
            if not self.transformed:
                self.magic = max(0.0, self.magic - C.FLY_DRAIN * dt)
        else:
            if not holding_jump:
                self.flying = False

        if not self.flying:
            self.vel.z += C.GRAVITY * dt
            if not self.grounded and holding_jump and can_fly:
                self.vel.z = max(self.vel.z, C.FLY_FALL_CLAMP)
        self.vel.z = max(self.vel.z, -34.0)

        # --- integrate + resolve -------------------------------------------
        pos = self.root.getPos()
        prev_z = pos.z

        pos.z += self.vel.z * dt
        support = self._support_height(pos.x, pos.y, prev_z)
        if self.vel.z <= 0.0 and pos.z <= support:
            pos.z = support
            self.vel.z = 0.0
            self.grounded = True
            self.flying = False
        else:
            self.grounded = False
            ceil = self._ceiling(pos.x, pos.y, pos.z)
            if ceil is not None and self.vel.z > 0.0 and \
                    pos.z + self.height > ceil:
                pos.z = ceil - self.height
                self.vel.z = 0.0

        pos.x += self.vel.x * dt
        pos.y += self.vel.y * dt
        pos = self._push_out(pos)

        # Walking off a ledge keeps you grounded until the drop is real.
        if self.grounded:
            support = self._support_height(pos.x, pos.y, pos.z)
            if abs(pos.z - support) < STEP_UP:
                pos.z = support
            else:
                self.grounded = False

        if pos.z < self.fall_z:               # fell off the course
            self.take_damage(1.0, force=True)
            pos = Vec3(self.respawn_point) + Vec3(0, 0, 1.0)
            self.vel = Vec3(0, 0, 0)
            self.grounded = False

        self.root.setPos(pos)

        # Turn the model toward its heading rather than snapping.
        cur = self.model.getH()
        diff = (self.heading - cur + 180.0) % 360.0 - 180.0
        self.model.setH(cur + max(-C.TURN_RATE * dt,
                                  min(C.TURN_RATE * dt, diff)))

        regen = C.MAGIC_REGEN * self.spec.magic_rate
        if self.transformed:
            regen *= 0.0                      # meter is spent while transformed
        elif self.flying:
            regen = 0.0
        self.magic = min(C.MAX_MAGIC, self.magic + regen * dt)

    # -- combat -------------------------------------------------------------
    @property
    def aim_pitch(self) -> float:
        """Firing pitch, in degrees, decoupled from the camera's own tilt.

        The camera sits above and behind the fairy and looks *down* at her, so
        its pitch is not where a shot from her hands should go - fired from
        chest height along that tilt, a bolt hits the ground a couple of paces
        ahead.  Worse, the camera pulls in when a wall is behind you, which
        would make the aim dive at exactly the wrong moment.  So neutral
        camera pitch means a level shot, and looking up or down moves the aim
        by the same amount.
        """
        return max(-60.0, min(60.0, self.cam_pitch - C.CAM_PITCH))

    def aim_direction(self, enemies) -> Vec3:
        """From the chest along the aim pitch, snapping to a locked target."""
        pitch = math.radians(self.aim_pitch)
        yaw = math.radians(self.cam_yaw)
        aim = Vec3(-math.sin(yaw) * math.cos(pitch),
                   math.cos(yaw) * math.cos(pitch),
                   math.sin(pitch))
        aim.normalize()
        origin = self.center() + Vec3(0, 0, 0.35)

        # Gather every enemy inside the assist cone, then lock the *nearest*
        # of them.  Picking the best-aligned one instead would let a distant
        # enemy that happens to line up steal the shot from the one the
        # player is standing in front of.
        best, best_dist = None, 1e9
        self.lock_target = None
        for e in enemies:
            if not e.alive:
                continue
            d = e.center() - origin
            dist = d.length()
            if dist > 45.0 or dist < 1e-3:
                continue
            d /= dist
            if d.dot(aim) > 0.80 and dist < best_dist:
                best, best_dist = d, dist
                self.lock_target = e
        if best is not None:
            # Commit to the locked target rather than blending part-way toward
            # it: a half-aimed bolt just misses, which reads as the game
            # ignoring the shot.
            aim = best
        return aim

    def aim_point(self, enemies, distance: float = 35.0) -> Vec3:
        """The world point the shot is heading for - what the reticle marks."""
        if self.lock_target is not None and self.lock_target.alive:
            return self.lock_target.center()
        origin = self.center() + Vec3(0, 0, 0.35)
        return origin + self.aim_direction(enemies) * distance

    def _combat(self, dt, keys, effects, enemies) -> None:
        free = self.transformed
        if keys.get("attack") and self.shoot_cd <= 0.0:
            cost = 0.0 if free else C.BOLT_COST
            if self.magic >= cost:
                self.magic -= cost
                self.shoot_cd = 0.22 if not free else 0.14
                self._fire(effects, enemies)
        if keys.get("special") and self.charge_cd <= 0.0:
            cost = 0.0 if free else C.CHARGE_COST
            if self.magic >= cost:
                self.magic -= cost
                self.charge_cd = 1.1
                self._blast(effects, enemies)
        if keys.get("transform_pressed"):
            keys["transform_pressed"] = False
            if not self.transformed and self.magic >= C.TRANSFORM_COST:
                self.begin_transform(effects)

    def _fire(self, effects, enemies) -> None:
        self.anim.trigger_attack()
        if self.audio is not None:
            self.audio.play_variant("shoot", self.spec.key)
        aim = self.aim_direction(enemies)
        origin = self.center() + aim * 1.2 + Vec3(0, 0, 0.3)
        n = self.spec.bolts
        for i in range(n):
            offset = (i - (n - 1) * 0.5) * self.spec.spread
            ang = math.radians(offset)
            ca, sa = math.cos(ang), math.sin(ang)
            d = Vec3(aim.x * ca - aim.y * sa, aim.x * sa + aim.y * ca, aim.z)
            effects.spawn_bolt(origin, d, C.BOLT_SPEED, self.spec.magic,
                               C.BOLT_DAMAGE * self.damage_mult, False,
                               radius=0.42 if not self.transformed else 0.6,
                               life=C.BOLT_LIFE)
        effects.burst(origin, self.spec.magic, 4, 3.0, 0.22, gravity=-2.0)

    def _blast(self, effects, enemies) -> None:
        """Close-range shockwave — the panic button when something closes in."""
        self.anim.trigger_attack()
        c = self.center()
        effects.ring(c, self.spec.magic, C.CHARGE_RADIUS, 24)
        effects.burst(c, self.spec.accent, 18, 10.0, 0.5, gravity=-4.0)
        dmg = C.CHARGE_DAMAGE * self.damage_mult
        for e in enemies:
            if not e.alive:
                continue
            d = (e.center() - c).length()
            if d < C.CHARGE_RADIUS + e.radius:
                falloff = max(0.35, 1.0 - d / (C.CHARGE_RADIUS + e.radius))
                e.take_damage(dmg * falloff, effects)

    # -- transformation -----------------------------------------------------
    def begin_transform(self, effects) -> None:
        if self.audio is not None:
            self.audio.play("transform")
        self.magic = 0.0
        self.transform_time = C.TRANSFORM_TIME
        self.parts["aura"].show()
        self.model.setColorScale(1.35, 1.30, 1.45, 1.0)
        c = self.center()
        effects.ring(c, self.spec.magic, 10.0, 28)
        effects.burst(c, self.spec.accent, 40, 12.0, 0.55, gravity=-3.0)

    def end_transform(self, effects) -> None:
        self.parts["aura"].hide()
        self.model.clearColorScale()
        effects.burst(self.center(), self.spec.magic, 12, 6.0, 0.35)

    # -- damage / death -----------------------------------------------------
    def take_damage(self, amount: float, force: bool = False) -> bool:
        if not self.alive or (self.invuln > 0.0 and not force):
            return False
        if self.transformed and not force:
            amount *= 0.5           # Enchantix soaks half of everything
        self.health -= amount
        self.invuln = C.INVULN_TIME
        if self.audio is not None:
            self.audio.play("hurt")
        if self.health <= 0.0:
            self.health = 0.0
            self.alive = False
        return True

    def respawn(self, pos: Vec3) -> None:
        self.alive = True
        self.health = C.MAX_HEALTH
        self.magic = C.MAX_MAGIC * 0.5
        self.transform_time = 0.0
        self.parts["aura"].hide()
        self.model.clearColorScale()
        self.model.show()
        self.vel = Vec3(0, 0, 0)
        self.invuln = C.INVULN_TIME * 2.0
        self.root.setPos(pos)

    def _blink(self, dt: float) -> None:
        """Flicker the model during invulnerability frames."""
        if self.invuln > 0.0:
            self.blink_t += dt
            if int(self.blink_t * 14.0) % 2 == 0:
                self.model.hide()
            else:
                self.model.show()
        else:
            self.blink_t = 0.0
            self.model.show()

    # -- camera -------------------------------------------------------------
    def orbit_camera(self, dyaw: float, dpitch: float) -> None:
        self.cam_yaw = (self.cam_yaw + dyaw) % 360.0
        self.cam_pitch = max(C.CAM_MIN_PITCH,
                             min(C.CAM_MAX_PITCH, self.cam_pitch + dpitch))

    def update_camera(self, camera: NodePath, dt: float) -> None:
        want = self.root.getPos() + Vec3(0, 0, 2.2)
        cur = self.focus.getPos()
        self.focus.setPos(cur + (want - cur) * min(1.0, dt * C.CAM_LAG))

        focus = self.focus.getPos()
        yaw = math.radians(self.cam_yaw)
        pitch = math.radians(self.cam_pitch)
        back = Vec3(math.sin(yaw) * math.cos(pitch),
                    -math.cos(yaw) * math.cos(pitch),
                    -math.sin(pitch))
        dist = self._camera_distance(focus, back, C.CAM_DISTANCE)
        pos = focus + back * dist + Vec3(0, 0, C.CAM_HEIGHT * 0.25)
        camera.setPos(pos)
        camera.lookAt(focus)
        self.cam_pos = Vec3(pos)
        d = focus - pos
        if d.lengthSquared() > 1e-9:
            d.normalize()
            self.cam_dir = d

    def _camera_distance(self, focus: Vec3, back: Vec3, want: float) -> float:
        """Pull the camera in when a wall would come between it and the player."""
        step = 0.75
        d = step
        while d < want:
            p = focus + back * d
            for center, half in self.solids:
                if (abs(p.x - center.x) < half.x + 0.4 and
                        abs(p.y - center.y) < half.y + 0.4 and
                        abs(p.z - center.z) < half.z + 0.4):
                    return max(2.5, d - step)
            d += step
        return want
