"""
Paints the 8 player classes (archer, assassin, necromancer, paladin, priest, rogue, warrior,
wizard) with the part-based painter from tools/paint_night_sprites.py (lit, dithered,
outlined parts) - a still plus three animation strips each. Wholly original.

Output (assets/sprites/v0.2/players/), every frame the same square size (56x56 logical, saved
at 2x = 112x112), figure centred, feet on the same baseline, FACING RIGHT (the game flips them):
  player_<cls>.png         the still
  player_<cls>_idle.png    4 frames - breathing, cloak / robe sway, a slight bob
  player_<cls>_walk.png    6 frames - legs stepping, arms swinging, the body bobbing
  player_<cls>_shoot.png   3 frames - wind-up, release toward the right with a flash, recover

Run: python tools/paint_player_sprites.py [class ...]   (+ --sheet to only redraw the contact sheet)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

import paint_night_sprites as N  # noqa: E402  (Part, ramp, render, strip, shape)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "sprites", "v0.2", "players")
SHEET_DIR = os.path.join(ROOT, "screenshots", "2026-10-08", "art_players")
W = H = 56
UP = 2
CX = 27          # body centre x
FEET = 54        # the baseline every frame stands on
ramp = N.ramp
RIM = (235, 235, 210)


def P(fn, r, z, **k):
    return N.Part(N.shape(W, H, fn), r, z=z, **k)


def poly(pts):
    return lambda s, c: pygame.draw.polygon(s, c, [(round(x), round(y)) for x, y in pts])


def rect(x, y, w, h, rad=0):
    return lambda s, c: pygame.draw.rect(s, c, pygame.Rect(round(x), round(y), round(w), round(h)), border_radius=rad)


def circ(x, y, r):
    return lambda s, c: pygame.draw.circle(s, c, (round(x), round(y)), max(1, round(r)))


def ell(x, y, w, h):
    return lambda s, c: pygame.draw.ellipse(s, c, pygame.Rect(round(x), round(y), round(w), round(h)))


def line(pts, width):
    return lambda s, c: pygame.draw.lines(s, c, False, [(round(x), round(y)) for x, y in pts], width)


def flat(col):
    return [col] * 5


# --------------------------------------------------------------- materials
SKIN = ramp((92, 52, 40), (255, 222, 186), warm_shadow=(120, 40, 40))
SKIN_PALE = ramp((70, 70, 80), (232, 228, 214))
BOOT = ramp((26, 16, 10), (120, 82, 50))
BOOT_D = ramp((14, 12, 16), (82, 74, 90))
WOODR = ramp((48, 26, 10), (196, 140, 76))
STEELR = ramp((44, 48, 60), (240, 242, 250))
GOLDR = ramp((96, 62, 8), (255, 232, 120))
EYE_W = flat((250, 250, 245))

CLASSES = {
    "archer": dict(top=ramp((22, 52, 18), (150, 214, 96)), hood=ramp((18, 58, 20), (120, 200, 90)),
                   pants=ramp((38, 24, 12), (150, 104, 60)), boot=BOOT, trim=ramp((60, 40, 14), (196, 150, 70)),
                   hair=ramp((60, 34, 12), (170, 110, 50)), eyes=(40, 26, 18), robe=False),
    "assassin": dict(top=ramp((14, 12, 22), (92, 82, 116)), hood=ramp((12, 10, 20), (84, 74, 108)),
                     pants=ramp((12, 10, 18), (74, 66, 92)), boot=BOOT_D, trim=ramp((80, 8, 14), (240, 70, 70)),
                     hair=ramp((10, 10, 14), (60, 56, 70)), eyes=(250, 160, 40), robe=False),
    "necromancer": dict(top=ramp((8, 26, 16), (64, 132, 84)), hood=ramp((6, 20, 12), (52, 112, 70)),
                        pants=ramp((8, 22, 14), (50, 96, 64)), boot=BOOT_D, trim=ramp((40, 10, 60), (170, 90, 220)),
                        hair=ramp((10, 20, 14), (50, 80, 60)), eyes=(110, 255, 140), robe=True, skin=SKIN_PALE),
    "paladin": dict(top=ramp((20, 36, 90), (130, 176, 255)), hood=STEELR,
                    pants=ramp((18, 30, 78), (110, 150, 230)), boot=ramp((30, 30, 40), (170, 170, 190)),
                    trim=GOLDR, hair=ramp((80, 50, 14), (230, 190, 90)), eyes=(60, 120, 230), robe=False),
    "priest": dict(top=ramp((120, 104, 70), (255, 248, 222)), hood=ramp((150, 110, 20), (255, 236, 130)),
                   pants=ramp((120, 104, 70), (250, 244, 220)), boot=ramp((80, 56, 20), (210, 170, 90)),
                   trim=GOLDR, hair=ramp((150, 110, 20), (255, 236, 130)), eyes=(70, 60, 40), robe=True),
    "rogue": dict(top=ramp((12, 12, 16), (88, 88, 102)), hood=ramp((10, 10, 12), (70, 70, 80)),
                  pants=ramp((14, 14, 18), (80, 80, 92)), boot=BOOT, trim=ramp((60, 20, 20), (180, 60, 60)),
                  hair=ramp((8, 8, 10), (64, 60, 66)), eyes=(60, 150, 120), robe=False),
    "warrior": dict(top=ramp((80, 10, 12), (240, 70, 60)), hood=STEELR,
                    pants=ramp((50, 52, 62), (200, 204, 216)), boot=ramp((30, 22, 16), (130, 96, 64)),
                    trim=ramp((60, 40, 14), (196, 150, 70)), hair=ramp((60, 40, 20), (160, 120, 70)),
                    eyes=(50, 40, 30), robe=False),
    "wizard": dict(top=ramp((34, 12, 70), (170, 110, 250)), hood=ramp((40, 14, 84), (180, 120, 255)),
                   pants=ramp((30, 10, 60), (140, 90, 220)), boot=BOOT_D, trim=ramp((120, 90, 10), (255, 220, 110)),
                   hair=ramp((30, 20, 40), (110, 90, 130)), eyes=(30, 26, 40), robe=True),
}


# --------------------------------------------------------------- the pose
def pose_for(anim, i, n):
    """Animation state -> numbers the body builder uses."""
    t = i / n
    ph = t * math.tau
    p = dict(bob=0.0, breath=0.0, sway=0.0, legL=0.0, legR=0.0, stepL=0.0, stepR=0.0, armF=0.0, armB=0.0,
             reach=0.0, lean=0.0, flash=0.0, draw=0.0)
    if anim == "idle":
        p["breath"] = (1 - math.cos(ph)) * 0.5          # 0 .. 1
        p["bob"] = -round(p["breath"])                  # 1 px up at full breath
        p["sway"] = math.sin(ph) * 1.2
        p["armF"] = p["armB"] = p["breath"] * 0.8
    elif anim == "walk":
        s = math.sin(ph)
        p["legL"] = max(0.0, s) * 4.5                    # how high each foot lifts
        p["legR"] = max(0.0, -s) * 4.5
        p["stepL"] = s * 2.6                             # forward / back shift of each leg
        p["stepR"] = -s * 2.6
        p["bob"] = -round(abs(math.cos(ph)) * 1.4)       # up on the passing pose
        p["armF"] = -s * 3.0                             # arms swing opposite to the legs
        p["armB"] = s * 3.0
        p["sway"] = -s * 1.4
        p["lean"] = 0.6
    elif anim == "shoot":
        stage = i                                        # 0 wind-up, 1 release, 2 recover
        p["reach"] = (-2.5, 3.5, 1.5)[stage]
        p["lean"] = (-1.0, 1.5, 0.5)[stage]
        p["draw"] = (1.0, 0.0, 0.3)[stage]
        p["flash"] = (0.0, 1.0, 0.35)[stage]
        p["armF"] = (-1.5, -2.5, -1.0)[stage]
        p["sway"] = (-1.0, 1.5, 0.5)[stage]
    return p


def body(cls, p):
    """The parts for one class in one pose."""
    c = CLASSES[cls]
    skin = c.get("skin", SKIN)
    parts = []
    b = p["bob"]
    lean = p["lean"]
    hipY = 41 + b
    shoulderY = 27 + b - p["breath"] * 0.6
    headY = 18 + b - p["breath"] * 0.4
    cx = CX + lean * 0.5
    # legs + boots (robes hide most of the leg; the feet still step)
    for side, lift, step, z in ((-1, p["legL"], p["stepL"], 1.0), (1, p["legR"], p["stepR"], 1.1)):
        lx = cx + side * 3.6 + step * 0.4 - 2.4
        foot = FEET - lift
        if not c["robe"]:
            parts.append(P(rect(lx, hipY - 1, 5, max(3, foot - hipY - 2.5), 1), c["pants"], z, height=2.5, rim=RIM))
        parts.append(P(poly([(lx - 0.5, foot - 4), (lx + 5, foot - 4), (lx + 6.5 + step * 0.3, foot - 1),
                             (lx + 6.5 + step * 0.3, foot), (lx - 0.5, foot)]), c["boot"], z + 0.05, height=2, rim=RIM))
    # cloak / cape behind (archer, assassin, paladin, rogue, warrior get a short cape)
    if cls in ("paladin", "warrior", "assassin", "rogue"):
        capecol = {"paladin": ramp((90, 10, 20), (230, 60, 70)), "warrior": ramp((40, 6, 8), (150, 30, 34)),
                   "assassin": ramp((60, 6, 12), (180, 30, 40)), "rogue": ramp((20, 20, 26), (90, 90, 104))}[cls]
        sw = p["sway"]
        parts.append(P(poly([(cx - 9, shoulderY + 1), (cx + 8, shoulderY + 1), (cx + 10 + sw * 0.4, hipY + 8),
                             (cx - 11 + sw, hipY + 10)]), capecol, 0.2, height=3, noise=0.04))
    # back arm (the left one - darker, behind the body)
    ab = p["armB"]
    parts.append(P(poly([(cx - 10, shoulderY + 1), (cx - 6.5, shoulderY + 1), (cx - 7.5, shoulderY + 11 + ab),
                         (cx - 11.5, shoulderY + 11 + ab)]), c["top"], 0.6, height=2))
    parts.append(P(circ(cx - 9.6, shoulderY + 12.5 + ab, 2.1), skin if cls not in ("paladin", "warrior") else STEELR,
                   0.65, height=1.5))
    # torso / robe
    if c["robe"]:
        sw = p["sway"]
        robe = [(cx - 8, shoulderY), (cx + 8, shoulderY), (cx + 10, hipY), (cx + 12 + sw * 0.5, FEET - 3),
                (cx + 6 + sw, FEET - 1.5), (cx - 6 + sw, FEET - 1.5), (cx - 12 + sw * 0.5, FEET - 3), (cx - 10, hipY)]
        parts.append(P(poly(robe), c["top"], 2, height=6, rim=RIM, noise=0.03, seed=3))
        # a central band / trim down the robe
        parts.append(P(poly([(cx - 1.5, shoulderY + 3), (cx + 1.5, shoulderY + 3), (cx + 2 + sw * 0.4, FEET - 2),
                             (cx - 2 + sw * 0.4, FEET - 2)]), c["trim"], 2.2, height=1.5))
        if cls == "priest":  # a gold cross on the chest
            parts.append(P(lambda s, col: (pygame.draw.rect(s, col, (round(cx - 1), round(shoulderY + 4), 3, 9)),
                                            pygame.draw.rect(s, col, (round(cx - 4), round(shoulderY + 6), 9, 3))),
                           GOLDR, 2.4, height=1.2))
        if cls == "necromancer":  # a bone sash
            parts.append(P(line([(cx - 8, shoulderY + 2), (cx + 7, hipY - 2)], 2), N.BONE, 2.3, height=1))
    else:
        tw = 8.5 + p["breath"] * 0.4
        parts.append(P(poly([(cx - tw, shoulderY), (cx + tw, shoulderY), (cx + tw - 0.5, hipY + 1),
                             (cx - tw + 0.5, hipY + 1)]), c["top"], 2, height=5, rim=RIM, noise=0.03, seed=4))
        parts.append(P(rect(cx - 8, hipY - 2.5, 16, 3), c["trim"], 2.3, height=1.2))       # belt
        parts.append(P(rect(cx - 1.5, hipY - 2.8, 3, 3.5), GOLDR, 2.4, height=1))          # buckle
        if cls in ("paladin", "warrior"):  # pauldrons + a chest plate
            for sx in (-1, 1):
                parts.append(P(ell(cx + sx * 8 - 4.5, shoulderY - 2, 9, 7), STEELR, 2.6, height=3, rim=RIM))
            if cls == "paladin":
                parts.append(P(rect(cx - 5, shoulderY + 3, 10, 9, 2), STEELR, 2.5, height=3, rim=RIM))
                parts.append(P(rect(cx - 1, shoulderY + 4, 2, 7), GOLDR, 2.55, height=1))
        if cls == "archer":  # a quiver strap + quiver on the back
            parts.append(P(line([(cx - 8, shoulderY), (cx + 6, hipY - 3)], 2), c["trim"], 2.4, height=1))
            parts.append(P(rect(cx - 12, shoulderY - 5, 4, 12, 1), WOODR, 0.3, height=2))
            parts.append(P(lambda s, col: [pygame.draw.line(s, col, (round(cx - 11 + k), round(shoulderY - 9)),
                                                            (round(cx - 11 + k), round(shoulderY - 5)), 1)
                                           for k in range(0, 3)], flat((240, 240, 230)), 0.25, flat=True))
        if cls in ("assassin", "rogue"):  # crossed straps
            parts.append(P(line([(cx - 8, shoulderY + 1), (cx + 7, hipY - 3)], 1), c["trim"], 2.4, flat=True))
    # head
    hy = headY
    parts.append(P(ell(cx - 7.5, hy - 7.5, 15, 15), skin, 4, height=6, rim=RIM, dome=0.3, noise=0.0))
    # eyes (2x2, so they survive the 48 px downscale) + a mouth hint
    ey = hy - 0.5
    for ex in (cx - 4.2, cx + 1.8):
        parts.append(P(rect(ex, ey, 2.4, 2.6), flat(c["eyes"]), 6, flat=True))
        parts.append(P(rect(ex + 1.4, ey, 1, 1), EYE_W, 6.1, flat=True))
    if cls not in ("assassin",):
        parts.append(P(rect(cx - 1, hy + 4, 3, 1), flat((150, 70, 60)), 6, flat=True))
    # head gear
    if cls == "archer":
        parts.append(P(poly([(cx - 9, hy + 1), (cx - 8, hy - 7), (cx - 2, hy - 10), (cx + 6, hy - 9), (cx + 10, hy - 3),
                             (cx + 9, hy + 1), (cx + 7, hy - 4), (cx - 6, hy - 4)]), c["hood"], 7, height=3, rim=RIM))
        parts.append(P(poly([(cx + 6, hy - 9), (cx + 13, hy - 12), (cx + 9, hy - 6)]), c["hood"], 7.1, height=1.5))
    elif cls == "assassin":
        parts.append(P(poly([(cx - 9, hy + 3), (cx - 8.5, hy - 7), (cx, hy - 10.5), (cx + 8.5, hy - 7), (cx + 9, hy + 3),
                             (cx + 7, hy - 2.5), (cx - 7, hy - 2.5)]), c["hood"], 7, height=3, rim=RIM))
        parts.append(P(poly([(cx - 7.5, hy + 1.8), (cx + 7.5, hy + 1.8), (cx + 6, hy + 7), (cx - 6, hy + 7)]),
                       c["hood"], 7.2, height=2))            # the mask over the lower face
        for sx in (-1, 1):
            parts.append(P(rect(cx + sx * 7 - 1, hy - 6, 2, 2), c["trim"], 7.3, flat=True))
    elif cls == "necromancer":
        parts.append(P(poly([(cx - 10, hy + 6), (cx - 9, hy - 6), (cx, hy - 11), (cx + 9, hy - 6), (cx + 10, hy + 6),
                             (cx + 7, hy - 2), (cx - 7, hy - 2)]), c["hood"], 7, height=3, rim=RIM))
        for ex in (cx - 4.2, cx + 1.8):  # glowing eyes in the hood's shadow
            parts.append(P(rect(ex, hy - 0.5, 2.4, 2.4), flat((150, 255, 170)), 7.5, flat=True, emit=(110, 255, 140)))
    elif cls == "paladin":
        parts.append(P(poly([(cx - 8.5, hy + 1), (cx - 8, hy - 6), (cx, hy - 9.5), (cx + 8, hy - 6), (cx + 8.5, hy + 1),
                             (cx + 6.5, hy - 2.5), (cx - 6.5, hy - 2.5)]), STEELR, 7, height=3, rim=RIM))
        parts.append(P(rect(cx - 1, hy - 11, 2, 7), GOLDR, 7.1, height=1))                     # a crest
        parts.append(P(rect(cx - 8.5, hy - 3.5, 17, 1.5), GOLDR, 7.2, flat=True))
    elif cls == "priest":
        parts.append(P(poly([(cx - 8, hy - 1), (cx - 7, hy - 7), (cx, hy - 9), (cx + 7, hy - 7), (cx + 8, hy - 1),
                             (cx + 6, hy - 4), (cx - 6, hy - 4)]), c["hair"], 7, height=3, rim=RIM))
        parts.append(P(lambda s, col: pygame.draw.ellipse(s, col, (round(cx - 7), round(hy - 13), 14, 4), 1),
                       GOLDR, 7.4, flat=True, emit=(255, 230, 140)))          # a halo
    elif cls == "rogue":
        parts.append(P(poly([(cx - 8, hy), (cx - 8, hy - 6), (cx - 2, hy - 9.5), (cx + 6, hy - 8), (cx + 8.5, hy - 2),
                             (cx + 6, hy - 4.5), (cx + 1, hy - 5.5), (cx - 5, hy - 4)]), c["hair"], 7, height=3, rim=RIM))
        parts.append(P(rect(cx - 7.5, hy + 3.5, 15, 3.5, 1), ramp((60, 20, 20), (180, 60, 60)), 7.1, height=1.5))  # scarf
    elif cls == "warrior":
        parts.append(P(poly([(cx - 8.5, hy + 2), (cx - 8, hy - 6), (cx, hy - 9.5), (cx + 8, hy - 6), (cx + 8.5, hy + 2),
                             (cx + 6.5, hy - 2.5), (cx - 6.5, hy - 2.5)]), STEELR, 7, height=3, rim=RIM))
        parts.append(P(rect(cx - 0.8, hy - 2.5, 1.6, 4), STEELR, 7.1, height=1))             # nose guard
        parts.append(P(poly([(cx - 3, hy - 9), (cx + 3, hy - 9), (cx + 1, hy - 14), (cx - 2, hy - 13)]),
                       ramp((80, 10, 12), (240, 70, 60)), 6.9, height=1.5))                 # a red plume
    elif cls == "wizard":
        tilt = p["sway"] * 0.5
        parts.append(P(poly([(cx - 11, hy - 3), (cx + 11, hy - 3), (cx + 8, hy - 7), (cx + 2 + tilt, hy - 15),
                             (cx + 7 + tilt * 1.5, hy - 16.5), (cx - 1 + tilt, hy - 15.5), (cx - 7, hy - 7)]),
                       c["hood"], 7, height=3, rim=RIM))                                     # a pointy hat
        parts.append(P(rect(cx - 8, hy - 5, 16, 2), c["trim"], 7.1, flat=True))
        parts.append(P(poly([(cx - 8, hy - 2), (cx - 9, hy + 5), (cx - 6, hy + 2)]), c["hair"], 6.8, height=1.5))
    # the front arm + the weapon
    parts += front_arm_and_weapon(cls, c, p, cx, shoulderY, hipY, skin)
    return parts


def front_arm_and_weapon(cls, c, p, cx, shoulderY, hipY, skin):
    out = []
    a = p["armF"]
    reach = p["reach"]
    hx, hy = cx + 11 + reach, shoulderY + 10 + a        # the hand
    sleeve = c["top"] if cls not in ("paladin", "warrior") else STEELR
    out.append(P(poly([(cx + 6.5, shoulderY + 1), (cx + 10, shoulderY + 1), (hx + 1.5, hy - 1), (hx - 2, hy + 1)]),
                 sleeve, 8, height=2, rim=RIM))
    glove = skin if cls not in ("paladin", "warrior", "assassin") else (STEELR if cls != "assassin" else c["hood"])
    fl = p["flash"]

    def flash(x, y, col, r=4.0):
        x = min(x, W - 2 - r * 1.3)
        if fl > 0:
            rr = r * fl
            out.append(P(poly([(x - rr, y), (x, y - rr * 0.55), (x + rr * 1.3, y), (x, y + rr * 0.55)]), flat(col), 11,
                         flat=True, emit=col))
            out.append(P(poly([(x, y - rr), (x + rr * 0.5, y), (x, y + rr), (x - rr * 0.5, y)]),
                         flat((255, 255, 240)), 11.1, flat=True))

    if cls == "archer":  # a bow held upright in front, the string drawn back on the wind-up
        bx = hx + 2
        out.append(P(lambda s, col: pygame.draw.arc(s, col, (round(bx - 4), round(hy - 13), 9, 26), -1.25, 1.25, 2),
                     WOODR, 9, height=1.5, rim=RIM))
        pull = p["draw"] * 5
        out.append(P(line([(bx + 1, hy - 12), (bx - pull, hy), (bx + 1, hy + 12)], 1), flat((236, 236, 220)), 9.1,
                     flat=True))
        if p["draw"] > 0.2 or fl > 0:
            ax0 = bx - pull if p["draw"] > 0.2 else bx + 2
            ax1 = min(ax0 + 10, W - 4)
            out.append(P(line([(ax0, hy), (ax1, hy)], 1), WOODR, 9.2, flat=True))
            out.append(P(poly([(ax1, hy - 1.5), (ax1 + 3, hy), (ax1, hy + 1.5)]), STEELR, 9.3, flat=True))
        flash(bx + 16, hy, (190, 255, 140))
    elif cls in ("assassin", "rogue"):  # daggers (the assassin holds a second one in the back hand)
        col = c["trim"] if cls == "assassin" else STEELR
        out.append(P(poly([(hx, hy - 1.5), (hx + 9, hy - 2.5), (hx + 11, hy - 1), (hx + 9, hy + 0.5), (hx, hy + 1)]),
                     col if cls == "assassin" else STEELR, 9, height=1.5, rim=RIM))
        out.append(P(rect(hx - 2, hy - 2, 3, 4), WOODR, 9.1, height=1))
        if cls == "assassin":
            bxh = cx - 10
            out.append(P(poly([(bxh, shoulderY + 12 + p["armB"]), (bxh - 2, shoulderY + 3 + p["armB"]),
                               (bxh - 0.5, shoulderY + 2 + p["armB"]), (bxh + 1, shoulderY + 11 + p["armB"])]),
                         c["trim"], 0.7, height=1))
        flash(hx + 13, hy - 1, (255, 120, 110) if cls == "assassin" else (230, 230, 255), 3.5)
    elif cls == "necromancer":  # a bone staff topped with a skull, green fire in its eyes
        sx = hx + 1
        out.append(P(line([(sx, hy - 18), (sx - 1, FEET - 1)], 2), N.BONE, 9, height=1.2, rim=RIM))
        out.append(P(circ(sx + 0.5, hy - 20, 3.6), N.BONE, 9.2, height=2.5, rim=RIM, dome=0.55))
        out.append(P(rect(sx - 1.5, hy - 21, 1.5, 1.5), flat((120, 255, 150)), 9.3, flat=True, emit=(110, 255, 140)))
        out.append(P(rect(sx + 1, hy - 21, 1.5, 1.5), flat((120, 255, 150)), 9.3, flat=True, emit=(110, 255, 140)))
        flash(sx + 6, hy - 20, (120, 255, 150), 5)
    elif cls == "paladin":  # a sword in the right hand, a white shield on the left arm
        out.append(P(poly([(hx, hy - 1.2), (hx + 10, hy - 2), (hx + 12, hy - 0.5), (hx + 10, hy + 1), (hx, hy + 1.2)]),
                     STEELR, 9, height=1.5, rim=RIM))
        out.append(P(rect(hx - 1, hy - 4, 2.5, 8), GOLDR, 9.1, height=1))
        shy = shoulderY + 6 + p["armB"]
        out.append(P(poly([(cx - 15, shy), (cx - 6, shy), (cx - 6, shy + 8), (cx - 10.5, shy + 13), (cx - 15, shy + 8)]),
                     ramp((150, 156, 176), (255, 255, 255)), 8.5, height=3, rim=RIM))
        out.append(P(lambda s, col: (pygame.draw.rect(s, col, (round(cx - 11.5), round(shy + 2), 2, 8)),
                                     pygame.draw.rect(s, col, (round(cx - 14), round(shy + 4), 7, 2))),
                     GOLDR, 8.6, flat=True))
        flash(hx + 13, hy - 0.5, (255, 240, 170))
    elif cls == "priest":  # a gold sceptre with a glowing orb
        sx = hx + 1
        out.append(P(line([(sx, hy - 12), (sx, hy + 7)], 2), GOLDR, 9, height=1, rim=RIM))
        out.append(P(circ(sx, hy - 14, 3.2), ramp((200, 160, 40), (255, 255, 220)), 9.2, height=2.5,
                     emit=(255, 240, 160), dome=0.6))
        flash(sx + 6, hy - 14, (255, 240, 160), 5)
    elif cls == "warrior":  # a broad sword
        out.append(P(poly([(hx, hy - 2), (hx + 11, hy - 3), (hx + 13.5, hy - 0.5), (hx + 11, hy + 2), (hx, hy + 2)]),
                     STEELR, 9, height=2, rim=RIM))
        out.append(P(rect(hx - 1.5, hy - 5, 3, 10), ramp((60, 40, 14), (196, 150, 70)), 9.1, height=1))
        flash(hx + 14, hy - 0.5, (255, 230, 200))
    elif cls == "wizard":  # a tall staff with a violet gem
        sx = hx + 1
        out.append(P(line([(sx, hy - 17), (sx - 1, FEET - 1)], 2), WOODR, 9, height=1.2, rim=RIM))
        out.append(P(poly([(sx, hy - 23), (sx + 3, hy - 19), (sx, hy - 15), (sx - 3, hy - 19)]),
                     ramp((70, 20, 140), (240, 200, 255)), 9.2, height=2, emit=(200, 140, 255)))
        flash(sx + 6, hy - 19, (210, 160, 255), 5)
    out.append(P(circ(hx, hy, 2.3), glove, 9.5, height=1.5, rim=RIM))
    return out


# --------------------------------------------------------------- output
def paint(cls):
    up = lambda s: pygame.transform.scale(s, (s.get_width() * UP, s.get_height() * UP))
    frames = {}
    for anim, n in (("idle", 4), ("walk", 6), ("shoot", 3)):
        frames[anim] = [N.render(body(cls, pose_for(anim, i, n)), W, H)[0] for i in range(n)]
    pygame.image.save(up(frames["idle"][0]), os.path.join(OUT, f"player_{cls}.png"))
    for anim, fr in frames.items():
        pygame.image.save(up(N.strip(fr)), os.path.join(OUT, f"player_{cls}_{anim}.png"))
    print(f"painted {cls}: idle 4, walk 6, shoot 3")


def sheet():
    """Every class: the still at 48 px and 3x, then idle / walk / shoot frames, on grass and dark."""
    os.makedirs(SHEET_DIR, exist_ok=True)
    cell = 112
    rows = list(CLASSES)
    w = 48 + 8 + 3 * 48 + 8 + 13 * 66 + 20
    sheet_s = pygame.Surface((w, len(rows) * (cell + 8) * 2 + 10))
    sheet_s.fill((20, 18, 26))
    y = 6
    for bg in ((74, 110, 60), (26, 24, 34)):
        for cls in rows:
            pygame.draw.rect(sheet_s, bg, (0, y - 4, w, cell + 8))
            still = pygame.image.load(os.path.join(OUT, f"player_{cls}.png")).convert_alpha()
            small = pygame.transform.smoothscale(still, (48, 48))
            sheet_s.blit(small, (4, y + 30))
            sheet_s.blit(pygame.transform.scale(small, (144, 144)).subsurface((0, 16, 144, 112)), (60, y))
            x = 60 + 150
            for anim, n in (("idle", 4), ("walk", 6), ("shoot", 3)):
                st = pygame.image.load(os.path.join(OUT, f"player_{cls}_{anim}.png")).convert_alpha()
                fw = st.get_width() // n
                for k in range(n):
                    f = st.subsurface((k * fw, 0, fw, st.get_height()))
                    sheet_s.blit(pygame.transform.smoothscale(f, (64, 64)), (x, y + 24))
                    x += 66
                x += 10
            y += cell + 8
    pygame.image.save(sheet_s, os.path.join(SHEET_DIR, "sheet.png"))
    print("sheet ->", os.path.join(SHEET_DIR, "sheet.png"))


def main():
    pygame.init()
    pygame.display.set_mode((10, 10))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--sheet" not in sys.argv:
        for cls in (args or list(CLASSES)):
            paint(cls)
    sheet()


if __name__ == "__main__":
    main()
