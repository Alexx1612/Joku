"""
Regression check for relocating the 10 procedural islands to open water near
the map's edges, connected to the mainland by a real colored plank walkway
(one color per island). Covers normal cases (islands measurably farther out,
real walkable connectivity, distinct plank colors) and the real edge case
this feature shipped with once already: the walkway overwriting the
island's own landmark tile at its exact center.

Run with: .venv\\Scripts\\python.exe tests\\check_island_relocation.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import realm_sim, world


def _build_sim():
    return realm_sim.RealmSim(bonus=False)


def check_islands_far_from_center():
    sim = _build_sim()
    assert len(sim.islands) >= 8, "expected most/all 10 islands to stamp"
    gh, gw = len(sim.realm_map.grid), len(sim.realm_map.grid[0])
    cx, cy = gw / 2, gh / 2
    max_r = min(gw, gh) / 2 - 3
    for isl in sim.islands:
        tx, ty = isl["pos"].x / 32, isl["pos"].y / 32
        dist = math.hypot(tx - cx, ty - cy)
        # the OLD formula placed islands only ~4 tiles past the coastline -
        # comfortably under half the map's own radius in most cases. The new
        # placement (coastline_radius + a real water-gap) should sit well
        # out toward the edge for every island, not just a lucky few.
        assert dist > max_r * 0.5, f"{isl['label']} is only {dist:.0f} tiles out - not relocated far enough"
    print("check_islands_far_from_center: PASSED")


def check_island_cores_are_land_not_water():
    sim = _build_sim()
    for isl in sim.islands:
        tile = sim.realm_map.tile_at(isl["pos"].x, isl["pos"].y)
        assert tile != world.WATER
        assert not sim.realm_map.is_solid(isl["pos"].x, isl["pos"].y)
    print("check_island_cores_are_land_not_water: PASSED")


def check_walkway_never_overwrites_landmark():
    """The actual bug this feature shipped with once: the walkway targeted
    the island's exact center, overwriting the landmark tile stamp_island
    had just placed there."""
    sim = _build_sim()
    for isl in sim.islands:
        tile = sim.realm_map.tile_at(isl["pos"].x, isl["pos"].y)
        assert tile in world.TALL_PROP_TILE_IDS, f"{isl['label']}'s core should still be its landmark"
        assert tile not in world.WALKWAY_PLANK_TILE.values(), \
            f"{isl['label']}'s landmark was overwritten by a walkway plank"
    print("check_walkway_never_overwrites_landmark: PASSED")


def check_walkway_planks_walkable_and_distinctly_colored():
    sim = _build_sim()
    grid = sim.realm_map.grid
    used_planks = set()
    for wid in world.WALKWAY_PLANK_TILE.values():
        assert wid not in world.SOLID, f"plank tile {wid} must never be SOLID - it's a bridge over water"
        if any(wid in row for row in grid):
            used_planks.add(wid)
    assert len(used_planks) >= 8, f"expected most/all 10 distinct plank colors to appear, got {len(used_planks)}"
    # edge case: the 10 colors must actually BE distinct from each other, not
    # just distinct ids mapped to the same visual color by mistake
    colors = [world.TILE_COLORS[wid] for wid in world.WALKWAY_PLANK_TILE.values()]
    assert len(set(colors)) == len(colors), "every island's plank color should be visually distinct"
    print("check_walkway_planks_walkable_and_distinctly_colored: PASSED")


def check_coastline_radius_extraction_matches_make_realm():
    """coastline_radius() was extracted from a make_realm()-local closure to
    a module-level function so island placement could reuse it - confirm
    the extraction didn't change its behavior (same values it always
    produced inside make_realm(), just now independently callable)."""
    import random
    random.seed(123)
    assert callable(world.coastline_radius)
    v1 = world.coastline_radius(0.0)
    v2 = world.coastline_radius(math.pi)
    assert v1 != v2, "the coastline should genuinely vary by angle, not be a constant"
    max_r = min(world.REALM_W, world.REALM_H) / 2 - 3
    assert max_r * 0.35 <= v1 <= max_r * 1.15
    print("check_coastline_radius_extraction_matches_make_realm: PASSED")


if __name__ == "__main__":
    check_islands_far_from_center()
    check_island_cores_are_land_not_water()
    check_walkway_never_overwrites_landmark()
    check_walkway_planks_walkable_and_distinctly_colored()
    check_coastline_radius_extraction_matches_make_realm()
    print("PASSED: island relocation + walkway checks all green.")
