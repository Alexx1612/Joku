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


if __name__ == "__main__":
    check_center_brighter_than_far_corner_at_night()
    check_light_falls_off_with_distance()
    check_no_overlay_at_full_daylight()
    check_blood_moon_tint_still_applies()
    check_light_sprite_is_cached_not_rebuilt()
    print("\nAll night-lightmap checks passed.")
