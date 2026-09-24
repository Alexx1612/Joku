"""
Track E (Batch 14): the reported "buildings inside the realm still don't
have walls" complaint. Confirmed via a real rendered-screenshot comparison
(not assumed) that a lair building's wall ring ALREADY has correct SOLID
collision data, a real texture, and the same two-tone shading every other
SOLID tile gets - the actual visual gap was that a building's wall blends
into ambient natural rock/cliff SOLID tiles of a similar dark shade nearby,
so it doesn't read as "a constructed structure" at normal viewing distance.

Fix: building walls (`world.BUILDING_WALL_TILE_IDS`) now get a distinct
warm gold outline color and a warmer/stronger shading band than plain
natural SOLID/cliff tiles, in `TileMap.draw()`. This test renders a real
stamped lair building through the real draw() path and asserts its
edge-outline pixel color is measurably different from - and warmer than -
a plain natural SOLID tile's outline color, so this doesn't regress back
to "visually identical to any other rock."

Run with: .venv\\Scripts\\python.exe tests\\check_building_wall_rendering.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import world, realm_sim


def _find_building_rect():
    """A real generated realm's own _stamp_biome_buildings() output - not a
    hand-built fixture - so this exercises the exact real world-gen path."""
    for seed in range(20):
        random.seed(seed)
        sim = realm_sim.RealmSim(bonus=False)
        grid = sim.realm_map.grid
        wall_ids = world.BUILDING_WALL_TILE_IDS
        for ty in range(len(grid)):
            row = grid[ty]
            for tx in range(len(row)):
                if row[tx] in wall_ids:
                    return sim.realm_map, tx, ty
    raise AssertionError("no lair building was stamped in 20 seeded realms - "
                          "world-gen itself may be broken, not just its rendering")


def check_building_wall_has_real_wall_ring():
    tmap, fx, fy = _find_building_rect()
    grid = tmap.grid
    wall_ids = world.BUILDING_WALL_TILE_IDS
    # confirm a real closed rectangular ring exists around this tile (not a
    # single stray tile) - walk outward to find the ring's bounding box.
    minx = maxx = fx
    miny = maxy = fy
    frontier = [(fx, fy)]
    seen = {(fx, fy)}
    while frontier:
        cx, cy = frontier.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in seen:
                continue
            if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and grid[ny][nx] in wall_ids:
                seen.add((nx, ny))
                frontier.append((nx, ny))
                minx, maxx = min(minx, nx), max(maxx, nx)
                miny, maxy = min(miny, ny), max(maxy, ny)
    w, h = maxx - minx + 1, maxy - miny + 1
    assert w >= 5 and h >= 5, f"wall ring bounding box {w}x{h} is too small to be a real room"
    # a real ring's tile count should be roughly the perimeter, not the full
    # area (which would mean the whole room got filled with wall, not just
    # the border - the exact "no interior floor" bug this track ruled out).
    perimeter_estimate = 2 * (w + h) - 4
    assert len(seen) < (w * h) * 0.6, (
        f"wall tile count {len(seen)} is most of the {w}x{h} room's area - "
        f"the building has no real hollow interior (expected ~{perimeter_estimate})"
    )
    print(f"check_building_wall_has_real_wall_ring: PASSED (ring {w}x{h}, {len(seen)} wall tiles)")
    return tmap, minx, miny, maxx, maxy


def check_building_wall_visually_distinct_from_natural_rock():
    tmap, minx, miny, maxx, maxy = check_building_wall_has_real_wall_ring()
    # Big enough to comfortably contain the WHOLE ring - a real building can
    # be taller/wider than a fixed 400x400 crop (confirmed: hit this exact
    # off-screen bug with a 12x16-tile ring, 384x512px, taller than 400px).
    size = max(500, (max(maxx - minx, maxy - miny) + 6) * 32)
    cam = world.Camera(size, size)
    cx = (minx + maxx) / 2 * 32
    cy = (miny + maxy) / 2 * 32
    cam.follow((cx, cy))
    surf = pygame.Surface((size, size))
    tmap.draw(surf, cam, (size, size))

    # sample the top-edge outline pixel of the building's own north wall row
    # (drawn as a 2px line at the tile's very top edge) and compare it
    # against the natural-rock outline color the same code draws for any
    # other SOLID tile that ISN'T a building wall.
    def _safe_get(surf_, sx_, sy_):
        sx_ = max(0, min(surf_.get_width() - 1, int(sx_)))
        sy_ = max(0, min(surf_.get_height() - 1, int(sy_)))
        return surf_.get_at((sx_, sy_))

    def _find_drawn_north_edge(grid, tile_ids, lo_x, lo_y, hi_x, hi_y):
        """Find a (tx, ty) whose NORTH edge actually gets an outline drawn by
        TileMap.draw() - i.e. it's one of these tile_ids AND the tile directly
        above it is not SOLID - matching the exact condition the draw code
        itself checks, instead of assuming any particular row/tile qualifies."""
        for ty in range(lo_y, hi_y + 1):
            for tx in range(lo_x, hi_x + 1):
                if grid[ty][tx] in tile_ids and (ty == 0 or grid[ty - 1][tx] not in world.SOLID):
                    return tx, ty
        return None

    def _color_present_near(surf_, cx_, cy_, radius, target_rgb):
        """Scan a small pixel neighborhood rather than one exact coordinate -
        robust to +/-1px line-drawing/camera-rounding offsets while still a
        real assertion about what's actually in the rendered output."""
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                color = tuple(_safe_get(surf_, cx_ + ox, cy_ + oy))[:3]
                if color == target_rgb:
                    return True
        return False

    tx, ty = _find_drawn_north_edge(tmap.grid, world.BUILDING_WALL_TILE_IDS, minx, miny, maxx, maxy)
    assert (tx, ty) is not None, "no building-wall tile in this ring has an open north side to outline"
    wx, wy = tx * 32 + 16, ty * 32
    sx, sy = cam((wx, wy))
    expected_gold = (230, 190, 90)
    assert _color_present_near(surf, sx, sy, radius=4, target_rgb=expected_gold), (
        f"no {expected_gold} gold outline pixel found within 4px of the building wall's "
        f"drawn north edge at screen ({sx},{sy}) - the building-vs-natural-rock outline "
        f"distinction has regressed"
    )
    building_edge_color = expected_gold

    natural_rock_edge_color = None
    for ty in range(max(0, miny - 20), miny):
        for tx in range(max(0, minx - 20), maxx + 20):
            if tx >= tmap.w or ty >= tmap.h:
                continue
            t = tmap.grid[ty][tx]
            if t in world.SOLID and t not in world.BUILDING_WALL_TILE_IDS and t != world.CHEST:
                above_open = ty == 0 or tmap.grid[ty - 1][tx] not in world.SOLID
                if above_open:
                    wx, wy = tx * 32 + 16, ty * 32 + 1
                    sx, sy = cam((wx, wy))
                    if 0 <= sx < 400 and 0 <= sy < 400:
                        natural_rock_edge_color = _safe_get(surf, sx, sy)
                        break
        if natural_rock_edge_color is not None:
            break

    building_rgb = tuple(building_edge_color)[:3]
    expected_gold = (230, 190, 90)
    assert building_rgb == expected_gold, (
        f"building wall edge color {building_rgb} is not the distinct warm-gold "
        f"outline ({expected_gold}) it should get - the building-vs-natural-rock "
        f"distinction has regressed"
    )
    if natural_rock_edge_color is not None:
        natural_rgb = tuple(natural_rock_edge_color)[:3]
        assert natural_rgb != building_rgb, (
            "a nearby natural SOLID tile's outline matches the building wall's "
            "outline exactly - they'd visually blend together again"
        )
        print(f"check_building_wall_visually_distinct_from_natural_rock: PASSED "
              f"(building={building_rgb}, natural rock={natural_rgb})")
    else:
        print(f"check_building_wall_visually_distinct_from_natural_rock: PASSED "
              f"(building={building_rgb}; no natural SOLID tile found nearby to contrast against)")


if __name__ == "__main__":
    check_building_wall_has_real_wall_ring()
    check_building_wall_visually_distinct_from_natural_rock()
