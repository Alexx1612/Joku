"""
The night light map (night-horror update): a real coloured lighting pass instead of a
flat darkness overlay with holes cut in it.

How a frame is lit (ui.draw_day_night_overlay -> render_light_map):
  1. A small light map (1/3 of the screen) is filled with the AMBIENT light: cold blue
     moonlight at night (crimson under a Blood Moon), as bright as the Luminosity
     setting allows (ui.night_darkness_alpha).
  2. Every light is ADDED into it with its own colour and a soft radial falloff -
     amber lamps, green-gold fireflies, the player's warm lantern-light - flickering
     (two sines + a little noise, quantised to a few cached intensity steps).
  3. Lights are OCCLUDED by walls: from each light ~96 rays march over the tile grid
     until they hit a solid tile (rock, building walls, closed doors, tree trunks), and
     only the polygon they enclose is lit - walls cast real shadows, a shut house is
     dark from outside, a lit doorway spills light out. The polygon (and the masked
     light texture) is cached per light / tile position / camera angle / door state, so
     a lamp costs one cached blit per frame; the player's light is rebuilt only when
     the player changes tile.
  4. The map is scaled up and MULTIPLIED over the scene: unlit areas fall to the dim
     ambient colour, lit areas are tinted by the light that reaches them.

Pure pygame, no per-pixel Python in the per-frame path.
"""
import math
import random

import pygame

SCALE = 3                 # the light map is 1/SCALE of the screen
RAY_COUNT = 96
RAY_STEP = 8.0            # world px per march step
SKIP_NEAR = 26.0          # ignore solid tiles this close to a light's origin (a lamp post's own tile)
FLICKER_STEPS = 5         # quantised flicker levels (each one a cached texture)
MAX_OCCLUDED = 7          # the player's light + the strongest nearby lights get wall shadows
PLAYER_LIGHT_COLOR = (255, 236, 205)
MOON_TINT = (0.88, 0.94, 1.0)
BLOOD_TINT = (1.0, 0.42, 0.42)

_grad_cache = {}          # (radius_px_small, colour, step) -> colour radial gradient (RGB)
_poly_cache = {}          # light key -> list of world points (the lit polygon)
_masked_cache = {}        # (light key, angle, step) -> masked colour texture
_frame = {}               # size -> reusable light-map surface
stats = {"poly_builds": 0, "masked_builds": 0}


def ambient_color(light_level, luminosity, blood):
    """The light-map fill: what an unlit spot looks like (multiplied over the scene)."""
    from game.ui import night_darkness_alpha
    dark = 1.0 - light_level
    a = 255 - night_darkness_alpha(luminosity) * dark
    tint = BLOOD_TINT if blood else MOON_TINT
    # at dusk / dawn the ambient warms back toward white
    return tuple(max(0, min(255, int(a * (t + (1 - t) * (1 - dark))))) for t in tint)


def _gradient(r, color, step):
    key = (r, color, step)
    g = _grad_cache.get(key)
    if g is None:
        inten = 0.82 + 0.09 * step  # step 0..4 -> 0.82 .. 1.18
        g = pygame.Surface((r * 2 + 2, r * 2 + 2))
        g.fill((0, 0, 0))
        c = (r + 1, r + 1)
        for k in range(r, 0, -1):
            f = (1.0 - k / r) ** 0.85 * inten
            pygame.draw.circle(g, tuple(min(255, int(ch * f)) for ch in color), c, k)
        _grad_cache[key] = g
    return g


def _flicker_step(x, y, t, strength=1.0):
    f = 0.5 * math.sin(t * 7.3 + x * 0.05) + 0.35 * math.sin(t * 12.7 + y * 0.07) \
        + 0.15 * math.sin(t * 31.0 + x * 0.3 + y)
    f = 0.5 + 0.5 * f * strength
    return max(0, min(FLICKER_STEPS - 1, int(f * FLICKER_STEPS)))


def light_polygon(grid, solid, wx, wy, radius, tile=32):
    """World-space points of the area a light at (wx, wy) really reaches (rays march over
    the tile grid until a solid tile stops them). Light-giving props (lamp posts, braziers,
    campfires...) never block light themselves - a lamp doesn't shadow its own post."""
    from game import world
    if not world.LIGHT_TILE_INFO:
        world._build_light_tiles()
    see_through = world.LIGHT_TILE_INFO
    pts = []
    h, w = len(grid), len(grid[0])
    for i in range(RAY_COUNT):
        a = math.tau * i / RAY_COUNT
        dx, dy = math.cos(a), math.sin(a)
        d = SKIP_NEAR
        while d < radius:
            x, y = wx + dx * d, wy + dy * d
            tx, ty = int(x // tile), int(y // tile)
            if not (0 <= tx < w and 0 <= ty < h):
                break
            t_ = grid[ty][tx]
            if t_ in solid and t_ not in see_through:
                break
            d += RAY_STEP
        d = min(d + 6, radius)  # light the face of the wall it hits
        pts.append((wx + dx * d, wy + dy * d))
    stats["poly_builds"] += 1
    return pts


def _polygon_for(key, grid, solid, wx, wy, r, tile):
    p = _poly_cache.get(key)
    if p is None:
        if len(_poly_cache) > 600:
            _poly_cache.clear()
        p = _poly_cache[key] = light_polygon(grid, solid, wx, wy, r, tile)
    return p


def _masked(key, poly_world, cam, wx, wy, r_small, color, step, angle):
    """The light's colour gradient clipped to its lit polygon, in light-map pixels,
    centred on the light. Cached: the polygon only changes with the camera angle."""
    mkey = (key, round(angle, 1), step)
    m = _masked_cache.get(mkey)
    if m is not None:
        return m
    if len(_masked_cache) > 900:
        _masked_cache.clear()
    tex = _gradient(r_small, color, step).copy()
    sx, sy = cam((wx, wy))
    mask = pygame.Surface(tex.get_size())
    mask.fill((0, 0, 0))
    c = r_small + 1
    local = []
    for (px, py) in poly_world:
        qx, qy = cam((px, py))
        local.append(((qx - sx) / SCALE + c, (qy - sy) / SCALE + c))
    if len(local) >= 3:
        pygame.draw.polygon(mask, (255, 255, 255), local)
    tex.blit(mask, (0, 0), special_flags=pygame.BLEND_MULT)
    _masked_cache[mkey] = tex
    stats["masked_builds"] += 1
    return tex


def render_light_map(size, light_level, luminosity, blood, lights_screen, player_screen=None,
                     player_radius=175, occlusion=None, t=None):
    """Builds the light map (light-map resolution) for this frame and returns it.

    lights_screen: [(sx, sy, r, colour)] screen-space lights (used when there's no
    occlusion info - tests, hubs). occlusion: optional dict(grid, solid, cam, tile,
    player_world, lights_world=[(wx, wy, r, colour)], version) - when given, lights get
    wall shadows and are positioned through the camera."""
    w, h = size[0] // SCALE + 1, size[1] // SCALE + 1
    lm = _frame.get((w, h))
    if lm is None:
        lm = _frame[(w, h)] = pygame.Surface((w, h))
    lm.fill(ambient_color(light_level, luminosity, blood))
    if t is None:
        t = pygame.time.get_ticks() / 1000.0
    dark = 1.0 - light_level

    def add(tex, sx, sy, r_small):
        lm.blit(tex, (int(sx / SCALE) - r_small - 1, int(sy / SCALE) - r_small - 1),
                special_flags=pygame.BLEND_ADD)

    if occlusion is None:
        if player_screen is not None:
            r = max(4, int(player_radius / SCALE))
            add(_gradient(r, _scale_col(PLAYER_LIGHT_COLOR, dark), 2), player_screen[0], player_screen[1], r)
        for (sx, sy, lr, col) in lights_screen:
            r = max(3, int(lr / SCALE))
            add(_gradient(r, _scale_col(col, dark), _flicker_step(sx, sy, t)), sx, sy, r)
        return lm

    grid, solid, cam, tile = occlusion["grid"], occlusion["solid"], occlusion["cam"], occlusion.get("tile", 32)
    version = occlusion.get("version", 0)
    angle = getattr(cam, "angle", 0.0)
    pw = occlusion.get("player_world")
    scored = []
    for (wx, wy, lr, col) in occlusion.get("lights_world", ()):
        sx, sy = cam((wx, wy))
        if sx < -lr or sy < -lr or sx > size[0] + lr or sy > size[1] + lr:
            continue  # off screen
        dist = math.hypot(sx - size[0] / 2, sy - size[1] / 2)
        scored.append((dist - lr, wx, wy, lr, col, sx, sy))
    scored.sort()
    for n, (_s, wx, wy, lr, col, sx, sy) in enumerate(scored):
        r = max(3, int(lr / SCALE))
        step = _flicker_step(wx, wy, t)
        c2 = _scale_col(col, dark)
        if n < MAX_OCCLUDED - 1:
            key = ("L", int(wx), int(wy), int(lr), c2, version)
            poly = _polygon_for(key, grid, solid, wx, wy, lr, tile)
            add(_masked(key, poly, cam, wx, wy, r, c2, step, angle), sx, sy, r)
        else:
            add(_gradient(r, c2, step), sx, sy, r)
    if pw is not None:
        r = max(4, int(player_radius / SCALE))
        ptx, pty = int(pw[0] // tile), int(pw[1] // tile)
        key = ("P", ptx, pty, int(player_radius), version)
        poly = _polygon_for(key, grid, solid, (ptx + 0.5) * tile, (pty + 0.5) * tile, player_radius, tile)
        # the polygon is built from the tile centre; offset to the player's exact spot
        ps = cam(pw)
        tex = _masked(key, poly, cam, (ptx + 0.5) * tile, (pty + 0.5) * tile, r,
                      _scale_col(PLAYER_LIGHT_COLOR, dark), 2, angle)
        cs = cam(((ptx + 0.5) * tile, (pty + 0.5) * tile))
        add(tex, cs[0], cs[1], r)
        if math.hypot(ps[0] - cs[0], ps[1] - cs[1]) > 40:  # (never happens - a tile is 32 px)
            add(_gradient(r, _scale_col(PLAYER_LIGHT_COLOR, dark), 2), ps[0], ps[1], r)
    return lm


def _scale_col(col, dark):
    """A light is as strong as the night is dark (no lamp glow at noon)."""
    f = max(0.0, min(1.0, dark * 1.15))
    return (int(col[0] * f), int(col[1] * f), int(col[2] * f))


_full = {}


def composite(surf, lm):
    """Multiplies the (scaled-up) light map over the scene."""
    size = (lm.get_width() * SCALE, lm.get_height() * SCALE)
    full = _full.get(size)
    if full is None:
        full = _full[size] = pygame.Surface(size)
    pygame.transform.smoothscale(lm, size, full)
    surf.blit(full, (0, 0), special_flags=pygame.BLEND_MULT)


def clear_caches():
    _grad_cache.clear()
    _poly_cache.clear()
    _masked_cache.clear()
    _frame.clear()


# ------------------------------------------------------------ night VFX helpers --
_fog_layers = {}


def fog_layers(size):
    """Three tiles of organic, layered mist (value noise smooth-scaled from coarse random
    grids), built once per screen size."""
    layers = _fog_layers.get(size)
    if layers is not None:
        return layers
    rnd = random.Random(11)
    layers = []
    for scale, alpha, tint in ((22, 150, (165, 175, 190)), (11, 120, (145, 155, 175)), (5, 80, (180, 186, 200))):
        gw, gh = max(4, size[0] // (scale * 4)), max(4, size[1] // (scale * 4))
        small = pygame.Surface((gw, gh), pygame.SRCALPHA)
        for y in range(gh):
            for x in range(gw):
                v = rnd.random() ** 1.7
                small.set_at((x, y), (*tint, int(alpha * v)))
        big = pygame.transform.smoothscale(small, (size[0] + 256, size[1] + 256))
        layers.append(big)
    _fog_layers[size] = layers
    return layers
