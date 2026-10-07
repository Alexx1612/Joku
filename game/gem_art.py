"""
Gemstone visuals (game/gems.py is the logic): faceted stone icons, a gemmed weapon's
icon (socket pips + a glow in the first stone's colour), each element's bullet trail
and core, the player's weapon aura and the glittering gem veins in the Realm.

Everything is procedural and original; sprites that don't animate are cached.
Trails / auras animate off pygame.time.get_ticks() so co-op ghosts (no local state)
look identical.
"""
import math

import pygame

from game import gems as G

_cache = {}


def _shade(col, f):
    return tuple(max(0, min(255, int(c * f))) for c in col)


def _mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def halo(color, r, alpha=150):
    """A soft coloured halo with real alpha - reads on bright snow as well as dark grass."""
    key = ("halo", color, r, alpha)
    s = _cache.get(key)
    if s is None:
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        for i in range(r, 0, -1):
            f = (1 - i / r)
            pygame.draw.circle(s, (*color, int(alpha * f * f)), (r, r), i)
        _cache[key] = s
    return s


def glow(color, r):
    """A soft radial glow disc (for additive blits)."""
    key = ("glow", color, r)
    s = _cache.get(key)
    if s is None:
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        for i in range(r, 0, -1):
            f = (1 - i / r) ** 1.6
            pygame.draw.circle(s, (*_shade(color, f), 255), (r, r), i)
        _cache[key] = s
    return s


# ------------------------------------------------------------------- stone icons --
def draw_gem_icon(surf, kind, grade):
    """A cut stone on a 28x28 icon: more facets and sparkle the better the grade, a
    chipped corner on a Chipped one, and a soft halo behind it."""
    col = G.color_of(kind)
    light, mid, dark = _mix(col, (255, 255, 255), 0.45), col, _shade(col, 0.42)
    n = G.GRADE_FACETS.get(grade, 5)
    cx, cy, R = 14, 15, 9 if grade in ("chipped", "flawed") else 10
    halo = pygame.Surface((28, 28), pygame.SRCALPHA)
    pygame.draw.circle(halo, (*col, 55 if grade in ("flawless", "perfect") else 30), (14, 14), 13)
    surf.blit(halo, (0, 0))
    if kind == "diamond":  # brilliant cut, seen from the side: crown + pavilion
        crown = [(cx - R, cy - 2), (cx - R // 2, cy - R + 2), (cx + R // 2, cy - R + 2), (cx + R, cy - 2)]
        outer = crown + [(cx, cy + R)]
        pygame.draw.polygon(surf, mid, outer)
        for i in range(n):
            x = cx - R + (2 * R) * i / max(1, n - 1)
            pygame.draw.line(surf, light if i % 2 else dark, (int(x), cy - 2), (cx, cy + R), 1)
        pygame.draw.polygon(surf, light, [(cx - R // 2, cy - R + 2), (cx + R // 2, cy - R + 2), (cx + R // 3, cy - 2),
                                          (cx - R // 3, cy - 2)])
    else:
        # an n-gon (oval-ish for emerald/sapphire step cuts) with a table and facet spokes
        sx = 1.0 if kind in ("ruby", "topaz", "onyx") else 0.8
        sy = 1.0 if kind not in ("emerald", "amethyst") else 1.15
        rot = math.pi / n
        outer = [(cx + math.cos(rot + i * math.tau / n) * R * sx, cy + math.sin(rot + i * math.tau / n) * R * sy)
                 for i in range(n)]
        table = [(cx + (x - cx) * 0.5, cy - 1 + (y - cy) * 0.5) for x, y in outer]
        pygame.draw.polygon(surf, mid, outer)
        for i in range(n):  # facets: lit top-left, shadowed bottom-right
            a, b = outer[i], outer[(i + 1) % n]
            ta, tb = table[i], table[(i + 1) % n]
            mx, my = (a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy
            f = 0.5 - 0.5 * (mx + my) / (abs(mx) + abs(my) + 0.01)
            pygame.draw.polygon(surf, _mix(dark, light, f), [a, b, tb, ta])
        pygame.draw.polygon(surf, _mix(mid, light, 0.35), table)
        pygame.draw.polygon(surf, _shade(col, 0.25), outer, 1)
    if grade == "chipped":  # a broken corner
        pygame.draw.polygon(surf, (30, 30, 34), [(cx + R - 1, cy - R + 1), (cx + R + 2, cy - R + 1), (cx + R + 2, cy - 1)])
    if grade == "flawed":  # a crack
        pygame.draw.lines(surf, _shade(col, 0.3), False, [(cx - 4, cy - 5), (cx - 1, cy - 1), (cx - 3, cy + 3)], 1)
    # highlight + sparkle
    pygame.draw.line(surf, (255, 255, 255), (cx - 5, cy - 5), (cx - 2, cy - 7), 1)
    if grade in ("flawless", "perfect"):
        for (x, y, s) in ((22, 6, 3), (6, 22, 2)) if grade == "perfect" else ((22, 6, 2),):
            pygame.draw.line(surf, (255, 255, 255), (x - s, y), (x + s, y), 1)
            pygame.draw.line(surf, (255, 255, 255), (x, y - s), (x, y + s), 1)


# ------------------------------------------------------------ gemmed weapon icons --
def weapon_icon(base, item):
    """`base` (a cached 28x28 item icon) with a glow in the first stone's colour and one
    pip per socket along the bottom-left (filled with its stone, or empty)."""
    stones = G.stones_in(item)
    n = G.socket_count(item)
    key = ("wicon", id(base), tuple(stones), n)
    s = _cache.get(key)
    if s is not None:
        return s
    s = base.copy()
    if stones:
        col = G.color_of(stones[0][0])
        rim = pygame.Surface((28, 28), pygame.SRCALPHA)
        for i, a in ((1, 150), (2, 90), (3, 45)):
            pygame.draw.rect(rim, (*col, a), (i, i, 28 - 2 * i, 28 - 2 * i), width=1, border_radius=4)
        s.blit(rim, (0, 0))
        _star(s, (22, 6), _mix(col, (255, 255, 255), 0.5), 2)
    for i in range(n):
        x, y = 5 + i * 6, 23
        pts = [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)]
        if i < len(stones):
            c = G.color_of(stones[i][0])
            pygame.draw.polygon(s, c, pts)
            pygame.draw.polygon(s, (255, 255, 255), pts, 1)
        else:
            pygame.draw.polygon(s, (20, 20, 24), pts)
            pygame.draw.polygon(s, (150, 150, 160), pts, 1)
    _cache[key] = s
    return s


# ------------------------------------------------------------------- bullet trails --
def _star(surf, pos, col, s):
    x, y = int(pos[0]), int(pos[1])
    pygame.draw.line(surf, col, (x - s, y), (x + s, y), 1)
    pygame.draw.line(surf, col, (x, y - s), (x, y + s), 1)


def draw_bullet(surf, cam, b):
    """The element's trail behind a gemmed shot plus a glowing core (drawn before the
    bullet sprite). Deterministic per frame - no particle state - so ghosts match."""
    kind = getattr(b, "gem", None)
    if not kind or kind not in G.STONES:
        return
    col = G.color_of(kind)
    t = pygame.time.get_ticks() / 1000.0
    px, py = cam(b.pos)
    v = pygame.Vector2(b.vel)
    d = v.normalize() if v.length_squared() > 1 else pygame.Vector2(1, 0)
    n = pygame.Vector2(-d.y, d.x)
    seed = (b.pos.x * 0.37 + b.pos.y * 0.61)
    r = max(3, int(b.radius))
    h = halo(col, r * 4)
    surf.blit(h, (px - r * 4, py - r * 4))
    g = glow(col, r * 3)
    surf.blit(g, (px - r * 3, py - r * 3), special_flags=pygame.BLEND_ADD)

    def at(k, side=0.0, up=0.0):
        p = pygame.Vector2(px, py) - d * k + n * side
        return (p.x, p.y - up)

    if kind == "ruby":  # embers: shed behind, drifting up, yellow -> deep red
        for i in range(1, 11):
            f = i / 11
            jit = math.sin(t * 23 + i * 2.1 + seed) * 5
            p = at(i * 6, jit, f * 10)
            c = _mix((255, 235, 130), (190, 30, 15), f)
            rr = max(1, int(4.5 * (1 - f)) + 1)
            pygame.draw.circle(surf, _shade(c, 0.55), (int(p[0]), int(p[1])), rr + 1)
            pygame.draw.circle(surf, c, (int(p[0]), int(p[1])), rr)
    elif kind == "sapphire":  # frost motes + twinkling crystal glints
        for i in range(1, 10):
            f = i / 10
            p = at(i * 6, math.sin(seed + i * 1.7) * 4)
            rr = max(1, int(3.5 * (1 - f)) + 1)
            pygame.draw.circle(surf, _shade(col, 0.6), (int(p[0]), int(p[1])), rr + 1)
            pygame.draw.circle(surf, _mix((235, 248, 255), col, f), (int(p[0]), int(p[1])), rr)
        for k in (8, 20, 34):
            p = at(k, math.cos(t * 9 + k) * 7)
            sz = 3 + int(1.5 + 1.5 * math.sin(t * 14 + k))
            _star(surf, (p[0] + 1, p[1] + 1), (50, 100, 210), sz)
            _star(surf, p, (235, 248, 255), sz)
    elif kind == "topaz":  # a flickering lightning tail
        step = int(t * 30)
        for strand in (0, 1):
            pts = [at(0)]
            for i in range(1, 8):
                j = ((step * 7919 + i * 104729 + strand * 31) % 17) - 8
                pts.append(at(i * 7, j))
            pygame.draw.lines(surf, _shade(col, 0.55), False, pts, 4 - strand * 2)
            pygame.draw.lines(surf, (255, 255, 225), False, pts, 2 - strand)
    elif kind == "emerald":  # venom drips falling off the shot
        for i in range(1, 9):
            f = i / 9
            p = at(i * 6, math.sin(seed + i) * 3)
            drop = ((t * 40 + i * 9) % 16)
            q = (int(p[0]), int(p[1] + drop))
            c = _mix((170, 255, 170), (20, 110, 50), f)
            rr = 3 if i < 4 else 2
            pygame.draw.circle(surf, (15, 70, 30), q, rr + 1)
            pygame.draw.circle(surf, c, q, rr)
            pygame.draw.line(surf, c, (q[0], q[1] - rr - 3), q, 2)
    elif kind == "amethyst":  # a twin arcane helix
        for i in range(1, 12):
            f = i / 12
            ph = t * 14 - i * 0.8
            for sgn, c in ((1, (215, 150, 255)), (-1, (255, 130, 215))):
                p = at(i * 5, sgn * math.sin(ph) * 7)
                rr = max(1, int(3.4 * (1 - f)) + 1)
                pygame.draw.circle(surf, (70, 20, 110), (int(p[0]), int(p[1])), rr + 1)
                pygame.draw.circle(surf, _mix(c, col, f), (int(p[0]), int(p[1])), rr)
    elif kind == "onyx":  # dark smoke billowing behind
        layer = pygame.Surface((120, 120), pygame.SRCALPHA)
        for i in range(1, 9):
            f = i / 9
            p = at(i * 6, math.sin(seed + t * 3 + i) * 4, f * 4)
            rr = int(4 + 8 * f)
            pygame.draw.circle(layer, (35, 15, 50, int(175 * (1 - f))), (int(p[0] - px + 60), int(p[1] - py + 60)), rr)
        surf.blit(layer, (px - 60, py - 60))
        pygame.draw.circle(surf, (190, 140, 230), (int(px), int(py)), 2)
    elif kind == "diamond":  # prismatic glints
        rainbow = ((255, 120, 120), (255, 230, 120), (120, 255, 160), (120, 200, 255), (220, 140, 255))
        for i in range(1, 9):
            p = at(i * 6, math.sin(seed + i * 2) * 6)
            s = 2 + int(2 + 2 * math.sin(t * 18 + i * 1.3))
            _star(surf, (p[0] + 1, p[1] + 1), (60, 60, 80), max(1, s))
            _star(surf, p, rainbow[(i + int(t * 10)) % 5], max(1, s))
    # the white-hot core, ringed in the stone's colour
    pygame.draw.circle(surf, _shade(col, 0.6), (int(px), int(py)), r + 2, 2)
    pygame.draw.circle(surf, _mix(col, (255, 255, 255), 0.7), (int(px), int(py)), max(2, r // 2 + 1))


# ------------------------------------------------------------------ player aura --
def draw_player_aura(surf, center, item, facing=None):
    """A subtle element aura on a player whose weapon carries stones: motes orbiting at
    the weapon hand side + a soft glow (stronger with more stones)."""
    stones = G.stones_in(item) if item is not None else []
    if not stones:
        return
    kind = stones[0][0]
    col = G.color_of(kind)
    t = pygame.time.get_ticks() / 1000.0
    cx, cy = center
    hand = pygame.Vector2(facing) if facing is not None and pygame.Vector2(facing).length_squared() > 0 else pygame.Vector2(1, 0)
    hand = hand.normalize() * 12
    hx, hy = cx + hand.x, cy + hand.y + 4
    g = glow(col, 9 + 3 * len(stones))
    surf.blit(g, (hx - g.get_width() // 2, hy - g.get_height() // 2), special_flags=pygame.BLEND_ADD)
    for i in range(2 + len(stones)):
        a = t * 2.4 + i * math.tau / (2 + len(stones))
        rx, ry = 20, 9
        x, y = cx + math.cos(a) * rx, cy + 10 + math.sin(a) * ry
        if kind == "ruby":
            y -= (t * 20 + i * 5) % 14
        elif kind == "emerald":
            y += (t * 12 + i * 4) % 6
        front = math.sin(a) > 0
        c = _mix(col, (255, 255, 255), 0.4 if front else 0.0)
        pygame.draw.circle(surf, c, (int(x), int(y)), 2 if front else 1)


# --------------------------------------------------------------------- gem veins --
def _vein_sprite(kinds, depleted):
    key = ("vein", tuple(kinds), depleted)
    s = _cache.get(key)
    if s is not None:
        return s
    s = pygame.Surface((72, 60), pygame.SRCALPHA)
    rock, rock_d, rock_l = (92, 86, 96), (52, 48, 58), (134, 128, 138)
    pygame.draw.ellipse(s, (0, 0, 0, 80), (4, 46, 64, 12))
    body = [(4, 50), (9, 30), (20, 18), (38, 14), (54, 20), (66, 34), (68, 50)]
    pygame.draw.polygon(s, rock, body)
    pygame.draw.polygon(s, rock_l, [(9, 30), (20, 18), (38, 14), (30, 28), (16, 36)])
    pygame.draw.polygon(s, rock_d, [(54, 20), (66, 34), (68, 50), (50, 47), (46, 32)])
    pygame.draw.polygon(s, (34, 32, 40), body, 2)
    # crystal clusters jutting out of the rock (prisms with a lit and a shaded face)
    shards = [(24, 30, 14, -0.35), (36, 26, 18, 0.05), (47, 32, 12, 0.45), (16, 42, 9, -0.6), (56, 42, 9, 0.7),
              (32, 42, 8, -0.1)]
    for i, (x, y, h, lean) in enumerate(shards):
        col = G.color_of(kinds[i % len(kinds)])
        if depleted:
            col = _mix(_shade(col, 0.4), rock_d, 0.5)
            h = max(3, h // 3)
        w = max(3, h // 3)
        tip = (x + lean * h, y - h)
        left, right = (x - w, y), (x + w, y)
        pygame.draw.polygon(s, _shade(col, 0.55), [left, tip, (x, y + 2)])
        pygame.draw.polygon(s, col, [(x, y + 2), tip, right])
        if not depleted:
            pygame.draw.line(s, _mix(col, (255, 255, 255), 0.65), (x + lean * h * 0.3, y - h * 0.3), tip, 1)
        pygame.draw.polygon(s, _shade(col, 0.3), [left, tip, right, (x, y + 2)], 1)
    _cache[key] = s
    return s


def draw_veins(surf, cam, veins, mining=None, prompt_at=None):
    """veins: [(pos, kinds, charges)]; mining: (pos, frac) of the local player's channel."""
    t = pygame.time.get_ticks() / 1000.0
    w, h = surf.get_size()
    for pos, kinds, charges in veins:
        x, y = cam(pos)
        if x < -60 or y < -60 or x > w + 60 or y > h + 60:
            continue
        img = _vein_sprite(kinds, charges <= 0)
        if charges > 0:  # a coloured halo pulsing behind the crystals
            col = G.color_of(kinds[int(t * 0.7 + pos[0]) % len(kinds)])
            surf.blit(halo(col, 40, 100 + 10 * int(4 * math.sin(t * 2.2 + pos[0]))), (x - 40, y - 52))
        surf.blit(img, (x - 36, y - 46))
        if charges > 0:  # glints wandering over the crystals
            g = glow(col, 18)
            surf.blit(g, (x - 18, y - 40), special_flags=pygame.BLEND_ADD)
            for k in range(3):
                ph = (t * 1.1 + k * 0.33 + pos[1] * 0.01) % 1.0
                if ph < 0.4:
                    s = int(2 + 4 * math.sin(ph / 0.4 * math.pi))
                    gx, gy = x - 18 + (k * 19 + int(pos[0])) % 36, y - 40 + (k * 13 + int(pos[1])) % 20
                    _star(surf, (gx + 1, gy + 1), (60, 60, 70), s)
                    _star(surf, (gx, gy), (255, 255, 255), s)
    if mining is not None:
        (mx, my), frac = cam(mining[0]), mining[1]
        pygame.draw.rect(surf, (20, 20, 24), (mx - 26, my - 62, 52, 8))
        pygame.draw.rect(surf, (240, 220, 140), (mx - 25, my - 61, int(50 * max(0.0, min(1.0, frac))), 6))
    elif prompt_at is not None:  # "[F] Mine" over the vein you're standing at
        _prompt(surf, cam(prompt_at), "[F] Mine")


_FONT = []


def _prompt(surf, at, text):
    if not _FONT:
        _FONT.append(pygame.font.SysFont("consolas", 14))
    img = _FONT[0].render(text, True, (240, 235, 220))
    x, y = int(at[0]) - img.get_width() // 2, int(at[1]) - 72
    box = (x - 5, y - 2, img.get_width() + 10, img.get_height() + 4)
    pygame.draw.rect(surf, (20, 20, 26), box, border_radius=4)
    pygame.draw.rect(surf, (200, 190, 150), box, 1, border_radius=4)
    surf.blit(img, (x, y))
