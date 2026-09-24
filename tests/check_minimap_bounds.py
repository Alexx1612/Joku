"""
Batch 14, Track F: the corner minimap and full-map screen (M key) had zero
bounds clamping on entity dots (enemies/portals/peers/player) - a dot's
world-to-screen projection was drawn straight onto the full game surface
with no clip to the map widget's own bordered rectangle. A boss blip (always
shown regardless of exploration/crop, per game.minimap._visible_enemy_blips)
or any entity outside the currently-zoomed/cropped view window could render
as a dot visibly detached outside the little map square. Fixed by clipping
(`surf.set_clip(...)`) the dot-drawing block to each widget's own real
content rect in both game.minimap.draw_corner() and draw_full_map().

This test does real pixel inspection on the rendered surface - not just
checking input coordinates - to catch a regression where the clip is
removed or scoped to the wrong rect.

Run with: .venv\\Scripts\\python.exe tests\\check_minimap_bounds.py
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((1280, 720))

from game import minimap
from game import constants as C
from game import world


class _FakeEntity:
    def __init__(self, x, y, rank=None, neutral=False, alive=True):
        self.pos = pygame.Vector2(x, y)
        self.rank = rank
        self.neutral = neutral
        self.alive = alive


def _build_tilemap(w=60, h=60):
    grid = [[world.GRASS for _ in range(w)] for _ in range(h)]
    tm = world.TileMap(grid)
    return tm


def _colored_pixel_count(surf, rect, bg):
    """Count pixels inside rect that differ from the plain background color -
    a crude but real "something was drawn here" probe that doesn't care about
    the exact dot color/shape."""
    count = 0
    x0, y0 = max(0, rect.x), max(0, rect.y)
    x1, y1 = min(surf.get_width(), rect.x + rect.w), min(surf.get_height(), rect.y + rect.h)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if surf.get_at((x, y))[:3] != bg:
                count += 1
    return count


def check_corner_minimap_clips_out_of_bounds_dots():
    tm = _build_tilemap()
    mm = minimap.MinimapState()
    mm.reveal_all(tm)
    # A tight radar crop so a "far away" enemy is guaranteed outside the
    # current view window while still being a "boss" (always shown per
    # _visible_enemy_blips, regardless of exploration/crop).
    mm.corner_zoom = minimap.CORNER_MAX_ZOOM
    player_pos = pygame.Vector2(30 * C.TILE, 30 * C.TILE)
    far_boss = _FakeEntity(59 * C.TILE, 59 * C.TILE, rank="boss")

    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    surf.fill((0, 0, 0))
    minimap.draw_corner(surf, tm, mm, player_pos, enemies=[far_boss])

    x, y = minimap.corner_origin()
    map_rect = pygame.Rect(x, y, minimap.CORNER_SIZE, minimap.CORNER_SIZE)
    screen_rect = surf.get_rect()

    # Nothing drawn by draw_corner should land outside the screen at all...
    outside_screen = _colored_pixel_count(
        surf, pygame.Rect(-10, -10, screen_rect.w + 20, screen_rect.h + 20), (0, 0, 0)
    ) - _colored_pixel_count(surf, screen_rect, (0, 0, 0))
    assert outside_screen == 0, "draw_corner drew something outside the screen surface entirely"

    # ...and specifically, no dot pixels should land in the border strip just
    # outside the map's own inner content rect but still inside the drawn
    # panel/frame area - sample a ring immediately outside map_rect.
    ring_top = pygame.Rect(map_rect.x - 20, map_rect.y - 20, map_rect.w + 40, 18)
    ring_bottom = pygame.Rect(map_rect.x - 20, map_rect.bottom + 2, map_rect.w + 40, 18)
    ring_left = pygame.Rect(map_rect.x - 20, map_rect.y, 18, map_rect.h)
    ring_right = pygame.Rect(map_rect.right + 2, map_rect.y, 18, map_rect.h)
    # These rings overlap the gold frame/panel border drawn around the map
    # (expected, non-dot pixels), so instead of a blanket "must be black"
    # check, assert specifically that none of the far boss's own bright-red
    # blip color (BOSS_BLIP_COLOR) or its white outline appears there.
    for ring in (ring_top, ring_bottom, ring_left, ring_right):
        x0, y0 = max(0, ring.x), max(0, ring.y)
        x1, y1 = min(surf.get_width(), ring.x + ring.w), min(surf.get_height(), ring.y + ring.h)
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                px = surf.get_at((xx, yy))[:3]
                assert px != minimap.BOSS_BLIP_COLOR, (
                    f"boss blip color leaked outside the corner minimap's content rect at ({xx},{yy})"
                )
    print("check_corner_minimap_clips_out_of_bounds_dots: PASSED")


def check_corner_minimap_still_draws_in_view_dots():
    """No false-negative: a dot that SHOULD be visible (in-view, un-zoomed)
    must still actually render inside the map rect."""
    tm = _build_tilemap()
    mm = minimap.MinimapState()
    mm.reveal_all(tm)
    mm.corner_zoom = minimap.CORNER_MIN_ZOOM  # whole map fit to the corner box
    player_pos = pygame.Vector2(30 * C.TILE, 30 * C.TILE)
    nearby_boss = _FakeEntity(31 * C.TILE, 30 * C.TILE, rank="boss")

    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    surf.fill((0, 0, 0))
    minimap.draw_corner(surf, tm, mm, player_pos, enemies=[nearby_boss])

    x, y = minimap.corner_origin()
    map_rect = pygame.Rect(x, y, minimap.CORNER_SIZE, minimap.CORNER_SIZE)
    found = False
    for yy in range(map_rect.y, map_rect.y + map_rect.h):
        for xx in range(map_rect.x, map_rect.x + map_rect.w):
            if surf.get_at((xx, yy))[:3] == minimap.BOSS_BLIP_COLOR:
                found = True
                break
        if found:
            break
    assert found, "an in-view boss blip failed to render at all after adding the bounds clip - false negative"
    print("check_corner_minimap_still_draws_in_view_dots: PASSED")


def check_full_map_clips_out_of_bounds_dots():
    tm = _build_tilemap()
    mm = minimap.MinimapState()
    mm.reveal_all(tm)
    mm.zoom = minimap.MAX_ZOOM  # tightest crop -> easiest to push an entity outside the rendered map image
    player_pos = pygame.Vector2(30 * C.TILE, 30 * C.TILE)
    far_boss = _FakeEntity(0, 0, rank="boss")

    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    minimap.draw_full_map(surf, tm, mm, player_pos, enemies=[far_boss], zone_name="Test")

    px_per_tile = max(2, int(5 * mm.zoom))
    ox = C.SCREEN_W // 2 - int(player_pos.x / C.TILE * px_per_tile)
    oy = C.SCREEN_H // 2 - int(player_pos.y / C.TILE * px_per_tile)
    view_w = min(tm.w, C.SCREEN_W // px_per_tile + 3)
    view_h = min(tm.h, C.SCREEN_H // px_per_tile + 3)
    crop_x0 = max(0, min(tm.w - view_w, int(player_pos.x / C.TILE - view_w / 2)))
    crop_y0 = max(0, min(tm.h - view_h, int(player_pos.y / C.TILE - view_h / 2)))
    map_rect = pygame.Rect(ox + crop_x0 * px_per_tile, oy + crop_y0 * px_per_tile,
                            view_w * px_per_tile, view_h * px_per_tile)

    leaked = False
    for yy in range(0, C.SCREEN_H):
        if map_rect.y <= yy < map_rect.y + map_rect.h:
            continue
        for xx in range(0, C.SCREEN_W):
            if surf.get_at((xx, yy))[:3] == minimap.BOSS_BLIP_COLOR:
                leaked = True
                break
        if leaked:
            break
    assert not leaked, "boss blip color rendered outside the full map's own rendered image rect"
    print("check_full_map_clips_out_of_bounds_dots: PASSED")


def check_full_map_still_draws_in_view_dots():
    tm = _build_tilemap()
    mm = minimap.MinimapState()
    mm.reveal_all(tm)
    mm.zoom = minimap.DEFAULT_ZOOM
    player_pos = pygame.Vector2(30 * C.TILE, 30 * C.TILE)
    nearby_boss = _FakeEntity(31 * C.TILE, 30 * C.TILE, rank="boss")

    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    minimap.draw_full_map(surf, tm, mm, player_pos, enemies=[nearby_boss], zone_name="Test")

    found = any(
        surf.get_at((xx, yy))[:3] == minimap.BOSS_BLIP_COLOR
        for yy in range(0, C.SCREEN_H)
        for xx in range(0, C.SCREEN_W)
    )
    assert found, "an in-view boss blip failed to render at all on the full map after adding the bounds clip"
    print("check_full_map_still_draws_in_view_dots: PASSED")


if __name__ == "__main__":
    check_corner_minimap_clips_out_of_bounds_dots()
    check_corner_minimap_still_draws_in_view_dots()
    check_full_map_clips_out_of_bounds_dots()
    check_full_map_still_draws_in_view_dots()
