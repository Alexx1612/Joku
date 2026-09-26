"""
Procedural pixel-art sprite generation.

RotMG's look: small chibi/front-facing characters, bold flat colours, and a
crisp 1px black outline around every silhouette, with just enough shading
to read as more than a flat cutout. Every sprite here is originally
synthesized at runtime from a tiny ASCII "pixel grid" DSL (an auto-shading
pass - soft top-down light + edge rim-light - and an auto-outline pass do
the work a hand-painted highlight/shadow layer would normally do, so the
grids only need to define flat base colours), with hand-painted PNG
replacements (see `assets/sprites/`, made with the pixel-mcp tool - still
100% original art, no RotMG assets) opportunistically loading in front of
it per-sprite, falling back to the procedural grid if the file is missing
or fails to load.
"""
import math
import os

import pygame

_SPRITE_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sprites", "v0.2")


def _load_art(filename, size):
    """Load a hand-painted PNG replacement, scaled (nearest-neighbour, so it
    stays crisp) to the same on-screen size the procedural grid would use.
    `size` is either an int (square target) or an (w, h) tuple (e.g. bosses,
    whose target keeps the original grid's non-square aspect ratio).
    Returns None on any failure so the caller can fall back to the grid."""
    target = (size, size) if isinstance(size, int) else tuple(size)
    path = os.path.join(_SPRITE_DIR, filename)
    if not os.path.isfile(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        if img.get_size() != target:
            img = pygame.transform.scale(img, target)
        return img
    except Exception:
        return None


def _art_native_size(filename):
    """Peek at a hand-painted PNG's own pixel dimensions (its aspect ratio may
    differ per-sprite - e.g. a tall wraith vs. a wide sandworm - unlike the
    procedural grids' original shared aspect). Returns None if unavailable."""
    path = os.path.join(_SPRITE_DIR, filename)
    if not os.path.isfile(path):
        return None
    try:
        return pygame.image.load(path).get_size()
    except Exception:
        return None

PX = 3  # base logical-pixel block before smart upscaling (kept small - see _upscale)
# On-screen size, decoupled from the Scale2x detail pass: Scale2x is run for QUALITY
# (smoother edges) then smoothscaled back down to this footprint. Matches the original
# v0.1 sprite size - a swarm-density test showed the naive Scale2x output (192px, 2x
# v0.1's 96px) made enemies fully overlap each other and hide bullets underneath them.
FINAL_SIZE = 48
BOSS_FINAL_SIZE = 76
OUTLINE = (10, 10, 12)

_cache = {}


def _shade(color, factor):
    return tuple(max(0, min(255, int(round(c * factor)))) for c in color)


def _scale2x(surf):
    """
    Scale2x/AdvMAME2x: a smart pixel-art upscaler that extends diagonal
    edges based on each pixel's neighbours, instead of just replicating
    blocks like nearest-neighbour scaling does. This is what makes "2x"
    mean more detail/quality rather than the same blocky pixels rendered
    bigger - it's run on the small base render, not a plain size multiplier.
    """
    w, h = surf.get_size()
    out = pygame.Surface((w * 2, h * 2), pygame.SRCALPHA)
    get = surf.get_at
    src = [[get((x, y)) for x in range(w)] for y in range(h)]

    def at(x, y):
        return src[max(0, min(h - 1, y))][max(0, min(w - 1, x))]

    for y in range(h):
        for x in range(w):
            p = src[y][x]
            a, b, c, d = at(x, y - 1), at(x + 1, y), at(x - 1, y), at(x, y + 1)
            e0 = a if (c == a and c != d and a != b) else p
            e1 = b if (a == b and a != c and b != d) else p
            e2 = c if (d == c and d != b and c != a) else p
            e3 = d if (b == d and b != a and d != c) else p
            out.set_at((x * 2, y * 2), e0)
            out.set_at((x * 2 + 1, y * 2), e1)
            out.set_at((x * 2, y * 2 + 1), e2)
            out.set_at((x * 2 + 1, y * 2 + 1), e3)
    return out


def _upscale(surf, passes, final_size=None):
    for _ in range(passes):
        surf = _scale2x(surf)
    if final_size:
        surf = pygame.transform.smoothscale(surf, final_size)
    return surf


def _autline_and_render(grid, palette, scale, shaded=True):
    h = len(grid)
    w = max(len(r) for r in grid)

    def cell(x, y):
        if 0 <= y < h:
            row = grid[y]
            if 0 <= x < len(row):
                return row[x]
        return " "

    def filled(x, y):
        return cell(x, y) not in (" ", ".")

    surf = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)

    # pass 1: black outline wherever a filled cell touches an empty/out-of-bounds cell
    for y in range(h):
        for x in range(w):
            if not filled(x, y):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if not filled(x + dx, y + dy):
                    ox, oy = (x + dx) * scale, (y + dy) * scale
                    surf.fill(OUTLINE, (ox, oy, scale, scale))

    # pass 2: coloured pixels, lightly shaded for a sense of volume:
    #   - a soft vertical gradient (lit from above, like the genre's sprites)
    #   - a rim-light on the top/left-facing edges of the silhouette
    for y in range(h):
        for x in range(w):
            code = cell(x, y)
            if code in (" ", "."):
                continue
            color = palette.get(code, (255, 0, 255))
            if shaded:
                grad = 1.14 - 0.24 * (y / max(1, h - 1))
                color = _shade(color, grad)
                if not filled(x - 1, y) or not filled(x, y - 1):
                    color = _shade(color, 1.16)
            surf.fill(color, (x * scale, y * scale, scale, scale))
    return surf


# ---------------------------------------------------------------- 16x16 --
# shared skin tone code: 'h' = skin. Each class adds a hat/hood + weapon hint.
_WIZARD = [
    "  . mmmm .  .  .",
    "  .mmmmmmm  .  .",
    "  mmmCCCmm  .  .",
    " mmCChhCCmm .  .",
    " mChhhhhhCm .  .",
    " ChheEhEheC .  .",
    " Chhhhhhh Cw   .",
    "  Chhhhhh Cw   .",
    "  .CCbbbbC w   .",
    "  .CbCCCbC ww  .",
    "  CCbCCCbCC .  .",
    "  CbbCCCbbC .  .",
    "  .bb   bb. .  .",
    "  .ll   ll. .  .",
    "  .kk   kk. .  .",
    "  .  .  .  .  . ",
]
_WIZARD_PAL = {"m": (60, 40, 130), "C": (100, 60, 190), "h": (245, 205, 170),
               "e": (25, 25, 30), "E": (25, 25, 30), "b": (80, 50, 160), "l": (40, 30, 30),
               "k": (30, 25, 20), "w": (150, 90, 230)}

_ARCHER = [
    "  .  hhhh  .  . ",
    "  . hhhhhh .  . ",
    "  .gghheghg.  . ",
    "  .ghhhhhhg.  . ",
    "  .gg hh gg.  . ",
    "   .ggggg. .  b ",
    "   gCCCCCg  b   ",
    "   gCCCCCg b    ",
    "   .CggggC.b    ",
    "   .CgCCgC. b   ",
    "   gCgCCgCg  b  ",
    "   gggCCggg .   ",
    "   .gg   gg.  . ",
    "   .ll   ll.  . ",
    "   .kk   kk.  . ",
    "  .  .  .  .  . ",
]
_ARCHER_PAL = {"g": (40, 100, 45), "h": (245, 205, 170), "e": (25, 25, 30), "E": (25, 25, 30),
               "C": (95, 150, 70), "l": (55, 40, 25), "k": (35, 28, 20), "b": (150, 110, 60)}

_WARRIOR = [
    "  . ssssss .  . ",
    "  .ssssssss.  . ",
    "  .shhhhhhs.  . ",
    "  .hheEheEh.  . ",
    "  .hhhhhhhh.  . ",
    "  . RRRRRR .  r ",
    "   RCCCCCCR  r  ",
    "   RCCCCCCR r   ",
    "   .CRRRRC.r    ",
    "   .RCCCCR. .   ",
    "   RCRRRCRR .   ",
    "   RRRCCRRR .   ",
    "   .RR   RR.  . ",
    "   .ll   ll.  . ",
    "   .kk   kk.  . ",
    "  .  .  .  .  . ",
]
_WARRIOR_PAL = {"s": (140, 140, 150), "h": (245, 205, 170), "e": (25, 25, 30), "E": (25, 25, 30),
                "R": (120, 30, 30), "C": (170, 45, 45), "l": (40, 30, 30),
                "k": (35, 28, 20), "r": (190, 190, 200)}

_PRIEST = [
    "  .  yyyy  .  . ",
    "  . yhhhhy .  . ",
    "  .yhhhhhhy.  . ",
    "  .whheEeEh.  . ",
    "  .whhhhhh .  . ",
    "  . wwwwww .  w ",
    "   wCCCCCCw  w  ",
    "   wCCyyCCw w   ",
    "   .CyCCyC.w    ",
    "   .wCyyCw.  .  ",
    "   wCwwwCww  .  ",
    "   wwwCCwww .   ",
    "   .ww   ww.  . ",
    "   .ll   ll.  . ",
    "   .kk   kk.  . ",
    "  .  .  .  .  . ",
]
_PRIEST_PAL = {"y": (250, 225, 120), "h": (245, 205, 170), "e": (25, 25, 30), "E": (25, 25, 30),
               "w": (232, 228, 215), "C": (200, 195, 175), "l": (60, 50, 40), "k": (200, 195, 180)}

_ROGUE = [
    "  .  nnnn  .  . ",
    "  . nnnnnn .  . ",
    "  .nnhheghn.  . ",
    "  .nhhhhhhn.  . ",
    "  .nn hh nn.  . ",
    "   .nnnnn. .  w ",
    "   dCCCCCd  w   ",
    "   dCCCCCd w    ",
    "   .CddddC.w    ",
    "   .CdCCdC. w   ",
    "   dCdCCdCd  w  ",
    "   dddCCddd .   ",
    "   .dd   dd.  . ",
    "   .ll   ll.  . ",
    "   .kk   kk.  . ",
    "  .  .  .  .  . ",
]
_ROGUE_PAL = {"n": (35, 35, 40), "h": (245, 205, 170), "e": (25, 25, 30), "E": (25, 25, 30),
              "g": (25, 25, 30), "C": (96, 70, 46), "d": (55, 50, 58), "w": (210, 210, 220),
              "l": (40, 30, 30), "k": (30, 25, 20)}

_NECROMANCER = [
    "  . mmmm .  .  .",
    "  .mmmmmmm  .  .",
    "  mmmCCCmm  .  .",
    " mmCChhCCmm .  .",
    " mChhhhhhCm .  .",
    " ChheEhEheC .  .",
    " Chhhhhhh Cw   .",
    "  Chhhhhh Cw   .",
    "  .CCSSSSC w   .",
    "  .CSCCCSC ww  .",
    "  CCSCCCSCC .  .",
    "  CSSCCCSSC .  .",
    "  .SS   SS. .  .",
    "  .ll   ll. .  .",
    "  .kk   kk. .  .",
    "  .  .  .  .  . ",
]
_NECROMANCER_PAL = {"m": (28, 44, 34), "C": (52, 82, 62), "h": (245, 205, 170),
                     "e": (25, 25, 30), "E": (25, 25, 30), "S": (82, 42, 112),
                     "w": (140, 220, 140), "l": (30, 30, 26), "k": (24, 22, 20)}

_PALADIN = [
    "  . ssssss .  . ",
    "  .ssssssss.  . ",
    "  .shhhhhhs.  . ",
    "  .hheEheEh.  . ",
    "  .hhhhhhhh.  . ",
    "  . BBBBBB .  r ",
    "   BCCCCCCB  r  ",
    "   BCCggCCB r   ",
    "   .CBggBC.r    ",
    "   .BCCCCB. .   ",
    "   BCBggBCB .   ",
    "   BBBCCBBB .   ",
    "   .BB   BB.  . ",
    "   .ll   ll. .  ",
    "   .kk   kk. .  ",
    "  .  .  .  .  . ",
]
_PALADIN_PAL = {"s": (205, 205, 216), "h": (245, 205, 170), "e": (25, 25, 30), "E": (25, 25, 30),
                "B": (70, 90, 150), "C": (112, 142, 202), "g": (230, 200, 90),
                "r": (222, 222, 232), "l": (40, 35, 40), "k": (35, 32, 34)}

_ASSASSIN = [
    "  .  nnnn  .  . ",
    "  . nnnnnn .  . ",
    "  .nnhheghn.  . ",
    "  .nhhhhhhn.  . ",
    "  .nn hh nn.  . ",
    "   .nnnnn. .  w ",
    "   RCCCCCR  w   ",
    "   RCCCCCR w    ",
    "   .CRRRRC.w    ",
    "   .RCCCCR. w   ",
    "   RCRRRCRR  w  ",
    "   RRRCCRRR .   ",
    "   .RR   RR.  . ",
    "   .ll   ll.  . ",
    "   .kk   kk.  . ",
    "  .  .  .  .  . ",
]
_ASSASSIN_PAL = {"n": (20, 20, 24), "h": (245, 205, 170), "e": (25, 25, 30), "E": (25, 25, 30),
                  "g": (25, 25, 30), "R": (110, 20, 20), "C": (58, 20, 24),
                  "w": (222, 222, 232), "l": (25, 22, 24), "k": (20, 18, 19)}

CLASS_GRIDS = {"wizard": (_WIZARD, _WIZARD_PAL), "archer": (_ARCHER, _ARCHER_PAL),
               "warrior": (_WARRIOR, _WARRIOR_PAL), "priest": (_PRIEST, _PRIEST_PAL),
               "rogue": (_ROGUE, _ROGUE_PAL), "necromancer": (_NECROMANCER, _NECROMANCER_PAL),
               "paladin": (_PALADIN, _PALADIN_PAL), "assassin": (_ASSASSIN, _ASSASSIN_PAL)}

# ---------------------------------------------------------------- enemies --
# Front-facing (not helicopter top-down) so each silhouette reads clearly,
# matching the same convention used for the player classes above.

_BAT = [
    ".M            M.",
    "MMM          MMM",
    " MMM        MMM ",
    " .MMD      DMM. ",
    "  DDMD    DMDD  ",
    "  .DDMDDDDMDD.  ",
    "   DDMBBBBMDD   ",
    "   .DBBhehBD.   ",
    "    DBhEBEhBD   ",
    "    DBBBffBBD   ",
    "    .BBBBBB.    ",
    "     BB  BB     ",
    "     .C  C.     ",
    "    .  .  .  .  ",
]
_BAT_PAL = {"M": (46, 28, 66), "D": (78, 48, 112), "B": (44, 38, 50),
            "h": (60, 52, 66), "e": (18, 16, 20), "E": (235, 30, 30),
            "f": (238, 238, 238), "C": (30, 26, 32)}

_GHOST = [
    "   .GGGGGGGG.   ",
    "  GGWWWWWWWWGG  ",
    " GGWWWWWWWWWWGG ",
    " GWWWWWWWWWWWWG ",
    "GWWWWWWWWWWWWWWG",
    "GWWWeeWWWWeeWWWG",
    "GWWWeeWWWWeeWWWG",
    "GWWWWWWuuWWWWWWG",
    "GWWWWWWWWWWWWWWG",
    "GWWWWWWWWWWWWWWG",
    "GWWWWWWWWWWWWWWG",
    " GWWWWWWWWWWWWG ",
    " GG.GG.GG.GG.GG ",
    "  G. G. G. G.G  ",
    "   .  .   . .   ",
]
_GHOST_PAL = {"G": (170, 205, 235), "W": (222, 238, 252), "e": (30, 34, 56), "u": (110, 130, 165)}

_SKELETON = [
    "   .wwwwwwww.   ",
    "  wwwwwwwwwwww  ",
    "  wweEwwwwEeww  ",
    "  wwwwwjjwwwww  ",
    "   w.wwwwww.w   ",
    "   wWzzWzzWWw z ",
    "  wWWzzWzzWWWw z",
    "  wWWzzWzzWWWwqz",
    "   wWzzWzzWWw qz",
    "    ww    ww  q ",
    "    w  ww  w    ",
    "   Ww  ww  wW   ",
    "   ww      ww   ",
    "  WwW      WwW  ",
]
_SKELETON_PAL = {"w": (222, 219, 200), "W": (245, 242, 226), "e": (25, 25, 28), "E": (25, 25, 28),
                  "j": (60, 54, 46), "z": (96, 88, 76), "q": (128, 120, 104)}

_IMP = [
    "h            h  ",
    " h          h   ",
    "  h        h    ",
    "   dddddddd     ",
    "  dddddddddd    ",
    "  ddEEddEEdd    ",
    "  ddddnnddd t   ",
    "   ddRRRRdd t   ",
    "   dddddddd  t  ",
    "  .ddd  ddd. t  ",
    "  .dd    dd.    ",
    "     f          ",
    "    fff         ",
]
_IMP_PAL = {"h": (55, 12, 12), "d": (188, 40, 40), "E": (250, 225, 70),
            "n": (110, 20, 20), "R": (70, 8, 8), "t": (150, 25, 25), "f": (60, 55, 60)}

_GOBLIN = [
    ".g            g.",
    " gg          gg ",
    " .gggggggggggg. ",
    " gghhhhhhhhhhgg ",
    " ghhEhh  hhEhhg ",
    " ghhhh    hhhhg ",
    " ghh  rrrr  hhg ",
    "  .gggggggggg.  ",
    "   dCCCCCCCCd   ",
    "   dCCCCCCCCd   ",
    "   .CddddddC.   ",
    "   dCdCCCCdCd   ",
    "   .dd    dd.   ",
    "   .kk    kk.   ",
]
_GOBLIN_PAL = {"g": (76, 126, 58), "h": (118, 162, 96), "E": (225, 45, 35), "r": (150, 35, 35),
               "d": (94, 74, 46), "C": (60, 48, 30), "k": (32, 27, 21)}

_SCORPION = [
    "  t              ",
    " t.t             ",
    "t    .CCCCCC.    ",
    "cc   CCCCCCCC    ",
    "cCc  CCCEEECC   c",
    "cCc  CCCCCCCC  cc",
    " c    CCCCCCCcc  ",
    "      cCCCCc     ",
    "       cc  cc    ",
    "       cc  cc    ",
    "      ccc  ccc   ",
]
_SCORPION_PAL = {"c": (196, 150, 70), "C": (222, 178, 96), "E": (255, 60, 40), "t": (150, 100, 45),
                  "p": (110, 70, 30)}

_YETI = [
    "  .wwwwwwwwss.  ",
    " wwwwwwwwwwwwss ",
    "wwwwwwwwwwwwwsss",
    "wwwEwwwwwwwwEwss",
    "wwwwwww tt wwsss",
    "wwwwwCCCCCCwwsss",
    " wwCCCCCCCCCCww ",
    " wCCuuCCCCuuCCw ",
    "  CCuuCCCCuuCC  ",
    "   CC      CC   ",
    "   CC      CC   ",
    "   ff      ff   ",
]
_YETI_PAL = {"w": (232, 236, 240), "E": (40, 40, 45), "t": (235, 235, 225), "C": (200, 208, 214),
             "u": (150, 165, 175), "f": (235, 235, 225), "s": (200, 210, 220)}

_TROLL = [
    "  .oooooooo.    ",
    " ooooooooooo    ",
    "ooohhhhhhhooo   ",
    "ooEhh  hhEooo   ",
    "oohh tt hhooo   ",
    " oo  vv  oo     ",
    " ooCCCCCCoo     ",
    "ooCCCCCCCCoo    ",
    "ooCCCCCCCCoo  o ",
    " oCCCCCCCCo  oo ",
    "  CC    CC   o  ",
    "  CC    CC      ",
]
_TROLL_PAL = {"o": (88, 108, 74), "h": (110, 132, 92), "E": (235, 210, 40), "t": (225, 220, 200),
              "v": (60, 40, 30), "C": (70, 84, 58)}

_HARPY = [
    ".f            f.",
    " ff    hh    ff ",
    "  ff  hEEh  ff  ",
    "   ffhhhhhhff   ",
    "    fhhhhhhf    ",
    "    .ffffff.    ",
    "   .fyyyyyyf.   ",
    "   ffyyyyyyff   ",
    "   .fyffffyf.   ",
    "    ff    ff    ",
    "    kk    kk    ",
]
_HARPY_PAL = {"f": (168, 172, 182), "h": (222, 202, 176), "E": (235, 210, 40),
              "y": (200, 176, 90), "k": (150, 90, 40)}

_SALAMANDER = [
    ".d            d.",
    " dd          dd ",
    "  ddd        d  ",
    "   dddddddd     ",
    "  ddDDDDDDdd    ",
    "  dDEE dd EEDd  ",
    "  dDDDddddDDd t ",
    "   dDDoooDDd tt ",
    "   .dDDDDDd. t  ",
    "    dd    dd    ",
    "    dd    dd    ",
]
_SALAMANDER_PAL = {"d": (150, 46, 30), "D": (192, 68, 38), "E": (255, 220, 60),
                    "o": (255, 130, 40), "t": (110, 30, 20)}

_PANTHER = [
    ".d            d.",
    " dd          dd ",
    "  ddd      ddd  ",
    "   dDDDDDDDDd   ",
    "  dDEEddddEEDd  ",
    "  dDDdd  ddDDd  ",
    "  dDDDDddDDDDd  ",
    "   dDDDDDDDDd   ",
    "    dd    dd    ",
    "    dd    dd    ",
    "   ff      ff   ",
]
_PANTHER_PAL = {"d": (18, 40, 22), "D": (30, 62, 34), "E": (230, 210, 40), "f": (40, 50, 34)}

_GHOUL = [
    "  .oooooooo.    ",
    " oooooooooooo   ",
    "oohhhhhhhhhooo  ",
    "ooEhh    hEooo  ",
    "ooh  tttt  hoo  ",
    " oo  vvvv  oo   ",
    " ooCCCCCCCCoo   ",
    "ooCCCCCCCCCCoo  ",
    " oCCddddddCCo   ",
    "  Cdd    ddC    ",
    "  Cd      dC    ",
]
_GHOUL_PAL = {"o": (96, 92, 70), "h": (120, 116, 94), "E": (200, 40, 40), "t": (230, 225, 210),
              "v": (60, 50, 30), "C": (78, 74, 56), "d": (58, 54, 40)}

_FROST_WRAITH = [
    "   .WWWWWWWW.   ",
    "  WWCCCCCCCCWW  ",
    " WWCCCCCCCCCCWW ",
    " WCCCeeCCeeCCCW ",
    "WCCCCCCCCCCCCCCW",
    "WCCC  CCCC  CCCW",
    " WCCCCCCCCCCCW  ",
    "  WCC.CCCC.CCW  ",
    "   W.  CC  .W   ",
    "    .  CC  .    ",
    "       CC       ",
]
_FROST_WRAITH_PAL = {"W": (170, 220, 245), "C": (210, 240, 255), "e": (40, 60, 90)}

_CAVE_LURKER = [
    ".p            p.",
    " pp          pp ",
    "  ppPPPPPPPPpp  ",
    "  pPEEppppEEPp  ",
    "  pPppp  ppPp   ",
    "   pPPPPPPPp    ",
    "   pPCCCCCPp    ",
    "    PCCCCCP     ",
    "    .P   P.     ",
    "    .p   p.     ",
]
_CAVE_LURKER_PAL = {"p": (58, 48, 78), "P": (88, 74, 116), "E": (200, 100, 255), "C": (68, 58, 92)}

# --- Quadruped body-plan archetype (Batch 13, track Q3): a shared body+legs
# "chassis" (two stances - 4-legged and 6-legged/crawler) reused across all 5
# targets below, each given its own distinguishing head-topper feature
# (antlers/ears/frill/shell-spikes) and palette - the "small archetype
# library, varied by params" approach the pixel-art research recommended,
# instead of 5 fully bespoke hand-authored grids. Replaces the old reused-
# shape placeholders (deer was a recolored yeti, etc.) with real distinct
# silhouettes.
_QUAD_BODY_LEGS_4 = [
    " bbbbbbbbbbbb ",
    "bbbBeBBBBeBbbb",
    "bbbBBBBBBBBbbb",
    " bbbbbbbbbbbb ",
    "   l      l   ",
    "   l      l   ",
    "   k      k   ",
]
_QUAD_BODY_LEGS_6 = [
    " bbbbbbbbbbbb ",
    "bbbBeBBBBeBbbb",
    "bbbBBBBBBBBbbb",
    " bbbbbbbbbbbb ",
    "l  l      l  l",
    "k  k      k  k",
]
_LIZARD_BODY_LEGS = [
    "bbbBeBBBBeBbbb",
    "bbbBBBBBBBBbbb",
    " bbbbbbbbbbbb ",
    "  l  tt   l   ",
    "  k  tt   k   ",
]

_DEER = [
    "  a        a  ",
    "   a      a   ",
    "    a.  .a    ",
    "  bbbbbbbbbb  ",
] + _QUAD_BODY_LEGS_4 + ["      tt      "]

_FOREST_HARE = [
    "  r        r  ",
    "  r        r  ",
    "  r        r  ",
    "  bbbbbbbbbb  ",
] + _QUAD_BODY_LEGS_4 + ["      tt      "]

_DESERT_LIZARD = [
    "  g        g  ",
    " ggbbbbbbbbgg ",
] + _LIZARD_BODY_LEGS

_RUBBLE_CRAWLER = [
    "  bb      bb  ",
    " bbbbbbbbbbbb ",
] + _QUAD_BODY_LEGS_4

_BRINE_CRAWLER = [
    " s          s ",
    "s bbbbbbbbbb s",
] + _QUAD_BODY_LEGS_6

_BOSS = [
    "..OOOOOOOOOOOOOO..",
    ".OOKKKKKKKKKKKKOO.",
    "OOKKoooooooooKKOO",
    "OKKoo.OOOOOO.ooKKO",
    "OKoo.OKKKKKKO.ooKO",
    "OKoOKKEE99EEKKOoKO",
    "OKoOKE9oo99o9EKOoKO",
    "OKoOK9orrrro9KOoKO",
    "OKoOKE9oo99o9EKOoKO",
    "OKoOKKEE99EEKKOoKO",
    "OKoo.OKKKKKKO.ooKO",
    "OKKoo.OOOOOO.ooKKO",
    "OOKKoooooooooKKOO",
    ".OOKKKKKKKKKKKKOO.",
]
_BOSS_PAL = {"O": (255, 158, 20), "K": (58, 16, 78), "o": (110, 40, 148),
             "E": (255, 250, 235), "9": (255, 70, 40), "r": (255, 210, 90)}

# three more boss variants reusing the same silhouette with an original palette/name
# each - "rehauling" the dungeon boss into a real roster instead of one reskin
_FROST_MONARCH_PAL = {"O": (210, 235, 250), "K": (30, 60, 95), "o": (90, 150, 200),
                       "E": (255, 255, 255), "9": (140, 210, 255), "r": (220, 245, 255)}
_ASH_BEHEMOTH_PAL = {"O": (90, 40, 30), "K": (30, 10, 10), "o": (150, 50, 20),
                      "E": (255, 220, 150), "9": (255, 120, 30), "r": (255, 60, 20)}
_VOID_REAPER_PAL = {"O": (60, 20, 90), "K": (10, 8, 20), "o": (110, 30, 160),
                     "E": (170, 255, 190), "9": (40, 220, 120), "r": (200, 255, 210)}
_THORN_WARDEN_PAL = {"O": (40, 80, 30), "K": (20, 35, 15), "o": (70, 130, 45),
                      "E": (210, 180, 60), "9": (150, 220, 80), "r": (90, 60, 30)}
_SAND_WYRM_PAL = {"O": (180, 150, 90), "K": (90, 65, 30), "o": (215, 190, 130),
                   "E": (255, 240, 200), "9": (230, 130, 40), "r": (140, 100, 55)}


def _phase2_pal(pal):
    """Darker + red-shifted - a real (if simple) "more scary and mean" retint
    distinct from the base boss's own palette, for the reserved-pocket second-
    phase boss (see realm_sim's boss-death choreography). Placeholder until
    the visual session paints bespoke phase-2 art per boss kind."""
    out = {}
    for k, (r, g, b) in pal.items():
        out[k] = (min(255, int(r * 0.55 + 70)), int(g * 0.35), int(b * 0.35))
    return out


_BOSS_PHASE2_PAL = _phase2_pal(_BOSS_PAL)
_FROST_MONARCH_PHASE2_PAL = _phase2_pal(_FROST_MONARCH_PAL)
_ASH_BEHEMOTH_PHASE2_PAL = _phase2_pal(_ASH_BEHEMOTH_PAL)
_VOID_REAPER_PHASE2_PAL = _phase2_pal(_VOID_REAPER_PAL)
_THORN_WARDEN_PHASE2_PAL = _phase2_pal(_THORN_WARDEN_PAL)
_SAND_WYRM_PHASE2_PAL = _phase2_pal(_SAND_WYRM_PAL)
# story finale boss (see realm_sim's "forge" theme) - pale gold + white-hot eyes on
# the shared boss silhouette; phase 2 gets the same darker/redder retint as the others
_MAD_GOD_PAL = {"O": (235, 200, 90), "K": (40, 20, 10), "o": (250, 235, 170),
                "E": (255, 255, 255), "9": (255, 90, 40), "r": (255, 245, 210)}
_MAD_GOD_PHASE2_PAL = _phase2_pal(_MAD_GOD_PAL)

# a second signature mob per biome - same cheap-but-effective trick as the boss
# palette variants: reuse an existing grid, just retint it, so ten more mobs
# (see entities.ENEMY_KINDS) cost ten palettes instead of ten hand-drawn grids
_THORNLING_PAL = {"g": (40, 70, 30), "h": (70, 110, 50), "E": (170, 60, 200), "r": (110, 30, 130),
                  "d": (60, 45, 25), "C": (35, 28, 15), "k": (20, 16, 10)}
_DUNE_STALKER_PAL = {"c": (225, 210, 170), "C": (245, 235, 205), "E": (255, 210, 60), "t": (190, 160, 110),
                      "p": (150, 120, 70)}
_FROST_SPRITE_PAL = {"G": (150, 220, 245), "W": (220, 245, 255), "e": (20, 60, 90), "u": (90, 170, 210)}
_BOG_CRAWLER_PAL = {"o": (55, 70, 45), "h": (75, 95, 60), "E": (140, 200, 60), "t": (150, 160, 120),
                     "v": (30, 25, 15), "C": (40, 55, 35)}
_CLIFF_STRIDER_PAL = {"f": (130, 128, 120), "h": (170, 165, 150), "E": (255, 240, 180), "y": (110, 105, 95),
                       "k": (80, 75, 65)}
_CINDER_WISP_PAL = {"d": (60, 40, 35), "D": (110, 60, 45), "E": (255, 240, 120), "o": (255, 160, 50), "t": (30, 20, 15)}
_VINE_SERPENT_PAL = {"d": (30, 60, 20), "D": (60, 110, 30), "E": (255, 230, 80), "f": (45, 70, 25)}
_HUSK_WANDERER_PAL = {"o": (110, 100, 80), "h": (140, 128, 100), "E": (90, 200, 90), "t": (200, 190, 160),
                       "v": (50, 45, 30), "C": (85, 78, 60), "d": (60, 55, 42)}
_GLACIER_SHARD_PAL = {"W": (90, 150, 220), "C": (140, 200, 250), "e": (10, 30, 70)}
# a carved stone idol - rounded head with glowing rune-eyes, wooden binding bands
# down a tapering body, and a wide dark stone base, distinct from every mobile
# humanoid mob silhouette (was a reused _TROLL-shape placeholder before this)
_TOTEM = [
    "     oooooo     ",
    "    ohhhhhho    ",
    "    ohEvvEho    ",
    "    oohvvhoo    ",
    "     oottoo     ",
    "      nnnn      ",
    "     wwwwww     ",
    "    oooggooo    ",
    "    oooooooo    ",
    "    wwwwwwww    ",
    "   ooooggoooo   ",
    "   oooooooooo   ",
    "  CCCCCCCCCCCC  ",
    "  CCCCCCCCCCCC  ",
]
_TOTEM_PAL = {"o": (120, 112, 98), "h": (160, 150, 130), "E": (235, 205, 70), "v": (46, 39, 31),
              "t": (150, 140, 120), "n": (70, 60, 48), "w": (96, 66, 38), "g": (150, 220, 130),
              "C": (84, 78, 68)}
_DEEP_STALKER_PAL = {"p": (25, 20, 35), "P": (45, 38, 60), "E": (255, 60, 180), "C": (30, 26, 42)}

# Batch 13 Track Q2: bespoke silhouettes for 5 "aerial/voice" mobs that were
# previously reusing an unrelated grid (a bat/ghost/harpy/frost-wraith shape)
# with just a new palette - the same _TOTEM-style upgrade above, applied to a
# small perching-bird archetype (songbird/marsh_heron, sharing the b/B/h/k/l
# key convention below, varied by proportion - plump+short vs. tall+long-necked)
# and a robed ethereal-singer archetype (siren_wraith/abyssal_chorister/
# choir_warden, sharing the h/H/e/G/r key convention - hood/inner-robe/eye/
# glowing "song" rune/tapering robe-tendril - varied by posture and hood shape).
_SONGBIRD = [
    "    .bbbb.      ",
    "   bbbbbbbb     ",
    "  bbbcccbbbk    ",
    "  bbcccceccbk   ",
    "  bbcccccbbb    ",
    " tbbbbbbbbbb    ",
    " ttbbbbbbbbb    ",
    "  ttbbbbbbb     ",
    "    kk  kk      ",
    "    kk  kk      ",
    "     .    .     ",
]
_MARSH_HERON = [
    "           h    ",
    "          hk    ",
    "         h      ",
    "        n       ",
    "       n        ",
    "      nb        ",
    "     nbB        ",
    "    nbBB        ",
    "    bBBb        ",
    "     bbb        ",
    "     ll  l      ",
    "     ll  l      ",
    "     ll  l      ",
    "      l   l     ",
]
_SIREN_WRAITH = [
    "    .hhhhh.     ",
    "   hhhhhhhhh    ",
    "  hhhhhhhhhhh   ",
    "  hHHHHHHHHHh   ",
    "  hH  eyye  Hh  ",
    "  hHH  GG  HHh  ",
    " ahHHHHHHHHHha  ",
    " a hHHHHHHh  a  ",
    "    HHHHHH      ",
    "    rrrrrr      ",
    "   rrrrrrrr     ",
    "   rr    rr     ",
    "   r      r     ",
]
_ABYSSAL_CHORISTER = [
    "     .hhhh.     ",
    "    hhhhhhhh    ",
    "   hhHHHHHHhh   ",
    "   hH  ee  Hh   ",
    "   hH      Hh   ",
    "   hHH GGG HHh  ",
    "    hHHHHHHh    ",
    "    .hhhhhh.    ",
    "     rrrrrr     ",
    "     rrrrrr     ",
    "      rrrr      ",
    "       rr       ",
]
_CHOIR_WARDEN = [
    "      hhhh   s  ",
    "     hhhhhh  s  ",
    "    hhHHHHhh s  ",
    "    hH eeee Hh  ",
    "    hHHHHHHHHh  ",
    "   hHH GGGG HHh ",
    "   hHHHHHHHHHHh ",
    "    hhhhhhhhhh  ",
    "     rrr  rrr   ",
    "     rrr  rrr   ",
    "     rr    rr   ",
    "      r    r    ",
]

# Neutral-mob palettes (reuse existing grids below - tint-reuse stopgap per the usual
# convention, real bespoke sprites are the visual session's to pick up whenever)
_FOREST_HARE_PAL = {"r": (200, 190, 175), "b": (185, 170, 150), "B": (225, 215, 200),
                     "e": (30, 25, 20), "l": (150, 140, 122), "k": (90, 80, 68),
                     "t": (245, 240, 230)}
_CAVE_MOTH_PAL = {"G": (200, 190, 230), "W": (240, 235, 250), "e": (140, 60, 180), "u": (170, 150, 210)}
_SONGBIRD_PAL = {"b": (200, 70, 50), "c": (230, 140, 90), "e": (20, 16, 12),
                  "k": (90, 60, 30), "t": (150, 40, 40)}
_DEER_PAL = {"a": (90, 60, 40), "b": (150, 110, 70), "B": (195, 150, 105), "e": (25, 20, 15),
             "l": (110, 80, 50), "k": (60, 45, 30), "t": (230, 225, 210)}
_DESERT_LIZARD_PAL = {"g": (130, 150, 60), "b": (170, 190, 100), "B": (205, 220, 140),
                       "e": (40, 35, 15), "l": (140, 160, 80), "k": (90, 100, 50),
                       "t": (150, 170, 85)}
_MARSH_HERON_PAL = {"h": (150, 165, 160), "n": (170, 185, 180), "b": (200, 205, 195),
                     "B": (225, 230, 220), "k": (90, 70, 40), "l": (100, 115, 108)}

# --- Batch 15 friendly creatures (talkable NPC herds + extra ambient wildlife) -
# same shared-chassis approach as the Q3 quadrupeds above: a distinct head/topper
# (or a fully bespoke small grid for the upright ones) over _QUAD_BODY_LEGS_4/6 or
# _LIZARD_BODY_LEGS, each with its own original palette.
_ELK = [
    "a a a    a a a",
    " aaa      aaa ",
    "  a  a  a  a  ",
    "   aa.  .aa   ",
    "  bbbbbbbbbb  ",
] + _QUAD_BODY_LEGS_4 + ["      tt      "]
_ELK_PAL = {"a": (215, 195, 150), "b": (105, 70, 45), "B": (140, 95, 60), "e": (20, 15, 10),
            "l": (80, 55, 35), "k": (45, 30, 20), "t": (235, 225, 205)}
_MOUNTAIN_GOAT = [
    "  hh      hh  ",
    " h  h    h  h ",
    "  hh      hh  ",
    "  bbbbbbbbbb  ",
] + _QUAD_BODY_LEGS_4 + ["     tttt     "]
_MOUNTAIN_GOAT_PAL = {"h": (120, 110, 95), "b": (200, 198, 190), "B": (228, 226, 220), "e": (30, 30, 35),
                      "l": (150, 148, 140), "k": (70, 68, 64), "t": (240, 240, 236)}
_SNOW_FOX = [
    "  r        r  ",
    " rrr      rrr ",
    "  bbbbbbbbbb  ",
] + _QUAD_BODY_LEGS_4 + ["  tttttt      ", " tt           "]
_SNOW_FOX_PAL = {"r": (240, 170, 110), "b": (235, 238, 242), "B": (250, 252, 255), "e": (25, 30, 45),
                 "l": (205, 210, 220), "k": (140, 145, 160), "t": (250, 250, 252)}
_SCRAP_RAT = [
    " rr        rr ",
    " rr        rr ",
    "  bbbbbbbbbb  ",
] + _QUAD_BODY_LEGS_6 + ["tttt          "]
_SCRAP_RAT_PAL = {"r": (170, 120, 110), "b": (120, 112, 104), "B": (150, 142, 132), "e": (200, 60, 40),
                  "l": (95, 88, 80), "k": (60, 55, 50), "t": (175, 125, 115)}
_TORTOISE = [
    "    ssssss    ",
    "  ssSSssSSss  ",
    " sSSssSSssSSs ",
    " ssssssssssss ",
] + _LIZARD_BODY_LEGS
_TORTOISE_PAL = {"s": (110, 90, 50), "S": (150, 125, 70), "b": (120, 150, 85), "B": (150, 180, 110),
                 "e": (25, 20, 10), "l": (100, 130, 70), "k": (70, 90, 45), "t": (120, 150, 85)}
_TREE_FROG = [
    " ee        ee ",
    "eWWe      eWWe",
    " eebbbbbbbbee ",
] + _LIZARD_BODY_LEGS
_TREE_FROG_PAL = {"e": (240, 130, 30), "W": (25, 20, 15), "b": (60, 190, 80), "B": (120, 230, 120),
                  "l": (240, 130, 30), "k": (200, 90, 20), "t": (60, 190, 80)}
_FIRE_BEETLE = [
    "      hh      ",
    "     h  h     ",
    "  ssssssssss  ",
    " sSSSSssSSSSs ",
] + _QUAD_BODY_LEGS_6
_FIRE_BEETLE_PAL = {"h": (255, 200, 90), "s": (150, 30, 20), "S": (230, 70, 30), "b": (60, 25, 20),
                    "B": (110, 40, 25), "e": (255, 220, 120), "l": (50, 20, 15), "k": (30, 12, 10)}
_FLAMINGO = [
    "      pppk      ",
    "     p   pk     ",
    "     p          ",
    "      p         ",
    "       p        ",
    "      pPPP      ",
    "     pPPPPPP    ",
    "     pPPPPPPp   ",
    "      pPPPPp    ",
    "        ll      ",
    "        l       ",
    "        l       ",
    "        l       ",
    "        k       ",
]
_FLAMINGO_PAL = {"p": (240, 120, 150), "P": (255, 160, 185), "k": (40, 30, 30), "l": (230, 110, 130)}
_ICE_PENGUIN = [
    "     kkkk     ",
    "    kkkkkk    ",
    "   kkwekwek   ",
    "   kkwwoowk   ",
    "  kkwwwwwwkk  ",
    "  kkwwwwwwkk  ",
    "  kkwwwwwwkk  ",
    "   kkwwwwkk   ",
    "    oo  oo    ",
]
_ICE_PENGUIN_PAL = {"k": (30, 34, 48), "w": (240, 244, 250), "e": (10, 10, 12), "o": (250, 160, 40)}
_MUSHROOM_FOLK = [
    "    rrrrrr    ",
    "  rrwrrrrwrr  ",
    " rrrrrwwrrrrr ",
    " rwrrrrrrrrwr ",
    "   cccccccc   ",
    "    ffffff    ",
    "    fekkef    ",
    "    ffffff    ",
    "    ffffff    ",
    "    ff  ff    ",
]
_MUSHROOM_FOLK_PAL = {"r": (200, 50, 50), "w": (250, 245, 235), "c": (225, 205, 175), "f": (238, 225, 200),
                      "e": (30, 25, 20), "k": (140, 90, 80)}

# "The Reforging" storyline - island flare/song guardian palettes (see
# entities.ENEMY_KINDS). Each reuses an existing base grid with a new
# palette, the established minor-mob convention - shard pool in a warm
# ember/charged-rubble scheme, choir pool in a cool teal/coral/pearl scheme.
_EMBER_WISP_PAL = {"G": (200, 90, 40), "W": (255, 170, 80), "e": (60, 20, 10), "u": (150, 60, 20)}
_FURY_SHARD_PAL = {"M": (60, 40, 30), "D": (180, 70, 30), "B": (40, 30, 25), "h": (90, 60, 45),
                    "e": (20, 10, 8), "E": (255, 120, 40), "f": (255, 220, 150), "C": (35, 25, 20)}
_RUBBLE_CRAWLER_PAL = {"b": (120, 105, 90), "B": (160, 145, 125), "e": (255, 100, 40),
                        "l": (95, 82, 70), "k": (60, 52, 45)}
_SPITE_SPIRIT_PAL = {"G": (140, 40, 40), "W": (220, 90, 70), "e": (40, 10, 10), "u": (100, 30, 30)}
# --- Q4 humanoid-guardian archetype (Batch 13): shared silhouette template -
# a peaked/plated head silhouette (rows 0-3), a torso block carrying one
# "regalia" accent distinct per mob - jagged shard spikes, a hollow ember
# visor, cracked stone plating, glowing crack-lines, or a flared acolyte
# hem/staff (rows 4-7), tapering to legs or a robe hem (rows 8+). Every
# instance below reuses this row skeleton but varies proportions/accent
# placement/which palette key goes where, per mob - not a copy-paste reskin.
_SHARD_SENTINEL = [
    "  .oo.    .oo.  ",
    " oohhoo  oohho  ",
    " ohhEhh  hEhho  ",
    "  ohh  tt  ho   ",
    " oCCCCCCCCCCCo  ",
    "oCCvCCCCCCCvCCo ",
    "oCCCCCCCCCCCCCo ",
    " oCC        CCo ",
    " oC          Co ",
    "  o          o  ",
]
_SHARD_SENTINEL_PAL = {"o": (95, 70, 55), "h": (135, 105, 80), "E": (255, 140, 40), "t": (230, 190, 120),
                        "v": (50, 35, 25), "C": (80, 60, 45)}
_ECHO_KNIGHT = [
    "   .dddddd.     ",
    "  ddCCCCCCdd    ",
    " ddCChhhhCCdd   ",
    " dCCEhh  hhECCd ",
    " dCh   tt   hCd ",
    "  Coo      ooC  ",
    "  CoCCCCCCCoC   ",
    " dCCCCCCCCCCCd  ",
    " dCC  CCCC  CCd ",
    "  Cv        vC  ",
    "  Cv        vC  ",
]
_ECHO_KNIGHT_PAL = {"o": (90, 60, 50), "h": (130, 90, 75), "E": (255, 110, 50), "t": (230, 150, 90),
                     "v": (45, 25, 20), "C": (70, 45, 38), "d": (55, 35, 28)}
_SHATTERED_GOLEM_PAL = {"w": (100, 85, 75), "E": (255, 120, 40), "t": (230, 160, 90), "C": (75, 62, 54),
                         "u": (55, 45, 38), "f": (100, 85, 75), "s": (85, 70, 60)}
_FRACTURE_HOUND_PAL = {"d": (55, 35, 28), "D": (95, 60, 45), "E": (255, 130, 40), "f": (40, 28, 22)}
_STONE_REVENANT = [
    "   PPPPPPPP     ",
    "  PPCCCCCCPP    ",
    " PPCCpEEpCCPP   ",
    " PCCCC  CCCCP   ",
    " PCCCCCCCCCCP   ",
    "PPCCCCCCCCCCPP  ",
    "PPCCCCCCCCCCPP  ",
    " PCC  CC  CCP   ",
    " PP        PP   ",
]
_STONE_REVENANT_PAL = {"p": (70, 55, 48), "P": (110, 88, 75), "E": (255, 140, 60), "C": (55, 42, 36)}
_CINDER_WARDEN = [
    "   .dddddd.     ",
    "  ddDDDDDDdd    ",
    " ddDoEE  EEoDd  ",
    " dDo   tt   oDd ",
    "  dDDDDDDDDDd   ",
    " dDDEDDddDDEDDd ",
    " dDDD  EE  DDDd ",
    "  dD        Dd  ",
    "  d          d  ",
]
_CINDER_WARDEN_PAL = {"d": (120, 35, 20), "D": (180, 60, 30), "E": (255, 220, 60), "o": (255, 140, 40),
                       "t": (80, 25, 15)}
_TIDE_WISP_PAL = {"G": (60, 140, 160), "W": (170, 230, 235), "e": (15, 40, 50), "u": (60, 110, 130)}
_PEARL_ACOLYTE = [
    "   .CCCCCC.     ",
    "  CChhhhhhCC    ",
    " CChEhh  hEhCC  ",
    " Chh   tt   hC  ",
    "  CCCCCCCCCC    ",
    " oCCCvvvvCCo d  ",
    " oCCCCCCCCCo d  ",
    "oCCC      CCCo d",
    "oCC        CCo  ",
    " C          C   ",
]
_PEARL_ACOLYTE_PAL = {"o": (70, 95, 100), "h": (110, 140, 145), "E": (230, 240, 250), "t": (220, 235, 240),
                       "v": (30, 50, 55), "C": (55, 78, 82), "d": (40, 60, 64)}
_BRINE_CRAWLER_PAL = {"s": (40, 130, 130), "b": (50, 140, 140), "B": (90, 180, 175),
                       "e": (255, 210, 90), "l": (35, 110, 108), "k": (20, 75, 72)}
_ABYSSAL_CHORISTER_PAL = {"h": (45, 90, 100), "H": (60, 110, 120), "e": (10, 20, 25),
                           "G": (120, 220, 230), "r": (20, 45, 55)}
_CORAL_SENTINEL_PAL = {"o": (200, 110, 110), "h": (230, 150, 150), "E": (255, 240, 200), "t": (235, 225, 210),
                        "v": (100, 55, 55), "C": (170, 90, 90)}
_DROWNED_CUSTODIAN_PAL = {"p": (40, 70, 80), "P": (70, 110, 120), "E": (150, 230, 235), "C": (30, 55, 62)}
_KELP_STALKER_PAL = {"d": (20, 55, 45), "D": (35, 95, 75), "E": (150, 230, 120), "f": (15, 40, 32)}
_SHELLBACK_GUARDIAN_PAL = {"w": (90, 130, 140), "E": (255, 220, 150), "t": (230, 235, 235), "C": (70, 100, 110),
                            "u": (50, 75, 82), "f": (90, 130, 140), "s": (75, 110, 118)}
_SIREN_WRAITH_PAL = {"h": (90, 140, 150), "H": (200, 220, 220), "e": (30, 40, 45),
                      "y": (150, 200, 190), "G": (255, 230, 180), "a": (170, 205, 205),
                      "r": (60, 95, 100)}
_CHOIR_WARDEN_PAL = {"h": (140, 200, 210), "H": (200, 235, 240), "e": (30, 55, 65),
                      "G": (230, 250, 255), "r": (90, 150, 160), "s": (210, 235, 240)}

# --- Batch 13 Track Q1: ethereal/wisp-flyer archetype generators ---
# Per this session's pixel-art research: a small parametrized body-plan
# archetype library, varied by proportion/params, is more efficient than
# fully bespoke hand-typed grids per mob while still giving each mob its
# own genuinely distinct silhouette (not another palette-swapped _GHOST/
# _BAT reuse). These generate real ASCII pixel-grids programmatically.


def _wisp_grid(chars, width=17, height=14, core_rx=5.3, core_ry=4.6, tail_rows=5, eyes=True):
    """A small rounded ethereal floating creature: a glowing radial core
    plus a tapering wispy tail. `chars` maps role name -> grid char (rim/
    core/eye/shadow), matching whichever palette dict the mob already has,
    so this one generator produces genuinely different silhouettes for
    ember_wisp/spite_spirit/tide_wisp purely from its numeric params."""
    rim, core, eye = chars["rim"], chars["core"], chars["eye"]
    cx = (width - 1) / 2.0
    core_h = height - tail_rows
    cy = core_h * 0.46
    rows = []
    for y in range(core_h):
        row = [" "] * width
        for x in range(width):
            dx = (x - cx) / core_rx
            dy = (y - cy) / core_ry
            dist = math.hypot(dx, dy)
            if dist <= 0.5:
                row[x] = core
            elif dist <= 0.92:
                row[x] = rim if (x - y) % 3 else core
            elif dist <= 1.08:
                row[x] = rim
        rows.append("".join(row))
    for t in range(tail_rows):
        row = [" "] * width
        frac = 1.0 - t / max(1, tail_rows - 1)
        span = max(0.6, core_rx * 0.85 * frac)
        for x in range(width):
            dx = x - cx
            if abs(dx) <= span and (int(round(dx)) + t) % 3 != 2:
                row[x] = core if t < 2 else rim
        rows.append("".join(row))
    if eyes:
        ey = int(round(cy))
        offset = max(1, int(round(core_rx * 0.4)))
        for ex in (int(round(cx - offset)), int(round(cx + offset))):
            if 0 <= ey < len(rows) and 0 <= ex < width:
                r = list(rows[ey])
                r[ex] = eye
                rows[ey] = "".join(r)
    return rows


def _shard_grid(chars, width=15, height=15, elongation=1.0):
    """A small angular floating crystal-shard creature: a diamond/prism
    silhouette built from straight faceted edges, deliberately unlike
    `_wisp_grid`'s soft rounded blob - so `fury_shard` reads as an actual
    shard instead of yet another ghost-shaped recolor."""
    outer, mid, body, hi, eye = chars["outer"], chars["mid"], chars["body"], chars["hi"], chars["eye"]
    cx = (width - 1) / 2.0
    top, bottom = 1, height - 2
    mid_y = (top + bottom) / 2.0
    rows = []
    for y in range(height):
        row = [" "] * width
        if top <= y <= bottom:
            frac = ((y - top) / max(1.0, mid_y - top)) if y <= mid_y else \
                   ((bottom - y) / max(1.0, bottom - mid_y) * elongation)
            half = frac * (width / 2.0 - 1)
            for x in range(width):
                dx = abs(x - cx)
                if dx <= half:
                    if dx <= half * 0.35:
                        row[x] = hi if y < mid_y else body
                    elif dx <= half * 0.75:
                        row[x] = mid
                    else:
                        row[x] = outer
        rows.append("".join(row))
    ey = int(round(mid_y - 1))
    for ex in (int(round(cx - 2)), int(round(cx + 2))):
        if 0 <= ey < len(rows) and 0 <= ex < width:
            r = list(rows[ey])
            r[ex] = eye
            rows[ey] = "".join(r)
    return rows


def _moth_grid(chars, width=17, height=12, wing_rx=7.0, wing_ry=3.6):
    """A small winged night-moth: two horizontal wing lobes either side of
    a thin vertical body - a fundamentally different (wing-shaped, wide/
    flat) silhouette from the rounded-blob wisp archetype, since a moth
    forcing itself into a wisp shape would read as arbitrary, not designed."""
    rim, core, eye, shadow = chars["rim"], chars["core"], chars["eye"], chars["shadow"]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    rows = []
    for y in range(height):
        row = [" "] * width
        for x in range(width):
            if abs(x - cx) <= 1:
                row[x] = shadow
                continue
            for side in (-1, 1):
                wx = cx + side * (wing_rx * 0.55)
                dist = math.hypot((x - wx) / wing_rx, (y - cy) / wing_ry)
                if dist <= 0.55:
                    row[x] = core
                    break
                elif dist <= 1.0:
                    row[x] = rim
                    break
        rows.append("".join(row))
    ey = int(round(cy))
    ex = int(round(cx))
    if 0 <= ey < len(rows) and 0 <= ex < width:
        r = list(rows[ey])
        r[ex] = eye
        rows[ey] = "".join(r)
    return rows


# Four genuinely distinct silhouettes from the 3 generators above, one
# per target mob, each tuned via its own params (not a shared shape):
_EMBER_WISP_CHARS = {"rim": "G", "core": "W", "eye": "e"}
_EMBER_WISP = _wisp_grid(_EMBER_WISP_CHARS, core_rx=4.6, core_ry=4.0, tail_rows=6, eyes=True)

_SPITE_SPIRIT_CHARS = {"rim": "G", "core": "W", "eye": "e"}
_SPITE_SPIRIT = _wisp_grid(_SPITE_SPIRIT_CHARS, core_rx=3.6, core_ry=5.4, tail_rows=3, eyes=True)

_TIDE_WISP_CHARS = {"rim": "G", "core": "W", "eye": "e"}
_TIDE_WISP = _wisp_grid(_TIDE_WISP_CHARS, width=19, core_rx=6.4, core_ry=3.4, tail_rows=7, eyes=True)

_FURY_SHARD_CHARS = {"outer": "M", "mid": "D", "body": "B", "hi": "h", "eye": "e"}
_FURY_SHARD = _shard_grid(_FURY_SHARD_CHARS, elongation=1.6)

_CAVE_MOTH_CHARS = {"rim": "G", "core": "W", "eye": "e", "shadow": "u"}
_CAVE_MOTH = _moth_grid(_CAVE_MOTH_CHARS)

# --- Batch 13 Track Q5: real silhouettes for 6 "Reforging" guardians that
# previously just palette-swapped an unrelated existing base grid (a
# shattered_golem literally reused the yeti shape, etc.) - see the plan doc.
# Two shared, parametrized body-plan archetypes rather than 6 fully bespoke
# grids: a "blocky construct" archetype (chunky, symmetric, armored/crested)
# and a "low-slung creature" archetype (elongated, forward head, trailing
# tail/legs). Each archetype function assembles the common base/leg rows;
# every mob still supplies its own distinct crown/torso or head/spine rows,
# so the six stay genuinely different from each other and from the 14
# pre-existing base shapes, not just re-palettes.
def _construct_body(crown_rows, torso_rows, leg_char):
    return crown_rows + torso_rows + [
        f"    {leg_char}{leg_char}      {leg_char}{leg_char}    ",
        f"    {leg_char}{leg_char}      {leg_char}{leg_char}    ",
    ]


def _lowslung_body(head_rows, spine_rows, tail_char):
    return head_rows + spine_rows + [
        f"  {tail_char}{tail_char}  {tail_char}{tail_char}  {tail_char}{tail_char}  ",
    ]


_SHATTERED_GOLEM = _construct_body(
    crown_rows=[
        "   .wwwwwwwww.   ",
        "  wwwCwwEwwCwww  ",
        " wwCCwwwwwwwCCww ",
    ],
    torso_rows=[
        "wwwwwwssssswwwwww",
        "wwsssCtttttCsssww",
        " wsCCttttttCCsw  ",
        "  sCCC     CCCs  ",
        "   sCC     CCs   ",
    ],
    leg_char="f",
)

_CORAL_SENTINEL = _construct_body(
    crown_rows=[
        "   .ohhhhho.   ",
        "  ohhEohoEhho  ",
        " ohhCCCCCChho  ",
    ],
    torso_rows=[
        "ohhhtCtCtCthhho",
        " ohhCtttttChho ",
        "  ohCC   CCho  ",
    ],
    leg_char="v",
)

_SHELLBACK_GUARDIAN = _construct_body(
    crown_rows=[
        "   .wwwwwww.   ",
        "  wwwwEwEwww   ",
    ],
    torso_rows=[
        " wwCCCCCCCCww  ",
        "wwCttCtCtCttCww",
        "wwCCCsssssCCCww",
        " wCCC     CCCw ",
        "  wC       Cw  ",
    ],
    leg_char="f",
)

_FRACTURE_HOUND = _lowslung_body(
    head_rows=[
        ".d          d.",
        " ddEdd  ddEdd ",
    ],
    spine_rows=[
        "  dDDddddDDd  ",
        " dDfDfDfDfDd  ",
        " ddDDDDDDDDdd ",
    ],
    tail_char="d",
)

_DROWNED_CUSTODIAN = _lowslung_body(
    head_rows=[
        "   .pPPPp.   ",
        "  pPEppEPp   ",
    ],
    spine_rows=[
        " pPPCCCCPPp  ",
        "pPCC    CCPp ",
        " pPC    CPp  ",
    ],
    tail_char="p",
)

_KELP_STALKER = _lowslung_body(
    head_rows=[
        ".d           .",
        " ddEdd   ddEd ",
    ],
    spine_rows=[
        "  dDdDdDdDdD  ",
        "   dDfDfDfd   ",
        "    dDDDDd    ",
    ],
    tail_char="f",
)

# --- Batch 14 Track B1: island mini-bosses for the first 5 islands ---
# Bigger, more ornate variants of the existing shard/choir archetype row-
# skeletons (echo_knight/stone_revenant's humanoid frame, shattered_golem's
# _construct_body, fracture_hound's _lowslung_body) - not new archetypes,
# just scaled up with extra crown/regalia detail so each reads as a real
# boss silhouette rather than another same-size guardian. All registered
# into BOSS_KINDS below so they also get the boss sprite-scale treatment
# (BOSS_FINAL_SIZE instead of FINAL_SIZE).
_CINDER_COLOSSUS = _construct_body(
    crown_rows=[
        "     .wwwwwwwwwwww.     ",
        "    wwwCwEwwwwEwCwww    ",
        "   wwCCwwwwwwwwwwCCww   ",
        "  wwCC   wwwwww   CCww  ",
    ],
    torso_rows=[
        " wwwwwwwwssssswwwwwwww ",
        "wwwsssssCtttttCsssssww ",
        "wwsssCCttttttttCCsssw  ",
        " wsCCCtttEEttttCCCsw   ",
        "  sCCC   tt   CCCs     ",
        "   sCC         CCs     ",
    ],
    leg_char="f",
)
_CINDER_COLOSSUS_PAL = {"w": (150, 95, 60), "C": (110, 70, 45), "s": (85, 55, 38), "t": (60, 40, 28),
                         "E": (255, 200, 60), "f": (75, 50, 35)}

_RUBBLE_WARLORD = _lowslung_body(
    head_rows=[
        "  .dd            dd.   ",
        " ddDDEdd      ddEDDdd  ",
        "ddDDDDDdd    ddDDDDDdd ",
    ],
    spine_rows=[
        " dDDffDDffDDffDDffDDd  ",
        "dDDDDDDDDDDDDDDDDDDDDd ",
        " dDffDfDfDfDfDfDfDffDd ",
        "  ddDDDDDDDDDDDDDDdd   ",
    ],
    tail_char="d",
)
_RUBBLE_WARLORD_PAL = {"d": (60, 40, 30), "D": (105, 68, 48), "E": (255, 150, 40), "f": (40, 26, 20)}

_ASHREACH_REVENANT = [
    "     .ddCCCCCCCCdd.     ",
    "    ddCCCoooooCCCdd     ",
    "   ddCCohhEohhoECCdd    ",
    "  dCChh    tt    hhCCd  ",
    "   Coo              ooC ",
    "   CoCCCCCCCCCCCCCCoC   ",
    "  dCCCCCCCCCCCCCCCCCCd  ",
    "  dCC  CCCCCCCCCC  CCd  ",
    "   Cv  CC        CC  vC ",
    "   Cv              vC   ",
    "    v                v  ",
]
_ASHREACH_REVENANT_PAL = {"o": (100, 65, 55), "h": (150, 105, 85), "E": (255, 120, 45), "t": (230, 170, 100),
                           "v": (48, 28, 22), "C": (78, 50, 42), "d": (58, 38, 30)}

_CHOIR_SOVEREIGN = [
    "     .CCCCCCCCCC.       ",
    "    CChhhhhhhhhhCC      ",
    "   CChEhhh  hhhEhCC     ",
    "   Chh   GG   GGhhC     ",
    "    CCCCCCCCCCCCCC      ",
    "  oCCCCvvvvvvvvCCCCo    ",
    "  oCCCCCCCCCCCCCCCCo d  ",
    " oCCC            CCCo d ",
    " oCC              CCo   ",
    "  C  d          d  C    ",
    "  C  d          d  C    ",
]
_CHOIR_SOVEREIGN_PAL = {"o": (60, 90, 96), "h": (150, 195, 200), "E": (240, 250, 255), "G": (150, 230, 235),
                         "v": (28, 48, 52), "C": (78, 112, 118), "d": (45, 68, 72)}

_CORAL_LEVIATHAN = _construct_body(
    crown_rows=[
        "    .ohhhhhhhhho.    ",
        "   ohhEohohohoEhho   ",
        "  ohhCCCCCCCCCCChho  ",
        " ohCC             CCho",
    ],
    torso_rows=[
        "ohhhtCtCtCtCtCthhho ",
        " ohhCtttttttttChho  ",
        " ohCC   ss    CCho  ",
        "  ohCC       CCho   ",
    ],
    leg_char="v",
)
_CORAL_LEVIATHAN_PAL = {"o": (210, 120, 120), "h": (235, 160, 155), "E": (255, 245, 210), "t": (240, 230, 215),
                         "v": (105, 60, 60), "C": (180, 100, 100), "s": (150, 80, 80)}

# "The Reforging" island mini-bosses (Batch 14, islands 6-10 by name order:
# Tideglass Sanctum, Thornrock Shard, Driftbell Cloister, Ashenreach Shard,
# Abyssal Hymnal) - one genuinely tougher, uniquely-silhouetted boss per
# island, built from the same parametrized archetype generators Batch 13
# proved out (bigger dimensions + unique params than any existing guardian,
# so each reads as a real boss, not a recolored trash mob).
_THORNROCK_COLOSSUS = _construct_body(
    crown_rows=[
        "   .GttGttGttG.   ",
        "  GttEGttttGEttG  ",
        " GGttttttttttttGG ",
        "GGtttCCCCCCCCtttGG",
    ],
    torso_rows=[
        "wwwGGtttttttttGGwww",
        " wwGGtCCCCCCCtGGww ",
        "  wGGCCC   CCCGGw  ",
        "   GGC       CGG   ",
    ],
    leg_char="w",
)

_ASHENREACH_DEVOURER = _lowslung_body(
    head_rows=[
        ".DD            DD.",
        " DDdEdd    ddEdDD ",
        "  ddd DDDDDD ddd  ",
    ],
    spine_rows=[
        "   dDDdddddddDDd   ",
        "  dDEdEdEdEdEdEDd  ",
        "   ddDDDDDDDDDDd   ",
    ],
    tail_char="d",
)

_TIDEGLASS_WARDEN_CHARS = {"outer": "u", "mid": "G", "body": "W", "hi": "H", "eye": "e"}
_TIDEGLASS_WARDEN = _shard_grid(_TIDEGLASS_WARDEN_CHARS, width=21, height=21, elongation=1.4)

_DRIFTBELL_MATRIARCH_CHARS = {"rim": "h", "core": "H", "eye": "e"}
_DRIFTBELL_MATRIARCH = _wisp_grid(_DRIFTBELL_MATRIARCH_CHARS, width=23, height=19,
                                   core_rx=7.6, core_ry=6.2, tail_rows=8, eyes=True)

_ABYSSAL_CHOIRMASTER_CHARS = {"rim": "p", "core": "P", "eye": "e"}
_ABYSSAL_CHOIRMASTER = _wisp_grid(_ABYSSAL_CHOIRMASTER_CHARS, width=23, height=20,
                                   core_rx=8.2, core_ry=5.4, tail_rows=6, eyes=True)

_THORNROCK_COLOSSUS_PAL = {"G": (90, 130, 60), "t": (110, 90, 70), "w": (150, 120, 90),
                            "C": (60, 55, 50), "E": (255, 150, 40), "e": (255, 210, 90)}
_ASHENREACH_DEVOURER_PAL = {"D": (60, 55, 60), "d": (95, 85, 90), "E": (255, 120, 40),
                             "e": (255, 200, 90)}
_TIDEGLASS_WARDEN_PAL = {"u": (40, 90, 110), "G": (70, 150, 170), "W": (150, 225, 230),
                          "H": (225, 250, 250), "e": (20, 45, 55)}
_DRIFTBELL_MATRIARCH_PAL = {"h": (150, 190, 210), "H": (225, 240, 245), "e": (35, 60, 70)}
_ABYSSAL_CHOIRMASTER_PAL = {"p": (70, 40, 100), "P": (120, 80, 160), "e": (230, 200, 255)}


ENEMY_GRIDS = {"bat": (_BAT, _BAT_PAL), "ghost": (_GHOST, _GHOST_PAL),
               "skeleton": (_SKELETON, _SKELETON_PAL), "imp": (_IMP, _IMP_PAL),
               "goblin": (_GOBLIN, _GOBLIN_PAL), "scorpion": (_SCORPION, _SCORPION_PAL),
               "yeti": (_YETI, _YETI_PAL), "troll": (_TROLL, _TROLL_PAL),
               "harpy": (_HARPY, _HARPY_PAL), "salamander": (_SALAMANDER, _SALAMANDER_PAL),
               "panther": (_PANTHER, _PANTHER_PAL), "ghoul": (_GHOUL, _GHOUL_PAL),
               "frost_wraith": (_FROST_WRAITH, _FROST_WRAITH_PAL),
               "cave_lurker": (_CAVE_LURKER, _CAVE_LURKER_PAL),
               "thornling": (_GOBLIN, _THORNLING_PAL), "dune_stalker": (_SCORPION, _DUNE_STALKER_PAL),
               "frost_sprite": (_GHOST, _FROST_SPRITE_PAL), "bog_crawler": (_TROLL, _BOG_CRAWLER_PAL),
               "cliff_strider": (_HARPY, _CLIFF_STRIDER_PAL), "cinder_wisp": (_SALAMANDER, _CINDER_WISP_PAL),
               "vine_serpent": (_PANTHER, _VINE_SERPENT_PAL), "husk_wanderer": (_GHOUL, _HUSK_WANDERER_PAL),
               "glacier_shard": (_FROST_WRAITH, _GLACIER_SHARD_PAL), "deep_stalker": (_CAVE_LURKER, _DEEP_STALKER_PAL),
               "boss": (_BOSS, _BOSS_PAL), "frost_monarch": (_BOSS, _FROST_MONARCH_PAL),
               "ash_behemoth": (_BOSS, _ASH_BEHEMOTH_PAL), "void_reaper": (_BOSS, _VOID_REAPER_PAL),
               "thorn_warden": (_BOSS, _THORN_WARDEN_PAL), "sand_wyrm": (_BOSS, _SAND_WYRM_PAL),
               # reserved-pocket second-phase boss variants (see realm_sim.py) - same
               # silhouette, darker/redder retint (see _phase2_pal) as a placeholder look
               "boss_phase2": (_BOSS, _BOSS_PHASE2_PAL), "frost_monarch_phase2": (_BOSS, _FROST_MONARCH_PHASE2_PAL),
               "ash_behemoth_phase2": (_BOSS, _ASH_BEHEMOTH_PHASE2_PAL),
               "void_reaper_phase2": (_BOSS, _VOID_REAPER_PHASE2_PAL),
               "thorn_warden_phase2": (_BOSS, _THORN_WARDEN_PHASE2_PAL),
               "sand_wyrm_phase2": (_BOSS, _SAND_WYRM_PHASE2_PAL),
               "mad_god": (_BOSS, _MAD_GOD_PAL), "mad_god_phase2": (_BOSS, _MAD_GOD_PHASE2_PAL),
               # neutral (always-passive), and now also unshootable/flee-on-threat, ambient wildlife
               "forest_hare": (_FOREST_HARE, _FOREST_HARE_PAL), "cave_moth": (_CAVE_MOTH, _CAVE_MOTH_PAL),
               "songbird": (_SONGBIRD, _SONGBIRD_PAL), "deer": (_DEER, _DEER_PAL),
               "desert_lizard": (_DESERT_LIZARD, _DESERT_LIZARD_PAL), "marsh_heron": (_MARSH_HERON, _MARSH_HERON_PAL),
               "totem": (_TOTEM, _TOTEM_PAL),
               # Batch 15 friendly creatures (see _ELK etc.)
               "elk": (_ELK, _ELK_PAL), "mountain_goat": (_MOUNTAIN_GOAT, _MOUNTAIN_GOAT_PAL),
               "snow_fox": (_SNOW_FOX, _SNOW_FOX_PAL), "scrap_rat": (_SCRAP_RAT, _SCRAP_RAT_PAL),
               "tortoise": (_TORTOISE, _TORTOISE_PAL), "tree_frog": (_TREE_FROG, _TREE_FROG_PAL),
               "fire_beetle": (_FIRE_BEETLE, _FIRE_BEETLE_PAL), "flamingo": (_FLAMINGO, _FLAMINGO_PAL),
               "ice_penguin": (_ICE_PENGUIN, _ICE_PENGUIN_PAL), "mushroom_folk": (_MUSHROOM_FOLK, _MUSHROOM_FOLK_PAL),
               # "The Reforging" island guardians - shard pool (warm ember/rubble)
               "ember_wisp": (_EMBER_WISP, _EMBER_WISP_PAL), "fury_shard": (_FURY_SHARD, _FURY_SHARD_PAL),
               "rubble_crawler": (_RUBBLE_CRAWLER, _RUBBLE_CRAWLER_PAL), "spite_spirit": (_SPITE_SPIRIT, _SPITE_SPIRIT_PAL),
               "shard_sentinel": (_SHARD_SENTINEL, _SHARD_SENTINEL_PAL), "echo_knight": (_ECHO_KNIGHT, _ECHO_KNIGHT_PAL),
               "shattered_golem": (_SHATTERED_GOLEM, _SHATTERED_GOLEM_PAL), "fracture_hound": (_FRACTURE_HOUND, _FRACTURE_HOUND_PAL),
               "stone_revenant": (_STONE_REVENANT, _STONE_REVENANT_PAL), "cinder_warden": (_CINDER_WARDEN, _CINDER_WARDEN_PAL),
               # Batch 14 Track B1 - island mini-bosses (first 5 islands, shard pool)
               "cinder_colossus": (_CINDER_COLOSSUS, _CINDER_COLOSSUS_PAL),
               "rubble_warlord": (_RUBBLE_WARLORD, _RUBBLE_WARLORD_PAL),
               "ashreach_revenant": (_ASHREACH_REVENANT, _ASHREACH_REVENANT_PAL),
               # choir pool (cool teal/coral/pearl)
               "tide_wisp": (_TIDE_WISP, _TIDE_WISP_PAL), "pearl_acolyte": (_PEARL_ACOLYTE, _PEARL_ACOLYTE_PAL),
               "brine_crawler": (_BRINE_CRAWLER, _BRINE_CRAWLER_PAL), "abyssal_chorister": (_ABYSSAL_CHORISTER, _ABYSSAL_CHORISTER_PAL),
               "coral_sentinel": (_CORAL_SENTINEL, _CORAL_SENTINEL_PAL), "drowned_custodian": (_DROWNED_CUSTODIAN, _DROWNED_CUSTODIAN_PAL),
               "kelp_stalker": (_KELP_STALKER, _KELP_STALKER_PAL), "shellback_guardian": (_SHELLBACK_GUARDIAN, _SHELLBACK_GUARDIAN_PAL),
               "siren_wraith": (_SIREN_WRAITH, _SIREN_WRAITH_PAL), "choir_warden": (_CHOIR_WARDEN, _CHOIR_WARDEN_PAL),
               # Batch 14 Track B1 - island mini-bosses (first 5 islands, choir pool)
               "choir_sovereign": (_CHOIR_SOVEREIGN, _CHOIR_SOVEREIGN_PAL),
               "coral_leviathan": (_CORAL_LEVIATHAN, _CORAL_LEVIATHAN_PAL),
               # Batch 14 Track B2 - island mini-bosses (last 5 islands)
               "thornrock_colossus": (_THORNROCK_COLOSSUS, _THORNROCK_COLOSSUS_PAL),
               "ashenreach_devourer": (_ASHENREACH_DEVOURER, _ASHENREACH_DEVOURER_PAL),
               "tideglass_warden": (_TIDEGLASS_WARDEN, _TIDEGLASS_WARDEN_PAL),
               "driftbell_matriarch": (_DRIFTBELL_MATRIARCH, _DRIFTBELL_MATRIARCH_PAL),
               "abyssal_choirmaster": (_ABYSSAL_CHOIRMASTER, _ABYSSAL_CHOIRMASTER_PAL)}


def _validate_grids(named_grids):
    """
    A grid character with no matching palette entry used to silently render
    as debug-magenta (255, 0, 255) - that's how the 'E' vs 'e' eye-colour
    typo slipped in unnoticed. Fail loudly at import time instead.
    """
    for name, (grid, palette) in named_grids.items():
        used = {ch for row in grid for ch in row if ch not in (" ", ".")}
        missing = used - palette.keys()
        if missing:
            raise ValueError(f"sprite '{name}': grid uses char(s) {sorted(missing)} with no palette entry")


_validate_grids(CLASS_GRIDS)
_validate_grids(ENEMY_GRIDS)


UPSCALE_PASSES = 2  # Scale2x applied twice = 4x linear resolution over the small base render


def player_sprite(cls_name: str) -> pygame.Surface:
    key = ("player", cls_name)
    if key not in _cache:
        art = _load_art(f"players/player_{cls_name}.png", FINAL_SIZE)
        if art is not None:
            _cache[key] = art
        else:
            grid, pal = CLASS_GRIDS[cls_name]
            base = _autline_and_render(grid, pal, PX)
            _cache[key] = _upscale(base, UPSCALE_PASSES, final_size=(FINAL_SIZE, FINAL_SIZE))
    return _cache[key]


BOSS_KINDS = {"boss", "frost_monarch", "ash_behemoth", "void_reaper", "thorn_warden", "sand_wyrm",
              "boss_phase2", "frost_monarch_phase2", "ash_behemoth_phase2", "void_reaper_phase2",
              "thorn_warden_phase2", "sand_wyrm_phase2",
              # Batch 14 Track B1 - island mini-bosses get the same boss sprite-scale treatment
              "cinder_colossus", "rubble_warlord", "ashreach_revenant", "choir_sovereign", "coral_leviathan",
              # Batch 14 Track B2 - same treatment for the last 5 islands' mini-bosses
              "thornrock_colossus", "ashenreach_devourer", "tideglass_warden",
              "driftbell_matriarch", "abyssal_choirmaster", "mad_god", "mad_god_phase2"}


def enemy_sprite(kind: str, scale: float = 1.0) -> pygame.Surface:
    """scale != 1 (Batch 15 E4 - big bosses/guardians): the normal sprite smoothscaled
    by that factor, cached separately per (kind, scale)."""
    if scale and abs(scale - 1.0) > 1e-3:
        skey = ("enemy", kind, round(scale, 2))
        if skey not in _cache:
            base = enemy_sprite(kind)
            _cache[skey] = pygame.transform.smoothscale(
                base, (max(1, round(base.get_width() * scale)), max(1, round(base.get_height() * scale))))
        return _cache[skey]
    key = ("enemy", kind)
    if key not in _cache:
        grid, pal = ENEMY_GRIDS[kind]
        if kind in BOSS_KINDS:
            base = _autline_and_render(grid, pal, PX)
            native = _art_native_size(f"enemies/enemy_{kind}.png")
            if native is not None:
                nw, nh = native
                scale = BOSS_FINAL_SIZE / max(nw, nh)
                target = (max(1, round(nw * scale)), max(1, round(nh * scale)))
            else:
                w, h = base.get_size()
                target = (BOSS_FINAL_SIZE, int(BOSS_FINAL_SIZE * h / w))
        else:
            base = _autline_and_render(grid, pal, PX)
            target = (FINAL_SIZE, FINAL_SIZE)
        art = _load_art(f"enemies/enemy_{kind}.png", target)
        if art is not None:
            _cache[key] = art
        else:
            _cache[key] = _upscale(base, UPSCALE_PASSES, final_size=target)
    return _cache[key]


def _radial_shade(surf, center, radius, base_color, steps=None):
    """Concentric-ring radial gradient (bright core -> base color at the rim) -
    at bullet scale (radius ~4-8px) there's no room for real per-pixel painted
    detail, so the "bespoke art" upgrade here is a richer procedural shade
    instead of a flat fill, drawn ring-by-ring from the outside in so each
    smaller circle paints over the last."""
    steps = steps or max(2, radius)
    for i in range(steps, 0, -1):
        t = i / steps  # 1.0 at the rim, ~0 at the core
        # visual-punch pass: a brighter, higher-contrast core (was 0.7-1.6, now
        # 0.7-2.0) so the hottest center reads as a real bright flare, not just
        # a slightly-lighter tint of the rim color
        ring_color = _shade(base_color, 0.7 + 1.3 * (1 - t))
        pygame.draw.circle(surf, ring_color, center, max(1, round(radius * t)))


def bullet_surface(color, radius=5, shape="bolt") -> pygame.Surface:
    """`shape` is a per-CLASS categorical hint (see realm_sim.player_fire) -
    "orb" (wizard/necromancer's default), "arrow" (archer), "blade"
    (warrior/paladin), "bone" (necromancer), "holy" (priest), "star"
    (rogue/assassin), or the generic "bolt" fallback for anything untagged
    (enemy bullets). A real shape difference per category, not just a color
    swap. Deliberately NOT hand-painted PNG art (unlike every other sprite in
    this module) - at this on-screen size (radius is typically 4-8px, so a
    ~12-20px canvas) individually painted pixels read as noise, not detail;
    a richer PROCEDURAL shade (radial gradient cores, edge highlights, small
    per-shape embellishments below) is the actual visual upgrade available
    at this scale."""
    key = ("bullet", color, radius, shape)
    if key not in _cache:
        pad = 4  # room for the bigger outer glow so it doesn't get clipped
        d = (radius + pad) * 2
        c = radius + pad
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        # visual-punch pass: a wider, brighter 3-layer glow (was a 2-layer,
        # +1/+2px, max alpha-70 halo) so every shot reads as more threatening at
        # a glance, not just the class/rank-specific shapes below
        glow = _shade(color, 1.0)
        for i, r in enumerate((radius + 4, radius + 2, radius + 1)):
            a = 110 - i * 30
            layer = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*glow, a), (c, c), r)
            surf.blit(layer, (0, 0))
        highlight = (255, 255, 255)
        dark = _shade(color, 0.55)
        if shape == "arrow":
            # a forward-pointing chevron/arrowhead with a small tail fletching -
            # Bullet.draw rotates the final blit to match the bullet's actual heading
            pts = [(c + radius, c), (c - radius * 0.6, c - radius * 0.75),
                   (c - radius * 0.1, c), (c - radius * 0.6, c + radius * 0.75)]
            pygame.draw.polygon(surf, OUTLINE, pts)
            pygame.draw.polygon(surf, dark, [(x, y) for x, y in
                                              [(c + radius - 1, c), (c - radius * 0.55, c - radius * 0.65),
                                               (c - radius * 0.1, c), (c - radius * 0.55, c + radius * 0.65)]])
            # bright shaft stripe along the top edge for a metallic-glint read
            pygame.draw.line(surf, highlight, (c + radius * 0.7, c - radius * 0.1),
                              (c - radius * 0.05, c - radius * 0.35), 1)
            pygame.draw.line(surf, dark, (c - radius * 0.6, c), (c - radius * 1.15, c - radius * 0.35), 2)
            pygame.draw.line(surf, dark, (c - radius * 0.6, c), (c - radius * 1.15, c + radius * 0.35), 2)
        elif shape == "blade":
            # a thin elongated diamond with a bright edge-glint stripe - reads as
            # a swung blade catching light, not a flat bolt
            pts = [(c + radius * 1.3, c), (c, c - radius * 0.45), (c - radius * 1.3, c), (c, c + radius * 0.45)]
            pygame.draw.polygon(surf, OUTLINE, pts)
            inner = [(c + radius * 1.1, c), (c, c - radius * 0.3), (c - radius * 1.1, c), (c, c + radius * 0.3)]
            pygame.draw.polygon(surf, dark, inner)
            pygame.draw.polygon(surf, color, [(c + radius * 1.1, c), (c, c - radius * 0.3), (c - radius * 0.3, c)])
            pygame.draw.line(surf, highlight, (c + radius * 0.9, c - radius * 0.06),
                              (c - radius * 0.3, c - radius * 0.06), 1)
        elif shape == "bone":
            # a shaded capsule with two knobbed ends - a literal bone shape,
            # darker underside on the shaft+knobs for a sense of roundness
            pygame.draw.line(surf, OUTLINE, (c - radius, c), (c + radius, c), max(2, radius // 2))
            pygame.draw.line(surf, dark, (c - radius, c + 1), (c + radius, c + 1), max(1, radius // 2 - 1))
            pygame.draw.line(surf, color, (c - radius, c - 1), (c + radius, c - 1), max(1, radius // 2 - 2))
            for kx in (c - radius, c + radius):
                pygame.draw.circle(surf, OUTLINE, (int(kx), c), max(2, radius // 2 + 1))
                pygame.draw.circle(surf, dark, (int(kx), c + 1), max(1, radius // 2))
                pygame.draw.circle(surf, highlight, (int(kx) - 1, c - 1), max(1, radius // 4))
        elif shape == "holy":
            # a radial-gradient core with a cross and four short diagonal light
            # rays past the ring - Priest's "holy light" identity, more of a
            # small burst than a flat cross-in-circle now
            pygame.draw.circle(surf, OUTLINE, (c, c), radius)
            _radial_shade(surf, (c, c), max(1, radius - 1), color)
            arm = max(1, radius - 2)
            pygame.draw.line(surf, highlight, (c, c - arm), (c, c + arm), 2)
            pygame.draw.line(surf, highlight, (c - arm, c), (c + arm, c), 2)
            ray = radius * 0.6
            for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                pygame.draw.line(surf, highlight, (c, c),
                                  (c + dx * (radius + ray), c + dy * (radius + ray)), 1)
        elif shape == "star":
            # an 8-point throwing star with alternating light/dark facets for a
            # faceted-metal read, plus a small bright center gem
            pts_outer, pts_inner = [], []
            for i in range(8):
                ang = math.pi / 4 * i
                pts_outer.append((c + math.cos(ang) * radius, c + math.sin(ang) * radius))
                r_in = (radius - 1) * 0.4
                pts_inner.append((c + math.cos(ang) * r_in, c + math.sin(ang) * r_in))
            full = []
            for i in range(8):
                full.append(pts_outer[i])
                full.append(pts_inner[i])
            pygame.draw.polygon(surf, OUTLINE, full)
            for i in range(8):
                facet = [pts_inner[i], pts_outer[i], pts_inner[(i + 1) % 8]]
                pygame.draw.polygon(surf, color if i % 2 == 0 else dark, facet)
            pygame.draw.circle(surf, highlight, (c, c), max(1, radius // 4))
        else:
            # "orb" (wizard/necromancer's non-bone default) and the generic "bolt"
            # fallback (enemy bullets, anything untagged) - a real radial-gradient
            # glowing core instead of a flat fill + single highlight dot
            pygame.draw.circle(surf, OUTLINE, (c, c), radius)
            _radial_shade(surf, (c, c), max(1, radius - 1), color)
            pygame.draw.circle(surf, highlight, (c - radius // 3, c - radius // 3), max(1, radius // 3))
        _cache[key] = surf
    return _cache[key]


def bag_sprite(full: bool, tint_color) -> pygame.Surface:
    """A loot-bag burlap sack, hand-painted in a neutral near-white base
    (assets/sprites/v0.2/decorations/items/bag_<small|full>.png) then
    multiply-tinted to the bag's rarity color at draw time - one art asset
    covers every rarity instead of needing a separate PNG per color, and the
    auto-shader's gradient/rim-light on the base art survives the tint since
    multiply preserves relative brightness. Falls back to a plain filled
    circle if the art is missing."""
    tint_color = tuple(tint_color)
    key = ("bag", full, tint_color)
    if key not in _cache:
        name = "bag_full" if full else "bag_small"
        art = _load_art(f"decorations/items/{name}.png", 48)
        if art is not None:
            tinted = art.copy()
            tinted.fill((*tint_color, 255), special_flags=pygame.BLEND_RGBA_MULT)
            _cache[key] = tinted
        else:
            surf = pygame.Surface((48, 48), pygame.SRCALPHA)
            pygame.draw.circle(surf, tint_color, (24, 24), 20 if full else 16)
            pygame.draw.circle(surf, OUTLINE, (24, 24), 20 if full else 16, width=2)
            _cache[key] = surf
    return _cache[key]


CHEST_SKIN_COLORS = [
    (120, 90, 50),   # bronze
    (150, 150, 160),  # silver
    (200, 170, 90),  # gold
    (180, 60, 60),   # ruby
]


def chest_sprite(skin_idx: int, filled: bool) -> pygame.Surface:
    """A small procedural treasure-chest glyph for the Bazaar's permanent
    chest containers - same body/lid/lock construction as the Vault tab
    icon (game.ui._draw_chest_icon) but rendered at world-sprite size and
    cached like every other entity sprite here, since this one needs to be
    drawn at an arbitrary world position via Entity.draw(), not into a
    fixed UI rect."""
    key = ("chest", skin_idx, filled)
    if key not in _cache:
        base = CHEST_SKIN_COLORS[skin_idx % len(CHEST_SKIN_COLORS)]
        body_col = base if filled else tuple(max(0, c - 45) for c in base)
        lid_col = tuple(min(255, c + 70) for c in base)
        lock_col = tuple(min(255, c + 100) for c in base)
        surf = pygame.Surface((32, 32), pygame.SRCALPHA)
        pygame.draw.rect(surf, body_col, (5, 14, 22, 13), border_radius=3)
        pygame.draw.rect(surf, OUTLINE, (5, 14, 22, 13), width=2, border_radius=3)
        pygame.draw.rect(surf, lid_col, (5, 8, 22, 8), border_radius=3)
        pygame.draw.rect(surf, OUTLINE, (5, 8, 22, 8), width=2, border_radius=3)
        pygame.draw.rect(surf, lock_col, (13, 12, 6, 6))
        _cache[key] = surf
    return _cache[key]


def obstacle_sprite() -> pygame.Surface | None:
    """A destructible dungeon-room obstacle (see entities.Obstacle) - one
    universal hand-painted crate (assets/sprites/v0.2/decorations/dungeons/
    obstacle_crate.png), since the entity carries no per-theme info to key
    themed art off of. Returns None on missing art so the caller keeps its
    own procedural rect+crack-lines fallback."""
    key = "obstacle_crate"
    if key not in _cache:
        _cache[key] = _load_art("decorations/dungeons/obstacle_crate.png", 30)
    return _cache[key]


def _tall_prop_row(width, fill, lo, hi, base=" "):
    chars = [base] * width
    for i in range(max(0, lo), min(width, hi)):
        chars[i] = fill
    return chars


def _tall_prop_grid(kind):
    """Builds a 16-wide ASCII grid (taller than wide, ~1.6x) for one of
    world.TALL_PROP_KINDS - rows generated by width/position rather than
    hand-typed line art, so alignment can't drift, while still giving each
    kind a genuinely different silhouette (thin post / thick column /
    tapering carved stack), matching this project's "no reuse, each shape
    is its own" convention for every other prop/mob set."""
    w = 16
    rows = []
    if kind == "pole":
        # a thin post with a small ornamental brass cap, flaring slightly at the base
        rows.append(_tall_prop_row(w, "c", 6, 10))
        rows.append(_tall_prop_row(w, "c", 5, 11))
        rows.append(_tall_prop_row(w, "c", 5, 11))
        rows.append(_tall_prop_row(w, "c", 6, 10))
        for _ in range(17):
            rows.append(_tall_prop_row(w, "p", 7, 9))
        rows.append(_tall_prop_row(w, "p", 6, 10))
        rows.append(_tall_prop_row(w, "p", 6, 10))
        rows.append(_tall_prop_row(w, "p", 5, 11))
        rows.append(_tall_prop_row(w, "p", 4, 12))
    elif kind == "pillar":
        # a thick load-bearing column - wide capital, wide flared base
        rows.append(_tall_prop_row(w, "c", 4, 12))
        rows.append(_tall_prop_row(w, "c", 3, 13))
        rows.append(_tall_prop_row(w, "c", 3, 13))
        rows.append(_tall_prop_row(w, "c", 5, 11))
        for _ in range(15):
            rows.append(_tall_prop_row(w, "p", 5, 11))
        rows.append(_tall_prop_row(w, "p", 4, 12))
        rows.append(_tall_prop_row(w, "p", 4, 12))
        rows.append(_tall_prop_row(w, "p", 3, 13))
        rows.append(_tall_prop_row(w, "p", 2, 14))
        rows.append(_tall_prop_row(w, "p", 2, 14))
    elif kind == "totem":
        # a tapering 3-segment carved idol stack with a glowing rune-eye motif
        # partway up - deliberately NOT the same design as entities.py's
        # separate, unrelated `_TOTEM` enemy grid
        rows.append(_tall_prop_row(w, "t", 7, 9))
        rows.append(_tall_prop_row(w, "t", 6, 10))
        for _ in range(5):
            rows.append(_tall_prop_row(w, "t", 5, 11))
        rows.append(_tall_prop_row(w, "t", 6, 10))
        rows.append(_tall_prop_row(w, "t", 6, 10))
        for i in range(7):
            r = _tall_prop_row(w, "t", 4, 12)
            if i == 3:
                r[6] = r[7] = r[8] = r[9] = "r"
            rows.append(r)
        rows.append(_tall_prop_row(w, "t", 5, 11))
        rows.append(_tall_prop_row(w, "t", 5, 11))
        for _ in range(7):
            rows.append(_tall_prop_row(w, "t", 3, 13))
    elif kind == "banner_pole":
        # a thin post with a long cloth banner/pennant flowing down one side -
        # asymmetric silhouette, distinct from the centered pole/pillar/totem
        rows.append(_tall_prop_row(w, "c", 6, 10))
        rows.append(_tall_prop_row(w, "c", 6, 10))
        for i in range(18):
            r = _tall_prop_row(w, "p", 7, 9)
            if 3 <= i <= 14:
                for x in range(9, 13):
                    r[x] = "b"
                if i in (3, 14):
                    r[12] = " "
            rows.append(r)
        rows.append(_tall_prop_row(w, "p", 6, 10))
        rows.append(_tall_prop_row(w, "p", 5, 11))
        rows.append(_tall_prop_row(w, "p", 5, 11))
        rows.append(_tall_prop_row(w, "p", 4, 12))
    elif kind == "brazier":
        # a waist-high metal stand + bowl with a lit flame on top - the only
        # tall prop with its own light-source-coded palette (bright flame)
        rows.append(_tall_prop_row(w, "f", 7, 9))
        rows.append(_tall_prop_row(w, "f", 6, 10))
        rows.append(_tall_prop_row(w, "f", 6, 10))
        rows.append(_tall_prop_row(w, "m", 4, 12))
        rows.append(_tall_prop_row(w, "m", 3, 13))
        rows.append(_tall_prop_row(w, "m", 4, 12))
        rows.append(_tall_prop_row(w, "m", 5, 11))
        rows.append(_tall_prop_row(w, "m", 6, 10))
        for _ in range(11):
            rows.append(_tall_prop_row(w, "s", 7, 9))
        rows.append(_tall_prop_row(w, "s", 6, 10))
        rows.append(_tall_prop_row(w, "s", 5, 11))
        rows.append(_tall_prop_row(w, "s", 4, 12))
        rows.append(_tall_prop_row(w, "s", 3, 13))
    elif kind == "signpost":
        # a post with two angled plank arms at different heights, pointing
        # opposite directions - reads as a trail marker, no text needed
        rows.append(_tall_prop_row(w, "w", 6, 10))
        rows.append(_tall_prop_row(w, "w", 6, 10))
        r1 = _tall_prop_row(w, "w", 7, 9)
        for x in range(2, 8):
            r1[x] = "a"
        rows.append(r1)
        r2 = _tall_prop_row(w, "w", 7, 9)
        for x in range(2, 7):
            r2[x] = "a"
        rows.append(r2)
        rows.append(_tall_prop_row(w, "w", 7, 9))
        r3 = _tall_prop_row(w, "w", 7, 9)
        for x in range(9, 15):
            r3[x] = "a"
        rows.append(r3)
        r4 = _tall_prop_row(w, "w", 7, 9)
        for x in range(9, 14):
            r4[x] = "a"
        rows.append(r4)
        for _ in range(14):
            rows.append(_tall_prop_row(w, "w", 7, 9))
        rows.append(_tall_prop_row(w, "w", 6, 10))
        rows.append(_tall_prop_row(w, "w", 5, 11))
    else:
        rows = [_tall_prop_row(w, "t", 6, 10) for _ in range(20)]
    return ["".join(r) for r in rows]


_TALL_PROP_PALETTES = {
    "pole": {"c": (180, 150, 90), "p": (120, 95, 60)},       # brass cap, wood post
    "pillar": {"c": (200, 195, 180), "p": (150, 145, 130)},  # pale stone
    "totem": {"t": (110, 90, 60), "r": (90, 210, 130)},      # carved wood + glowing rune
    "banner_pole": {"c": (180, 150, 90), "p": (110, 85, 55), "b": (170, 40, 50)},  # brass
    # cap, wood post, red cloth - NOT the same asset as the unrelated flat
    # NEXUS_BANNER wall decoration elsewhere in this file
    "brazier": {"f": (255, 150, 40), "m": (90, 80, 70), "s": (60, 55, 50)},  # flame, bowl, stand
    "signpost": {"w": (120, 90, 55), "a": (150, 115, 75)},   # post, plank arms
}


def tall_prop_sprite(kind) -> pygame.Surface:
    """A semi-3D decoration prop (see world.TALL_PROP_KINDS/TALL_PROP_TILE) -
    totem/pole/pillar, rendered taller than a normal tile footprint (~1.6x
    height:width) via the same `_autline_and_render` pipeline every other
    sprite here uses, with a genuinely TRANSPARENT background (unlike the
    flat, fully-opaque ground-decoration tiles elsewhere in this module -
    this is a narrow standalone object, not a floor-replacing texture:
    world.py's TileMap.draw() draws the real floor tile underneath
    separately, then blits this on top, anchored at its own bottom edge so
    it visually extends upward past its tile's top edge - the actual
    "semi-3D" cue). One universal look per kind, not per-biome, matching
    obstacle_sprite()'s same "no per-theme info to key off of" reasoning.
    Unrelated to entities.ENEMY_KINDS["totem"] (a damageable enemy) despite
    the shared name - different registry, different asset, coincidental
    naming overlap only.

    A hand-painted PNG (assets/sprites/v0.2/decorations/props/tile_tallprop_
    <kind>_0.png, made with the pixel-mcp tool) loads in front of the
    procedural grid below, same graceful-fallback convention as every other
    hand-painted replacement in this module (_load_art returns None on any
    failure). Unlike the square/boss-aspect PNGs elsewhere in this file,
    these are loaded at their OWN native size via _art_native_size (no
    forced rescale to a fixed target) - TileMap.draw()'s tall-prop overlay
    pass already just uses whatever width/height the returned Surface
    actually has to anchor it at the tile's bottom edge, so preserving the
    exact painted pixel dimensions is correct here, not a square/boss-style
    "fit to a target size" scale."""
    key = ("tall_prop", kind)
    if key not in _cache:
        filename = f"decorations/props/tile_tallprop_{kind}_0.png"
        native = _art_native_size(filename)
        art = _load_art(filename, native) if native is not None else None
        if art is not None:
            _cache[key] = art
        else:
            grid = _tall_prop_grid(kind)
            palette = _TALL_PROP_PALETTES.get(kind, {"t": (150, 150, 150)})
            _cache[key] = _autline_and_render(grid, palette, scale=3, shaded=True)
    return _cache[key]


# permanent-potion/temp-draught liquid colors per stat key (see items.STAT_KEYS) -
# both potion families share one neutral hand-painted bottle (icon_potion_neutral.png,
# same multiply-tint technique as bag_sprite) instead of needing 6 separately
# painted bottles; the tint IS the whole visual distinction between stats.
_POTION_STAT_COLORS = {
    "att": (215, 60, 45), "deF": (75, 115, 205), "spd": (225, 205, 45),
    "dex": (65, 175, 95), "vit": (225, 75, 145), "wis": (155, 85, 225),
}


def _potion_icon_art(stat_key, dramatic=False) -> pygame.Surface | None:
    """`dramatic=True` is the temp "Draught of X" look - the same tinted bottle,
    just bigger and with a glowing aura + sparkles behind it, so it reads as
    a stronger/showier effect than the small permanent-potion bottle even
    though it's built from the same base art."""
    key = ("potion_icon", stat_key, dramatic)
    if key in _cache:
        return _cache[key]
    base = _load_art("decorations/items/icon_potion_neutral.png", 24)
    if base is None:
        _cache[key] = None
        return None
    color = _POTION_STAT_COLORS.get(stat_key, (200, 200, 200))
    tinted = base.copy()
    tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
    if not dramatic:
        _cache[key] = tinted
        return tinted
    surf = pygame.Surface((28, 28), pygame.SRCALPHA)
    glow = _shade(color, 1.15)
    for i, rad in enumerate((13, 10)):
        a = 100 - i * 35
        layer = pygame.Surface((28, 28), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*glow, a), (14, 14), rad)
        surf.blit(layer, (0, 0))
    big = pygame.transform.smoothscale(tinted, (27, 27))
    surf.blit(big, big.get_rect(center=(14, 14)))
    for ang in (30, 150, 270):
        ex = 14 + 12 * math.cos(math.radians(ang))
        ey = 14 + 12 * math.sin(math.radians(ang))
        pygame.draw.circle(surf, (255, 255, 255), (int(ex), int(ey)), 1)
    _cache[key] = surf
    return surf


def item_icon(tier_color, shape="sword") -> pygame.Surface:
    key = ("item", tier_color, shape)
    if key in _cache:
        return _cache[key]
    surf = pygame.Surface((28, 28), pygame.SRCALPHA)
    pygame.draw.rect(surf, (30, 30, 34), (0, 0, 28, 28), border_radius=4)
    pygame.draw.rect(surf, tier_color, (0, 0, 28, 28), width=2, border_radius=4)
    if shape.startswith("potion_") or shape.startswith("draught_"):
        dramatic = shape.startswith("draught_")
        stat_key = shape.split("_", 1)[1]
        art = _potion_icon_art(stat_key, dramatic=dramatic)
        if art is not None:
            surf.blit(art, (0, 0) if dramatic else (2, 2))
            _cache[key] = surf
            return surf
        shape = "potion"  # neutral bottle art missing - fall back to the plain primitive draw below
    art = _load_art(f"decorations/items/icon_{shape}.png", 24)
    if art is not None:
        surf.blit(art, (2, 2))
        _cache[key] = surf
        return surf
    cx, cy = 14, 14
    if shape == "sword":
        pygame.draw.line(surf, (90, 70, 30), (6, 24), (10, 20), 4)
        pygame.draw.line(surf, (210, 210, 220), (8, 22), (22, 8), 3)
        pygame.draw.line(surf, (245, 245, 250), (9, 21), (21, 9), 1)
    elif shape == "bow":
        pygame.draw.arc(surf, (110, 80, 45), (6, 4, 16, 20), 1.2, 5.1, 3)
        pygame.draw.line(surf, (230, 230, 230), (10, 6), (10, 22), 1)
    elif shape == "staff":
        pygame.draw.line(surf, (100, 70, 40), (10, 24), (20, 4), 3)
        pygame.draw.circle(surf, (60, 30, 100), (20, 4), 5)
        pygame.draw.circle(surf, (170, 110, 250), (20, 4), 3)
    elif shape == "ring":
        pygame.draw.circle(surf, (150, 120, 40), (cx, cy), 8, 3)
        pygame.draw.circle(surf, (250, 220, 110), (cx, cy), 6, 2)
    elif shape == "armor":
        pygame.draw.polygon(surf, (100, 100, 110), [(8, 6), (20, 6), (22, 16), (14, 24), (6, 16)])
        pygame.draw.polygon(surf, (170, 170, 180), [(8, 6), (14, 8), (14, 20), (6, 16)])
    elif shape == "potion":
        pygame.draw.rect(surf, (140, 30, 30), (10, 10, 8, 12), border_radius=2)
        pygame.draw.rect(surf, (220, 60, 60), (11, 11, 3, 10))
        pygame.draw.rect(surf, (230, 230, 230), (11, 6, 6, 5))
    elif shape == "ability":
        pygame.draw.circle(surf, (40, 20, 70), (cx, cy), 9)
        pygame.draw.circle(surf, (150, 90, 230), (cx, cy), 7)
        pygame.draw.circle(surf, (220, 190, 255), (cx, cy), 3)
        for ang in (0, 72, 144, 216, 288):
            ex = cx + 11 * math.cos(math.radians(ang))
            ey = cy + 11 * math.sin(math.radians(ang))
            pygame.draw.circle(surf, (200, 160, 250), (int(ex), int(ey)), 1)
    elif shape == "shard":
        # a faceted crystal shard - one universal look regardless of which
        # dungeon theme it opens (Item.shard_theme isn't threaded through to
        # here), an arcane violet fragment fits "torn piece of a dungeon" for
        # any theme without needing 7 separate painted variants
        outer = [(14, 3), (21, 13), (16, 25), (9, 15)]
        pygame.draw.polygon(surf, (45, 16, 68), outer)
        pygame.draw.polygon(surf, (150, 70, 200), [(14, 3), (21, 13), (14, 14)])
        pygame.draw.polygon(surf, (110, 45, 155), [(14, 3), (14, 14), (9, 15)])
        pygame.draw.polygon(surf, (95, 35, 135), [(21, 13), (16, 25), (14, 14)])
        pygame.draw.line(surf, (225, 190, 250), (14, 6), (14, 19), 1)
        pygame.draw.polygon(surf, OUTLINE, outer, width=1)
    elif shape == "egg":
        pygame.draw.ellipse(surf, (60, 45, 30), (7, 4, 15, 21))
        pygame.draw.ellipse(surf, tier_color, (8, 5, 13, 19), width=1)
        for (sx, sy) in ((11, 10), (16, 9), (13, 15), (17, 15)):
            pygame.draw.circle(surf, (255, 245, 220), (sx, sy), 1)
    elif shape == "carrier":
        # a little barred pet carrier with a handle and two glowing eyes peeking out
        # (a packed pet, see items.make_carrier) - frame in the item's tier color
        pygame.draw.arc(surf, (90, 70, 50), (10, 2, 10, 9), 0, math.pi, 2)
        pygame.draw.rect(surf, (55, 42, 32), (5, 7, 20, 18), border_radius=3)
        pygame.draw.rect(surf, tier_color, (5, 7, 20, 18), width=1, border_radius=3)
        pygame.draw.rect(surf, (20, 16, 22), (8, 11, 14, 11))
        pygame.draw.circle(surf, (255, 240, 150), (12, 15), 1)
        pygame.draw.circle(surf, (255, 240, 150), (18, 15), 1)
        for bx in (10, 13, 16, 19):
            pygame.draw.line(surf, (150, 140, 130), (bx, 11), (bx, 21), 1)
        pygame.draw.rect(surf, OUTLINE, (5, 7, 20, 18), width=1, border_radius=3)
    elif shape == "quest":
        # a rolled parchment with a gold "!" - quest items (see game/sidequests.QUEST_ITEMS)
        pygame.draw.rect(surf, (225, 205, 160), (7, 6, 14, 16), border_radius=2)
        pygame.draw.rect(surf, (170, 140, 90), (5, 5, 18, 4), border_radius=2)
        pygame.draw.rect(surf, (170, 140, 90), (5, 19, 18, 4), border_radius=2)
        pygame.draw.line(surf, (230, 170, 40), (14, 9), (14, 15), 3)
        pygame.draw.circle(surf, (230, 170, 40), (14, 18), 1)
    _cache[key] = surf
    return surf
