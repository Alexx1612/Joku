"""
Regression checks for the persisted options menu (game/settings.py +
game/options_menu.py): load/save/defaults/corrupt-file handling, live volume
application, the shake/hit-stop/particle toggles actually gating vfx, menu
keyboard/mouse navigation changing + persisting values, and the Esc quit
confirmation in the real single-player Game.
"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp(prefix="rr_check_settings_")
os.environ["RR_SETTINGS_PATH"] = os.path.join(TMP, "settings.json")
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()
screen = pygame.display.set_mode((100, 100))

from game import settings, options_menu, audio, vfx, weather, ui
from game import constants as C

PATH = settings.SETTINGS_PATH


def _reset():
    if os.path.exists(PATH):
        os.remove(PATH)
    settings.load()


def check_defaults_and_roundtrip():
    _reset()
    assert settings.current == settings.DEFAULTS
    settings.change("music_volume", 0.3)
    settings.change("particles", "low")
    settings.change("fps_cap", 120)
    with open(PATH, encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["music_volume"] == 0.3 and on_disk["particles"] == "low" and on_disk["fps_cap"] == 120
    settings.current = dict(settings.DEFAULTS)
    settings.load()
    assert settings.get("music_volume") == 0.3 and settings.fps_cap() == 120
    assert not os.path.exists(PATH + ".tmp")
    print("check_defaults_and_roundtrip: PASSED")


def check_missing_keys_and_bad_values():
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump({"sfx_volume": 5, "muted": "yes", "particles": "ultra", "fps_cap": 77,
                   "show_fps": False, "bogus": 1}, f)
    settings.load()
    assert settings.get("sfx_volume") == 1.0  # clamped to 0..1
    assert settings.get("muted") is False  # wrong type -> default
    assert settings.get("particles") == "high"
    assert settings.get("fps_cap") == 60
    assert settings.get("show_fps") is False  # a valid value survives
    assert "bogus" not in settings.current
    assert settings.get("master_volume") == 1.0  # missing -> default
    print("check_missing_keys_and_bad_values: PASSED")


def check_corrupt_file():
    with open(PATH, "w", encoding="utf-8") as f:
        f.write("{not json")
    settings.load()
    assert settings.current == settings.DEFAULTS
    with open(PATH, "w", encoding="utf-8") as f:
        f.write("[1, 2, 3]")
    settings.load()
    assert settings.current == settings.DEFAULTS
    print("check_corrupt_file: PASSED")


def check_volume_application():
    _reset()
    settings.change("master_volume", 0.5)
    settings.change("music_volume", 0.4)
    settings.change("sfx_volume", 0.8)
    assert abs(audio._music_gain - 0.2) < 1e-9 and abs(audio._sfx_gain - 0.4) < 1e-9
    settings.change("muted", True)
    assert audio._music_gain == 0 and audio._sfx_gain == 0
    audio.play_pickup()  # muted: must be a silent no-op, never a crash
    settings.change("muted", False)
    assert abs(audio._sfx_gain - 0.4) < 1e-9
    # the live theme channel gets re-leveled immediately, not just on the next track
    audio.init()
    if audio._enabled:
        audio.play_theme("nexus")
        settings.change("music_volume", 1.0)
        ch = audio._theme_channel
        if ch is not None:
            assert abs(ch.get_volume() - 0.5) < 0.02, ch.get_volume()
        audio.stop_theme()
    print("check_volume_application: PASSED")


def check_juice_toggles():
    _reset()
    vfx._particles.clear()
    vfx._rings.clear()
    vfx.spawn_burst((0, 0), (255, 255, 255), count=20)
    assert len(vfx._particles) == 20
    settings.change("particles", "low")
    vfx._particles.clear()
    vfx.spawn_burst((0, 0), (255, 255, 255), count=20)
    assert 1 <= len(vfx._particles) < 20
    vfx._particles.clear()
    vfx.spawn_burst((0, 0), (255, 255, 255), count=1)
    assert len(vfx._particles) == 1  # low never erases an effect entirely
    settings.change("particles", "off")
    vfx.spawn_burst((0, 0), (255, 255, 255), count=20)
    vfx.spawn_ring((0, 0), (255, 255, 255))
    vfx.spawn_rise((0, 0), (255, 255, 255))
    assert vfx._particles == [] and vfx._rings == []
    wfx = weather.WeatherFX()
    wfx.update(0.016, "rain")
    assert wfx.particles == []
    settings.change("particles", "high")
    wfx.update(0.016, "rain")
    assert len(wfx.particles) == weather.MAX_PARTICLES

    settings.change("screen_shake", False)
    vfx.trigger_shake(0.5, 10)
    assert vfx.shake_offset(0.016) == (0, 0)
    settings.change("screen_shake", True)
    vfx.trigger_shake(0.5, 10)
    assert vfx._shake_time > 0
    vfx.shake_offset(1.0)  # expire it
    vfx.trigger_shake(0.2, 2)  # a smaller shake after a big one has ended must still fire
    assert vfx._shake_time > 0
    vfx.shake_offset(1.0)

    settings.change("hit_stop", False)
    vfx.trigger_hitstop(500)
    assert vfx.apply_hitstop(0.016) == 0.016
    settings.change("hit_stop", True)
    vfx.trigger_hitstop(500)
    assert vfx.apply_hitstop(0.016) == 0.0
    settings.change("hit_stop", False)  # turning it off cancels one in progress
    assert vfx.apply_hitstop(0.016) == 0.016
    print("check_juice_toggles: PASSED")


def _rows(state):
    return options_menu.build_rows(
        auto_fire_get=lambda: state["auto"], auto_fire_set=lambda v: state.__setitem__("auto", v),
        fullscreen_get=lambda: state["fs"], fullscreen_toggle=lambda: state.__setitem__("fs", not state["fs"]),
        reset_camera=lambda: state.__setitem__("cam", True), close=lambda: state.__setitem__("closed", True),
        leave=("Leave", lambda: state.__setitem__("left", True)))


def _idx(rows, label):
    return next(i for i, r in enumerate(rows) if r.label == label)


def check_menu_keyboard_navigation():
    _reset()
    state = {"auto": False, "fs": False}
    rows = _rows(state)
    sel = 0
    assert rows[sel].label == "Auto-fire"
    sel = options_menu.handle_key(rows, sel, pygame.K_RIGHT)
    assert state["auto"] is True
    sel = options_menu.handle_key(rows, sel, pygame.K_UP)
    assert sel == len(rows) - 1 and rows[sel].label == "Close menu"
    sel = options_menu.handle_key(rows, sel, pygame.K_DOWN)
    sel = options_menu.handle_key(rows, sel, pygame.K_DOWN)
    assert rows[sel].label == "Master volume"
    for _ in range(3):
        options_menu.handle_key(rows, sel, pygame.K_LEFT)
    assert abs(settings.get("master_volume") - 0.7) < 1e-9
    for _ in range(20):
        options_menu.handle_key(rows, sel, pygame.K_RIGHT)
    assert settings.get("master_volume") == 1.0  # clamped
    sel = _idx(rows, "Particles")
    options_menu.handle_key(rows, sel, pygame.K_RETURN)  # high -> wraps to off
    assert settings.get("particles") == "off"
    options_menu.handle_key(rows, sel, pygame.K_LEFT)
    assert settings.get("particles") == "high"
    sel = _idx(rows, "FPS cap")
    options_menu.handle_key(rows, sel, pygame.K_RIGHT)
    assert settings.get("fps_cap") == 120
    options_menu.handle_key(rows, sel, pygame.K_RIGHT)
    assert settings.get("fps_cap") == 0
    sel = _idx(rows, "Fullscreen")
    options_menu.handle_key(rows, sel, pygame.K_RETURN)
    assert state["fs"] is True
    assert options_menu.handle_key(rows, sel, pygame.K_q) is None  # not a menu key
    sel = _idx(rows, "Close menu")
    options_menu.handle_key(rows, sel, pygame.K_RETURN)
    assert state.get("closed")
    # persisted: a fresh load sees what the menu changed
    settings.load()
    assert settings.get("fps_cap") == 0 and settings.get("master_volume") == 1.0
    print("check_menu_keyboard_navigation: PASSED")


def check_menu_mouse_and_geometry():
    _reset()
    state = {"auto": False, "fs": False}
    rows = _rows(state)
    rects = ui.help_menu_item_rects(rows)
    assert len(rects) == len(rows) and all(r is not None for r in rects)
    close = ui.help_close_button_rect(rows)
    assert not any(r.colliderect(close) for r in rects)
    for a, b in zip(rects, rects[1:]):
        assert a.bottom <= b.top, (a, b)  # rows never overlap
    # panel fits on the default screen
    x, y, w, h, *_ = ui._help_panel_geometry(rows)
    assert x >= 0 and y >= 0 and x + w <= C.SCREEN_W and y + h <= C.SCREEN_H, (x, y, w, h)

    i = _idx(rows, "Screen shake")
    assert options_menu.handle_click(rows, rects[i].center) == i
    assert settings.get("screen_shake") is False
    i = _idx(rows, "Music volume")
    bar = ui.help_slider_rect(rows, i)
    assert bar is not None and rects[i].contains(bar)
    options_menu.handle_click(rows, (bar.x + bar.w // 4, bar.centery))
    assert abs(settings.get("music_volume") - 0.25) < 0.051
    options_menu.handle_click(rows, (bar.right + 3, bar.centery))
    assert settings.get("music_volume") == 1.0
    assert ui.help_slider_rect(rows, _idx(rows, "Mute all")) is None
    assert options_menu.handle_click(rows, (0, 0)) is None
    i = _idx(rows, "Leave")
    options_menu.handle_click(rows, rects[i].center)
    assert state.get("left")
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    ui.draw_help_overlay(surf, menu_items=rows, selected_idx=3, mouse_pos=rects[5].center)
    ui.draw_help_overlay(surf, menu_items=[], selected_idx=0)
    print("check_menu_mouse_and_geometry: PASSED")


def check_help_lines_match_bindings():
    keys = {k for _, k in ui.HELP_LINES}
    joined = " ".join(keys)
    for needed in ("Space", "Shift", "Tab", "F11", "Esc", "Enter", "1-8"):
        assert needed in joined, needed
    assert all("Interact" != label for label, _ in ui.HELP_LINES)
    print("check_help_lines_match_bindings: PASSED")


def _key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)


def check_quit_confirm_in_game():
    _reset()
    import main
    game = main.Game()
    game.state = main.STATE_CLASS_SELECT
    pygame.event.clear()
    pygame.event.post(_key(pygame.K_ESCAPE))
    assert game.handle_events() is True  # Esc no longer quits instantly
    assert game.quit_confirm_open
    pygame.event.post(_key(pygame.K_n))
    assert game.handle_events() is True and not game.quit_confirm_open
    pygame.event.post(_key(pygame.K_ESCAPE))
    game.handle_events()
    quit_rect, stay_rect = ui.quit_confirm_button_rects()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=stay_rect.center))
    assert game.handle_events() is True and not game.quit_confirm_open
    pygame.event.post(_key(pygame.K_ESCAPE))
    game.handle_events()
    game.draw()  # the dialog renders
    pygame.event.post(_key(pygame.K_RETURN))
    assert game.handle_events() is False  # confirmed -> quit

    # the O menu inside the real Game drives settings and the I-key auto-fire persists
    game.quit_confirm_open = False
    game.help_open = True
    rows = game._menu_items()
    game.menu_selected = _idx(rows, "Show FPS")
    pygame.event.post(_key(pygame.K_RETURN))
    game.handle_events()
    assert settings.get("show_fps") is False
    game._set_auto_fire(True)
    settings.load()
    assert settings.get("auto_fire") is True
    print("check_quit_confirm_in_game: PASSED")


if __name__ == "__main__":
    check_defaults_and_roundtrip()
    check_missing_keys_and_bad_values()
    check_corrupt_file()
    check_volume_application()
    check_juice_toggles()
    check_menu_keyboard_navigation()
    check_menu_mouse_and_geometry()
    check_help_lines_match_bindings()
    check_quit_confirm_in_game()
    print("PASSED: check_settings")
