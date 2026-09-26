"""
Regression checks for the Realm terrain generator (world.make_realm, the
warped value-noise + Whittaker + priority-flood-rivers rewrite): every biome
appears with a real share of land on every seed, inner-tier biomes sit toward
the centre, rivers only ever flow downhill into the sea or a lake, the beach
spawn is on a real sea shore, coastline_radius() describes the generated
coast, island walkways are laid over water only, and generation stays inside
its time budget.

Run with: .venv\\Scripts\\python.exe tests\\check_terrain_generation.py
"""
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import world, realm_sim

MIN_BIOME_SHARE = 0.03   # every biome gets at least 3% of the land, on every seed
TIME_BUDGET_S = 3.0


def check_all_biomes_present_with_real_share():
    for seed in (11, 12, 13):
        random.seed(seed)
        grid = world.make_realm()
        counts = {}
        land = 0
        for row in grid:
            for t in row:
                if t != world.WATER:
                    land += 1
                    counts[t] = counts.get(t, 0) + 1
        for ground, name in world.GROUND_TO_BIOME_NAME.items():
            share = counts.get(ground, 0) / land
            assert share >= MIN_BIOME_SHARE, f"seed {seed}: {name} only {share:.1%} of land"
        # Batch 15: the continent is generated on its own CONTINENT_SIZE square and embedded
        # in a larger ocean-ringed map, so its land share is measured against that square
        frac = land / (world.CONTINENT_SIZE ** 2)
        assert 0.35 <= frac <= 0.55, f"seed {seed}: land fraction {frac:.2f} out of range"
    print("check_all_biomes_present_with_real_share: PASSED")


def check_generation_time_budget():
    random.seed(21)
    t0 = time.perf_counter()
    world.make_realm()
    dt = time.perf_counter() - t0
    print(f"  make_realm() {world.REALM_W}x{world.REALM_H}: {dt:.2f}s")
    assert dt <= TIME_BUDGET_S, f"make_realm took {dt:.2f}s, budget {TIME_BUDGET_S}s"
    print("check_generation_time_budget: PASSED")


def _build(seed):
    random.seed(seed)
    grid = world.make_realm()
    return grid, dict(world.LAST_REALM_INFO)


def check_inner_tier_toward_centre(grid):
    cx, cy = world.REALM_W / 2, world.REALM_H / 2
    inner = {world.BIOME_GROUND[b] for b in world.BIOME_TIER_INNER}
    outer = {world.BIOME_GROUND[b] for b in world.BIOME_TIER_OUTER}
    di, ni, do, no = 0.0, 0, 0.0, 0
    for y in range(0, len(grid), 3):
        row = grid[y]
        for x in range(0, len(row), 3):
            t = row[x]
            if t in inner:
                di += math.hypot(x - cx, y - cy)
                ni += 1
            elif t in outer:
                do += math.hypot(x - cx, y - cy)
                no += 1
    assert di / ni < 0.75 * (do / no), (
        f"inner-tier biomes should sit toward the centre: mean dist {di / ni:.0f} vs outer {do / no:.0f}")
    print("check_inner_tier_toward_centre: PASSED")


def check_rivers_flow_downhill_to_sea_or_lake(info):
    F = info["fields"]
    filled, down, ocean_c, lake, river_c = F["filled"], F["down"], F["ocean_c"], F["lake"], F["river_c"]
    rivers = F["rivers"]
    assert rivers, "expected at least some rivers"
    for k, _dk, _fl in rivers:
        steps = 0
        cur = k
        while not (ocean_c[cur] or lake[cur]):
            nxt = down[cur]
            assert nxt >= 0, "a river path ended before reaching the sea or a lake"
            assert filled[nxt] <= filled[cur], "a river flowed uphill"
            cur = nxt
            steps += 1
            assert steps < 10000, "river path loops"
    print(f"check_rivers_flow_downhill_to_sea_or_lake: PASSED ({len(rivers)} river cells)")


def check_coastline_radius_matches_real_coast(grid, info):
    w, h = len(grid[0]), len(grid)
    cx, cy = w / 2, h / 2
    for b in range(0, world.COAST_BINS, 10):
        ang = b / world.COAST_BINS * math.tau
        r = world.coastline_radius(ang, info)
        dx, dy = math.cos(ang), math.sin(ang)
        tx, ty = int(cx + dx * r), int(cy + dy * r)
        assert grid[ty][tx] != world.WATER or r <= 0, f"angle bin {b}: coast point is water"
        # everything past the recorded coast is water, out to the map rim
        rr = r + 1.5
        while rr < min(w, h) / 2 - 1:
            ix, iy = int(cx + dx * rr), int(cy + dy * rr)
            assert grid[iy][ix] == world.WATER, f"angle bin {b}: land at r={rr:.0f} past the coast r={r:.0f}"
            rr += 1.0
    print("check_coastline_radius_matches_real_coast: PASSED")


def check_spawn_on_sea_shore_and_walkways_over_water():
    laid = []
    real_stamp = world.stamp_walkway

    def recording_stamp(grid, from_tile, to_tile, plank_tile_id):
        # sample the tiles along the walkway BEFORE the planks go down
        fx, fy = from_tile
        tx, ty = to_tile
        n = max(1, int(math.hypot(tx - fx, ty - fy)))
        tiles = [grid[int(fy + (ty - fy) * s / n)][int(fx + (tx - fx) * s / n)] for s in range(2, n - 1)]
        laid.append(tiles)
        return real_stamp(grid, from_tile, to_tile, plank_tile_id)

    world.stamp_walkway = recording_stamp
    try:
        random.seed(31)
        sim = realm_sim.RealmSim(bonus=False)
    finally:
        world.stamp_walkway = real_stamp
    assert len(laid) >= 8, f"expected most islands to get a walkway, got {len(laid)}"
    for tiles in laid:
        land = [t for t in tiles if t != world.WATER]
        assert not land, f"a walkway was laid across {len(land)} land tiles"
    sp = sim._beach_spawn
    tx, ty = int(sp.x // realm_sim.TILE), int(sp.y // realm_sim.TILE)
    # the arrival plaza (world.stamp_realm_start) is stamped over the spawn, so look nearby
    near_ocean = any(world.is_ocean(sim.realm_info, x, y)
                     for y in range(ty - 12, ty + 13) for x in range(tx - 12, tx + 13))
    assert near_ocean, "the beach spawn must be next to the open sea, not a river bank or lake"
    print("check_spawn_on_sea_shore_and_walkways_over_water: PASSED")


if __name__ == "__main__":
    check_all_biomes_present_with_real_share()
    check_generation_time_budget()
    grid, info = _build(41)
    check_inner_tier_toward_centre(grid)
    check_rivers_flow_downhill_to_sea_or_lake(info)
    check_coastline_radius_matches_real_coast(grid, info)
    check_spawn_on_sea_shore_and_walkways_over_water()
    print("PASSED: terrain generation checks all green.")
