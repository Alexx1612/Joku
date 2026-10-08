"""
Paints the CHOIR islands' monsters (the drowned temple: coral, pearl, kelp, tideglass, song) that
still used coarse procedural grids - 10 mobs and their 5 mini-bosses: a still PNG, a 4-frame move
strip, a 3-frame attack strip, and (for the bioluminescent ones) an emissive glow layer each.
Wholly original.

It reuses the part-based painter of tools/paint_night_sprites.py (shapes -> per-part dome
lighting, key light top-left + a cold rim, 5-step ramps with Bayer dithering, selective
outlines). Mobs: 64x64 logical, saved at 2x. Mini-bosses: 160x104 logical, saved at 2x.

Run: python tools/paint_choir_island_sprites.py [kind ...]   (writes assets/sprites/v0.2/enemies/)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

import paint_night_sprites as pn  # noqa: E402
from paint_night_sprites import P, ramp, render, soft_glow, strip  # noqa: E402

OUT = pn.OUT
UP = 2

# ------------------------------------------------------------- materials (sea, pearl, coral, kelp, abyss)
SEA = ramp((8, 36, 46), (130, 220, 226))
SEA_D = ramp((4, 20, 26), (60, 128, 138))
FOAM = ramp((90, 150, 160), (240, 254, 255))
PEARL = ramp((110, 108, 120), (255, 252, 246))
CORAL = ramp((84, 26, 38), (255, 176, 162), warm_shadow=(70, 10, 50))
CORAL_D = ramp((50, 16, 24), (176, 92, 92))
CORAL_TIP = ramp((150, 60, 70), (255, 214, 196))
KELP = ramp((6, 30, 20), (120, 196, 120))
KELP_D = ramp((4, 18, 12), (56, 112, 72))
SHELL = ramp((36, 56, 62), (206, 228, 226))
SHELL_D = ramp((22, 36, 40), (120, 150, 154))
VERD = ramp((16, 36, 40), (138, 196, 184))              # verdigris temple bronze
VERD_D = ramp((10, 22, 26), (74, 112, 110))
ROBE_TEAL = ramp((12, 30, 36), (112, 166, 174))
ROBE_DARK = ramp((6, 14, 20), (54, 92, 104))
ROBE_PALE = ramp((70, 100, 108), (238, 250, 252))
ABYSS = ramp((14, 6, 26), (156, 112, 206))
ABYSS_D = ramp((8, 4, 16), (88, 56, 124))
GLASS = ramp((18, 58, 78), (226, 252, 255))
GLASS_D = ramp((10, 34, 50), (110, 190, 210))
JELLY = ramp((40, 74, 96), (236, 248, 252))
BONEP = ramp((96, 92, 84), (246, 240, 226))
GOLDSONG = ramp((150, 112, 40), (255, 250, 214))
EYE_DARK = [(8, 20, 26)] * 5
WATER_RIM = (196, 252, 255)
CORAL_RIM = (255, 220, 210)
SONG = (150, 242, 240)


def _spine(pts_fn, n, half_fn):
    """A tapering ribbon polygon along a curve: pts_fn(u)->(x, y), half_fn(u)->half width."""
    left, right = [], []
    for k in range(n + 1):
        u = k / n
        x, y = pts_fn(u)
        x2, y2 = pts_fn(min(1.0, u + 1.0 / n)) if u < 1 else pts_fn(u - 1.0 / n)
        dx, dy = x2 - x, y2 - y
        if u >= 1:
            dx, dy = -dx, -dy
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        hw = half_fn(u)
        left.append((x + nx * hw, y + ny * hw))
        right.append((x - nx * hw, y - ny * hw))
    return left + list(reversed(right))


def poly(pts):
    return lambda s, c: pygame.draw.polygon(s, c, [(int(round(x)), int(round(y))) for x, y in pts])


def ell(x, y, w, h):
    return lambda s, c: pygame.draw.ellipse(s, c, (int(round(x)), int(round(y)), max(1, int(round(w))),
                                                   max(1, int(round(h)))))


def circ(x, y, r):
    return lambda s, c: pygame.draw.circle(s, c, (int(round(x)), int(round(y))), max(1, int(round(r))))


def many(*fns):
    return lambda s, c: [f(s, c) for f in fns]


def lines(pts, w):
    return lambda s, c: pygame.draw.lines(s, c, False, [(int(round(x)), int(round(y))) for x, y in pts], w)


def glow_dot(x, y, r, col):
    return P(64, 64, circ(x, y, r), [col] * 5, z=20, flat=True, emit=col)


# ============================================================ 64x64 mobs
def tide_wisp(t, attack):
    """A drifting water spirit: a glassy teal droplet-head with a swirling bright core, a curling
    tail of water, and droplets orbiting it. On attack it flares and flings the droplets out."""
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 2
    flare = (1.0 + 0.25 * t) if attack else 1.0
    parts = []
    tail = _spine(lambda u: (32 + math.sin(ph + u * 4.0) * u * 7, 30 + bob + u * 30), 12,
                  lambda u: 11 * (1 - u) ** 1.1 + 0.5)
    parts.append(P(W, H, poly(tail), SEA, z=1, rim=WATER_RIM, height=4, alpha=225, noise=0.04))
    rx, ry = 16 * flare, 14 * flare
    parts.append(P(W, H, ell(32 - rx, 23 + bob - ry, rx * 2, ry * 2), SEA, z=2, rim=WATER_RIM, height=8,
                   alpha=235, dome=0.5, seed=11))
    # the swirling core (emissive)
    sw = [(32 + math.cos(ph + a * 0.5) * (2 + a * 0.9), 21 + bob + math.sin(ph + a * 0.5) * (1.5 + a * 0.6))
          for a in range(14)]
    parts.append(P(W, H, ell(22, 12 + bob, 18, 13), FOAM, z=3, height=5, dome=0.6, emit=(150, 236, 250),
                   alpha=230))
    parts.append(P(W, H, lines(sw, 1), [(240, 255, 255)] * 5, z=3.5, flat=True, emit=(210, 255, 255)))
    # eyes (bigger and angry on attack)
    ey = 25 + bob
    eh = 3 if attack else 5
    parts.append(P(W, H, many(ell(24, ey, 4, eh), ell(36, ey, 4, eh)), EYE_DARK, z=4, flat=True))
    if attack:
        parts.append(P(W, H, ell(28, 31 + bob, 8, 5 + 3 * t), EYE_DARK, z=4, flat=True))
    # orbiting droplets
    for k in range(4):
        a = ph * (1 if not attack else 0) + k * math.tau / 4
        rr = 22 + (10 * t if attack else 0)
        x, y = 32 + math.cos(a) * rr, 24 + bob + math.sin(a) * rr * 0.55
        parts.append(P(W, H, many(circ(x, y, 2.2), poly([(x - 1.5, y), (x + 1.5, y), (x, y - 4)])), FOAM, z=5,
                       height=1.5, emit=(170, 240, 255)))
    return parts


def pearl_acolyte(t, attack):
    """A hooded temple acolyte in sea-grey robes, a pearl string across the chest, cradling a
    glowing pearl; on attack the pearl lifts and blazes."""
    W = H = 64
    ph = t * math.tau
    sway = math.sin(ph) * 1.5
    parts = []
    hem = [(12 + k * 5, 60 + math.sin(ph + k) * 1.5 * (k % 2)) for k in range(9)]
    robe = [(22, 24), (42, 24), (48, 40), (53, 60)] + list(reversed(hem)) + [(11, 60), (16, 40)]
    parts.append(P(W, H, poly(robe), ROBE_TEAL, z=1, rim=WATER_RIM, height=9, noise=0.07, seed=12))
    parts.append(P(W, H, many(*[lines([(26 + k * 4, 30), (23 + k * 5 + sway * 0.3, 59)], 1) for k in range(4)]),
                   ROBE_DARK, z=1.2, flat=True))                                       # folds
    parts.append(P(W, H, poly([(28, 26), (36, 26), (38, 60), (26, 60)]), ROBE_DARK, z=1.4, height=3, noise=0.06))
    parts.append(P(W, H, many(*[circ(32 + (k % 2) * 0.6, 46 + k * 3.4, 1.3) for k in range(4)]), PEARL, z=1.5, height=1,
                   emit=(190, 186, 176)))
    # sleeves meeting in front, hands cradling the pearl
    lift = (8 * t) if attack else 0
    parts.append(P(W, H, many(poly([(18, 30), (26, 31), (30, 42 - lift * 0.5), (22, 44 - lift * 0.4)]),
                              poly([(46, 30), (38, 31), (34, 42 - lift * 0.5), (42, 44 - lift * 0.4)])),
                   ROBE_TEAL, z=3, rim=WATER_RIM, height=3, noise=0.06))
    parts.append(P(W, H, many(circ(28, 42 - lift * 0.5, 2.5), circ(36, 42 - lift * 0.5, 2.5)), BONEP, z=3.5, height=1.5))
    # pearl string
    beads = [circ(32 + math.cos(a) * 11, 28 + math.sin(a) * 6, 1.5) for a in [0.25 + k * 0.33 for k in range(9)]]
    parts.append(P(W, H, many(*beads), PEARL, z=4.8, height=1.2, emit=(200, 196, 186)))
    # the hood
    parts.append(P(W, H, ell(19 + sway * 0.3, 4, 26, 26), ROBE_TEAL, z=4, rim=WATER_RIM, height=7, noise=0.06, seed=13))
    parts.append(P(W, H, ell(24 + sway * 0.3, 10, 16, 15), [(6, 14, 18)] * 5, z=4.5, flat=True))
    ex = 28 + sway * 0.3
    parts.append(P(W, H, many(ell(ex, 15, 3, 2), ell(ex + 6, 15, 3, 2)), [(220, 246, 250)] * 5, z=5, flat=True,
                   emit=(200, 246, 250)))
    # the pearl
    pr = 5 + (3 * t if attack else math.sin(ph) * 0.4)
    parts.append(P(W, H, circ(32, 38 - lift, pr), PEARL, z=6, height=4, dome=0.65, rim=(255, 255, 255),
                   emit=(255, 246, 226)))
    return parts


def brine_crawler(t, attack):
    """A teal brine crab: a wide ridged shell crusted with barnacles, eyes on stalks, six jointed
    legs scuttling, two heavy pincers - raised and snapping on attack."""
    W = H = 64
    ph = t * math.tau
    parts = []
    # legs (3 a side, alternating)
    legs = []
    for side in (-1, 1):
        for k in range(3):
            lift = math.sin(ph * 2 + k * 2.1 + (0 if side < 0 else math.pi)) * 2.5
            x0, y0 = 32 + side * (10 + k * 3), 38 + k * 2
            kx, ky = 32 + side * (20 + k * 2), 36 + k * 3 - lift
            fx, fy = 32 + side * (25 + k * 1.5), 50 + k * 3
            legs.append(lines([(x0, y0), (kx, ky), (fx, fy)], 3))
    parts.append(P(W, H, many(*legs), SEA_D, z=0, rim=WATER_RIM, height=1.5, noise=0.06))
    # claw arms + pincers
    raise_ = (8 * t) if attack else math.sin(ph) * 1.0
    snap = (0.25 + 0.9 * t) if attack else 0.35
    for side in (-1, 1):
        ax, ay = 32 + side * 12, 30
        cx, cy = 32 + side * 22, 18 - raise_
        parts.append(P(W, H, lines([(ax, ay), (32 + side * 20, 27 - raise_ * 0.5), (cx, cy + 5)], 4), SEA, z=2,
                       rim=WATER_RIM, height=1.5))
        # pincer: a fat palm + a hinged finger
        parts.append(P(W, H, ell(cx - 6, cy - 4, 12, 11), SEA, z=3, rim=WATER_RIM, height=4, seed=14))
        a0 = -math.pi / 2 + side * 0.2
        f1 = [(cx - 1, cy - 2), (cx + math.cos(a0 - side * snap) * 10, cy - 3 + math.sin(a0 - side * snap) * 9),
              (cx + 2 * side, cy - 2)]
        f2 = [(cx + 1, cy - 2), (cx + math.cos(a0 + side * snap) * 9, cy - 3 + math.sin(a0 + side * snap) * 8),
              (cx - 2 * side, cy - 1)]
        parts.append(P(W, H, many(poly(f1), poly(f2)), SEA, z=3.5, rim=WATER_RIM, height=2))
    # the shell
    parts.append(P(W, H, ell(12, 26, 40, 24), SEA, z=4, rim=WATER_RIM, height=9, noise=0.06, seed=15, dome=0.5))
    parts.append(P(W, H, many(*[lines([(18 + k * 7, 30 + abs(k - 2) * 1.5), (20 + k * 6, 45)], 1) for k in range(5)]),
                   SEA_D, z=4.2, flat=True))
    parts.append(P(W, H, many(circ(22, 33, 2), circ(40, 31, 1.5), circ(35, 42, 1.5), circ(26, 43, 1)), PEARL, z=4.4,
                   height=1.2))                                                         # barnacles
    # eye stalks
    for x in (26, 38):
        sx = x + math.sin(ph + x) * 1.0
        parts.append(P(W, H, lines([(x, 29), (sx, 20)], 2), SEA, z=5, height=1))
        parts.append(P(W, H, circ(sx, 19, 2.5), [(255, 214, 96)] * 5, z=6, flat=True, emit=(255, 200, 80)))
        parts.append(P(W, H, circ(sx + 0.5, 19, 1), EYE_DARK, z=6.5, flat=True))
    return parts


def abyssal_chorister(t, attack):
    """A hovering hooded singer of the deep: a dark teal cowl, a void face with two dim eyes and a
    glowing open mouth, robes dissolving into tendrils, song-notes drifting up. It sings louder on
    attack."""
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 1.5
    parts = []
    tails = []
    for k in range(5):
        x0 = 22 + k * 5
        off = math.sin(ph + k * 1.4) * 3
        tails.append(poly([(x0, 40 + bob), (x0 + 5, 40 + bob), (x0 + 3 + off, 61 - (k % 2) * 4), (x0 + 1 + off * 0.5, 54)]))
    parts.append(P(W, H, many(*tails), ROBE_DARK, z=0, rim=(110, 200, 210), height=2, alpha=215, noise=0.08))
    parts.append(P(W, H, poly([(22, 22 + bob), (42, 22 + bob), (47, 44 + bob), (17, 44 + bob)]), ROBE_TEAL, z=1,
                   rim=WATER_RIM, height=7, noise=0.07, seed=16))
    parts.append(P(W, H, many(lines([(26, 26 + bob), (24, 43 + bob)], 1), lines([(38, 26 + bob), (40, 43 + bob)], 1)),
                   ROBE_DARK, z=1.2, flat=True))
    arm_up = (6 * t) if attack else 0
    parts.append(P(W, H, many(lines([(21, 26 + bob), (14, 36 + bob - arm_up), (12, 30 + bob - arm_up * 1.5)], 3),
                              lines([(43, 26 + bob), (50, 36 + bob - arm_up), (52, 30 + bob - arm_up * 1.5)], 3)),
                   ROBE_TEAL, z=2, rim=WATER_RIM, height=1.5))
    parts.append(P(W, H, ell(18, 3 + bob, 28, 26), ROBE_TEAL, z=3, rim=WATER_RIM, height=7, noise=0.06, seed=17))
    parts.append(P(W, H, ell(23, 9 + bob, 18, 17), [(4, 10, 14)] * 5, z=3.5, flat=True))
    parts.append(P(W, H, many(ell(26, 14 + bob, 3, 2), ell(35, 14 + bob, 3, 2)), [(120, 170, 176)] * 5, z=4, flat=True,
                   emit=(80, 150, 160)))
    mo = (3 + 4 * t) if attack else 2.5 + math.sin(ph * 2) * 0.8
    parts.append(P(W, H, ell(29, 19 + bob, 6, mo), [SONG] * 5, z=4, flat=True, emit=SONG))
    # drifting notes
    for k in range(3):
        u = (t + k / 3) % 1.0
        nx, ny = 46 + k * 3 + math.sin(ph + k) * 2, 18 - u * 16 + bob
        parts.append(P(W, H, many(circ(nx, ny, 1.5), lines([(nx + 1, ny), (nx + 1, ny - 4)], 1)), [SONG] * 5, z=6,
                       flat=True, emit=SONG))
    return parts


def coral_sentinel(t, attack):
    """A squat coral golem: a knobbly pink body crusted with polyps, a crown of branching coral,
    pale lamp-eyes over a toothed grille, two stumpy legs. On attack the crown flares and spores
    puff from the tips."""
    W = H = 64
    ph = t * math.tau
    step = math.sin(ph) * 1.5
    parts = []
    parts.append(P(W, H, many(poly([(20, 44), (28, 44), (27, 58 - step), (19, 58 - step)]),
                              poly([(36, 44), (44, 44), (45, 58 + step), (37, 58 + step)])),
                   CORAL_D, z=0, rim=CORAL_RIM, height=2.5, noise=0.1))
    parts.append(P(W, H, many(ell(16, 56 - step, 14, 5), ell(34, 56 + step, 14, 5)), CORAL_D, z=0.5, height=2))
    parts.append(P(W, H, ell(9, 20, 46, 32), CORAL, z=1, rim=CORAL_RIM, height=10, noise=0.12, seed=18, dome=0.5))
    parts.append(P(W, H, many(*[circ(14 + (k * 11) % 36, 26 + (k * 7) % 20, 1.5) for k in range(9)]), CORAL_D, z=1.2,
                   flat=True))                                                          # polyp pits
    # the crown: branching coral
    flare = (1 + 0.35 * t) if attack else 1.0
    br = []
    for k in range(5):
        x0 = 16 + k * 8
        a = -math.pi / 2 + (k - 2) * 0.32 * flare + math.sin(ph + k) * 0.06
        L = (10 + (k % 2) * 4) * flare
        x1, y1 = x0 + math.cos(a) * L, 22 + math.sin(a) * L
        br.append(lines([(x0, 24), (x1, y1)], 3))
        for s in (-1, 1):
            a2 = a + s * 0.6
            br.append(lines([((x0 + x1) / 2, (24 + y1) / 2), ((x0 + x1) / 2 + math.cos(a2) * 5,
                                                               (24 + y1) / 2 + math.sin(a2) * 5)], 2))
    parts.append(P(W, H, many(*br), CORAL_TIP, z=0.8, rim=CORAL_RIM, height=1.5, noise=0.05))
    # face: eyes + grille
    parts.append(P(W, H, many(ell(19, 28, 8, 6), ell(37, 28, 8, 6)), [(255, 240, 206)] * 5, z=2, flat=True,
                   emit=(255, 226, 190)))
    parts.append(P(W, H, many(circ(23, 31, 1.2), circ(41, 31, 1.2)), EYE_DARK, z=2.5, flat=True))
    gap = (3 + 3 * t) if attack else 2
    parts.append(P(W, H, ell(18, 38, 28, 6 + gap), [(40, 6, 14)] * 5, z=2, flat=True))
    teeth = [poly([(19 + k * 3.4, 38), (22 + k * 3.4, 38), (20.5 + k * 3.4, 41)]) for k in range(8)]
    parts.append(P(W, H, many(*teeth), BONEP, z=3, flat=True))
    if attack:
        for k in range(4):
            sx, sy = 14 + k * 11, 6 - t * 4
            parts.append(P(W, H, circ(sx, sy, 1.5 + t), [(255, 170, 180)] * 5, z=5, flat=True, emit=(255, 150, 170)))
    return parts


def drowned_custodian(t, attack):
    """A hulking temple custodian of green-gold bronze: barnacled pauldrons, a cage-barred helm with
    sea-light eye slits, huge gauntlets on chains. On attack it raises both fists."""
    W = H = 64
    ph = t * math.tau
    sway = math.sin(ph) * 1.2
    parts = []
    parts.append(P(W, H, many(poly([(20, 46), (28, 46), (27, 61), (18, 61)]), poly([(36, 46), (44, 46), (46, 61), (37, 61)])),
                   VERD_D, z=0, height=2.5, rim=WATER_RIM, noise=0.08))
    parts.append(P(W, H, poly([(18, 22), (46, 22), (49, 34), (44, 48), (20, 48), (15, 34)]), VERD, z=1, rim=WATER_RIM,
                   height=9, noise=0.1, seed=19))
    parts.append(P(W, H, many(lines([(20, 32), (44, 32)], 1), lines([(22, 40), (42, 40)], 1), lines([(32, 23), (32, 47)], 1)),
                   VERD_D, z=1.2, flat=True))
    parts.append(P(W, H, many(ell(8, 18, 18, 14), ell(38, 18, 18, 14)), VERD, z=2, rim=WATER_RIM, height=5, noise=0.1,
                   seed=20))                                                            # pauldrons
    parts.append(P(W, H, many(circ(13, 21, 1.5), circ(19, 19, 1), circ(45, 20, 1.5), circ(50, 23, 1)), PEARL, z=2.3,
                   height=1))                                                           # barnacles
    up = (14 * t) if attack else 0
    for side in (-1, 1):
        sx = 32 + side * 19
        hx, hy = 32 + side * 23 + sway * side, 44 - up
        parts.append(P(W, H, lines([(sx, 26), (32 + side * 23, 36 - up * 0.5), (hx, hy)], 5), VERD, z=1.5, rim=WATER_RIM,
                       height=2))
        parts.append(P(W, H, ell(hx - 5, hy - 4, 10, 10), VERD, z=3, rim=WATER_RIM, height=4, noise=0.08))
        parts.append(P(W, H, lines([(hx, hy + 5), (hx + side * 2, hy + 10 + sway)], 1), [(70, 80, 80)] * 5, z=2.8, flat=True))
    # the caged helm
    parts.append(P(W, H, ell(21 + sway * 0.4, 3, 22, 22), VERD, z=4, rim=WATER_RIM, height=7, noise=0.08, seed=21))
    parts.append(P(W, H, ell(24 + sway * 0.4, 9, 16, 12), [(4, 16, 18)] * 5, z=4.5, flat=True))
    parts.append(P(W, H, many(*[lines([(26 + k * 4 + sway * 0.4, 9), (26 + k * 4 + sway * 0.4, 20)], 1) for k in range(4)]),
                   VERD_D, z=5, flat=True))
    glow = (180, 250, 252) if attack else (130, 226, 230)
    parts.append(P(W, H, many(lines([(25 + sway * 0.4, 13), (30 + sway * 0.4, 13)], 2),
                              lines([(34 + sway * 0.4, 13), (39 + sway * 0.4, 13)], 2)), [glow] * 5, z=5.5, flat=True,
                   emit=glow))
    return parts


def kelp_stalker(t, attack):
    """A tall, kelp-wrapped stalker: overlapping fronds swaying round a lean body, a lamp-green visor
    slit, ribbon arms that lash out on attack, a tangle of holdfast roots for feet."""
    W = H = 64
    ph = t * math.tau
    parts = []
    parts.append(P(W, H, many(*[lines([(28 + k * 2.5, 52), (24 + k * 4 + math.sin(ph + k) * 1.5, 62)], 2) for k in range(4)]),
                   KELP_D, z=0, height=1))                                              # roots
    lash = (1 + 0.55 * t) if attack else 1.0
    for side in (-1, 1):
        rib = _spine(lambda u, side=side: (32 + side * (6 + u * 16 * lash),
                                           22 + u * 14 + math.sin(ph * 1.5 + u * 5 + side) * 3 * u), 10,
                     lambda u: 2.4 * (1 - u * 0.7))
        parts.append(P(W, H, poly(rib), KELP, z=1, rim=(190, 255, 170), height=1.5, noise=0.08))
    parts.append(P(W, H, poly([(25, 12), (39, 12), (42, 30), (40, 52), (24, 52), (22, 30)]), KELP_D, z=2, height=6,
                   noise=0.1, seed=22))
    for k in range(6):  # fronds layered over the body
        x0 = 22 + (k % 3) * 7
        y0 = 16 + (k // 3) * 16
        sw = math.sin(ph + k * 0.9) * 2
        fr = _spine(lambda u, x0=x0, y0=y0, sw=sw: (x0 + 3 + sw * u, y0 + u * 18), 8,
                    lambda u: 3.2 * math.sin(math.pi * min(1, u + 0.08)))
        parts.append(P(W, H, poly(fr), KELP, z=3 + k * 0.1, rim=(190, 255, 170), height=2, noise=0.08, seed=23 + k))
    parts.append(P(W, H, ell(23, 4, 18, 14), KELP, z=4, rim=(190, 255, 170), height=5, noise=0.08, seed=29))
    vis = (190, 255, 140) if attack else (150, 236, 120)
    parts.append(P(W, H, ell(25, 10, 14, 3), [vis] * 5, z=5, flat=True, emit=vis))
    return parts


def shellback_guardian(t, attack):
    """A great shell-backed guardian: a domed shell with spiral ridges and pale plate rims, a
    beaked head with ember-orange eyes, thick scaled legs. On attack the head thrusts out, beak
    open."""
    W = H = 64
    ph = t * math.tau
    step = math.sin(ph) * 1.5
    parts = []
    parts.append(P(W, H, many(ell(10, 44 - step, 12, 16), ell(42, 44 + step, 12, 16)), SHELL_D, z=0, rim=WATER_RIM,
                   height=3, noise=0.1))
    parts.append(P(W, H, ell(6, 14, 52, 38), SHELL, z=1, rim=WATER_RIM, height=12, noise=0.08, seed=30, dome=0.55))
    # spiral ridges + plates
    sp = [(32 + math.cos(a) * a * 2.1, 30 + math.sin(a) * a * 1.4) for a in [k * 0.35 for k in range(26)]]
    parts.append(P(W, H, lines(sp, 1), SHELL_D, z=1.2, flat=True))
    parts.append(P(W, H, ell(7, 40, 50, 9), BONEP, z=1.4, height=2, noise=0.05))  # the plastron rim
    thrust = (6 * t) if attack else math.sin(ph) * 0.8
    hy = 34 + thrust
    parts.append(P(W, H, ell(22, hy, 20, 16), SHELL_D, z=2, rim=WATER_RIM, height=5, noise=0.08))
    beak = (2 + 4 * t) if attack else 1.5
    parts.append(P(W, H, many(poly([(27, hy + 9), (37, hy + 9), (32, hy + 15)]),
                              poly([(28, hy + 10 + beak), (36, hy + 10 + beak), (32, hy + 13 + beak)])),
                   BONEP, z=3, height=1.5))
    parts.append(P(W, H, many(circ(27, hy + 6, 2.2), circ(37, hy + 6, 2.2)), [(255, 170, 80)] * 5, z=3.5, flat=True,
                   emit=(255, 150, 60)))
    return parts


def siren_wraith(t, attack):
    """A drowned siren: a pale face framed by long streaming sea-green hair, hollow eyes, a mouth of
    golden song, pale arms reaching, a tattered robe trailing into the water. On attack the arms
    open wide and the song blazes."""
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 1.5
    parts = []
    for k in range(5):
        x0 = 22 + k * 5
        off = math.sin(ph + k * 1.2) * 3
        parts.append(P(W, H, poly([(x0, 40 + bob), (x0 + 5, 40 + bob), (x0 + 2 + off, 62 - (k % 2) * 4)]), ROBE_TEAL,
                       z=0, alpha=210, height=2, noise=0.08))
    hair = []
    for side in (-1, 1):
        hair.append(_spine(lambda u, side=side: (32 + side * (9 + u * 8) + math.sin(ph + u * 4) * 2 * u, 8 + bob + u * 34),
                           10, lambda u: 4.5 * (1 - u * 0.75)))
    parts.append(P(W, H, many(*[poly(hh) for hh in hair]), ROBE_TEAL, z=1, rim=WATER_RIM, height=2, noise=0.08))
    parts.append(P(W, H, poly([(27, 23 + bob), (37, 23 + bob), (39, 31 + bob), (35, 34 + bob), (46, 46 + bob),
                              (38, 44 + bob), (32, 47 + bob), (26, 44 + bob), (18, 46 + bob), (29, 34 + bob),
                              (25, 31 + bob)]), ROBE_PALE, z=2, rim=WATER_RIM, height=5, alpha=235, noise=0.05, seed=31))
    parts.append(P(W, H, many(*[circ(32 + math.cos(a) * 6, 25 + bob + math.sin(a) * 3, 1) for a in [0.3 + k * 0.5 for k in range(6)]]),
                   PEARL, z=2.2, height=1, emit=(200, 196, 186)))
    wide = (10 * t) if attack else 0
    parts.append(P(W, H, many(lines([(23, 27 + bob), (14 - wide, 34 + bob - wide * 0.6), (10 - wide, 30 + bob - wide)], 2),
                              lines([(41, 27 + bob), (50 + wide, 34 + bob - wide * 0.6), (54 + wide, 30 + bob - wide)], 2)),
                   ROBE_PALE, z=2.5, height=1, rim=WATER_RIM))
    parts.append(P(W, H, ell(23, 4 + bob, 18, 21), ROBE_PALE, z=3, rim=WATER_RIM, height=6, dome=0.55))
    parts.append(P(W, H, many(ell(26, 12 + bob, 4, 5), ell(34, 12 + bob, 4, 5)), [(14, 30, 36)] * 5, z=3.5, flat=True))
    parts.append(P(W, H, many(circ(28, 15 + bob, 0.8), circ(36, 15 + bob, 0.8)), [(170, 230, 220)] * 5, z=3.6,
                   flat=True, emit=(150, 220, 210)))
    mo = (3 + 4 * t) if attack else 2 + math.sin(ph * 2) * 0.6
    parts.append(P(W, H, ell(30, 19 + bob, 5, mo), [(255, 232, 180)] * 5, z=4, flat=True, emit=(255, 220, 160)))
    if attack:
        for k in range(2):
            r = 8 + k * 6 + t * 6
            parts.append(P(W, H, lambda s, c, r=r: pygame.draw.arc(s, c, (32 - r, 20 + bob - r * 0.6, r * 2, r * 1.2),
                                                                     -0.8, 0.8, 1),
                           [(255, 230, 170)] * 5, z=5, flat=True, emit=(255, 220, 150)))
    return parts


def choir_warden(t, attack):
    """A tall choir warden in pale temple armour: a peaked hood, a dark visor band, a glowing hymn
    on its breast, and a towering tuning-fork spear it charges with on attack."""
    W = H = 64
    ph = t * math.tau
    step = math.sin(ph) * 1.5
    lunge = (5 * t) if attack else 0
    X = lambda x: x + lunge
    parts = []
    parts.append(P(W, H, many(poly([(X(23), 44), (X(29), 44), (X(28), 60 - step), (X(21), 60 - step)]),
                              poly([(X(33), 44), (X(39), 44), (X(41), 60 + step), (X(34), 60 + step)])),
                   ROBE_TEAL, z=0, rim=WATER_RIM, height=2.5, noise=0.06))
    parts.append(P(W, H, poly([(X(20), 20), (X(42), 20), (X(45), 34), (X(41), 46), (X(21), 46), (X(17), 34)]), ROBE_PALE,
                   z=1, rim=WATER_RIM, height=8, noise=0.05, seed=32))
    parts.append(P(W, H, poly([(X(25), 22), (X(37), 22), (X(38), 47), (X(31), 52), (X(24), 47)]), ROBE_TEAL, z=1.4,
                   height=4, noise=0.06))
    parts.append(P(W, H, many(lines([(X(28), 30), (X(34), 30)], 1), lines([(X(27), 34), (X(35), 34)], 1),
                              lines([(X(28), 38), (X(34), 38)], 1), circ(X(31), 43, 1.6)), [(220, 250, 255)] * 5, z=1.5,
                   flat=True, emit=(170, 240, 250)))
    parts.append(P(W, H, many(ell(X(15), 18, 12, 9), ell(X(36), 18, 12, 9)), ROBE_PALE, z=3.5, rim=WATER_RIM, height=4,
                   noise=0.05))
    # the spear (tuning fork)
    sx = X(48)
    tilt = (8 * t) if attack else 0
    parts.append(P(W, H, lines([(sx - tilt * 0.3, 60), (sx + tilt, 8)], 2), BONEP, z=2, height=1))
    parts.append(P(W, H, many(lines([(sx + tilt - 4, 12), (sx + tilt - 4, 2)], 2), lines([(sx + tilt + 4, 12), (sx + tilt + 4, 2)], 2),
                              lines([(sx + tilt - 4, 12), (sx + tilt + 4, 12)], 2)), ROBE_PALE, z=2.2, height=1,
                   rim=WATER_RIM, emit=(170, 240, 250) if attack else None))
    parts.append(P(W, H, lines([(X(41), 26), (sx - 2 + tilt * 0.4, 34)], 4), ROBE_PALE, z=3, rim=WATER_RIM, height=1.5))
    parts.append(P(W, H, circ(sx + tilt * 0.4, 34, 3), BONEP, z=3.2, height=1.5))
    # hood + visor
    parts.append(P(W, H, poly([(X(31), 0), (X(43), 14), (X(40), 22), (X(22), 22), (X(19), 14)]), ROBE_PALE, z=4,
                   rim=WATER_RIM, height=6, noise=0.05, seed=33))
    parts.append(P(W, H, poly([(X(23), 11), (X(39), 11), (X(38), 15), (X(24), 15)]), [(14, 34, 42)] * 5, z=4.5, flat=True))
    parts.append(P(W, H, many(circ(X(28), 13, 1), circ(X(34), 13, 1)), [(200, 250, 255)] * 5, z=5, flat=True,
                   emit=(180, 246, 255)))
    return parts


# ============================================================ 160x104 mini-bosses
BW, BH = 160, 104


def B(fn, *a, **k):
    return P(BW, BH, fn, *a, **k)


def choir_sovereign(t, attack):
    """The Choir Sovereign: a towering crowned singer-king in layered sea-robes, a pale mask with
    two lamp-eyes, a crown of tideglass spires, conducting two orbiting orbs of song. On attack it
    raises both arms and the orbs and crown blaze."""
    ph = t * math.tau
    bob = math.sin(ph) * 2
    parts = []
    hem = [(30 + k * 12.5, 100 - (k % 2) * 6 + math.sin(ph + k) * 2) for k in range(9)]
    robe = [(62, 30 + bob), (98, 30 + bob), (116, 60), (132, 98)] + list(reversed(hem)) + [(28, 98), (44, 60)]
    parts.append(B(poly(robe), ROBE_TEAL, z=1, rim=WATER_RIM, height=12, noise=0.07, seed=40))
    parts.append(B(poly([(72, 36 + bob), (88, 36 + bob), (96, 98), (64, 98)]), ROBE_DARK, z=1.3, height=6, noise=0.06))
    parts.append(B(many(*[circ(80, 50 + bob + k * 9, 2.5) for k in range(5)]), PEARL, z=1.35, height=1.5,
                   emit=(210, 206, 196)))
    parts.append(B(many(*[lines([(66 + k * 7, 44 + bob), (58 + k * 11 + math.sin(ph + k) * 2, 98)], 1) for k in range(5)]),
                   ROBE_DARK, z=1.4, flat=True))
    parts.append(B(many(*[circ(80 + math.cos(a) * 15, 40 + bob + math.sin(a) * 7, 2) for a in [0.2 + k * 0.34 for k in range(9)]]),
                   PEARL, z=1.6, height=1.5, emit=(210, 206, 196)))
    # shoulders / mantle
    parts.append(B(ell(44, 26 + bob, 72, 24), ROBE_TEAL, z=2, rim=WATER_RIM, height=7, noise=0.06, seed=41))
    parts.append(B(many(*[poly([(48 + k * 8, 36 + bob - abs(k - 4) * 1.5), (54 + k * 8, 36 + bob - abs(k - 4) * 1.5),
                                (51 + k * 8, 44 + bob - abs(k - 4) * 1.5)]) for k in range(9)]), GOLDSONG, z=2.1, height=1.5))
    up = (18 * t) if attack else 0
    orbs = []
    for side in (-1, 1):
        sx, sy = 80 + side * 30, 34 + bob
        hx, hy = 80 + side * 54, 56 + bob - up
        parts.append(B(lines([(sx, sy), (80 + side * 46, 48 + bob - up * 0.5), (hx, hy)], 7), ROBE_TEAL, z=2.5,
                       rim=WATER_RIM, height=2))
        parts.append(B(circ(hx, hy, 4), BONEP, z=3, height=2))
        a = ph * (1 if not attack else 0) + (0 if side < 0 else math.pi)
        ox, oy = hx + math.cos(a) * 3, hy - 12 - abs(math.sin(a)) * 3
        orbs.append((ox, oy))
    r_orb = 7 + (4 * t if attack else 0)
    for (ox, oy) in orbs:
        parts.append(B(circ(ox, oy, r_orb), GLASS, z=6, height=5, dome=0.6, rim=(255, 255, 255), emit=(160, 240, 246)))
    # head + mask
    parts.append(B(ell(66, 2 + bob, 28, 32), ROBE_TEAL, z=4, rim=WATER_RIM, height=8, noise=0.05, seed=42))
    parts.append(B(ell(69, 8 + bob, 22, 25), [(6, 14, 18)] * 5, z=4.4, flat=True))
    parts.append(B(poly([(72, 12 + bob), (88, 12 + bob), (86, 26 + bob), (80, 30 + bob), (74, 26 + bob)]), ROBE_PALE,
                   z=4.5, height=4, dome=0.55))
    parts.append(B(many(poly([(73, 16 + bob), (79, 17 + bob), (78, 20 + bob), (74, 19 + bob)]),
                        poly([(87, 16 + bob), (81, 17 + bob), (82, 20 + bob), (86, 19 + bob)])), [(10, 40, 48)] * 5, z=5,
                   flat=True))
    parts.append(B(many(circ(76, 18 + bob, 1), circ(84, 18 + bob, 1)), [(220, 255, 255)] * 5, z=5.2, flat=True,
                   emit=(200, 250, 255)))
    parts.append(B(ell(77, 23 + bob, 6, 2 + (3 * t if attack else 0)), [SONG] * 5, z=5, flat=True, emit=SONG))
    # the crown of tideglass spires
    spires = []
    for k in range(7):
        x = 66 + k * 4.6
        h = 10 + (6 if k == 3 else 3 * (k % 2)) + (4 * t if attack else 0)
        spires.append(poly([(x - 2, 6 + bob), (x + 2, 6 + bob), (x, 6 + bob - h)]))
    parts.append(B(many(*spires), GLASS, z=5.5, height=2, rim=(255, 255, 255), emit=(150, 236, 240)))
    return parts


def coral_leviathan(t, attack):
    """The Coral Leviathan: a vast serpent crusted in pink coral, its coils humping out of the sea
    behind a great armoured head - branching coral spines, a pale lamp-eye, a jaw of bone teeth that
    gapes on attack."""
    ph = t * math.tau
    rise = math.sin(ph) * 2
    parts = []
    # coils behind (two humps)
    for k, (cx, w) in enumerate(((30, 40), (122, 40))):
        hump = _spine(lambda u, cx=cx, w=w, k=k: (cx - w / 2 + u * w, 80 - math.sin(u * math.pi) * (22 + k * 4) + rise * (1 - k)),
                      14, lambda u: 9 * math.sin(math.pi * min(0.99, u * 0.9 + 0.05)) + 3)
        parts.append(B(poly(hump), CORAL_D, z=1 + k * 0.1, rim=CORAL_RIM, height=6, noise=0.1, seed=43 + k))
        spines = []
        for j in range(4):
            u = 0.2 + j * 0.2
            x = cx - w / 2 + u * w
            y = 80 - math.sin(u * math.pi) * (22 + k * 4) - 8
            spines.append(lines([(x, y + 4), (x + 2, y - 8), (x + 6, y - 12)], 2))
        parts.append(B(many(*spines), CORAL_TIP, z=1.2 + k * 0.1, height=1, emit=(255, 150, 160)))
    # the neck rising to the head
    neck = _spine(lambda u: (80 + math.sin(u * 2 + ph) * 4, 100 - u * 50 + rise * u), 12, lambda u: 15 - u * 3)
    parts.append(B(poly(neck), CORAL, z=2, rim=CORAL_RIM, height=9, noise=0.1, seed=45))
    parts.append(B(many(*[lines([(70, 96 - k * 9 + rise * k / 6), (90, 96 - k * 9 + rise * k / 6)], 1) for k in range(5)]),
                   CORAL_D, z=2.2, flat=True))
    jaw = (12 * t) if attack else 3 + math.sin(ph) * 1
    hy = 22 + rise
    # head: upper skull + lower jaw
    parts.append(B(poly([(52, hy + 18 + jaw), (108, hy + 18 + jaw), (102, hy + 30 + jaw), (60, hy + 30 + jaw)]), CORAL_D,
                   z=3, rim=CORAL_RIM, height=5, noise=0.1))
    parts.append(B(poly([(58, hy + 18), (102, hy + 18), (100, hy + 26 + jaw), (60, hy + 26 + jaw)]), [(50, 6, 16)] * 5,
                   z=3.2, flat=True))
    teeth = [poly([(60 + k * 5.5, hy + 18), (64 + k * 5.5, hy + 18), (62 + k * 5.5, hy + 25)]) for k in range(8)] + \
            [poly([(61 + k * 5.5, hy + 18 + jaw), (65 + k * 5.5, hy + 18 + jaw), (63 + k * 5.5, hy + 12 + jaw)]) for k in range(7)]
    parts.append(B(many(*teeth), BONEP, z=3.5, flat=True))
    parts.append(B(poly([(48, hy + 18), (60, hy - 4), (80, hy - 10), (100, hy - 4), (112, hy + 18)]), CORAL, z=4,
                   rim=CORAL_RIM, height=10, noise=0.1, seed=46))
    # coral spines / branches on the head
    br = []
    for k in range(6):
        x0 = 58 + k * 9
        a = -math.pi / 2 + (k - 2.5) * 0.25 + math.sin(ph + k) * 0.05
        L = 14 + (k % 2) * 6
        x1, y1 = x0 + math.cos(a) * L, hy - 4 + math.sin(a) * L
        br.append(lines([(x0, hy), (x1, y1)], 3))
        br.append(lines([((x0 + x1) / 2, (hy + y1) / 2), ((x0 + x1) / 2 + 5, (hy + y1) / 2 - 4)], 2))
    parts.append(B(many(*br), CORAL_TIP, z=3.8, rim=CORAL_RIM, height=1.5, emit=(255, 150, 160)))
    # eyes
    eye = (255, 250, 200) if attack else (255, 236, 190)
    parts.append(B(many(ell(64, hy + 6, 9, 6), ell(87, hy + 6, 9, 6)), [eye] * 5, z=5, flat=True, emit=eye))
    parts.append(B(many(ell(67, hy + 7, 3, 4), ell(90, hy + 7, 3, 4)), EYE_DARK, z=5.5, flat=True))
    return parts


def tideglass_warden(t, attack):
    """The Tideglass Warden: a towering faceted crystal of sea-glass with a swirling tide caught in
    its heart, two dark eyes in the facets, shards orbiting it - flung outward on attack."""
    ph = t * math.tau
    bob = math.sin(ph) * 2
    parts = []
    cx, top, mid, bot = 80, 4 + bob, 48 + bob, 100 + bob * 0.5
    outer = [(cx, top), (cx + 30, mid - 10), (cx + 24, mid + 20), (cx, bot), (cx - 24, mid + 20), (cx - 30, mid - 10)]
    parts.append(B(poly(outer), GLASS_D, z=1, rim=(255, 255, 255), height=10, alpha=235, noise=0.03, seed=47))
    facets = [([(cx, top), (cx + 30, mid - 10), (cx, mid - 4)], GLASS), ([(cx, top), (cx - 30, mid - 10), (cx, mid - 4)], GLASS_D),
              ([(cx + 30, mid - 10), (cx + 24, mid + 20), (cx, mid - 4)], GLASS_D),
              ([(cx - 30, mid - 10), (cx - 24, mid + 20), (cx, mid - 4)], GLASS),
              ([(cx - 24, mid + 20), (cx, bot), (cx, mid - 4)], GLASS_D), ([(cx + 24, mid + 20), (cx, bot), (cx, mid - 4)], GLASS)]
    for k, (pts, rp) in enumerate(facets):
        parts.append(B(poly(pts), rp, z=1.5 + k * 0.01, height=6, alpha=225, dome=0.35, noise=0.03, seed=48 + k))
    # the tide caught inside: a glowing swirl
    sw = [(cx + math.cos(ph * (2 if attack else 1) + a * 0.45) * (2 + a * 1.1), mid + 6 + math.sin(ph + a * 0.45) * (1.5 + a * 0.8))
          for a in range(18)]
    core_r = 9 + (6 * t if attack else 0)
    parts.append(B(circ(cx, mid + 6, core_r), FOAM, z=2, height=6, dome=0.6, alpha=230, emit=(150, 240, 250)))
    parts.append(B(lines(sw, 2), [(240, 255, 255)] * 5, z=2.5, flat=True, emit=(220, 255, 255)))
    parts.append(B(many(poly([(cx - 14, mid - 12), (cx - 6, mid - 14), (cx - 8, mid - 8)]),
                        poly([(cx + 14, mid - 12), (cx + 6, mid - 14), (cx + 8, mid - 8)])), EYE_DARK, z=3, flat=True))
    # orbiting shards
    for k in range(6):
        a = ph + k * math.tau / 6
        rr = 50 + (18 * t if attack else 0)
        x, y = cx + math.cos(a) * rr, mid + math.sin(a) * rr * 0.42
        parts.append(B(poly([(x, y - 7), (x + 4, y), (x, y + 6), (x - 3, y)]), GLASS, z=4 if math.sin(a) > 0 else 0.5,
                       height=2, rim=(255, 255, 255), emit=(140, 230, 240)))
    return parts


def driftbell_matriarch(t, attack):
    """The Driftbell Matriarch: a vast jellyfish queen - a translucent frilled bell pulsing with
    inner lights, small dark eyes, frilly oral arms and long trailing tentacles that sway; on attack
    the bell contracts and the tentacles flare out, glowing."""
    ph = t * math.tau
    pulse = math.sin(ph) * 3
    contract = (8 * t) if attack else 0
    parts = []
    cx = 80
    # tentacles (behind)
    for k in range(9):
        x0 = 50 + k * 7.5
        spread = (k - 4) * (1.6 + (2.5 * t if attack else 0))
        tent = _spine(lambda u, x0=x0, k=k, spread=spread: (x0 + spread * u * 8 + math.sin(ph + u * 5 + k) * 4 * u,
                                                            42 + u * 60), 12, lambda u: 2.2 * (1 - u * 0.6))
        parts.append(B(poly(tent), JELLY, z=0.5, alpha=200, height=1, flat=False, rim=(220, 250, 255),
                       emit=(130, 200, 230) if attack else None))
    # frilly oral arms
    for k in range(4):
        x0 = 66 + k * 9
        arm = _spine(lambda u, x0=x0, k=k: (x0 + math.sin(ph * 1.3 + u * 6 + k) * 5, 44 + u * 40), 12,
                     lambda u: 3.5 * (1 - u * 0.6) * (0.75 + 0.25 * math.sin(u * 20)))
        parts.append(B(poly(arm), JELLY, z=1, alpha=215, height=2, rim=(220, 250, 255), noise=0.06))
    # the bell
    bw = 86 - contract + pulse
    bh = 48 - contract * 0.4 - pulse * 0.4
    parts.append(B(ell(cx - bw / 2, 2, bw, bh), JELLY, z=2, alpha=220, height=12, dome=0.55, rim=(255, 255, 255),
                   noise=0.03, seed=55))
    scal = [ell(cx - bw / 2 + k * bw / 10 - 1, 2 + bh - 9 + math.sin(ph + k) * 1.5, bw / 10 + 2, 10) for k in range(10)]
    parts.append(B(many(*scal), JELLY, z=1.9, alpha=210, height=3, rim=(255, 255, 255), noise=0.04))
    # inner organs - glowing
    lit = (200, 250, 255) if attack else (160, 230, 246)
    parts.append(B(many(*[ell(cx - 22 + k * 12, 14 + (k % 2) * 4, 8, 10) for k in range(4)]), FOAM, z=3, height=3,
                   alpha=220, emit=lit))
    parts.append(B(many(*[lines([(cx, 6), (cx - 30 + k * 12, 2 + bh - 8)], 1) for k in range(6)]), [(200, 236, 246)] * 5,
                   z=3.2, flat=True, alpha=200))
    parts.append(B(many(ell(cx - 14, 26, 5, 4), ell(cx + 9, 26, 5, 4)), EYE_DARK, z=4, flat=True))
    return parts


def abyssal_choirmaster(t, attack):
    """The Abyssal Choirmaster: a cowled conductor of the deep in violet - a bell-shaped hood with
    two lavender lamp-eyes, a tentacled robe drifting below, and rings of sigils (the song itself)
    turning around it; on attack the rings blaze and spread."""
    ph = t * math.tau
    bob = math.sin(ph) * 2
    parts = []
    cx = 80
    for k in range(8):
        x0 = 54 + k * 7.5
        tent = _spine(lambda u, x0=x0, k=k: (x0 + (k - 3.5) * u * 4 + math.sin(ph + u * 5 + k) * 4 * u, 52 + bob + u * 48),
                      12, lambda u: 3.2 * (1 - u * 0.75))
        parts.append(B(poly(tent), ABYSS_D, z=0.5, rim=(200, 170, 255), height=2, noise=0.08))
    parts.append(B(poly([(cx - 22, 36 + bob), (cx + 22, 36 + bob), (cx + 30, 62 + bob), (cx - 30, 62 + bob)]), ABYSS, z=1,
                   rim=(210, 180, 255), height=8, noise=0.08, seed=60))
    parts.append(B(ell(cx - 36, 2 + bob, 72, 52), ABYSS, z=2, rim=(220, 190, 255), height=12, dome=0.5, noise=0.07, seed=61))
    parts.append(B(many(*[lines([(cx - 30 + k * 10, 10 + bob + abs(k - 3) * 2), (cx - 32 + k * 11, 50 + bob)], 1) for k in range(7)]),
                   ABYSS_D, z=2.2, flat=True))
    parts.append(B(ell(cx - 20, 20 + bob, 40, 26), [(10, 4, 18)] * 5, z=2.5, flat=True))
    eye = (250, 226, 255) if attack else (230, 200, 255)
    parts.append(B(many(ell(cx - 13, 28 + bob, 9, 6), ell(cx + 4, 28 + bob, 9, 6)), [eye] * 5, z=3, flat=True, emit=eye))
    # hands conducting
    up = (10 * t) if attack else math.sin(ph) * 3
    parts.append(B(many(lines([(cx - 24, 44 + bob), (cx - 40, 40 + bob - up), (cx - 46, 30 + bob - up)], 4),
                        lines([(cx + 24, 44 + bob), (cx + 40, 40 + bob + up), (cx + 46, 30 + bob + up)], 4)),
                   ABYSS, z=3.5, rim=(220, 190, 255), height=1.5))
    # sigil rings - the song
    for k in range(2):
        rr = 58 + k * 10 + (14 * t if attack else 0)
        col = (220, 190, 255) if not attack else (255, 230, 255)
        rect = (cx - rr, 74 + bob - rr * 0.28, rr * 2, rr * 0.56)
        parts.append(B(lambda s, c, rect=rect, k=k: [pygame.draw.arc(s, c, rect, a0 + ph * (1 - 2 * k), a0 + 0.5 + ph * (1 - 2 * k), 2)
                                                     for a0 in (0, 1.6, 3.2, 4.8)],
                       [col] * 5, z=0.3, flat=True, emit=col))
    return parts


KINDS = {
    "tide_wisp": (tide_wisp, False), "pearl_acolyte": (pearl_acolyte, False), "brine_crawler": (brine_crawler, False),
    "abyssal_chorister": (abyssal_chorister, False), "coral_sentinel": (coral_sentinel, False),
    "drowned_custodian": (drowned_custodian, False), "kelp_stalker": (kelp_stalker, False),
    "shellback_guardian": (shellback_guardian, False), "siren_wraith": (siren_wraith, False),
    "choir_warden": (choir_warden, False),
    "choir_sovereign": (choir_sovereign, True), "coral_leviathan": (coral_leviathan, True),
    "tideglass_warden": (tideglass_warden, True), "driftbell_matriarch": (driftbell_matriarch, True),
    "abyssal_choirmaster": (abyssal_choirmaster, True),
}
MOVES, ATTACKS = 4, 3


def _empty(s):
    return all(s.get_at((x, y))[3] == 0 for y in range(0, s.get_height(), 2) for x in range(0, s.get_width(), 2))


def build(name, pose_fn, boss):
    w, h = (BW, BH) if boss else (64, 64)
    mv, gm, at, ga = [], [], [], []
    for i in range(MOVES):
        s, g = render(pose_fn(i / MOVES, False), w, h)
        mv.append(s)
        gm.append(soft_glow(g))
    for i in range(ATTACKS):
        s, g = render(pose_fn(i / max(1, ATTACKS - 1), True), w, h)
        at.append(s)
        ga.append(soft_glow(g))
    up = lambda s: pygame.transform.scale(s, (s.get_width() * UP, s.get_height() * UP))
    pygame.image.save(up(mv[0]), os.path.join(OUT, f"enemy_{name}.png"))
    pygame.image.save(up(strip(mv)), os.path.join(OUT, f"enemy_{name}_anim.png"))
    pygame.image.save(up(strip(at)), os.path.join(OUT, f"enemy_{name}_attack.png"))
    if not all(_empty(g) for g in gm + ga):  # bioluminescent: an emissive layer for the night
        pygame.image.save(up(strip(gm)), os.path.join(OUT, f"enemy_{name}_glow.png"))
        pygame.image.save(up(strip(ga)), os.path.join(OUT, f"enemy_{name}_glow_attack.png"))
    print(f"painted {name}: {MOVES} move + {ATTACKS} attack frames", flush=True)


def main(names=None):
    pygame.init()
    pygame.display.set_mode((8, 8))
    for name in names or KINDS:
        fn, boss = KINDS[name]
        build(name, fn, boss)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
