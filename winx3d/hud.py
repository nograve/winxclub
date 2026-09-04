"""The in-game heads-up display.

Built from flat 2-D cards and text under ``aspect2d`` so it costs almost
nothing to draw and needs no image assets.
"""
from __future__ import annotations

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (CardMaker, NodePath, TextNode, TransparencyAttrib,
                          Vec4)

from . import config as C

FONT_SCALE = 0.055


def card(parent: NodePath, x, y, w, h, color, name="card") -> NodePath:
    """An axis-aligned coloured rectangle anchored at its lower-left corner."""
    cm = CardMaker(name)
    cm.setFrame(0, w, 0, h)
    np = parent.attachNewNode(cm.generate())
    np.setPos(x, 0, y)
    np.setColor(Vec4(*color))
    np.setTransparency(TransparencyAttrib.MAlpha)
    return np


def text(parent, msg, x, y, scale=FONT_SCALE, fg=(1, 1, 1, 1),
         align=TextNode.ALeft, shadow=(0, 0, 0, 0.85)) -> OnscreenText:
    return OnscreenText(text=msg, pos=(x, y), scale=scale, fg=fg,
                        align=align, parent=parent, shadow=shadow,
                        mayChange=True)


class HUD:
    def __init__(self, base) -> None:
        self.base = base
        self.root = base.aspect2d.attachNewNode("hud")
        a = base.getAspectRatio()
        left = -a + 0.06
        right = a - 0.06

        # Opaque backing panels.  Without them a bar can vanish against a
        # same-coloured sky - the magic bar's blue is very close to Alfea's.
        card(self.root, left - 0.03, 0.695, 0.55, 0.265,
             (0.07, 0.05, 0.13, 0.72), "panel_l")
        card(self.root, right - 0.42, 0.735, 0.45, 0.225,
             (0.07, 0.05, 0.13, 0.72), "panel_r")

        # --- health -------------------------------------------------------
        self.heart_bg = []
        self.heart_fg = []
        for i in range(C.MAX_HEALTH):
            x = left + i * 0.075
            self.heart_bg.append(card(self.root, x, 0.86, 0.06, 0.06,
                                      (0.05, 0.03, 0.09, 0.95), "hp_bg"))
            self.heart_fg.append(card(self.root, x + 0.006, 0.866, 0.048,
                                      0.048, (1.0, 0.35, 0.50, 1.0), "hp"))

        # --- magic --------------------------------------------------------
        self.magic_w = 0.46
        card(self.root, left, 0.79, self.magic_w, 0.038,
             (0.05, 0.03, 0.09, 0.95), "mp_bg")
        self.magic_bar = card(self.root, left + 0.004, 0.794,
                              self.magic_w - 0.008, 0.030,
                              (0.40, 0.95, 0.95, 1.0), "mp")
        self.magic_full_x = self.magic_w - 0.008
        self.magic_label = text(self.root, "MAGIC", left + 0.008, 0.798,
                                0.030, (1, 1, 1, 0.85))

        # --- transformation prompt ---------------------------------------
        self.enchantix = text(self.root, "", left, 0.72, 0.042,
                              (1.0, 0.92, 0.45, 1))

        # --- score / gems / lives -----------------------------------------
        self.score = text(self.root, "", right, 0.88, 0.048, (1, 1, 1, 1),
                          TextNode.ARight)
        self.gems = text(self.root, "", right, 0.82, 0.042,
                         (0.65, 0.90, 1.0, 1), TextNode.ARight)
        self.lives = text(self.root, "", right, 0.76, 0.042,
                          (1.0, 0.60, 0.70, 1), TextNode.ARight)

        # --- objective ----------------------------------------------------
        self.objective = text(self.root, "", 0, -0.92, 0.040,
                              (1, 1, 1, 0.92), TextNode.ACenter)

        # --- boss bar -----------------------------------------------------
        self.boss_root = self.root.attachNewNode("boss")
        card(self.boss_root, -0.62, 0.70, 1.24, 0.045,
             (0.05, 0.03, 0.09, 0.92), "boss_bg")
        self.boss_bar = card(self.boss_root, -0.615, 0.7045, 1.23, 0.036,
                             (0.65, 0.85, 1.0, 1.0), "boss")
        self.boss_name = text(self.boss_root, "", 0, 0.755, 0.040,
                              (0.85, 0.92, 1.0, 1), TextNode.ACenter)
        self.boss_root.hide()

        # --- centre banner ------------------------------------------------
        self.banner = text(self.root, "", 0, 0.12, 0.075,
                           (1, 1, 1, 1), TextNode.ACenter)
        self.banner_sub = text(self.root, "", 0, 0.03, 0.045,
                               (1, 0.95, 0.80, 1), TextNode.ACenter)
        self.banner_timer = 0.0

        # --- reticle ------------------------------------------------------
        self.reticle = NodePath("reticle")
        self.reticle.reparentTo(base.aspect2d)
        card(self.reticle, -0.016, -0.0025, 0.032, 0.005,
             (1, 1, 1, 0.55), "rh")
        card(self.reticle, -0.0025, -0.016, 0.005, 0.032,
             (1, 1, 1, 0.55), "rv")

    # -- API ----------------------------------------------------------------
    def show_banner(self, title: str, sub: str = "", seconds: float = 2.6)\
            -> None:
        self.banner.setText(title)
        self.banner_sub.setText(sub)
        self.banner_timer = seconds

    def set_objective(self, msg: str) -> None:
        self.objective.setText(msg)

    def update(self, dt: float, player, boss=None) -> None:
        if self.banner_timer > 0.0:
            self.banner_timer -= dt
            if self.banner_timer <= 0.0:
                self.banner.setText("")
                self.banner_sub.setText("")

        full = int(player.health)
        partial = player.health - full
        for i, fg in enumerate(self.heart_fg):
            if i < full:
                fg.show()
                fg.setScale(1.0)
                fg.setColor(1.0, 0.35, 0.50, 1.0)
            elif i == full and partial > 0.05:
                fg.show()
                fg.setScale(partial, 1.0, 1.0)
                fg.setColor(1.0, 0.55, 0.35, 1.0)
            else:
                fg.hide()

        frac = max(0.0, min(1.0, player.magic / C.MAX_MAGIC))
        self.magic_bar.setScale(max(0.001, frac), 1.0, 1.0)
        if player.transformed:
            self.magic_bar.setColor(1.0, 0.85, 0.35, 1.0)
            self.magic_label.setText("ENCHANTIX  %0.0fs" % player.transform_time)
            self.magic_bar.setScale(
                max(0.001, player.transform_time / C.TRANSFORM_TIME), 1, 1)
            self.enchantix.setText("")
        else:
            self.magic_bar.setColor(0.40, 0.95, 0.95, 1.0)
            self.magic_label.setText("MAGIC")
            self.enchantix.setText(
                "[F]  ENCHANTIX READY" if player.magic >= C.TRANSFORM_COST
                else "")

        self.score.setText("SCORE  %06d" % player.score)
        self.gems.setText("GEMS  %d" % player.gems)
        self.lives.setText("LIVES  %d" % player.lives)

        if boss is not None and boss.alive:
            self.boss_root.show()
            self.boss_name.setText("ICY OF CLOUD TOWER")
            self.boss_bar.setScale(
                max(0.001, boss.health / boss.max_health), 1.0, 1.0)
        else:
            self.boss_root.hide()

    def set_visible(self, on: bool) -> None:
        (self.root.show if on else self.root.hide)()
        (self.reticle.show if on else self.reticle.hide)()

    def destroy(self) -> None:
        self.root.removeNode()
        self.reticle.removeNode()
