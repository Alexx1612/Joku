r"""
Batch 15 Phase 3A: the realm grew to world.REALM_W x REALM_H around an unchanged
continent, and the ten islands became big (~100x100) themed landmasses in the
ocean ring. Checks: 10 islands of the right size, everything inside the map,
no island overlapping another or touching the continent, walkways/portals/
chests/camps present, the spawn never on an island, and the generation budget.

Run with: .venv\Scripts\python.exe tests\check_big_islands.py
"""
import os
import sys
import time
import random
import tempfile
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((100, 100))

from game import achievements, characters, accounts
achievements._DIR = tempfile.mkdtemp(prefix="rr_isl_ach_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_isl_chr_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_isl_acc_")

from game import world, realm_sim
from game.realm_sim import RealmSim, ISLAND_NAMES, ISLAND_WATER_GAP

TILE = realm_sim.TILE
TIME_BUDGET_S = 3.0

random.seed(7)
_t0 = time.perf_counter()
SIM = RealmSim(bonus=False)
BUILD_S = time.perf_counter() - _t0
GRID = SIM.realm_map.grid
H, W = len(GRID), len(GRID[0])
PLANKS = set(world.WALKWAY_PLANK_TILE.values())


def _tile(pos):
    return int(pos.x // TILE), int(pos.y // TILE)


def _in_bounds(tx, ty, margin=0):
    return margin <= tx < W - margin and margin <= ty < H - margin


def check_map_grew_and_budget():
    assert (W, H) == (world.REALM_W, world.REALM_H) and W >= 1300, (W, H)
    print(f"  RealmSim() {W}x{H}: {BUILD_S:.2f}s")
    assert BUILD_S <= TIME_BUDGET_S, f"RealmSim took {BUILD_S:.2f}s, budget {TIME_BUDGET_S}s"
    print("check_map_grew_and_budget: PASSED")


def check_ten_big_islands_in_bounds_no_overlap():
    assert len(SIM.islands) == len(ISLAND_NAMES) == 10, len(SIM.islands)
    rects = []
    for isl in SIM.islands:
        r = isl["rect"]
        assert 80 <= r.w <= 110 and 80 <= r.h <= 110, f"{isl['label']}: {r.w}x{r.h} tiles, want ~100x100"
        assert _in_bounds(r.left, r.top, 4) and _in_bounds(r.right - 1, r.bottom - 1, 4), \
            f"{isl['label']} rect {r} leaves the map"
        rects.append(r)
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not a.colliderect(b), f"islands overlap: {a} {b}"
    for (tx, ty) in SIM.island_tiles:
        assert _in_bounds(tx, ty, 2), (tx, ty)
    print("check_ten_big_islands_in_bounds_no_overlap: PASSED")


def _continent_component():
    """Flood fill over land (non-water, non-plank) from the spawn = the mainland."""
    sx, sy = _tile(SIM._beach_spawn)
    seen = bytearray(W * H)
    q = deque([(sx, sy)])
    seen[sy * W + sx] = 1
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H and not seen[ny * W + nx]:
                t = GRID[ny][nx]
                if t != world.WATER and t not in PLANKS:
                    seen[ny * W + nx] = 1
                    q.append((nx, ny))
    return seen


def check_islands_separate_from_continent():
    cont = _continent_component()
    joined = [t for t in SIM.island_tiles if cont[t[1] * W + t[0]]]
    assert not joined, f"{len(joined)} island tiles are connected to the continent by land"
    # a real water gap: no mainland tile within half the design gap of any island coast tile
    gap = ISLAND_WATER_GAP // 2
    for isl in SIM.islands:
        r = isl["rect"]
        coast = [(x, y) for (x, y) in SIM.island_tiles if r.collidepoint(x, y)
                 and any(GRID[y + dy][x + dx] == world.WATER for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        for (x, y) in coast[::3]:
            for yy in range(y - gap, y + gap + 1):
                for xx in range(x - gap, x + gap + 1):
                    if 0 <= xx < W and 0 <= yy < H:
                        assert not cont[yy * W + xx], f"{isl['label']} is within {gap} tiles of the mainland"
    print("check_islands_separate_from_continent: PASSED")


def check_spawn_on_continent_not_island():
    st = _tile(SIM._beach_spawn)
    assert st not in SIM.island_tiles, "spawn landed on an island"
    x0, x1 = world.CONTINENT_OFFSET, world.CONTINENT_OFFSET + world.CONTINENT_SIZE
    assert x0 <= st[0] < x1 and x0 <= st[1] < x1, f"spawn {st} outside the continent square"
    for lair in SIM.lairs:
        t = _tile(lair["pos"])
        assert _in_bounds(*t, 2)
        if lair.get("island_camp") is None:
            assert t not in SIM.island_tiles, "a continental lair landed on an island"
    print("check_spawn_on_continent_not_island: PASSED")


def check_walkways_portals_chests_camps():
    with_walkway = 0
    for isl in SIM.islands:
        r = isl["rect"].inflate(4, 4)
        planks_here = any(GRID[y][x] in PLANKS for y in range(max(0, r.top), min(H, r.bottom))
                          for x in range(max(0, r.left), min(W, r.right)))
        with_walkway += planks_here
        camps = [l for l in SIM.lairs if l.get("island_camp") == isl["idx"]]
        assert len(camps) >= 3, f"{isl['label']}: only {len(camps)} mob camps"
        for c in camps:
            assert _tile(c["pos"]) in SIM.island_tiles, f"{isl['label']} camp off the island"
        mobs = [e for e in SIM.enemies if any(e.pos.distance_to(c["pos"]) < 8 * TILE for c in camps)]
        assert len(mobs) >= 6, f"{isl['label']}: only {len(mobs)} camp mobs spawned"
        chest = [ch for ch in SIM.island_chests if ch["idx"] == isl["idx"]]
        assert chest and _tile(chest[0]["pos"]) in SIM.island_tiles, f"{isl['label']}: chest missing/off-island"
        core = _tile(isl["pos"])
        assert core in SIM.island_tiles and GRID[core[1]][core[0]] in world.TALL_PROP_TILE_IDS
    assert with_walkway >= 8, f"only {with_walkway}/10 islands got a walkway"
    links = [p for p in SIM.portals if p.kind == "island_link"]
    assert len(links) == 20, len(links)
    for p in links:
        assert _in_bounds(int(p.pos.x // TILE), int(p.pos.y // TILE), 2)
        tx, ty = int(p.target_pos[0] // TILE), int(p.target_pos[1] // TILE)
        assert _in_bounds(tx, ty, 2) and GRID[ty][tx] != world.WATER, "an island portal targets water/out of bounds"
    print(f"check_walkways_portals_chests_camps: PASSED ({with_walkway}/10 walkways, "
          f"{sum(1 for l in SIM.lairs if l.get('island_camp') is not None)} island camps)")


if __name__ == "__main__":
    check_map_grew_and_budget()
    check_ten_big_islands_in_bounds_no_overlap()
    check_islands_separate_from_continent()
    check_spawn_on_continent_not_island()
    check_walkways_portals_chests_camps()
    print("PASSED: big island checks all green.")
