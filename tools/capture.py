#!/usr/bin/env python3
"""Render reference screenshots of the menus and every level, headlessly.

Uses Panda3D's software rasteriser so it runs on a machine with no GPU.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panda3d.core import ClockObject, Filename, loadPrcFileData

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

    game.select_index = 0
    game._refresh_select()
    game.on_confirm()
    step(4)
    shot("03-story-chapter1")          # chapter dialogue over the world

    def play():
        n = 0
        while game.state == "story" and n < 60:
            game.on_confirm()
            n += 1
        step(6)

    play()
    p = game.player
    p.root.setPos(0, -34, 1.0)
    p.cam_yaw, p.cam_pitch = 0.0, -6.0
    step(30)
    shot("04-gardenia-park")

    views = [
        ("05-alfea-college",      1, (0, -26, 0.0),  0.0,  -8.0),
        ("06-black-mud-swamp",    2, (0, -30, 1.0),  0.0,  -5.0),
        ("07-cloud-tower",        3, (0, -34, 2.0),  0.0,   0.0),
        ("08-lake-roccaluce",     4, (0, -34, 2.0),  0.0,  -3.0),
        ("09-red-fountain",       5, (0, -34, 2.0),  0.0,  -2.0),
        ("10-pixie-village",      6, (0, -34, 2.0),  0.0,  -4.0),
        ("11-cloud-tower-fallen", 7, (0, -34, 2.0),  0.0,   0.0),
        ("12-battle-of-alfea",    8, (0, -30, 1.0),  0.0,  -4.0),
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
