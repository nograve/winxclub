"""Application shell: window setup, screens, level flow and the frame loop."""
from __future__ import annotations

import math
import sys

from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (AmbientLight, CardMaker, ClockObject,
                          DirectionalLight, Fog,
                          NodePath, TextNode, TransparencyAttrib, Vec3, Vec4,
                          WindowProperties)

from . import characters, config as C, enemies as E, lore
from .audio import Audio
from .effects import EffectSystem, Pickup
from .geometry import MeshBuilder, shade
from .hud import HUD, card, text
from .player import Player
from .world import LEVELS, WorldBuilder

TITLE_COLOR = (1.0, 0.55, 0.78, 1)

# Three synthesised tracks cover the campaign: a bright one for the safe
# places, a darker one for the wild ones, and a driving one for the Trix.
MUSIC_FOR = {
    "gardenia": "music_alfea", "alfea": "music_alfea",
    "pixievillage": "music_alfea",
    "swamp": "music_wood", "roccaluce": "music_wood",
    "redfountain": "music_wood",
    "cloudtower": "music_tower", "siege_cloudtower": "music_tower",
    "battle_alfea": "music_tower",
}


def _portal_model(color: Vec4) -> NodePath:
    """A free-standing ring the player steps into to finish a level."""
    mb = MeshBuilder()
    segs = 20
    for i in range(segs):
        a = math.tau * i / segs
        mb.sphere((math.cos(a) * 2.6, math.sin(a) * 2.6, 2.8), 0.45,
                  shade(color, 0.8 + 0.4 * (i % 2)), segments=7, rings=5)
    disc = MeshBuilder()
    disc.cylinder((0, 0, 0.6), 2.4, 2.4, 4.4,
                  Vec4(color[0], color[1], color[2], 0.35), segments=18,
                  cap_top=False, cap_bottom=False)
    np = NodePath("portal")
    ring = mb.build("portal_ring")
    ring.setLightOff()
    ring.reparentTo(np)
    d = disc.build("portal_disc")
    d.setTransparency(TransparencyAttrib.MAlpha)
    d.setTwoSided(True)
    d.setDepthWrite(False)
    d.setLightOff()
    d.reparentTo(np)
    return np


class Game(ShowBase):
    def __init__(self, low_detail: bool = False) -> None:
        ShowBase.__init__(self)
        self.disableMouse()
        self.low_detail = low_detail
        self.profile = C.load_profile()

        props = WindowProperties()
        props.setTitle("%s  v%s" % (C.TITLE, C.VERSION))
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)

        self.setBackgroundColor(0.1, 0.1, 0.16)
        self.camLens.setFov(70)
        self.camLens.setNear(0.4)
        self.camLens.setFar(900 if not low_detail else 420)
        self.render.setShaderOff()          # fixed-function only, by design

        self.globalClock = ClockObject.getGlobalClock()
        self.audio = Audio(self, self.profile)

        # --- scene roots ---------------------------------------------------
        self.world_root = self.render.attachNewNode("world")
        self.fx_root = self.render.attachNewNode("fx")
        self.effects = EffectSystem(self.fx_root)

        self._setup_lights()

        # --- state ---------------------------------------------------------
        self.state = "title"
        self.screen = NodePath("screen")
        self.screen.reparentTo(self.aspect2d)
        # Holds the world-space backdrop used by the character-select screen.
        self.screen_bg = NodePath("screen_bg")
        self.screen_bg.reparentTo(self.render)
        self.hud = None
        self.player = None
        self.level = None
        self.level_index = 0
        self.level_node = None
        self.enemy_list: list = []
        self.pickups: list = []
        self.portal = None
        self.portal_active = False
        self.bosses = []
        self.chapter = None
        self.story_lines = []
        self.story_index = 0
        self.story_chapter = None
        self.story_after = "play"
        self.time = 0.0
        self.level_time = 0.0
        self.paused = False
        self.death_timer = 0.0
        self.finish_timer = 0.0
        self.menu_index = 0
        self.select_index = max(0, next(
            (i for i, f in enumerate(characters.ROSTER)
             if f.key == self.profile.get("last_fairy")), 0))
        self.preview = None
        self.preview_anim = None
        self.mouse_look = bool(self.profile.get("mouse_look", True))
        self._mouse_ready = False

        self.keys = {k: False for k in (
            "forward", "back", "left", "right", "run", "jump", "attack",
            "special", "cam_left", "cam_right", "cam_up", "cam_down")}
        self.keys["jump_pressed"] = False
        self.keys["transform_pressed"] = False

        self._bind_keys()
        self.show_title()
        self.taskMgr.add(self._frame, "frame")

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _setup_lights(self) -> None:
        self.ambient = AmbientLight("ambient")
        self.ambient.setColor(Vec4(0.55, 0.57, 0.66, 1))
        self.ambient_np = self.render.attachNewNode(self.ambient)
        self.render.setLight(self.ambient_np)

        self.sun = DirectionalLight("sun")
        self.sun.setColor(Vec4(1.0, 0.97, 0.9, 1))
        self.sun_np = self.render.attachNewNode(self.sun)
        self.sun_np.setHpr(-40, -55, 0)
        self.render.setLight(self.sun_np)

        self.fog = Fog("fog")
        self.fog.setColor(0.7, 0.85, 0.97)
        self.fog.setExpDensity(0.0022 if not self.low_detail else 0.0045)

    # Held-movement bindings.  Every physical key is accepted exactly once
    # and dispatched from there: Panda3D's ``accept`` replaces any previous
    # handler for an event, so binding a key twice would silently drop the
    # first meaning.
    HELD = {
        "w": "forward", "arrow_up": "forward",
        "s": "back", "arrow_down": "back",
        "a": "left", "arrow_left": "left",
        "d": "right", "arrow_right": "right",
        "shift": "run", "lshift": "run", "rshift": "run",
        "space": "jump",
        "j": "attack", "mouse1": "attack", "control": "attack",
        "lcontrol": "attack", "rcontrol": "attack",
        "k": "special", "mouse3": "special",
        "q": "cam_left", "e": "cam_right",
        "r": "cam_up", "v": "cam_down",
    }
    # Menu navigation, applied only while a menu screen is up.
    MENU_VERTICAL = {"w": -1, "arrow_up": -1, "s": 1, "arrow_down": 1}
    MENU_HORIZONTAL = {"a": -1, "arrow_left": -1, "d": 1, "arrow_right": 1}

    def _bind_keys(self) -> None:
        keys = set(self.HELD) | set(self.MENU_VERTICAL) | \
            set(self.MENU_HORIZONTAL) | {"f"}
        for key in keys:
            self.accept(key, self._on_key_down, [key])
            self.accept(key + "-up", self._on_key_up, [key])
        self.accept("escape", self.on_escape)
        self.accept("enter", self.on_confirm)
        self.accept("tab", self.toggle_mouse_look)
        self.accept("m", self.toggle_music)
        self.accept("n", self.toggle_sfx)
        self.accept("f12", self.screenshot_now)

    def _on_key_down(self, key: str) -> None:
        in_menu = self.state in ("title", "options", "select", "help",
                                 "results", "gameover", "paused", "story")
        if in_menu:
            if key in self.MENU_VERTICAL:
                self._menu_move(self.MENU_VERTICAL[key])
            if key in self.MENU_HORIZONTAL:
                self._menu_side(self.MENU_HORIZONTAL[key])
            if key == "q" and self.state == "paused":
                self._quit_to_title()
            return
        action = self.HELD.get(key)
        if action:
            self.keys[action] = True
        if key == "space":
            self.keys["jump_pressed"] = True
        elif key == "f":
            self.keys["transform_pressed"] = True

    def _on_key_up(self, key: str) -> None:
        action = self.HELD.get(key)
        if action:
            self.keys[action] = False

    def _release_all(self) -> None:
        """Drop every held key — used when leaving gameplay for a menu."""
        for k in self.keys:
            self.keys[k] = False


    # ------------------------------------------------------------------
    # screens
    # ------------------------------------------------------------------
    def clear_screen(self) -> None:
        self.screen.removeNode()
        self.screen = NodePath("screen")
        self.screen.reparentTo(self.aspect2d)
        self.screen_bg.removeNode()
        self.screen_bg = NodePath("screen_bg")
        self.screen_bg.reparentTo(self.render)
        if self.preview is not None:
            self.preview.removeNode()
            self.preview = None
            self.preview_anim = None

    MENU_BG = (0.11, 0.08, 0.19)

    def _title_backdrop(self, behind_preview: bool = False) -> None:
        """Darken the screen behind a menu.

        Normally that is a full-screen card in front of everything.  The
        character-select screen shows a live 3-D model, though, and no 2-D
        layer reliably draws behind the 3-D scene - so there the backdrop is
        a large card placed in the world, behind the preview itself.
        """
        if behind_preview:
            cm = CardMaker("backdrop")
            cm.setFrame(-60, 60, -34, 34)
            np = self.screen_bg.attachNewNode(cm.generate())
            np.setPos(0, 26, -400)
            np.setColor(Vec4(*(self.MENU_BG + (1.0,))))
            np.setLightOff()
            np.setTwoSided(True)
        else:
            a = self.getAspectRatio()
            card(self.screen, -a, -1, a * 2, 2, (0.10, 0.07, 0.18, 0.94),
                 "dim")

    def show_title(self) -> None:
        self.state = "title"
        self.set_playing_visuals(False)
        self._release_all()
        self.clear_screen()
        self._title_backdrop()
        self.audio.play_music("music_menu")
        text(self.screen, "WINX CLUB", 0, 0.62, 0.16, TITLE_COLOR,
             TextNode.ACenter)
        text(self.screen, "Magic of Alfea", 0, 0.49, 0.075,
             (1, 0.90, 0.55, 1), TextNode.ACenter)
        self.menu_items = ["Start Adventure", "How to Play", "Options", "Quit"]
        self.menu_index = 0
        self.menu_text = []
        for i, item in enumerate(self.menu_items):
            self.menu_text.append(text(self.screen, item, 0, 0.20 - i * 0.11,
                                       0.062, (1, 1, 1, 1), TextNode.ACenter))
        text(self.screen,
             "Best score  %06d          Levels cleared  %d/%d"
             % (self.profile.get("high_score", 0),
                self.profile.get("levels_cleared", 0), len(LEVELS)),
             0, -0.62, 0.040, (0.80, 0.85, 1.0, 1), TextNode.ACenter)
        text(self.screen, "Arrow keys / W S to choose   -   Enter to confirm",
             0, -0.78, 0.042, (1, 1, 1, 0.75), TextNode.ACenter)
        self._refresh_menu()

    def _refresh_menu(self) -> None:
        for i, t in enumerate(getattr(self, "menu_text", [])):
            if i == self.menu_index:
                t.setFg((1.0, 0.85, 0.35, 1))
                t.setText("> " + self.menu_items[i] + " <")
            else:
                t.setFg((1, 1, 1, 0.85))
                t.setText(self.menu_items[i])

    def show_help(self) -> None:
        self.state = "help"
        self.clear_screen()
        self._title_backdrop()
        text(self.screen, "HOW TO PLAY", 0, 0.72, 0.085, TITLE_COLOR,
             TextNode.ACenter)
        lines = [
            ("W A S D / Arrows", "Move (relative to the camera)"),
            ("Mouse  or  Q / E", "Swing the camera around"),
            ("Shift", "Run"),
            ("Space", "Jump  -  hold in the air to fly"),
            ("J  or  Left mouse", "Magic bolt"),
            ("K  or  Right mouse", "Magic blast (close range, costly)"),
            ("F", "Enchantix, once the magic meter is full"),
            ("Tab / M / N", "Mouse look / music / sound effects"),
            ("Esc", "Pause"),
        ]
        for i, (key, what) in enumerate(lines):
            y = 0.50 - i * 0.105
            text(self.screen, key, -0.05, y, 0.048, (1.0, 0.88, 0.45, 1),
                 TextNode.ARight)
            text(self.screen, what, 0.05, y, 0.048, (1, 1, 1, 0.92),
                 TextNode.ALeft)
        text(self.screen, "Flying drains magic. So does every spell -"
             " let it refill between fights.", 0, -0.55, 0.040,
             (0.85, 0.92, 1.0, 1), TextNode.ACenter)
        text(self.screen, "Enter or Esc to go back", 0, -0.78, 0.044,
             (1, 1, 1, 0.75), TextNode.ACenter)

    def show_options(self) -> None:
        self.state = "options"
        self.clear_screen()
        self._title_backdrop()
        text(self.screen, "OPTIONS", 0, 0.60, 0.085, TITLE_COLOR,
             TextNode.ACenter)
        self.menu_items = ["Music", "Sound effects", "Mouse look", "Back"]
        self.menu_index = 0
        self.menu_text = []
        for i, item in enumerate(self.menu_items):
            self.menu_text.append(text(self.screen, item, 0, 0.30 - i * 0.12,
                                       0.058, (1, 1, 1, 1), TextNode.ACenter))
        text(self.screen, "Left / Right to change, Enter to confirm",
             0, -0.70, 0.042, (1, 1, 1, 0.75), TextNode.ACenter)
        self._refresh_options()

    def _refresh_options(self) -> None:
        vals = ["ON" if self.profile.get("music", True) else "OFF",
                "ON" if self.profile.get("sound", True) else "OFF",
                "ON" if self.mouse_look else "OFF", ""]
        for i, t in enumerate(self.menu_text):
            label = self.menu_items[i]
            if vals[i]:
                label = "%s   %s" % (label, vals[i])
            sel = i == self.menu_index
            t.setText(("> %s <" % label) if sel else label)
            t.setFg((1.0, 0.85, 0.35, 1) if sel else (1, 1, 1, 0.85))

    # ------------------------------------------------------------------
    # story
    # ------------------------------------------------------------------
    def show_story(self, chapter, lines, after: str) -> None:
        """Play a chapter's dialogue, one line at a time, over the world."""
        self.state = "story"
        self.story_lines = list(lines)
        self.story_index = 0
        self.story_chapter = chapter
        self.story_after = after
        self._release_all()
        if self.hud is not None:
            self.hud.set_visible(False)
        self._apply_mouse_mode()
        self._render_story()

    def _render_story(self) -> None:
        self.clear_screen()
        ch = self.story_chapter
        a = self.getAspectRatio()
        # Dim the top of the screen a little, the dialogue box a lot.
        card(self.screen, -a, -1.0, a * 2, 0.68, (0.06, 0.05, 0.12, 0.90),
             "story_box")
        card(self.screen, -a, 0.62, a * 2, 0.38, (0.06, 0.05, 0.12, 0.72),
             "story_head")

        text(self.screen, "CHAPTER %d" % ch.number, 0, 0.85, 0.046,
             (1.0, 0.80, 0.40, 1), TextNode.ACenter)
        text(self.screen, ch.title.upper(), 0, 0.75, 0.070, TITLE_COLOR,
             TextNode.ACenter)
        text(self.screen, lore.REALMS.get(ch.realm, ""), 0, 0.67, 0.040,
             (0.80, 0.86, 0.98, 1), TextNode.ACenter)

        key, line = self.story_lines[self.story_index]
        sp = lore.speaker(key)
        if sp.name:
            text(self.screen, sp.name.upper(), -a + 0.10, -0.44, 0.056,
                 sp.color, TextNode.ALeft)
            if sp.title:
                text(self.screen, sp.title, -a + 0.10, -0.515, 0.034,
                     (0.78, 0.80, 0.88, 1), TextNode.ALeft)
            # A colour swatch so each speaker is identifiable at a glance.
            card(self.screen, -a + 0.035, -0.525, 0.045, 0.135,
                 (sp.color[0], sp.color[1], sp.color[2], 1.0), "swatch")
        # Body text wraps downward, so it starts high enough in the box that
        # three wrapped lines still clear the bottom of the screen.
        body_y = -0.62 if sp.name else -0.52
        text(self.screen, line, -a + 0.10, body_y, 0.050,
             (1, 1, 1, 0.96) if sp.name else (0.86, 0.90, 1.0, 0.96),
             TextNode.ALeft, wordwrap=(a * 2 - 0.22) / 0.050)

        text(self.screen, "%d / %d      Enter to continue"
             % (self.story_index + 1, len(self.story_lines)),
             a - 0.10, -0.92, 0.038, (1, 1, 1, 0.65), TextNode.ARight)

    def _advance_story(self) -> None:
        self.story_index += 1
        if self.story_index < len(self.story_lines):
            self.audio.play("menu")
            self._render_story()
            return
        if self.story_after == "play":
            self.begin_play()
        else:
            self.show_results()

    def fairy_unlocked(self, f) -> bool:
        """Aisha of Andros joins the Winx in their second year, so she is
        locked until the first-year campaign has been cleared once."""
        return f.season <= 1 or \
            self.profile.get("levels_cleared", 0) >= len(LEVELS)

    def show_select(self) -> None:
        self.state = "select"
        self.clear_screen()
        self._title_backdrop(behind_preview=True)
        text(self.screen, "CHOOSE YOUR FAIRY", 0, 0.89, 0.070, TITLE_COLOR,
             TextNode.ACenter)
        self.sel_name = text(self.screen, "", 0, -0.30, 0.075,
                             (1, 1, 1, 1), TextNode.ACenter)
        self.sel_element = text(self.screen, "", 0, -0.40, 0.048,
                                (1.0, 0.88, 0.45, 1), TextNode.ACenter)
        self.sel_blurb = text(self.screen, "", 0, -0.50, 0.042,
                              (1, 1, 1, 0.90), TextNode.ACenter)
        self.sel_stats = text(self.screen, "", 0, -0.60, 0.040,
                              (0.75, 0.90, 1.0, 1), TextNode.ACenter)
        self.sel_row = []
        n = len(characters.ROSTER)
        for i, f in enumerate(characters.ROSTER):
            # Each chip hangs off a pivot at its own centre so highlighting it
            # scales it in place instead of growing it off to one side.
            pivot = self.screen.attachNewNode("chip_" + f.key)
            pivot.setPos((i - (n - 1) * 0.5) * 0.28, 0, 0.76)
            card(pivot, -0.115, -0.055, 0.23, 0.11,
                 (f.dress[0], f.dress[1], f.dress[2], 1.0), "chip")
            card(pivot, -0.128, -0.068, 0.256, 0.136,
                 (1.0, 1.0, 1.0, 0.30), "chip_edge").setBin("fixed", -1)
            self.sel_row.append(pivot)
        text(self.screen, "Left / Right to browse   -   Enter to begin"
             "   -   Esc to go back", 0, -0.80, 0.042, (1, 1, 1, 0.75),
             TextNode.ACenter)
        self._refresh_select()

    def _refresh_select(self) -> None:
        f = characters.ROSTER[self.select_index]
        unlocked = self.fairy_unlocked(f)
        self.sel_name.setText(f.name.upper() if unlocked else "? ? ?")
        self.sel_element.setText(
            "Fairy of the %s   -   %s" % (f.element, lore.REALMS.get(
                f.realm, "").split(" - ")[-1])
            if unlocked else "Joins the Winx in their second year")
        self.sel_blurb.setText(
            f.blurb if unlocked
            else "Clear the first-year campaign to unlock Aisha.")
        bolts = "%d bolt%s" % (f.bolts, "" if f.bolts == 1 else "s")
        self.sel_stats.setText(
            "Speed %s    Power %s    Magic %s    %s"
            % (self._pips(f.speed), self._pips(f.power),
               self._pips(f.magic_rate), bolts))
        for i, chip in enumerate(self.sel_row):
            sel = i == self.select_index
            locked = not self.fairy_unlocked(characters.ROSTER[i])
            chip.setScale(1.22 if sel else 0.94)
            if locked:
                chip.setColorScale(0.28, 0.28, 0.34, 1.0 if sel else 0.5)
            else:
                chip.setColorScale(1.0, 1.0, 1.0, 1.0 if sel else 0.5)

        if self.preview is not None:
            self.preview.removeNode()
        model, parts = characters.build_fairy(f, scale=1.0)
        if not unlocked:
            model.setColorScale(0.16, 0.15, 0.22, 1.0)   # silhouette only
        self.preview = NodePath("preview")
        self.preview.reparentTo(self.render)
        model.reparentTo(self.preview)
        self.preview_anim = characters.FairyAnimator(parts)
        # Park the preview well away from any level and frame it from
        # slightly below, so the fairy sits above the description text.
        self.preview.setPos(0, 0, -400)
        self.camera.setPos(0, -8.4, -397.2)
        self.camera.lookAt(0, 0, -398.9)

    @staticmethod
    def _pips(value: float) -> str:
        n = max(1, min(5, int(round(value * 3.2))))
        return "*" * n + "-" * (5 - n)

    # ------------------------------------------------------------------
    # menu input
    # ------------------------------------------------------------------
    def _menu_move(self, delta: int) -> None:
        if self.state in ("title", "options"):
            self.menu_index = (self.menu_index + delta) % len(self.menu_items)
            self.audio.play("menu")
            (self._refresh_options if self.state == "options"
             else self._refresh_menu)()

    def _menu_side(self, delta: int) -> None:
        if self.state == "select":
            self.select_index = (self.select_index + delta) % \
                len(characters.ROSTER)
            self.audio.play("menu")
            self._refresh_select()
        elif self.state == "options":
            key = ("music", "sound", None, None)[self.menu_index]
            if key:
                self.profile[key] = not self.profile.get(key, True)
                (self.audio.set_music if key == "music"
                 else self.audio.set_sfx)(self.profile[key])
            elif self.menu_index == 2:
                self.mouse_look = not self.mouse_look
                self.profile["mouse_look"] = self.mouse_look
                self._apply_mouse_mode()
            C.save_profile(self.profile)
            self.audio.play("menu")
            self._refresh_options()

    def on_confirm(self) -> None:
        if self.state == "story":
            self._advance_story()
        elif self.state == "title":
            choice = self.menu_items[self.menu_index]
            self.audio.play("menu")
            if choice == "Start Adventure":
                self.show_select()
            elif choice == "How to Play":
                self.show_help()
            elif choice == "Options":
                self.show_options()
            else:
                self.quit()
        elif self.state == "select":
            f = characters.ROSTER[self.select_index]
            if not self.fairy_unlocked(f):
                self.audio.play("hurt")
                return
            self.profile["last_fairy"] = f.key
            C.save_profile(self.profile)
            self.start_run(f)
        elif self.state in ("help",):
            self.show_title()
        elif self.state == "options":
            if self.menu_items[self.menu_index] == "Back":
                self.show_title()
            else:
                self._menu_side(1)
        elif self.state == "results":
            self.advance_level()
        elif self.state == "gameover":
            self.show_title()
        elif self.state == "paused":
            self.toggle_pause()

    def on_escape(self) -> None:
        if self.state == "story":
            # Skip the rest of this chapter's dialogue.
            self.story_index = len(self.story_lines) - 1
            self._advance_story()
        elif self.state == "playing":
            self.toggle_pause()
        elif self.state == "paused":
            self.toggle_pause()
        elif self.state in ("help", "options", "select"):
            self.show_title()
        elif self.state == "title":
            self.quit()
        elif self.state in ("results", "gameover"):
            self.end_run()
            self.show_title()

    def quit(self) -> None:
        C.save_profile(self.profile)
        sys.exit(0)

    # ------------------------------------------------------------------
    # options toggles
    # ------------------------------------------------------------------
    def toggle_music(self) -> None:
        self.profile["music"] = not self.profile.get("music", True)
        self.audio.set_music(self.profile["music"])
        C.save_profile(self.profile)

    def toggle_sfx(self) -> None:
        self.profile["sound"] = not self.profile.get("sound", True)
        self.audio.set_sfx(self.profile["sound"])
        C.save_profile(self.profile)

    def toggle_mouse_look(self) -> None:
        self.mouse_look = not self.mouse_look
        self.profile["mouse_look"] = self.mouse_look
        C.save_profile(self.profile)
        self._apply_mouse_mode()

    def _apply_mouse_mode(self) -> None:
        if self.win is None or not hasattr(self.win, "requestProperties"):
            return
        props = WindowProperties()
        want = self.mouse_look and self.state == "playing"
        props.setCursorHidden(want)
        self.win.requestProperties(props)
        self._mouse_ready = False

    def screenshot_now(self) -> None:
        try:
            self.screenshot("winx", defaultFilename=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # run / level lifecycle
    # ------------------------------------------------------------------
    def start_run(self, spec) -> None:
        self.spec = spec
        self.level_index = 0
        self.total_score = 0
        self.lives = C.START_LIVES
        self.load_level(0)

    def load_level(self, index: int) -> None:
        self.unload_level()
        self.level_index = index
        level = LEVELS[index]
        self.level = level

        builder = WorldBuilder()
        level.build(builder)
        self.level_node = builder.attach(self.world_root, "level_" + level.key)
        self.solids = builder.boxes
        self.effects.set_solids(self.solids)

        self.setBackgroundColor(level.sky)
        self.fog.setColor(level.fog)
        self.render.setFog(self.fog)
        self.ambient.setColor(level.ambient)
        self.sun.setColor(level.sun)

        keep_score = getattr(self, "total_score", 0)
        keep_lives = getattr(self, "lives", C.START_LIVES)
        self.player = Player(self.world_root, self.spec, self.solids,
                             Vec3(level.start))
        self.player.score = keep_score
        self.player.lives = keep_lives
        self.player.cam_yaw = 0.0

        self.enemy_list = [
            E.spawn(s.kind, self.world_root, Vec3(s.pos), self.solids)
            for s in level.enemies]
        # Chapter 9 fields all three Trix at once, so bosses is a list.
        self.bosses = [e for e in self.enemy_list
                       if getattr(e, "is_boss", False)]

        self.pickups = [Pickup(self.world_root, Vec3(p), "gem")
                        for p in level.gems]
        self.pickups += [Pickup(self.world_root, Vec3(p), "heart")
                         for p in level.hearts]

        self.portal = _portal_model(Vec4(0.6, 0.85, 1.0, 1))
        self.portal.reparentTo(self.world_root)
        self.portal.setPos(level.portal)
        self.portal.setColorScale(0.35, 0.35, 0.40, 1.0)
        self.portal_active = False

        if self.hud is None:
            self.hud = HUD(self)
        self.paused = False
        self.death_timer = 0.0
        self.finish_timer = 0.0
        self.level_time = 0.0
        self.audio.play_music(MUSIC_FOR.get(level.key, "music_alfea"))

        # Frame the camera on the level while the chapter's dialogue plays.
        self.player.update_camera(self.camera, 1.0)
        chapter = lore.chapter_for(level.key)
        self.chapter = chapter
        if chapter is not None and chapter.intro:
            self.show_story(chapter, chapter.intro, after="play")
        else:
            self.begin_play()

    def begin_play(self) -> None:
        """Hand control to the player once the chapter intro is done."""
        level = self.level
        self.clear_screen()
        self.state = "playing"
        self.hud.set_visible(True)
        chapter = self.chapter
        if chapter is not None:
            self.hud.show_banner(level.name.upper(), chapter.objective, 3.6)
            self.hud.set_objective(chapter.objective)
        else:
            self.hud.show_banner(level.name.upper(), level.subtitle, 3.4)
            self.hud.set_objective(level.hint)
        self.hud.set_gem_label(level.gem_name)
        self.set_playing_visuals(True)
        self._apply_mouse_mode()

    def unload_level(self) -> None:
        self.effects.clear()
        for e in self.enemy_list:
            if e.alive:
                e.root.removeNode()
        self.enemy_list = []
        for p in self.pickups:
            if not p.taken:
                p.np.removeNode()
        self.pickups = []
        if self.portal is not None:
            self.portal.removeNode()
            self.portal = None
        if self.level_node is not None:
            self.level_node.removeNode()
            self.level_node = None
        if self.player is not None:
            self.player.root.removeNode()
            self.player.focus.removeNode()
            self.player = None
        self.bosses = []
        self.render.clearFog()

    def end_run(self) -> None:
        self.unload_level()
        if self.hud is not None:
            self.hud.set_visible(False)
        self.set_playing_visuals(False)

    def set_playing_visuals(self, on: bool) -> None:
        if self.hud is not None:
            self.hud.set_visible(on)
        if not on:
            self.render.clearFog()

    def toggle_pause(self) -> None:
        if self.state == "playing":
            self.state = "paused"
            self.clear_screen()
            self._title_backdrop()
            text(self.screen, "PAUSED", 0, 0.30, 0.10, TITLE_COLOR,
                 TextNode.ACenter)
            text(self.screen, "Enter or Esc to resume", 0, 0.10, 0.050,
                 (1, 1, 1, 0.9), TextNode.ACenter)
            text(self.screen, "M music   -   N sound   -   Tab mouse look",
                 0, -0.02, 0.042, (1, 1, 1, 0.72), TextNode.ACenter)
            text(self.screen, "Q  quit to title", 0, -0.16, 0.045,
                 (1, 0.7, 0.7, 0.9), TextNode.ACenter)
            self._release_all()
            self._apply_mouse_mode()
        elif self.state == "paused":
            self.clear_screen()
            self.state = "playing"
            self._apply_mouse_mode()

    def _quit_to_title(self) -> None:
        self._release_all()
        self.end_run()
        self.show_title()

    # ------------------------------------------------------------------
    # results / game over
    # ------------------------------------------------------------------
    def complete_level(self) -> None:
        """Chapter cleared: play its closing dialogue, then show the results."""
        self.audio.stop_music()
        self._release_all()
        self.audio.play("victory")
        chapter = self.chapter
        if chapter is not None and chapter.outro:
            self.show_story(chapter, chapter.outro, after="results")
        else:
            self.show_results()

    def show_results(self) -> None:
        self.state = "results"
        self.total_score = self.player.score + 500 + self.player.gems * 50
        self.lives = self.player.lives
        cleared = max(self.profile.get("levels_cleared", 0),
                      self.level_index + 1)
        self.profile["levels_cleared"] = cleared
        self.profile["high_score"] = max(self.profile.get("high_score", 0),
                                         self.total_score)
        C.save_profile(self.profile)

        last = self.level_index >= len(LEVELS) - 1
        self.clear_screen()
        self._title_backdrop()
        title = "FIRST YEAR COMPLETE" if last else "CHAPTER COMPLETE"
        text(self.screen, title, 0, 0.60, 0.080, TITLE_COLOR, TextNode.ACenter)
        ch = self.chapter
        text(self.screen,
             ("%d. %s" % (ch.number, ch.title)) if ch else self.level.name,
             0, 0.48, 0.055, (1, 0.92, 0.6, 1), TextNode.ACenter)
        if ch is not None and ch.codex:
            text(self.screen, "Codex piece at stake:  " + ch.codex,
                 0, 0.40, 0.038, (0.75, 0.88, 1.0, 1), TextNode.ACenter)
        rows = [(self.level.gem_name.title() + "s collected",
                 "%d" % self.player.gems),
                ("Time", "%d:%02d" % (int(self.level_time) // 60,
                                      int(self.level_time) % 60)),
                ("Lives remaining", "%d" % self.player.lives),
                ("Total score", "%06d" % self.total_score)]
        for i, (label, value) in enumerate(rows):
            y = 0.22 - i * 0.10
            text(self.screen, label, -0.06, y, 0.048, (1, 1, 1, 0.9),
                 TextNode.ARight)
            text(self.screen, value, 0.06, y, 0.048, (1.0, 0.88, 0.45, 1),
                 TextNode.ALeft)
        if last:
            text(self.screen, "Alfea still stands. Aisha of Andros has been "
                 "unlocked.", 0, -0.34, 0.046, (0.85, 0.95, 1.0, 1),
                 TextNode.ACenter)
        text(self.screen, "Enter to continue" if not last else
             "Enter to return to the title", 0, -0.62, 0.046,
             (1, 1, 1, 0.8), TextNode.ACenter)
        if self.hud is not None:
            self.hud.set_visible(False)

    def advance_level(self) -> None:
        if self.level_index >= len(LEVELS) - 1:
            self.end_run()
            self.show_title()
        else:
            self.load_level(self.level_index + 1)

    def game_over(self) -> None:
        self.state = "gameover"
        self.audio.stop_music()
        self._release_all()
        self.audio.play("defeat")
        score = self.player.score if self.player else 0
        self.profile["high_score"] = max(self.profile.get("high_score", 0),
                                         score)
        C.save_profile(self.profile)
        self.end_run()
        self.clear_screen()
        self._title_backdrop()
        text(self.screen, "GAME OVER", 0, 0.35, 0.10, (1.0, 0.45, 0.55, 1),
             TextNode.ACenter)
        text(self.screen, "Final score  %06d" % score, 0, 0.18, 0.055,
             (1, 1, 1, 1), TextNode.ACenter)
        text(self.screen, "Enter to return to the title", 0, -0.10, 0.048,
             (1, 1, 1, 0.8), TextNode.ACenter)

    # ------------------------------------------------------------------
    # frame loop
    # ------------------------------------------------------------------
    def _frame(self, task):
        dt = min(0.05, self.globalClock.getDt())   # clamp so a hitch cannot
        self.time += dt                            # tunnel the player
        if self.state == "select" and self.preview_anim is not None:
            self.preview.setH(self.preview.getH() + 42.0 * dt)
            # Grounded idle: the flight pose crosses the arms over the chest.
            self.preview_anim.update(dt, 0.0, False, True)
        elif self.state == "playing":
            self._update_play(dt)
        return Task.cont

    def _camera_input(self, dt: float) -> None:
        dyaw = 0.0
        dpitch = 0.0
        if self.keys.get("cam_left"):
            dyaw -= C.KEY_TURN_SPEED * dt
        if self.keys.get("cam_right"):
            dyaw += C.KEY_TURN_SPEED * dt
        if self.keys.get("cam_up"):
            dpitch += C.KEY_TURN_SPEED * 0.6 * dt
        if self.keys.get("cam_down"):
            dpitch -= C.KEY_TURN_SPEED * 0.6 * dt

        if self.mouse_look and self.win is not None and \
                hasattr(self.win, "movePointer") and \
                self.mouseWatcherNode.hasMouse():
            props = self.win.getProperties()
            cx = props.getXSize() // 2
            cy = props.getYSize() // 2
            md = self.win.getPointer(0)
            if self._mouse_ready:
                dyaw += (md.getX() - cx) * C.MOUSE_SENS * dt * 0.12
                dp = (md.getY() - cy) * C.MOUSE_SENS * dt * 0.12
                dpitch += dp if self.profile.get("invert_y") else -dp
            if self.win.movePointer(0, cx, cy):
                self._mouse_ready = True
        else:
            self._mouse_ready = False

        self.player.orbit_camera(dyaw, dpitch)

    def _update_play(self, dt: float) -> None:
        self.level_time += dt
        player = self.player

        if player.alive:
            self._camera_input(dt)
            player.update(dt, self.keys, self.effects, self.enemy_list)
        else:
            self.death_timer += dt
            if self.death_timer > 2.0:
                self.death_timer = 0.0
                player.lives -= 1
                if player.lives <= 0:
                    self.game_over()
                    return
                player.respawn(Vec3(self.level.start))
                self.hud.show_banner("TRY AGAIN",
                                     "%d live%s left" %
                                     (player.lives,
                                      "" if player.lives == 1 else "s"), 2.0)
        player.update_camera(self.camera, dt)

        before = [e.alive for e in self.enemy_list]
        for e in self.enemy_list:
            if e.alive:
                e.update(dt, player, self.effects)
        self.effects.update(dt, player, self.enemy_list)

        for was_alive, e in zip(before, self.enemy_list):
            if was_alive and not e.alive:
                player.score += e.score
                self.audio.play("enemy_die")

        # Any boss can call for reinforcements; Knut whistles up ghouls, the
        # Trix pull more wisps out of the air.
        for boss in self.bosses:
            if not boss.alive or getattr(boss, "summon_request", 0) <= 0:
                continue
            boss.summon_request = 0
            kind = "ghoul" if boss.name == "knut" else "wisp"
            base = boss.root.getPos()
            for i in range(2):
                a = math.tau * i / 2 + self.time
                pos = Vec3(base.x + math.cos(a) * 9.0,
                           base.y + math.sin(a) * 9.0,
                           base.z if kind == "wisp" else 2.0)
                self.enemy_list.append(
                    E.spawn(kind, self.world_root, pos, self.solids))

        self._update_pickups(dt, player)
        self._update_portal(dt, player)
        self.hud.update(dt, player, self.active_boss())

    def active_boss(self):
        """The boss the HUD bar tracks - the first still standing."""
        for b in self.bosses:
            if b.alive:
                return b
        return None

    def _update_pickups(self, dt: float, player) -> None:
        pc = player.center()
        for p in self.pickups:
            if p.taken:
                continue
            p.update(dt, self.time)
            if (p.np.getPos() - pc).length() < p.radius + player.radius + 0.4:
                if p.kind == "gem":
                    player.gems += 1
                    player.score += 25
                    player.magic = min(C.MAX_MAGIC, player.magic + 20.0)
                    self.audio.play("gem")
                else:
                    if player.health >= C.MAX_HEALTH:
                        continue        # leave full-health hearts on the map
                    player.health = min(C.MAX_HEALTH, player.health + 2.0)
                    self.audio.play("heart")
                self.effects.burst(p.np.getPos(), p.color, 12, 6.0, 0.32)
                p.collect()

    def _update_portal(self, dt: float, player) -> None:
        remaining = sum(1 for e in self.enemy_list if e.alive)
        need_gems = max(0, self.level.gem_goal - player.gems)
        ready = remaining == 0 and need_gems == 0

        if ready and not self.portal_active:
            self.portal_active = True
            self.portal.clearColorScale()
            self.audio.play("portal")
            self.hud.show_banner("THE PORTAL IS OPEN",
                                 "Step into the ring", 3.0)
            self.effects.ring(self.portal.getPos() + Vec3(0, 0, 1.5),
                              Vec4(0.6, 0.9, 1.0, 1), 8.0, 26)

        self.portal.setH(self.portal.getH() + (90.0 if ready else 18.0) * dt)
        self.portal.setZ(self.level.portal.z +
                         math.sin(self.time * 1.8) * (0.4 if ready else 0.12))

        if self.portal_active and player.alive and self.finish_timer <= 0.0:
            d = player.center() - (self.portal.getPos() + Vec3(0, 0, 2.0))
            if d.length() < 3.4:
                self.finish_timer = 0.01
                self.complete_level()
                return

        noun = self.level.gem_name
        if remaining:
            what = "Enemies remaining  %d" % remaining
            if need_gems:
                what += "     %ss needed  %d" % (noun.title(), need_gems)
        elif need_gems:
            what = "Find %d more %s%s" % (need_gems, noun,
                                          "" if need_gems == 1 else "s")
        else:
            what = "Head for the portal!"
        self.hud.set_objective(what)
