"""
Paints the Realm's neutral wildlife (hares, deer, elk, goats, foxes, rats, tortoises, frogs,
beetles, flamingos, herons, penguins, songbirds, owls, cave moths, mushroom folk, lizards) and the
two night herbs (Moonpetal, Ghostbloom): a still PNG and a 4-frame idle/move strip each, plus an
emissive "glow" strip for the night-only ones (the herbs, the owl's eyes). Wholly original.

It reuses the part-based painter of tools/paint_night_sprites.py (automatic lighting from each
part's silhouette, colour ramps, Bayer dithering, selective + silhouette outlines). Each creature
is drawn on a small logical canvas, then every frame is cropped to the union of the creature's
frames (so it fills the in-game 48 px box) and saved at 2x.

Run: python tools/paint_wildlife_sprites.py [kind ...]   (writes into assets/sprites/v0.2/enemies/)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

import paint_night_sprites as N  # noqa: E402
from paint_night_sprites import P, ramp  # noqa: E402

pygame.init()
OUT = N.OUT
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = 4
TAU = math.tau


# ------------------------------------------------------------------ helpers
def ell(cx, cy, rx, ry):
    return lambda s, c: pygame.draw.ellipse(s, c, (cx - rx, cy - ry, rx * 2, ry * 2))


def poly(pts):
    return lambda s, c: pygame.draw.polygon(s, c, [(int(round(x)), int(round(y))) for x, y in pts])


def line(pts, w):
    def f(s, c):
        ip = [(int(round(x)), int(round(y))) for x, y in pts]
        pygame.draw.lines(s, c, False, ip, w)
        for p in ip:  # round the joints
            pygame.draw.circle(s, c, p, max(1, w // 2))
    return f


def circ(cx, cy, r):
    return lambda s, c: pygame.draw.circle(s, c, (int(round(cx)), int(round(cy))), max(1, int(round(r))))


def dot(x, y):
    return lambda s, c: s.set_at((int(round(x)), int(round(y))), c)


def many(*fns):
    def f(s, c):
        for fn in fns:
            fn(s, c)
    return f


def leg(hx, hy, length, ph, stride=3.0, lift=2.0, knee=1.5, back=False):
    """A walking leg from the hip: the foot swings `stride` and lifts on the forward swing."""
    fx = hx + math.sin(ph) * stride
    fy = hy + length - max(0.0, math.cos(ph)) * lift
    kx = (hx + fx) / 2 + (-knee if back else knee)
    ky = hy + length * 0.5
    return [(hx, hy), (kx, ky), (fx, fy)]


def eye(x, y, iris=(30, 24, 20), shine=(250, 250, 250), r=1.2, z=20):
    return [P(W_, H_, circ(x, y, r), [iris] * 5, z=z, flat=True),
            P(W_, H_, dot(x - 0.4, y - 0.6), [shine] * 5, z=z + 0.1, flat=True)]


W_ = H_ = 64  # the canvas the current creature draws on (set by each pose function)


def canvas(w, h):
    global W_, H_
    W_, H_ = w, h
    return w, h


# ------------------------------------------------------------------ materials
def fur(dark, light, warm=None):
    return ramp(dark, light, warm_shadow=warm)


CREAM = fur((120, 104, 84), (250, 244, 230))
PINK_EAR = fur((120, 70, 70), (240, 170, 165))
NOSE = fur((30, 20, 20), (110, 70, 70))
HOOF = fur((20, 16, 12), (80, 66, 52))
WHITE = fur((140, 146, 160), (255, 255, 255))


# ------------------------------------------------------------------ the creatures
def forest_hare(t):
    w, h = canvas(56, 48)
    ph = t * TAU
    hop = -max(0.0, math.sin(ph)) * 3.0             # a little hop on half the cycle
    ear = math.sin(ph * 2) * 1.2
    body, belly = fur((80, 66, 50), (226, 212, 192), (60, 30, 20)), CREAM
    y = lambda v: v + hop
    parts = [
        P(w, h, line([(30, y(33)), (35, y(41)), (42, 44 + hop * 0.3)], 3), fur((60, 50, 40), (170, 155, 135)), z=0),   # far hind leg
        P(w, h, ell(26, y(32), 13, 9), body, z=2, height=6, noise=0.07, seed=1),                     # body
        P(w, h, ell(20, y(36), 8, 7), body, z=2.5, height=5, noise=0.07, seed=2),                    # haunch
        P(w, h, ell(30, y(37), 8, 3), belly, z=2.6, height=2, noise=0.04),                           # belly
        P(w, h, circ(9, y(31), 4), WHITE, z=1.5, height=3, noise=0.12),                              # tail puff
        P(w, h, line([(18, y(40)), (12, y(44)), (22, y(45))], 3), body, z=3, height=1.5),            # near hind foot
        P(w, h, line([(36, y(36)), (37, y(44)), (40, y(45))], 2), body, z=3.2, height=1.2),          # fore leg
        P(w, h, ell(40, y(25), 8, 7), body, z=4, height=5, noise=0.06, seed=3),                      # head
        P(w, h, ell(44, y(28), 4, 3), belly, z=4.2, height=2),                                       # muzzle
        P(w, h, ell(33 + ear * 0.4, y(10), 2.6, 9), body, z=3.6, height=2.5),                        # far ear
        P(w, h, ell(37 + ear, y(9), 3, 10), body, z=4.6, height=3),                                  # near ear
        P(w, h, ell(37.3 + ear, y(10), 1.4, 7), PINK_EAR, z=4.7, flat=True),
        P(w, h, circ(48, y(27), 1.2), NOSE, z=5, flat=True),
    ]
    return parts + eye(43, y(23), r=1.4)


def snow_fox(t):
    w, h = canvas(60, 44)
    ph = t * TAU
    body = fur((140, 150, 172), (252, 253, 255), (80, 90, 140))
    legc = fur((110, 118, 138), (200, 206, 220))
    orange = fur((160, 80, 30), (250, 180, 110))
    wag = math.sin(ph) * 2
    parts = [
        P(w, h, line(leg(22, 28, 11, ph + math.pi, back=True), 3), legc, z=0),
        P(w, h, line(leg(40, 28, 11, ph, back=True), 3), legc, z=0),
        P(w, h, poly([(16, 26), (8, 18 + wag), (2, 8 + wag), (6, 4 + wag), (13, 8 + wag), (20, 18), (22, 26)]),
          body, z=1, height=6, noise=0.1, seed=4),                                                   # big plume tail
        P(w, h, many(circ(4, 6 + wag, 3.2), circ(7, 4 + wag, 2.4)), orange, z=1.2, height=2),         # orange tip
        P(w, h, ell(30, 26, 13, 7.5), body, z=2, height=6, noise=0.08, seed=5),
        P(w, h, line(leg(24, 28, 12, ph), 3), body, z=3),
        P(w, h, line(leg(38, 28, 12, ph + math.pi), 3), body, z=3),
        P(w, h, ell(44, 20, 7, 6.5), body, z=4, height=5, seed=6),                                     # head
        P(w, h, poly([(46, 18), (58, 22), (59, 24), (46, 26)]), body, z=4.3, height=3),                # pointed snout
        P(w, h, poly([(39, 17), (39, 5), (45, 14)]), orange, z=3.8, height=2),                         # ears
        P(w, h, poly([(44, 15), (48, 4), (50, 15)]), orange, z=4.5, height=2),
        P(w, h, poly([(45, 14), (48, 8), (49, 14)]), fur((90, 50, 50), (240, 160, 150)), z=4.6, flat=True),
        P(w, h, circ(58, 22, 1.4), NOSE, z=5, flat=True),
        P(w, h, many(circ(25, 39, 1.6), circ(37, 39, 1.6)), orange, z=3.2, flat=True),                 # socks
    ]
    return parts + eye(48, 18, iris=(25, 30, 45), r=1.3)


def _quadruped(t, w, h, body, belly, legc, hoofc, head_fn, extra=(), stride=3.0, body_y=30, length=16):
    ph = t * TAU
    parts = [
        P(w, h, line(leg(18, body_y + 4, length, ph + math.pi, stride, back=True), 3), legc, z=0),
        P(w, h, line(leg(42, body_y + 4, length, ph, stride, back=True), 3), legc, z=0),
        P(w, h, ell(30, body_y, 17, 8), body, z=2, height=7, noise=0.07, seed=7),
        P(w, h, ell(31, body_y + 5, 12, 3), belly, z=2.2, height=2, noise=0.03),
        P(w, h, line(leg(20, body_y + 4, length, ph, stride), 3), body, z=3),
        P(w, h, line(leg(40, body_y + 4, length, ph + math.pi, stride), 3), body, z=3),
    ]
    for xh, p in ((20, ph), (40, ph + math.pi)):
        f = leg(xh, body_y + 4, length, p, stride)[-1]
        parts.append(P(w, h, circ(f[0], f[1], 1.6), hoofc, z=3.1, flat=True))
    return parts + list(head_fn(ph)) + list(extra)


def deer(t):
    w, h = canvas(64, 60)
    body = fur((80, 54, 32), (210, 162, 112), (70, 30, 20))
    belly = fur((150, 120, 90), (246, 232, 206))

    def head(ph):
        bob = math.sin(ph * 2) * 0.8
        return [P(w, h, poly([(44, 26), (50, 12 + bob), (55, 12 + bob), (52, 27)]), body, z=4, height=3),      # neck
                P(w, h, ell(55, 11 + bob, 6, 4.5), body, z=5, height=4, seed=8),
                P(w, h, ell(60, 13 + bob, 3, 2.4), belly, z=5.1, height=1.5),
                P(w, h, ell(51, 5 + bob, 2, 4), body, z=4.8, height=1.5),                               # ear
                P(w, h, many(line([(54, 7 + bob), (52, 1 + bob), (50, -1 + bob)], 1),
                             line([(56, 7 + bob), (58, 1 + bob)], 1)), fur((60, 40, 26), (150, 112, 76)), z=5.5,
                  flat=True),                                                                           # spike antlers
                P(w, h, circ(63, 13 + bob, 1), NOSE, z=6, flat=True)] + eye(56, 10 + bob, r=1.2)
    tail = P(w, h, ell(13, 26, 3, 3), WHITE, z=1.5, height=2)
    return _quadruped(t, w, h, body, belly, fur((60, 42, 26), (150, 110, 74)), HOOF, head, extra=[tail])


def elk(t):
    w, h = canvas(64, 64)
    body = fur((52, 32, 18), (150, 104, 66), (50, 20, 10))
    mane = fur((34, 22, 14), (100, 70, 46))
    antler = fur((120, 104, 78), (240, 226, 190))

    def head(ph):
        bob = math.sin(ph * 2) * 0.7
        return [P(w, h, poly([(42, 30), (48, 18 + bob), (56, 18 + bob), (54, 32)]), mane, z=4, height=4, noise=0.12),
                P(w, h, ell(56, 18 + bob, 6.5, 5), body, z=5, height=4, seed=9),
                P(w, h, ell(61, 21 + bob, 3, 2.6), fur((90, 66, 46), (200, 170, 130)), z=5.1, height=1.5),
                P(w, h, many(line([(53, 14 + bob), (46, 6 + bob), (42, 0 + bob)], 2),
                             line([(48, 9 + bob), (44, 12 + bob)], 1), line([(45, 4 + bob), (40, 6 + bob)], 1),
                             line([(57, 14 + bob), (62, 5 + bob), (63, 0 + bob)], 2),
                             line([(60, 9 + bob), (64, 9 + bob)], 1)), antler, z=6, height=1.2),             # big antlers
                P(w, h, circ(64, 21 + bob, 1), NOSE, z=6, flat=True)] + eye(57, 16 + bob, r=1.2)
    tail = P(w, h, ell(13, 33, 3, 2.5), CREAM, z=1.5, height=2)
    return _quadruped(t, w, h, body, fur((80, 56, 36), (176, 136, 96)), fur((40, 26, 16), (110, 78, 50)), HOOF,
                      head, extra=[tail], body_y=36, length=17)


def mountain_goat(t):
    w, h = canvas(64, 56)
    body = fur((118, 116, 108), (244, 242, 236), (70, 70, 90))
    horn = fur((40, 36, 30), (150, 138, 118))

    def head(ph):
        bob = math.sin(ph * 2) * 0.8
        return [P(w, h, poly([(44, 24), (49, 14 + bob), (56, 15 + bob), (53, 27)]), body, z=4, height=4, noise=0.12),
                P(w, h, ell(56, 14 + bob, 6, 4.5), body, z=5, height=4, seed=10),
                P(w, h, poly([(55, 18 + bob), (58, 26 + bob), (54, 24 + bob)]), body, z=5.2, height=1.5),   # beard
                P(w, h, line([(53, 10 + bob), (50, 3 + bob), (45, 2 + bob), (44, 6 + bob)], 2), horn, z=5.5, height=1.2),
                P(w, h, circ(61, 15 + bob, 1), NOSE, z=6, flat=True)] + eye(55, 12 + bob, r=1.1)
    shag = P(w, h, poly([(16, 34), (22, 40), (28, 35), (34, 41), (40, 35), (46, 39), (44, 32), (18, 31)]), body,
             z=2.1, height=2, noise=0.14)
    return _quadruped(t, w, h, body, fur((150, 148, 140), (250, 250, 248)), fur((100, 98, 92), (200, 198, 190)), HOOF,
                      head, extra=[shag], body_y=30, length=14, stride=2.5)


def scrap_rat(t):
    w, h = canvas(52, 28)
    ph = t * TAU
    body = fur((46, 42, 38), (168, 158, 146), (40, 20, 20))
    pink = fur((110, 70, 64), (220, 156, 146))
    sway = math.sin(ph) * 2
    parts = [
        P(w, h, line([(12, 18), (6, 20 + sway), (1, 16 + sway)], 2), pink, z=0, height=1),                # tail
        P(w, h, line(leg(18, 20, 6, ph + math.pi, 2.5, 1.5, back=True), 2), pink, z=0.5),
        P(w, h, ell(23, 16, 12, 7), body, z=2, height=5, noise=0.12, seed=11),
        P(w, h, line(leg(30, 20, 6, ph, 2.5, 1.5), 2), pink, z=3),
        P(w, h, line(leg(18, 20, 6, ph, 2.5, 1.5), 2), pink, z=3),
        P(w, h, poly([(31, 11), (40, 12), (48, 17), (40, 20), (32, 20)]), body, z=4, height=4, seed=12),
        P(w, h, circ(34, 8, 3.2), pink, z=4.5, height=2),                                                # ear
        P(w, h, circ(48, 17, 1.2), pink, z=5, flat=True),
        P(w, h, many(line([(46, 17), (51, 15)], 1), line([(46, 18), (51, 20)], 1)), [(200, 196, 190)] * 5, z=5,
          flat=True),                                                                                     # whiskers
    ]
    return parts + eye(41, 14, iris=(210, 60, 40), shine=(255, 200, 180), r=1.1)


def tortoise(t):
    w, h = canvas(56, 36)
    ph = t * TAU
    shell = fur((56, 42, 20), (176, 142, 80), (40, 30, 10))
    plate = fur((90, 70, 34), (210, 180, 110))
    skin = fur((58, 78, 38), (172, 200, 124))
    head_out = 2 + math.sin(ph) * 1.5
    parts = [
        P(w, h, line(leg(16, 24, 6, ph + math.pi, 2, 1, back=True), 4), skin, z=0),
        P(w, h, line(leg(36, 24, 6, ph, 2, 1, back=True), 4), skin, z=0),
        P(w, h, poly([(40 + head_out, 18), (48 + head_out, 15), (54 + head_out, 18), (50 + head_out, 23), (41, 24)]),
          skin, z=1, height=3, seed=13),
        P(w, h, poly([(6, 25), (10, 12), (20, 5), (34, 5), (43, 13), (46, 25)]), shell, z=2, height=8, noise=0.06, seed=14),
        P(w, h, many(poly([(16, 10), (24, 7), (30, 10), (28, 16), (19, 16)]), poly([(31, 11), (38, 12), (41, 19), (33, 20)]),
                     poly([(10, 18), (17, 17), (19, 22), (11, 24)]), poly([(21, 18), (30, 18), (31, 23), (21, 24)])),
          plate, z=2.5, height=2.5, noise=0.05),
        P(w, h, ell(26, 26, 20, 2.5), fur((80, 70, 40), (190, 170, 110)), z=2.2, height=1.2),             # shell rim
        P(w, h, line(leg(14, 24, 7, ph, 2, 1), 4), skin, z=3),
        P(w, h, line(leg(37, 24, 7, ph + math.pi, 2, 1), 4), skin, z=3),
    ]
    return parts + eye(51 + head_out, 17, r=1.0)


def tree_frog(t):
    w, h = canvas(44, 34)
    ph = t * TAU
    body = fur((16, 86, 36), (150, 244, 136))
    belly = fur((140, 160, 100), (240, 250, 200))
    orange = fur((150, 60, 10), (255, 176, 70))
    puff = 1.0 + max(0.0, math.sin(ph * 2)) * 1.6        # the throat sac
    hop = -max(0.0, math.sin(ph)) * 2.0
    y = lambda v: v + hop
    parts = [
        P(w, h, line([(14, y(24)), (7, y(28)), (13, 31), (18, 31)], 3), body, z=0, height=1.5),           # far hind leg
        P(w, h, ell(21, y(21), 12, 7), body, z=2, height=6, noise=0.05, seed=15),
        P(w, h, ell(26, y(26), 7, 3), belly, z=2.2, height=1.5),
        P(w, h, ell(33, y(25), 3.2 * puff, 2.6 * puff), belly, z=2.4, height=2),                          # throat
        P(w, h, line([(15, y(25)), (9, y(30)), (17, 32)], 3), body, z=3, height=1.5),
        P(w, h, line([(29, y(25)), (31, 30), (34, 32)], 2), body, z=3, height=1.2),
        P(w, h, many(circ(18, 32, 1.5), circ(35, 32, 1.4)), orange, z=3.2, flat=True),                    # toe pads
        P(w, h, circ(28, y(13), 4.2), orange, z=4, height=3, dome=0.6),                                   # the big eye
    ]
    return parts + [P(w, h, ell(28.5, y(13), 1.2, 3), [(20, 16, 12)] * 5, z=4.5, flat=True),
                    P(w, h, dot(27, y(11)), [(255, 255, 240)] * 5, z=4.6, flat=True)]


def fire_beetle(t):
    w, h = canvas(48, 34)
    ph = t * TAU
    shell = fur((72, 10, 8), (255, 112, 52), (60, 10, 30))
    body = fur((20, 8, 6), (110, 46, 30))
    glow = fur((200, 120, 30), (255, 236, 150))
    parts = []
    for i, x in enumerate((14, 22, 30)):
        p = ph + i * 2.1
        parts.append(P(w, h, line([(x, 24), (x - 3 + math.sin(p) * 2, 28), (x - 5 + math.sin(p) * 3, 32)], 2), body, z=0))
    parts += [
        P(w, h, ell(21, 18, 15, 9), shell, z=2, height=7, noise=0.04, seed=16),
        P(w, h, line([(9, 14), (33, 14)], 1), fur((40, 6, 4), (120, 30, 20)), z=2.5, flat=True),         # wing seam
        P(w, h, many(circ(14, 19, 1.6), circ(24, 21, 1.6), circ(19, 13, 1.3)), glow, z=2.6, flat=True),  # glowing spots
        P(w, h, ell(37, 20, 6, 5), body, z=3, height=3, seed=17),
        P(w, h, many(line([(40, 16), (44, 9 + math.sin(ph) * 1.5), (47, 7)], 1),
                     line([(41, 17), (46, 13 - math.sin(ph) * 1.5)], 1)), body, z=3.5, flat=True),
        P(w, h, many(circ(47, 7, 1.2), circ(46, 13 - math.sin(ph) * 1.5, 1.1)), glow, z=3.6, flat=True),
    ]
    for i, x in enumerate((16, 24, 32)):
        p = ph + i * 2.1 + math.pi
        parts.append(P(w, h, line([(x, 25), (x + 2 + math.sin(p) * 2, 29), (x + 4 + math.sin(p) * 3, 33)], 2), body,
                       z=4))
    return parts + eye(40, 19, iris=(255, 220, 120), shine=(255, 255, 230), r=1.0)


def flamingo(t):
    w, h = canvas(44, 64)
    ph = t * TAU
    pink = fur((150, 46, 80), (255, 190, 206), (120, 30, 70))
    leg_c = fur((150, 56, 80), (246, 130, 150))
    sway = math.sin(ph) * 1.5
    lift = max(0.0, math.sin(ph)) * 4                # the other leg tucks up and down
    parts = [
        P(w, h, line([(20, 36), (22, 49), (21, 62)], 2), leg_c, z=1),
        P(w, h, line([(24, 36), (26, 46 - lift), (21, 50 - lift)], 2), leg_c, z=0.5),
        P(w, h, ell(21, 32, 12, 7), pink, z=2, height=6, noise=0.06, seed=18),
        P(w, h, poly([(8, 30), (2, 27), (10, 26)]), fur((30, 20, 24), (110, 60, 70)), z=2.4, height=1.5),  # black tail tips
        P(w, h, line([(29, 29), (34, 22), (31, 14 + sway), (26, 8 + sway), (29, 3 + sway)], 3), pink, z=3, height=1.6),
        P(w, h, ell(31, 4 + sway, 4, 3), pink, z=4, height=2.5, seed=19),
        P(w, h, poly([(34, 3 + sway), (40, 6 + sway), (39, 10 + sway), (35, 7 + sway)]), fur((220, 200, 190), (250, 240, 236)),
          z=4.5, height=1.5),                                                                              # bent beak
        P(w, h, poly([(39, 8 + sway), (40, 6 + sway), (40, 11 + sway), (38, 10 + sway)]), NOSE, z=4.6, flat=True),
    ]
    return parts + eye(32, 3 + sway, r=0.9)


def marsh_heron(t):
    w, h = canvas(48, 64)
    ph = t * TAU
    grey = fur((76, 92, 94), (238, 242, 236), (40, 50, 70))
    dark = fur((30, 36, 40), (100, 110, 112))
    legc = fur((70, 74, 60), (160, 160, 120))
    step = math.sin(ph) * 3
    neck = math.sin(ph) * 1.5
    parts = [
        P(w, h, line([(18, 38), (18 + step * 0.4, 51), (16 + step, 62)], 2), legc, z=0.5),
        P(w, h, line([(22, 38), (22 - step * 0.4, 51), (24 - step, 62)], 2), legc, z=1),
        P(w, h, poly([(8, 34), (12, 26), (24, 25), (32, 31), (26, 40), (14, 40)]), grey, z=2, height=6, noise=0.07, seed=20),
        P(w, h, poly([(9, 35), (2, 40), (10, 38)]), dark, z=2.2, height=1.5),                                # tail
        P(w, h, line([(14, 30), (26, 31)], 2), dark, z=2.3, flat=True),                                       # wing edge
        P(w, h, line([(28, 28), (31, 20), (28 + neck, 13), (31 + neck, 7)], 3), grey, z=3, height=1.6),
        P(w, h, ell(32 + neck, 6, 4, 3), grey, z=4, height=2.5, seed=21),
        P(w, h, line([(31 + neck, 3), (24 + neck, 1), (21 + neck, 3)], 1), dark, z=4.2, flat=True),           # crest
        P(w, h, poly([(35 + neck, 5), (46 + neck, 7), (35 + neck, 8)]), fur((150, 120, 30), (250, 210, 90)), z=4.5,
          height=1),                                                                                            # yellow bill
    ]
    return parts + eye(33 + neck, 5, iris=(200, 160, 40), r=0.9)


def ice_penguin(t):
    w, h = canvas(40, 50)
    ph = t * TAU
    rock = math.sin(ph) * 2.2                     # a waddle: the whole bird rocks side to side
    black = fur((10, 12, 22), (86, 96, 122), (20, 30, 60))
    white = fur((150, 160, 182), (255, 255, 255))
    orange = fur((170, 80, 10), (255, 186, 70))
    X = lambda x, y: x + rock * (1 - y / 50)
    return [
        P(w, h, many(ell(X(14, 46), 46, 5, 2.5), ell(X(26, 46), 46 - max(0.0, math.sin(ph)) * 1.5, 5, 2.5)), orange,
          z=0, height=1.5),                                                                                    # feet
        P(w, h, poly([(X(8, 30), 30), (X(12, 10), 10), (X(20, 3), 3), (X(28, 10), 10), (X(32, 30), 30),
                       (X(28, 44), 44), (X(12, 44), 44)]), black, z=2, height=8, noise=0.05, seed=22),
        P(w, h, poly([(X(12, 22), 22), (X(16, 14), 14), (X(24, 14), 14), (X(28, 22), 22), (X(27, 40), 40),
                      (X(13, 40), 40)]), white, z=3, height=6, noise=0.03),                                    # white front
        P(w, h, poly([(X(8, 22), 22), (X(3, 34), 34), (X(8, 33), 33)]), black, z=3.5, height=2),               # flippers
        P(w, h, poly([(X(32, 22), 22), (X(37, 34), 34), (X(32, 33), 33)]), black, z=3.5, height=2),
        P(w, h, poly([(X(18, 13), 13), (X(22, 13), 13), (X(20, 17), 17)]), orange, z=4, height=1),             # beak
    ] + eye(X(16, 10), 10, iris=(10, 10, 14), r=1.2) + eye(X(24, 10), 10, iris=(10, 10, 14), r=1.2)


def songbird(t):
    w, h = canvas(40, 30)
    ph = t * TAU
    red = fur((100, 22, 18), (240, 110, 80), (80, 10, 30))
    breast = fur((170, 80, 40), (255, 186, 124))
    dark = fur((60, 20, 18), (150, 50, 40))
    hop = -max(0.0, math.sin(ph)) * 2.5
    flap = math.sin(ph * 2) * 3
    y = lambda v: v + hop
    return [
        P(w, h, many(line([(18, y(22)), (17, 28)], 1), line([(22, y(22)), (23, 28)], 1)),
          fur((60, 40, 20), (140, 100, 60)), z=0, flat=True),                                                  # legs
        P(w, h, poly([(9, y(14)), (1, y(10)), (3, y(17)), (10, y(19))]), dark, z=1, height=1.5),               # tail
        P(w, h, ell(18, y(16), 10, 6.5), red, z=2, height=5, noise=0.05, seed=23),
        P(w, h, ell(22, y(18), 6, 4), breast, z=2.4, height=3),
        P(w, h, poly([(12, y(13)), (20, y(11 - flap)), (24, y(15)), (16, y(18))]), dark, z=3, height=2),       # wing
        P(w, h, circ(27, y(10), 5), red, z=4, height=3.5, seed=24),
        P(w, h, poly([(31, y(9)), (36, y(11)), (31, y(12))]), fur((150, 110, 40), (250, 210, 110)), z=4.5, height=1),
        P(w, h, poly([(24, y(6)), (26, y(1)), (28, y(6))]), red, z=4.2, height=1.5),                           # crest
    ] + eye(29, y(9), r=1.0)


def owl(t):
    w, h = canvas(44, 52)
    ph = t * TAU
    brown = fur((48, 30, 16), (172, 126, 78), (40, 20, 30))
    disc = fur((140, 104, 64), (238, 212, 162))
    chest = fur((150, 124, 90), (240, 222, 186))
    bark = fur((40, 28, 18), (120, 88, 56))
    blink = 0.25 if 0.5 <= t < 0.75 else 1.0        # one blink per cycle
    tilt = math.sin(ph) * 1.2
    parts = [
        P(w, h, poly([(0, 44), (44, 42), (44, 48), (0, 50)]), bark, z=0, height=2, noise=0.15),               # branch
        P(w, h, poly([(10, 44), (8, 24), (12, 14), (32, 14), (36, 24), (34, 44)]), brown, z=2, height=7, noise=0.08, seed=25),
        P(w, h, ell(22, 31, 9, 11), chest, z=2.5, height=4, noise=0.05),
        P(w, h, many(*[line([(15 + k * 3, 24 + (k % 2) * 6), (17 + k * 3, 26 + (k % 2) * 6)], 1) for k in range(5)],
                     *[line([(15 + k * 3, 32 + (k % 2) * 5), (17 + k * 3, 34 + (k % 2) * 5)], 1) for k in range(5)]),
          brown, z=2.6, flat=True),                                                                          # chest bars
        P(w, h, poly([(9, 22), (6, 34), (10, 42), (13, 30)]), brown, z=3, height=2.5),                        # wings
        P(w, h, poly([(35, 22), (38, 34), (34, 42), (31, 30)]), brown, z=3, height=2.5),
        P(w, h, many(ell(16 + tilt, 14, 7, 6.5), ell(28 + tilt, 14, 7, 6.5)), disc, z=4, height=3.5),          # facial disc
        P(w, h, many(poly([(11 + tilt, 9), (12 + tilt, 2), (17 + tilt, 8)]), poly([(33 + tilt, 9), (32 + tilt, 2), (27 + tilt, 8)])),
          brown, z=4.2, height=1.5),                                                                         # ear tufts
        P(w, h, poly([(21 + tilt, 16), (23 + tilt, 16), (22 + tilt, 20)]), fur((150, 100, 30), (240, 180, 70)), z=4.8,
          height=1),
        P(w, h, many(line([(16, 44), (16, 47)], 1), line([(20, 44), (20, 47)], 1), line([(25, 44), (25, 47)], 1),
                     line([(29, 44), (29, 47)], 1)), fur((150, 110, 40), (230, 180, 80)), z=5, flat=True),     # talons
    ]
    for ex in (16, 28):
        parts.append(P(w, h, ell(ex + tilt, 13, 3.6, 3.6 * blink), fur((200, 130, 20), (255, 214, 90)), z=5,
                       flat=True, emit=(255, 196, 70)))
        if blink > 0.5:
            parts.append(P(w, h, circ(ex + tilt, 13, 1.5), [(14, 10, 6)] * 5, z=5.2, flat=True))
            parts.append(P(w, h, dot(ex - 1 + tilt, 12), [(255, 250, 220)] * 5, z=5.3, flat=True))
    return parts


def cave_moth(t):
    w, h = canvas(60, 44)
    ph = t * TAU
    flap = 0.55 + 0.45 * abs(math.cos(ph))          # wings fold and open
    wing = fur((110, 100, 150), (246, 242, 255), (60, 40, 110))
    edge = fur((150, 130, 200), (210, 196, 240))
    spot = fur((80, 30, 120), (190, 110, 230))
    body = fur((90, 76, 130), (200, 180, 230))
    cx, cy = 30, 22

    def wings(sign):
        top = [(cx, cy - 2), (cx + sign * 26 * flap, cy - 16 * flap), (cx + sign * 29 * flap, cy - 4), (cx + sign * 8, cy + 2)]
        bot = [(cx, cy + 2), (cx + sign * 22 * flap, cy + 8), (cx + sign * 16 * flap, cy + 18), (cx + sign * 4, cy + 10)]
        return top, bot
    parts = []
    for sign in (-1, 1):
        top, bot = wings(sign)
        parts += [P(w, h, poly(top), wing, z=1, height=4, noise=0.08, seed=26 + sign),
                  P(w, h, poly(bot), edge, z=0.8, height=3, noise=0.08),
                  P(w, h, ell(cx + sign * 15 * flap, cy - 6 * flap, 3.5 * flap + 1, 3), spot, z=1.5, flat=True),
                  P(w, h, circ(cx + sign * 15 * flap, cy - 6 * flap, 1.2), [(250, 240, 255)] * 5, z=1.6, flat=True)]
    parts += [
        P(w, h, ell(cx, cy + 4, 3.2, 10), body, z=3, height=3, noise=0.15, seed=28),                       # fuzzy body
        P(w, h, many(line([(cx - 1, cy - 6), (cx - 6, cy - 14), (cx - 8, cy - 14)], 1),
                     line([(cx + 1, cy - 6), (cx + 6, cy - 14), (cx + 8, cy - 14)], 1)), body, z=3.2, flat=True),
        P(w, h, many(circ(cx - 1.5, cy - 5, 1), circ(cx + 1.5, cy - 5, 1)), [(140, 60, 180)] * 5, z=3.5, flat=True),
    ]
    return parts


def mushroom_folk(t):
    w, h = canvas(40, 44)
    ph = t * TAU
    cap = fur((90, 14, 14), (244, 84, 72), (70, 10, 40))
    stalk = fur((150, 128, 98), (252, 244, 226))
    gills = fur((170, 150, 120), (230, 210, 180))
    waddle = math.sin(ph) * 1.5
    squash = 1 + math.sin(ph * 2) * 0.06
    parts = [
        P(w, h, many(ell(14 + waddle, 41, 4, 2.4), ell(26 + waddle, 41 - max(0.0, math.sin(ph)) * 2, 4, 2.4)), stalk, z=0,
          height=1.5),
        P(w, h, poly([(11, 40), (12, 22), (28, 22), (29, 40)]), stalk, z=2, height=6, noise=0.06, seed=29),
        P(w, h, ell(20, 21, 13, 3), gills, z=2.5, height=1.5),
        P(w, h, poly([(2, 20), (6, 9 / squash), (14, 3 / squash), (26, 3 / squash), (34, 9 / squash), (38, 20)]), cap,
          z=3, height=7, noise=0.05, seed=30),
        P(w, h, many(circ(11, 11, 2.2), circ(22, 7, 2.6), circ(30, 13, 1.8), circ(17, 15, 1.4)), WHITE, z=3.5,
          height=1.5, dome=0.3),                                                                              # cap spots
        P(w, h, line([(16, 34), (18, 35), (22, 35), (24, 34)], 1), [(150, 90, 80)] * 5, z=4, flat=True),      # smile
        P(w, h, many(ell(14, 32, 1.5, 1), ell(26, 32, 1.5, 1)), [(240, 150, 150)] * 5, z=4, flat=True),       # cheeks
    ]
    return parts + eye(16, 28, r=1.3) + eye(24, 28, r=1.3)


def desert_lizard(t):
    w, h = canvas(50, 32)
    ph = t * TAU
    skin = fur((70, 80, 30), (214, 226, 148), (90, 60, 20))
    belly = fur((150, 150, 90), (240, 236, 180))
    spots = fur((90, 70, 30), (170, 130, 60))
    pushup = max(0.0, math.sin(ph)) * 2.5           # the classic lizard push-up
    tail = math.sin(ph) * 2
    parts = [
        P(w, h, line([(14, 22), (7, 22), (3, 18 + tail), (5, 12 + tail), (10, 11 + tail)], 3), skin, z=0, height=1.5),
        P(w, h, line([(17, 23), (12, 28), (8, 29)], 3), skin, z=0.5),
        P(w, h, line([(32, 22 - pushup), (36, 28), (40, 29)], 3), skin, z=0.5),
        P(w, h, ell(24, 20 - pushup * 0.5, 13, 6), skin, z=2, height=5, noise=0.08, seed=31),
        P(w, h, ell(25, 24 - pushup * 0.5, 9, 2), belly, z=2.2, height=1),
        P(w, h, many(circ(18, 18, 1.6), circ(24, 16 - pushup * 0.5, 1.6), circ(30, 17 - pushup * 0.6, 1.4),
                     circ(21, 22 - pushup * 0.5, 1.2)), spots, z=2.5, flat=True),
        P(w, h, poly([(34, 15 - pushup), (43, 12 - pushup), (49, 16 - pushup), (44, 20 - pushup), (35, 22 - pushup)]),
          skin, z=3, height=3.5, seed=32),
        P(w, h, line([(20, 24), (23, 29), (27, 30)], 3), skin, z=3.5),
        P(w, h, line([(33, 22 - pushup), (31, 29), (28, 30)], 3), skin, z=3.5),
    ]
    return parts + eye(43, 14 - pushup, iris=(40, 34, 14), r=1.2)


def moonpetal(t):
    w, h = canvas(36, 48)
    ph = t * TAU
    sway = math.sin(ph) * 1.2
    pulse = 0.5 + 0.5 * math.sin(ph)
    petal = fur((80, 100, 176), (236, 244, 255), (40, 40, 120))
    inner = fur((150, 170, 230), (255, 255, 255))
    core = fur((200, 160, 60), (255, 246, 190))
    stem = fur((30, 70, 40), (110, 170, 110))
    cx, cy = 18 + sway, 15
    parts = [
        P(w, h, line([(18, 47), (18 + sway * 0.5, 34), (cx, cy + 4)], 2), stem, z=0, height=1),
        P(w, h, many(poly([(18, 40), (8, 34), (6, 38), (14, 42)]), poly([(18, 36), (28, 30), (30, 34), (22, 39)])), stem,
          z=0.5, height=2),
    ]
    for k in range(6):
        a = k * TAU / 6 + 0.3
        px_, py_ = cx + math.cos(a) * 7, cy + math.sin(a) * 6.5
        parts.append(P(w, h, ell(px_, py_, 5, 4), petal, z=2 + (k % 2) * 0.2, height=3, seed=33 + k,
                       emit=(int(130 + 60 * pulse), int(170 + 50 * pulse), 255)))
    parts += [P(w, h, ell(cx, cy, 5, 4.5), inner, z=3, height=2.5, emit=(200, 220, 255)),
              P(w, h, circ(cx, cy, 2.4), core, z=3.5, height=1.5, emit=(255, 240, 170))]
    return parts


def ghostbloom(t):
    w, h = canvas(36, 48)
    ph = t * TAU
    sway = math.sin(ph) * 1.0
    pulse = 0.5 + 0.5 * math.sin(ph)
    bell = fur((40, 120, 90), (226, 255, 238), (20, 70, 80))
    stem = fur((26, 64, 44), (96, 150, 110))
    drop = fur((150, 230, 190), (240, 255, 248))
    cx = 18 + sway
    parts = [
        P(w, h, line([(18, 47), (18, 30), (cx + 2, 16), (cx - 2, 10)], 2), stem, z=0, height=1),
        P(w, h, many(poly([(18, 42), (9, 38), (8, 42), (15, 45)]), poly([(18, 38), (27, 34), (28, 38), (21, 41)])), stem,
          z=0.5, height=2),
        P(w, h, poly([(cx - 9, 22), (cx - 7, 12), (cx - 2, 7), (cx + 4, 8), (cx + 8, 13), (cx + 9, 22),
                      (cx + 5, 20), (cx + 2, 23), (cx - 2, 21), (cx - 5, 23)]), bell, z=2, height=5, noise=0.04, seed=40,
          emit=(110, int(220 + 30 * pulse), 170), alpha=210),
        P(w, h, ell(cx, 13, 3, 4), drop, z=2.5, height=2, alpha=230, emit=(200, 255, 225)),
        P(w, h, circ(cx - 3, 26 + pulse * 3, 1.3), drop, z=3, flat=True, emit=(180, 255, 210)),            # dripping light
        P(w, h, circ(cx + 4, 25 + (1 - pulse) * 3, 1.0), drop, z=3, flat=True, emit=(180, 255, 210)),
    ]
    return parts


CREATURES = {
    "forest_hare": forest_hare, "snow_fox": snow_fox, "deer": deer, "elk": elk, "mountain_goat": mountain_goat,
    "scrap_rat": scrap_rat, "tortoise": tortoise, "tree_frog": tree_frog, "fire_beetle": fire_beetle,
    "flamingo": flamingo, "marsh_heron": marsh_heron, "ice_penguin": ice_penguin, "songbird": songbird, "owl": owl,
    "cave_moth": cave_moth, "mushroom_folk": mushroom_folk, "desert_lizard": desert_lizard,
    "moonpetal": moonpetal, "ghostbloom": ghostbloom,
}
GLOWING = {"moonpetal", "ghostbloom", "owl"}  # night-only: their emissive layer shines through the dark


def _bbox(surfs):
    box = None
    for s in surfs:
        r = s.get_bounding_rect()
        if r.w and r.h:
            box = r if box is None else box.union(r)
    return box.inflate(2, 2) if box else None


def paint(kind):
    fn = CREATURES[kind]
    sprites, glows = [], []
    for i in range(FRAMES):
        parts = fn(i / FRAMES)
        s, g = N.render(parts, W_, H_)
        sprites.append(s)
        glows.append(N.soft_glow(g) if kind in GLOWING else g)
    box = _bbox(sprites).clip(pygame.Rect(0, 0, W_, H_))
    crop = lambda s: s.subsurface(box).copy()
    sprites = [crop(s) for s in sprites]
    glows = [crop(g) for g in glows]
    up = lambda s: pygame.transform.scale(s, (s.get_width() * N.UP, s.get_height() * N.UP))
    pygame.image.save(up(sprites[0]), os.path.join(OUT, f"enemy_{kind}.png"))
    pygame.image.save(up(N.strip(sprites)), os.path.join(OUT, f"enemy_{kind}_anim.png"))
    if kind in GLOWING:
        pygame.image.save(up(N.strip(glows)), os.path.join(OUT, f"enemy_{kind}_glow.png"))
    print(f"painted {kind}: {box.w}x{box.h} logical, {FRAMES} frames" + (" + glow" if kind in GLOWING else ""))
    return sprites


def contact_sheet(path, kinds):
    """Every creature: in-game size (48 px longest side) on grass and on a dark floor, a 3x zoom,
    and the 4 animation frames."""
    rows = []
    for k in kinds:
        still = pygame.image.load(os.path.join(OUT, f"enemy_{k}.png"))
        strip_ = pygame.image.load(os.path.join(OUT, f"enemy_{k}_anim.png"))
        fw = still.get_width()
        frames = [strip_.subsurface((i * fw, 0, fw, still.get_height())) for i in range(strip_.get_width() // fw)]
        rows.append((k, still, frames))
    cell_h = 156
    sheet = pygame.Surface((1180, cell_h * len(rows)))
    font = pygame.font.SysFont("consolas", 14, bold=True)
    for i, (k, still, frames) in enumerate(rows):
        y = i * cell_h
        sheet.fill((70, 112, 58) if i % 2 == 0 else (60, 98, 50), (0, y, 1180, cell_h))
        sheet.fill((18, 18, 24), (110, y, 110, cell_h))
        w, h = still.get_size()
        f = 48 / max(w, h)
        small = pygame.transform.smoothscale(still, (max(1, int(w * f)), max(1, int(h * f))))
        sheet.blit(small, (55 - small.get_width() // 2, y + 70 - small.get_height() // 2))
        sheet.blit(small, (165 - small.get_width() // 2, y + 70 - small.get_height() // 2))
        f3 = 144 / max(w, h)
        big = pygame.transform.scale(still, (int(w * f3), int(h * f3)))
        sheet.blit(big, (240, y + 6))
        for j, fr in enumerate(frames):
            fz = 96 / max(w, h)
            sheet.blit(pygame.transform.scale(fr, (int(w * fz), int(h * fz))), (420 + j * 105, y + 30))
        for j, fr in enumerate(frames):  # in-game-size frames too
            sheet.blit(pygame.transform.smoothscale(fr, small.get_size()), (850 + j * 60, y + 70 - small.get_height() // 2))
        sheet.blit(font.render(k, True, (255, 255, 255)), (6, y + 4))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pygame.image.save(sheet, path)
    print("contact sheet ->", path)


def main(argv):
    pygame.display.set_mode((8, 8))
    kinds = argv or list(CREATURES)
    for k in kinds:
        paint(k)
    contact_sheet(os.path.join(REPO, "screenshots", "2026-10-08", "art_wildlife", "sheet.png"), list(CREATURES)
                  if not argv else kinds)


if __name__ == "__main__":
    main(sys.argv[1:])
