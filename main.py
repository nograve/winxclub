#!/usr/bin/env python3
"""Winx Club: Magic of Alfea — launcher.

Parses the command line, configures Panda3D before the engine starts up (a
number of settings can only be applied at that point), then hands over to the
game.  Run ``python3 main.py --help`` for the options.
"""
from __future__ import annotations

import argparse
import sys


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="winx",
        description="Winx Club: Magic of Alfea - a 3D fairy action adventure.")
    p.add_argument("--windowed", action="store_true",
                   help="force windowed mode (the default)")
    p.add_argument("--fullscreen", action="store_true",
                   help="start fullscreen")
    p.add_argument("--width", type=int, default=None, help="window width")
    p.add_argument("--height", type=int, default=None, help="window height")
    p.add_argument("--low", action="store_true",
                   help="low-detail mode: shorter view distance, no "
                        "multisampling, smaller default window")
    p.add_argument("--software", action="store_true",
                   help="use Panda3D's software renderer (no GPU needed)")
    p.add_argument("--no-audio", action="store_true", help="disable all audio")
    p.add_argument("--no-vsync", action="store_true",
                   help="do not wait for vertical sync")
    p.add_argument("--headless", action="store_true",
                   help=argparse.SUPPRESS)   # used by the test harness
    return p.parse_args(argv)


def configure(args) -> None:
    from panda3d.core import loadPrcFileData

    lines = [
        "window-title Winx Club: Magic of Alfea",
        "notify-level-util error",
        "default-directnotify-level warning",
        "textures-power-2 down",
        "text-minfilter linear",
        "model-cache-dir",          # nothing to cache: all geometry is code
        "sync-video %d" % (0 if args.no_vsync else 1),
    ]
    if args.low:
        w = args.width or 640
        h = args.height or 480
        lines += ["multisamples 0", "framebuffer-multisample 0"]
    else:
        w = args.width or 1024
        h = args.height or 768
    lines.append("win-size %d %d" % (w, h))
    lines.append("fullscreen %d" % (1 if args.fullscreen else 0))

    if args.software:
        # p3tinydisplay is Panda3D's built-in software rasteriser; it needs no
        # OpenGL at all, which keeps the game running on very old or
        # driver-less machines.
        lines.append("load-display p3tinydisplay")
    else:
        # Try hardware first, fall back to software rather than failing.
        lines.append("load-display pandagl")
        lines.append("aux-display pandadx9")
        lines.append("aux-display p3tinydisplay")

    if args.no_audio:
        lines.append("audio-library-name null")
    if args.headless:
        lines.append("window-type offscreen")
        lines.append("load-display p3tinydisplay")
        lines.append("audio-library-name null")

    loadPrcFileData("winx-config", "\n".join(lines))


def main(argv=None) -> int:
    args = parse_args(argv)
    configure(args)

    # Synthesising the audio takes a couple of seconds the very first time.
    if not args.no_audio and not args.headless:
        from winx3d import audio
        import os
        if not os.path.exists(os.path.join(
                audio.C.user_dir(), "sfx-v%d" % audio.CACHE_VERSION,
                "music_alfea.wav")):
            print("First run: generating sound effects and music...")
            audio.ensure_sounds()

    from winx3d.app import Game
    game = Game(low_detail=args.low)
    game.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
