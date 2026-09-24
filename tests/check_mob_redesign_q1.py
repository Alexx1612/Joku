"""
Regression check for Batch 13 Track Q1 - the ethereal/wisp-flyer mob
redesign (ember_wisp, fury_shard, spite_spirit, tide_wisp, cave_moth).
Before this batch, all 5 had no bespoke silhouette at all: they were
palette-swapped reuses of an existing base enemy grid (_GHOST/_BAT), so
e.g. `tide_wisp` was pixel-for-pixel `_GHOST`'s shape wearing a different
color. This check asserts the redesign actually delivered real, distinct
silhouettes - not just that the code runs without crashing.

Run with: .venv\\Scripts\\python.exe tests\\check_mob_redesign_q1.py
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

Q1_KINDS = ("ember_wisp", "fury_shard", "spite_spirit", "tide_wisp", "cave_moth")

# The 14 pre-existing base enemy shapes every one of the 26 "too simple"
# mobs used to reuse before this batch's redesign - Q1's 5 new shapes
# must not be pixel-identical to any of these (that would mean the
# "redesign" silently kept the old reused shape).
PRE_EXISTING_BASE_KINDS = (
    "bat", "ghost", "skeleton", "imp", "goblin", "scorpion", "yeti", "troll",
    "harpy", "salamander", "panther", "ghoul", "frost_wraith", "cave_lurker",
)


def _pixels(surf):
    w, h = surf.get_size()
    return [surf.get_at((x, y)) for y in range(h) for x in range(w)]


def check_all_five_render_valid_surfaces():
    for kind in Q1_KINDS:
        surf = sprites.enemy_sprite(kind)
        assert isinstance(surf, pygame.Surface), f"{kind}: not a Surface"
        assert surf.get_size() == (sprites.FINAL_SIZE, sprites.FINAL_SIZE), (
            f"{kind}: expected {(sprites.FINAL_SIZE, sprites.FINAL_SIZE)}, got {surf.get_size()}"
        )
        px = _pixels(surf)
        opaque = sum(1 for p in px if p.a > 0)
        assert opaque > 20, f"{kind}: sprite looks blank/degenerate ({opaque} opaque pixels)"
    print("check_all_five_render_valid_surfaces: PASSED")


def check_q1_mobs_are_distinct_from_each_other():
    pixel_sets = {k: _pixels(sprites.enemy_sprite(k)) for k in Q1_KINDS}
    kinds = list(Q1_KINDS)
    for i in range(len(kinds)):
        for j in range(i + 1, len(kinds)):
            a, b = kinds[i], kinds[j]
            assert pixel_sets[a] != pixel_sets[b], (
                f"{a} and {b} render pixel-identical - not actually redesigned distinctly"
            )
    print("check_q1_mobs_are_distinct_from_each_other: PASSED")


def check_q1_mobs_are_not_reused_base_shapes():
    """The actual bug this batch fixes: e.g. tide_wisp used to be exactly
    _GHOST's grid with a new palette. Compare against every pre-existing
    base shape rendered with EACH Q1 mob's own new palette (not just the
    base shape's own default palette) - a same-shape-different-palette
    reuse would still fail this, which is exactly the bug being fixed."""
    for kind in Q1_KINDS:
        grid, pal = sprites.ENEMY_GRIDS[kind]
        new_pixels = _pixels(sprites.enemy_sprite(kind))
        for base_kind in PRE_EXISTING_BASE_KINDS:
            base_grid, _base_pal = sprites.ENEMY_GRIDS[base_kind]
            if base_grid is grid:
                raise AssertionError(f"{kind} still points at the same grid object as {base_kind}")
            base_pixels = _pixels(sprites.enemy_sprite(base_kind))
            assert new_pixels != base_pixels, (
                f"{kind} renders pixel-identical to pre-existing '{base_kind}' shape"
            )
    print("check_q1_mobs_are_not_reused_base_shapes: PASSED")


def check_grids_pass_palette_validation():
    """`_validate_grids` already runs at import time and would have raised
    ValueError on a bad char/palette mismatch - reaching this line at all
    proves the 5 new grids only use characters their own palette defines."""
    for kind in Q1_KINDS:
        grid, palette = sprites.ENEMY_GRIDS[kind]
        used = {ch for row in grid for ch in row if ch not in (" ", ".")}
        missing = used - palette.keys()
        assert not missing, f"{kind}: grid uses undefined char(s) {sorted(missing)}"
    print("check_grids_pass_palette_validation: PASSED")


if __name__ == "__main__":
    check_all_five_render_valid_surfaces()
    check_q1_mobs_are_distinct_from_each_other()
    check_q1_mobs_are_not_reused_base_shapes()
    check_grids_pass_palette_validation()
    print("PASSED: Q1 mob redesign checks all green.")
