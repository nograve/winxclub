#!/usr/bin/env python3
"""Headless playthrough test: boots the game and plays the campaign.

Runs the real Game class against Panda3D's software renderer with the clock in
non-real-time mode, so every frame advances a fixed dt and the run is
deterministic.  Exercised: menus, the story system, level loading for all nine
chapters, movement, collision, flight, combat, pickups, death/respawn, the
portal, bosses, unlocks and teardown.
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

from winx3d import config as C                       # noqa: E402
from winx3d import characters, lore                  # noqa: E402
from winx3d.app import Game                          # noqa: E402
from winx3d.world import (CAMPAIGN_LENGTH, HOME_LEVELS,     # noqa: E402
                          campaign_for, WorldBuilder)

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

    def skip_story(self, limit=60):
        """Click through a chapter's dialogue until play resumes."""
        n = 0
        while self.game.state == "story" and n < limit:
            self.game.on_confirm()
            n += 1
        self.step(2)
        return n


def main():
    print("Booting headless game...")
    h = Harness()
    g = h.game

    print("\n[1] Lore integrity")
    check("ten chapters per campaign", CAMPAIGN_LENGTH == 10)
    check("every chapter has dialogue",
          all(c.intro and c.outro for c in lore.CHAPTERS.values()))
    check("every speaker referenced exists",
          all(k in lore.SPEAKERS
              for c in lore.CHAPTERS.values()
              for k, _ in list(c.intro) + list(c.outro)))
    codex = {c.codex for c in lore.CHAPTERS.values() if c.codex}
    check("all four Codex pieces appear", codex == set(lore.CODEX_PIECES),
          str(sorted(codex)))

    print("\n[1b] Every fairy gets her own realm")
    seen_home, seen_siege = set(), set()
    for f in characters.ROSTER:
        keys = lore.campaign_keys(f.key)
        levels = [lv.key for lv in campaign_for(f.key)]
        ok = keys == levels and len(keys) == CAMPAIGN_LENGTH
        numbers = [lore.CHAPTERS[k].number for k in keys]
        ok = ok and numbers == list(range(1, 11))
        # Chapters 1 and 8 must be hers; 2-7, 9 and 10 are shared.
        ok = ok and keys[0] == "home_" + f.key and keys[7] == "siege_" + f.key
        check("%-7s campaign is well formed" % f.name, ok, str(keys))
        seen_home.add(keys[0])
        seen_siege.add(keys[7])
        # Her chapter 1 and 8 should be set in her own realm.
        check("%-7s opens on %-8s" % (f.name, f.home_realm),
              lore.CHAPTERS[keys[0]].realm == f.home_realm,
              lore.CHAPTERS[keys[0]].realm)
    check("all six home chapters are distinct", len(seen_home) == 6)
    check("all six siege chapters are distinct", len(seen_siege) == 6)
    check("shared chapters are actually shared",
          len({tuple(lore.campaign_keys(f.key)[1:7])
               for f in characters.ROSTER}) == 1)

    print("\n[1c] Every home realm builds")
    for key, (calm, siege) in HOME_LEVELS.items():
        good = True
        for lv in (calm, siege):
            wb = WorldBuilder()
            lv.build(wb)
            good = good and len(wb.boxes) > 20 and not wb.mesh.is_empty()
        check("%-7s realm geometry (calm + besieged)" % key, good)
    check("home realms are visually distinct",
          len({id(HOME_LEVELS[f.key][0].build) for f in characters.ROSTER}) == 6)

    print("\n[2] Title and menus")
    h.step(3)
    check("starts on the title screen", g.state == "title")
    h.key("arrow_down"); h.key("arrow_down", False)
    check("menu selection moves", g.menu_index == 1)
    g.on_confirm()
    check("'How to Play' opens", g.state == "help")
    g.on_escape()
    check("escape returns to title", g.state == "title")

    print("\n[3] Character select and unlocks")
    g.menu_index = 0
    g.on_confirm()
    check("select screen opens", g.state == "select")
    check("preview model built", g.preview is not None)
    bloom = characters.BY_KEY["bloom"]
    aisha = characters.BY_KEY["aisha"]
    check("Bloom is available from the start", g.fairy_unlocked(bloom))
    g.profile["levels_cleared"] = 0
    check("Aisha is locked before the campaign is cleared",
          not g.fairy_unlocked(aisha))
    g.select_index = [f.key for f in characters.ROSTER].index("aisha")
    g._refresh_select()
    g.on_confirm()
    check("a locked fairy cannot be chosen", g.state == "select")
    g.profile["levels_cleared"] = CAMPAIGN_LENGTH
    check("Aisha unlocks after clearing the campaign",
          g.fairy_unlocked(aisha))
    g.profile["levels_cleared"] = 0
    g.select_index = 0
    g._refresh_select()
    g.on_confirm()

    print("\n[4] Chapter 1 story and level")
    check("chapter intro plays before gameplay", g.state == "story")
    check("chapter is 'The Ogre in the Park'",
          g.story_chapter.title == "The Ogre in the Park")
    check("Knut has a line in chapter 1",
          any(k == "knut" for k, _ in g.story_chapter.intro))
    lines = h.skip_story()
    check("dialogue advances line by line", lines == len(g.chapter.intro),
          "%d lines" % lines)
    check("play begins after the intro", g.state == "playing")
    check("level is Gardenia Park", g.level.key == "home_bloom")
    check("Knut is the chapter 1 boss",
          any(b.name == "knut" for b in g.bosses))
    check("ghouls spawned",
          any(e.name == "ghoul" for e in g.enemy_list))
    check("boss bar tracks Knut", g.active_boss() is not None)
    check("hud built", g.hud is not None)

    print("\n[5] Movement, collision and flight")
    p = g.player
    check("player settles on the ground", abs(p.root.getZ()) < 3.0,
          "z=%.2f" % p.root.getZ())
    x0, y0 = p.root.getX(), p.root.getY()
    h.step(45, keys={"forward": True, "run": True})
    h.step(1, keys={"forward": False, "run": False})
    moved = math.hypot(p.root.getX() - x0, p.root.getY() - y0)
    check("running moves the player", moved > 3.0, "moved %.2f" % moved)

    # Walk hard into the bandstand plinth; pushout must keep us outside it.
    p.root.setPos(0, -14.0, 1.2)
    p.vel = Vec3(0, 0, 0)
    h.step(90, keys={"forward": True, "run": True})
    h.step(1, keys={"forward": False, "run": False})
    inside = (abs(p.root.getX()) < 7.5 and abs(p.root.getY()) < 7.5
              and p.root.getZ() < 0.8)
    check("cannot walk inside a solid", not inside, "%s" % p.root.getPos())

    p.root.setPos(0, -40, 2.0)
    p.vel = Vec3(0, 0, 0)
    p.magic = C.MAX_MAGIC
    g.keys["jump_pressed"] = True
    h.step(70, keys={"jump": True})
    check("holding jump gains height", p.root.getZ() > 5.0,
          "z=%.2f" % p.root.getZ())
    check("flying drains magic", p.magic < C.MAX_MAGIC)
    check("wings are out", p.flying)
    h.step(150, keys={"jump": False})
    check("player lands again", p.grounded)

    print("\n[6] Combat")
    for e in g.enemy_list:
        if e.alive:
            e.root.setPos(e.root.getPos() + Vec3(0, 160, 0))
    target = next(e for e in g.enemy_list if e.name == "ghoul")
    target.root.setPos(-52, -52, 1.0)
    p.root.setPos(-52, -64, 1.0)
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
    check("bolt damages the enemy (lock-on)", target.health < hp_before,
          "%.1f -> %.1f" % (hp_before, target.health))

    p.magic = C.MAX_MAGIC
    near = [e for e in g.enemy_list if e.name == "ghoul" and e.alive][1]
    near.root.setPos(p.root.getPos() + Vec3(2.0, 0, 0))
    h.step(1)
    hp2 = near.health
    h.step(2, keys={"special": True})
    h.step(2, keys={"special": False})
    check("blast damages a nearby enemy", near.health < hp2)

    print("\n[7] Transformation uses the fairy's signature spell")
    check("Bloom's ultimate is the Dragon Flame",
          p.spec.ultimate == "DRAGON FLAME")
    near.take_damage(999.0, g.effects)
    p.root.setPos(0, -60, 20.0)
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

    print("\n[8] Pickups and damage")
    gem = next(q for q in g.pickups if q.kind == "gem" and not q.taken)
    before = p.gems
    p.root.setPos(gem.np.getPos() - Vec3(0, 0, 1.0))
    h.step(3)
    check("collectible is picked up", p.gems == before + 1)

    hp_pick = next(q for q in g.pickups if q.kind == "heart" and not q.taken)
    p.health = 2.0
    p.root.setPos(hp_pick.np.getPos() - Vec3(0, 0, 1.0))
    h.step(3)
    check("heart restores health", p.health > 2.0)

    p.invuln = 0.0
    hp_before = p.health
    p.take_damage(1.0)
    check("taking damage costs health", p.health == hp_before - 1.0)
    p.take_damage(1.0)
    check("i-frames block repeat hits", p.health == hp_before - 1.0)

    lives = p.lives
    p.invuln = 0.0
    p.take_damage(99.0, force=True)
    check("player dies at zero health", not p.alive)
    h.step(140)
    check("a life is spent", p.lives == lives - 1)
    check("player respawns alive", p.alive)

    print("\n[9] Objective, portal and the outro")
    for e in g.enemy_list:
        if e.alive:
            e.take_damage(999.0, g.effects)
    p.gems = max(p.gems, g.level.gem_goal)
    h.step(3)
    check("portal opens once the chapter is clear", g.portal_active)
    score = p.score
    check("defeating enemies scored points", score > 0, "score=%d" % score)
    p.root.setPos(g.portal.getPos() + Vec3(0, 0, 1.5))
    h.step(3)
    check("entering the portal ends the chapter", g.state == "story")
    check("the outro is playing",
          g.story_lines == list(g.chapter.outro))
    h.skip_story()
    check("results follow the outro", g.state == "results")
    check("progress was recorded", g.profile["levels_cleared"] >= 1)

    print("\n[10] Every chapter of Bloom's campaign loads and runs")
    for i, level in enumerate(g.campaign):
        g.load_level(i)
        h.skip_story()
        h.step(30)
        ch = lore.CHAPTERS[level.key]
        ok = (g.state == "playing" and g.level.key == level.key
              and g.player is not None and len(g.enemy_list) > 0)
        check("chapter %2d: %-24s" % (ch.number, ch.title), ok,
              "state=%s" % g.state)

    print("\n[10b] Each fairy's own chapters load and run")
    for f in characters.ROSTER:
        g.start_run(f)
        h.skip_story()
        h.step(20)
        opened = (g.state == "playing" and g.level.key == "home_" + f.key
                  and g.player.spec.key == f.key)
        # Then jump straight to her chapter 8 and play a little of it.
        g.load_level(7)
        h.skip_story()
        h.step(20)
        sieged = (g.state == "playing" and g.level.key == "siege_" + f.key
                  and any(getattr(e, "is_boss", False) for e in g.enemy_list))
        check("%-7s plays %s and its siege" % (f.name, f.home_realm),
              opened and sieged, "state=%s key=%s" % (g.state, g.level.key))

    print("\n[11] The Trix")
    g.start_run(characters.BY_KEY["bloom"])
    h.skip_story()
    g.load_level(CAMPAIGN_LENGTH - 1)
    h.skip_story()
    h.step(3)
    names = {b.name for b in g.bosses}
    check("all three Trix in the finale", names == {"icy", "darcy", "stormy"},
          str(sorted(names)))
    check("Army of Decay present",
          any(e.name == "decay" for e in g.enemy_list))
    g.player.root.setPos(0, -12, 6.0)
    icy = next(b for b in g.bosses if b.name == "icy")
    check("boss bar shows a Trix title", "ICY" in g.active_boss().title)
    for frac, label in ((0.5, "phase 2"), (0.2, "phase 3")):
        icy.health = icy.max_health * frac
        icy.pattern_cd = 0.0
        h.step(30)
        check("Icy reaches %s" % label, icy.phase in (2, 3),
              "phase=%d" % icy.phase)
    h.step(60)
    check("the Trix attack", any(pr.hostile for pr in g.effects.projectiles))
    for b in g.bosses:
        b.take_damage(999.0, g.effects)
    h.step(3)
    check("the Trix can be defeated", not any(b.alive for b in g.bosses))
    check("boss bar clears", g.active_boss() is None)

    print("\n[12] Rendering and teardown")
    g.load_level(0)
    h.skip_story()
    h.step(4, render=True)
    from panda3d.core import Filename
    shot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "screenshots")
    os.makedirs(shot_dir, exist_ok=True)
    check("screenshot captured", g.win.saveScreenshot(
        Filename.fromOsSpecific(os.path.join(shot_dir, "gameplay.png"))))
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
