"""
Regression check for Batch 14 Track K - the unified "dungeon door" visual
language for every Portal kind plus the Vault/Bazaar-return tile overlay.

Before this batch, `entities.Portal.draw()` dispatched to 4 completely
unrelated hand-coded shapes (a swirl, a beacon, spikes, a torn rift) plus a
plain-circle fallback, and Vault/Bazaar were flat-colored floor tiles with
zero special draw code. This asserts every portal kind now shares the same
stone-archway silhouette (readable as "a doorway"), stays pixel-distinct
from every other kind (color/glow differences), and that the Vault/Bazaar
tile overlay produces a real archway, not a plain colored square.

Run with: .venv\\Scripts\\python.exe tests\\check_dungeon_door_visuals.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game.entities import Portal
from game import world

FRAME = 80
CENTER = (FRAME // 2, FRAME // 2)
BG = (12, 12, 16)

ALL_KINDS = ("entrance", "realm_exit", "phase2", "dungeon_shard", "ambient", "island_link")


def _render_portal(kind, t=0.6):
    surf = pygame.Surface((FRAME, FRAME))
    surf.fill(BG)
    p = Portal(pygame.Vector2(0, 0), kind=kind)
    p.t = t

    class _FakeCam:
        def __call__(self, pos):
            return CENTER
    p.draw(surf, _FakeCam())
    return surf


def _pixels(surf):
    w, h = surf.get_size()
    return [surf.get_at((x, y)) for y in range(h) for x in range(w)]


def _non_bg_count(surf):
    return sum(1 for px in _pixels(surf) if tuple(px)[:3] != BG)


def check_every_kind_renders_an_archway():
    for kind in ALL_KINDS:
        surf = _render_portal(kind)
        non_bg = _non_bg_count(surf)
        assert non_bg > 200, f"Portal kind '{kind}' rendered almost nothing ({non_bg} non-bg pixels) - expected a real archway"

        # Shared silhouette check: both side-pillar columns (left of center-x,
        # right of center-x, within the doorway's vertical band) must have
        # real stone-colored pixels for every kind, since they all now share
        # the same archway shape.
        cx, cy = CENTER
        left_col_has_stone = any(tuple(surf.get_at((cx - 20, y)))[:3] != BG for y in range(cy - 15, cy + 15))
        right_col_has_stone = any(tuple(surf.get_at((cx + 20, y)))[:3] != BG for y in range(cy - 15, cy + 15))
        assert left_col_has_stone, f"Portal kind '{kind}' missing a left archway pillar"
        assert right_col_has_stone, f"Portal kind '{kind}' missing a right archway pillar"
    print("check_every_kind_renders_an_archway: PASSED")


def check_kinds_are_pixel_distinct():
    frames = {kind: _pixels(_render_portal(kind)) for kind in ALL_KINDS}
    for i, k1 in enumerate(ALL_KINDS):
        for k2 in ALL_KINDS[i + 1:]:
            assert frames[k1] != frames[k2], f"Portal kinds '{k1}' and '{k2}' rendered pixel-identical frames"
    print("check_kinds_are_pixel_distinct: PASSED")


def check_vault_and_bazaar_tile_get_archway_overlay():
    from game.world import _draw_archway_tile, TILE_COLORS, VAULT_TILE, BAZAAR_PORTAL

    for tile_id, name in ((VAULT_TILE, "Vault"), (BAZAAR_PORTAL, "Bazaar")):
        plain = pygame.Surface((32, 32))
        plain.fill(TILE_COLORS[tile_id])

        archway = pygame.Surface((32, 32))
        archway.fill(TILE_COLORS[world.NEXUS_FLOOR])
        _draw_archway_tile(archway, 16, 16, TILE_COLORS[tile_id], t_ms=500)

        plain_pixels = [tuple(plain.get_at((x, y)))[:3] for y in range(32) for x in range(32)]
        archway_pixels = [tuple(archway.get_at((x, y)))[:3] for y in range(32) for x in range(32)]
        assert plain_pixels != archway_pixels, f"{name} tile's archway overlay produced no visible difference from a plain colored tile"

        distinct_colors = len(set(archway_pixels))
        assert distinct_colors >= 4, f"{name} tile's archway overlay only used {distinct_colors} distinct colors - expected a real multi-part archway (stone + glow + doorway), not a flat fill"
    print("check_vault_and_bazaar_tile_get_archway_overlay: PASSED")


if __name__ == "__main__":
    check_every_kind_renders_an_archway()
    check_kinds_are_pixel_distinct()
    check_vault_and_bazaar_tile_get_archway_overlay()
