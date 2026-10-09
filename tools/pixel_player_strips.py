"""
The players keep their chunky pixel look (the 128 px stills in assets/sprites/v0.2/players/) and get
idle / walk / shoot strips built from those stills by moving whole blocks - no repainting, no smoothing,
so every frame stays the same pixel art:

  idle  (4): the body above the legs breathes down 4 px and back
  walk  (6): the left and right leg take turns lifting (and stepping forward); the body dips on contact
  shoot (3): lean back, lean in with a chunky muzzle flash at the weapon tip, settle

Frames face right like the stills (the game flips them for left).

Run with: python tools/pixel_player_strips.py [class ...]
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "assets", "sprites", "v0.2", "players")
CLASSES = ["wizard", "archer", "warrior", "priest", "rogue", "necromancer", "paladin", "assassin"]
LEGS = 0.75  # the legs are the bottom quarter of the frame


def _opaque_box(img):
    r = img.get_bounding_rect(min_alpha=40)
    return r


def _tip(img):
    """The rightmost solid pixel between the shoulders and the knees - where the weapon points."""
    w, h = img.get_size()
    for x in range(w - 1, -1, -1):
        for y in range(int(h * 0.2), int(h * 0.75)):
            if img.get_at((x, y)).a > 120:
                return x, y
    return w - 8, h // 2


def _body_legs(still):
    w, h = still.get_size()
    ly = int(h * LEGS)
    return ly, still.subsurface((0, 0, w, ly)), still.subsurface((0, ly, w, h - ly))


def idle(still):
    w, h = still.get_size()
    ly, body, legs = _body_legs(still)
    out = []
    for dip in (0, 4, 4, 0):
        f = pygame.Surface((w, h), pygame.SRCALPHA)
        f.blit(legs, (0, ly))
        f.blit(body, (0, dip))
        out.append(f)
    return out


def walk(still):
    w, h = still.get_size()
    ly, body, _ = _body_legs(still)
    left = still.subsurface((0, ly, w // 2, h - ly))
    right = still.subsurface((w // 2, ly, w - w // 2, h - ly))
    # (left lift, right lift, body dip): lift a leg, pass, plant, other leg...
    steps = [(8, 0, 0), (4, 0, 4), (0, 0, 4), (0, 8, 0), (0, 4, 4), (0, 0, 4)]
    out = []
    for ll, rl, dip in steps:
        f = pygame.Surface((w, h), pygame.SRCALPHA)
        f.blit(left, (4 if ll else 0, ly - ll))
        f.blit(right, (w // 2 + (4 if rl else 0), ly - rl))
        f.blit(body, (0, dip))
        out.append(f)
    return out


def shoot(still):
    w, h = still.get_size()
    tx, ty = _tip(still)
    out = []
    for dx, flash in ((-4, 0), (4, 2), (0, 1)):
        f = pygame.Surface((w, h), pygame.SRCALPHA)
        f.blit(still, (dx, 0))
        if flash:
            cx, cy = min(w - 12, tx + dx + 4), ty
            c = 8  # one chunky pixel
            pts = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)] if flash == 2 else [(0, 0)]
            for i, (px, py) in enumerate(pts):
                col = (255, 255, 230) if i == 0 else (255, 210, 90)
                f.fill(col, (cx + px * c - c // 2, cy + py * c - c // 2, c, c))
        out.append(f)
    return out


def strip(frames):
    w, h = frames[0].get_size()
    s = pygame.Surface((w * len(frames), h), pygame.SRCALPHA)
    for i, f in enumerate(frames):
        s.blit(f, (i * w, 0))
    return s


def main(classes):
    pygame.init()
    pygame.display.set_mode((8, 8))
    for cls in classes:
        still = pygame.image.load(os.path.join(DIR, f"player_{cls}.png")).convert_alpha()
        for name, fn in (("idle", idle), ("walk", walk), ("shoot", shoot)):
            pygame.image.save(strip(fn(still)), os.path.join(DIR, f"player_{cls}_{name}.png"))
        print("strips:", cls, still.get_size())


if __name__ == "__main__":
    main(sys.argv[1:] or CLASSES)
