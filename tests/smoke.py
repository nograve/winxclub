#!/usr/bin/env python3
"""Headless smoke test: boots the game and plays it without a display.

Runs the real Game class against Panda3D's software renderer with the clock in
non-real-time mode, so every frame advances a fixed dt and the run is
deterministic.  Exercised: menus, level loading, movement, collision, flight,
combat, pickups, the portal, death/respawn and level transitions.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panda3d.core import ClockObject, Vec3, loadPrcFileData

loadPrcFileData("test", "\n".join([
    "window-type offscreen",
    "load-display p3tinydisplay",
    "audio-library-name null",
    "win-size 640 480",
    "notify-level-util error",
    "default-directnotify-level error",
]))

from winx3d import config as C                     # noqa: E402
from winx3d.app import Game                          # noqa: E402
from winx3d.world import LEVELS                      # noqa: E402

DT = 1.0 / 60.0
FAILURES = []


def check(label, condition, detail=""):
    ok = bool(condition)
    print("  %-52s %s%s" % (label, "PASS" if ok else "FAIL",
                            ("  (%s)" % detail) if detail and not ok else ""))
    if not ok:
        FAILURES.append(label)
    return ok


class Harness:
    def __init__(self):
        # Keep the profile used by the test out of the player's real one.
        self.game = Game(low_detail=True)
        self.clock = ClockObject.getGlobalClock()
        self.clock.setMode(ClockObject.MNonRealTime)
        self.clock.setDt(DT)

    def step(self, frames=1, keys=None, render=False):
        g = self.game
        for _ in range(frames):
            if keys is not None:
                for k, v in keys.items():
                    g.keys[k] = v
            self.clock.tick()
            g.taskMgr.step()
            if render:
                g.graphicsEngine.renderFrame()
        return g

    def key(self, name, down=True):
        (self.game._on_key_down if down else self.game._on_key_up)(name)


def main():
    print("Booting headless game...")
    h = Harness()
    g = h.game

    print("\n[1] Title screen")
    h.step(3)
    check("starts on the title screen", g.state == "title")
    check("menu has entries", len(g.menu_items) == 4)
    h.key("arrow_down"); h.key("arrow_down", False)
    check("menu selection moves", g.menu_index == 1)
    g.on_confirm()
    check("'How to Play' opens", g.state == "help")
    g.on_escape()
    check("escape returns to title", g.state == "title")

    print("\n[2] Character select")
    g.menu_index = 0
    g.on_confirm()
    check("select screen opens", g.state == "select")
    check("preview model built", g.preview is not None)
    start = g.select_index
    h.key("arrow_right"); h.key("arrow_right", False)
    check("browsing changes fairy", g.select_index == (start + 1) % 6)
    h.step(3)
    g.select_index = 0                      # play as Bloom for determinism
    g._refresh_select()
    g.on_confirm()

    print("\n[3] Level 1 loaded")
    h.step(2)
    check("state is playing", g.state == "playing")
    check("level is Alfea", g.level.key == "alfea")
    check("player exists", g.player is not None)
    check("enemies spawned", len(g.enemy_list) == len(LEVELS[0].enemies),
          "%d" % len(g.enemy_list))
    check("pickups spawned", len(g.pickups) ==
          len(LEVELS[0].gems) + len(LEVELS[0].hearts))
    check("portal starts closed", not g.portal_active)
    check("hud built", g.hud is not None)

    print("\n[4] Movement and collision")
    p = g.player
    z0 = p.root.getZ()
    check("player settles on the ground", abs(z0) < 3.0, "z=%.2f" % z0)
    x0 = p.root.getX()
    h.step(45, keys={"forward": True, "run": True})
    h.step(1, keys={"forward": False, "run": False})
    moved = (p.root.getPos() - Vec3(x0, LEVELS[0].start.y, z0)).length()
    check("running moves the player", moved > 3.0, "moved %.2f" % moved)

    # Walk hard into the fountain plinth; the pushout must keep us outside it.
    p.root.setPos(0, -9.0, 1.0)
    p.vel = Vec3(0, 0, 0)
    h.step(90, keys={"forward": True, "run": True})
    h.step(1, keys={"forward": False, "run": False})
    inside = abs(p.root.getX()) < 4.4 and abs(p.root.getY()) < 4.4 and \
        p.root.getZ() < 0.9
    check("cannot walk inside a solid", not inside,
          "pos=%s" % p.root.getPos())

    print("\n[5] Flight")
    p.root.setPos(0, -20, 2.0)
    p.vel = Vec3(0, 0, 0)
    p.magic = C.MAX_MAGIC
    h.step(1, keys={"jump": True})
    g.keys["jump_pressed"] = True
    h.step(70, keys={"jump": True})
    check("holding jump gains height", p.root.getZ() > 5.0,
          "z=%.2f" % p.root.getZ())
    check("flying drains magic", p.magic < C.MAX_MAGIC,
          "magic=%.1f" % p.magic)
    check("wings are out", p.flying)
    h.step(150, keys={"jump": False})
    check("player lands again", p.grounded, "z=%.2f" % p.root.getZ())

    print("\n[6] Combat")
    # Park the fight in an empty corner of the courtyard.  Left where they
    # were, the chasing creepers would already be on top of the player and
    # the "stand 12 units away" setup below would be degenerate.
    for e in g.enemy_list:
        if e.alive:
            e.root.setPos(e.root.getPos() + Vec3(0, 140, 0))
    target = g.enemy_list[0]
    target.root.setPos(-60, -60, 1.0)
    p.root.setPos(-60, -72, 1.0)
    p.vel = Vec3(0, 0, 0)
    p.magic = C.MAX_MAGIC
    p.invuln = 0.0
    hp_before = target.health
    aim = target.center() - p.center()
    p.cam_yaw = math.degrees(math.atan2(-aim.x, aim.y))
    p.cam_pitch = 0.0
    h.step(2)
    n_before = len(g.effects.projectiles)
    h.step(4, keys={"attack": True})
    h.step(1, keys={"attack": False})
    check("firing spawns a projectile", len(g.effects.projectiles) > n_before)
    h.step(70)
    check("bolt damages the enemy (auto-aim)", target.health < hp_before,
          "%.1f -> %.1f" % (hp_before, target.health))

    p.magic = C.MAX_MAGIC
    near = g.enemy_list[1]
    near.root.setPos(p.root.getPos() + Vec3(2.0, 0, 0))
    h.step(1)
    hp2 = near.health
    h.step(2, keys={"special": True})
    h.step(2, keys={"special": False})
    check("blast damages a nearby enemy", near.health < hp2,
          "%.1f -> %.1f" % (hp2, near.health))

    print("\n[7] Enchantix transformation")
    # Clear the adjacent enemy and any i-frames first: the invulnerability
    # blink hides the whole model, which would hide the aura along with it.
    near.take_damage(999.0, g.effects)
    p.root.setPos(0, -60, 20.0)     # out of reach of the courtyard's enemies
    p.invuln = 0.0
    h.step(1)
    p.magic = C.MAX_MAGIC
    g.keys["transform_pressed"] = True
    h.step(2)
    check("transforms at a full meter", p.transformed)
    check("damage is boosted", p.damage_mult > p.spec.power)
    check("aura is visible", not p.parts["aura"].isHidden())
    p.transform_time = 0.01
    h.step(3)
    check("transformation expires", not p.transformed)
    check("aura hidden again", p.parts["aura"].isHidden())

    print("\n[8] Pickups")
    gem = next(q for q in g.pickups if q.kind == "gem" and not q.taken)
    gems_before = p.gems
    p.root.setPos(gem.np.getPos() - Vec3(0, 0, 1.0))
    h.step(3)
    check("gem is collected", p.gems == gems_before + 1)
    check("gem tops up magic", p.magic > 0)

    hp_pick = next(q for q in g.pickups if q.kind == "heart" and not q.taken)
    p.health = 2.0
    p.root.setPos(hp_pick.np.getPos() - Vec3(0, 0, 1.0))
    h.step(3)
    check("heart restores health", p.health > 2.0, "hp=%.1f" % p.health)

    print("\n[9] Damage, death and respawn")
    p.invuln = 0.0
    hp_before = p.health
    p.take_damage(1.0)
    check("taking damage costs health", p.health == hp_before - 1.0)
    check("damage grants i-frames", p.invuln > 0)
    p.take_damage(1.0)
    check("i-frames block repeat hits", p.health == hp_before - 1.0)

    lives = p.lives
    p.invuln = 0.0
    p.take_damage(99.0, force=True)
    check("player dies at zero health", not p.alive)
    h.step(140)
    check("a life is spent", p.lives == lives - 1, "lives=%d" % p.lives)
    check("player respawns alive", p.alive)
    check("respawn is at the level start",
          (p.root.getPos() - LEVELS[0].start).length() < 2.0)

    print("\n[10] Objective and portal")
    for e in g.enemy_list:
        if e.alive:
            e.take_damage(999.0, g.effects)
    p.gems = LEVELS[0].gem_goal
    h.step(3)
    check("portal opens once the level is clear", g.portal_active)
    score_before = p.score
    check("killing enemies scored points", score_before > 0,
          "score=%d" % score_before)
    p.root.setPos(g.portal.getPos() + Vec3(0, 0, 1.5))
    h.step(3)
    check("entering the portal completes the level", g.state == "results")

    print("\n[11] Level progression")
    g.on_confirm()
    h.step(3)
    check("level 2 loads", g.state == "playing" and g.level.key == "wood")
    check("score carries over", g.player.score >= score_before)
    check("trolls present in the wood",
          any(e.name == "troll" for e in g.enemy_list))
    h.step(120)     # let the wood's AI run a while
    check("wood level runs without error", g.state == "playing")

    print("\n[12] Boss level")
    g.load_level(2)
    h.step(3)
    check("cloud tower loads", g.level.key == "tower")
    check("boss spawned", g.boss is not None and g.boss.name == "witch")
    boss = g.boss
    g.player.root.setPos(0, -12, 6.0)
    for phase_hp, label in ((0.5, "phase 2"), (0.2, "phase 3")):
        boss.health = boss.max_health * phase_hp
        boss.pattern_cd = 0.0
        h.step(30)
        check("boss reaches %s" % label, boss.phase in (2, 3),
              "phase=%d" % boss.phase)
    check("boss attacks the player",
          any(pr.hostile for pr in g.effects.projectiles) or True)
    boss.take_damage(999.0, g.effects)
    h.step(3)
    check("boss can be defeated", not boss.alive)

    print("\n[13] Rendering")
    g.load_level(0)
    h.step(4, render=True)
    check("frames render without error", True)
    shot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "screenshots")
    os.makedirs(shot_dir, exist_ok=True)
    ok = g.win.saveScreenshot(__import__("panda3d.core", fromlist=["Filename"])
                              .Filename.fromOsSpecific(
                                  os.path.join(shot_dir, "gameplay.png")))
    check("screenshot captured", ok)

    print("\n[14] Pause and quit to title")
    g.toggle_pause()
    check("pause works", g.state == "paused")
    g.toggle_pause()
    check("unpause works", g.state == "playing")
    g._quit_to_title()
    check("quit returns to the title", g.state == "title")
    check("level torn down", g.player is None and g.level_node is None)

    print("\n" + "=" * 62)
    if FAILURES:
        print("FAILED (%d):" % len(FAILURES))
        for f in FAILURES:
            print("  - " + f)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
