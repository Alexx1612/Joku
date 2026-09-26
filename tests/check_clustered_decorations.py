"""
Regression check that biome decoration props CLUSTER into groves/outcrops
instead of sprinkling uniformly over the land (world.py's _decorate_realm).

History: the first version of this check used the Clark-Evans nearest-neighbour
index, which fit the old seed-and-spread placement (props piled up tightly
around random centres). The 2026-09-25 decoration rewrite places props with
blue-noise (Poisson-disk-style) spacing INSIDE noise-thresholded groves - so
props are deliberately evenly spaced at the 2-5 tile scale (nearest-neighbour
R ~= 1, by design) while being strongly clustered at the grove scale (dense
groves, empty clearings). The intent - "real forests don't grow uniformly" -
is now measured where it actually lives: a quadrat test. The land is cut into
12x12-tile quadrats and the variance-to-mean ratio (VMR, the index of
dispersion) of per-quadrat prop counts is compared against a synthetic control
population of the same size sampled UNIFORMLY at random from the exact same
land mask. Uniform (Poisson) placement gives VMR ~= 1; clustering gives VMR >> 1.

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
Q = 12  # quadrat size in tiles


def _vmr(points, land_quadrats):
    counts = {q: 0 for q in land_quadrats}
    for x, y in points:
        q = (x // Q, y // Q)
        if q in counts:
            counts[q] += 1
    vals = list(counts.values())
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return var / mean if mean else 0.0


def _nn_ratio(points, area, sample=400):
    """Clark-Evans R on a random subsample (diagnostic only - see module doc)."""
    pts = random.sample(points, min(sample, len(points)))
    cells = {}
    for x, y in points:
        cells.setdefault((x // 8, y // 8), []).append((x, y))
    total = 0.0
    for x, y in pts:
        best = None
        for gy in range(y // 8 - 2, y // 8 + 3):
            for gx in range(x // 8 - 2, x // 8 + 3):
                for (px, py) in cells.get((gx, gy), ()):
                    if (px, py) != (x, y):
                        d2 = (px - x) ** 2 + (py - y) ** 2
                        if best is None or d2 < best:
                            best = d2
        total += math.sqrt(best) if best is not None else 16.0
    expected = 1.0 / (2.0 * math.sqrt(len(points) / area))
    return (total / len(pts)) / expected


def check_decoration_props_are_clustered_not_uniform():
    for seed in (1, 2, 3):
        random.seed(seed)
        t0 = time.time()
        grid = world.make_realm()
        gen_time = time.time() - t0
        h, w = len(grid), len(grid[0])

        land_tiles = []
        decor_points = []
        quad_land = {}
        for y in range(h):
            row = grid[y]
            for x in range(w):
                t = row[x]
                if t == world.WATER:
                    continue
                land_tiles.append((x, y))
                q = (x // Q, y // Q)
                quad_land[q] = quad_land.get(q, 0) + 1
                if t in DECOR_PROP_TILE_IDS:
                    decor_points.append((x, y))
        # only quadrats that are (almost) all land, so coast/river cuts don't count as "clearings"
        land_quadrats = {q for q, n in quad_land.items() if n >= Q * Q * 0.9}

        assert len(decor_points) > 50, (
            f"seed {seed}: only {len(decor_points)} decoration props placed - "
            "too few to measure clustering, something regressed in placement")

        vmr_observed = _vmr(decor_points, land_quadrats)
        control = random.sample(land_tiles, len(decor_points))
        vmr_baseline = _vmr(control, land_quadrats)
        r_nn = _nn_ratio(decor_points, len(land_tiles))
        print(f"seed {seed}: {len(decor_points)} props, gen {gen_time:.2f}s, quadrat VMR observed="
              f"{vmr_observed:.2f} baseline(uniform)={vmr_baseline:.2f}; NN ratio {r_nn:.2f} (diagnostic)")

        # the uniform control must look uniform, or the comparison means nothing
        assert 0.6 < vmr_baseline < 1.6, (
            f"seed {seed}: uniform baseline VMR={vmr_baseline:.2f} isn't ~1 - can't trust the comparison")
        # clustered: per-quadrat counts vary far more than uniform placement would give
        assert vmr_observed > 2.0 and vmr_observed > vmr_baseline * 2.0, (
            f"seed {seed}: VMR {vmr_observed:.2f} vs uniform {vmr_baseline:.2f} - props don't read as "
            "groves/clearings")
    print("check_decoration_props_are_clustered_not_uniform: PASSED")


if __name__ == "__main__":
    check_decoration_props_are_clustered_not_uniform()
    print("PASSED: clustered decoration placement checks all green.")
