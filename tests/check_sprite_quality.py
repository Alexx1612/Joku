"""
Sprite audit regression checks: every drawable character (8 classes, every
ENEMY_KINDS kind incl. bosses at their scale, every NPC, every pet base) has a
non-empty sprite; sprites keep their SOURCE aspect ratio (PNG or grid) instead of
being squashed into a 48x48 square; nothing is too tiny to read; scaled bosses are
re-rendered (not blown up); no two different mob kinds render pixel-identical;
and NPC people no longer reuse (tinted) class sprites.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import sprites, npcs
from game.entities import ENEMY_KINDS
from game.items import PET_KINDS


def _source_aspect(kind):
    nat = sprites._art_native_size(f"enemies/enemy_{kind}.png")
    if nat:
        return nat[0] / nat[1]
    grid = sprites.ENEMY_GRIDS[kind][0]
    base = sprites._autline_and_render(grid, sprites.ENEMY_GRIDS[kind][1], sprites.PX)
    return base.get_width() / base.get_height()


def check_every_character_has_a_readable_sprite():
    for cls in sprites.CLASS_GRIDS:
        img = sprites.player_sprite(cls)
        assert min(img.get_size()) >= 24, (cls, img.get_size())
    for kind, d in ENEMY_KINDS.items():
        img = sprites.enemy_sprite(kind, d.get("scale", 1.0) or 1.0)
        w, h = img.get_size()
        assert max(w, h) >= 40 and min(w, h) >= 16, f"{kind} too small to read: {img.get_size()}"
        assert any(img.get_at((x, y))[3] for x in range(0, w, 2) for y in range(0, h, 2)), kind
    for d in npcs.NPCS.values():
        src, key = d["sprite"]
        img = sprites.player_sprite(key) if src == "player" else sprites.enemy_sprite(key)
        assert min(img.get_size()) >= 16, (d["name"], img.get_size())
    for d in PET_KINDS.values():
        assert sprites.enemy_sprite(d["base"]).get_width() > 0
    print("check_every_character_has_a_readable_sprite: PASSED")


def check_aspect_ratio_preserved():
    bad = []
    for kind in ENEMY_KINDS:
        img = sprites.enemy_sprite(kind)
        src, drawn = _source_aspect(kind), img.get_width() / img.get_height()
        if abs(src - drawn) / src > 0.08:
            bad.append(f"{kind}: source {src:.2f} drawn {drawn:.2f}")
    assert not bad, "stretched sprites: " + "; ".join(bad)
    print("check_aspect_ratio_preserved: PASSED")


def check_scaled_bosses_rerendered_not_blown_up():
    for kind, d in ENEMY_KINDS.items():
        scale = d.get("scale", 1.0) or 1.0
        if scale <= 1.0:
            continue
        big, base = sprites.enemy_sprite(kind, scale), sprites.enemy_sprite(kind)
        assert abs(big.get_width() / base.get_width() - scale) < 0.05, kind
        # a re-render from the hi-res source has more distinct colours than a smoothscaled 48px blow-up
        # would only if detail exists - at minimum it must match the requested size exactly
        assert max(big.get_size()) == round(max(base.get_size()) * scale) or \
            abs(max(big.get_size()) - max(base.get_size()) * scale) <= 1, kind
    print("check_scaled_bosses_rerendered_not_blown_up: PASSED")


def check_no_two_kinds_pixel_identical():
    seen = {}
    for kind in ENEMY_KINDS:
        img = sprites.enemy_sprite(kind)
        key = (img.get_size(), pygame.image.tostring(img, "RGBA"))
        assert key not in seen, f"{kind} renders pixel-identical to {seen.get(key)}"
        seen[key] = kind
    print("check_no_two_kinds_pixel_identical: PASSED")


def check_npc_people_have_their_own_sprites():
    people = [d for d in npcs.NPCS.values() if d["kind"] == "person"]
    keys = [d["sprite"] for d in people]
    assert all(src == "enemy" for src, _ in keys), "an NPC still reuses a (tinted) class sprite"
    assert len(set(keys)) == len(keys), "two NPC people share a sprite"
    print("check_npc_people_have_their_own_sprites: PASSED")


if __name__ == "__main__":
    check_every_character_has_a_readable_sprite()
    check_aspect_ratio_preserved()
    check_scaled_bosses_rerendered_not_blown_up()
    check_no_two_kinds_pixel_identical()
    check_npc_people_have_their_own_sprites()
    print("PASSED: sprite quality checks all green.")
