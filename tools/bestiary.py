#!/usr/bin/env python3
"""Render every enemy model side by side, for checking the bestiary."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panda3d.core import ClockObject, Filename, loadPrcFileData

loadPrcFileData("cap", "\n".join([
    "window-type offscreen", "load-display p3tinydisplay",
    "audio-library-name null", "win-size 380 560",
    "default-directnotify-level error",
]))

from direct.showbase.ShowBase import ShowBase                  # noqa: E402
from panda3d.core import (AmbientLight, DirectionalLight,      # noqa: E402
                          NodePath, Vec3, Vec4)

from winx3d import enemies as E                                # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "screenshots")
FRAMING = {"ghoul": 6.5, "knut": 11.0, "decay": 9.0, "troll": 11.0,
           "wisp": 4.5, "creeper": 5.5, "icy": 9.5, "darcy": 9.5,
           "stormy": 9.5}


def main():
    base = ShowBase()
    base.disableMouse()
    base.setBackgroundColor(0.16, 0.14, 0.24)
    base.render.setShaderOff()
    amb = AmbientLight("a")
    amb.setColor(Vec4(0.60, 0.60, 0.68, 1))
    base.render.setLight(base.render.attachNewNode(amb))
    sun = DirectionalLight("s")
    sun.setColor(Vec4(1.0, 0.97, 0.92, 1))
    np = base.render.attachNewNode(sun)
    np.setHpr(-35, -35, 0)
    base.render.setLight(np)

    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNonRealTime)
    clock.setDt(1.0 / 60.0)
    os.makedirs(OUT, exist_ok=True)
    root = NodePath("bestiary")
    root.reparentTo(base.render)

    for key in sorted(E.KINDS):
        foe = E.spawn(key, root, Vec3(0, 0, 0), [])
        d = FRAMING.get(key, 8.0)
        base.camera.setPos(d * 0.25, -d, d * 0.42)
        base.camera.lookAt(0, 0, d * 0.22)
        for _ in range(3):
            clock.tick()
            base.taskMgr.step()
            base.graphicsEngine.renderFrame()
        base.win.saveScreenshot(
            Filename.fromOsSpecific(os.path.join(OUT, "foe-%s.png" % key)))
        print("  wrote foe-%s.png" % key)
        foe.root.removeNode()


if __name__ == "__main__":
    main()
