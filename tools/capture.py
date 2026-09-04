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
    step(5)

    # Level 1, looking across the plaza at the school.
    p = game.player
    p.root.setPos(0, -26, 0)
    p.cam_yaw, p.cam_pitch = 0.0, -8.0
    step(30)
    shot("03-alfea-courtyard")

    # Airborne over the terraces, mid-fight.
    p.root.setPos(-30, -6, 12.0)
    p.cam_yaw, p.cam_pitch = 300.0, -18.0
    p.magic = 100.0
    p.begin_transform(game.effects)
    for _ in range(3):
        p._fire(game.effects, game.enemy_list)
        step(4)
    step(6)
    shot("04-enchantix-flight")

    game.load_level(1)
    step(5)
    p = game.player
    p.root.setPos(0, -30, 1.0)
    p.cam_yaw, p.cam_pitch = 0.0, -4.0
    step(30)
    shot("05-whispering-wood")

    game.load_level(2)
    step(5)
    p = game.player
    p.root.setPos(0, -26, 6.0)
    p.cam_yaw, p.cam_pitch = 0.0, -2.0
    game.boss.root.setPos(0, 4, 9.0)
    step(40)
    shot("06-cloud-tower-boss")
    print("done")


if __name__ == "__main__":
    main()
