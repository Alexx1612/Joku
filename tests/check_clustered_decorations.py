"""
Regression check for the clustered biome-prop placement rewrite: the main
continent decorator pass (world.py's make_realm(), the "scattered single-tile
decoration props" section) used to sample every prop's (x, y) independently
and uniformly across the whole land area. It now picks a handful of cluster
centers first and scatters each cluster's props around its center with a
density that falls off with distance - "real forests don't grow uniformly."

This measures a real spatial statistic (the Clark-Evans nearest-neighbor
index) on the actual placed decoration-prop tiles, and separately on a
synthetic control population of the same size sampled UNIFORMLY at random
from the exact same land mask - so the comparison isn't just against a
theoretical formula's edge-effect assumptions, it's against a real empirical
"what would independent uniform placement on this exact map have looked
like" baseline.

Clark-Evans R = (observed mean nearest-neighbor distance) / (expected mean
NN distance under complete spatial randomness, 1/(2*sqrt(density))). R < 1
means points are closer together than random chance would produce (i.e.
clustered); R ~= 1 means random; R > 1 means dispersed/regular.

Run with: .venv\\Scripts\\python.exe tests\\check_clustered_decorations.py
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

from game import world

DECOR_PROP_TILE_IDS = set(world.BIOME_PROP_TILE.values())


def _nn_mean_distance(points):
    """Mean nearest-neighbor distance across a list of (x, y) points. O(n^2)
    but n is only ~1-2k for this map size, which is trivial in practice."""
    n = len(points)
    if n < 2:
        return None
    total = 0.0
    for i in range(n):
        xi, yi = points[i]
        best = None
        for j in range(n):
            if i == j:
                continue
            xj, yj = points[j]
            d2 = (xi - xj) ** 2 + (yi - yj) ** 2
            if best is None or d2 < best:
                best = d2
        total += math.sqrt(best)
    return total / n


def _clark_evans_r(points, area):
    n = len(points)
    mean_nn = _nn_mean_distance(points)
    if mean_nn is None or n == 0 or area <= 0:
        return None
    density = n / area
    expected_nn = 1.0 / (2.0 * math.sqrt(density))
    return mean_nn / expected_nn


def check_decoration_props_are_clustered_not_uniform():
    r_values_observed = []
    r_values_baseline = []
    for seed in (1, 2, 3):
        random.seed(seed)
        t0 = time.time()
        grid = world.make_realm()
        gen_time = time.time() - t0
        h, w = len(grid), len(grid[0])

        land_tiles = []
        decor_points = []
        for y in range(h):
            row = grid[y]
            for x in range(w):
                t = row[x]
                if t == world.WATER:
                    continue
                land_tiles.append((x, y))
                if t in DECOR_PROP_TILE_IDS:
                    decor_points.append((x, y))

        assert len(decor_points) > 50, (
            f"seed {seed}: only {len(decor_points)} decoration props placed - "
            "too few to measure clustering, something regressed in placement")

        land_area = len(land_tiles)
        r_observed = _clark_evans_r(decor_points, land_area)
        assert r_observed is not None

        # empirical control: same N points, sampled uniformly at random from
        # the exact same land mask (not the whole rectangle), so this is a
        # fair apples-to-apples comparison against what independent uniform
        # placement really would have produced on this exact coastline.
        control_sample = random.sample(land_tiles, min(len(decor_points), len(land_tiles)))
        r_baseline = _clark_evans_r(control_sample, land_area)
        assert r_baseline is not None

        r_values_observed.append(r_observed)
        r_values_baseline.append(r_baseline)
        print(f"seed {seed}: {len(decor_points)} props, gen {gen_time:.2f}s, "
              f"Clark-Evans R observed={r_observed:.3f} baseline(uniform)={r_baseline:.3f}")

        # 1. Clark-Evans criterion: R < 1.0 means points sit closer together
        #    than chance alone would produce - the textbook definition of
        #    clustering.
        assert r_observed < 1.0, (
            f"seed {seed}: observed R={r_observed:.3f} is not below 1.0 - "
            "decoration props don't read as clustered")

        # 2. The empirical uniform-baseline control should land close to 1.0
        #    (it's drawn from literal random.sample, i.e. what the OLD code's
        #    behavior effectively was) - confirms the baseline itself isn't
        #    secretly clustered for some domain-shape reason.
        assert 0.8 < r_baseline < 1.2, (
            f"seed {seed}: uniform baseline R={r_baseline:.3f} isn't close to 1.0 - "
            "baseline sampling itself looks off, can't trust the comparison")

        # 3. The real test: observed clustering must be measurably tighter
        #    than the uniform-random control on the SAME map, not just
        #    below the generic 1.0 threshold.
        assert r_observed < r_baseline * 0.85, (
            f"seed {seed}: observed R={r_observed:.3f} isn't meaningfully "
            f"below the uniform baseline R={r_baseline:.3f} - clustering effect "
            "is too weak to be real")

    print(f"observed R range: {min(r_values_observed):.3f}-{max(r_values_observed):.3f}; "
          f"baseline R range: {min(r_values_baseline):.3f}-{max(r_values_baseline):.3f}")
    print("check_decoration_props_are_clustered_not_uniform: PASSED")


if __name__ == "__main__":
    check_decoration_props_are_clustered_not_uniform()
    print("PASSED: clustered decoration placement checks all green.")
