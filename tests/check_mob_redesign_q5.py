"""
Regression check for Batch 13 Track Q5 (construct/remaining mob redesign).

Six "Reforging" island-guardian kinds - shattered_golem, fracture_hound,
coral_sentinel, drowned_custodian, kelp_stalker, shellback_guardian -
used to just palette-swap an unrelated existing base grid (e.g.
shattered_golem literally reused the yeti shape). This check confirms
each now renders from its own real, distinct grid: a valid non-empty
surface, no two of the six pixel-identical to each other, and none of
the six pixel-identical to any of the 14 pre-existing base enemy shapes.

Run with: .venv\\Scripts\\python.exe tests\\check_mob_redesign_q5.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from game import sprites

Q5_KINDS = [
    "shattered_golem", "fracture_hound", "coral_sentinel",
    "drowned_custodian", "kelp_stalker", "shellback_guardian",
]

BASE_KINDS = [
    "bat", "ghost", "skeleton", "imp", "goblin", "scorpion", "yeti",
    "troll", "harpy", "salamander", "panther", "ghoul", "frost_wraith",
    "cave_lurker",
]


def _pixels(surf):
    return pygame.image.tostring(surf, "RGBA")


def check_all_render_valid_surfaces():
    for kind in Q5_KINDS:
        surf = sprites.enemy_sprite(kind)
        assert isinstance(surf, pygame.Surface), f"{kind}: not a Surface"
        w, h = surf.get_size()
        assert w > 0 and h > 0, f"{kind}: empty surface {w}x{h}"
        # not a fully-transparent blank render
        assert pygame.transform.average_color(surf)[3] > 0 or \
            any(surf.get_at((x, y))[3] > 0 for x in range(w) for y in range(h)), \
            f"{kind}: fully transparent, nothing actually drawn"
    print("check_all_render_valid_surfaces: OK")


def check_q5_kinds_distinct_from_each_other():
    rendered = {k: _pixels(sprites.enemy_sprite(k)) for k in Q5_KINDS}
    for i, a in enumerate(Q5_KINDS):
        for b in Q5_KINDS[i + 1:]:
            assert rendered[a] != rendered[b], f"{a} and {b} render pixel-identical"
    print("check_q5_kinds_distinct_from_each_other: OK")


def check_q5_kinds_distinct_from_base_shapes():
    base_pixels = {k: _pixels(sprites.enemy_sprite(k)) for k in BASE_KINDS}
    for q in Q5_KINDS:
        qp = _pixels(sprites.enemy_sprite(q))
        for b, bp in base_pixels.items():
            assert qp != bp, f"{q} renders pixel-identical to base shape {b} (still a reuse)"
    print("check_q5_kinds_distinct_from_base_shapes: OK")


def check_grids_use_only_declared_palette_chars():
    # _validate_grids already runs at import time and would have raised if
    # any Q5 grid used an undeclared palette char - re-assert the specific
    # grid/palette pairs directly here so this stays a real, targeted check
    # rather than relying only on the module-level import side effect.
    for kind in Q5_KINDS:
        grid, palette = sprites.ENEMY_GRIDS[kind]
        used = {ch for row in grid for ch in row if ch not in (" ", ".")}
        missing = used - palette.keys()
        assert not missing, f"{kind}: grid uses undeclared char(s) {sorted(missing)}"
    print("check_grids_use_only_declared_palette_chars: OK")


if __name__ == "__main__":
    check_all_render_valid_surfaces()
    check_q5_kinds_distinct_from_each_other()
    check_q5_kinds_distinct_from_base_shapes()
    check_grids_use_only_declared_palette_chars()
    print("ALL CHECKS PASSED")
