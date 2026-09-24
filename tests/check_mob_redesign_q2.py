"""
Regression check for Batch 13 Track Q2 (mob redesign - "aerial/voice
creatures"). Before this batch, songbird/marsh_heron/siren_wraith/
abyssal_chorister/choir_warden all fell back to a REUSED procedural grid
(bat/ghost/harpy/frost-wraith shape) with just a new palette - visually
indistinguishable in silhouette from an unrelated existing mob. This check
verifies each of the 5 now renders its own bespoke grid: a valid sprite
Surface, distinct from each of its 4 siblings, and distinct from every
pre-existing base enemy shape it used to alias.

Run with: .venv\\Scripts\\python.exe tests\\check_mob_redesign_q2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import sprites

Q2_KINDS = ["songbird", "marsh_heron", "siren_wraith", "abyssal_chorister", "choir_warden"]

# the shapes these 5 used to alias before this batch (bat/ghost/harpy/frost_wraith)
PREVIOUSLY_ALIASED_BASE_KINDS = ["bat", "ghost", "harpy", "frost_wraith"]


def _pixels(surf):
    return pygame.image.tostring(surf, "RGBA")


def check_all_five_render_valid_surfaces():
    for kind in Q2_KINDS:
        surf = sprites.enemy_sprite(kind)
        assert isinstance(surf, pygame.Surface), f"{kind}: enemy_sprite did not return a Surface"
        assert surf.get_size() == (sprites.FINAL_SIZE, sprites.FINAL_SIZE), \
            f"{kind}: expected {sprites.FINAL_SIZE}x{sprites.FINAL_SIZE}, got {surf.get_size()}"
        # a real drawn sprite has more than a handful of non-transparent pixels
        opaque = sum(1 for y in range(surf.get_height()) for x in range(surf.get_width())
                     if surf.get_at((x, y)).a > 0)
        assert opaque > 50, f"{kind}: sprite looks almost empty ({opaque} opaque px)"
    print(f"check_all_five_render_valid_surfaces: PASSED ({len(Q2_KINDS)} kinds)")


def check_no_two_of_the_five_are_pixel_identical():
    pixel_data = {kind: _pixels(sprites.enemy_sprite(kind)) for kind in Q2_KINDS}
    for i, a in enumerate(Q2_KINDS):
        for b in Q2_KINDS[i + 1:]:
            assert pixel_data[a] != pixel_data[b], f"{a} and {b} render pixel-identical sprites"
    print("check_no_two_of_the_five_are_pixel_identical: PASSED")


def check_none_still_matches_its_old_aliased_shape():
    """The real regression this batch fixes: none of the 5 should render
    pixel-identical to the base shape it used to silently reuse."""
    for kind in Q2_KINDS:
        new_pixels = _pixels(sprites.enemy_sprite(kind))
        for base_kind in PREVIOUSLY_ALIASED_BASE_KINDS:
            base_pixels = _pixels(sprites.enemy_sprite(base_kind))
            assert new_pixels != base_pixels, \
                f"{kind} still renders pixel-identical to '{base_kind}' - redesign didn't take effect"
    print("check_none_still_matches_its_old_aliased_shape: PASSED")


def check_grids_are_registered_with_own_names():
    grid_ids = {kind: id(sprites.ENEMY_GRIDS[kind][0]) for kind in Q2_KINDS}
    # all 5 must point at 5 DIFFERENT grid objects (not accidentally sharing one)
    assert len(set(grid_ids.values())) == len(Q2_KINDS), \
        f"some of the 5 mobs still share the same underlying grid object: {grid_ids}"
    print("check_grids_are_registered_with_own_names: PASSED")


if __name__ == "__main__":
    check_all_five_render_valid_surfaces()
    check_no_two_of_the_five_are_pixel_identical()
    check_none_still_matches_its_old_aliased_shape()
    check_grids_are_registered_with_own_names()
    print("PASSED: mob redesign Q2 (aerial/voice creatures) checks all green.")
