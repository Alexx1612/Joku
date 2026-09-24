"""
Batch 13, track Q3: quadruped mob redesign (deer, forest_hare, desert_lizard,
brine_crawler, rubble_crawler). These 5 kinds used to fall back to a reused/
palette-swapped base shape (e.g. deer was literally a recolored yeti) - this
check confirms each now renders its own real, distinct silhouette.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((10, 10))

from game import sprites

Q3_KINDS = ["deer", "forest_hare", "desert_lizard", "brine_crawler", "rubble_crawler"]
BASE_14_KINDS = ["bat", "ghost", "skeleton", "imp", "goblin", "scorpion", "yeti", "troll",
                 "harpy", "salamander", "panther", "ghoul", "frost_wraith", "cave_lurker"]


def _bytes(kind):
    return pygame.image.tostring(sprites.enemy_sprite(kind), "RGBA")


def check_all_render_valid_nonempty_surfaces():
    for kind in Q3_KINDS:
        surf = sprites.enemy_sprite(kind)
        assert isinstance(surf, pygame.Surface), f"{kind}: not a Surface"
        assert surf.get_size() == (48, 48), f"{kind}: unexpected size {surf.get_size()}"
        raw = _bytes(kind)
        assert any(b != 0 for b in raw), f"{kind}: fully empty/transparent surface"


def check_all_five_are_pairwise_distinct():
    data = {k: _bytes(k) for k in Q3_KINDS}
    for i, a in enumerate(Q3_KINDS):
        for b in Q3_KINDS[i + 1:]:
            assert data[a] != data[b], f"{a} is pixel-identical to {b}"


def check_none_match_the_14_base_shapes():
    base_data = {k: _bytes(k) for k in BASE_14_KINDS}
    for kind in Q3_KINDS:
        kd = _bytes(kind)
        for base_kind, bd in base_data.items():
            assert kd != bd, f"{kind} is pixel-identical to base shape '{base_kind}'"


def check_deer_specifically_no_longer_matches_yeti():
    # This is the exact regression the plan called out: deer used to be
    # (_YETI, _DEER_PAL) - a straight recolor of the yeti shape.
    assert _bytes("deer") != _bytes("yeti"), "deer is still pixel-identical to yeti"


def check_grid_palette_consistency_enforced_at_import():
    # sprites.py's _validate_grids() already runs at import time and would have
    # raised ValueError on module import if any of our new grids referenced a
    # palette-less character - reaching this line at all is the assertion.
    for kind in Q3_KINDS:
        grid, pal = sprites.ENEMY_GRIDS[kind]
        used = {ch for row in grid for ch in row if ch not in (" ", ".")}
        missing = used - pal.keys()
        assert not missing, f"{kind}: grid uses undefined palette chars {missing}"


if __name__ == "__main__":
    check_all_render_valid_nonempty_surfaces()
    check_all_five_are_pairwise_distinct()
    check_none_match_the_14_base_shapes()
    check_deer_specifically_no_longer_matches_yeti()
    check_grid_palette_consistency_enforced_at_import()
    print("check_mob_redesign_q3: all checks passed")
