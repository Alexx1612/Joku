"""
Paints the night-horror mobs (Lantern-Eater, Shade Stalker, Night Mimic, Hollow Watcher,
The Red Harvester, fireflies) and the Ghost Merchant: a still PNG, an animated move strip,
an attack strip and an emissive "glow" layer for each. Wholly original.

How: each creature is a stack of hand-shaped PARTS (pygame polygons / ellipses / lines on
a small logical canvas, posed per animation frame). Every part gets automatic lighting:
  * a height field from its own silhouette (distance to the edge) -> a soft dome normal
  * a key light from the top-left, a cold moon rim light from the back-right
  * a 5-step colour ramp per material, ordered (Bayer) dithering between steps
  * subtle hashed surface noise (skin, bark, cloth)
then a selective outline (dark where a front part overlaps a back one, black round the
silhouette). Logical canvas 64x64 (bosses 160x104), saved at 2x - the game shows night
mobs at ~65 px, so this is close to 1:1 and every painted pixel is visible.

Run: python tools/paint_night_sprites.py   (writes into assets/sprites/v0.2/enemies/)
"""
import math
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "sprites", "v0.2", "enemies")
UP = 2
OUTLINE = (10, 6, 12)
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
KEY = (-0.62, -0.78)            # key light from the top-left
RIM = (0.72, -0.69)             # moon rim from the back-right


def _h(x, y, s=0):
    n = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def ramp(dark, light, steps=5, warm_shadow=None):
    """A colour ramp dark -> light (hue-shifted: shadows lean `warm_shadow` if given)."""
    out = []
    for i in range(steps):
        t = i / (steps - 1)
        c = [dark[k] + (light[k] - dark[k]) * t for k in range(3)]
        if warm_shadow is not None:
            w = (1 - t) * 0.25
            c = [c[k] * (1 - w) + warm_shadow[k] * w for k in range(3)]
        out.append(tuple(int(max(0, min(255, v))) for v in c))
    return out


class Part:
    def __init__(self, mask, ramp_, z=0, rim=None, height=4.0, noise=0.05, flat=False, emit=None,
                 seed=0, dome=0.45, alpha=255):
        self.mask, self.ramp, self.z, self.rim = mask, ramp_, z, rim
        self.height, self.noise, self.flat, self.emit = height, noise, flat, emit
        self.seed, self.dome, self.alpha = seed, dome, alpha


def shape(w, h, fn):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    fn(s, (255, 255, 255, 255))
    return s


def _distance(mask, w, h):
    inside = [[mask.get_at((x, y))[3] > 0 for x in range(w)] for y in range(h)]
    INF = 10 ** 6
    d = [[INF if inside[y][x] else 0 for x in range(w)] for y in range(h)]
    from collections import deque
    q = deque()
    for y in range(h):
        for x in range(w):
            if inside[y][x] and any(not (0 <= x + dx < w and 0 <= y + dy < h) or not inside[y + dy][x + dx]
                                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                d[y][x] = 1
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and d[ny][nx] > d[y][x] + 1:
                d[ny][nx] = d[y][x] + 1
                q.append((nx, ny))
    return inside, d


def render(parts, w, h):
    """Lights, dithers and outlines a stack of parts -> (sprite, glow) logical surfaces."""
    color = [[None] * w for _ in range(h)]
    owner = [[-1] * w for _ in range(h)]
    glow = pygame.Surface((w, h), pygame.SRCALPHA)
    order = sorted(range(len(parts)), key=lambda i: parts[i].z)
    for i in order:
        p = parts[i]
        inside, d = _distance(p.mask, w, h)
        R = p.height
        hh = [[min(d[y][x], R) / R if inside[y][x] else 0.0 for x in range(w)] for y in range(h)]
        n = len(p.ramp)
        for y in range(h):
            for x in range(w):
                if not inside[y][x]:
                    continue
                if p.flat:
                    v = 0.6
                else:
                    gx = (hh[y][min(w - 1, x + 1)] - hh[y][max(0, x - 1)]) * 0.5
                    gy = (hh[min(h - 1, y + 1)][x] - hh[max(0, y - 1)][x]) * 0.5
                    lit = -(gx * KEY[0] + gy * KEY[1]) * 3.2           # faces toward the key light
                    v = 0.42 + p.dome * hh[y][x] + lit
                    v += (_h(x, y, p.seed) - 0.5) * 2 * p.noise
                thr = (BAYER[y % 4][x % 4] + 0.5) / 16.0 - 0.5
                idx = int(max(0, min(n - 1, round(v * (n - 1) + thr * 0.9))))
                c = p.ramp[idx]
                if p.rim is not None and d[y][x] <= 1 and not p.flat:
                    gx = hh[y][min(w - 1, x + 1)] - hh[y][max(0, x - 1)]
                    gy = hh[min(h - 1, y + 1)][x] - hh[max(0, y - 1)][x]
                    ln = math.hypot(gx, gy) or 1.0
                    out_x, out_y = -gx / ln, -gy / ln
                    if out_x * RIM[0] + out_y * RIM[1] > 0.35:
                        c = p.rim
                color[y][x] = (c, p.alpha)
                owner[y][x] = i
                if p.emit is not None:
                    glow.set_at((x, y), (*p.emit, 255))
    spr = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            if color[y][x] is None:
                continue
            c, a = color[y][x]
            me = owner[y][x]
            # selective outline: where a front part sits over a back part, darken the front's edge
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and owner[ny][nx] != -1 and owner[ny][nx] != me \
                        and parts[owner[ny][nx]].z < parts[me].z and not parts[me].flat:
                    c = tuple(int(v * 0.55) for v in parts[me].ramp[0])
                    break
            spr.set_at((x, y), (*c, a))
    edge = [(x, y) for y in range(h) for x in range(w)  # silhouette outline (computed first, then drawn)
            if color[y][x] is None and any(0 <= x + dx < w and 0 <= y + dy < h and color[y + dy][x + dx] is not None
                                           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
    for (x, y) in edge:
        spr.set_at((x, y), (*OUTLINE, 255))
    return spr, glow


def soft_glow(glow, radius=3):
    """Emissive pixels -> a soft halo (for the additive pass over the darkness)."""
    w, h = glow.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    pts = [(x, y, glow.get_at((x, y))) for y in range(h) for x in range(w) if glow.get_at((x, y))[3] > 0]
    for (x, y, c) in pts:
        for r in range(radius, 0, -1):
            f = (1 - r / (radius + 1)) ** 2 * 0.35
            col = (int(c[0] * f), int(c[1] * f), int(c[2] * f))
            for yy in range(y - r, y + r + 1):
                for xx in range(x - r, x + r + 1):
                    if 0 <= xx < w and 0 <= yy < h and (xx - x) ** 2 + (yy - y) ** 2 <= r * r:
                        o = out.get_at((xx, yy))
                        out.set_at((xx, yy), (min(255, o[0] + col[0]), min(255, o[1] + col[1]),
                                              min(255, o[2] + col[2]), 255))
    for (x, y, c) in pts:
        out.set_at((x, y), (c[0], c[1], c[2], 255))
    return out


def strip(frames):
    w, h = frames[0].get_size()
    s = pygame.Surface((w * len(frames), h), pygame.SRCALPHA)
    for i, f in enumerate(frames):
        s.blit(f, (i * w, 0))
    return s


def save_set(name, still, moves, attacks, glow_moves, glow_attacks, out=OUT):
    up = lambda s: pygame.transform.scale(s, (s.get_width() * UP, s.get_height() * UP))
    pygame.image.save(up(still), os.path.join(out, f"enemy_{name}.png"))
    pygame.image.save(up(strip(moves)), os.path.join(out, f"enemy_{name}_anim.png"))
    pygame.image.save(up(strip(attacks)), os.path.join(out, f"enemy_{name}_attack.png"))
    pygame.image.save(up(strip(glow_moves)), os.path.join(out, f"enemy_{name}_glow.png"))
    pygame.image.save(up(strip(glow_attacks)), os.path.join(out, f"enemy_{name}_glow_attack.png"))


def build(name, pose_fn, w, h, moves, attacks):
    mv, gm, at, ga = [], [], [], []
    for i in range(moves):
        s, g = render(pose_fn(i / moves, False), w, h)
        mv.append(s)
        gm.append(soft_glow(g))
    for i in range(attacks):
        s, g = render(pose_fn(i / max(1, attacks - 1), True), w, h)
        at.append(s)
        ga.append(soft_glow(g))
    save_set(name, mv[0], mv, at, gm, ga)
    print(f"painted {name}: {moves} move + {attacks} attack frames")


# ------------------------------------------------------------- materials
SKIN = ramp((34, 28, 30), (176, 160, 140), warm_shadow=(60, 20, 30))      # grey, sickly, bruised shadows
SKIN_D = ramp((22, 18, 22), (120, 106, 96))
BONE = ramp((70, 62, 52), (240, 232, 210))
MAW = ramp((26, 4, 10), (120, 24, 40))
GUM = ramp((70, 14, 26), (200, 80, 96))
LURE = ramp((180, 110, 30), (255, 250, 200))
SHADOW = ramp((4, 4, 8), (46, 40, 74))
SHADOW_RIM = (128, 120, 210)
WOOD = ramp((40, 22, 10), (170, 112, 58))
IRON = ramp((24, 24, 30), (150, 150, 166))
GOLDR = ramp((90, 60, 10), (255, 226, 120))
TONGUE = ramp((70, 10, 40), (226, 96, 150))
SCLERA = ramp((110, 96, 90), (250, 244, 232))
IRIS = ramp((90, 4, 10), (255, 70, 60))
ROOT = ramp((20, 12, 10), (110, 76, 52))
FLESH = ramp((50, 10, 16), (170, 70, 70))
CLOAK = ramp((26, 2, 6), (176, 22, 34))
CLOAK_D = ramp((12, 0, 2), (90, 8, 16))
STEEL = ramp((40, 40, 50), (236, 236, 246))
HAFT = ramp((24, 14, 10), (120, 84, 56))
GHOST = ramp((30, 60, 70), (170, 230, 220))
MOON_RIM = (190, 210, 255)


def P(w, h, fn, *a, **k):
    return Part(shape(w, h, fn), *a, **k)


# ------------------------------------------------------------- Lantern-Eater (64x64)
def lantern_eater(t, attack):
    """Side-on, facing right: an emaciated hunched thing - arched knobbed spine, ribs, spindly
    reverse-jointed legs, long arms planted forward, a jutting angler head with needle teeth and a
    fleshy lure arcing over it to dangle a glowing bulb right in front of the open maw."""
    W = H = 64
    ph = t * math.tau
    br = math.sin(ph) * 1.0                      # breathing
    sway = math.sin(ph) * (2.5 if not attack else 1.0)
    jaw = (3 + 7 * t) if attack else 2.5 + math.sin(ph) * 0.8
    lunge = 3 * t if attack else 0.0
    X = lambda x: x + lunge
    parts = []
    # far limbs (darker, behind)
    parts.append(P(W, H, lambda s, c: (pygame.draw.lines(s, c, False, [(X(20), 40), (X(15), 50), (X(19), 61)], 3),
                                       pygame.draw.lines(s, c, False, [(X(38), 32), (X(43), 46), (X(44), 61)], 3)),
                   SKIN_D, z=0, height=1.5, noise=0.1))
    # torso: arched, gaunt
    torso = [(X(8), 42), (X(11), 30), (X(20), 21 - br), (X(31), 20 - br), (X(40), 26), (X(41), 36), (X(30), 42 + br * 0.5),
             (X(16), 45)]
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, torso), SKIN, z=2, rim=MOON_RIM, height=6, noise=0.1,
                   seed=1))
    parts.append(P(W, H, lambda s, c: [pygame.draw.line(s, c, (X(17 + k * 4), 31 + k * 0.3 - br), (X(19 + k * 4), 41), 1)
                                       for k in range(5)], SKIN_D, z=2.2, flat=True))          # ribs
    parts.append(P(W, H, lambda s, c: [pygame.draw.circle(s, c, (int(X(13 + k * 5.2)), int(27 - abs(k - 2.6) * -0.0
                                                                                        - (6 - abs(k - 2.4) * 2.2) - br)), 2)
                                       for k in range(6)], BONE, z=2.5, height=1.5, rim=MOON_RIM))  # spine knobs
    # near hind leg (reverse knee)
    parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, [(X(14), 40), (X(8), 50), (X(13), 61), (X(17), 62)], 4),
                   SKIN, z=3, rim=MOON_RIM, height=2, noise=0.08))
    # neck + jutting head
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(X(36), 24), (X(46), 19), (X(55), 21), (X(58), 27),
                                                                 (X(52), 31), (X(42), 31)]),
                   SKIN, z=4, rim=MOON_RIM, height=4, noise=0.09, seed=2))
    # the hanging lower jaw + the maw
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(X(43), 30), (X(57), 28), (X(56), 31 + jaw), (X(46), 33 + jaw)]),
                   MAW, z=4.5, flat=True))
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(X(44), 32 + jaw), (X(57), 30 + jaw), (X(55), 34 + jaw),
                                                                 (X(45), 35 + jaw)]),
                   SKIN_D, z=5, height=1.5, rim=MOON_RIM))
    teeth = []
    for k in range(6):
        x = X(45 + k * 2.1)
        teeth.append([(x, 29.5 - k * 0.15), (x + 1.2, 29.5 - k * 0.15), (x + 0.6, 32.5)])
        teeth.append([(x + 0.4, 32 + jaw), (x + 1.6, 32 + jaw - 0.2), (x + 1.0, 29.5 + jaw)])
    parts.append(P(W, H, lambda s, c: [pygame.draw.polygon(s, c, tr) for tr in teeth], BONE, z=6, flat=True))
    # a tiny milky eye
    parts.append(P(W, H, lambda s, c: s.set_at((int(X(51)), 23), c), [(255, 246, 220)] * 5, z=7, flat=True,
                   emit=(255, 236, 190)))
    # near arm planted forward (long, spindly, knuckles down)
    parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, [(X(37), 30), (X(46), 44), (X(49), 60), (X(53), 61)], 3),
                   SKIN, z=6.5, rim=MOON_RIM, height=1.5, noise=0.08))
    # the lure: a fleshy stalk arcing from the brow over and forward, the bulb dangling before the jaw
    bx, by = X(60) + sway * 0.4, 33 + (2 if attack else 0) + abs(sway) * 0.3
    stalk = [(X(47), 19), (X(45), 10), (X(50), 4), (X(57), 5), (X(61), 11), (bx, by - 5)]
    parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, stalk, 2), SKIN_D, z=8, height=1, rim=MOON_RIM))
    bulb = 3 if not attack else 3 + int(2 * t)
    parts.append(P(W, H, lambda s, c: pygame.draw.circle(s, c, (int(bx), int(by)), bulb), LURE, z=9, height=2.5,
                   emit=(255, 214, 120), dome=0.6))
    return parts


# ------------------------------------------------------------- Shade Stalker (64x64)
def shade_stalker(t, attack):
    W = H = 64
    ph = t * math.tau
    lean = math.sin(ph) * 1.5
    parts = []
    # smoky tattered lower body - wisps trail and curl
    wisps = []
    for k in range(6):
        x0 = 22 + k * 4
        off = math.sin(ph + k * 1.3) * 3
        wisps.append([(x0, 44), (x0 + 3, 44), (x0 + 1 + off, 58 + (k % 3) * 2), (x0 - 1 + off * 0.6, 54)])
    parts.append(P(W, H, lambda s, c: [pygame.draw.polygon(s, c, wp) for wp in wisps], SHADOW, z=1, rim=SHADOW_RIM,
                   height=2, noise=0.12, seed=3))
    # a tall, too-thin torso
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(27 + lean, 14), (37 + lean, 14), (40, 30), (38, 46),
                                                                 (26, 46), (24, 30)]),
                   SHADOW, z=2, rim=SHADOW_RIM, height=5, noise=0.1, seed=4))
    # arms down to the knees (or flung wide, claws spread, on attack)
    if attack:
        a = 0.5 + t * 0.8
        la = [(26, 18), (16 - 3 * a, 22 - 6 * a), (10 - 2 * a, 8 - 4 * a)]
        ra = [(38, 18), (48 + 3 * a, 22 - 6 * a), (54 + 2 * a, 8 - 4 * a)]
    else:
        la = [(26 + lean, 18), (19, 32 + lean), (16, 46)]
        ra = [(38 + lean, 18), (45, 32 - lean), (48, 46)]
    parts.append(P(W, H, lambda s, c: (pygame.draw.lines(s, c, False, la, 3), pygame.draw.lines(s, c, False, ra, 3)),
                   SHADOW, z=3, rim=SHADOW_RIM, height=1.5, noise=0.1))
    claws = []
    for (hx, hy) in (la[-1], ra[-1]):
        for k in (-1, 0, 1):
            claws.append([(hx, hy), (hx + k * 3, hy + 6), (hx + k * 3 + 1, hy + 5)])
    parts.append(P(W, H, lambda s, c: [pygame.draw.polygon(s, c, cl) for cl in claws], ramp((30, 30, 40), (200, 196, 220)),
                   z=4, height=1, noise=0.02))
    # a small faceless head
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (int(28 + lean), 3, 8, 12)), SHADOW, z=5,
                   rim=SHADOW_RIM, height=4))
    # two pin-prick eyes (they're what you see in the dark)
    blink = (not attack) and 0.82 < t < 0.95
    if not blink:
        parts.append(P(W, H, lambda s, c: (s.set_at((int(30 + lean), 8), c), s.set_at((int(34 + lean), 8), c)),
                       [(250, 250, 255)] * 5, z=6, flat=True, emit=(225, 225, 255)))
    return parts


# ------------------------------------------------------------- Night Mimic (64x64, revealed)
def night_mimic(t, attack):
    W = H = 64
    ph = t * math.tau
    open_ = (10 + 10 * t) if attack else 7 + math.sin(ph) * 2
    parts = []
    # stubby clawed legs poking out under the chest
    parts.append(P(W, H, lambda s, c: [pygame.draw.line(s, c, (14 + k * 12, 50), (10 + k * 12 + (k % 2) * 6, 60), 3)
                                       for k in range(4)], SKIN_D, z=0, height=1.5))
    # the chest body: planks + iron bands + gold corners
    parts.append(P(W, H, lambda s, c: pygame.draw.rect(s, c, (10, 34, 44, 18)), WOOD, z=2, rim=MOON_RIM, height=6,
                   noise=0.12, seed=5))
    parts.append(P(W, H, lambda s, c: [pygame.draw.line(s, c, (10, y), (53, y), 1) for y in (40, 46)],
                   ramp((20, 10, 4), (60, 34, 14)), z=2.2, flat=True))
    parts.append(P(W, H, lambda s, c: (pygame.draw.rect(s, c, (17, 34, 3, 18)), pygame.draw.rect(s, c, (44, 34, 3, 18))),
                   IRON, z=2.5, height=1.5))
    parts.append(P(W, H, lambda s, c: [pygame.draw.rect(s, c, (x, y, 4, 4)) for x in (10, 50) for y in (34, 48)],
                   GOLDR, z=2.6, height=1.5))
    # the maw inside the open lid, rows of fangs, eyes in the dark
    lid_y = 34 - open_
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(11, 34), (53, 34), (51, lid_y + 4), (13, lid_y + 4)]),
                   MAW, z=1.5, flat=True))
    fangs = []
    for k in range(8):
        x = 13 + k * 5
        fangs.append([(x, 34), (x + 3, 34), (x + 1.5, 29 - (k % 2) * 2)])
        fangs.append([(x + 1, lid_y + 4), (x + 4, lid_y + 4), (x + 2.5, lid_y + 9 + (k % 2) * 2)])
    parts.append(P(W, H, lambda s, c: [pygame.draw.polygon(s, c, f) for f in fangs], BONE, z=3, height=1, noise=0.02))
    eye_open = not ((not attack) and 0.6 < t < 0.7)
    if eye_open:
        parts.append(P(W, H, lambda s, c: (pygame.draw.circle(s, c, (24, int(lid_y + 12)), 2),
                                           pygame.draw.circle(s, c, (40, int(lid_y + 12)), 2)),
                       [(255, 220, 70)] * 5, z=3.5, flat=True, emit=(255, 210, 60)))
    # the lid (lifted, tilted back)
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(9, lid_y + 4), (55, lid_y + 4), (52, lid_y - 4),
                                                                 (12, lid_y - 4)]),
                   WOOD, z=4, rim=MOON_RIM, height=3, noise=0.12, seed=6))
    parts.append(P(W, H, lambda s, c: pygame.draw.rect(s, c, (29, int(lid_y - 3), 6, 5)), GOLDR, z=4.5, height=1.5))
    # a long lolling tongue
    tw = math.sin(ph * (2 if attack else 1)) * (8 if attack else 4)
    tongue = [(30, 33), (33 + tw * 0.3, 40), (36 + tw, 48 + (6 if attack else 2)), (31 + tw, 50), (28, 40)]
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, tongue), TONGUE, z=5, height=2.5, rim=(255, 170, 200)))
    return parts


# ------------------------------------------------------------- Hollow Watcher (64x64)
def hollow_watcher(t, attack):
    W = H = 64
    ph = t * math.tau
    look = (math.cos(ph) * 3, math.sin(ph * 2) * 1.5) if not attack else (0, 0)
    pupil = 2 if attack else 3 + int(math.sin(ph) > 0.6)
    parts = []
    # gnarled roots spreading out, twitching
    roots = []
    for k in range(9):
        a = k / 9 * math.tau + 0.3
        tw = math.sin(ph + k) * 0.08
        r0, r1 = 14, 30 + (k % 3) * 2
        p0 = (32 + math.cos(a) * r0, 34 + math.sin(a) * r0 * 0.8)
        pm = (32 + math.cos(a + tw + 0.2) * (r0 + r1) / 2, 34 + math.sin(a + tw + 0.2) * (r0 + r1) / 2 * 0.8)
        p1 = (32 + math.cos(a + tw * 2 + 0.35) * r1, 34 + math.sin(a + tw * 2 + 0.35) * r1 * 0.8)
        roots.append((p0, pm, p1))
    parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, rt, 3) for rt in roots], ROOT, z=0, height=1.5,
                   noise=0.12, seed=7))
    # a fleshy socket nest
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (11, 14, 42, 40)), FLESH, z=1, height=6, noise=0.12,
                   rim=(220, 120, 120), seed=8))
    # the eyeball
    lid = 0 if not ((not attack) and 0.88 < t) else 14
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (15, 18 + lid, 34, 32 - lid * 2)), SCLERA, z=2,
                   height=9, rim=MOON_RIM, dome=0.55))
    if lid == 0:
        veins = []
        for k in range(7):
            a = k / 7 * math.tau
            veins.append([(32 + math.cos(a) * 15, 34 + math.sin(a) * 14), (32 + math.cos(a + 0.25) * 11,
                                                                            34 + math.sin(a + 0.25) * 10),
                          (32 + math.cos(a + 0.1) * 8, 34 + math.sin(a + 0.1) * 7)])
        parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, v, 1) for v in veins],
                       [(150, 30, 40)] * 5, z=2.5, flat=True))
        ix, iy = 32 + look[0], 34 + look[1]
        ir = 9 if not attack else 9 + int(t * 2)
        parts.append(P(W, H, lambda s, c: pygame.draw.circle(s, c, (int(ix), int(iy)), ir), IRIS, z=3, height=4,
                       emit=(255, 60, 50) if attack else (200, 40, 40), dome=0.5))
        parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (int(ix - pupil * 0.5), int(iy - ir + 2),
                                                                      pupil, (ir - 2) * 2)),
                       [(8, 2, 4)] * 5, z=4, flat=True))
        parts.append(P(W, H, lambda s, c: pygame.draw.circle(s, c, (int(ix - 3), int(iy - 4)), 1),
                       [(255, 255, 255)] * 5, z=5, flat=True))
    else:  # blink: a wrinkled lid
        parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (15, 26, 34, 16)), FLESH, z=3, height=4, noise=0.1))
    return parts


# ------------------------------------------------------------- The Red Harvester (160x104 boss)
def red_harvester(t, attack):
    W, H = 160, 104
    ph = t * math.tau
    bob = math.sin(ph) * 2
    parts = []
    # the scythe: a long haft across the body and a huge curved blade (swung on attack)
    ang = -0.75 + (math.sin(ph) * 0.06 if not attack else -0.35 + 1.25 * t)
    cx, cy = 80, 58 + bob
    hx0, hy0 = cx - math.cos(ang) * 52, cy - math.sin(ang) * 52
    hx1, hy1 = cx + math.cos(ang) * 46, cy + math.sin(ang) * 46
    parts.append(P(W, H, lambda s, c: pygame.draw.line(s, c, (hx0, hy0), (hx1, hy1), 4), HAFT, z=1, height=1.5, noise=0.1))
    # a huge crescent blade: it starts AT the haft's top and sweeps out and down like a hook
    R = 30
    perp = (math.cos(ang + math.pi / 2), math.sin(ang + math.pi / 2))   # the blade's "inside" side
    cxb, cyb = hx1 - perp[0] * -R, hy1 - perp[1] * -R
    a_tip = math.atan2(hy1 - cyb, hx1 - cxb)
    outer, inner = [], []
    for k in range(16):
        u = k / 15
        a2 = a_tip - u * 1.9
        outer.append((cxb + math.cos(a2) * R, cyb + math.sin(a2) * R))
        r_in = R - 1 - 8 * math.sin(u * math.pi) ** 0.8
        inner.append((cxb + math.cos(a2) * r_in + perp[0] * 2, cyb + math.sin(a2) * r_in + perp[1] * 2))
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, outer + list(reversed(inner))), STEEL, z=1.5, height=3,
                   rim=(255, 150, 150), dome=0.35, noise=0.04))
    parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, inner, 1), [(255, 90, 80)] * 5, z=1.6, flat=True,
                   emit=(255, 70, 60)))
    # the tattered cloak: a long flowing body, hem billowing in tatters
    hem = []
    for k in range(10):
        x = 52 + k * 6
        hem.append((x, 98 - (k % 2) * 6 + math.sin(ph + k) * 3))
    body = [(70, 26 + bob), (90, 26 + bob), (104, 48), (110, 92)] + list(reversed(hem)) + [(50, 92), (56, 48)]
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, body), CLOAK, z=2, rim=(255, 110, 100), height=10,
                   noise=0.09, seed=9))
    # folds
    folds = [[(72 + k * 6, 40 + bob), (68 + k * 7 + math.sin(ph + k) * 2, 92)] for k in range(4)]
    parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, f, 1) for f in folds], CLOAK_D, z=2.2, flat=True))
    # the hood and the dark inside it
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (63, 6 + bob, 34, 32)), CLOAK, z=3, rim=(255, 110, 100),
                   height=8, noise=0.08, seed=10))
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (70, 14 + bob, 20, 20)), [(6, 0, 2)] * 5, z=3.5, flat=True))
    # two burning eyes in the hood
    parts.append(P(W, H, lambda s, c: (pygame.draw.circle(s, c, (75, int(23 + bob)), 2),
                                       pygame.draw.circle(s, c, (85, int(23 + bob)), 2)),
                   [(255, 80, 60)] * 5, z=4, flat=True, emit=(255, 60, 40)))
    # bony hands gripping the haft
    for (gx, gy) in ((cx - math.cos(ang) * 10, cy - math.sin(ang) * 10), (cx + math.cos(ang) * 16, cy + math.sin(ang) * 16)):
        parts.append(P(W, H, lambda s, c, gx=gx, gy=gy: pygame.draw.circle(s, c, (int(gx), int(gy)), 4), BONE, z=5,
                       height=2, rim=MOON_RIM))
    # a few hanging chains / talismans for detail
    parts.append(P(W, H, lambda s, c: [pygame.draw.line(s, c, (62 + k * 9, 50 + bob), (60 + k * 9, 62 + bob + (k % 2) * 4), 1)
                                       for k in range(4)], IRON, z=2.4, height=1))
    return parts


# ------------------------------------------------------------- fireflies (64x64 swarm)
FLY_SEED = [(random.Random(k).uniform(8, 56), random.Random(k + 99).uniform(8, 56)) for k in range(9)]


def fireflies(t, attack):
    W = H = 64
    ph = t * math.tau
    parts = []
    for k, (x0, y0) in enumerate(FLY_SEED):
        x = x0 + math.sin(ph + k * 1.7) * 4
        y = y0 + math.cos(ph * 1 + k * 2.3) * 3
        parts.append(P(W, H, lambda s, c, x=x, y=y: pygame.draw.ellipse(s, c, (int(x) - 1, int(y) - 1, 3, 2)),
                       ramp((20, 26, 18), (80, 96, 70)), z=k * 0.1, height=1, flat=True))
        on = math.sin(ph * 2 + k * 2.1) > -0.3
        parts.append(P(W, H, lambda s, c, x=x, y=y: pygame.draw.circle(s, c, (int(x) + 1, int(y) + 1), 1),
                       [(235, 255, 140) if on else (110, 130, 70)] * 5, z=k * 0.1 + 0.05, flat=True,
                       emit=(220, 255, 120) if on else None))
    return parts


# ------------------------------------------------------------- the Ghost Merchant (64x64, NPC)
def ghost_merchant(t, attack):
    W = H = 64
    ph = t * math.tau
    bob = math.sin(ph) * 1.5
    parts = []
    tails = [[(22 + k * 5, 48 + bob), (26 + k * 5, 48 + bob), (24 + k * 5 + math.sin(ph + k) * 2, 60 - (k % 2) * 3)]
             for k in range(5)]
    parts.append(P(W, H, lambda s, c: [pygame.draw.polygon(s, c, tl) for tl in tails], GHOST, z=0, height=2, alpha=170))
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(24, 18 + bob), (40, 18 + bob), (46, 50 + bob),
                                                                 (18, 50 + bob)]),
                   GHOST, z=1, height=6, rim=(220, 255, 250), alpha=190, noise=0.06))
    # a huge peddler's pack of curios
    parts.append(P(W, H, lambda s, c: pygame.draw.rect(s, c, (38, 16 + bob, 16, 22), border_radius=3), WOOD, z=0.5,
                   height=3, noise=0.1, rim=MOON_RIM))
    parts.append(P(W, H, lambda s, c: [pygame.draw.circle(s, c, (42 + k * 4, int(15 + bob)), 2) for k in range(3)],
                   GOLDR, z=0.6, height=1))
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (23, 4 + bob, 18, 18)), GHOST, z=2, height=5,
                   rim=(220, 255, 250), alpha=200))
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (27, 9 + bob, 10, 10)), [(8, 20, 26)] * 5, z=2.5, flat=True))
    parts.append(P(W, H, lambda s, c: (s.set_at((29, int(13 + bob)), c), s.set_at((34, int(13 + bob)), c)),
                   [(190, 255, 235)] * 5, z=3, flat=True, emit=(170, 255, 230)))
    # a lantern on a crooked pole
    lx, ly = 14 + math.sin(ph) * 1.5, 22 + bob
    parts.append(P(W, H, lambda s, c: pygame.draw.line(s, c, (20, 46 + bob), (14, 14 + bob), 2), HAFT, z=3, height=1))
    parts.append(P(W, H, lambda s, c: pygame.draw.rect(s, c, (int(lx) - 3, int(ly) - 2, 6, 8)), LURE, z=4, height=2,
                   emit=(255, 220, 140)))
    return parts


def main():
    pygame.init()
    pygame.display.set_mode((8, 8))
    build("lantern_eater", lantern_eater, 64, 64, 6, 3)
    build("shade_stalker", shade_stalker, 64, 64, 6, 3)
    build("night_mimic", night_mimic, 64, 64, 6, 3)
    build("hollow_watcher", hollow_watcher, 64, 64, 6, 3)
    build("red_harvester", red_harvester, 160, 104, 6, 3)
    build("fireflies", fireflies, 64, 64, 6, 2)
    build("npc_ghost_merchant", ghost_merchant, 64, 64, 6, 2)


if __name__ == "__main__":
    main()
