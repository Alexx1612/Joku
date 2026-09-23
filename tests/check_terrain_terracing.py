"""
Regression check for visual terracing (plan section 2 - "levels/stairs/
walls for a more 3D look"). This is a VISUAL effect only, never real
elevation/collision: every terrace tile (interior, cliff-lip, stairs) must
remain fully walkable. Covers normal cases (a real generated Realm's
terraces) and the specific edge case that would be easy to get wrong: the
cliff-lip tiles get the same shaded-band visual as SOLID walls but must
never actually be SOLID.

Run with: .venv\\Scripts\\python.exe tests\\check_terrain_terracing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import world, realm_sim


def check_cliff_and_stair_tiles_never_solid():
    for tile_id in world.CLIFF_EDGE_TILE_IDS:
        assert tile_id not in world.SOLID, f"cliff-edge tile {tile_id} must never be SOLID"
    for tile_id in world.TERRACE_STAIR_TILE.values():
        assert tile_id not in world.SOLID, f"stair tile {tile_id} must never be SOLID"
    print("check_cliff_and_stair_tiles_never_solid: PASSED")


def check_stamp_terrace_direct():
    grid = world.make_realm()
    gh, gw = len(grid), len(grid[0])
    cx, cy = gw // 2, gh // 2
    x = cx
    while grid[cy][x] != world.WATER and x < gw - 1:
        x += 1
    anchor = (x - 20, cy - 20)
    rect = world.stamp_terrace(grid, anchor, "forest")
    tm = world.TileMap(grid)

    # interior is genuinely walkable
    assert not tm.is_solid(anchor[0] * 32 + 16, anchor[1] * 32 + 16)

    # at least one cliff-edge tile was actually placed, and every cliff/stair
    # tile within the stamped rect is walkable (the real edge case: it LOOKS
    # like a wall via the shared shading trick, but must never BE one)
    cliff_ids = world.CLIFF_EDGE_TILE_IDS
    stair_ids = set(world.TERRACE_STAIR_TILE.values())
    found_cliff = found_stair = False
    for yy in range(rect.top, rect.bottom):
        for xx in range(rect.left, rect.right):
            t = grid[yy][xx]
            if t in cliff_ids:
                found_cliff = True
                assert not tm.is_solid(xx * 32 + 16, yy * 32 + 16), "a cliff-edge tile is blocking movement!"
            if t in stair_ids:
                found_stair = True
                assert not tm.is_solid(xx * 32 + 16, yy * 32 + 16)
    assert found_cliff, "expected at least one cliff-edge tile in the stamped terrace"
    assert found_stair, "expected at least one stair tile bridging the cliff ring"
    print("check_stamp_terrace_direct: PASSED")


def check_terraces_dont_overlap_landmark_buildings():
    """Full world-gen integration: every biome's terrace (if placed) must
    not overlap that biome's own landmark building."""
    sim = realm_sim.RealmSim(bonus=False)
    # both stamp_lair_building and stamp_terrace carve directly into the grid
    # with no separate registry of "where are the terraces" kept on RealmSim,
    # so re-derive terrace locations by scanning for cliff/stair tile ids and
    # clustering them, then check against known building wall tile positions
    building_wall_ids = set(world.BUILDING_WALL_TILE.values())
    grid = sim.realm_map.grid
    gh, gw = len(grid), len(grid[0])
    cliff_or_stair_ids = world.CLIFF_EDGE_TILE_IDS | set(world.TERRACE_STAIR_TILE.values())
    terrace_tiles = [(x, y) for y in range(gh) for x in range(gw) if grid[y][x] in cliff_or_stair_ids]
    building_tiles = [(x, y) for y in range(gh) for x in range(gw) if grid[y][x] in building_wall_ids]
    for (tx, ty) in terrace_tiles:
        for (bx, by) in building_tiles:
            assert abs(tx - bx) > 1 or abs(ty - by) > 1, "a terrace edge tile landed adjacent to a building wall"
    print(f"check_terraces_dont_overlap_landmark_buildings: PASSED "
          f"({len(terrace_tiles)} terrace-edge tiles, {len(building_tiles)} building-wall tiles, no collisions)")


if __name__ == "__main__":
    check_cliff_and_stair_tiles_never_solid()
    check_stamp_terrace_direct()
    check_terraces_dont_overlap_landmark_buildings()
    print("PASSED: terrain terracing checks all green.")
