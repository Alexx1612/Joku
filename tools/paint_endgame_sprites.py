"""
Paints the hand-made PNG sprites for the V0.2 "final final" endgame characters:
the Mad God's two evolutions ("Unhinged", "Absolutely Livid") and Brother
Hammerstein. Every pixel is placed here by hand-chosen shapes on a small canvas,
then outlined and nearest-neighbour upscaled in the same chunky style as the
other hand-painted boss PNGs (assets/sprites/v0.2/enemies/). Wholly original.

Run: python tools/paint_endgame_sprites.py   (writes into assets/sprites/v0.2/enemies/)
"""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sprites", "v0.2",
                   "enemies")
OUTLINE = (16, 8, 18)
UP = 8


def outline(surf, color=OUTLINE):
    w, h = surf.get_size()
    solid = [[surf.get_at((x, y))[3] > 0 for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            if solid[y][x]:
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and solid[y + dy][x + dx]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                surf.set_at((x, y), (*color, 255))


def mirror_left(surf):
    """Copy the left half onto the right (a symmetric base, asymmetric details go on after)."""
    w, h = surf.get_size()
    for y in range(h):
        for x in range(w // 2):
            surf.set_at((w - 1 - x, y), surf.get_at((x, y)))


def px(surf, pts, color):
    for (x, y) in pts:
        surf.set_at((x, y), (*color, 255))


def save(surf, name):
    big = pygame.transform.scale(surf, (surf.get_width() * UP, surf.get_height() * UP))
    pygame.image.save(big, os.path.join(OUT, name))
    return big


# ------------------------------------------------------------------ palettes
GOLD, GOLD_D, GOLD_L = (250, 208, 80), (184, 132, 36), (255, 244, 170)
FACE, FACE_D = (244, 230, 200), (196, 174, 142)
VIO, VIO_D, VIO_L, CRACK = (140, 80, 204), (86, 42, 138), (190, 134, 240), (255, 150, 255)
RED, RED_D, RED_L = (204, 40, 46), (122, 16, 26), (246, 96, 86)
WING, WING_D, WING_L = (118, 18, 34), (70, 8, 18), (170, 40, 56)
FIRE, FIRE_Y, FIRE_W = (255, 128, 30), (255, 214, 70), (255, 250, 210)


def paint_unhinged():
    W, H = 40, 30
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    # four arms (behind the robe): upper pair raised, lower pair flung out
    for (a, b) in (((14, 15), (6, 7)), ((14, 18), (4, 21))):
        pygame.draw.line(s, VIO_D, a, b, 3)
        pygame.draw.line(s, VIO, (a[0], a[1] - 1), (b[0], b[1] - 1), 1)
    # hands with crackling sparks
    for c in ((5, 6), (3, 21)):
        pygame.draw.circle(s, FACE, c, 2)
        px(s, [(c[0] - 2, c[1] - 2), (c[0] + 2, c[1] - 3)], CRACK)
    # robe: a wide trapezoid, lit on the left, dark on the right
    pygame.draw.polygon(s, VIO, [(14, 13), (26, 13), (31, 28), (9, 28)])
    pygame.draw.polygon(s, VIO_L, [(14, 13), (16, 13), (12, 28), (9, 28)])
    pygame.draw.polygon(s, VIO_D, [(24, 13), (26, 13), (31, 28), (27, 28)])
    # gold collar + hem
    pygame.draw.line(s, GOLD, (14, 13), (25, 13), 2)
    pygame.draw.line(s, GOLD, (9, 27), (30, 27), 2)
    px(s, [(12, 28), (16, 28), (20, 28), (24, 28), (28, 28)], GOLD_D)
    # head
    pygame.draw.ellipse(s, FACE, (15, 5, 10, 9))
    pygame.draw.ellipse(s, FACE_D, (21, 7, 4, 6))
    mirror_left(s)  # symmetric base: arms, robe and head
    # re-shade after the mirror so the light still comes from the left
    pygame.draw.polygon(s, VIO_D, [(24, 13), (26, 13), (31, 28), (27, 28)])
    pygame.draw.line(s, GOLD, (9, 27), (30, 27), 2)
    # jagged, uneven crown (asymmetric on purpose - he made it himself, badly)
    pygame.draw.rect(s, GOLD, (14, 4, 12, 2))
    for (x, top) in ((14, 0), (16, 2), (18, 1), (20, 0), (22, 2), (24, 1), (25, 3)):
        pygame.draw.line(s, GOLD, (x, top), (x, 4))
    px(s, [(15, 4), (19, 4), (23, 4)], (255, 90, 200))       # gems
    px(s, [(14, 1), (20, 1)], GOLD_L)
    # face: three red eyes, a wide crooked grin
    px(s, [(17, 8), (18, 8), (22, 8), (23, 8), (20, 7)], (255, 60, 60))
    px(s, [(17, 7), (22, 7)], (120, 20, 20))
    for x in range(17, 24):
        s.set_at((x, 11 if x % 2 else 10), (*OUTLINE, 255))
    px(s, [(18, 11), (20, 11), (22, 11)], (255, 255, 255))   # teeth
    # glowing cracks running down the robe
    for path in (((18, 15), (17, 18), (19, 21), (17, 25)), ((23, 16), (24, 20), (22, 23), (23, 26))):
        pygame.draw.lines(s, CRACK, False, path, 1)
    px(s, [(20, 17), (21, 24)], (255, 220, 255))
    outline(s)
    return s


def paint_livid():
    W, H = 44, 30
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    # great crimson wings, ribbed, behind everything
    wing = [(18, 14), (8, 3), (3, 2), (1, 9), (4, 12), (0, 17), (5, 19), (3, 24), (10, 22), (16, 20)]
    pygame.draw.polygon(s, WING, wing)
    for rib in (((18, 14), (3, 2)), ((18, 15), (1, 11)), ((17, 17), (2, 18)), ((16, 19), (4, 23))):
        pygame.draw.line(s, WING_D, rib[0], rib[1], 1)
    pygame.draw.line(s, WING_L, (17, 13), (8, 3), 1)
    # arms raised in a fury, fists on fire
    pygame.draw.line(s, RED_D, (17, 15), (11, 8), 3)
    pygame.draw.circle(s, FACE, (10, 7), 2)
    # robe
    pygame.draw.polygon(s, RED, [(17, 13), (27, 13), (33, 28), (11, 28)])
    pygame.draw.polygon(s, RED_L, [(17, 13), (19, 13), (14, 28), (11, 28)])
    pygame.draw.line(s, GOLD, (17, 13), (26, 13), 2)
    pygame.draw.line(s, GOLD, (11, 27), (32, 27), 2)
    # head
    pygame.draw.ellipse(s, FACE, (17, 5, 10, 9))
    mirror_left(s)
    pygame.draw.polygon(s, RED_D, [(25, 13), (27, 13), (33, 28), (29, 28)])
    pygame.draw.line(s, GOLD, (11, 27), (32, 27), 2)
    pygame.draw.ellipse(s, FACE_D, (23, 7, 4, 6))
    # burning crown: a gold band with flames licking up out of it
    pygame.draw.rect(s, GOLD, (17, 4, 10, 2))
    for (x, top, col) in ((17, 1, FIRE), (18, 0, FIRE_Y), (20, 2, FIRE), (21, 0, FIRE_W), (22, 1, FIRE_Y),
                          (24, 2, FIRE), (25, 0, FIRE_Y), (26, 2, FIRE)):
        pygame.draw.line(s, col, (x, top), (x, 3))
    # fists ablaze
    for c in ((10, 6), (33, 6)):
        px(s, [(c[0], c[1] - 2), (c[0] - 1, c[1] - 1), (c[0] + 1, c[1] - 1)], FIRE)
        s.set_at((c[0], c[1] - 3), (*FIRE_Y, 255))
    # a furious red flush over the face
    pygame.draw.ellipse(s, (250, 176, 150), (18, 6, 8, 7))
    # dark sockets with burning pupils, brows slanted down to the middle
    pygame.draw.rect(s, (60, 8, 10), (18, 8, 3, 2))
    pygame.draw.rect(s, (60, 8, 10), (23, 8, 3, 2))
    px(s, [(19, 8), (24, 8)], (255, 255, 120))
    px(s, [(17, 6), (18, 6), (19, 7), (20, 7), (26, 6), (25, 6), (24, 7), (23, 7)], OUTLINE)
    # an open snarl, corners turned down, teeth bared
    pygame.draw.rect(s, (50, 6, 10), (19, 11, 6, 2))
    px(s, [(18, 12), (25, 12)], OUTLINE)
    px(s, [(20, 11), (22, 11), (24, 11)], (255, 255, 255))
    # embers drifting off the robe
    px(s, [(15, 22), (29, 19), (22, 24)], FIRE_Y)
    outline(s)
    return s


def paint_hammerstein():
    W, H = 18, 22
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    SKIN, SKIN_D = (230, 182, 142), (192, 140, 104)
    BEARD, BEARD_D = (208, 208, 216), (150, 150, 160)
    ROBE, ROBE_D = (124, 72, 42), (86, 48, 28)
    APRON, APRON_D = (70, 50, 36), (48, 34, 24)
    # legs + boots
    pygame.draw.rect(s, (70, 50, 40), (6, 18, 2, 2))
    pygame.draw.rect(s, (70, 50, 40), (10, 18, 2, 2))
    pygame.draw.rect(s, (36, 28, 22), (5, 20, 3, 1))
    pygame.draw.rect(s, (36, 28, 22), (10, 20, 3, 1))
    # robe body + sleeves
    pygame.draw.polygon(s, ROBE, [(5, 8), (13, 8), (15, 18), (3, 18)])
    pygame.draw.polygon(s, ROBE_D, [(11, 8), (13, 8), (15, 18), (12, 18)])
    # leather apron with a glowing burn mark
    pygame.draw.rect(s, APRON, (6, 10, 6, 8))
    pygame.draw.line(s, APRON_D, (11, 10), (11, 17))
    s.set_at((8, 14), (255, 150, 60, 255))
    # bald head
    pygame.draw.ellipse(s, SKIN, (6, 1, 6, 6))
    pygame.draw.ellipse(s, SKIN_D, (9, 2, 3, 4))
    s.set_at((7, 1), (250, 214, 180, 255))  # the shine on the dome
    px(s, [(7, 4), (10, 4)], (30, 24, 24))  # eyes
    # big grey beard over the chest
    pygame.draw.polygon(s, BEARD, [(6, 5), (12, 5), (11, 10), (9, 12), (7, 10)])
    pygame.draw.line(s, BEARD_D, (10, 6), (9, 11))
    # hammer in his right hand (our left), raised
    pygame.draw.line(s, (112, 80, 50), (3, 13), (2, 5), 1)
    pygame.draw.rect(s, (150, 156, 168), (0, 3, 5, 3))
    pygame.draw.line(s, (210, 214, 224), (0, 3), (4, 3))
    pygame.draw.circle(s, SKIN, (3, 13), 1)
    outline(s)
    return s


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((10, 10))
    os.makedirs(OUT, exist_ok=True)
    save(paint_unhinged(), "enemy_mad_god_unhinged.png")
    save(paint_livid(), "enemy_mad_god_livid.png")
    save(paint_hammerstein(), "enemy_npc_hammerstein.png")
    print("painted 3 sprites into", OUT)
    sys.exit(0)
