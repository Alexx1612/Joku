"""
Paints the last two boss families that still used coarse procedural grids:

  boss / boss_phase2          - the horned Demon Lord (the generic world / dungeon boss): purple hide,
                                orange horns, cream-and-red eyes, a gold belt, burning claws. Phase 2
                                is the same brute enraged: crimson hide split by glowing lava cracks,
                                horns on fire, bigger flames.
  mad_god / mad_god_phase2    - the Mad God's first two forms, leading into the hand-painted
                                "Unhinged" (violet, four arms) and "Absolutely Livid" (crimson wings):
                                first a serene, regal god in a pale-gold robe with a spiked crown, a
                                sun halo and a too-wide grin; phase 2 is the same god coming apart -
                                the robe scorched red, the crown cracked and askew, violet cracks
                                (Unhinged's colour) splitting the robe, hands crackling.

Same part-based lighting painter as tools/paint_night_sprites.py (key light top-left, rim light,
5-step ramps, Bayer dithering, selective outline, emissive glow layer). Logical canvas 160x104,
saved at 2x: a still, a 4-frame move strip, a 3-frame attack strip and the matching glow strips.
Wholly original.

Run: python tools/paint_boss_sprites.py   (writes into assets/sprites/v0.2/enemies/)
"""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pygame  # noqa: E402

from paint_night_sprites import P, ramp, render, soft_glow, save_set  # noqa: E402

W, H = 160, 104

# ------------------------------------------------------------- materials
# the Demon Lord (identity from game/sprites.py _BOSS_PAL: O horns, o/K hide, E/9 eyes, r belt)
HIDE = ramp((30, 8, 44), (160, 84, 200), warm_shadow=(40, 0, 30))
HIDE_D = ramp((18, 4, 28), (96, 40, 128))
HORN = ramp((90, 40, 6), (255, 196, 90), warm_shadow=(80, 20, 0))
GOLDB = ramp((96, 60, 8), (255, 232, 140))
EYE_W = ramp((150, 130, 110), (255, 250, 235))
EMBER = [(255, 70, 40)] * 5
FIRE_O = ramp((200, 60, 10), (255, 200, 80))
FIRE_Y = ramp((255, 150, 30), (255, 250, 200))
CLAW = ramp((40, 30, 30), (230, 220, 200))
MAW = ramp((20, 2, 6), (110, 20, 30))
TOOTH = ramp((150, 140, 120), (255, 252, 236))
HOOF = ramp((14, 10, 12), (90, 80, 84))
# enraged (phase 2)
HIDE2 = ramp((26, 4, 8), (176, 50, 46), warm_shadow=(50, 0, 0))
HIDE2_D = ramp((14, 2, 4), (100, 24, 22))
HORN2 = ramp((60, 16, 6), (230, 120, 60))
LAVA = [(255, 120, 30)] * 5

# the Mad God (identity from _MAD_GOD_PAL: O gold, o pale cream robe, K dark face, E white eyes, 9 red hem)
ROBE = ramp((96, 70, 30), (255, 244, 200), warm_shadow=(90, 40, 10))
ROBE_D = ramp((60, 40, 16), (190, 160, 100))
GOLD = ramp((110, 70, 10), (255, 236, 140))
HEM = ramp((90, 12, 14), (255, 96, 70))
SKIN = ramp((120, 96, 70), (252, 238, 214))
SHADE = ramp((26, 14, 8), (80, 50, 30))
SKIN_SH = [(190, 160, 128)] * 5
GEM = [(90, 220, 255)] * 5
GEM_R = [(255, 70, 160)] * 5
HALO = ramp((150, 110, 30), (255, 246, 190))
WHITE_HOT = [(255, 255, 240)] * 5
# coming apart (phase 2) - scorched red robe, violet cracks like the Unhinged form
ROBE2 = ramp((60, 14, 16), (230, 150, 120), warm_shadow=(80, 0, 10))
ROBE2_D = ramp((34, 6, 8), (150, 70, 60))
VIOLET = [(232, 124, 255)] * 5
RIM_GOLD = (255, 240, 190)
RIM_HOT = (255, 170, 120)


def _flame(cx, cy, size, ph, k=0):
    """A flickering flame polygon (base at cy, licking upward)."""
    pts = []
    n = 9
    for i in range(n + 1):
        u = i / n
        a = math.pi * u
        r = size * (0.55 + 0.45 * math.sin(u * math.pi))
        lick = (1.6 + 0.6 * math.sin(ph * 2 + k + u * 5)) if 0.3 < u < 0.7 else 1.0
        pts.append((cx - math.cos(a) * size * 0.6, cy - math.sin(a) * r * lick))
    return pts


# ------------------------------------------------------------- the Demon Lord
def demon_lord(t, attack, enraged=False):
    ph = t * math.tau
    bob = math.sin(ph) * 1.5
    breathe = math.sin(ph) * 1.0
    hide, hide_d = (HIDE2, HIDE2_D) if enraged else (HIDE, HIDE_D)
    horn = HORN2 if enraged else HORN
    rim = RIM_HOT if enraged else (210, 170, 255)
    cx = 80
    parts = []
    # arms: idle they hang at the sides with claws flexing; attack raises both fists, then slams
    if attack:
        lift = (1 - t) * 30 if t > 0.5 else 30 * (t / 0.5)  # up, then down on the slam
        fists = [(cx - 58, 62 - lift), (cx + 58, 62 - lift)]
    else:
        fists = [(cx - 54 + math.sin(ph) * 1.5, 70 + breathe), (cx + 54 - math.sin(ph) * 1.5, 70 + breathe)]
    shoulders = [(cx - 34, 38 + bob), (cx + 34, 38 + bob)]
    for (sx, sy), (fx, fy) in zip(shoulders, fists):
        ex, ey = (sx + fx) / 2 + (-6 if fx < cx else 6), (sy + fy) / 2 + 2  # elbow
        parts.append(P(W, H, lambda s, c, a=(sx, sy), b=(ex, ey): pygame.draw.line(s, c, a, b, 13), hide_d, z=1,
                       height=5, rim=rim, noise=0.07, seed=3))
        parts.append(P(W, H, lambda s, c, a=(ex, ey), b=(fx, fy): pygame.draw.line(s, c, a, b, 11), hide, z=1.2,
                       height=5, rim=rim, noise=0.07, seed=4))
        parts.append(P(W, H, lambda s, c, f=(fx, fy): pygame.draw.circle(s, c, (int(f[0]), int(f[1])), 8), hide,
                       z=1.4, height=4, rim=rim, seed=5))
        for k in range(3):  # three hooked claws
            dx = (k - 1) * 5
            parts.append(P(W, H, lambda s, c, f=(fx, fy), dx=dx: pygame.draw.polygon(
                s, c, [(f[0] + dx - 2, f[1] + 5), (f[0] + dx + 2, f[1] + 5), (f[0] + dx + 1, f[1] + 12)]),
                CLAW, z=1.5, height=1.5))
        # the burning claws (bigger on the slam / when enraged)
        size = (7 if not attack else 9 + 6 * t) * (1.4 if enraged else 1.0)
        parts.append(P(W, H, lambda s, c, f=(fx, fy), sz=size, k=fx: pygame.draw.polygon(
            s, c, _flame(f[0], f[1] - 4, sz, ph, k)), FIRE_O, z=1.6, height=3, flat=False, dome=0.6,
            emit=(255, 120, 40), alpha=230))
        parts.append(P(W, H, lambda s, c, f=(fx, fy), sz=size * 0.55, k=fx + 1: pygame.draw.polygon(
            s, c, _flame(f[0], f[1] - 5, sz, ph, k)), FIRE_Y, z=1.7, flat=True, emit=(255, 220, 120)))
    # legs + hooves
    for side in (-1, 1):
        lx = cx + side * 14
        stride = math.sin(ph) * 2 * side if not attack else 0
        parts.append(P(W, H, lambda s, c, lx=lx, st=stride: pygame.draw.polygon(
            s, c, [(lx - 9, 72 + bob), (lx + 9, 72 + bob), (lx + 7 + st, 96), (lx - 7 + st, 96)]),
            hide_d, z=0.5, height=6, rim=rim, noise=0.06, seed=6))
        parts.append(P(W, H, lambda s, c, lx=lx, st=stride: pygame.draw.ellipse(s, c, (lx - 9 + st, 94, 18, 8)),
                       HOOF, z=0.6, height=2))
    # torso: a huge barrel chest tapering to the belt
    torso = [(cx - 37, 33 + bob), (cx + 37, 33 + bob), (cx + 25, 72 + bob), (cx - 25, 72 + bob)]
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, torso), hide, z=2, height=12, rim=rim, noise=0.08,
                   seed=7, dome=0.5))
    # chest plates + abs
    parts.append(P(W, H, lambda s, c: (pygame.draw.arc(s, c, (cx - 26, 36 + bob, 26, 18), math.pi, math.tau, 2),
                                       pygame.draw.arc(s, c, (cx, 36 + bob, 26, 18), math.pi, math.tau, 2),
                                       [pygame.draw.line(s, c, (cx - 9, 56 + bob + k * 5), (cx + 9, 56 + bob + k * 5), 1)
                                        for k in range(3)],
                                       pygame.draw.line(s, c, (cx, 50 + bob), (cx, 70 + bob), 1)),
                   hide_d, z=2.2, flat=True))
    if enraged:  # lava cracks splitting the hide
        cracks = [[(cx - 20, 40 + bob), (cx - 14, 48 + bob), (cx - 18, 56 + bob), (cx - 10, 64 + bob)],
                  [(cx + 18, 38 + bob), (cx + 12, 47 + bob), (cx + 17, 55 + bob)],
                  [(cx - 3, 42 + bob), (cx + 3, 50 + bob), (cx - 2, 58 + bob)]]
        parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, cr, 2) for cr in cracks], LAVA, z=2.3,
                       flat=True, emit=(255, 110, 30)))
    # the gold belt with a horned skull buckle
    parts.append(P(W, H, lambda s, c: pygame.draw.rect(s, c, (cx - 26, 67 + bob, 52, 7), border_radius=2), GOLDB,
                   z=2.5, height=2, rim=RIM_GOLD, noise=0.04))
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 6, 64 + bob, 12, 11)), TOOTH, z=2.6, height=2))
    parts.append(P(W, H, lambda s, c: (pygame.draw.circle(s, c, (cx - 2, int(69 + bob)), 1),
                                       pygame.draw.circle(s, c, (cx + 2, int(69 + bob)), 1)), MAW, z=2.7, flat=True))
    # shoulder pauldrons of bone
    for side in (-1, 1):
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.ellipse(s, c, (cx + sd * 34 - 12, 29 + bob, 24, 15)),
                       TOOTH, z=2.8, height=3, rim=RIM_GOLD, noise=0.05, seed=8))
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.polygon(
            s, c, [(cx + sd * 34 - 3, 30 + bob), (cx + sd * 34 + 3, 30 + bob), (cx + sd * 39, 20 + bob)]),
            TOOTH, z=2.9, height=2))
    # the head
    hy = 20 + bob
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 15, hy - 4, 30, 30)), hide, z=3, height=8,
                   rim=rim, noise=0.07, seed=9))
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(cx - 14, hy + 4), (cx + 14, hy + 4), (cx, hy + 9)]),
                   hide_d, z=3.2, flat=True))  # the heavy brow
    # the horns: thick at the root, curling up and out (burning tips when enraged)
    for side in (-1, 1):
        # a quadratic curve: root at the side of the skull, sweeping OUT, then up, the tip hooking back in
        p0 = (cx + side * 11, hy + 2)
        p1 = (cx + side * 34, hy - 2)
        p2 = (cx + side * 27, hy - 26)
        pts_o, pts_i = [], []
        for k in range(14):
            u = k / 13
            x = (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0]
            y = (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1]
            th = 7 * (1 - u) ** 0.8 + 0.6
            pts_o.append((x + side * th * 0.5, y + th * 0.3))
            pts_i.append((x - side * th * 0.5, y - th * 0.3))
        poly = pts_o + list(reversed(pts_i))
        parts.append(P(W, H, lambda s, c, pl=poly: pygame.draw.polygon(s, c, pl), horn, z=3.4, height=3,
                       rim=RIM_GOLD, noise=0.05, seed=10))
        parts.append(P(W, H, lambda s, c, pl=pts_o: [pygame.draw.line(s, c, pl[k], (pl[k][0] + 2, pl[k][1] + 2), 1)
                                                     for k in range(2, 10, 2)], ramp((70, 30, 4), (140, 70, 20)), z=3.5,
                       flat=True))  # ridges
        if enraged:
            tip = pts_o[-1]
            parts.append(P(W, H, lambda s, c, tp=tip, k=side: pygame.draw.polygon(s, c, _flame(tp[0], tp[1] + 2, 5, ph, k)),
                           FIRE_Y, z=3.6, flat=True, emit=(255, 170, 60)))
    # eyes: cream with red pupils, burning
    for side in (-1, 1):
        ex = cx + side * 6
        parts.append(P(W, H, lambda s, c, ex=ex: pygame.draw.ellipse(s, c, (ex - 4, hy + 5, 8, 5)), EYE_W, z=3.7,
                       height=1.5, emit=(255, 240, 200) if not enraged else None))
        parts.append(P(W, H, lambda s, c, ex=ex: pygame.draw.circle(s, c, (ex + (1 if attack else 0), int(hy + 7)),
                                                                    2 if not enraged else 3),
                       EMBER, z=3.8, flat=True, emit=(255, 60, 30)))
    # the fanged maw (wider on the attack roar)
    jaw = 4 + (6 * t if attack else math.sin(ph) * 0.8)
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 9, hy + 14, 18, 4 + jaw)), MAW, z=3.9, flat=True,
                   emit=(160, 30, 20) if enraged else None))
    parts.append(P(W, H, lambda s, c: [pygame.draw.polygon(s, c, [(cx - 8 + k * 4, hy + 14), (cx - 6 + k * 4, hy + 14),
                                                                   (cx - 7 + k * 4, hy + 18)]) for k in range(5)]
                   + [pygame.draw.polygon(s, c, [(cx - 9, hy + 14), (cx - 6, hy + 14), (cx - 8, hy + 20)]),
                      pygame.draw.polygon(s, c, [(cx + 9, hy + 14), (cx + 6, hy + 14), (cx + 8, hy + 20)])],
                   TOOTH, z=4, height=1, flat=True))
    return parts


def demon_lord_enraged(t, attack):
    return demon_lord(t, attack, enraged=True)


# ------------------------------------------------------------- the Mad God
def mad_god(t, attack, unravelling=False):
    ph = t * math.tau
    bob = math.sin(ph) * 2.0  # he floats
    robe, robe_d = (ROBE2, ROBE2_D) if unravelling else (ROBE, ROBE_D)
    rim = RIM_HOT if unravelling else RIM_GOLD
    cx = 80
    parts = []
    # the sun halo behind his head (cracked open when he's unravelling)
    hy = 22 + bob
    parts.append(P(W, H, lambda s, c: pygame.draw.circle(s, c, (cx, int(hy)), 21, 3), HALO, z=0, height=1.5,
                   emit=(255, 230, 150) if not unravelling else (255, 120, 120)))
    rays = 14
    parts.append(P(W, H, lambda s, c: [pygame.draw.line(
        s, c, (cx + math.cos(k * math.tau / rays + ph * 0.25) * 23, hy + math.sin(k * math.tau / rays + ph * 0.25) * 23),
        (cx + math.cos(k * math.tau / rays + ph * 0.25) * (28 + (k % 2) * 4),
         hy + math.sin(k * math.tau / rays + ph * 0.25) * (28 + (k % 2) * 4)), 1)
        for k in range(rays) if not (unravelling and k in (3, 4, 9))], HALO, z=0.1, flat=True,
        emit=(255, 220, 140) if not unravelling else (255, 110, 110)))
    # arms spread wide (raised high on the attack, a white-hot orb in each hand)
    if attack:
        rise = 26 * min(1.0, t * 1.4)
        hands = [(cx - 58, 44 - rise), (cx + 58, 44 - rise)]
    else:
        hands = [(cx - 56, 50 + math.sin(ph) * 3 + bob), (cx + 56, 50 - math.sin(ph) * 3 + bob)]
    shoulders = [(cx - 14, 40 + bob), (cx + 14, 40 + bob)]
    for (sx, sy), (hx, hyy) in zip(shoulders, hands):
        # a wide flowing sleeve: a long trapezoid flaring toward the hand
        dirx = -1 if hx < cx else 1
        sleeve = [(sx, sy - 5), (sx, sy + 7), (hx - dirx * 6, hyy + 12), (hx - dirx * 8, hyy - 4)]
        parts.append(P(W, H, lambda s, c, sl=sleeve: pygame.draw.polygon(s, c, sl), robe, z=1, height=5, rim=rim,
                       noise=0.06, seed=11))
        cuff = [(hx - dirx * 6, hyy + 12), (hx - dirx * 8, hyy - 4), (hx - dirx * 11, hyy - 4), (hx - dirx * 10, hyy + 13)]
        parts.append(P(W, H, lambda s, c, cf=cuff: pygame.draw.polygon(s, c, cf), GOLD, z=1.2, height=2, rim=RIM_GOLD))
        parts.append(P(W, H, lambda s, c, h=(hx, hyy): pygame.draw.circle(s, c, (int(h[0]), int(h[1]) + 4), 5), SKIN,
                       z=1.3, height=2.5, rim=rim))
        # power in the hands: a soft orb idle, a blazing one on the attack
        orb = 3 + math.sin(ph * 2) * 0.8 + (7 * t if attack else 0)
        col = VIOLET if unravelling else WHITE_HOT
        parts.append(P(W, H, lambda s, c, h=(hx, hyy), r=orb: pygame.draw.circle(s, c, (int(h[0]), int(h[1]) - 4),
                                                                                  max(2, int(r))),
                       col, z=1.4, flat=True, emit=(232, 124, 255) if unravelling else (255, 250, 210)))
        if unravelling:  # the hands crackle (Unhinged's sparks)
            parts.append(P(W, H, lambda s, c, h=(hx, hyy): pygame.draw.lines(s, c, False, [
                (h[0] - 6, h[1] - 10), (h[0] - 2, h[1] - 6), (h[0] - 5, h[1] - 2), (h[0] + 1, h[1] + 1)], 1),
                VIOLET, z=1.5, flat=True, emit=(240, 150, 255)))
    # the robe: a tall bell, its hem rippling (he doesn't walk - it trails)
    hem = []
    for k in range(13):
        x = cx - 34 + k * (68 / 12)
        hem.append((x, 98 + math.sin(ph + k * 0.9) * 2.5 - (k % 2) * 2))
    body = [(cx - 14, 34 + bob), (cx + 14, 34 + bob), (cx + 22, 60 + bob), (cx + 34, 96)] + list(reversed(hem)) + \
           [(cx - 34, 96), (cx - 22, 60 + bob)]
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, body), robe, z=2, height=12, rim=rim, noise=0.06,
                   seed=12, dome=0.45))
    # folds
    folds = [[(cx - 10 + k * 7, 48 + bob), (cx - 22 + k * 15 + math.sin(ph + k) * 2, 94)] for k in range(4)]
    parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, f, 1) for f in folds], robe_d, z=2.1, flat=True))
    # the gold stole down the front, with the red hem band
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(cx - 5, 36 + bob), (cx + 5, 36 + bob), (cx + 8, 92),
                                                                 (cx - 8, 92)]), GOLD, z=2.2, height=3, rim=RIM_GOLD,
                   noise=0.04))
    parts.append(P(W, H, lambda s, c: [pygame.draw.circle(s, c, (cx, int(46 + bob + k * 12)), 2) for k in range(4)],
                   GEM_R, z=2.3, flat=True, emit=(255, 90, 170)))
    parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, hem, 4), HEM, z=2.25, height=1.5))
    if unravelling:  # violet cracks splitting the robe - the Unhinged form clawing its way out
        cracks = [[(cx - 18, 52 + bob), (cx - 14, 62 + bob), (cx - 19, 72 + bob), (cx - 13, 84 + bob)],
                  [(cx + 16, 50 + bob), (cx + 20, 60 + bob), (cx + 14, 70 + bob), (cx + 21, 82 + bob)],
                  [(cx - 2, 70 + bob), (cx + 3, 78 + bob), (cx - 1, 88 + bob)]]
        parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, cr, 2) for cr in cracks], VIOLET, z=2.4,
                       flat=True, emit=(232, 124, 255)))
    # the gold collar
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 17, 32 + bob, 34, 10)), GOLD, z=2.5, height=2,
                   rim=RIM_GOLD))
    # the head: a pale, serene face (the shadow K of his grid) - too wide a grin
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 11, hy - 8, 22, 24)), SKIN, z=3, height=6,
                   rim=rim, noise=0.03, seed=13))
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 9, hy - 2, 18, 7)), SKIN_SH, z=3.1,
                   flat=True))  # the shadowed brow band
    eye_col = [(255, 80, 70)] * 5 if unravelling else WHITE_HOT
    for side in (-1, 1):
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.ellipse(s, c, (cx + sd * 5 - 3, int(hy), 6, 3)),
                       eye_col, z=3.2, flat=True, emit=(255, 80, 70) if unravelling else (255, 255, 230)))
    grin_w = 8 + (4 if unravelling else 0) + (3 * t if attack else 0)
    parts.append(P(W, H, lambda s, c: pygame.draw.arc(s, c, (cx - grin_w, hy + 1, grin_w * 2, 10), math.pi * 1.1,
                                                      math.pi * 1.9, 2), [(30, 10, 10)] * 5, z=3.3, flat=True))
    parts.append(P(W, H, lambda s, c: [s.set_at((int(cx - grin_w * 0.6 + k * grin_w * 0.4), int(hy + 9)), c)
                                       for k in range(4)], [(255, 255, 255)] * 5, z=3.4, flat=True))
    # the spiked crown (cracked and knocked askew when he's unravelling)
    tilt = 0.18 if unravelling else 0.0
    spikes = []
    for k in range(7):
        bx = cx - 12 + k * 4
        top = hy - 20 - (6 if k == 3 else (3 if k % 2 == 0 else 0))
        spikes.append([(bx - 2, hy - 9), (bx + 2, hy - 9), (bx, top)])

    def _crown(s, c):
        pygame.draw.rect(s, c, (cx - 13, hy - 12, 26, 5), border_radius=1)
        for sp in spikes:
            pygame.draw.polygon(s, c, sp)
    crown_surf = pygame.Surface((W, H), pygame.SRCALPHA)
    _crown(crown_surf, (255, 255, 255, 255))
    if tilt:
        crown_surf = pygame.transform.rotate(crown_surf, -tilt * 57.3)
        crown_surf = crown_surf.subsurface(crown_surf.get_rect(center=crown_surf.get_rect().center).clip(
            pygame.Rect((crown_surf.get_width() - W) // 2 + 3, (crown_surf.get_height() - H) // 2, W, H))).copy()
        fixed = pygame.Surface((W, H), pygame.SRCALPHA)
        fixed.blit(crown_surf, (0, 0))
        crown_surf = fixed
    from paint_night_sprites import Part
    parts.append(Part(crown_surf, GOLD, z=3.6, height=2, rim=RIM_GOLD, noise=0.04, seed=14))
    parts.append(P(W, H, lambda s, c: [pygame.draw.circle(s, c, (cx - 8 + k * 8, int(hy - 10)), 1) for k in range(3)],
                   GEM if not unravelling else GEM_R, z=3.7, flat=True,
                   emit=(110, 230, 255) if not unravelling else (255, 90, 170)))
    if unravelling:  # a crack through the crown
        parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, [(cx + 2, hy - 17), (cx, hy - 13), (cx + 3, hy - 9)],
                                                            1), VIOLET, z=3.8, flat=True, emit=(232, 124, 255)))
    return parts


def mad_god_unravelling(t, attack):
    return mad_god(t, attack, unravelling=True)


def build(name, pose_fn, moves=4, attacks=3):
    mv, gm, at, ga = [], [], [], []
    for i in range(moves):
        s, g = render(pose_fn(i / moves, False), W, H)
        mv.append(s)
        gm.append(soft_glow(g))
    for i in range(attacks):
        s, g = render(pose_fn(i / max(1, attacks - 1), True), W, H)
        at.append(s)
        ga.append(soft_glow(g))
    save_set(name, mv[0], mv, at, gm, ga)
    print(f"painted {name}: {moves} move + {attacks} attack frames")


def main():
    pygame.init()
    pygame.display.set_mode((8, 8))
    build("boss", demon_lord)
    build("boss_phase2", demon_lord_enraged)
    build("mad_god", mad_god)
    build("mad_god_phase2", mad_god_unravelling)


if __name__ == "__main__":
    main()
