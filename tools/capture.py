#!/usr/bin/env python3
"""Render reference screenshots of the menus and every level, headlessly.

Uses Panda3D's software rasteriser so it runs on a machine with no GPU.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panda3d.core import ClockObject, Filename, Vec3, loadPrcFileData

W, H = 960, 720
loadPrcFileData("cap", "\n".join([
    "window-type offscreen",
    "load-display p3tinydisplay",
    "audio-library-name null",
    "win-size %d %d" % (W, H),
    "default-directnotify-level error",
]))

from winx3d.app import Game                          # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "screenshots")


def main():
    os.makedirs(OUT, exist_ok=True)
    game = Game(low_detail=False)
    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNonRealTime)
    clock.setDt(1.0 / 60.0)

    def step(n=1):
        for _ in range(n):
            clock.tick()
            game.taskMgr.step()
            game.graphicsEngine.renderFrame()

    def shot(name):
        step(2)
        path = os.path.join(OUT, name + ".png")
        game.win.saveScreenshot(Filename.fromOsSpecific(path))
        print("  wrote", os.path.relpath(path))

    step(3)
    shot("01-title")

    game.menu_index = 0
    game.on_confirm()
    step(20)
    shot("02-character-select")

    from winx3d import characters

    def play():
        n = 0
        while game.state == "story" and n < 80:
            game.on_confirm()
            n += 1
        step(6)

    game.select_index = 0
    game._refresh_select()
    game.on_confirm()
    step(4)
    shot("03-story-chapter1")

    # One shot of every fairy's home realm, at peace and besieged.
    homes = [
        ("bloom",  (0, -34, 1.0),  0.0, -6.0),
        ("stella", (0, -40, 1.0),  0.0, -4.0),
        ("flora",  (0, -42, 1.0),  0.0, -2.0),
        ("musa",   (0, -46, 1.0),  0.0, -3.0),
        ("tecna",  (0, -42, 1.0),  0.0, -2.0),
        ("aisha",  (0, -48, 1.0),  0.0, -3.0),
    ]
    for i, (key, pos, yaw, pitch) in enumerate(homes):
        f = characters.BY_KEY[key]
        for slot, tag in ((0, "home"), (7, "siege")):
            game.start_run(f) if slot == 0 else game.load_level(slot)
            play()
            p = game.player
            p.root.setPos(*pos)
            p.cam_yaw, p.cam_pitch = yaw, pitch
            p.magic = 100.0
            step(30)
            shot("%02d-%s-%s" % (4 + i * 2 + (1 if tag == "siege" else 0),
                                 key, tag))

    def overview(name, level_index, height=95.0, pitch=-55.0, back=70.0):
        game.load_level(level_index)
        play()
        p = game.player
        mid = game.checkpoints[len(game.checkpoints) // 2] \
            if game.checkpoints else p.root.getPos()
        p.root.setPos(mid.x, mid.y - back, mid.z + height)
        p.cam_yaw, p.cam_pitch = 0.0, pitch
        p.vel.z = 0.0
        step(2)
        game.player.update_camera(game.camera, 1.0)
        step(2)
        shot(name)

    overview("29-course-overview", 1)
    overview("30-course-overview-swamp", 2, height=80.0, back=60.0)

    # Puzzles and exploration.
    game.start_run(characters.BY_KEY["bloom"])
    play()
    game.load_level(1)                       # Alfea: the barrier runes
    play()
    p = game.player
    p.root.setPos(-20, -28, 1.0)
    p.cam_yaw, p.cam_pitch = 20.0, -6.0
    step(30)
    shot("24-puzzle-runes")

    tab = next(i for i in game.interactables
               if i.__class__.__name__ == "Tablet")
    p.root.setPos(tab.center().x, tab.center().y - 4.0, 0.0)
    p.cam_yaw, p.cam_pitch = 0.0, -4.0
    step(20)
    shot("25-puzzle-tablet-prompt")
    game.do_interact()
    step(4)
    shot("26-puzzle-reading")
    game.on_confirm()
    step(4)

    # A chest beside the path.
    game.load_level(1)
    play()
    chest = next(i for i in game.interactables
                 if i.__class__.__name__ == "Chest")
    p = game.player
    cp = chest.center()
    off = Vec3(-7.0, -7.0, 0.0)
    p.root.setPos(cp.x + off.x, cp.y + off.y, cp.z - 1.0)
    to = cp - p.center()
    p.cam_yaw = math.degrees(math.atan2(-to.x, to.y))
    p.cam_pitch = -14.0
    step(25)
    shot("31-chest-closed")
    game.do_interact()
    step(20)
    shot("32-chest-open")

    game.load_level(3)                       # Cloud Tower: the chime sequence
    play()
    p = game.player
    p.root.setPos(0, -22, 2.0)
    p.cam_yaw, p.cam_pitch = 0.0, -6.0
    step(30)
    shot("27-puzzle-sequence")

    game.load_level(5)                       # Red Fountain: counterweights
    play()
    p = game.player
    p.root.setPos(0, -22, 1.0)
    p.cam_yaw, p.cam_pitch = 0.0, -8.0
    step(30)
    shot("28-puzzle-blocks")

    # The shared chapters.
    game.start_run(characters.BY_KEY["bloom"])
    play()
    views = [
        ("16-alfea-college",      1, (0, -26, 0.0),  0.0,  -8.0),
        ("17-black-mud-swamp",    2, (0, -30, 1.0),  0.0,  -5.0),
        ("18-cloud-tower",        3, (0, -34, 2.0),  0.0,   0.0),
        ("19-lake-roccaluce",     4, (0, -34, 2.0),  0.0,  -3.0),
        ("20-red-fountain",       5, (0, -34, 2.0),  0.0,  -2.0),
        ("21-pixie-village",      6, (0, -34, 2.0),  0.0,  -4.0),
        ("22-cloud-tower-fallen", 8, (0, -34, 2.0),  0.0,   0.0),
        ("23-battle-of-alfea",    9, (0, -30, 1.0),  0.0,  -4.0),
    ]
    for name, idx, pos, yaw, pitch in views:
        game.load_level(idx)
        play()
        p = game.player
        p.root.setPos(*pos)
        p.cam_yaw, p.cam_pitch = yaw, pitch
        p.magic = 100.0
        step(30)
        shot(name)

    print("done")


if __name__ == "__main__":
    main()
