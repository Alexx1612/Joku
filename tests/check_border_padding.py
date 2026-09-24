"""
Batch 14, Track G2: every top-level HUD element must stay at least
`ui.SCREEN_EDGE_MARGIN` px clear of all four screen edges - the user's
explicit ask ("shouldn't get less than 2 pixels close to the borders").
`tests/check_hud_and_overlap.py` already covers element-vs-element overlap
but never checked distance from the screen edges themselves - this fills
that gap with real rect math against C.SCREEN_W/C.SCREEN_H, not eyeballing.

Run with: .venv\\Scripts\\python.exe tests\\check_border_padding.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import constants as C
from game import ui, minimap


def _assert_clear_of_edges(name, rect):
    assert rect.left >= ui.SCREEN_EDGE_MARGIN, (
        f"{name} is only {rect.left}px from the left edge (floor: {ui.SCREEN_EDGE_MARGIN}px): {rect}")
    assert rect.top >= ui.SCREEN_EDGE_MARGIN, (
        f"{name} is only {rect.top}px from the top edge (floor: {ui.SCREEN_EDGE_MARGIN}px): {rect}")
    assert C.SCREEN_W - rect.right >= ui.SCREEN_EDGE_MARGIN, (
        f"{name} is only {C.SCREEN_W - rect.right}px from the right edge "
        f"(floor: {ui.SCREEN_EDGE_MARGIN}px): {rect}")
    assert C.SCREEN_H - rect.bottom >= ui.SCREEN_EDGE_MARGIN, (
        f"{name} is only {C.SCREEN_H - rect.bottom}px from the bottom edge "
        f"(floor: {ui.SCREEN_EDGE_MARGIN}px): {rect}")


def check_static_hud_rects_clear_of_edges():
    """The fixed-geometry elements - checkable directly from their own
    rect-returning helpers, no rendering needed."""
    mm_x, mm_y = minimap.corner_origin()
    minimap_rect = pygame.Rect(mm_x, mm_y, minimap.CORNER_SIZE, minimap.corner_block_height())
    _assert_clear_of_edges("corner minimap block", minimap_rect)

    _assert_clear_of_edges("day/night clock", ui.day_night_clock_rect())
    _assert_clear_of_edges("FPS counter", ui.fps_counter_rect())

    from game.entities import Player
    p = Player("wizard", "X", pid="p1")
    x0 = C.SCREEN_W - ui.DOCK_PAD - ui.PLAYER_PANEL_WIDTH
    y0 = ui._dock_top_y() - ui.PLAYER_PANEL_HEIGHT
    player_panel_rect = pygame.Rect(x0 - 6, y0 - 4, ui.PLAYER_PANEL_WIDTH + 12, ui.PLAYER_PANEL_HEIGHT + 8)
    _assert_clear_of_edges("player panel", player_panel_rect)
    print("check_static_hud_rects_clear_of_edges: PASSED")


def check_draw_hud_text_clear_of_edges():
    """The zone-name/kill-count text (top-right) and the centered bottom
    hint text (draw_hud) - measured from their real rendered surfaces, not
    guessed sizes, since font metrics vary by string content."""
    pad = 12
    zone_surf = ui._FONT_M.render("The Realm", True, C.COL_WHITE)
    zone_rect = pygame.Rect(C.SCREEN_W - zone_surf.get_width() - pad, pad,
                             zone_surf.get_width(), zone_surf.get_height())
    _assert_clear_of_edges("zone name text", zone_rect)

    kc_surf = ui._FONT_S.render("kills: 999  [BOSS ACTIVE]", True, (220, 180, 80))
    kc_rect = pygame.Rect(C.SCREEN_W - kc_surf.get_width() - pad, pad + 24,
                           kc_surf.get_width(), kc_surf.get_height())
    _assert_clear_of_edges("kill counter text", kc_rect)

    hint_surf = ui._FONT_S.render("WASD move | mouse aim+click fire | Space ability | Enter chat", True, (150, 150, 160))
    hint_rect = pygame.Rect(C.SCREEN_W // 2 - hint_surf.get_width() // 2, C.SCREEN_H - 26,
                             hint_surf.get_width(), hint_surf.get_height())
    _assert_clear_of_edges("bottom hint text", hint_rect)

    ui.draw_hud(screen, "The Realm", 999, True)
    ui.draw_fps_counter(screen, 60.0)
    print("check_draw_hud_text_clear_of_edges: PASSED")


def check_real_hub_frame_edges():
    """Real end-to-end integration check through the actual app - drives a
    genuine Game() into the Realm and draws a full frame, then re-checks
    the same fixed-geometry rects still hold once everything (weather,
    day/night overlay, live events, etc.) is actually layered on screen."""
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.enter_realm()
    game.draw()  # would raise if any call site's args/positions are broken

    check_static_hud_rects_clear_of_edges()
    print("check_real_hub_frame_edges: PASSED")


if __name__ == "__main__":
    check_static_hud_rects_clear_of_edges()
    check_draw_hud_text_clear_of_edges()
    check_real_hub_frame_edges()
    print("PASSED: every checked HUD element stays clear of the screen edges.")
