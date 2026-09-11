#!/usr/bin/env python3
"""Render a close-up of every fairy, for checking the character models."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panda3d.core import ClockObject, Filename, loadPrcFileData

loadPrcFileData("cap", "\n".join([
    "window-type offscreen", "load-display p3tinydisplay",
    "audio-library-name null", "win-size 420 620",
    "default-directnotify-level error",
]))

from direct.showbase.ShowBase import ShowBase                  # noqa: E402
from panda3d.core import AmbientLight, DirectionalLight, Vec4  # noqa: E402

from winx3d import characters                                  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "screenshots")


def main(close=False):
    base = ShowBase()
    base.disableMouse()
    base.setBackgroundColor(0.16, 0.14, 0.24)
    base.render.setShaderOff()
    amb = AmbientLight("a")
    amb.setColor(Vec4(0.62, 0.62, 0.70, 1))
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

    for i, spec in enumerate(characters.ROSTER):
        model, parts = characters.build_fairy(spec)
        model.reparentTo(base.render)
        model.setPos(0, 0, 0)
        anim = characters.FairyAnimator(parts)
        anim.update(0.016, 0.0, False, True)
        if close:
            base.camera.setPos(0.0, -2.2, 2.85)
            base.camera.lookAt(0, 0, 2.72)
        else:
            base.camera.setPos(0.6, -6.4, 2.2)
            base.camera.lookAt(0, 0, 1.55)
        for _ in range(3):
            clock.tick()
            base.taskMgr.step()
            base.graphicsEngine.renderFrame()
        name = "fairy-%s%s" % (spec.key, "-face" if close else "")
        base.win.saveScreenshot(
            Filename.fromOsSpecific(os.path.join(OUT, name + ".png")))
        print("  wrote", name + ".png")
        model.removeNode()


if __name__ == "__main__":
    main(close="--face" in sys.argv)
