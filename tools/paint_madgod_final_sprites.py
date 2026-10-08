"""
Paints the Mad God's last two forms in the same high-detail style as tools/paint_boss_sprites.py
(mad_god -> mad_god_phase2 -> these):

  mad_god_unhinged  - the scorched god has torn out of his robe: a gaunt, floating violet horror
                      with FOUR arms (two raised, two reaching), skeletal clawed hands each holding a
                      crackling orb, a shattered halo orbiting in shards, the cracked gold crown
                      knocked sideways, red eyes in hollow sockets and a grin far too wide. The robe
                      is in ribbons, split by magenta cracks. Attack: all four arms thrust out.
  mad_god_livid     - Absolutely Livid: crimson, huge bat wings (bone fingers, torn membrane), a
                      burning crown, a flushed furious face (brows down, teeth gritted, white-hot
                      eyes), fists on fire and embers drifting up off him. Attack: the wings flare
                      up and the burning fists rise.

Logical canvases keep the old sprites' aspect (160x120 and 176x120, saved at 2x = 320x240 and
352x240), so in-game size and hitbox feel don't change. Wholly original.

Run: python tools/paint_madgod_final_sprites.py   (writes into assets/sprites/v0.2/enemies/)
"""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pygame  # noqa: E402

from paint_night_sprites import P, ramp, build  # noqa: E402
from paint_boss_sprites import GOLD, RIM_GOLD, GEM_R, _flame, FIRE_O, FIRE_Y, TOOTH  # noqa: E402

# ------------------------------------------------------------- materials
# Unhinged (identity: violet robe, pale skull-ish face, red eyes, gold crown, pink sparks)
VROBE = ramp((26, 8, 44), (196, 120, 255), warm_shadow=(30, 0, 40))
VROBE_D = ramp((14, 4, 26), (110, 50, 160))
BONE = ramp((90, 76, 96), (246, 236, 240), warm_shadow=(40, 10, 40))
SOCKET = ramp((8, 2, 12), (40, 12, 40))
MAGENTA = [(255, 110, 230)] * 5
VIOLET_HOT = [(236, 150, 255)] * 5
RED_EYE = [(255, 60, 60)] * 5
RIM_V = (230, 180, 255)
# Livid (identity: crimson robe, dark-red wings, gold crown, embers)
CRIM = ramp((40, 4, 8), (240, 70, 60), warm_shadow=(60, 0, 10))
CRIM_D = ramp((22, 2, 4), (140, 26, 26))
WING = ramp((26, 2, 6), (150, 28, 34), warm_shadow=(40, 0, 20))
WING_BONE = ramp((40, 10, 10), (200, 120, 100))
FLUSH = ramp((110, 30, 26), (255, 170, 140))
EMBER = [(255, 150, 50)] * 5
RIM_HOT = (255, 170, 120)


# ------------------------------------------------------------- Unhinged (160x120)
def unhinged(t, attack):
    W, H = 160, 120
    ph = t * math.tau
    bob = math.sin(ph) * 2.0
    jit = math.sin(ph * 3) * 0.8  # he twitches
    cx = 80
    hy = 30 + bob
    parts = []
    # the shattered halo: phase 2's sun ring, broken into arcs that drift apart and slowly turn
    for k in range(5):
        a0 = k * math.tau / 5 + ph * 0.25
        drift = 1.5 + (k % 2) * 2 + math.sin(ph + k) * 0.8
        r = 21 + drift
        ox, oy = math.cos(a0 + 0.45) * drift, math.sin(a0 + 0.45) * drift
        rect = (cx - r + ox, hy - r + oy, r * 2, r * 2)
        parts.append(P(W, H, lambda s, c, rc=rect, a=a0: pygame.draw.arc(s, c, rc, -a - 0.9, -a, 3), GOLD, z=0,
                       height=1.5, rim=RIM_GOLD, emit=(240, 150, 255)))
    # four arms: (shoulder, hand) - the upper pair raised, the lower pair reaching out and down
    if attack:
        k = min(1.0, t * 1.5)
        hands = [(cx - 62, 18 - 8 * k), (cx + 62, 18 - 8 * k), (cx - 66, 66 - 10 * k), (cx + 66, 66 - 10 * k)]
    else:
        hands = [(cx - 54, 22 + math.sin(ph) * 4 + bob), (cx + 54, 22 - math.sin(ph) * 4 + bob),
                 (cx - 58, 72 - math.sin(ph) * 3 + bob), (cx + 58, 72 + math.sin(ph) * 3 + bob)]
    shoulders = [(cx - 14, 48 + bob), (cx + 14, 48 + bob), (cx - 15, 58 + bob), (cx + 15, 58 + bob)]
    for i, ((sx, sy), (hx, hyy)) in enumerate(zip(shoulders, hands)):
        dirx = -1 if hx < cx else 1
        upper = i < 2
        ex = (sx + hx) / 2 + dirx * 4
        ey = (sy + hyy) / 2 + (8 if upper else 6)  # elbows bend down: long, wrong-jointed arms
        z0 = 1 if upper else 0.8
        # tattered sleeve on the upper arm, bare bone forearm
        parts.append(P(W, H, lambda s, c, a=(sx, sy), b=(ex, ey): pygame.draw.line(s, c, a, b, 9), VROBE, z=z0,
                       height=4, rim=RIM_V, noise=0.08, seed=20 + i))
        parts.append(P(W, H, lambda s, c, a=(ex, ey), d=dirx: pygame.draw.polygon(
            s, c, [(a[0] - 4, a[1] - 2), (a[0] + 4, a[1] - 2), (a[0] + d * 2, a[1] + 9), (a[0] - d * 3, a[1] + 6)]),
            VROBE_D, z=z0 + 0.05, height=2, noise=0.08))  # a torn rag hanging off the elbow
        parts.append(P(W, H, lambda s, c, a=(ex, ey), b=(hx, hyy): pygame.draw.line(s, c, a, b, 4), BONE, z=z0 + 0.1,
                       height=2.5, rim=RIM_V, noise=0.05, seed=24 + i))
        parts.append(P(W, H, lambda s, c, h=(hx, hyy): pygame.draw.circle(s, c, (int(h[0]), int(h[1])), 4), BONE,
                       z=z0 + 0.2, height=2, rim=RIM_V))
        for f in range(3):  # long claws
            ang = math.atan2(hyy - ey, hx - ex) + (f - 1) * 0.55
            parts.append(P(W, H, lambda s, c, h=(hx, hyy), an=ang: pygame.draw.line(
                s, c, (h[0] + math.cos(an) * 3, h[1] + math.sin(an) * 3), (h[0] + math.cos(an) * 9, h[1] + math.sin(an) * 9),
                2), BONE, z=z0 + 0.25, height=1, flat=True))
        # an orb crackling in each hand (blazing on the attack)
        orb = 3 + math.sin(ph * 2 + i) * 0.8 + (5 * t if attack else 0)
        parts.append(P(W, H, lambda s, c, h=(hx, hyy), r=orb, d=dirx: pygame.draw.circle(
            s, c, (int(h[0] + d * 6), int(h[1] - 5)), max(2, int(r))), VIOLET_HOT, z=z0 + 0.3, flat=True,
            emit=(240, 150, 255)))
        spark = [(hx + dirx * 6 - 6, hyy - 14), (hx + dirx * 6 - 2, hyy - 9), (hx + dirx * 6 - 6, hyy - 6),
                 (hx + dirx * 6 + 1, hyy - 1)]
        parts.append(P(W, H, lambda s, c, sp=spark: pygame.draw.lines(s, c, False, sp, 1), MAGENTA, z=z0 + 0.35,
                       flat=True, emit=(255, 130, 240)))
    # the robe in ribbons: a narrow torso flaring into long ragged tatters
    hem = []
    n = 15
    for k in range(n):
        x = cx - 30 + k * (60 / (n - 1))
        drop = (14 if k % 2 == 0 else 0) + math.sin(ph + k * 1.3) * 3
        hem.append((x + math.sin(ph * 1.5 + k) * 1.5, 98 + drop))
    body = [(cx - 13, 42 + bob), (cx + 13, 42 + bob), (cx + 16, 64 + bob), (cx + 30, 96)] + list(reversed(hem)) + \
           [(cx - 30, 96), (cx - 16, 64 + bob)]
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, body), VROBE, z=2, height=12, rim=RIM_V, noise=0.08,
                   seed=30, dome=0.45))
    # deep folds and the hollow of the ribs showing through a tear in the chest
    folds = [[(cx - 8 + k * 6, 66 + bob), (cx - 24 + k * 16 + math.sin(ph + k) * 2, 104)] for k in range(3)]
    parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, f, 1) for f in folds], VROBE_D, z=2.1, flat=True))
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 9, 46 + bob, 18, 16)), SOCKET, z=2.2, flat=True))
    parts.append(P(W, H, lambda s, c: [pygame.draw.arc(s, c, (cx - 8, 46 + bob + k * 4, 16, 8), math.pi * 0.1,
                                                       math.pi * 0.9, 1) for k in range(3)]
                   + [pygame.draw.line(s, c, (cx, 47 + bob), (cx, 60 + bob), 1)], BONE, z=2.25, flat=True))
    parts.append(P(W, H, lambda s, c: pygame.draw.circle(s, c, (cx, int(55 + bob)), 2), MAGENTA, z=2.3, flat=True,
                   emit=(255, 120, 240)))  # something burning where the heart was
    # magenta cracks splitting the robe
    cracks = [[(cx - 14, 66 + bob), (cx - 10, 76 + bob), (cx - 16, 86 + bob), (cx - 10, 98)],
              [(cx + 13, 64 + bob), (cx + 18, 74 + bob), (cx + 12, 86 + bob), (cx + 19, 100)],
              [(cx, 70 + bob), (cx + 3, 80 + bob), (cx - 2, 92 + bob)]]
    parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, cr, 2) for cr in cracks], MAGENTA, z=2.4,
                   flat=True, emit=(255, 110, 230)))
    # a torn gold stole, hanging from one shoulder only
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(cx + 6, 42 + bob), (cx + 11, 43 + bob),
                                                                 (cx + 8, 76 + bob), (cx + 3, 72 + bob)]),
                   GOLD, z=2.5, height=2, rim=RIM_GOLD, noise=0.05))
    parts.append(P(W, H, lambda s, c: pygame.draw.circle(s, c, (cx + 7, int(56 + bob)), 2), GEM_R, z=2.55, flat=True,
                   emit=(255, 90, 170)))
    # the collar of bone spikes
    parts.append(P(W, H, lambda s, c: [pygame.draw.polygon(s, c, [(cx - 14 + k * 4, 44 + bob), (cx - 11 + k * 4, 44 + bob),
                                                                  (cx - 13 + k * 4 - (7 - k) * 0.6, 36 + bob)])
                                       for k in range(8)], BONE, z=2.6, height=2, rim=RIM_V))
    # the head: gaunt, pale, a skull pulled tight
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 11 + jit, hy - 10, 22, 26)), BONE, z=3, height=6,
                   rim=RIM_V, noise=0.04, seed=31))
    parts.append(P(W, H, lambda s, c: (pygame.draw.line(s, c, (cx - 9 + jit, hy + 7), (cx - 5 + jit, hy + 12), 1),
                                       pygame.draw.line(s, c, (cx + 9 + jit, hy + 7), (cx + 5 + jit, hy + 12), 1)),
                   ramp((120, 90, 130), (170, 140, 170)), z=3.05, flat=True))  # sunken cheeks
    for side in (-1, 1):  # hollow sockets, a red pinprick burning in each
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.ellipse(s, c, (cx + sd * 5 - 4 + jit, hy - 2, 8, 7)),
                       SOCKET, z=3.1, flat=True))
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.circle(s, c, (int(cx + sd * 5 + jit), int(hy + 1)),
                                                                      2 if not attack else 3),
                       RED_EYE, z=3.2, flat=True, emit=(255, 50, 50)))
    # the grin: ear to ear, every tooth showing (wider on the attack)
    gw = 9 + (3 * t if attack else 0)
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - gw + jit, hy + 7, gw * 2, 6 + (3 * t if attack else 0))),
                   SOCKET, z=3.3, flat=True))
    parts.append(P(W, H, lambda s, c: [pygame.draw.line(s, c, (cx - gw + 2 + k * 2 + jit, hy + 8),
                                                        (cx - gw + 2 + k * 2 + jit, hy + 10), 1)
                                       for k in range(int(gw))], TOOTH, z=3.4, flat=True))
    # a violet crack running down the face from the crown
    parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, [(cx + 3 + jit, hy - 10), (cx + 1 + jit, hy - 5),
                                                                      (cx + 4 + jit, hy - 1)], 1),
                   MAGENTA, z=3.5, flat=True, emit=(255, 110, 230)))
    # the cracked crown, knocked well over to one side, one spike snapped
    spikes = []
    base_y = hy - 10
    for k in range(7):
        bx = cx - 12 + k * 4 + jit
        top = base_y - 9 - (6 if k == 3 else (3 if k % 2 == 0 else 0))
        if k == 5:
            top = base_y - 5  # snapped
        lean = (k - 3) * 0.6 + 3
        spikes.append([(bx - 2, base_y + 2), (bx + 2, base_y + 2), (bx + lean, top + abs(k - 6) * 0.8)])
    band = [(cx - 14 + jit, base_y - 1), (cx + 12 + jit, base_y + 3), (cx + 12 + jit, base_y + 7), (cx - 14 + jit, base_y + 3)]
    parts.append(P(W, H, lambda s, c: (pygame.draw.polygon(s, c, band), [pygame.draw.polygon(s, c, sp) for sp in spikes]),
                   GOLD, z=3.6, height=2, rim=RIM_GOLD, noise=0.05, seed=32))
    parts.append(P(W, H, lambda s, c: pygame.draw.lines(s, c, False, [(cx - 3 + jit, base_y - 6), (cx - 1 + jit, base_y),
                                                                      (cx - 4 + jit, base_y + 5)], 1),
                   SOCKET, z=3.7, flat=True))
    parts.append(P(W, H, lambda s, c: [pygame.draw.circle(s, c, (int(cx - 8 + k * 8 + jit), int(base_y + 2 + k * 1.3)), 1)
                                       for k in range(3)], GEM_R, z=3.75, flat=True, emit=(255, 90, 170)))
    return parts


# ------------------------------------------------------------- Absolutely Livid (176x120)
def livid(t, attack):
    W, H = 176, 120
    ph = t * math.tau
    bob = math.sin(ph) * 2.0
    cx = 88
    hy = 34 + bob
    parts = []
    # the wings: shoulder root, a bony leading edge out to the wrist, finger bones fanning down to a
    # scalloped, torn trailing edge. They beat with the bob; on the attack they flare high.
    lift = (14 * min(1.0, t * 1.5)) if attack else math.sin(ph) * 6
    for side in (-1, 1):
        root = (cx + side * 12, 46 + bob)
        wrist = (cx + side * 54, 16 + bob - lift)
        tips = [(cx + side * 86, 30 + bob - lift * 0.8), (cx + side * 82, 60 + bob - lift * 0.5),
                (cx + side * 66, 80 + bob - lift * 0.3), (cx + side * 40, 86 + bob - lift * 0.1)]
        edge = [root, wrist]
        prev = wrist
        for k, tp in enumerate(tips):
            edge.append(tp)
            nxt = tips[k + 1] if k + 1 < len(tips) else (cx + side * 18, 72 + bob)
            mid = ((tp[0] + nxt[0]) / 2, (tp[1] + nxt[1]) / 2)
            # scallop: the membrane sags in toward the wrist between fingers
            edge.append((mid[0] + (wrist[0] - mid[0]) * 0.22, mid[1] + (wrist[1] - mid[1]) * 0.22))
            prev = tp
        edge.append((cx + side * 18, 72 + bob))
        parts.append(P(W, H, lambda s, c, e=edge: pygame.draw.polygon(s, c, e), WING, z=0, height=4, rim=RIM_HOT,
                       noise=0.09, seed=40 + side, dome=0.3))
        # a couple of tears in the membrane
        tear = [(cx + side * 60, 48 + bob - lift * 0.6), (cx + side * 64, 52 + bob - lift * 0.6),
                (cx + side * 58, 56 + bob - lift * 0.6)]
        parts.append(P(W, H, lambda s, c, tr=tear: pygame.draw.polygon(s, c, tr), [(14, 2, 4)] * 5, z=0.05, flat=True))
        # the bones: arm to the wrist, fingers to each tip (with a hooked claw at the wrist)
        parts.append(P(W, H, lambda s, c, a=root, b=wrist: pygame.draw.line(s, c, a, b, 4), WING_BONE, z=0.1,
                       height=2, rim=RIM_HOT))
        parts.append(P(W, H, lambda s, c, w=wrist: [pygame.draw.line(s, c, w, tp, 2) for tp in tips], WING_BONE,
                       z=0.15, height=1.5))
        parts.append(P(W, H, lambda s, c, w=wrist, sd=side: pygame.draw.polygon(
            s, c, [(w[0] - 2, w[1]), (w[0] + 2, w[1]), (w[0] + sd * 3, w[1] - 8)]), TOOTH, z=0.2, height=1))
    # fists: down at his sides idle (clenched, smouldering); raised and blazing on the attack
    if attack:
        k = min(1.0, t * 1.5)
        fists = [(cx - 34, 52 - 24 * k), (cx + 34, 52 - 24 * k)]
    else:
        fists = [(cx - 30, 70 + bob + math.sin(ph) * 1.5), (cx + 30, 70 + bob - math.sin(ph) * 1.5)]
    for i, (fx, fy) in enumerate(fists):
        sx, sy = cx + (-1 if i == 0 else 1) * 15, 50 + bob
        parts.append(P(W, H, lambda s, c, a=(sx, sy), b=(fx, fy): pygame.draw.line(s, c, a, b, 9), CRIM, z=1.2,
                       height=4, rim=RIM_HOT, noise=0.06, seed=44 + i))
        parts.append(P(W, H, lambda s, c, f=(fx, fy): pygame.draw.circle(s, c, (int(f[0]), int(f[1])), 5), FLUSH,
                       z=1.3, height=2.5, rim=RIM_HOT))
        parts.append(P(W, H, lambda s, c, f=(fx, fy): [pygame.draw.line(s, c, (f[0] - 3, f[1] - 1 + k * 2),
                                                                         (f[0] + 3, f[1] - 1 + k * 2), 1) for k in range(2)],
                       ramp((90, 20, 20), (130, 40, 30)), z=1.35, flat=True))  # knuckles
        size = 6 + (6 * t if attack else math.sin(ph * 2 + i) * 1.0)
        parts.append(P(W, H, lambda s, c, f=(fx, fy), sz=size, k=i * 2: pygame.draw.polygon(
            s, c, _flame(f[0], f[1] - 3, sz, ph, k)), FIRE_O, z=1.4, height=3, flat=False, dome=0.6,
            emit=(255, 120, 40), alpha=230))
        parts.append(P(W, H, lambda s, c, f=(fx, fy), sz=size * 0.55, k=i * 2 + 1: pygame.draw.polygon(
            s, c, _flame(f[0], f[1] - 4, sz, ph, k)), FIRE_Y, z=1.5, flat=True, emit=(255, 220, 120)))
    # the robe: crimson, gold-trimmed, the hem charring into flame
    hem = []
    n = 13
    for k in range(n):
        x = cx - 30 + k * (60 / (n - 1))
        hem.append((x, 104 + math.sin(ph + k * 0.9) * 2.5 - (k % 2) * 3))
    body = [(cx - 14, 44 + bob), (cx + 14, 44 + bob), (cx + 20, 66 + bob), (cx + 30, 102)] + list(reversed(hem)) + \
           [(cx - 30, 102), (cx - 20, 66 + bob)]
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, body), CRIM, z=2, height=12, rim=RIM_HOT, noise=0.07,
                   seed=46, dome=0.45))
    folds = [[(cx - 9 + k * 6, 58 + bob), (cx - 20 + k * 13 + math.sin(ph + k) * 2, 100)] for k in range(4)]
    parts.append(P(W, H, lambda s, c: [pygame.draw.lines(s, c, False, f, 1) for f in folds], CRIM_D, z=2.1, flat=True))
    parts.append(P(W, H, lambda s, c: pygame.draw.polygon(s, c, [(cx - 5, 46 + bob), (cx + 5, 46 + bob), (cx + 7, 100),
                                                                 (cx - 7, 100)]), GOLD, z=2.2, height=3, rim=RIM_GOLD,
                   noise=0.04))
    parts.append(P(W, H, lambda s, c: [pygame.draw.circle(s, c, (cx, int(56 + bob + k * 12)), 2) for k in range(4)],
                   [(255, 80, 40)] * 5, z=2.3, flat=True, emit=(255, 110, 50)))
    # the hem burning
    for k in range(0, n, 2):
        x, y = hem[k]
        parts.append(P(W, H, lambda s, c, x=x, y=y, k=k: pygame.draw.polygon(s, c, _flame(x, y + 1, 3.5, ph, k)),
                       FIRE_O, z=2.35, flat=True, emit=(255, 130, 40)))
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 17, 42 + bob, 34, 10)), GOLD, z=2.5, height=2,
                   rim=RIM_GOLD))
    # the head: flushed red with fury
    parts.append(P(W, H, lambda s, c: pygame.draw.ellipse(s, c, (cx - 11, hy - 9, 22, 25)), FLUSH, z=3, height=6,
                   rim=RIM_HOT, noise=0.04, seed=47))
    for side in (-1, 1):
        # brows slammed down into a V
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.polygon(s, c, [(cx + sd * 10, hy - 5), (cx + sd * 10, hy - 2),
                                                                              (cx + sd * 1, hy + 2), (cx + sd * 2, hy - 1)]),
                       [(34, 2, 4)] * 5, z=3.2, flat=True))
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.ellipse(s, c, (cx + sd * 5 - 3, int(hy + 1), 6, 3)),
                       [(255, 250, 220)] * 5, z=3.15, flat=True, emit=(255, 240, 200)))
        parts.append(P(W, H, lambda s, c, sd=side: s.set_at((int(cx + sd * 5), int(hy + 2)), c), [(255, 40, 30)] * 5,
                       z=3.18, flat=True, emit=(255, 60, 40)))
        # a throbbing vein at each temple
        parts.append(P(W, H, lambda s, c, sd=side: pygame.draw.lines(s, c, False, [(cx + sd * 9, hy - 6), (cx + sd * 8, hy - 4),
                                                                                   (cx + sd * 10, hy - 2)], 1),
                       [(150, 20, 30)] * 5, z=3.22, flat=True))
    # gritted teeth (bared wide on the attack roar)
    mh = 4 + (4 * t if attack else 0)
    parts.append(P(W, H, lambda s, c: pygame.draw.rect(s, c, (cx - 7, hy + 8, 14, mh)), TOOTH, z=3.3, height=1,
                   flat=True))
    parts.append(P(W, H, lambda s, c: (pygame.draw.line(s, c, (cx - 7, hy + 8 + mh / 2), (cx + 7, hy + 8 + mh / 2), 1),
                                       [pygame.draw.line(s, c, (cx - 5 + k * 3, hy + 8), (cx - 5 + k * 3, hy + 8 + mh), 1)
                                        for k in range(4)]), [(60, 10, 10)] * 5, z=3.35, flat=True))
    # the crown, upright, every spike on fire
    spikes = []
    for k in range(7):
        bx = cx - 12 + k * 4
        top = hy - 20 - (6 if k == 3 else (3 if k % 2 == 0 else 0))
        spikes.append(((bx, top), [(bx - 2, hy - 9), (bx + 2, hy - 9), (bx, top)]))
    parts.append(P(W, H, lambda s, c: (pygame.draw.rect(s, c, (cx - 13, hy - 12, 26, 5), border_radius=1),
                                       [pygame.draw.polygon(s, c, sp) for _, sp in spikes]),
                   GOLD, z=3.6, height=2, rim=RIM_GOLD, noise=0.04, seed=48))
    parts.append(P(W, H, lambda s, c: [pygame.draw.circle(s, c, (cx - 8 + k * 8, int(hy - 10)), 1) for k in range(3)],
                   [(255, 60, 40)] * 5, z=3.7, flat=True, emit=(255, 80, 50)))
    for k, ((tx, ty), _) in enumerate(spikes):
        if k % 2 == 0:
            parts.append(P(W, H, lambda s, c, tx=tx, ty=ty, k=k: pygame.draw.polygon(s, c, _flame(tx, ty + 2, 3, ph, k)),
                           FIRE_Y, z=3.8, flat=True, emit=(255, 180, 70)))
    # embers drifting up off him (looping with t so the strip cycles)
    for k in range(10):
        u = (t + k * 0.137) % 1.0
        x = cx + math.sin(k * 2.3) * 40 + math.sin(u * math.tau + k) * 3
        y = 100 - u * 95
        r = 1 if k % 3 else 2
        parts.append(P(W, H, lambda s, c, x=x, y=y, r=r: pygame.draw.circle(s, c, (int(x), int(y)), r), EMBER, z=5,
                       flat=True, emit=(255, 160, 60)))
    return parts


def main():
    pygame.init()
    pygame.display.set_mode((8, 8))
    build("mad_god_unhinged", unhinged, 160, 120, 4, 3)
    build("mad_god_livid", livid, 176, 120, 4, 3)


if __name__ == "__main__":
    main()
