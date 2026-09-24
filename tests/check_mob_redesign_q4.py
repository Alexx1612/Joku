"""
Regression check for Batch 13 Track Q4 (humanoid-guardian mob redesign):
echo_knight, shard_sentinel, stone_revenant, cinder_warden, and
pearl_acolyte used to be plain palette-swaps of pre-existing base enemy
shapes (_GHOUL, _TROLL, _CAVE_LURKER, _SALAMANDER) with zero bespoke
silhouette. Each now has its own dedicated ASCII grid in game/sprites.py,
following a shared "humanoid guardian" archetype template (peaked/plated
head, torso + one distinct regalia accent, tapered legs/hem) but with a
genuinely different silhouette and accent placement per mob.

This checks the real, rendered pixel output, not just that the grids
exist as text - a genuinely distinct sprite must actually rasterize to
different pixels, not just have a different variable name.

Run with: .venv\\Scripts\\python.exe tests\\check_mob_redesign_q4.py
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

Q4_KINDS = ["echo_knight", "shard_sentinel", "stone_revenant", "cinder_warden", "pearl_acolyte"]

# the 14 original base enemy shapes these 5 used to be palette-swapped
# copies of (bat/ghost/skeleton/imp/goblin/scorpion/yeti/troll/harpy/
# salamander/panther/ghoul/frost_wraith/cave_lurker) - none of the Q4
# kinds should render pixel-identical to any of these anymore.
BASE_KINDS = ["bat", "ghost", "skeleton", "imp", "goblin", "scorpion", "yeti", "troll",
              "harpy", "salamander", "panther", "ghoul", "frost_wraith", "cave_lurker"]


def _pixels(surf):
    return pygame.image.tostring(surf, "RGBA")


def check_q4_sprites_render_and_are_valid_surfaces():
    for kind in Q4_KINDS:
        surf = sprites.enemy_sprite(kind)
        assert isinstance(surf, pygame.Surface), f"{kind}: enemy_sprite did not return a Surface"
        assert surf.get_size() == (sprites.FINAL_SIZE, sprites.FINAL_SIZE), (
            f"{kind}: expected {sprites.FINAL_SIZE}x{sprites.FINAL_SIZE}, got {surf.get_size()}")
        # not a blank/fully-transparent surface
        raw = _pixels(surf)
        assert any(b != 0 for b in raw), f"{kind}: rendered surface is entirely blank"
    print("check_q4_sprites_render_and_are_valid_surfaces: PASSED")


def check_q4_sprites_are_pixel_distinct_from_each_other():
    pixel_sets = {kind: _pixels(sprites.enemy_sprite(kind)) for kind in Q4_KINDS}
    for i, kind_a in enumerate(Q4_KINDS):
        for kind_b in Q4_KINDS[i + 1:]:
            assert pixel_sets[kind_a] != pixel_sets[kind_b], (
                f"{kind_a} and {kind_b} render pixel-identical - not actually distinct redesigns")
    print("check_q4_sprites_are_pixel_distinct_from_each_other: PASSED")


def check_q4_sprites_are_distinct_from_the_14_base_shapes():
    base_pixels = {kind: _pixels(sprites.enemy_sprite(kind)) for kind in BASE_KINDS}
    for q4_kind in Q4_KINDS:
        q4_pixels = _pixels(sprites.enemy_sprite(q4_kind))
        for base_kind, base_px in base_pixels.items():
            assert q4_pixels != base_px, (
                f"{q4_kind} still renders pixel-identical to base shape '{base_kind}' - "
                f"redesign did not actually take effect")
    print("check_q4_sprites_are_distinct_from_the_14_base_shapes: PASSED")


def check_q4_grids_use_only_declared_palette_keys():
    # game/sprites.py already runs _validate_grids() at import time, which
    # raises ValueError on any grid/palette key mismatch - successfully
    # importing the module at all is itself a real assertion of this, but
    # re-check explicitly here so a future edit that silently swallowed
    # that exception still gets caught by this test.
    for kind in Q4_KINDS:
        grid, pal = sprites.ENEMY_GRIDS[kind]
        used = {ch for row in grid for ch in row if ch not in (" ", ".")}
        missing = used - pal.keys()
        assert not missing, f"{kind}: grid uses undeclared palette char(s) {sorted(missing)}"
    print("check_q4_grids_use_only_declared_palette_keys: PASSED")


if __name__ == "__main__":
    check_q4_sprites_render_and_are_valid_surfaces()
    check_q4_sprites_are_pixel_distinct_from_each_other()
    check_q4_sprites_are_distinct_from_the_14_base_shapes()
    check_q4_grids_use_only_declared_palette_keys()
    print("PASSED: Q4 humanoid-guardian mob redesign checks all green.")
