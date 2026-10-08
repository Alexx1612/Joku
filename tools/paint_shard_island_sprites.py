"""
Paints the SHARD-island monsters (the land-shattered, ember-charged half of the Reforging
islands) that still used coarse procedural grids: five trash mobs, five elites and their five
mini-bosses. Each gets a still PNG, a 4-frame move strip, a 3-frame attack strip and an emissive
glow layer (embers, magma veins, charged crystal cores - drawn over the darkness at night).

Reuses the part-based painter of tools/paint_night_sprites.py (shaped parts, automatic dome
lighting with a key light + rim, dithered colour ramps, selective outlines). Wholly original.
Colours follow each kind's old grid palette in game/sprites.py ENEMY_GRIDS: charred / ash-grey
stone, warm basalt, ember orange cracks; Thornrock keeps its moss green.

Logical canvas 64x64 for trash / elites, 160x104 for the mini-bosses; saved at 2x.
Run: python tools/paint_shard_island_sprites.py [kind ...]   (writes assets/sprites/v0.2/enemies/)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

import paint_night_sprites as PN  # noqa: E402
from paint_night_sprites import P, ramp, build  # noqa: E402

pygame.init()

# ------------------------------------------------------------- materials (from the old palettes)
CHAR = ramp((14, 10, 10), (96, 74, 62), warm_shadow=(50, 14, 6))           # charred stone
BASALT = ramp((26, 18, 14), (150, 108, 80), warm_shadow=(70, 20, 6))       # warm basalt (C / w)
ASH = ramp((22, 20, 22), (150, 140, 136))                                   # ash grey
RUBBLE = ramp((40, 34, 28), (196, 180, 156))                                # light rubble (B / b)
EMBER = ramp((120, 34, 8), (255, 236, 150))                                 # glowing ember
MAGMA = ramp((140, 40, 8), (255, 214, 96))
FLAME = ramp((170, 60, 16), (255, 246, 200))
CRIMSON = ramp((40, 6, 8), (230, 96, 76))                                   # spite red
CRYSTAL = ramp((90, 34, 10), (255, 214, 150))                               # charged shard crystal
STEELD = ramp((22, 16, 14), (150, 112, 92))                                 # dark armour (o / h)
BONE = ramp((80, 68, 54), (240, 226, 196))
MOSS = ramp((18, 36, 12), (140, 190, 90))                                   # thornrock green
THORN = ramp((30, 22, 12), (150, 120, 80))
MAW = ramp((30, 4, 4), (150, 40, 24))
RIM_WARM = (255, 170, 90)
RIM_COLD = (170, 160, 170)
EMB = (255, 140, 50)          # emissive colours
EMB_HOT = (255, 210, 110)
EMB_RED = (255, 80, 60)


def poly(pts):
    return lambda s, c: pygame.draw.polygon(s, c, [(round(x), round(y)) for x, y in pts])


def ell(x, y, w, h):
    return lambda s, c: pygame.draw.ellipse(s, c, (round(x), round(y), max(1, round(w)), max(1, round(h))))


def circ(x, y, r):
    return lambda s, c: pygame.draw.circle(s, c, (round(x), round(y)), max(1, round(r)))


def lines(pts, w=1):
    return lambda s, c: pygame.draw.lines(s, c, False, [(round(x), round(y)) for x, y in pts], w)


def multi(*fns):
    def f(s, c):
        for fn in fns:
            fn(s, c)
    return f


def cracks(pts_list, w=1):
    return lambda s, c: [pygame.draw.lines(s, c, False, [(round(x), round(y)) for x, y in pts], w)
                         for pts in pts_list]


# =============================================================== trash (64x64)
def ember_wisp(t, attack):
    """A living flame: a teardrop of fire round a white-hot core, two cinder eyes, sparks trailing."""
    W = H = 64
    ph = t * math.tau
    fl = math.sin(ph * 2) * 2
    grow = 1.0 + (0.35 * t if attack else 0.0)
    cx, cy = 32, 36
    parts = []
    tail = [(cx - 14 * grow, cy + 2), (cx - 22 * grow + fl, cy - 6), (cx - 12 * grow, cy - 4)]
    parts.append(P(W, H, poly(tail), EMBER, z=0, flat=True, emit=EMB))
    OUTER = ramp((110, 30, 8), (255, 160, 70))
    body = [(cx - 13 * grow, cy + 8), (cx - 15 * grow, cy - 4), (cx - 10 * grow, cy - 2),
            (cx - 9 * grow + fl, cy - 16 * grow), (cx - 3, cy - 10 * grow), (cx + 1 + fl, cy - 27 * grow),
            (cx + 5, cy - 12 * grow), (cx + 11 * grow - fl, cy - 19 * grow), (cx + 11 * grow, cy - 4),
            (cx + 15 * grow, cy - 8 * grow + fl), (cx + 13 * grow, cy + 8), (cx, cy + 14 * grow)]
    parts.append(P(W, H, poly(body), OUTER, z=1, height=5, dome=0.5, emit=EMB, noise=0.08, seed=11))
    mid = [(cx - 9, cy + 8), (cx - 9, cy - 2), (cx - 4, cy - 8 * grow), (cx + fl * 0.5, cy - 18 * grow),
           (cx + 5, cy - 7 * grow), (cx + 9, cy - 1), (cx + 9, cy + 8), (cx, cy + 11)]
    parts.append(P(W, H, poly(mid), ramp((220, 120, 30), (255, 220, 120)), z=1.5, flat=True, emit=EMB_HOT))
    core = [(cx - 5, cy + 7), (cx - 4, cy + 1), (cx, cy - 6 * grow + fl * 0.5), (cx + 4, cy + 1), (cx + 5, cy + 7),
            (cx, cy + 9)]
    parts.append(P(W, H, poly(core), [(255, 250, 220)] * 5, z=2, flat=True, emit=EMB_HOT))
    eyes = multi(ell(cx - 5, cy - 2, 3, 4 if not attack else 2), ell(cx + 3, cy - 2, 3, 4 if not attack else 2))
    parts.append(P(W, H, eyes, [(60, 18, 8)] * 5, z=3, flat=True))
    if attack:
        parts.append(P(W, H, ell(cx - 3, cy + 3, 6, 3 + 3 * t), [(90, 20, 6)] * 5, z=3, flat=True))
    sparks = [circ(cx - 18 + k * 9 + math.sin(ph + k) * 3, cy + 16 + (k % 2) * 4 - (t * 6 % 6), 1) for k in range(5)]
    parts.append(P(W, H, multi(*sparks), EMBER, z=4, flat=True, emit=EMB_HOT))
    return parts


def fury_shard(t, attack):
    """A furious floating shard of the shattered land: a charred rock shell split open around a
    blazing crystal core, jagged fragments orbiting it and a snarl cracked into its face."""
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 2
    spread = 6 * t if attack else 0
    cx, cy = 32, 30 + bob
    parts = []
    for k in range(4):  # orbiting chips (behind and in front)
        a = ph + k * math.pi / 2
        r = 22 + spread
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r * 0.55 + 4
        chip = [(x - 3, y), (x, y - 4), (x + 3, y - 1), (x + 1, y + 3)]
        parts.append(P(W, H, poly(chip), CHAR, z=0 if math.sin(a) < 0 else 5, rim=RIM_WARM, height=2))
    shell = [(cx - 15, cy + 6), (cx - 17, cy - 6), (cx - 9, cy - 18), (cx + 2, cy - 22), (cx + 13, cy - 14),
             (cx + 17, cy - 2), (cx + 12, cy + 12), (cx + 2, cy + 18), (cx - 8, cy + 15)]
    parts.append(P(W, H, poly(shell), CHAR, z=1, rim=RIM_WARM, height=7, noise=0.12, seed=21))
    spikes = []
    for k in range(5):
        a = -math.pi / 2 + (k - 2) * 0.55
        L = 10 + spread * 1.4 + (k % 2) * 3
        bx, by = cx + math.cos(a) * 12, cy + math.sin(a) * 12
        tx, ty = cx + math.cos(a) * (12 + L), cy + math.sin(a) * (12 + L)
        nx, ny = -math.sin(a) * 3, math.cos(a) * 3
        spikes.append(poly([(bx + nx, by + ny), (tx, ty), (bx - nx, by - ny)]))
    parts.append(P(W, H, multi(*spikes), CRYSTAL, z=2, height=2, emit=EMB, dome=0.6))
    parts.append(P(W, H, cracks([[(cx - 9, cy - 10), (cx - 3, cy - 2), (cx - 7, cy + 8)],
                                 [(cx + 6, cy - 14), (cx + 3, cy - 3), (cx + 10, cy + 6)]], 2),
                   EMBER, z=3, flat=True, emit=EMB))
    parts.append(P(W, H, ell(cx - 6, cy - 4, 12, 10), CRYSTAL, z=3.5, height=3, emit=EMB_HOT, dome=0.7))
    snarl = poly([(cx - 7, cy + 7), (cx + 7, cy + 7), (cx + 4, cy + 10 + (3 * t if attack else 0)), (cx - 4, cy + 10)])
    parts.append(P(W, H, snarl, MAW, z=4, flat=True))
    parts.append(P(W, H, multi(poly([(cx - 9, cy - 9), (cx - 3, cy - 6), (cx - 8, cy - 5)]),
                               poly([(cx + 9, cy - 9), (cx + 3, cy - 6), (cx + 8, cy - 5)])),
                   [(255, 245, 200)] * 5, z=4.5, flat=True, emit=EMB_HOT))
    return parts


def rubble_crawler(t, attack):
    """A scuttling heap of rubble on six stubby stone legs, two ember eyes in the cracks and one
    big club claw it lobs pebbles with."""
    W = H = 64
    ph = t * math.tau
    parts = []
    for k in range(3):  # far legs
        lx = 18 + k * 12
        sw = math.sin(ph + k * 2.1) * 3
        parts.append(P(W, H, lines([(lx, 44), (lx - 4 + sw, 52), (lx - 2 + sw, 60)], 3), ASH, z=0, height=1.5))
    body = [(8, 46), (10, 36), (18, 28), (30, 24), (44, 27), (54, 34), (56, 44), (46, 50), (22, 51)]
    parts.append(P(W, H, poly(body), RUBBLE, z=1, rim=RIM_COLD, height=7, noise=0.14, seed=31))
    for (x, y, r) in ((20, 32, 6), (32, 28, 7), (44, 33, 6), (27, 40, 5), (40, 42, 5)):  # boulders in the heap
        parts.append(P(W, H, circ(x, y, r), RUBBLE, z=2, rim=RIM_COLD, height=3, noise=0.12, seed=x + y))
    parts.append(P(W, H, cracks([[(23, 36), (28, 39)], [(36, 35), (39, 39)]], 1), EMBER, z=2.5, flat=True, emit=EMB))
    for k in range(3):  # near legs
        lx = 20 + k * 12
        sw = math.sin(ph + k * 2.1 + math.pi) * 3
        parts.append(P(W, H, lines([(lx, 46), (lx + 3 + sw, 54), (lx + 1 + sw, 61)], 3), RUBBLE, z=3,
                       height=1.5, rim=RIM_COLD))
    parts.append(P(W, H, multi(circ(50, 38, 2), circ(54, 37, 2)), [(255, 160, 80)] * 5, z=4, flat=True, emit=EMB_HOT))
    raise_ = (12 * t) if attack else math.sin(ph) * 1.5
    claw = [(48, 40), (56, 36 - raise_), (62, 30 - raise_ * 1.2), (60, 24 - raise_), (54, 27 - raise_), (50, 33)]
    parts.append(P(W, H, poly(claw), RUBBLE, z=5, rim=RIM_COLD, height=3, noise=0.1, seed=33))
    if attack:
        parts.append(P(W, H, circ(60, 20 - raise_, 3), ASH, z=6, height=2, rim=RIM_COLD))
    return parts


def spite_spirit(t, attack):
    """A spirit of pure spite: a hooded crimson wraith with a whipping tail, burning eyes and a
    mouth stretched in a scream."""
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 2
    parts = []
    tail = []
    for k in range(5):
        y = 40 + k * 4 + bob
        off = math.sin(ph * 2 + k * 0.9) * (4 + k)
        tail.append((26 - k * 2 + off, y))
    tail_poly = [(18, 38 + bob)] + tail + [(30 + math.sin(ph * 2 + 4) * 6, 60 + bob), (40, 40 + bob)]
    parts.append(P(W, H, poly(tail_poly), CRIMSON, z=0, height=3, noise=0.1, seed=41, alpha=235))
    hood = [(16, 40 + bob), (18, 22 + bob), (28, 10 + bob), (40, 10 + bob), (48, 20 + bob), (48, 40 + bob),
            (40, 46 + bob), (24, 46 + bob)]
    parts.append(P(W, H, poly(hood), CRIMSON, z=1, rim=(255, 150, 130), height=6, noise=0.08, seed=42))
    parts.append(P(W, H, ell(23, 18 + bob, 20, 20), [(20, 4, 6)] * 5, z=2, flat=True))  # the dark inside of the hood
    eye_h = 2 if attack else 3
    parts.append(P(W, H, multi(poly([(24, 22 + bob), (30, 25 + bob), (29, 25 + bob + eye_h), (24, 24 + bob + eye_h)]),
                               poly([(40, 22 + bob), (34, 25 + bob), (35, 25 + bob + eye_h), (40, 24 + bob + eye_h)])),
                   [(255, 200, 150)] * 5,
                   z=3, flat=True, emit=EMB_RED))
    mouth = 3 + (6 * t if attack else math.sin(ph) * 1)
    parts.append(P(W, H, ell(28, 30 + bob, 8, mouth), [(255, 90, 60)] * 5, z=3, flat=True, emit=EMB_RED))
    if attack:
        a = t
        arms = multi(lines([(18, 28 + bob), (8 - 4 * a, 22 + bob - 6 * a), (4 - 4 * a, 14 + bob - 6 * a)], 2),
                     lines([(46, 28 + bob), (56 + 4 * a, 22 + bob - 6 * a), (60 + 3 * a, 14 + bob - 6 * a)], 2))
    else:
        arms = multi(lines([(18, 30 + bob), (12, 38 + bob), (12, 44 + bob)], 2),
                     lines([(46, 30 + bob), (52, 38 + bob), (52, 44 + bob)], 2))
    parts.append(P(W, H, arms, CRIMSON, z=4, height=1.2, rim=(255, 150, 130)))
    return parts


# =============================================================== elites (64x64)
def shard_sentinel(t, attack):
    """A hovering monolith of the old land, carved with glowing runes, one great crystal eye in
    its face and three shards orbiting it - on the attack they spear outward."""
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 1.5
    parts = []
    out = 10 * t if attack else 0
    for k in range(3):
        a = ph * 0.5 + k * math.tau / 3
        r = 24 + out
        x, y = 32 + math.cos(a) * r, 34 + math.sin(a) * r * 0.45
        sh = [(x, y - 7), (x + 3, y), (x, y + 6), (x - 3, y)]
        parts.append(P(W, H, poly(sh), CRYSTAL, z=0 if math.sin(a) < 0 else 6, height=2, emit=EMB, dome=0.6))
    body = [(20, 54 + bob), (18, 18 + bob), (24, 6 + bob), (40, 6 + bob), (46, 18 + bob), (44, 54 + bob)]
    parts.append(P(W, H, poly(body), BASALT, z=1, rim=RIM_WARM, height=8, noise=0.1, seed=51))
    parts.append(P(W, H, poly([(22, 58 + bob), (32, 62 + bob), (42, 58 + bob), (40, 52 + bob), (24, 52 + bob)]),
                   CHAR, z=1.5, height=3, rim=RIM_WARM))
    runes = cracks([[(24, 36 + bob), (28, 40 + bob), (24, 44 + bob)], [(40, 36 + bob), (36, 40 + bob), (40, 44 + bob)],
                    [(26, 48 + bob), (38, 48 + bob)], [(28, 12 + bob), (36, 12 + bob)]], 1)
    parts.append(P(W, H, runes, EMBER, z=2, flat=True, emit=EMB))
    eye = 5 + (2 * t if attack else 0)
    parts.append(P(W, H, ell(32 - eye, 22 + bob - eye * 0.6, eye * 2, eye * 1.3), [(30, 10, 6)] * 5, z=2.5, flat=True))
    parts.append(P(W, H, ell(32 - eye * 0.6, 22 + bob - eye * 0.4, eye * 1.2, eye * 0.8), CRYSTAL, z=3, height=2,
                   emit=EMB_HOT, dome=0.7))
    return parts


def echo_knight(t, attack):
    """A knight of cracked stone plate with a burning visor slit and a long blade - and the faint
    echo of itself one step behind, the way the shattered land remembers."""
    W = H = 64
    ph = t * math.tau
    step = math.sin(ph) * 3
    lunge = 8 * t if attack else 0
    parts = []

    def knight(dx, z0, alpha, emit_ok):
        X = lambda x: x + dx + lunge
        ps = []
        ps.append(P(W, H, multi(lines([(X(28), 42), (X(26) - step, 52), (X(25) - step, 61)], 4),
                                lines([(X(36), 42), (X(38) + step, 52), (X(39) + step, 61)], 4)),
                    STEELD, z=z0, height=2, rim=RIM_WARM, alpha=alpha))
        torso = [(X(24), 42), (X(22), 26), (X(26), 18), (X(38), 18), (X(42), 26), (X(40), 42)]
        ps.append(P(W, H, poly(torso), STEELD, z=z0 + 1, rim=RIM_WARM, height=6, noise=0.1, seed=61, alpha=alpha))
        ps.append(P(W, H, poly([(X(26), 18), (X(26), 8), (X(32), 4), (X(38), 8), (X(38), 18)]), STEELD, z=z0 + 2,
                    rim=RIM_WARM, height=4, alpha=alpha))
        ps.append(P(W, H, poly([(X(28), 11), (X(37), 11), (X(37), 13), (X(28), 13)]), [(255, 220, 160)] * 5,
                    z=z0 + 3, flat=True, emit=EMB_HOT if emit_ok else None, alpha=alpha))
        ps.append(P(W, H, cracks([[(X(30), 22), (X(33), 30), (X(29), 38)]], 1), EMBER, z=z0 + 2.5, flat=True,
                    emit=EMB if emit_ok else None, alpha=alpha))
        if attack:
            blade = [(X(40), 28), (X(62), 26 - 2 * t), (X(63), 28 - 2 * t), (X(41), 31)]
        else:
            blade = [(X(40), 30), (X(46), 54), (X(44), 55), (X(38), 31)]
        ps.append(P(W, H, poly(blade), ramp((60, 50, 46), (250, 230, 210)), z=z0 + 4, height=1.5, rim=(255, 250, 230),
                    alpha=alpha))
        ps.append(P(W, H, circ(X(40), 30, 3), STEELD, z=z0 + 4.5, height=2, alpha=alpha))
        return ps

    parts += knight(-7 - (4 * t if attack else 0), 0, 90, False)   # the echo, faded, a step behind
    parts += knight(0, 10, 255, True)
    return parts


def shattered_golem(t, attack):
    """A golem that never quite held together: body, shoulders, head and fists hover apart with
    molten light showing in every gap between them."""
    W = H = 64
    ph = t * math.tau
    gap = 2 + math.sin(ph) * 1.5 + (4 * t if attack else 0)
    parts = []
    parts.append(P(W, H, ell(20, 20, 24, 30), MAGMA, z=0, flat=True, emit=EMB))   # the glow behind the gaps
    legs = multi(poly([(20, 50), (28, 50), (27, 61), (19, 61)]), poly([(36, 50), (44, 50), (45, 61), (37, 61)]))
    parts.append(P(W, H, legs, BASALT, z=1, rim=RIM_WARM, height=3, noise=0.12))
    parts.append(P(W, H, poly([(18, 48 - gap * 0.3), (16, 28), (26, 22), (38, 22), (48, 28), (46, 48 - gap * 0.3),
                               (32, 52)]), BASALT, z=2, rim=RIM_WARM, height=6, noise=0.13, seed=71))
    sh_y = 22 - gap
    parts.append(P(W, H, multi(poly([(8, sh_y + 6), (12, sh_y - 2), (22, sh_y - 2), (24, sh_y + 6)]),
                               poly([(40, sh_y + 6), (42, sh_y - 2), (52, sh_y - 2), (56, sh_y + 6)])),
                   BASALT, z=3, rim=RIM_WARM, height=3, noise=0.1, seed=72))
    hy = 8 - gap
    parts.append(P(W, H, poly([(26, hy + 12), (25, hy + 2), (32, hy - 2), (39, hy + 2), (38, hy + 12)]), BASALT, z=4,
                   rim=RIM_WARM, height=4))
    parts.append(P(W, H, multi(circ(29, hy + 6, 1.5), circ(35, hy + 6, 1.5)), [(255, 230, 160)] * 5, z=5, flat=True,
                   emit=EMB_HOT))
    fx = 6 * t if attack else 0
    fists = multi(ell(4 - fx, 34 + gap, 13, 13), ell(47 + fx, 34 + gap, 13, 13))
    parts.append(P(W, H, fists, BASALT, z=6, rim=RIM_WARM, height=4, noise=0.12, seed=73))
    parts.append(P(W, H, cracks([[(28, 30), (31, 38), (27, 44)], [(38, 32), (36, 42)]], 1), EMBER, z=6.5, flat=True,
                   emit=EMB))
    return parts


def fracture_hound(t, attack):
    """A hound of stone plates split along the spine by a glowing fissure; ember eyes, heavy jaws,
    a gallop that shakes chips off it."""
    W = H = 64
    ph = t * math.tau
    parts = []
    gal = math.sin(ph) * 5
    lunge = 6 * t if attack else 0
    X = lambda x: x + lunge
    parts.append(P(W, H, multi(lines([(X(16), 40), (X(10) - gal, 50), (X(12) - gal, 60)], 4),
                               lines([(X(42), 40), (X(48) + gal, 50), (X(46) + gal, 60)], 4)),
                   ramp((20, 12, 10), (90, 60, 46)), z=0, height=2))
    body = [(X(6), 36), (X(12), 26), (X(30), 22), (X(46), 24), (X(52), 32), (X(48), 42), (X(30), 44), (X(12), 44)]
    parts.append(P(W, H, poly(body), ramp((26, 16, 12), (150, 100, 76)), z=1, rim=RIM_WARM, height=6, noise=0.14, seed=81))
    plates = [poly([(X(12 + k * 8), 26 - (k % 2)), (X(19 + k * 8), 24 - (k % 2)), (X(18 + k * 8), 32), (X(12 + k * 8), 32)])
              for k in range(4)]
    parts.append(P(W, H, multi(*plates), ramp((40, 26, 20), (180, 128, 96)), z=2, rim=RIM_WARM, height=2.5))
    parts.append(P(W, H, lines([(X(10), 27), (X(20), 24), (X(30), 25), (X(40), 23), (X(46), 26)], 2), EMBER, z=3,
                   flat=True, emit=EMB))
    jaw = 6 * t if attack else 1 + math.sin(ph) * 0.8
    head = [(X(44), 24), (X(54), 20), (X(62), 25), (X(62), 30), (X(52), 32), (X(46), 32)]
    parts.append(P(W, H, poly(head), ramp((26, 16, 12), (150, 100, 76)), z=4, rim=RIM_WARM, height=4, seed=82))
    parts.append(P(W, H, poly([(X(48), 32), (X(62), 31), (X(61), 33 + jaw), (X(50), 35 + jaw)]),
                   ramp((20, 12, 10), (110, 70, 52)), z=4.5, height=1.5))
    parts.append(P(W, H, multi(*[poly([(X(51 + k * 3), 31), (X(52 + k * 3), 31), (X(51.5 + k * 3), 33)]) for k in range(4)]),
                   BONE, z=5, flat=True))
    parts.append(P(W, H, circ(X(55), 24, 1.5), [(255, 220, 140)] * 5, z=5, flat=True, emit=EMB_HOT))
    parts.append(P(W, H, multi(lines([(X(18), 42), (X(22) + gal, 52), (X(20) + gal, 61)], 4),
                               lines([(X(38), 42), (X(34) - gal, 52), (X(37) - gal, 61)], 4)),
                   ramp((26, 16, 12), (150, 100, 76)), z=6, rim=RIM_WARM, height=2))
    return parts


def stone_revenant(t, attack):
    """An undead tomb-priest carved from grave stone: a hooded stone robe that never touches the
    ground, a skull-like face, chains, and a spiralling rune of embers when it casts."""
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 2
    parts = []
    if attack:
        ring = []
        for k in range(10):
            a = ph * 0.3 + k * math.tau / 10 + t * 2
            r = 24 - k * 1.2
            ring.append(circ(32 + math.cos(a) * r, 30 + math.sin(a) * r * 0.6, 1.5))
        parts.append(P(W, H, multi(*ring), EMBER, z=0, flat=True, emit=EMB))
    robe = [(18, 54 + bob), (20, 30 + bob), (24, 16 + bob), (40, 16 + bob), (44, 30 + bob), (46, 54 + bob)]
    hem = [(18 + k * 4, 54 + bob + (3 if k % 2 else 0) + math.sin(ph + k) * 1.5) for k in range(8)]
    parts.append(P(W, H, poly(robe + hem[::-1]), ramp((22, 18, 16), (140, 116, 100)), z=1, rim=RIM_COLD, height=6,
                   noise=0.12, seed=91))
    parts.append(P(W, H, poly([(22, 22 + bob), (24, 8 + bob), (32, 4 + bob), (40, 8 + bob), (42, 22 + bob)]),
                   ramp((22, 18, 16), (140, 116, 100)), z=2, rim=RIM_COLD, height=4))
    parts.append(P(W, H, ell(26, 10 + bob, 12, 13), BONE, z=3, height=3, rim=(255, 240, 220)))
    parts.append(P(W, H, multi(ell(27, 14 + bob, 4, 3), ell(33, 14 + bob, 4, 3)), [(255, 160, 80)] * 5, z=4, flat=True,
                   emit=EMB_HOT))
    parts.append(P(W, H, lines([(28, 20 + bob), (36, 20 + bob)], 1), [(40, 30, 26)] * 5, z=4, flat=True))
    chain = [circ(22 + k * 2.6, 36 + bob + math.sin(k * 0.9) * 2, 1.2) for k in range(8)]
    parts.append(P(W, H, multi(*chain), ramp((30, 30, 34), (190, 190, 200)), z=5, height=1))
    up = 10 * t if attack else 0
    hands = multi(lines([(20, 30 + bob), (12, 36 + bob - up), (10, 40 + bob - up * 1.4)], 3),
                  lines([(44, 30 + bob), (52, 36 + bob - up), (54, 40 + bob - up * 1.4)], 3))
    parts.append(P(W, H, hands, ramp((22, 18, 16), (140, 116, 100)), z=6, height=1.5, rim=RIM_COLD))
    parts.append(P(W, H, cracks([[(28, 30 + bob), (32, 38 + bob), (36, 30 + bob)]], 1), EMBER, z=6.5, flat=True,
                   emit=EMB))
    return parts


def cinder_warden(t, attack):
    """The islands' fire-jailer: dark red plate armour, a brazier for a head with flames pouring
    out of the visor, and a swinging censer of coals."""
    W = H = 64
    ph = t * math.tau
    step = math.sin(ph) * 3
    parts = []
    ARM = ramp((30, 8, 4), (200, 80, 40))
    parts.append(P(W, H, multi(lines([(26, 42), (24 - step, 52), (23 - step, 61)], 4),
                               lines([(36, 42), (38 + step, 52), (39 + step, 61)], 4)), ARM, z=0, height=2, rim=RIM_WARM))
    parts.append(P(W, H, poly([(22, 44), (20, 26), (24, 18), (40, 18), (44, 26), (42, 44)]), ARM, z=1, rim=RIM_WARM,
                   height=6, noise=0.1, seed=101))
    parts.append(P(W, H, poly([(18, 26), (20, 19), (28, 18), (26, 26)]), ARM, z=1.5, rim=RIM_WARM, height=3))
    flare = 6 * t if attack else math.sin(ph * 2) * 2
    fire = [(23, 14), (25, 4 - flare), (28, 9), (31, -2 - flare), (34, 8), (38, 2 - flare), (41, 14)]
    parts.append(P(W, H, poly(fire), ramp((200, 70, 16), (255, 200, 90)), z=2, flat=True, emit=EMB_HOT))
    parts.append(P(W, H, poly([(23, 18), (22, 10), (42, 10), (41, 18)]), ARM, z=3, rim=RIM_WARM, height=3))
    parts.append(P(W, H, poly([(26, 13), (38, 13), (38, 15), (26, 15)]), [(255, 230, 140)] * 5, z=4, flat=True,
                   emit=EMB_HOT))
    parts.append(P(W, H, cracks([[(28, 24), (32, 32), (30, 40)], [(36, 26), (38, 34)]], 1), EMBER, z=4, flat=True, emit=EMB))
    sw = (-1 + 2 * t) * 0.9 if attack else math.sin(ph) * 0.35
    hx, hy = 46, 28
    cx_, cy_ = hx + math.sin(sw) * 14, hy + math.cos(sw) * 14
    parts.append(P(W, H, lines([(hx, hy), (cx_, cy_)], 1), ramp((30, 30, 34), (190, 190, 200)), z=5, flat=True))
    parts.append(P(W, H, circ(cx_, cy_ + 2, 4), ramp((26, 20, 18), (150, 120, 100)), z=6, height=2, rim=RIM_WARM))
    parts.append(P(W, H, circ(cx_, cy_ + 1, 2), FLAME, z=7, flat=True, emit=EMB_HOT))
    return parts


# =============================================================== mini-bosses (160x104)
BW, BH = 160, 104


def cinder_colossus(t, attack):
    """A walking volcano: basalt plates over a molten chest, magma running in every seam, a crown
    of flame, fists like boulders - on the attack one rises for the Magma Slam."""
    W, H = BW, BH
    ph = t * math.tau
    br = math.sin(ph) * 1.5
    parts = []
    lift = 26 * t if attack else 0
    parts.append(P(W, H, multi(poly([(54, 76), (70, 76), (68, 102), (50, 102)]),
                               poly([(90, 76), (106, 76), (110, 102), (92, 102)])), BASALT, z=0, rim=RIM_WARM, height=6,
                   noise=0.12, seed=111))
    torso = [(44, 78), (38, 46 - br), (50, 26 - br), (80, 18 - br), (110, 26 - br), (122, 46 - br), (116, 78), (80, 86)]
    parts.append(P(W, H, poly(torso), BASALT, z=1, rim=RIM_WARM, height=14, noise=0.13, seed=112))
    plates = [poly([(48 + k * 13, 34 - br + (k % 2) * 3), (60 + k * 13, 32 - br), (62 + k * 13, 44 - br),
                    (50 + k * 13, 46 - br)]) for k in range(5)]
    parts.append(P(W, H, multi(*plates), CHAR, z=2, rim=RIM_WARM, height=4, noise=0.1, seed=113))
    parts.append(P(W, H, ell(66, 46 - br, 28, 22), MAGMA, z=2.5, height=5, emit=EMB_HOT, dome=0.7))
    veins = cracks([[(52, 50), (60, 60), (56, 72)], [(108, 50), (100, 62), (104, 74)], [(80, 66), (78, 80)],
                    [(66, 30), (72, 38)], [(94, 30), (88, 38)]], 2)
    parts.append(P(W, H, veins, MAGMA, z=3, flat=True, emit=EMB))
    hx = 80
    parts.append(P(W, H, poly([(hx - 12, 22 - br), (hx - 10, 10 - br), (hx, 6 - br), (hx + 10, 10 - br), (hx + 12, 22 - br)]),
                   BASALT, z=4, rim=RIM_WARM, height=5))
    crown = [(hx - 11, 9 - br)] + [(hx - 10 + k * 4, (6 if k % 2 else 0) - br - (math.sin(ph * 2 + k) * 2)) for k in range(6)] \
        + [(hx + 12, 9 - br)]
    parts.append(P(W, H, poly(crown), ramp((200, 70, 16), (255, 200, 90)), z=3.5, flat=True, emit=EMB_HOT))
    parts.append(P(W, H, multi(poly([(hx - 7, 14 - br), (hx - 2, 15 - br), (hx - 6, 17 - br)]),
                               poly([(hx + 7, 14 - br), (hx + 2, 15 - br), (hx + 6, 17 - br)])),
                   [(255, 240, 180)] * 5, z=5, flat=True, emit=EMB_HOT))
    parts.append(P(W, H, multi(lines([(42, 40), (28, 58), (24, 70)], 9),
                               lines([(118, 40), (132, 56 - lift), (136, 66 - lift * 1.4)], 9)),
                   BASALT, z=6, rim=RIM_WARM, height=4, noise=0.12, seed=114))
    parts.append(P(W, H, multi(ell(12, 64, 24, 22), ell(124, 60 - lift * 1.4, 26, 24)), BASALT, z=7, rim=RIM_WARM,
                   height=6, noise=0.14, seed=115))
    parts.append(P(W, H, cracks([[(18, 72), (26, 76)], [(132, 68 - lift * 1.4), (140, 74 - lift * 1.4)]], 1), MAGMA,
                   z=7.5, flat=True, emit=EMB))
    return parts


def rubble_warlord(t, attack):
    """A charging war-beast of boulders: a hunched rock behemoth on four pillar legs, a ram-horn of
    raw stone, tusks, a back of jagged slabs flying tattered banners - it charges head down."""
    W, H = BW, BH
    ph = t * math.tau
    gal = math.sin(ph) * 6
    dip = 10 * t if attack else 0
    lunge = 14 * t if attack else 0
    X = lambda x: x + lunge
    parts = []
    LEG = ramp((22, 14, 10), (120, 84, 60))
    parts.append(P(W, H, multi(poly([(X(30), 66), (X(42), 66), (X(40) - gal, 102), (X(28) - gal, 102)]),
                               poly([(X(96), 66), (X(108), 66), (X(110) + gal, 102), (X(98) + gal, 102)])),
                   LEG, z=0, height=5, noise=0.1))
    body = [(X(16), 70), (X(20), 44), (X(40), 26), (X(80), 20), (X(112), 28), (X(126), 46 + dip * 0.3),
            (X(122), 72), (X(80), 78), (X(40), 78)]
    parts.append(P(W, H, poly(body), ramp((30, 20, 14), (176, 124, 92)), z=1, rim=RIM_WARM, height=13, noise=0.14,
                   seed=121))
    for k in range(6):
        x = 28 + k * 15
        parts.append(P(W, H, poly([(X(x), 30 - (k % 2) * 2), (X(x + 6), 12 + (k % 3) * 3), (X(x + 13), 28)]),
                       CHAR, z=2, rim=RIM_WARM, height=4, noise=0.1, seed=122 + k))
    for k, x in enumerate((36, 76)):
        flap = math.sin(ph + k) * 4
        parts.append(P(W, H, lines([(X(x), 26), (X(x), 0)], 2), ramp((30, 20, 10), (140, 100, 60)), z=1.5, flat=True))
        parts.append(P(W, H, poly([(X(x), 1), (X(x + 16 + flap), 4), (X(x + 12 + flap), 9), (X(x + 17 + flap), 14), (X(x), 12)]),
                       ramp((50, 8, 4), (200, 60, 30)), z=1.6, height=2, noise=0.15))
    parts.append(P(W, H, cracks([[(X(50), 50), (X(60), 58)], [(X(84), 44), (X(92), 56)]], 2), EMBER, z=3, flat=True, emit=EMB))
    hy = 40 + dip
    head = [(X(110), hy - 6), (X(132), hy - 10), (X(150), hy), (X(148), hy + 16), (X(128), hy + 22), (X(112), hy + 18)]
    parts.append(P(W, H, poly(head), ramp((30, 20, 14), (176, 124, 92)), z=4, rim=RIM_WARM, height=8, seed=128))
    parts.append(P(W, H, poly([(X(136), hy - 8), (X(158), hy - 22 + dip * 0.6), (X(148), hy - 2)]), RUBBLE, z=5,
                   rim=RIM_COLD, height=4))
    parts.append(P(W, H, poly([(X(140), hy + 16), (X(156), hy + 14), (X(146), hy + 22)]), BONE, z=5, height=2))
    parts.append(P(W, H, circ(X(136), hy + 3, 2.5), [(255, 200, 100)] * 5, z=6, flat=True, emit=EMB_HOT))
    parts.append(P(W, H, multi(poly([(X(50), 70), (X(62), 70), (X(64) + gal, 102), (X(52) + gal, 102)]),
                               poly([(X(116), 70), (X(126), 70), (X(124) - gal, 102), (X(112) - gal, 102)])),
                   ramp((30, 20, 14), (176, 124, 92)), z=6.5, rim=RIM_WARM, height=5, noise=0.12))
    return parts


def ashreach_revenant(t, attack):
    """A towering lich of ash: a tattered cloak that frays into drifting cinders, a skeletal face
    under a crown of embers, long bone hands - and souls circling it, faster as it casts."""
    W, H = BW, BH
    ph = t * math.tau
    bob = math.sin(ph) * 2
    parts = []
    spin = ph + (t * 3 if attack else 0)
    orbs = []
    for k in range(6):
        a = spin + k * math.tau / 6
        orbs.append((80 + math.cos(a) * 62, 52 + math.sin(a) * 22 + bob, math.sin(a)))
    for (x, y, d) in orbs:
        if d < 0:
            parts.append(P(W, H, circ(x, y, 4), EMBER, z=0, height=2, emit=EMB, dome=0.6))
    cloak = [(46, 100), (52, 50 + bob), (62, 26 + bob), (80, 18 + bob), (98, 26 + bob), (108, 50 + bob), (114, 100)]
    hem = [(46 + k * 8.5, 100 - (6 if k % 2 else 0) + math.sin(ph + k) * 2) for k in range(9)]
    parts.append(P(W, H, poly(cloak + hem[::-1]), ASH, z=1, rim=RIM_WARM, height=12, noise=0.15, seed=131))
    parts.append(P(W, H, cracks([[(60, 60 + bob), (66, 80 + bob)], [(98, 58 + bob), (94, 84 + bob)],
                                 [(80, 50 + bob), (78, 70 + bob)]], 1), EMBER, z=2, flat=True, emit=EMB))
    parts.append(P(W, H, poly([(64, 34 + bob), (66, 14 + bob), (80, 6 + bob), (94, 14 + bob), (96, 34 + bob)]), ASH, z=2.5,
                   rim=RIM_WARM, height=6))
    parts.append(P(W, H, ell(70, 12 + bob, 20, 22), BONE, z=3, height=4, rim=(255, 240, 220), noise=0.06))
    parts.append(P(W, H, multi(ell(72, 18 + bob, 6, 5), ell(82, 18 + bob, 6, 5)), [(30, 6, 4)] * 5, z=4, flat=True))
    parts.append(P(W, H, multi(circ(75, 20 + bob, 1.5), circ(85, 20 + bob, 1.5)), [(255, 200, 120)] * 5, z=5, flat=True,
                   emit=EMB_HOT))
    parts.append(P(W, H, multi(*[lines([(73 + k * 3, 28 + bob), (73 + k * 3, 31 + bob)], 1) for k in range(5)]), BONE,
                   z=4.5, flat=True))
    crown = [(68, 10 + bob)] + [(70 + k * 4, (6 if k % 2 else 0) + bob) for k in range(6)] + [(92, 10 + bob)]
    parts.append(P(W, H, poly(crown), ramp((200, 70, 16), (255, 200, 90)), z=4.6, flat=True, emit=EMB_HOT))
    up = 22 * t if attack else 0
    arms = multi(lines([(54, 46 + bob), (36, 58 + bob - up), (24, 54 + bob - up * 1.3)], 4),
                 lines([(106, 46 + bob), (124, 58 + bob - up), (136, 54 + bob - up * 1.3)], 4))
    parts.append(P(W, H, arms, ASH, z=5, rim=RIM_WARM, height=2))
    fingers = []
    for (hx, hy) in ((24, 54 + bob - up * 1.3), (136, 54 + bob - up * 1.3)):
        for k in (-1, 0, 1):
            fingers.append(lines([(hx, hy), (hx + k * 4, hy - 7), (hx + k * 5, hy - 10)], 1))
    parts.append(P(W, H, multi(*fingers), BONE, z=6, flat=True))
    for (x, y, d) in orbs:
        if d >= 0:
            parts.append(P(W, H, circ(x, y, 4), EMBER, z=7, height=2, emit=EMB, dome=0.6))
    return parts


def thornrock_colossus(t, attack):
    """A cliff that got up: a mossy rock giant wrapped in thorn vines, flowering embers in its
    cracks, a club-arm of root and stone - Quake slams it down."""
    W, H = BW, BH
    ph = t * math.tau
    br = math.sin(ph) * 1.5
    lift = 24 * t if attack else 0
    parts = []
    ROCK = ramp((26, 22, 18), (176, 150, 118))
    parts.append(P(W, H, multi(poly([(52, 76), (70, 76), (66, 102), (48, 102)]),
                               poly([(90, 76), (108, 76), (112, 102), (94, 102)])), ROCK, z=0, height=6, rim=RIM_COLD,
                   noise=0.12))
    torso = [(40, 80), (36, 48 - br), (48, 26 - br), (80, 16 - br), (112, 26 - br), (124, 48 - br), (120, 80), (80, 88)]
    parts.append(P(W, H, poly(torso), ROCK, z=1, rim=RIM_COLD, height=14, noise=0.14, seed=141))
    parts.append(P(W, H, multi(ell(44, 20 - br, 30, 14), ell(84, 14 - br, 34, 14), ell(60, 60, 20, 10)), MOSS, z=2,
                   height=3, noise=0.2, seed=142))
    vines = cracks([[(40, 52), (60, 44), (80, 50), (100, 42), (122, 50)], [(44, 70), (66, 64), (88, 72), (116, 64)]], 2)
    parts.append(P(W, H, vines, THORN, z=3, flat=True))
    thorns = []
    for (x, y) in ((52, 46), (70, 46), (92, 46), (110, 45), (56, 67), (78, 68), (100, 68)):
        thorns.append(poly([(x - 2, y), (x, y - 6), (x + 2, y)]))
    parts.append(P(W, H, multi(*thorns), THORN, z=3.5, height=1.5, rim=(220, 200, 160)))
    parts.append(P(W, H, cracks([[(62, 30), (68, 40)], [(98, 30), (92, 40)]], 2), EMBER, z=3.6, flat=True, emit=EMB))
    hx = 80
    parts.append(P(W, H, poly([(hx - 13, 24 - br), (hx - 10, 10 - br), (hx, 6 - br), (hx + 10, 10 - br), (hx + 13, 24 - br)]),
                   ROCK, z=4, rim=RIM_COLD, height=5))
    parts.append(P(W, H, multi(circ(hx - 5, 15 - br, 2), circ(hx + 5, 15 - br, 2)), [(255, 220, 120)] * 5, z=5, flat=True,
                   emit=EMB_HOT))
    parts.append(P(W, H, multi(lines([(40, 40), (24, 58), (20, 72)], 9),
                               lines([(120, 40), (136, 54 - lift), (140, 64 - lift * 1.4)], 11)), ROCK, z=6,
                   rim=RIM_COLD, height=4, noise=0.12))
    parts.append(P(W, H, multi(ell(8, 66, 24, 22), ell(126, 56 - lift * 1.4, 30, 28)), ROCK, z=7, rim=RIM_COLD,
                   height=6, noise=0.14, seed=143))
    parts.append(P(W, H, multi(ell(130, 52 - lift * 1.4, 18, 8), ell(10, 64, 14, 6)), MOSS, z=7.5, height=2, noise=0.2))
    return parts


def ashenreach_devourer(t, attack):
    """A burrowing ash-worm: grey armoured rings rising out of the ground, ember light between
    them, and a round maw ringed with teeth - it opens all the way for the Maw Cone."""
    W, H = BW, BH
    ph = t * math.tau
    parts = []
    SEG = ramp((18, 16, 20), (128, 118, 124))
    open_ = 1.0 if not attack else 1.0 + t * 0.8
    parts.append(P(W, H, ell(4, 84, 56, 18), ramp((30, 22, 16), (120, 96, 76)), z=0, height=3, noise=0.25, seed=151))
    parts.append(P(W, H, cracks([[(14, 92), (24, 96), (34, 92)], [(40, 90), (50, 94)]], 1), EMBER, z=0.5, flat=True, emit=EMB))
    segs = []
    for k in range(7):
        u = k / 6
        x = 24 + u * 92 + math.sin(ph + k * 0.8) * 3
        y = 86 - math.sin(u * math.pi * 0.9) * 50 - u * 6 + math.cos(ph + k) * 2
        r = 16 - k * 0.8
        segs.append((x, y, r))
    for i, (x, y, r) in enumerate(segs):
        parts.append(P(W, H, circ(x, y, r + 2), MAGMA, z=1 + i * 0.1, flat=True, emit=EMB))
        parts.append(P(W, H, circ(x, y, r), SEG, z=1.05 + i * 0.1, rim=RIM_WARM, height=5, noise=0.1, seed=152 + i))
        parts.append(P(W, H, multi(poly([(x - 3, y - r), (x, y - r - 6), (x + 3, y - r)])), SEG, z=1.07 + i * 0.1,
                       height=1.5))
    hx, hy, _r = segs[-1]
    hx += 12
    R = 15 * open_
    parts.append(P(W, H, circ(hx, hy, R + 5), SEG, z=3, rim=RIM_WARM, height=6, noise=0.1, seed=160))
    parts.append(P(W, H, circ(hx, hy, R), MAW, z=4, flat=True))
    parts.append(P(W, H, circ(hx, hy, R * 0.45), MAGMA, z=4.5, flat=True, emit=EMB_HOT))
    teeth = []
    n = 12
    for k in range(n):
        a = k * math.tau / n
        bx, by = hx + math.cos(a) * R, hy + math.sin(a) * R
        tx, ty = hx + math.cos(a) * (R - 6), hy + math.sin(a) * (R - 6)
        nx, ny = -math.sin(a) * 2, math.cos(a) * 2
        teeth.append(poly([(bx + nx, by + ny), (tx, ty), (bx - nx, by - ny)]))
    parts.append(P(W, H, multi(*teeth), BONE, z=5, flat=True))
    parts.append(P(W, H, multi(circ(hx - R - 2, hy - 8, 2), circ(hx - R + 2, hy - 13, 1.5)), [(255, 210, 120)] * 5,
                   z=6, flat=True, emit=EMB_HOT))
    return parts


KINDS = {
    "ember_wisp": (ember_wisp, 64, 64), "fury_shard": (fury_shard, 64, 64),
    "rubble_crawler": (rubble_crawler, 64, 64), "spite_spirit": (spite_spirit, 64, 64),
    "shard_sentinel": (shard_sentinel, 64, 64), "echo_knight": (echo_knight, 64, 64),
    "shattered_golem": (shattered_golem, 64, 64), "fracture_hound": (fracture_hound, 64, 64),
    "stone_revenant": (stone_revenant, 64, 64), "cinder_warden": (cinder_warden, 64, 64),
    "cinder_colossus": (cinder_colossus, BW, BH), "rubble_warlord": (rubble_warlord, BW, BH),
    "ashreach_revenant": (ashreach_revenant, BW, BH), "thornrock_colossus": (thornrock_colossus, BW, BH),
    "ashenreach_devourer": (ashenreach_devourer, BW, BH),
}


def main(names=None):
    pygame.display.set_mode((1, 1))
    for name in names or KINDS:
        fn, w, h = KINDS[name]
        build(name, fn, w, h, 4, 3)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
