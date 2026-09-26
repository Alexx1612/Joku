"""
Decoration placement on the noise terrain (world._decorate_realm + the
RealmSim vignette/island/clearance passes):

  * decoration art actually loads in the REAL game's import order (main.py /
    coop_client.py import game.world before any display mode exists - every
    hand-painted PNG used to silently fall back to a flat ground-coloured tile,
    i.e. invisible props), and no prop kind is left without art;
  * props stay off water edges (ocean always; fresh water except water-loving kinds);
  * no solid outcrop ROCK near a landmark/building/terrace, a lair, a walkway
    landing or the arrival plaza - and every landmark, lair and island is
    reachable on foot from the spawn;
  * blue-noise spacing inside groves is respected per biome;
  * density really varies: groves are much denser than clearings;
  * curated counts kept: 20 vignettes/biome target on plain ground in their own
    footprint, 10 island props laid out around each island's landmark.

Run with: .venv\\Scripts\\python.exe tests\\check_decoration_placement.py
"""
import math
import os
import random
import subprocess
import sys
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import world
from game import constants as C
from game.realm_sim import RealmSim

random.seed(11)
SIM = RealmSim(bonus=False)
GRID = SIM.realm_map.grid
H, W = len(GRID), len(GRID[0])
INFO = SIM.realm_info
DECOR = INFO["decor"]
PROP_KIND = {tid: (b, k) for (b, k), tid in world.BIOME_PROP_TILE.items()}


def _tile(v):
    return int(v.x // C.TILE), int(v.y // C.TILE)


def check_art_loads_in_real_import_order():
    """Fresh interpreter, world imported BEFORE set_mode (exactly like main.py)."""
    code = (
        "import os; os.environ['SDL_VIDEODRIVER']='dummy'\n"
        "import pygame; pygame.init()\n"
        "from game import world as W\n"
        "def distinct(s):\n"
        "    return len({tuple(s.get_at((x, y))) for x in range(0, s.get_width(), 3) for y in range(0, s.get_height(), 3)})\n"
        "flat = [k for (b, k), t in W.BIOME_PROP_TILE.items() if distinct(W._BIOME_PROP_TEX[t][0]) < 4]\n"
        "flat += [k for (a, k), t in W.ISLAND_PROP_TILE.items() if distinct(W._ISLAND_PROP_TEX[t][0]) < 4]\n"
        "tree = W._BIOME_PROP_TEX[W.BIOME_PROP_TILE[('forest', 'tree')]][0]\n"
        "print('FLAT', sorted(set(flat)))\n"
        "print('PENDING', len(W._UNCONVERTED))\n"
        "pygame.display.set_mode((50, 50)); W._finalize_textures()\n"
        "print('FINAL', W._textures_final, len(W._UNCONVERTED), distinct(tree))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True).stdout
    lines = {ln.split(" ", 1)[0]: ln.split(" ", 1)[1] for ln in out.splitlines() if " " in ln}
    assert lines.get("FLAT") == "[]", f"prop kinds still rendering as a flat tile: {lines.get('FLAT')}"
    assert int(lines.get("PENDING", "0")) > 100, "hand-painted PNGs didn't load before a display existed"
    final = lines.get("FINAL", "").split()
    assert final and final[0] == "True" and final[1] == "0", f"textures not finalized: {lines.get('FINAL')}"
    print(f"check_art_loads_in_real_import_order: PASSED ({lines['PENDING']} textures deferred-converted)")


def _near(x, y, pred, reach):
    for dx, dy in ((reach, 0), (-reach, 0), (0, reach), (0, -reach)):
        xx, yy = x + dx, y + dy
        if 0 <= xx < W and 0 <= yy < H and pred(xx, yy):
            return True
    return False


def check_props_off_water_edges():
    ocean = lambda x, y: world.is_ocean(INFO, x, y)
    fresh = lambda x, y: GRID[y][x] == world.WATER and not world.is_ocean(INFO, x, y)
    bad_ocean = bad_fresh = n = 0
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            pk = PROP_KIND.get(GRID[y][x])
            if pk is None:
                continue
            n += 1
            if _near(x, y, ocean, 1):
                bad_ocean += 1
            elif pk[1] not in world.WATER_LOVING_KINDS and _near(x, y, fresh, 1):
                bad_fresh += 1
    # curated vignettes/buildings stamp fixed templates, so allow a tiny residue
    assert bad_ocean <= n * 0.002, f"{bad_ocean} props sit right on the ocean edge"
    assert bad_fresh <= n * 0.01, f"{bad_fresh} dry-land props hug a river/lake bank"
    print(f"check_props_off_water_edges: PASSED ({n} props, {bad_ocean} ocean-edge, {bad_fresh} bank)")


def check_clearances_and_reachability():
    def no_rock_near(tx, ty, margin, what):
        for yy in range(max(0, ty - margin), min(H, ty + margin + 1)):
            for xx in range(max(0, tx - margin), min(W, tx + margin + 1)):
                assert GRID[yy][xx] != world.ROCK, f"solid outcrop rock at ({xx},{yy}) blocks {what} ({tx},{ty})"
    for lm in SIM.landmarks:
        no_rock_near(*_tile(lm["pos"]), world.LANDMARK_RADIUS + 2 if hasattr(world, "LANDMARK_RADIUS") else 5,
                     "landmark")
    for lair in SIM.lairs:
        no_rock_near(*_tile(lair["pos"]), 3, "lair")
    for lx, ly in SIM._walkway_landings:
        no_rock_near(lx, ly, 3, "walkway landing")
    no_rock_near(*_tile(SIM._beach_spawn), world.REALM_START_RADIUS + 2, "arrival plaza")

    # flood fill over walkable tiles from the arrival point
    start = _tile(SIM._beach_spawn)
    seen = bytearray(W * H)
    seen[start[1] * W + start[0]] = 1
    dq = deque([start])
    solid = world.SOLID
    while dq:
        x, y = dq.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H:
                k = ny * W + nx
                if not seen[k] and GRID[ny][nx] not in solid:
                    seen[k] = 1
                    dq.append((nx, ny))
    def reachable(tx, ty):
        return any(seen[yy * W + xx] for yy in range(ty - 1, ty + 2) for xx in range(tx - 1, tx + 2)
                   if 0 <= xx < W and 0 <= yy < H)
    unreach = [("landmark", lm["name"]) for lm in SIM.landmarks if not reachable(*_tile(lm["pos"]))]
    unreach += [("island", isl["label"]) for isl in SIM.islands if not reachable(*_tile(isl["pos"]))]
    # landmark buildings have a doorway now (world.stamp_lair_building), so EVERY
    # lair - including the one inside each building - must be reachable on foot
    lairs_unreached = [_tile(l["pos"]) for l in SIM.lairs if not reachable(*_tile(l["pos"]))]
    assert not unreach, f"unreachable on foot from the spawn: {unreach}"
    assert not lairs_unreached, f"{len(lairs_unreached)} lairs unreachable on foot: {lairs_unreached[:5]}"
    print(f"check_clearances_and_reachability: PASSED ({len(SIM.landmarks)} landmarks, "
          f"{len(SIM.islands)} islands, all {len(SIM.lairs)} lairs reachable)")


def check_grove_spacing():
    # biome of each recorded grove point = the biome of the prop placed there at generation
    all_pts = [p for pts in DECOR["grove_points"].values() for p in pts]
    cells = {}
    for p in all_pts:
        cells.setdefault((p[0] >> 2, p[1] >> 2), []).append(p)
    violations = 0
    checked = 0
    for (x, y) in random.Random(3).sample(all_pts, min(3000, len(all_pts))):
        b = world.TILE_TO_BIOME_NAME.get(GRID[y][x])
        if b is None or GRID[y][x] not in PROP_KIND:
            continue   # overwritten later by a structure - not part of the scatter anymore
        checked += 1
        for gy in range((y >> 2) - 2, (y >> 2) + 3):
            for gx in range((x >> 2) - 2, (x >> 2) + 3):
                for (px, py) in cells.get((gx, gy), ()):
                    if (px, py) == (x, y):
                        continue
                    # each dart is spaced by ITS biome's radius, so across a biome border
                    # the tighter of the two spacings applies (0.8 = a grove core's factor)
                    b2 = world.TILE_TO_BIOME_NAME.get(GRID[py][px], b)
                    min_d = min(DECOR["spacing"][b], DECOR["spacing"].get(b2, 99)) * 0.8 - 1e-6
                    if (px - x) ** 2 + (py - y) ** 2 < min_d * min_d:
                        violations += 1
    assert checked > 500, f"too few grove points checked ({checked})"
    assert violations == 0, f"{violations} grove props closer than their biome's blue-noise spacing"
    print(f"check_grove_spacing: PASSED ({checked} grove props, spacing respected)")


def check_groves_denser_than_clearings():
    dens, thr = DECOR["dens"], DECOR["thr"]
    counts = {"grove": [0, 0], "clear": [0, 0]}  # [props, land tiles]
    for y in range(3, H - 3, 2):
        for x in range(3, W - 3, 2):
            t = GRID[y][x]
            b = world.TILE_TO_BIOME_NAME.get(t)
            if b is None:
                continue
            key = "grove" if world._coarse_sample(dens, x, y) >= thr[b] else "clear"
            counts[key][1] += 1
            if t in PROP_KIND:
                counts[key][0] += 1
    g = counts["grove"][0] / max(1, counts["grove"][1])
    c = counts["clear"][0] / max(1, counts["clear"][1])
    assert g > c * 4, f"grove density {g:.4f} isn't clearly above clearing density {c:.4f}"
    print(f"check_groves_denser_than_clearings: PASSED (grove {g:.3f} vs clearing {c:.4f} props/tile)")


def check_curated_counts_and_footprints():
    per = {}
    for v in SIM.biome_vignettes:
        per[v["biome"]] = per.get(v["biome"], 0) + 1
        ax, ay = v["anchor"]
        r = world.BIOME_VIGNETTE_RADIUS
        for yy in range(ay - r, ay + r + 1):
            for xx in range(ax - r, ax + r + 1):
                assert world.TILE_TO_BIOME_NAME.get(GRID[yy][xx]) == v["biome"] or GRID[yy][xx] in (
                    world.DIRT,), f"vignette at {v['anchor']} sits on foreign ground {GRID[yy][xx]}"
    assert sum(per.values()) >= 150 and all(n >= 1 for n in per.values()), per
    anchors = [v["anchor"] for v in SIM.biome_vignettes]
    close = sum(1 for i, a in enumerate(anchors) for b in anchors[i + 1:]
                if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 < 16 ** 2)
    assert close == 0, f"{close} vignette pairs piled closer than 16 tiles"
    for isl in SIM.islands:
        cx, cy = _tile(isl["pos"])
        found = {}
        for yy in range(cy - 10, cy + 11):
            for xx in range(cx - 10, cx + 11):
                if 0 <= xx < W and 0 <= yy < H:
                    for (area, kind), tid in world.ISLAND_PROP_TILE.items():
                        if GRID[yy][xx] == tid and area == isl["theme"]:
                            found[kind] = math.hypot(xx - cx, yy - cy)
        assert len(found) == 10, f"{isl['label']}: {len(found)} curated props"
        assert all(1.5 < d < 8.5 for d in found.values()), f"{isl['label']}: props strayed off the ring {found}"
    print(f"check_curated_counts_and_footprints: PASSED ({sum(per.values())} vignettes, "
          f"10 ringed props on each of {len(SIM.islands)} islands)")


if __name__ == "__main__":
    check_art_loads_in_real_import_order()
    check_props_off_water_edges()
    check_clearances_and_reachability()
    check_grove_spacing()
    check_groves_denser_than_clearings()
    check_curated_counts_and_footprints()
    print("PASSED: decoration placement checks all green.")
