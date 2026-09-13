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
                          SHARED_LEVELS, campaign_for, WorldBuilder)
from winx3d.enemies import ground_height                    # noqa: E402

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

    def solve_puzzles(self, required_only=True):
        """Work every puzzle in the current level the way a player would."""
        g = self.game
        from winx3d import puzzles as P
        for name, members in list(g.groups.items()):
            drivers = [m for m in members if not isinstance(m, P.OPENERS)]
            if drivers and isinstance(drivers[0], P.Pedestal):
                for m in sorted(drivers, key=lambda x: x.spec.order):
                    m.use(g)
            elif drivers and isinstance(drivers[0], P.Plate):
                continue          # plates need blocks pushed onto them
            else:
                for m in drivers:
                    if m.can_use(g):
                        m.use(g)
        self.step(2)

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

    print("\n[1d] Puzzle and pickup placement")
    all_levels = list(SHARED_LEVELS.values())
    for _c, _s in HOME_LEVELS.values():
        all_levels += [_c, _s]
    misplaced = []
    for lv in all_levels:
        wb = WorldBuilder()
        lv.build(wb)
        boxes = wb.boxes
        spots = [("gem", g) for g in lv.gems] + \
                [("heart", p) for p in lv.hearts] + \
                [(s.kind, s.pos) for s in lv.puzzles if s.kind != "bridge"]
        for kind, p in spots:
            buried = any(abs(p.x - c.x) < h.x - 0.05
                         and abs(p.y - c.y) < h.y - 0.05
                         and c.z - h.z + 0.05 < p.z < c.z + h.z - 0.05
                         for c, h in boxes)
            gz = ground_height(boxes, p.x, p.y, p.z + 1.5)
            adrift = abs(gz - p.z) > 1.6
            if buried or adrift:
                misplaced.append("%s/%s at %s" % (lv.key, kind, p))
    check("nothing is buried in a wall or floating", not misplaced,
          "%d bad: %s" % (len(misplaced), misplaced[:3]))

    levels_with_puzzles = [lv for lv in all_levels if lv.puzzles]
    check("every level has interactive content",
          len(levels_with_puzzles) == len(all_levels),
          "%d of %d" % (len(levels_with_puzzles), len(all_levels)))
    check("every level has an objective list",
          all(lv.objectives for lv in all_levels))
    kinds = {s.kind for lv in all_levels for s in lv.puzzles}
    check("all puzzle kinds are used somewhere",
          kinds >= {"tablet", "cache", "rune", "pedestal", "lever",
                    "bridge", "gate", "block", "plate"}, str(sorted(kinds)))
    check("every tablet has text",
          all(s.text and s.title for lv in all_levels
              for s in lv.puzzles if s.kind == "tablet"))
    # A group that opens a gate or bridge must have something driving it.
    for lv in all_levels:
        groups = {}
        for s in lv.puzzles:
            if s.group:
                groups.setdefault(s.group, []).append(s.kind)
        for name, members in groups.items():
            openers = [k for k in members if k in ("gate", "bridge")]
            drivers = [k for k in members if k not in ("gate", "bridge")]
            if openers and not drivers:
                check("%s/%s has a driver" % (lv.key, name), False)

    print("\n[1e] Audio: a theme and a bed for every realm")
    from winx3d import audio as A
    from winx3d.app import realm_audio
    tracks = {k for k in A.GENERATORS if k.startswith("music_")}
    beds = {k for k in A.GENERATORS if k.startswith("ambience_")}
    check("there is a theme per realm and location", len(tracks) >= 14,
          "%d" % len(tracks))
    check("there are ambient beds", len(beds) >= 6, "%d" % len(beds))
    missing = []
    assigned_music, assigned_beds = set(), set()
    for lv in all_levels:
        music, bed = realm_audio(lv.key)
        assigned_music.add(music)
        assigned_beds.add(bed)
        if music not in A.GENERATORS:
            missing.append(lv.key + " -> " + music)
        if bed not in A.GENERATORS:
            missing.append(lv.key + " -> " + bed)
    check("every level maps to sounds that exist", not missing, str(missing))
    check("the six home realms have six different themes",
          len({realm_audio("home_" + f.key)[0]
               for f in characters.ROSTER}) == 6)
    check("home realms have distinct ambience",
          len({realm_audio("home_" + f.key)[1]
               for f in characters.ROSTER}) >= 4)
    check("a besieged realm keeps its own ambience",
          realm_audio("siege_tecna")[1] == realm_audio("home_tecna")[1])
    check("a besieged realm changes its music",
          realm_audio("siege_tecna")[0] != realm_audio("home_tecna")[0])
    check("most themes are actually used", len(assigned_music) >= 12,
          "%d" % len(assigned_music))

    for f in characters.ROSTER:
        ok = ("shoot_" + f.key in A.GENERATORS
              and "hit_" + f.key in A.GENERATORS)
        check("%-7s has her own magic sound" % f.name, ok)
    check("elemental sounds differ per fairy",
          len({tuple(A.ELEMENTS[f.key]) for f in characters.ROSTER}) == 6)

    cached = A.ensure_sounds()
    on_disk = {n[:-4] for n in os.listdir(cached) if n.endswith(".wav")}
    check("every sound was generated to disk",
          set(A.GENERATORS) <= on_disk,
          str(sorted(set(A.GENERATORS) - on_disk))[:120])
    # Structure is not enough: measure the samples. A bug in the envelope
    # once made every chord and every percussion-free track render pure
    # silence, and nothing above would have noticed.
    import array as _array
    import wave as _wave
    bad_wav, silent, clipping, sigs = [], [], [], {}
    for name in sorted(A.GENERATORS):
        try:
            with _wave.open(os.path.join(cached, name + ".wav")) as fh:
                frames = fh.getnframes()
                if frames < 500 or fh.getnchannels() != 1:
                    bad_wav.append(name)
                    continue
                raw = _array.array("h")
                raw.frombytes(fh.readframes(frames))
        except Exception:
            bad_wav.append(name)
            continue
        rms = math.sqrt(sum(float(s) * s for s in raw) / len(raw)) / 32768.0
        peak = max(abs(s) for s in raw) / 32768.0
        if rms < 0.005:
            silent.append("%s (rms %.4f)" % (name, rms))
        if peak > 0.995:
            clipping.append(name)
        sigs[name] = rms
    check("every generated file is a readable mono WAV", not bad_wav,
          str(bad_wav[:5]))
    check("no generated sound is silent", not silent, str(silent[:4]))
    check("no generated sound clips", not clipping, str(clipping[:4]))
    themes = sorted(k for k in A.GENERATORS if k.startswith("music_"))
    check("every theme carries real signal",
          all(sigs.get(k, 0) > 0.02 for k in themes),
          str([k for k in themes if sigs.get(k, 0) <= 0.02])[:120])
    check("themes are not all the same rendering",
          len({round(sigs[k], 3) for k in themes}) >= len(themes) // 2)

    print("\n[1f] Model detail")
    from winx3d import enemies as _E
    from winx3d.geometry import MeshBuilder
    from panda3d.core import NodePath as _NP

    def tri_count(build):
        mb = MeshBuilder()
        build(mb)
        return len(mb._tris)

    # Every fairy must be a real model, not a stub.
    for f in characters.ROSTER:
        model, parts = characters.build_fairy(f)
        pieces = model.findAllMatches("**/+GeomNode").getNumPaths()
        ok = pieces >= 8 and set(parts) >= {"head", "torso", "hips", "aura",
                                            "arm_l", "arm_r", "leg_l",
                                            "leg_r", "wing_l", "wing_r"}
        check("%-7s has a full body" % f.name, ok, "%d pieces" % pieces)
        model.removeNode()
    styles = {f.hair_style for f in characters.ROSTER}
    check("the fairies do not share one hairstyle", len(styles) >= 5,
          str(sorted(styles)))
    check("each fairy has her own eye colour",
          len({tuple(f.eye) for f in characters.ROSTER}) == 6)

    # Enemies likewise, and the Trix must differ in shape not just palette.
    holder = _NP("holder")
    for key in sorted(_E.KINDS):
        foe = _E.spawn(key, holder, Vec3(0, 0, 0), [])
        pieces = foe.root.findAllMatches("**/+GeomNode").getNumPaths()
        check("%-8s model built" % key, pieces >= 1, "%d" % pieces)
        foe.root.removeNode()
    trix = (_E.Icy, _E.Darcy, _E.Stormy)
    check("the Trix have different silhouettes",
          len({(c.hair_style, c.gown, c.charm) for c in trix}) == 3)
    check("the Trix have different palettes",
          len({tuple(c.ice) for c in trix}) == 3)

    # Ground should carry surface variation, not be a bare plane.
    plain = tri_count(lambda m: m.grid_ground(120, 120, (0.4, 0.7, 0.4),
                                              (0.4, 0.7, 0.4), step=11.0))
    detailed = tri_count(lambda m: m.grid_ground(120, 120, (0.4, 0.7, 0.4),
                                                 (0.35, 0.65, 0.35), step=5.5,
                                                 jitter=0.12, relief=0.09))
    check("ground is finely tiled", detailed > plain * 3,
          "%d vs %d tris" % (detailed, plain))

    # And every level's mesh should be substantial but not extravagant.
    heavy = []
    for lv in all_levels:
        wb = WorldBuilder()
        lv.build(wb)
        n = len(wb.mesh._tris) + len(wb.alpha_mesh._tris)
        if n < 3000 or n > 60000:
            heavy.append("%s:%d" % (lv.key, n))
    check("level geometry is detailed and within budget", not heavy,
          str(heavy[:4]))

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

    # Walk hard into a wall and confirm the pushout keeps us outside it.
    # Pick a real solid from the level rather than assuming a landmark.
    tall = [(c, h) for c, h in g.solids
            if h.z > 1.0 and h.x > 2.0 and h.y > 2.0 and c.z > -5.0]
    wall_c, wall_h = max(tall, key=lambda ch: ch[1].z)
    approach = Vec3(wall_c.x, wall_c.y - wall_h.y - 6.0,
                    wall_c.z + wall_h.z + 0.2)
    p.root.setPos(approach)
    p.vel = Vec3(0, 0, 0)
    p.cam_yaw = 0.0
    h.step(110, keys={"forward": True, "run": True})
    h.step(1, keys={"forward": False, "run": False})
    q = p.root.getPos()
    inside = (abs(q.x - wall_c.x) < wall_h.x - 0.2 and
              abs(q.y - wall_c.y) < wall_h.y - 0.2 and
              wall_c.z - wall_h.z + 0.2 < q.z < wall_c.z + wall_h.z - 0.2)
    check("cannot walk inside a solid", not inside, "%s" % q)

    p.root.setPos(Vec3(g.level.start) + Vec3(0, 0, 1.0))
    p.vel = Vec3(0, 0, 0)
    p.magic = C.MAX_MAGIC
    h.step(6)
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
    base = Vec3(g.level.start)
    target.root.setPos(base.x, base.y + 12.0, base.z)
    p.root.setPos(base.x, base.y, base.z)
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
    others = [e for e in g.enemy_list if e.name == "ghoul" and e.alive
              and e is not target]
    near = others[0]
    near.root.setPos(p.root.getPos() + Vec3(2.0, 0, 0))
    h.step(1)
    hp2 = near.health
    h.step(2, keys={"special": True})
    h.step(2, keys={"special": False})
    check("blast damages a nearby enemy", near.health < hp2)

    print("\n[6b] Free-aim shooting")
    # Regression: aiming used to follow the camera's downward tilt from chest
    # height, so an unlocked bolt buried itself in the ground after ~2 units.
    for e in g.enemy_list:
        if e.alive:
            e.root.setPos(e.root.getPos() + Vec3(0, 400, 0))
    p.root.setPos(Vec3(g.level.start) + Vec3(0, 0, 1.0))
    p.vel = Vec3(0, 0, 0)
    p.cam_yaw, p.cam_pitch = 0.0, C.CAM_PITCH
    p.magic = C.MAX_MAGIC
    h.step(4)
    check("neutral camera aims level", abs(p.aim_pitch) < 0.01,
          "%.2f" % p.aim_pitch)
    aim = p.aim_direction(g.enemy_list)
    check("an unlocked shot is not fired into the ground", abs(aim.z) < 0.05,
          "z=%.3f" % aim.z)
    h.step(3, keys={"attack": True})
    h.step(1, keys={"attack": False})
    bolt = g.effects.projectiles[0]
    start = Vec3(bolt.np.getPos())
    far = start
    for _ in range(120):
        h.step(1)
        if not g.effects.projectiles:
            break
        far = Vec3(g.effects.projectiles[0].np.getPos())
    reach = (far - start).length()
    check("a level shot carries across open ground", reach > 20.0,
          "%.1f units" % reach)
    check("it stays at the height it was fired", abs(far.z - start.z) < 1.0,
          "dz=%.2f" % (far.z - start.z))

    # Looking up and down moves the aim by the same amount.
    p.cam_pitch = C.CAM_PITCH + 20.0
    check("looking up raises the aim",
          p.aim_direction(g.enemy_list).z > 0.3)
    p.cam_pitch = C.CAM_PITCH - 20.0
    check("looking down lowers the aim",
          p.aim_direction(g.enemy_list).z < -0.3)
    p.cam_pitch = C.CAM_PITCH

    # The aim must not depend on the camera being pulled in by a wall.
    aim_free = p.aim_direction(g.enemy_list)
    p.cam_pos = p.center() + Vec3(0, -2.0, 0.5)     # camera jammed against us
    check("a wall behind the player does not tilt the shot",
          abs(p.aim_direction(g.enemy_list).z - aim_free.z) < 0.01)

    # Lock-on and the reticle that reports it.
    foe = next(e for e in g.enemy_list if e.alive)
    foe.root.setPos(0, -16, 0)
    h.step(2)
    p.aim_direction(g.enemy_list)
    check("a target ahead is locked", p.lock_target is foe)
    check("the aim point is the locked target",
          (p.aim_point(g.enemy_list) - foe.center()).length() < 0.01)
    g._update_reticle()
    check("the reticle marks the lock", g.hud.reticle_locked)
    check("the reticle is on screen",
          abs(g.hud.reticle.getX()) < 2.0 and abs(g.hud.reticle.getZ()) < 1.0)
    foe.root.setPos(0, 400, 0)
    h.step(2)
    p.aim_direction(g.enemy_list)
    check("the lock clears when the target leaves", p.lock_target is None)

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

    print("\n[9] Puzzles, objectives and the portal")
    check("chapter 1 has interactive objects", len(g.interactables) > 0,
          "%d" % len(g.interactables))
    tablet = next(it for it in g.interactables
                  if it.__class__.__name__ == "Tablet")
    p.root.setPos(tablet.center() + Vec3(0, -2.0, -1.0))
    h.step(2)
    check("standing near a tablet offers a prompt",
          g.nearest_interactable() is tablet)
    g.do_interact()
    check("reading opens the inscription panel", g.state == "reading")
    check("the inscription has text", bool(g.reading[1]))
    g.on_confirm()
    check("closing it returns to play", g.state == "playing")
    check("the tablet is marked read", g.puzzle.tablets_read == 1)

    rune = next(it for it in g.interactables
                if it.__class__.__name__ == "Rune")
    check("runes can be shot", rune.shootable)
    # Lock-on takes enemies over scenery, which is right in play but would
    # steal this shot - clear the line first.
    for e in g.enemy_list:
        if e.alive:
            e.root.setPos(e.root.getPos() + Vec3(0, 500, 0))
    p.magic = C.MAX_MAGIC
    p.invuln = 0.0
    p.root.setPos(rune.center() + Vec3(0, -11.0, -1.0))
    aim = rune.center() - p.center()
    p.cam_yaw = math.degrees(math.atan2(-aim.x, aim.y))
    # Aim pitch is measured from neutral camera tilt, not absolute.
    p.cam_pitch = math.degrees(
        math.asin(max(-1, min(1, aim.z / aim.length())))) + C.CAM_PITCH
    h.step(2)
    h.step(4, keys={"attack": True})
    h.step(1, keys={"attack": False})
    h.step(40)
    check("a magic bolt lights a rune", rune.solved)

    caches = [it for it in g.interactables
              if it.__class__.__name__ in ("Cache", "Chest")]
    check("the level has chests and caches", len(caches) >= 4,
          "%d" % len(caches))
    before = p.score
    p.root.setPos(caches[0].center() + Vec3(0, -2.0, -1.0))
    h.step(2)
    g.do_interact()
    check("a cache can be opened", caches[0].solved)
    check("finding one is rewarded", p.score > before)
    check("opening one is counted",
          g.puzzle.secrets_found + g.puzzle.chests_opened == 1)

    flags = [o for o in g.level.objectives if o.kind == "flag"]
    check("chapter 1 has a puzzle objective", len(flags) >= 1)
    check("it starts incomplete", not g.objective_done(flags[0]))
    for e in g.enemy_list:
        if e.alive:
            e.take_damage(999.0, g.effects)
    h.step(3)
    check("the portal stays shut while a puzzle is unsolved",
          not g.portal_active)
    h.solve_puzzles()
    check("solving the group completes the objective",
          g.objective_done(flags[0]))
    p.gems = max(p.gems, g.level.gem_goal)
    h.step(3)
    check("the portal opens once everything is done", g.portal_active)
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

    print("\n[9a] Linear stage structure")
    from winx3d import puzzles as _P
    short = [lv.key for lv in all_levels if lv.course_length < 150]
    check("every chapter is a full-length course", not short, str(short[:4]))
    few = [lv.key for lv in all_levels if len(lv.checkpoints) < 3]
    check("every course drops checkpoints", not few, str(few[:4]))
    nochest = [lv.key for lv in all_levels
               if not any(s.kind == "chest" for s in lv.puzzles)]
    check("every course has chests", not nochest, str(nochest[:4]))
    nospring = [lv.key for lv in all_levels
                if not any(s.kind == "spring" for s in lv.puzzles)]
    check("every course has a spring", not nospring, str(nospring[:4]))
    check("the goal is far from the start",
          all((lv.portal - lv.start).length() > 80.0 for lv in all_levels))

    g.load_level(0)
    h.skip_story()
    h.step(3)
    p = g.player
    check("the run starts at the first checkpoint",
          (p.respawn_point - Vec3(g.level.start)).length() < 12.0)

    # Reaching a checkpoint moves where a fall puts you back.
    before = Vec3(p.respawn_point)
    p.root.setPos(g.checkpoints[1])
    h.step(3)
    check("passing a checkpoint claims it", g.checkpoint_index >= 1)
    check("it moves the respawn point",
          (p.respawn_point - before).length() > 5.0)

    # Falling off the course costs health and returns you to it.
    hp = p.health
    p.invuln = 0.0
    p.root.setPos(Vec3(g.checkpoints[1]) + Vec3(0, 0, -60.0))
    h.step(4)
    check("falling off costs health", p.health < hp)
    check("falling returns you to the checkpoint",
          (p.root.getPos() - g.checkpoints[1]).length() < 6.0,
          "%s" % p.root.getPos())

    # Chests pay out and their lid opens.
    chest = next(i for i in g.interactables if isinstance(i, _P.Chest))
    p.health = 2.0
    p.root.setPos(chest.center() + Vec3(0, -2.0, -1.0))
    h.step(2)
    score_before = p.score
    g.do_interact()
    h.step(30)
    check("a chest can be opened", chest.solved)
    check("it pays out", p.score > score_before)
    check("its lid swings open", chest.hinge.getP() < -30.0,
          "%.0f" % chest.hinge.getP())
    check("chests are counted", g.puzzle.chests_opened >= 1)

    # A spring throws the player upward.
    spring = next(i for i in g.interactables if isinstance(i, _P.Spring))
    p.root.setPos(spring.root.getPos() + Vec3(0, 0, 0.6))
    p.vel = Vec3(0, 0, 0)
    h.step(3)
    check("a spring launches the player", p.vel.z > 15.0,
          "vz=%.1f" % p.vel.z)

    print("\n[9b] The harder puzzle types")
    from winx3d import puzzles as P

    # --- Cloud Tower: a sequence that punishes the wrong order -------------
    g.load_level(lore.CAMPAIGN_TEMPLATE.index("cloudtower"))
    h.skip_story()
    h.step(3)
    peds = sorted([it for it in g.interactables if isinstance(it, P.Pedestal)],
                  key=lambda x: x.spec.order)
    gate = next(it for it in g.interactables if isinstance(it, P.Gate))
    check("Cloud Tower has a four-note sequence", len(peds) == 4)
    check("its gate starts closed and solid",
          not gate.solved and g.solids[gate.box_index][1].z > 1.0)
    peds[0].use(g)
    peds[2].use(g)                      # out of order
    h.step(2)
    check("a wrong note resets the sequence",
          g.puzzle.count("verse") == 0 and not any(x.solved for x in peds))
    for x in peds:
        x.use(g)
    h.step(2)
    check("the right order solves it", g.puzzle.has("verse"))
    check("solving it opens the gate", gate.solved)
    h.step(90)
    check("the opened gate stops blocking",
          g.solids[gate.box_index][0].z < -100.0)

    # --- Red Fountain: push a counterweight onto a plate -------------------
    g.load_level(lore.CAMPAIGN_TEMPLATE.index("redfountain"))
    h.skip_story()
    h.step(3)
    blocks = [it for it in g.interactables if isinstance(it, P.PushBlock)]
    plates = [it for it in g.interactables if isinstance(it, P.Plate)]
    check("Red Fountain has counterweights and plates",
          len(blocks) == 2 and len(plates) == 2)
    # A block that starts flush against a rail can never be pushed at all.
    jammed = [b for b in blocks
              if g.solid_at(b.root.getPos() + Vec3(0, 0, b.half.z), b.half,
                            ignore=b.box_index)]
    check("no counterweight starts jammed against scenery", not jammed,
          "%d jammed" % len(jammed))
    # Pair each block with its nearest plate, and push along that line -
    # the course can be running along any axis at that point.
    blk = blocks[0]
    plate = min(plates, key=lambda q: (q.root.getPos() -
                                       blk.root.getPos()).length())
    to_plate = plate.root.getPos() - blk.root.getPos()
    to_plate.z = 0.0
    to_plate.normalize()
    p = g.player
    start_pos = Vec3(blk.root.getPos())
    p.root.setPos(blk.root.getPos() - to_plate * 4.6 + Vec3(0, 0, 0.2))
    p.vel = Vec3(0, 0, 0)
    p.cam_yaw = math.degrees(math.atan2(-to_plate.x, to_plate.y))
    h.step(110, keys={"forward": True, "run": True})
    h.step(1, keys={"forward": False, "run": False})
    moved = (blk.root.getPos() - start_pos).length()
    check("walking into a block pushes it", moved > 1.0,
          "moved %.2f" % moved)
    check("the block's collision moves with it",
          (Vec3(g.solids[blk.box_index][0].x, g.solids[blk.box_index][0].y, 0)
           - Vec3(blk.root.getX(), blk.root.getY(), 0)).length() < 0.1)
    # Drop it straight onto the plate and confirm the plate responds.
    blk.root.setPos(plate.root.getX(), plate.root.getY(), plate.root.getZ())
    g.move_solid(blk.box_index, blk.root.getPos() + Vec3(0, 0, blk.half.z))
    p.root.setPos(plate.root.getX(), plate.root.getY() - 20.0, 1.0)
    h.step(4)
    check("a block on a plate presses it", plate.pressed)

    # --- Swamp: two levers extend the bridge -------------------------------
    g.load_level(lore.CAMPAIGN_TEMPLATE.index("swamp"))
    h.skip_story()
    h.step(3)
    levers = [it for it in g.interactables if isinstance(it, P.Lever)]
    bridge = next(it for it in g.interactables if isinstance(it, P.Bridge))
    check("the swamp has two levers and a bridge", len(levers) == 2)
    stowed = bridge.root.getPos()
    levers[0].use(g)
    h.step(10)
    check("one lever is not enough", not bridge.extending)
    levers[1].use(g)
    h.step(2)
    check("both levers start the bridge", bridge.extending)
    h.step(180)
    check("the bridge reaches its span",
          (bridge.root.getPos() - bridge.pos).length() < 0.5,
          "%s" % bridge.root.getPos())
    check("it moved from where it was stowed",
          (bridge.root.getPos() - stowed).length() > 5.0)
    check("its collision followed",
          (g.solids[bridge.box_index][0] - bridge.root.getPos()).length() < 0.5)

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

    print("\n[9c] The game drives the audio channels")
    g.load_level(0)
    h.skip_story()
    h.step(2)
    want_music, want_bed = realm_audio(g.level.key)
    check("loading a level selects its theme",
          g.audio.current_music == want_music,
          "%s != %s" % (g.audio.current_music, want_music))
    check("loading a level selects its ambience",
          g.audio.current_ambience == want_bed)
    g.load_level(3)
    h.skip_story()
    h.step(2)
    check("moving to another realm swaps the theme",
          g.audio.current_music == realm_audio(g.level.key)[0])
    check("the player can make her own noise", g.player.audio is not None)
    check("impacts are wired to the fairy's element",
          g.effects.hit_sound is not None)

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
