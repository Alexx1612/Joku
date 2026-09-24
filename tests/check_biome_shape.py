"""
Regression check for biome-region shape irregularity (the "diamond shapes"
fix): make_realm()'s per-biome affinity field went from a flat sum of 3
independently-random plane-wave terms to a real 5-octave fBm-style sum
(frequency doubling, amplitude halving per octave) - see world.py's
_affinity()/_affinity_tables(). This measures a real geometric property of
the generated regions, not just "it renders"/"it compiles".

Metric: perimeter / sqrt(area) for each biome's set of land tiles. A perfect
circle's theoretical minimum is 2*sqrt(pi) ~= 3.5449; a perfect square is
exactly 4.0. A "diamond"/regular-polygon-like region (few, smooth, low-
frequency boundary terms) stays close to this geometric floor; a genuinely
organic, noise-driven boundary (many direction changes as the boundary
wiggles) runs measurably higher. This is an absolute, seed-independent
geometric assertion, not a comparison against old code (which no longer
exists to compare against) - it directly tests "is this shape actually
irregular", which is what was asked for.

Run with: .venv\\Scripts\\python.exe tests\\check_biome_shape.py
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

import random
from game import world

# a perfect square's perimeter/sqrt(area) is exactly 4.0 - the floor for any
# axis-aligned regular blob. Real organic, noise-carved coastlines/biome
# boundaries should run measurably above this.
REGULAR_POLYGON_FLOOR = 4.0
IRREGULARITY_THRESHOLD = 4.6  # a modest, defensible margin above the floor


def _shape_irregularity(grid, ground_tile):
    h, w = len(grid), len(grid[0])
    area = 0
    perimeter = 0
    for y in range(h):
        row = grid[y]
        for x in range(w):
            if row[x] != ground_tile:
                continue
            area += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h) or grid[ny][nx] != ground_tile:
                    perimeter += 1
    if area == 0:
        return None
    return perimeter / math.sqrt(area)


def check_biome_regions_are_organic_not_regular():
    seeds_checked = 0
    ratios = []
    for seed in (1, 2, 3):
        random.seed(seed)
        grid = world.make_realm()
        for biome_ground_tile in set(world.BIOME_GROUND.values()):
            ratio = _shape_irregularity(grid, biome_ground_tile)
            if ratio is None:
                continue  # that biome got ~zero territory this seed - rare, not a failure
            ratios.append(ratio)
            assert ratio > REGULAR_POLYGON_FLOOR, (
                f"seed {seed} tile {biome_ground_tile}: ratio {ratio:.2f} at or below the "
                f"perfect-square floor ({REGULAR_POLYGON_FLOOR}) - shape reads as regular, not organic")
        seeds_checked += 1
    assert seeds_checked == 3
    above_threshold = sum(1 for r in ratios if r > IRREGULARITY_THRESHOLD)
    print(f"measured {len(ratios)} biome-region shapes across 3 seeds; "
          f"{above_threshold} exceed the {IRREGULARITY_THRESHOLD} irregularity threshold "
          f"(range {min(ratios):.2f}-{max(ratios):.2f})")
    assert above_threshold >= len(ratios) * 0.7, (
        "most measured biome regions should read as genuinely irregular, not just barely above square")
    # real variation across seeds/biomes - not one fixed constant every time
    assert len(set(round(r, 2) for r in ratios)) > 3, "shapes should vary across seeds/biomes, not repeat a constant"
    print("check_biome_regions_are_organic_not_regular: PASSED")


def _convex_hull(points):
    """Monotone chain, no external deps. points: list of (x, y). Returns hull
    vertices in CCW order (len < 3 if degenerate)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _polygon_area(hull):
    if len(hull) < 3:
        return 0.0
    total = 0.0
    n = len(hull)
    for i in range(n):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


# A REAL macro-silhouette check the perimeter/sqrt(area) roughness metric
# above genuinely can't catch (confirmed by rendering actual seeded realms to
# PNGs and looking at them: the inner-tier biome cluster showed visibly
# straighter/more diamond-like boundaries than the outer tier, while still
# passing the roughness check above just fine, since fine-scale octave noise
# texture on the EDGE was enough to pass that test even though the overall
# SHAPE traced out something close to a simple convex polygon). This test
# instead measures how much smaller the actual filled region is than its own
# convex hull - a true diamond/square/regular-polygon region IS its own
# convex hull (ratio ~1.0, no concavity anywhere); a genuinely organic,
# lobed/concave region is measurably smaller than its hull, since the hull
# "fills in" every concave dent and bay the real irregular outline has.
HULL_FILL_RATIO_CEILING = 0.92  # a real diamond/regular-polygon region would sit near 1.0


def check_biome_regions_are_not_convex_diamonds():
    seeds_checked = 0
    ratios = []
    for seed in (1, 2, 3):
        random.seed(seed)
        grid = world.make_realm()
        h, w = len(grid), len(grid[0])
        for biome_ground_tile in set(world.BIOME_GROUND.values()):
            points = [(x, y) for y in range(h) for x in range(w) if grid[y][x] == biome_ground_tile]
            area = len(points)
            if area < 200:
                continue  # too small this seed to measure a meaningful hull - not a failure
            hull = _convex_hull(points)
            hull_area = _polygon_area(hull)
            if hull_area <= 0:
                continue
            ratio = area / hull_area
            ratios.append(ratio)
            assert ratio < HULL_FILL_RATIO_CEILING, (
                f"seed {seed} tile {biome_ground_tile}: fill/hull ratio {ratio:.3f} is at or "
                f"above {HULL_FILL_RATIO_CEILING} - this region is nearly its own convex hull, "
                f"i.e. it reads as a simple diamond/regular polygon at the macro scale, not a "
                f"genuinely lobed/concave organic shape")
        seeds_checked += 1
    assert seeds_checked == 3
    print(f"measured {len(ratios)} biome-region fill/hull ratios across 3 seeds "
          f"(range {min(ratios):.3f}-{max(ratios):.3f}, ceiling {HULL_FILL_RATIO_CEILING})")
    print("check_biome_regions_are_not_convex_diamonds: PASSED")


if __name__ == "__main__":
    check_biome_regions_are_organic_not_regular()
    check_biome_regions_are_not_convex_diamonds()
    print("PASSED: biome-shape irregularity checks all green.")
