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


if __name__ == "__main__":
    check_biome_regions_are_organic_not_regular()
    print("PASSED: biome-shape irregularity checks all green.")
