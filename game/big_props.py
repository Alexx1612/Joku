"""
Batch 15 (E1/E5): big multi-tile world assets - real trees that tower over the
player, 2x2 boulders, and the tents/stalls/wells/furnaces/fences the big named
areas are built from. All art here is original, drawn procedurally with pygame
primitives on a 2x canvas and smoothscaled down (same soft-edged look as
game/prop_art.py).

A big prop lives on the tile grid as ONE anchor tile (bottom row, middle column
of its footprint) plus "blocker" tiles for the rest of its footprint - see
world.BIG_PROP_TILE / BIG_BLOCKER_TILE. Only the footprint is solid; a tree's
canopy is sprite-only, drawn over entities by world.TileMap.draw_canopies when a
client hooks it (and faded while the player stands under it).
"""
import math
import random

import pygame

# kind -> (sprite w, h in px, footprint (tiles w, h), trunk_h px (bottom part NOT
#          covered by the canopy overlay), has_canopy, solid)
KINDS = {
    # trees / rocks
    "oak":             ((104, 120), (1, 1), 34, True, True),
    "pine":            ((76, 128), (1, 1), 24, True, True),
    "palm":            ((100, 124), (1, 1), 66, True, True),
    "dead_big":        ((92, 112), (1, 1), 44, True, True),
    "jungle_giant":    ((140, 150), (1, 1), 36, True, True),
    "snow_pine":       ((80, 128), (1, 1), 22, True, True),
    "mushroom_tree":   ((104, 110), (1, 1), 46, True, True),
    "crystal_spire":   ((64, 120), (1, 1), 120, False, True),
    "big_boulder":     ((66, 58), (2, 2), 58, False, True),
    "ice_boulder":     ((66, 58), (2, 2), 58, False, True),
    # area architecture
    "tent":            ((100, 84), (3, 2), 84, False, True),
    "market_stall":    ((100, 88), (3, 2), 88, False, True),
    "well":            ((64, 74), (2, 2), 74, False, True),
    "campfire":        ((40, 44), (1, 1), 44, False, True),
    "cauldron":        ((50, 50), (1, 1), 50, False, True),
    "anvil":           ((44, 38), (1, 1), 38, False, True),
    "furnace":         ((66, 92), (2, 2), 92, False, True),
    "scrap_pile":      ((100, 74), (3, 2), 74, False, True),
    "crystal_cluster": ((72, 82), (2, 2), 82, False, True),
    "shrine":          ((64, 100), (2, 1), 100, False, True),
    "lamp_post":       ((24, 82), (1, 1), 82, False, True),
    "fence":           ((32, 34), (1, 1), 34, False, True),
    "hay_bale":        ((42, 36), (1, 1), 36, False, True),
    "barrels":         ((48, 54), (1, 1), 54, False, True),
    "fishing_rack":    ((66, 66), (2, 1), 66, False, True),
    "bench":           ((64, 36), (2, 1), 36, False, True),
    "bell_tower":      ((64, 144), (2, 2), 144, False, True),
    "cart":            ((82, 62), (2, 1), 62, False, True),
    "signboard":       ((40, 58), (1, 1), 58, False, True),
    "totem_big":       ((40, 112), (1, 1), 112, False, True),
    "statue":          ((58, 112), (2, 2), 112, False, True),
    "flower_planter":  ((64, 42), (2, 1), 42, False, True),
    "boat":            ((98, 58), (3, 1), 58, False, True),
    "banner":          ((32, 98), (1, 1), 98, False, True),
}
TREE_KINDS = {k for k, v in KINDS.items() if v[3]}


def footprint(kind):
    return KINDS[kind][1]


def footprint_tiles(kind, anchor):
    """Tiles a big prop occupies - the anchor is the bottom row's middle column."""
    fw, fh = KINDS[kind][1]
    ax, ay = anchor
    x0 = ax - (fw - 1) // 2
    return [(x, y) for y in range(ay - fh + 1, ay + 1) for x in range(x0, x0 + fw)]


def footprint_center_x_tiles(kind, anchor_x):
    """Footprint centre (in tiles, fractional) - the sprite is centred on it."""
    fw = KINDS[kind][1][0]
    return anchor_x - (fw - 1) // 2 + fw / 2.0


# ------------------------------------------------------------------ painting

def _sh(c, d):
    return tuple(max(0, min(255, v + d)) for v in c)


def _shadow(L, cx, cy, rx, ry, a=80):
    pygame.draw.ellipse(L, (0, 0, 0, a), (cx - rx, cy - ry, rx * 2, ry * 2))


def _blob_canopy(L, r, cx, cy, rx, ry, base, n=14, lumps=(0.35, 0.55)):
    """Leafy canopy: many overlapping lumps, dark underside, bright rim on top."""
    pts = []
    for _ in range(n):
        a = r.uniform(0, math.tau)
        d = r.uniform(0.0, 0.62)
        pts.append((cx + math.cos(a) * rx * d, cy + math.sin(a) * ry * d, r.uniform(*lumps)))
    for x, y, s in sorted(pts, key=lambda p: p[1]):
        rad = int(min(rx, ry) * s)
        pygame.draw.circle(L, _sh(base, -34), (int(x), int(y + rad * 0.25)), rad)
    for x, y, s in sorted(pts, key=lambda p: p[1]):
        rad = int(min(rx, ry) * s)
        pygame.draw.circle(L, base, (int(x), int(y)), rad)
        pygame.draw.circle(L, _sh(base, 26), (int(x - rad * 0.28), int(y - rad * 0.3)), max(2, int(rad * 0.45)))
    for _ in range(n * 2):
        a = r.uniform(0, math.tau)
        d = r.uniform(0.2, 0.9)
        pygame.draw.circle(L, _sh(base, r.choice((-40, 40, 55))),
                           (int(cx + math.cos(a) * rx * d * 0.8), int(cy + math.sin(a) * ry * d * 0.8)), 2)


def _trunk(L, x, y_top, y_bot, w, col):
    pygame.draw.polygon(L, col, [(x - w // 2 - 3, y_bot), (x + w // 2 + 3, y_bot), (x + w // 2, y_top), (x - w // 2, y_top)])
    pygame.draw.line(L, _sh(col, 28), (x - w // 4, y_bot - 2), (x - w // 4, y_top + 2), 2)
    pygame.draw.line(L, _sh(col, -30), (x + w // 3, y_bot - 2), (x + w // 3, y_top + 2), 2)
    for rx in (-w // 2 - 6, w // 2 + 6):   # root flare
        pygame.draw.line(L, col, (x, y_bot - 4), (x + rx, y_bot), 4)


def _p_oak(L, W, H, r):
    _shadow(L, W // 2, H - 10, W * 0.34, 12)
    _trunk(L, W // 2, H - 90, H - 8, 18, (96, 66, 42))
    _blob_canopy(L, r, W // 2, H * 0.40, W * 0.47, H * 0.34, (58, 122, 52), n=18)


def _p_pine(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.32, 10)
    _trunk(L, W // 2, H - 60, H - 6, 12, (92, 62, 40))
    base = (40, 100, 62)
    for i, (w, y) in enumerate(((0.95, 0.86), (0.78, 0.66), (0.60, 0.46), (0.40, 0.26))):
        top, bot = H * (y - 0.26), H * y
        c = _sh(base, i * 8)
        pygame.draw.polygon(L, _sh(c, -30), [(W // 2, top + 4), (W // 2 - W * w / 2, bot + 4), (W // 2 + W * w / 2, bot + 4)])
        pygame.draw.polygon(L, c, [(W // 2, top), (W // 2 - W * w / 2, bot), (W // 2 + W * w / 2, bot)])
        pygame.draw.line(L, _sh(c, 34), (W // 2, top + 3), (W // 2 - W * w / 3, bot - 3), 2)


def _p_snow_pine(L, W, H, r):
    _p_pine(L, W, H, r)
    for i, (w, y) in enumerate(((0.95, 0.86), (0.78, 0.66), (0.60, 0.46), (0.40, 0.26))):
        top, bot = H * (y - 0.26), H * y
        pygame.draw.polygon(L, (236, 244, 250), [(W // 2, top), (W // 2 - W * w / 5, top + (bot - top) * 0.45),
                                                  (W // 2 + W * w / 6, top + (bot - top) * 0.40)])
        for _ in range(5):
            x = W // 2 + r.uniform(-W * w / 2.4, W * w / 2.4)
            pygame.draw.circle(L, (240, 246, 252), (int(x), int(bot - 3)), 3)


def _p_palm(L, W, H, r):
    _shadow(L, W // 2 + 8, H - 8, W * 0.30, 9)
    bark = (150, 112, 70)
    pts = [(W // 2 + math.sin(t / 10) * 10 + t * 0.12, H - 8 - t * (H - 40) / 60) for t in range(61)]
    for i, (x, y) in enumerate(pts):
        pygame.draw.circle(L, _sh(bark, -18 if i % 6 < 3 else 6), (int(x), int(y)), 7)
    cx, cy = pts[-1]
    for a in range(0, 360, 40):
        ang = math.radians(a + r.uniform(-8, 8))
        ex, ey = cx + math.cos(ang) * W * 0.46, cy + math.sin(ang) * H * 0.22 + 14
        mx, my = (cx + ex) / 2, (cy + ey) / 2 - 12
        pygame.draw.lines(L, (46, 120, 50), False, [(cx, cy), (mx, my), (ex, ey)], 9)
        pygame.draw.lines(L, (86, 164, 74), False, [(cx, cy - 2), (mx, my - 3), (ex, ey - 2)], 3)
    for dx in (-6, 5, 0):
        pygame.draw.circle(L, (110, 74, 40), (int(cx + dx), int(cy + 8)), 6)


def _p_dead_big(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.30, 9)
    bark = (88, 70, 56)
    _trunk(L, W // 2, H - 80, H - 6, 16, bark)

    def branch(x, y, ang, ln, w):
        if ln < 10 or w < 1:
            return
        ex, ey = x + math.cos(ang) * ln, y + math.sin(ang) * ln
        pygame.draw.line(L, bark, (x, y), (ex, ey), w)
        branch(ex, ey, ang - r.uniform(0.25, 0.6), ln * 0.66, w - 2)
        branch(ex, ey, ang + r.uniform(0.25, 0.6), ln * 0.62, w - 2)
    branch(W // 2, H - 76, -math.pi / 2, H * 0.30, 8)


def _p_jungle_giant(L, W, H, r):
    _shadow(L, W // 2, H - 10, W * 0.38, 13)
    _trunk(L, W // 2, H - 96, H - 8, 26, (88, 70, 44))
    for dx in (-30, 30):  # buttress roots
        pygame.draw.polygon(L, (78, 60, 38), [(W // 2 + dx, H - 6), (W // 2, H - 60), (W // 2 + dx // 3, H - 6)])
    _blob_canopy(L, r, W // 2, H * 0.36, W * 0.49, H * 0.32, (34, 110, 50), n=22)
    for _ in range(9):  # hanging vines
        x = W // 2 + r.uniform(-W * 0.38, W * 0.38)
        y = H * 0.5 + r.uniform(-10, 10)
        pygame.draw.line(L, (60, 140, 60), (x, y), (x + r.uniform(-3, 3), y + r.uniform(18, 36)), 2)


def _p_mushroom_tree(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.30, 9)
    stalk = (220, 210, 186)
    pygame.draw.polygon(L, stalk, [(W // 2 - 12, H - 6), (W // 2 + 12, H - 6), (W // 2 + 8, H - 90), (W // 2 - 8, H - 90)])
    pygame.draw.line(L, (190, 180, 160), (W // 2 + 5, H - 8), (W // 2 + 4, H - 88), 2)
    cap = (170, 72, 150)
    pygame.draw.ellipse(L, _sh(cap, -40), (4, H * 0.18, W - 8, H * 0.36))
    pygame.draw.ellipse(L, cap, (6, H * 0.10, W - 12, H * 0.34))
    pygame.draw.ellipse(L, _sh(cap, 30), (W * 0.2, H * 0.12, W * 0.45, H * 0.14))
    for _ in range(9):
        pygame.draw.circle(L, (250, 236, 220), (int(r.uniform(W * 0.18, W * 0.82)), int(r.uniform(H * 0.14, H * 0.34))), 4)


def _p_crystal_spire(L, W, H, r):
    _shadow(L, W // 2, H - 6, W * 0.40, 8)
    for dx, h, c in ((-14, 0.55, (120, 170, 230)), (14, 0.62, (150, 120, 230)), (0, 0.95, (160, 210, 250))):
        x = W // 2 + dx
        top = H - H * h
        pygame.draw.polygon(L, c, [(x, top), (x - 11, H - 30), (x - 7, H - 6), (x + 7, H - 6), (x + 11, H - 30)])
        pygame.draw.polygon(L, _sh(c, 50), [(x, top + 4), (x - 5, H - 34), (x, H - 12)])
        pygame.draw.line(L, (240, 250, 255), (x - 2, top + 10), (x - 5, H - 36), 1)


def _p_boulder(L, W, H, r, col=(128, 124, 118)):
    _shadow(L, W // 2, H - 10, W * 0.46, 10)
    pts = [(W * 0.08, H * 0.80), (W * 0.14, H * 0.38), (W * 0.40, H * 0.14), (W * 0.72, H * 0.20),
           (W * 0.94, H * 0.52), (W * 0.86, H * 0.88), (W * 0.30, H * 0.94)]
    pygame.draw.polygon(L, _sh(col, -30), [(x, y + 4) for x, y in pts])
    pygame.draw.polygon(L, col, pts)
    pygame.draw.polygon(L, _sh(col, 34), [(W * 0.22, H * 0.40), (W * 0.42, H * 0.20), (W * 0.62, H * 0.30), (W * 0.40, H * 0.46)])
    pygame.draw.line(L, _sh(col, -45), (W * 0.52, H * 0.40), (W * 0.62, H * 0.76), 2)


def _p_ice_boulder(L, W, H, r):
    _p_boulder(L, W, H, r, col=(170, 210, 232))


def _p_tent(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.48, 10)
    cloth = r.choice([(178, 70, 60), (70, 110, 170), (190, 150, 70), (90, 140, 80)])
    pygame.draw.polygon(L, _sh(cloth, -40), [(W // 2, 8), (W - 4, H - 8), (4, H - 8)])
    pygame.draw.polygon(L, cloth, [(W // 2, 8), (W * 0.78, H - 8), (W * 0.22, H - 8)])
    for i in range(1, 4):
        pygame.draw.line(L, _sh(cloth, 30), (W // 2, 8), (W * (0.22 + 0.14 * i), H - 8), 2)
    pygame.draw.polygon(L, (40, 30, 26), [(W // 2, H * 0.42), (W * 0.60, H - 8), (W * 0.40, H - 8)])
    pygame.draw.line(L, (110, 80, 50), (W // 2, 2), (W // 2, 14), 3)
    pygame.draw.polygon(L, (230, 200, 90), [(W // 2, 2), (W // 2 + 12, 6), (W // 2, 10)])


def _p_market_stall(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.48, 9)
    wood = (120, 84, 52)
    for x in (10, W - 14):
        pygame.draw.rect(L, wood, (x, H * 0.30, 6, H * 0.66))
    pygame.draw.rect(L, _sh(wood, 20), (6, H * 0.62, W - 12, H * 0.30))
    pygame.draw.rect(L, _sh(wood, -25), (6, H * 0.86, W - 12, 6))
    c1, c2 = r.choice([((200, 60, 60), (240, 230, 210)), ((60, 130, 190), (240, 230, 210)), ((70, 150, 80), (240, 220, 120))])
    for i in range(6):
        pygame.draw.polygon(L, c1 if i % 2 == 0 else c2, [(4 + i * (W - 8) / 6, 8), (4 + (i + 1) * (W - 8) / 6, 8),
                                                           (4 + (i + 1) * (W - 8) / 6, H * 0.34), (4 + i * (W - 8) / 6, H * 0.34)])
    for i in range(7):  # goods on the counter
        pygame.draw.circle(L, r.choice([(230, 180, 60), (200, 70, 70), (120, 200, 90), (240, 240, 220)]),
                           (int(16 + i * (W - 32) / 6), int(H * 0.60)), 5)


def _p_well(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.46, 9)
    stone = (140, 134, 124)
    pygame.draw.ellipse(L, _sh(stone, -30), (4, H * 0.50, W - 8, H * 0.46))
    pygame.draw.ellipse(L, stone, (4, H * 0.44, W - 8, H * 0.42))
    pygame.draw.ellipse(L, (40, 70, 110), (14, H * 0.50, W - 28, H * 0.26))
    wood = (110, 76, 46)
    for x in (8, W - 14):
        pygame.draw.rect(L, wood, (x, 12, 6, H * 0.50))
    pygame.draw.polygon(L, (150, 70, 50), [(0, 18), (W // 2, 2), (W, 18), (W - 6, 24), (6, 24)])
    pygame.draw.line(L, (70, 50, 30), (W // 2, 22), (W // 2, H * 0.52), 2)


def _p_campfire(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.44, 7)
    for a in range(0, 360, 60):
        ang = math.radians(a)
        pygame.draw.circle(L, (120, 116, 108), (int(W / 2 + math.cos(ang) * 15), int(H - 14 + math.sin(ang) * 6)), 5)
    pygame.draw.line(L, (100, 66, 40), (W * 0.2, H - 12), (W * 0.8, H - 18), 5)
    pygame.draw.line(L, (90, 60, 38), (W * 0.2, H - 18), (W * 0.8, H - 12), 5)
    pygame.draw.polygon(L, (240, 120, 40), [(W / 2, H * 0.18), (W * 0.72, H - 18), (W * 0.28, H - 18)])
    pygame.draw.polygon(L, (255, 210, 90), [(W / 2, H * 0.40), (W * 0.62, H - 18), (W * 0.38, H - 18)])


def _p_cauldron(L, W, H, r):
    _shadow(L, W // 2, H - 6, W * 0.44, 7)
    pygame.draw.ellipse(L, (40, 40, 46), (6, H * 0.30, W - 12, H * 0.62))
    pygame.draw.ellipse(L, (70, 70, 80), (6, H * 0.26, W - 12, H * 0.20))
    pygame.draw.ellipse(L, (90, 200, 90), (12, H * 0.28, W - 24, H * 0.14))
    for _ in range(4):
        pygame.draw.circle(L, (170, 250, 150), (int(r.uniform(16, W - 16)), int(r.uniform(4, H * 0.28))), 4, 1)


def _p_anvil(L, W, H, r):
    _shadow(L, W // 2, H - 6, W * 0.44, 6)
    iron = (80, 82, 92)
    pygame.draw.rect(L, (90, 70, 50), (W * 0.30, H * 0.56, W * 0.40, H * 0.40))
    pygame.draw.polygon(L, iron, [(2, H * 0.24), (W - 2, H * 0.24), (W * 0.74, H * 0.56), (W * 0.26, H * 0.56)])
    pygame.draw.line(L, _sh(iron, 60), (6, H * 0.26), (W - 6, H * 0.26), 2)


def _p_furnace(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.46, 8)
    brick = (120, 60, 44)
    pygame.draw.rect(L, brick, (6, H * 0.28, W - 12, H * 0.66))
    for y in range(int(H * 0.30), H - 8, 10):
        pygame.draw.line(L, _sh(brick, -40), (6, y), (W - 6, y), 1)
    pygame.draw.rect(L, (80, 40, 30), (W * 0.34, 2, W * 0.32, H * 0.30))
    pygame.draw.ellipse(L, (255, 140, 40), (W * 0.24, H * 0.58, W * 0.52, H * 0.30))
    pygame.draw.ellipse(L, (255, 220, 110), (W * 0.34, H * 0.66, W * 0.32, H * 0.16))


def _p_scrap_pile(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.48, 10)
    for _ in range(22):
        x, y = r.uniform(8, W - 8), r.uniform(H * 0.30, H - 10)
        w, h = r.uniform(10, 26), r.uniform(6, 16)
        c = r.choice([(120, 110, 96), (150, 90, 60), (90, 96, 104), (170, 150, 110)])
        pygame.draw.polygon(L, c, [(x, y), (x + w, y + r.uniform(-4, 4)), (x + w * 0.8, y + h), (x - w * 0.1, y + h * 0.9)])
    pygame.draw.circle(L, (70, 70, 76), (int(W * 0.66), int(H * 0.40)), 13, 4)  # an old gear
    pygame.draw.line(L, (140, 130, 120), (W * 0.2, H * 0.2), (W * 0.36, H * 0.62), 3)


def _p_crystal_cluster(L, W, H, r):
    _shadow(L, W // 2, H - 6, W * 0.46, 8)
    for i in range(6):
        x = W * (0.18 + 0.13 * i) + r.uniform(-4, 4)
        h = H * r.uniform(0.35, 0.9)
        c = r.choice([(140, 200, 250), (180, 140, 250), (120, 230, 220)])
        pygame.draw.polygon(L, c, [(x, H - h), (x - 8, H - 12), (x + 8, H - 12)])
        pygame.draw.line(L, _sh(c, 60), (x - 1, H - h + 6), (x - 4, H - 16), 2)


def _p_shrine(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.46, 8)
    stone = (150, 146, 136)
    pygame.draw.rect(L, _sh(stone, -20), (4, H * 0.80, W - 8, H * 0.16))
    pygame.draw.rect(L, stone, (W * 0.30, H * 0.24, W * 0.40, H * 0.58))
    pygame.draw.polygon(L, (180, 90, 60), [(W * 0.14, H * 0.26), (W / 2, H * 0.04), (W * 0.86, H * 0.26)])
    pygame.draw.circle(L, (250, 220, 120), (W // 2, int(H * 0.46)), 7)


def _p_lamp_post(L, W, H, r):
    _shadow(L, W // 2, H - 5, W * 0.6, 5)
    pygame.draw.rect(L, (50, 46, 44), (W // 2 - 3, H * 0.20, 6, H * 0.78))
    pygame.draw.rect(L, (40, 36, 34), (W // 2 - 8, H * 0.14, 16, 16))
    pygame.draw.rect(L, (255, 220, 120), (W // 2 - 5, H * 0.16, 10, 11))


def _p_fence(L, W, H, r):
    wood = (130, 94, 58)
    for x in (4, W - 8):
        pygame.draw.rect(L, wood, (x, 6, 5, H - 8))
        pygame.draw.rect(L, _sh(wood, 30), (x, 6, 2, H - 8))
    for y in (H * 0.34, H * 0.66):
        pygame.draw.rect(L, _sh(wood, -12), (0, y, W, 5))


def _p_hay_bale(L, W, H, r):
    _shadow(L, W // 2, H - 5, W * 0.46, 5)
    pygame.draw.rect(L, (214, 184, 90), (3, H * 0.20, W - 6, H * 0.74), border_radius=5)
    for i in range(6):
        pygame.draw.line(L, (180, 150, 70), (6, H * 0.28 + i * 5), (W - 6, H * 0.30 + i * 5), 1)
    pygame.draw.line(L, (120, 90, 50), (W * 0.35, H * 0.20), (W * 0.35, H * 0.94), 2)


def _p_barrels(L, W, H, r):
    _shadow(L, W // 2, H - 5, W * 0.46, 5)
    for x, y in ((6, H * 0.34), (W * 0.46, H * 0.36), (W * 0.26, H * 0.05)):
        pygame.draw.rect(L, (130, 88, 50), (x, y, W * 0.48, H * 0.58), border_radius=6)
        pygame.draw.line(L, (70, 60, 56), (x, y + H * 0.14), (x + W * 0.48, y + H * 0.14), 2)
        pygame.draw.line(L, (70, 60, 56), (x, y + H * 0.44), (x + W * 0.48, y + H * 0.44), 2)


def _p_fishing_rack(L, W, H, r):
    _shadow(L, W // 2, H - 5, W * 0.46, 5)
    wood = (120, 86, 52)
    for x in (6, W - 10):
        pygame.draw.rect(L, wood, (x, 8, 5, H - 10))
    pygame.draw.rect(L, wood, (4, 10, W - 8, 4))
    for i in range(4):
        x = 14 + i * (W - 28) / 3
        pygame.draw.line(L, (90, 90, 90), (x, 14), (x, 24), 1)
        pygame.draw.ellipse(L, (150, 170, 190), (x - 5, 24, 10, 20))


def _p_bench(L, W, H, r):
    _shadow(L, W // 2, H - 4, W * 0.46, 4)
    wood = (140, 100, 62)
    pygame.draw.rect(L, wood, (2, H * 0.30, W - 4, 8))
    pygame.draw.rect(L, _sh(wood, -20), (2, H * 0.06, W - 4, 6))
    for x in (6, W - 12):
        pygame.draw.rect(L, _sh(wood, -40), (x, H * 0.30, 6, H * 0.64))


def _p_bell_tower(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.46, 8)
    stone = (156, 150, 138)
    pygame.draw.rect(L, stone, (8, H * 0.20, W - 16, H * 0.78))
    pygame.draw.rect(L, (40, 36, 34), (W * 0.30, H * 0.30, W * 0.40, H * 0.20))
    pygame.draw.ellipse(L, (220, 180, 80), (W * 0.36, H * 0.33, W * 0.28, H * 0.14))
    pygame.draw.polygon(L, (120, 60, 50), [(2, H * 0.22), (W / 2, 2), (W - 2, H * 0.22)])
    pygame.draw.rect(L, (60, 50, 44), (W * 0.40, H * 0.80, W * 0.20, H * 0.18))


def _p_cart(L, W, H, r):
    _shadow(L, W // 2, H - 5, W * 0.46, 6)
    wood = (130, 90, 54)
    pygame.draw.rect(L, wood, (6, H * 0.22, W * 0.76, H * 0.44))
    pygame.draw.line(L, _sh(wood, -40), (W * 0.82, H * 0.50), (W - 2, H * 0.36), 4)
    for x in (W * 0.22, W * 0.62):
        pygame.draw.circle(L, (70, 50, 34), (int(x), int(H * 0.74)), 11)
        pygame.draw.circle(L, (150, 120, 80), (int(x), int(H * 0.74)), 4)
    for _ in range(5):
        pygame.draw.circle(L, r.choice([(214, 184, 90), (200, 80, 70), (120, 180, 80)]),
                           (int(r.uniform(14, W * 0.74)), int(H * 0.22)), 6)


def _p_signboard(L, W, H, r):
    _shadow(L, W // 2, H - 4, W * 0.5, 4)
    pygame.draw.rect(L, (100, 72, 44), (W // 2 - 3, H * 0.40, 6, H * 0.58))
    pygame.draw.rect(L, (150, 110, 66), (2, 4, W - 4, H * 0.42), border_radius=3)
    for i in range(3):
        pygame.draw.line(L, (70, 50, 30), (8, 12 + i * 7), (W - 8 - r.randint(0, 10), 12 + i * 7), 2)


def _p_totem_big(L, W, H, r):
    _shadow(L, W // 2, H - 5, W * 0.5, 5)
    cols = [(160, 70, 60), (70, 120, 160), (190, 160, 70), (90, 140, 80)]
    seg = (H - 10) / 4
    for i in range(4):
        y = 4 + i * seg
        c = cols[i]
        pygame.draw.rect(L, c, (6, y, W - 12, seg - 2), border_radius=4)
        pygame.draw.circle(L, (250, 240, 220), (W // 2 - 6, int(y + seg * 0.35)), 3)
        pygame.draw.circle(L, (250, 240, 220), (W // 2 + 6, int(y + seg * 0.35)), 3)
        pygame.draw.line(L, _sh(c, -60), (W // 2 - 6, y + seg * 0.7), (W // 2 + 6, y + seg * 0.7), 2)


def _p_statue(L, W, H, r):
    _shadow(L, W // 2, H - 8, W * 0.46, 7)
    stone = (170, 166, 156)
    pygame.draw.rect(L, _sh(stone, -30), (4, H * 0.82, W - 8, H * 0.16))
    pygame.draw.polygon(L, stone, [(W * 0.30, H * 0.82), (W * 0.70, H * 0.82), (W * 0.62, H * 0.30), (W * 0.38, H * 0.30)])
    pygame.draw.circle(L, stone, (W // 2, int(H * 0.22)), int(W * 0.14))
    pygame.draw.line(L, _sh(stone, -40), (W * 0.62, H * 0.36), (W * 0.84, H * 0.14), 4)  # raised mug arm
    pygame.draw.rect(L, _sh(stone, 20), (W * 0.80, H * 0.06, 10, 12))


def _p_flower_planter(L, W, H, r):
    _shadow(L, W // 2, H - 4, W * 0.46, 4)
    pygame.draw.rect(L, (120, 80, 50), (2, H * 0.48, W - 4, H * 0.48), border_radius=3)
    for _ in range(14):
        x, y = r.uniform(8, W - 8), r.uniform(6, H * 0.50)
        pygame.draw.circle(L, (60, 130, 60), (int(x), int(y + 6)), 4)
        pygame.draw.circle(L, r.choice([(240, 120, 150), (250, 220, 90), (170, 130, 240), (245, 245, 245)]),
                           (int(x), int(y)), 3)


def _p_boat(L, W, H, r):
    _shadow(L, W // 2, H - 6, W * 0.48, 6)
    wood = (120, 80, 48)
    pygame.draw.polygon(L, wood, [(2, H * 0.36), (W - 2, H * 0.36), (W * 0.84, H * 0.88), (W * 0.16, H * 0.88)])
    pygame.draw.polygon(L, _sh(wood, 30), [(6, H * 0.36), (W - 6, H * 0.36), (W - 10, H * 0.48), (10, H * 0.48)])
    pygame.draw.line(L, (90, 60, 36), (W / 2, H * 0.36), (W / 2, 2), 3)
    pygame.draw.polygon(L, (230, 224, 206), [(W / 2 + 2, 4), (W * 0.80, H * 0.30), (W / 2 + 2, H * 0.30)])


def _p_banner(L, W, H, r):
    _shadow(L, W // 2, H - 4, W * 0.6, 4)
    pygame.draw.rect(L, (90, 66, 42), (W // 2 - 2, 2, 4, H - 4))
    c = r.choice([(170, 50, 60), (60, 90, 170), (200, 160, 60), (60, 140, 90)])
    pygame.draw.polygon(L, c, [(W // 2 + 2, 6), (W - 2, 6), (W - 2, H * 0.52), (W * 0.78, H * 0.44), (W // 2 + 2, H * 0.52)])
    pygame.draw.circle(L, (240, 220, 140), (int(W * 0.76), int(H * 0.24)), 4)


_PAINTERS = {
    "oak": _p_oak, "pine": _p_pine, "palm": _p_palm, "dead_big": _p_dead_big, "jungle_giant": _p_jungle_giant,
    "snow_pine": _p_snow_pine, "mushroom_tree": _p_mushroom_tree, "crystal_spire": _p_crystal_spire,
    "big_boulder": _p_boulder, "ice_boulder": _p_ice_boulder, "tent": _p_tent, "market_stall": _p_market_stall,
    "well": _p_well, "campfire": _p_campfire, "cauldron": _p_cauldron, "anvil": _p_anvil, "furnace": _p_furnace,
    "scrap_pile": _p_scrap_pile, "crystal_cluster": _p_crystal_cluster, "shrine": _p_shrine,
    "lamp_post": _p_lamp_post, "fence": _p_fence, "hay_bale": _p_hay_bale, "barrels": _p_barrels,
    "fishing_rack": _p_fishing_rack, "bench": _p_bench, "bell_tower": _p_bell_tower, "cart": _p_cart,
    "signboard": _p_signboard, "totem_big": _p_totem_big, "statue": _p_statue,
    "flower_planter": _p_flower_planter, "boat": _p_boat, "banner": _p_banner,
}
assert set(_PAINTERS) == set(KINDS)

_cache = {}


def sprite(kind, variant=0):
    """The big prop's sprite at its KINDS size (a few seeded variants per kind so a
    forest isn't a row of identical clones)."""
    key = (kind, variant % 3)
    if key not in _cache:
        (w, h), _fp, _th, _canopy, _solid = KINDS[kind]
        layer = pygame.Surface((w * 2, h * 2), pygame.SRCALPHA)
        _PAINTERS[kind](layer, w * 2, h * 2, random.Random(sum(map(ord, kind)) * 977 + key[1] * 31))
        _cache[key] = pygame.transform.smoothscale(layer, (w, h))
    return _cache[key]


def canopy_part(kind, variant=0):
    """The sprite with its bottom trunk_h rows cut away (drawn over entities)."""
    key = ("canopy", kind, variant % 3)
    if key not in _cache:
        img = sprite(kind, variant)
        th = KINDS[kind][2]
        _cache[key] = img.subsurface((0, 0, img.get_width(), max(1, img.get_height() - th))).copy()
    return _cache[key]


def trunk_part(kind, variant=0):
    key = ("trunk", kind, variant % 3)
    if key not in _cache:
        img = sprite(kind, variant)
        th = min(KINDS[kind][2], img.get_height())
        _cache[key] = img.subsurface((0, img.get_height() - th, img.get_width(), th)).copy()
    return _cache[key]
