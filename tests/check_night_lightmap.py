"""
Regression check for ui.py:draw_day_night_overlay()'s lightmap cutout -
Batch 12's replacement of the old single flat-alpha night tint with a real
per-source lightmap. The player is always exactly screen-center (the camera
follows the player every frame, and Camera.__call__ maps cam.pos to
(screen_w/2, screen_h/2) regardless of Q/E rotation - see game/world.py's
Camera class), so the overlay should be measurably BRIGHTER (lower alpha)
right at screen-center than out in a dark corner far from it, at night.

Run with: .venv\\Scripts\\python.exe tests\\check_night_lightmap.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import constants as C
from game import ui


def _render_overlay(light_level, blood_moon=False):
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H)).convert_alpha()
    surf.fill((255, 255, 255, 255))  # known-bright base so darkening is visible
    ui.draw_day_night_overlay(surf, light_level, blood_moon)
    return surf


def _brightness(surf, pos):
    r, g, b, a = surf.get_at(pos)
    return r + g + b  # base is pure white, so lower sum == more of the dark tint applied


def check_center_brighter_than_far_corner_at_night():
    surf = _render_overlay(light_level=0.05)  # near-midnight, overlay definitely active
    center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
    corner = (10, 10)  # far outside the player light radius (130px) from center
    center_brightness = _brightness(surf, center)
    corner_brightness = _brightness(surf, corner)
    assert center_brightness > corner_brightness, (
        f"expected screen-center (player light) brighter than a far corner at night, "
        f"got center={center_brightness} corner={corner_brightness}"
    )
    print("check_center_brighter_than_far_corner_at_night: PASSED "
          f"(center={center_brightness}, corner={corner_brightness})")


def check_light_falls_off_with_distance():
    """The cutout should be a real gradient, not a hard-edged disc: brightness
    should decrease monotonically-ish as we move away from center."""
    surf = _render_overlay(light_level=0.05)
    cx, cy = C.SCREEN_W // 2, C.SCREEN_H // 2
    near = _brightness(surf, (cx + 20, cy))
    mid = _brightness(surf, (cx + 80, cy))
    far = _brightness(surf, (cx + 300, cy))
    assert near >= mid >= far, f"expected a falloff near>=mid>=far, got {near} {mid} {far}"
    assert near > far, "expected a real difference between near-center and far-away brightness"
    print(f"check_light_falls_off_with_distance: PASSED (near={near}, mid={mid}, far={far})")


def check_no_overlay_at_full_daylight():
    """light_level=1.0 (noon) should draw nothing at all - same early-out as before."""
    surf = _render_overlay(light_level=1.0)
    assert _brightness(surf, (10, 10)) == 255 * 3
    print("check_no_overlay_at_full_daylight: PASSED")


def check_blood_moon_tint_still_applies():
    """The red Blood Moon tint (vs. the default blue night tint) must still be
    intact - the lightmap change must not have broken the existing tint logic."""
    normal = _render_overlay(light_level=0.1, blood_moon=False)
    blood = _render_overlay(light_level=0.1, blood_moon=True)
    corner = (10, 10)
    nr, ng, nb, _ = normal.get_at(corner)
    br, bg, bb, _ = blood.get_at(corner)
    assert br > nr and br > bb, f"expected a red-dominant tint during Blood Moon, got {(br, bg, bb)}"
    print("check_blood_moon_tint_still_applies: PASSED")


def check_light_sprite_is_cached_not_rebuilt():
    """Calling the overlay repeatedly must not grow/rebuild the cached sprite -
    the whole point of caching by radius instead of rebuilding every frame."""
    ui._LIGHT_SPRITE_CACHE.clear()
    _render_overlay(light_level=0.1)
    assert ui.PLAYER_LIGHT_RADIUS in ui._LIGHT_SPRITE_CACHE
    cached_sprite = ui._LIGHT_SPRITE_CACHE[ui.PLAYER_LIGHT_RADIUS]
    _render_overlay(light_level=0.2)
    _render_overlay(light_level=0.05)
    assert ui._LIGHT_SPRITE_CACHE[ui.PLAYER_LIGHT_RADIUS] is cached_sprite, (
        "expected the same cached sprite object to be reused across frames"
    )
    assert len(ui._LIGHT_SPRITE_CACHE) == 1
    print("check_light_sprite_is_cached_not_rebuilt: PASSED")


class _Cam:
    """Identity camera: world == screen (what the occlusion path expects: cam(world) -> screen)."""
    angle = 0.0

    def __call__(self, pos):
        return int(pos[0]), int(pos[1])


def _occluded(grid, light_world, player_world=None):
    from game import world
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H)).convert_alpha()
    surf.fill((255, 255, 255, 255))
    occ = dict(grid=grid, solid=world.SOLID, cam=_Cam(), tile=C.TILE,
               player_world=player_world if player_world is not None else (-5000, -5000),
               lights_world=[(light_world[0], light_world[1], 320, (255, 220, 160))],
               version=(id(grid), sum(row.count(world.DOOR_OPEN) for row in grid)))
    ui.draw_day_night_overlay(surf, 0.0, False, luminosity=0.5, occlusion=occ)
    return surf


def check_walls_cast_shadows():
    """A wall between a light and a spot leaves that spot dark; the same spot with no wall
    in the way is lit (rays stop at solid tiles - real shadows)."""
    from game import world, lighting
    lighting.clear_caches()
    w, h = C.SCREEN_W // C.TILE + 2, C.SCREEN_H // C.TILE + 2
    open_grid = [[world.GRASS] * w for _ in range(h)]
    walled = [row[:] for row in open_grid]
    for y in range(h):
        walled[y][14] = world.ROCK  # a wall at x = 14 tiles (448..480 px)
    light = (10 * C.TILE, 10 * C.TILE)
    spot = (16 * C.TILE, 10 * C.TILE)  # 6 tiles right of the light, behind the wall
    lit_open = _brightness(_occluded(open_grid, light), spot)
    lit_walled = _brightness(_occluded(walled, light), spot)
    near_side = _brightness(_occluded(walled, light), (12 * C.TILE, 10 * C.TILE))
    assert lit_open > lit_walled + 150, (lit_open, lit_walled)
    assert near_side > lit_walled + 150, "the light's own side of the wall stays lit"
    # a closed door is a wall too; an open one lets the light out
    door = [row[:] for row in walled]
    for y in range(8, 13):
        door[y][14] = world.DOOR_CLOSED
    shut = _brightness(_occluded(door, light), spot)
    for y in range(8, 13):
        door[y][14] = world.DOOR_OPEN
    lighting.clear_caches()
    opened = _brightness(_occluded(door, light), spot)
    assert opened > shut + 150, (opened, shut)
    print(f"check_walls_cast_shadows: PASSED (open {lit_open}, behind wall {lit_walled}, door {shut}->{opened})")


def check_light_polygons_are_cached():
    """A static lamp's lit polygon is built once and reused; the player's light only
    rebuilds when the player moves to another tile."""
    from game import world, lighting
    lighting.clear_caches()
    lighting.stats["poly_builds"] = 0
    w, h = C.SCREEN_W // C.TILE + 2, C.SCREEN_H // C.TILE + 2
    grid = [[world.GRASS] * w for _ in range(h)]
    for _ in range(5):
        _occluded(grid, (300, 300), player_world=(600, 400))
    assert lighting.stats["poly_builds"] == 2, lighting.stats  # one lamp + one player tile
    _occluded(grid, (300, 300), player_world=(605, 404))       # same tile
    assert lighting.stats["poly_builds"] == 2
    _occluded(grid, (300, 300), player_world=(700, 400))       # a new tile
    assert lighting.stats["poly_builds"] == 3
    print("check_light_polygons_are_cached: PASSED")


def check_lights_are_coloured_and_luminosity_orders():
    """Lit ground takes the colour of the light reaching it (a green firefly light makes a
    green spot), and the Luminosity setting orders the darkness."""
    surf = pygame.Surface((400, 300)).convert_alpha()
    surf.fill((255, 255, 255, 255))
    ui.draw_day_night_overlay(surf, 0.0, False, luminosity=0.5, player_screen=(-900, -900),
                              lights=[(200, 150, 100, (60, 255, 60))])
    r, g, b, _a = surf.get_at((200, 150))
    assert g > r + 60 and g > b + 60, (r, g, b)
    vals = []
    for lum in (0.0, 0.5, 1.0):
        s2 = pygame.Surface((400, 300)).convert_alpha()
        s2.fill((255, 255, 255, 255))
        ui.draw_day_night_overlay(s2, 0.0, False, luminosity=lum, player_screen=(-900, -900))
        vals.append(_brightness(s2, (200, 150)))
    assert vals[0] < vals[1] < vals[2], vals
    print(f"check_lights_are_coloured_and_luminosity_orders: PASSED ({vals})")


def check_night_overlay_frame_cost():
    """The whole night lighting pass (light map with ~10 lights, 7 of them with wall
    shadows, scale-up + multiply) must stay a small slice of a frame at 1366x820."""
    import time
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _timing
    _timing.disable_power_throttling()
    from game import world, lighting
    lighting.clear_caches()
    w, h = C.SCREEN_W // C.TILE + 2, C.SCREEN_H // C.TILE + 2
    grid = [[world.GRASS] * w for _ in range(h)]
    for x in range(5, 40, 6):  # a few walls so the rays have something to stop on
        for y in range(4, 20):
            grid[y][x] = world.ROCK
    lights = [(100 + i * 120, 200 + (i % 3) * 180, 120 + (i % 4) * 25, (255, 200, 120)) for i in range(10)]
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    occ = dict(grid=grid, solid=world.SOLID, cam=_Cam(), tile=C.TILE, player_world=(683, 410),
               lights_world=lights, version=0)
    ui.draw_day_night_overlay(surf, 0.0, False, luminosity=0.5, occlusion=occ)  # warm the caches
    t0 = time.perf_counter()
    n = 60
    for _ in range(n):
        ui.draw_day_night_overlay(surf, 0.0, False, luminosity=0.5, occlusion=occ)
    ms = (time.perf_counter() - t0) / n * 1000
    assert ms < 8.0, f"night lighting costs {ms:.2f} ms/frame"
    print(f"check_night_overlay_frame_cost: PASSED ({ms:.2f} ms/frame, 10 lights)")


if __name__ == "__main__":
    check_center_brighter_than_far_corner_at_night()
    check_light_falls_off_with_distance()
    check_no_overlay_at_full_daylight()
    check_blood_moon_tint_still_applies()
    check_light_sprite_is_cached_not_rebuilt()
    check_walls_cast_shadows()
    check_light_polygons_are_cached()
    check_lights_are_coloured_and_luminosity_orders()
    check_night_overlay_frame_cost()
    print("\nAll night-lightmap checks passed.")
