"""
Procedural art for the decoration prop kinds that never got a hand-painted PNG
(5 of the 27 biome prop kinds and all 20 island prop kinds). Before this they
fell back to a flat tile the exact colour of the ground, i.e. they were placed
but invisible. Each recipe draws a small original sprite with pygame primitives
on top of the tile's own ground texture, at 2x and smoothscaled down so edges
read soft like the painted props. Only used when the PNG is missing - a painted
file with the same name always wins (see world._load_tile_variants).
"""
import math
import random

import pygame

S = 64  # working canvas (drawn at 2x, scaled to the tile size at the end)


def _shadow(layer, cx, cy, rx, ry, alpha=70):
    pygame.draw.ellipse(layer, (0, 0, 0, alpha), (cx - rx, cy - ry, rx * 2, ry * 2))


def _shade(c, d):
    return tuple(max(0, min(255, v + d)) for v in c)


def _pebbles(L, r):
    for _ in range(7):
        x, y = r.randint(10, 52), r.randint(14, 54)
        w, h = r.randint(6, 11), r.randint(4, 8)
        g = r.randint(150, 200)
        _shadow(L, x + 1, y + 3, w // 2 + 1, h // 2, 60)
        pygame.draw.ellipse(L, (g, g, g - 6), (x - w // 2, y - h // 2, w, h))
        pygame.draw.ellipse(L, (g + 45, g + 45, g + 40), (x - w // 4, y - h // 2 + 1, max(2, w // 3), max(2, h // 3)))


def _wildflowers(L, r):
    for _ in range(12):
        x, y = r.randint(8, 56), r.randint(12, 58)
        pygame.draw.line(L, (70, 140, 60), (x, y), (x + r.randint(-3, 3), y - r.randint(6, 11)), 2)
    for _ in range(9):
        x, y = r.randint(10, 54), r.randint(10, 50)
        col = r.choice([(250, 220, 90), (240, 130, 170), (245, 245, 245), (170, 120, 230), (255, 160, 80)])
        for dx, dy in ((0, -2), (2, 0), (0, 2), (-2, 0)):
            pygame.draw.circle(L, col, (x + dx, y + dy), 2)
        pygame.draw.circle(L, (250, 200, 60), (x, y), 1)


def _dead_tree(L, r):
    _shadow(L, 34, 56, 16, 5)
    bark = (82, 62, 46)
    pygame.draw.polygon(L, bark, [(28, 58), (36, 58), (35, 28), (30, 28)])
    for (x0, y0, x1, y1) in ((32, 34, 16, 18), (33, 30, 48, 12), (32, 40, 48, 30), (32, 26, 26, 8), (22, 24, 12, 22)):
        pygame.draw.line(L, bark, (x0, y0), (x1, y1), 3)
    pygame.draw.line(L, _shade(bark, 30), (31, 56), (31, 30), 1)


def _berry_bush(L, r):
    _shadow(L, 32, 52, 20, 6)
    for (x, y, rad, d) in ((22, 38, 12, 0), (42, 38, 12, -8), (32, 28, 13, 10)):
        pygame.draw.circle(L, _shade((52, 118, 52), d), (x, y), rad)
    for _ in range(9):
        pygame.draw.circle(L, (200, 40, 60), (r.randint(16, 48), r.randint(22, 46)), 2)
    pygame.draw.circle(L, (90, 160, 80), (28, 24), 4)


def _reeds(L, r):
    for i in range(8):
        x = 16 + i * 4 + r.randint(-2, 2)
        top = r.randint(8, 22)
        pygame.draw.line(L, (104, 128, 60), (x, 58), (x + r.randint(-4, 4), top), 2)
        if i % 3 == 0:
            pygame.draw.ellipse(L, (110, 72, 40), (x - 2 + r.randint(-3, 3), top - 2, 5, 11))


def _coral(L, r):
    _shadow(L, 32, 54, 18, 5)
    col = r.choice([(240, 120, 130), (250, 150, 90)])

    def branch(x, y, ang, length, depth):
        if depth == 0 or length < 4:
            pygame.draw.circle(L, _shade(col, 30), (int(x), int(y)), 3)
            return
        x2, y2 = x + math.cos(ang) * length, y - math.sin(ang) * length
        pygame.draw.line(L, col, (x, y), (x2, y2), max(2, depth + 1))
        branch(x2, y2, ang + 0.5, length * 0.7, depth - 1)
        branch(x2, y2, ang - 0.45, length * 0.7, depth - 1)
    branch(32, 56, math.pi / 2, 16, 3)


def _pearl_shell(L, r):
    _shadow(L, 32, 50, 18, 5)
    shell = (235, 205, 190)
    pygame.draw.circle(L, shell, (32, 40), 16, draw_top_right=True, draw_top_left=True)
    for i in range(7):
        a = math.pi * (i + 0.5) / 7
        pygame.draw.line(L, _shade(shell, -40), (32, 40), (32 + math.cos(a) * 15, 40 - math.sin(a) * 15), 1)
    pygame.draw.rect(L, _shade(shell, -25), (18, 40, 28, 4))
    pygame.draw.circle(L, (250, 250, 255), (32, 36), 5)
    pygame.draw.circle(L, (255, 255, 255), (30, 34), 2)


def _altar(L, r):
    _shadow(L, 32, 52, 22, 6)
    stone = (130, 140, 150)
    pygame.draw.rect(L, _shade(stone, -30), (12, 30, 40, 20))
    pygame.draw.rect(L, stone, (10, 24, 44, 10))
    pygame.draw.rect(L, (60, 150, 140), (12, 26, 12, 4))
    pygame.draw.ellipse(L, (70, 120, 200, 160), (26, 44, 22, 8))


def _kelp(L, r):
    for k in range(3):
        x0 = 20 + k * 12
        pts = [(x0 + math.sin(t * 0.9 + k) * 5, 58 - t * 5) for t in range(10)]
        pygame.draw.lines(L, (40, 110, 70), False, pts, 3)
        pygame.draw.lines(L, (80, 160, 100), False, [(x + 1, y) for x, y in pts], 1)


def _barnacle_rock(L, r):
    _shadow(L, 32, 52, 20, 6)
    pygame.draw.ellipse(L, (110, 108, 104), (12, 26, 40, 28))
    pygame.draw.ellipse(L, (150, 148, 142), (18, 28, 20, 10))
    for _ in range(10):
        x, y = r.randint(18, 46), r.randint(30, 50)
        pygame.draw.circle(L, (235, 232, 220), (x, y), 3)
        pygame.draw.circle(L, (90, 90, 90), (x, y), 1)


def _tide_pool(L, r):
    pygame.draw.ellipse(L, (150, 140, 120), (8, 18, 48, 32))
    pygame.draw.ellipse(L, (50, 110, 170), (12, 22, 40, 24))
    pygame.draw.ellipse(L, (120, 190, 230), (18, 26, 14, 6))
    pygame.draw.circle(L, (240, 150, 60), (40, 36), 3)


def _bell(L, r):
    _shadow(L, 32, 54, 18, 5)
    bronze = (170, 120, 50)
    pygame.draw.polygon(L, bronze, [(20, 50), (44, 50), (40, 22), (24, 22)])
    pygame.draw.circle(L, bronze, (32, 22), 8)
    pygame.draw.ellipse(L, (60, 40, 20), (20, 46, 24, 7))
    pygame.draw.line(L, (90, 170, 130), (26, 28), (24, 46), 3)
    pygame.draw.line(L, _shade(bronze, 50), (37, 24), (40, 46), 2)


def _driftwood_arch(L, r):
    _shadow(L, 32, 56, 22, 5)
    wood = (150, 125, 95)
    pygame.draw.rect(L, wood, (12, 26, 7, 30))
    pygame.draw.rect(L, wood, (45, 26, 7, 30))
    pygame.draw.arc(L, wood, (10, 8, 44, 40), 0, math.pi, 7)
    pygame.draw.line(L, _shade(wood, 35), (14, 28), (14, 54), 1)


def _anemone(L, r):
    _shadow(L, 32, 50, 16, 5)
    for i in range(16):
        a = i / 16 * math.tau
        pygame.draw.line(L, (230, 90, 200), (32, 38), (32 + math.cos(a) * 15, 38 + math.sin(a) * 11), 3)
    pygame.draw.circle(L, (150, 60, 170), (32, 38), 7)
    pygame.draw.circle(L, (250, 170, 240), (30, 36), 2)


def _lantern(L, r):
    _shadow(L, 32, 58, 12, 4)
    pygame.draw.circle(L, (255, 230, 120, 70), (32, 20), 16)
    pygame.draw.rect(L, (60, 50, 50), (30, 26, 4, 32))
    pygame.draw.rect(L, (70, 60, 50), (24, 12, 16, 16))
    pygame.draw.rect(L, (255, 225, 110), (27, 15, 10, 10))


def _cracked_pillar(L, r):
    _shadow(L, 32, 57, 14, 5)
    stone = (120, 115, 120)
    pygame.draw.rect(L, stone, (23, 14, 18, 44))
    pygame.draw.rect(L, _shade(stone, 30), (21, 10, 22, 6))
    pygame.draw.lines(L, (50, 45, 50), False, [(32, 16), (28, 26), (35, 34), (29, 44), (33, 56)], 2)
    pygame.draw.line(L, (255, 140, 60), (35, 34), (29, 44), 1)


def _ember_vent(L, r):
    pygame.draw.ellipse(L, (40, 30, 30), (12, 24, 40, 24))
    pygame.draw.ellipse(L, (230, 90, 30), (20, 29, 24, 14))
    pygame.draw.ellipse(L, (255, 200, 80), (26, 32, 12, 7))
    for _ in range(4):
        pygame.draw.circle(L, (255, 150, 60), (r.randint(22, 42), r.randint(12, 26)), 2)


def _shard_chunk(L, r):
    _shadow(L, 32, 56, 12, 4, 55)
    pts = [(32, 6), (44, 22), (38, 40), (26, 40), (20, 20)]
    pygame.draw.polygon(L, (140, 90, 210), pts)
    pygame.draw.polygon(L, (200, 160, 250), [(32, 6), (38, 20), (30, 26), (24, 18)])
    pygame.draw.polygon(L, (90, 50, 150), pts, 2)


def _rune_scorch(L, r):
    pygame.draw.circle(L, (25, 20, 20, 170), (32, 34), 20)
    pygame.draw.circle(L, (240, 110, 40), (32, 34), 14, 2)
    for a in (0.3, 2.4, 4.4):
        pygame.draw.line(L, (255, 170, 70), (32, 34), (32 + math.cos(a) * 12, 34 + math.sin(a) * 12), 2)


def _fury_crystal(L, r):
    _shadow(L, 32, 55, 16, 5)
    for (x, h, c) in ((24, 26, (200, 40, 70)), (34, 36, (230, 60, 90)), (42, 22, (170, 30, 60))):
        pygame.draw.polygon(L, c, [(x - 6, 54), (x + 6, 54), (x, 54 - h)])
        pygame.draw.line(L, _shade(c, 70), (x, 54 - h), (x - 3, 52), 1)


def _broken_statue(L, r):
    _shadow(L, 32, 57, 18, 5)
    stone = (150, 145, 140)
    pygame.draw.rect(L, _shade(stone, -30), (16, 44, 32, 12))
    pygame.draw.polygon(L, stone, [(22, 44), (42, 44), (40, 22), (34, 16), (30, 24), (24, 20)])
    pygame.draw.circle(L, _shade(stone, -15), (47, 52), 4)


def _ash_drift(L, r):
    for (x, y, w, h) in ((10, 34, 26, 12), (28, 28, 28, 14), (20, 44, 24, 10)):
        pygame.draw.ellipse(L, (150, 145, 145), (x, y, w, h))
        pygame.draw.ellipse(L, (185, 180, 180), (x + 4, y + 1, w // 2, h // 3))


def _brazier(L, r):
    _shadow(L, 32, 57, 14, 4)
    iron = (60, 55, 60)
    pygame.draw.line(L, iron, (24, 56), (30, 36), 3)
    pygame.draw.line(L, iron, (40, 56), (34, 36), 3)
    pygame.draw.polygon(L, iron, [(18, 30), (46, 30), (40, 40), (24, 40)])
    pygame.draw.polygon(L, (240, 110, 40), [(22, 30), (28, 12), (32, 22), (37, 8), (42, 30)])
    pygame.draw.polygon(L, (255, 210, 90), [(27, 30), (32, 18), (37, 30)])


def _rubble(L, r):
    _shadow(L, 32, 52, 20, 6)
    for _ in range(7):
        x, y = r.randint(16, 46), r.randint(28, 50)
        g = r.randint(125, 175)
        pts = [(x + r.randint(-7, 7), y + r.randint(-6, 6)) for _ in range(4)]
        pygame.draw.polygon(L, (g, g - 4, g - 8), pts)


def _scorched_banner(L, r):
    _shadow(L, 32, 58, 10, 3)
    pygame.draw.line(L, (70, 55, 45), (24, 58), (24, 8), 3)
    pygame.draw.polygon(L, (140, 30, 30), [(26, 10), (50, 12), (46, 20), (50, 28), (44, 34), (26, 32)])
    pygame.draw.polygon(L, (40, 20, 20), [(40, 28), (44, 34), (36, 32)])


RECIPES = {
    "pebbles": _pebbles, "wildflower_patch": _wildflowers, "dead_tree": _dead_tree,
    "berry_bush": _berry_bush, "reed_cluster": _reeds,
    "coral_cluster": _coral, "pearl_shell": _pearl_shell, "drowned_altar": _altar, "kelp_strand": _kelp,
    "barnacle_rock": _barnacle_rock, "tide_pool": _tide_pool, "sunken_bell": _bell,
    "driftwood_arch": _driftwood_arch, "anemone_bloom": _anemone, "choir_lantern": _lantern,
    "cracked_pillar": _cracked_pillar, "ember_vent": _ember_vent, "floating_shard_chunk": _shard_chunk,
    "rune_scorch": _rune_scorch, "fury_crystal": _fury_crystal, "broken_statue": _broken_statue,
    "ash_drift": _ash_drift, "shard_brazier": _brazier, "rubble_pile": _rubble,
    "scorched_banner": _scorched_banner,
}


def paint_prop(kind, ground_tex, tile_size, seed=0):
    """A tile-sized prop texture for `kind` drawn over `ground_tex`, or None if
    there's no recipe for it (caller keeps its own fallback)."""
    recipe = RECIPES.get(kind)
    if recipe is None or ground_tex is None:
        return None
    base = pygame.Surface((S, S), pygame.SRCALPHA)
    base.blit(pygame.transform.smoothscale(ground_tex, (S, S)), (0, 0))
    layer = pygame.Surface((S, S), pygame.SRCALPHA)
    recipe(layer, random.Random(sum(map(ord, kind)) * 131 + seed))  # stable across runs
    base.blit(layer, (0, 0))
    return pygame.transform.smoothscale(base, (tile_size, tile_size))
