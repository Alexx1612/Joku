"""
Lightweight, dependency-free burst/ring/screen-shake effects layered on top of
the existing hit-flash (entities.py), floating damage numbers (ui.py), and
weather particles (weather.py) - this module fills the real gaps a VFX audit
found: no visual at all for enemy/player death, most ability casts (only
shield's ring and freeze's tint existed), level-up, boss-appear, and the
fishing/wishing jackpot, plus no screen-shake anywhere.

Same from-scratch-code philosophy as the rest of the game's art/audio: every
effect is just plain pygame.draw primitives on small per-effect SRCALPHA
surfaces, no external assets. Module-level lists so both main.py
(single-player, in-process RealmSim) and coop_client.py (networked snapshot)
can feed it from wherever they learn "this just happened" - see
`dispatch(vfx_events)` for the shared entry point both use.
"""
import math
import random

import pygame

_particles = []  # each: dict(pos, vel, life, max_life, color, radius)
_rings = []       # each: dict(pos, life, max_life, color, max_radius)
_shapes = []      # each: dict(kind, pos, life, max_life, color, ...) - bolts/shards/pillars/domes/crescents/
#                   waves/clouds for the per-ability spell looks (see ABILITY_STYLES / spawn_ability_style)
MAX_SHAPES = 60
_shake_mag = 0.0
_shake_time = 0.0
_shake_total = 1.0
_hitstop_until = 0  # absolute pygame.time.get_ticks() timestamp; 0 = not active
# options-menu toggles (game/settings.py -> configure) - both clients share them
_shake_enabled = True
_hitstop_enabled = True
_PARTICLE_SCALE = {"off": 0.0, "low": 0.4, "high": 1.0}
_particle_scale = 1.0


def configure(shake=True, hitstop=True, particles="high"):
    """Screen shake / hit-stop on-off and the particle amount (off/low/high).
    Turning shake or hit-stop off also cancels one already in progress."""
    global _shake_enabled, _hitstop_enabled, _particle_scale, _shake_time, _hitstop_until
    _shake_enabled, _hitstop_enabled = bool(shake), bool(hitstop)
    _particle_scale = _PARTICLE_SCALE.get(particles, 1.0)
    if not _shake_enabled:
        _shake_time = 0.0
    if not _hitstop_enabled:
        _hitstop_until = 0
    if _particle_scale <= 0:
        _particles.clear()
        _rings.clear()
        _shapes.clear()


def _scaled(count):
    """Particle count after the options-menu particle level - 'low' keeps at
    least one particle so an effect never silently vanishes, 'off' keeps none."""
    if _particle_scale >= 1.0 or count <= 0:
        return count
    if _particle_scale <= 0:
        return 0
    return max(1, int(round(count * _particle_scale)))


def spawn_burst(pos, color, count=18, speed=(50, 190), life=(0.35, 0.75), radius=(2, 4), angle_range=(0, math.tau)):
    count = _scaled(count)
    for _ in range(count):
        ang = random.uniform(*angle_range)
        spd = random.uniform(*speed)
        vel = pygame.Vector2(math.cos(ang), math.sin(ang)) * spd
        lf = random.uniform(*life)
        _particles.append({"pos": pygame.Vector2(pos), "vel": vel, "life": lf,
                            "max_life": lf, "color": color, "radius": random.uniform(*radius)})


def spawn_converge(pos, color, count=14, radius=60, life=(0.3, 0.55), pradius=(2, 4)):
    """Particles start scattered around `pos` and flow INWARD toward it -
    the opposite of spawn_burst, used for drain/lifesteal so the effect
    reads as "being pulled in" rather than another outward explosion."""
    count = _scaled(count)
    pos = pygame.Vector2(pos)
    for _ in range(count):
        ang = random.uniform(0, math.tau)
        start = pos + pygame.Vector2(math.cos(ang), math.sin(ang)) * radius
        lf = random.uniform(*life)
        vel = (pos - start) / max(lf, 0.05)
        _particles.append({"pos": start, "vel": vel, "life": lf,
                            "max_life": lf, "color": color, "radius": random.uniform(*pradius)})


def spawn_rise(pos, color, count=10, life=(0.5, 0.9), speed=(25, 55), radius=(1, 3), spread=10):
    """Particles drift mostly STRAIGHT UP off `pos` with a little side sway -
    reads as "a restorative effect happening ON you" (sparkles floating up
    past your own sprite), distinct from spawn_burst's omnidirectional
    explosion or spawn_converge's inward pull. Used for heal/mana so pet/
    priest/ability healing has a clear, attached-to-the-player cue instead
    of just another ambient particle pop that's easy to miss mid-combat."""
    count = _scaled(count)
    pos = pygame.Vector2(pos)
    for _ in range(count):
        start = pos + pygame.Vector2(random.uniform(-spread, spread), random.uniform(-4, 4))
        vel = pygame.Vector2(random.uniform(-12, 12), -random.uniform(*speed))
        lf = random.uniform(*life)
        _particles.append({"pos": start, "vel": vel, "life": lf,
                            "max_life": lf, "color": color, "radius": random.uniform(*radius)})


def spawn_ring(pos, color, max_radius=70, life=0.45):
    if _particle_scale <= 0:
        return
    _rings.append({"pos": pygame.Vector2(pos), "life": life, "max_life": life,
                    "color": color, "max_radius": max_radius})


def spawn_dust(pos, color, count=2, life=(0.25, 0.45), speed=(5, 20), radius=(1, 2)):
    """Tiny, low, short-lived puffs - footstep dust while a player moves.
    A thin semantic wrapper over spawn_burst's tuned-down defaults so call
    sites read as "footstep dust" rather than an unexplained burst call."""
    spawn_burst(pos, color, count=count, speed=speed, life=life, radius=radius)


def spawn_stream(src, dst, color, count=10, life=0.4):
    """A handful of particles drifting from src to dst over `life` seconds -
    used for lifesteal drain (enemy -> caster)."""
    count = _scaled(count)
    src, dst = pygame.Vector2(src), pygame.Vector2(dst)
    for i in range(count):
        t0 = i / max(1, count)
        _particles.append({"pos": src.lerp(dst, t0), "vel": (dst - src) * (1.0 / max(life, 0.05)),
                            "life": life * (1 - t0), "max_life": life * (1 - t0),
                            "color": color, "radius": 3})


def draw_fishing_bobber(surf, cam, player_pos, fishing_state):
    """Draws the cast line + bobber for an active fishing session - called once
    per frame per fishing player while `fishing_state` (the same dict RealmSim
    stores on Player.fishing_state: {"phase": "casting"|"biting", "timer",
    "bobber": (wx, wy)}) is not None. Purely a draw-time overlay (matches the
    global-clock-driven idle/walk animation pattern already used for Player/
    Enemy) - no new per-frame simulation state needed."""
    bobber = fishing_state.get("bobber")
    if bobber is None:
        return
    t = pygame.time.get_ticks() / 1000.0
    p_screen = cam(player_pos)
    b_screen = cam(bobber)
    mid = ((p_screen[0] + b_screen[0]) / 2, (p_screen[1] + b_screen[1]) / 2 - 10)
    pygame.draw.lines(surf, (215, 210, 190), False,
                       [(int(p_screen[0]), int(p_screen[1])), (int(mid[0]), int(mid[1])),
                        (int(b_screen[0]), int(b_screen[1]))], 1)
    phase = fishing_state.get("phase", "casting")
    if phase == "biting":
        bob_y = -abs(math.sin(t * 14.0)) * 6  # a sharp repeated dip, distinct from the idle bob
        color = (255, 210, 90)
    else:
        bob_y = math.sin(t * 6.0) * 3  # a slow, small idle bob while waiting
        color = (140, 210, 255)
    bx, by = b_screen[0], b_screen[1] + bob_y
    pygame.draw.circle(surf, color, (int(bx), int(by)), 4)
    pygame.draw.circle(surf, (25, 25, 30), (int(bx), int(by)), 4, 1)
    if phase == "biting":
        pygame.draw.line(surf, (255, 70, 70), (int(bx), int(by - 15)), (int(bx), int(by - 6)), 2)
        pygame.draw.circle(surf, (255, 70, 70), (int(bx), int(by - 3)), 1)


def trigger_shake(duration, magnitude):
    global _shake_mag, _shake_time, _shake_total
    if not _shake_enabled:
        return
    if magnitude < _shake_mag and _shake_time > 0:
        return
    _shake_mag, _shake_time, _shake_total = magnitude, duration, duration


def shake_offset(dt):
    """Called once per frame; returns a small (dx, dy) to add to the camera's
    followed position, decaying to (0, 0) over the triggered duration."""
    global _shake_time
    if _shake_time <= 0:
        return (0, 0)
    _shake_time = max(0.0, _shake_time - dt)
    mag = _shake_mag * (_shake_time / _shake_total if _shake_total else 0)
    return (random.uniform(-mag, mag), random.uniform(-mag, mag))


def trigger_hitstop(duration_ms):
    """A brief freeze-frame: `apply_hitstop(dt)` returns 0 while active. Timed
    off the real wall clock (pygame.time.get_ticks()), NOT decremented by the
    dt it scales, so a hitstop that zeroes dt to 0 can never re-arm itself and
    hang - it always expires on real time regardless of what dt does meanwhile.
    Bigger wins, same "don't stack, don't shorten" rule as trigger_shake."""
    global _hitstop_until
    if not _hitstop_enabled:
        return
    end = pygame.time.get_ticks() + duration_ms
    if end > _hitstop_until:
        _hitstop_until = end


def apply_hitstop(dt):
    """Call once per frame, immediately after computing raw dt, before it
    reaches sim.update()/vfx.update()/any animation timer. Returns 0.0 while
    a hitstop is active, otherwise returns `dt` unchanged. Safe in co-op - the
    client never runs the authoritative sim, so zeroing its local dt only
    pauses local rendering/animation smoothing for a couple of frames, never
    the server tick; in single-player it also briefly pauses the local sim,
    which is the actual intended hit-stop feel."""
    if pygame.time.get_ticks() < _hitstop_until:
        return 0.0
    return dt


def update(dt):
    for p in _particles[:]:
        p["life"] -= dt
        if p["life"] <= 0:
            _particles.remove(p)
            continue
        p["pos"] += p["vel"] * dt
        p["vel"] *= 0.92
    for r in _rings[:]:
        r["life"] -= dt
        if r["life"] <= 0:
            _rings.remove(r)
    for sh in _shapes[:]:
        sh["life"] -= dt
        if sh["life"] <= 0:
            _shapes.remove(sh)


def draw(surf, cam):
    for p in _particles:
        t = max(0.0, p["life"] / p["max_life"])
        r = max(1, int(p["radius"] * (0.5 + 0.5 * t)))
        d = r * 2 + 2
        layer = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*p["color"], int(255 * t)), (d // 2, d // 2), r)
        px, py = cam(p["pos"])
        surf.blit(layer, (px - d // 2, py - d // 2))
    for ring in _rings:
        t = max(0.0, ring["life"] / ring["max_life"])
        radius = int(6 + ring["max_radius"] * (1 - t))
        d = radius * 2 + 6
        layer = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*ring["color"], int(230 * t)), (d // 2, d // 2), radius, width=3)
        px, py = cam(ring["pos"])
        surf.blit(layer, (px - d // 2, py - d // 2))
    for sh in _shapes:
        _draw_shape(surf, cam, sh)


# ------------------------------------------------------------- dispatch --
# Structured (kind, x, y, color) tuples - RealmSim.vfx_events, in-process for
# single-player, or the equivalent field off the co-op snapshot - both funnel
# through this one place so the two renderers never have to duplicate the
# actual effect design, only how they source the event list.
_ABILITY_RING_RADIUS = {"nova": 90, "freeze": 90, "drain": 90, "chain": 40, "heal": 60, "haste": 50, "mana": 55}


def _add_shape(kind, pos, color, life, **kw):
    if _particle_scale <= 0 or len(_shapes) >= MAX_SHAPES:
        return
    _shapes.append(dict(kind=kind, pos=pygame.Vector2(pos), color=color, life=life, max_life=life, **kw))


def _jagged(a, b, segments=7, jitter=10):
    """A lightning-style polyline from a to b (fixed at spawn so it doesn't boil)."""
    a, b = pygame.Vector2(a), pygame.Vector2(b)
    d = b - a
    n = pygame.Vector2(-d.y, d.x)
    if n.length_squared() > 0:
        n = n.normalize()
    pts = [a]
    for i in range(1, segments):
        pts.append(a + d * (i / segments) + n * random.uniform(-jitter, jitter))
    pts.append(b)
    return pts


def _draw_shape(surf, cam, sh):
    t = max(0.0, sh["life"] / sh["max_life"])
    a = int(255 * t)
    col = sh["color"]
    kind = sh["kind"]
    if kind == "bolt":  # world-space jagged line (lightning / chain arc)
        pts = [cam(p) for p in sh["points"]]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = int(min(xs)) - 4, int(min(ys)) - 4
        layer = pygame.Surface((int(max(xs)) - x0 + 8, int(max(ys)) - y0 + 8), pygame.SRCALPHA)
        local = [(p[0] - x0, p[1] - y0) for p in pts]
        pygame.draw.lines(layer, (*col, a // 2), False, local, 6)
        pygame.draw.lines(layer, (255, 255, 255, a), False, local, 2)
        surf.blit(layer, (x0, y0))
        return
    if kind == "shard":  # a spinning crystal splinter flying outward
        c = sh["pos"] + sh["vel"] * (sh["max_life"] - sh["life"])
        px, py = cam(c)
        ang = sh["ang"] + (1 - t) * 8
        L = sh["r"]
        pts = [(px + math.cos(ang) * L, py + math.sin(ang) * L),
               (px + math.cos(ang + 2.6) * L * 0.4, py + math.sin(ang + 2.6) * L * 0.4),
               (px - math.cos(ang) * L * 0.5, py - math.sin(ang) * L * 0.5),
               (px + math.cos(ang - 2.6) * L * 0.4, py + math.sin(ang - 2.6) * L * 0.4)]
        x0, y0 = min(p[0] for p in pts) - 2, min(p[1] for p in pts) - 2
        layer = pygame.Surface((L * 3 + 6, L * 3 + 6), pygame.SRCALPHA)
        local = [(p[0] - x0, p[1] - y0) for p in pts]
        pygame.draw.polygon(layer, (*col, a), local)
        pygame.draw.polygon(layer, (255, 255, 255, a), local, 1)
        surf.blit(layer, (x0, y0))
        return
    px, py = cam(sh["pos"])
    grow = min(1.0, (1 - t) * 4)
    if kind == "pillar":  # a column of light rising out of the ground
        w, h = sh["w"], max(4, int(sh["h"] * (0.4 + 0.6 * min(1.0, (1 - t) * 3))))
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(w // 2):
            f = i / max(1, w // 2)
            c = (*col, int(a * 0.6 * f))
            pygame.draw.line(layer, c, (i, 0), (i, h))
            pygame.draw.line(layer, c, (w - 1 - i, 0), (w - 1 - i, h))
        pygame.draw.line(layer, (255, 255, 240, a), (w // 2, 0), (w // 2, h), 2)
        surf.blit(layer, (px - w // 2, py - h))
    elif kind == "dome":  # a translucent bubble
        r = max(4, int(sh["r"] * (0.6 + 0.4 * grow)))
        layer = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*col, int(a * 0.25)), (r + 2, r + 2), r)
        pygame.draw.circle(layer, (*col, a), (r + 2, r + 2), r, 2)
        pygame.draw.arc(layer, (255, 255, 255, a), (r // 2, r // 3, r, r), 0.6, 2.2, 2)
        surf.blit(layer, (px - r - 2, py - r - 2))
    elif kind == "crescent":  # a sweeping scythe arc
        r = sh["r"]
        start = sh["ang"] + (1 - t) * 2.4
        layer = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
        rect = (4, 4, r * 2, r * 2)
        pygame.draw.arc(layer, (*col, a // 2), rect, start, start + 1.6, 8)
        pygame.draw.arc(layer, (240, 240, 255, a), rect, start, start + 1.6, 3)
        surf.blit(layer, (px - r - 4, py - r - 4))
    elif kind == "wave":  # sound-wave arcs rippling outward (horns)
        r = int(10 + sh["r"] * (1 - t))
        layer = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
        for k in range(3):
            base = sh["ang"] + k * (math.tau / 3)
            pygame.draw.arc(layer, (*col, a), (3, 3, r * 2, r * 2), base - 0.5, base + 0.5, 3)
        surf.blit(layer, (px - r - 3, py - r - 3))
    elif kind == "cloud":  # a soft, lingering blob (poison / smoke / rot)
        r = max(3, int(sh["r"] * (0.7 + 0.3 * (1 - t))))
        layer = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*col, int(a * 0.35)), (r + 1, r + 1), r)
        pygame.draw.circle(layer, (*col, int(a * 0.5)), (r + 1, r + 1), int(r * 0.6))
        surf.blit(layer, (px - r - 1, py - r - 1))


# ability NAME -> visual style (each spell looks like what it's called)
ABILITY_STYLES = {
    "Orb of Shatter": "shatter", "Orb of Ruin": "ruin", "Orb of the Void": "void",
    "Skull of Blight": "blight", "Skull of Corruption": "corruption", "Skull of the Reaper": "reaper",
    "Quiver of Thunder": "thunder", "Quiver of Storms": "storms", "Quiver of the Gale": "gale",
    "Tome of Mending": "mending", "Tome of Restoration": "restoration", "Tome of Rebirth": "rebirth",
    "Aegis of Faith": "aegis", "Aegis of Devotion": "aegis", "Aegis of the Ward": "ward",
    "Rally Horn": "horn", "War Horn": "horn", "Horn of the Vanguard": "horn",
    "Smoke Draught": "smoke", "Shadow Draught": "smoke", "Draught of the Void": "smoke",
    "Cloak of Shadows": "shadow", "Veil of Night": "shadow", "Veil of the Abyss": "shadow",
}


def _around(pos, r):
    ang = random.uniform(0, math.tau)
    d = random.uniform(0, r)
    return pygame.Vector2(pos) + pygame.Vector2(math.cos(ang) * d, math.sin(ang) * d)


def spawn_ability_style(style, pos, color, extra=()):
    """The impact/cast look for one ability style. `extra` optionally carries a
    second world point (chain-hop source / drain caster)."""
    pos = pygame.Vector2(pos)
    R = _ABILITY_RING_RADIUS["nova"]
    other = pygame.Vector2(extra[0], extra[1]) if len(extra) >= 2 else None
    if style == "shatter":  # crystal splinters flying out of a cracked orb
        for i in range(12):
            ang = i * math.tau / 12 + random.uniform(-0.2, 0.2)
            _add_shape("shard", pos, (200, 170, 255), random.uniform(0.4, 0.6), r=random.randint(10, 15),
                       ang=ang, vel=pygame.Vector2(math.cos(ang), math.sin(ang)) * random.uniform(160, 260))
        spawn_ring(pos, (230, 210, 255), max_radius=R * 0.8, life=0.3)
        trigger_shake(0.2, 5)
    elif style == "ruin":  # a dark implosion that then cracks outward
        spawn_converge(pos, (70, 30, 90), count=22, radius=R, life=(0.25, 0.4), pradius=(3, 5))
        _add_shape("dome", pos, (60, 20, 70), 0.45, r=int(R * 0.7))
        spawn_burst(pos, (170, 90, 255), count=24, speed=(160, 300), life=(0.25, 0.45), radius=(2, 5))
        spawn_ring(pos, (120, 60, 180), max_radius=R, life=0.45)
        trigger_shake(0.3, 8)
    elif style == "void":  # purple chain lightning between hops
        if other is not None:
            _add_shape("bolt", pos, (190, 110, 255), 0.35, points=_jagged(other, pos, 8, 12))
        spawn_burst(pos, (200, 150, 255), count=10, speed=(40, 120), life=(0.2, 0.4), radius=(1, 3))
    elif style == "blight":  # a green poison cloud that lingers
        for _ in range(6):
            _add_shape("cloud", _around(pos, R * 0.55), (110, 200, 70), random.uniform(0.8, 1.2),
                       r=random.randint(18, 30))
        spawn_rise(pos, (150, 230, 90), count=10, life=(0.6, 1.0), spread=R * 0.5)
    elif style == "corruption":  # rot spreading out in dark rings with drips
        for k in range(3):
            spawn_ring(pos, (70, 110, 40), max_radius=R * (0.5 + 0.25 * k), life=0.5 + 0.2 * k)
        for _ in range(8):
            _add_shape("cloud", _around(pos, R * 0.7), (60, 90, 30), random.uniform(0.9, 1.3),
                       r=random.randint(12, 22))
        spawn_burst(pos, (120, 160, 60), count=14, speed=(30, 90), life=(0.5, 0.9), radius=(2, 4))
    elif style == "reaper":  # a scythe sweep + souls streaming back to the caster
        _add_shape("crescent", pos, (200, 40, 60), 0.4, r=int(R * 0.8), ang=random.uniform(0, math.tau))
        _add_shape("crescent", pos, (150, 20, 40), 0.5, r=int(R * 0.55), ang=random.uniform(0, math.tau))
        if other is not None:
            spawn_stream(pos, other, (230, 90, 110), count=12, life=0.5)
        spawn_converge(pos, (170, 40, 60), count=10, radius=R * 0.8, life=(0.3, 0.5))
    elif style in ("thunder", "storms"):  # lightning strikes from the sky
        n = 3 if style == "thunder" else 6
        for _ in range(n):
            ground = _around(pos, R * 0.8)
            top = ground + pygame.Vector2(random.uniform(-20, 20), -260)
            _add_shape("bolt", ground, (255, 240, 140), random.uniform(0.2, 0.35), points=_jagged(top, ground, 7, 14))
            spawn_burst(ground, (255, 240, 160), count=5, speed=(60, 140), life=(0.15, 0.3), radius=(1, 3))
        if style == "storms":
            spawn_ring(pos, (180, 200, 255), max_radius=R, life=0.4)
        trigger_shake(0.25, 6 if style == "thunder" else 9)
    elif style == "gale":  # a howling wind spiral that frosts over
        for i in range(18):
            ang = i * 0.7
            d = 10 + i * (R / 18)
            p = pos + pygame.Vector2(math.cos(ang) * d, math.sin(ang) * d)
            spawn_burst(p, (200, 240, 255), count=1, speed=(20, 50), life=(0.4, 0.7), radius=(2, 3),
                        angle_range=(ang + 1.3, ang + 1.8))
        spawn_burst(pos, (150, 220, 255), count=20, speed=(20, 70), life=(0.6, 1.0), radius=(2, 4))
        spawn_ring(pos, (170, 230, 255), max_radius=R, life=0.7)
    elif style in ("mending", "restoration", "rebirth"):  # holy light pillars, escalating
        n = {"mending": 1, "restoration": 3, "rebirth": 6}[style]
        for i in range(n):
            p = pos if i == 0 else _around(pos, 45)
            _add_shape("pillar", p, (255, 240, 170), 0.6 + 0.1 * n, w=18 + 4 * n, h=90 + 15 * n)
        spawn_rise(pos, (255, 245, 190), count=6 + 3 * n, life=(0.6, 1.1), spread=20 + 6 * n)
        if style == "rebirth":
            spawn_ring(pos, (255, 240, 170), max_radius=90, life=0.7)
    elif style == "aegis":  # a golden dome of blessing
        _add_shape("dome", pos, (255, 210, 90), 0.6, r=46)
        spawn_rise(pos, (255, 230, 140), count=8, life=(0.5, 0.9))
    elif style == "ward":  # a shimmering shield bubble
        _add_shape("dome", pos, (120, 180, 255), 0.8, r=52)
        _add_shape("dome", pos, (200, 230, 255), 0.5, r=40)
        spawn_ring(pos, (140, 190, 255), max_radius=55, life=0.5)
    elif style == "horn":  # sound waves blasting outward
        for k in range(3):
            _add_shape("wave", pos, (255, 220, 120), 0.35 + 0.12 * k, r=50 + 22 * k, ang=random.uniform(0, math.tau))
    elif style == "smoke":  # a puff of drinker's smoke
        for _ in range(9):
            _add_shape("cloud", _around(pos, 34), (170, 170, 180), random.uniform(0.7, 1.1), r=random.randint(14, 24))
        spawn_rise(pos, (210, 210, 220), count=12, life=(0.6, 1.0), spread=20)
    elif style == "shadow":  # darkness wrapping the caster
        # a violet-edged cloak of darkness folding in around the caster
        spawn_converge(pos, (150, 110, 220), count=22, radius=60, life=(0.35, 0.6), pradius=(2, 4))
        _add_shape("cloud", pos, (60, 30, 100), 0.7, r=38)
        _add_shape("crescent", pos, (170, 130, 240), 0.45, r=30, ang=random.uniform(0, math.tau))
        _add_shape("crescent", pos, (120, 80, 200), 0.55, r=40, ang=random.uniform(0, math.tau))
        spawn_ring(pos, (140, 100, 210), max_radius=44, life=0.45)




def dispatch(vfx_events):
    for ev in vfx_events:
        kind, x, y, color = ev[0], ev[1], ev[2], tuple(ev[3])
        pos = (x, y)
        if kind.startswith("ab_"):
            # a per-ability spell look: ("ab_<style>", x, y, color[, x2, y2])
            spawn_ability_style(kind[3:], pos, color, tuple(ev[4:]))
        elif kind == "death":
            # bigger/brighter punch pass - was a plain burst with no ring at all
            spawn_burst(pos, color, count=36, speed=(70, 260), life=(0.35, 0.75), radius=(2, 5))
            spawn_ring(pos, color, max_radius=55, life=0.4)
        elif kind == "boss_appear":
            spawn_burst(pos, color, count=65, speed=(90, 300), life=(0.55, 1.15), radius=(4, 8))
            spawn_ring(pos, color, max_radius=170, life=0.75)
            spawn_ring(pos, color, max_radius=220, life=0.95)  # a second, slower outer glow ring layered
            # behind the first - reads as a bigger shockwave, reusing spawn_ring, no new primitives
            trigger_shake(0.8, 16)
        elif kind == "levelup":
            spawn_burst(pos, color, count=40, speed=(50, 180), life=(0.55, 1.0), radius=(2, 5))
            spawn_ring(pos, color, max_radius=80, life=0.7)
            spawn_ring(pos, color, max_radius=115, life=0.95)  # outer glow ring for more depth
        elif kind == "jackpot":
            spawn_burst(pos, color, count=45, speed=(70, 230), life=(0.45, 0.95), radius=(3, 6))
        elif kind == "fish_cast":
            # a small ripple where the bobber lands - a single quiet ring, not a burst
            spawn_ring(pos, color, max_radius=18, life=0.5)
        elif kind == "fish_bite":
            # a quick surprised pop at the bobber the instant the bite window opens
            spawn_burst(pos, color, count=10, speed=(30, 70), life=(0.25, 0.4), radius=(1, 3))
        elif kind == "fish_splash":
            # every successful catch gets a real splash, not just the rare jackpot -
            # a burst plus a ring reads as "something broke the water's surface"
            spawn_burst(pos, color, count=20, speed=(40, 130), life=(0.3, 0.55), radius=(2, 4))
            spawn_ring(pos, (170, 200, 230), max_radius=34, life=0.4)
        elif kind == "heal":
            spawn_burst(pos, color, count=14, speed=(20, 60), life=(0.5, 0.9), radius=(2, 3))
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS["heal"], life=0.5)
            spawn_rise(pos, color, count=9, life=(0.6, 1.05))
        elif kind == "mana":
            spawn_burst(pos, color, count=10, speed=(15, 40), life=(0.4, 0.7), radius=(1, 3))
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS["mana"], life=0.4)
            spawn_rise(pos, color, count=8, life=(0.55, 0.95))
        elif kind == "haste":
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS["haste"], life=0.4)
        elif kind in ("nova_warning", "chain_warning", "drain_warning", "freeze_warning"):
            # telegraph: a single ring that visibly grows to (approximately) the
            # real impact radius over the same TELEGRAPH_DELAY window realm_sim
            # actually waits before resolving - gives a real, dodgeable warning
            # instead of an instant undodgeable AoE, distinct from each effect's
            # own punchier IMPACT look below
            key = kind.split("_")[0]
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS[key], life=0.45)
        elif kind == "nova":
            # a fast, punchy double shockwave ring - the defining "outward shove" look
            spawn_burst(pos, color, count=22, speed=(140, 260), life=(0.22, 0.4), radius=(2, 4))
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS["nova"], life=0.35)
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS["nova"] * 0.6, life=0.5)
            trigger_shake(0.25, 6)  # a real (if brief) impact kick - previously silent
        elif kind == "freeze":
            # slower, lingering icy shards + a single wide frost ring - reads as
            # "everything just got heavy and cold", not another quick pop
            spawn_burst(pos, color, count=30, speed=(25, 85), life=(0.55, 1.05), radius=(2, 4))
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS["freeze"], life=0.75)
        elif kind == "drain":
            # particles pulled INTO the position instead of exploding out of it -
            # the opposite motion of nova, matches "life being siphoned away"
            spawn_converge(pos, color, count=16, radius=70, life=(0.35, 0.6))
            spawn_ring(pos, color, max_radius=_ABILITY_RING_RADIUS["drain"] * 0.5, life=0.35)
        elif kind == "chain":
            spawn_burst(pos, color, count=8, speed=(40, 120), life=(0.25, 0.45), radius=(1, 3))
        elif kind == "hit_enemy":
            # a small, tight spark burst at the impact point + a light shake/hitstop -
            # "the cheapest weight you'll ever add" per the juice research; deliberately
            # smaller than every other kind below so regular trash hits don't overpower them
            spawn_burst(pos, color, count=6, speed=(60, 140), life=(0.15, 0.3), radius=(1, 3))
            trigger_shake(0.08, 2)
            trigger_hitstop(30)
        elif kind == "hit_boss":
            # same impact feedback as hit_enemy, scaled up - landing a hit on a boss
            # should read as heavier than landing one on a trash mob
            spawn_burst(pos, color, count=14, speed=(80, 200), life=(0.2, 0.4), radius=(2, 4))
            trigger_shake(0.15, 5)
            trigger_hitstop(55)
        elif kind == "hit_player":
            # taking damage should feel weightier than dealing it - bigger than hit_enemy
            spawn_burst(pos, color, count=10, speed=(70, 160), life=(0.2, 0.35), radius=(2, 4))
            trigger_shake(0.18, 7)
            trigger_hitstop(60)
        elif kind == "hit_player_by_boss":
            # taking a hit FROM a boss - the biggest of the four juice-trio kinds
            spawn_burst(pos, color, count=20, speed=(90, 220), life=(0.25, 0.5), radius=(3, 5))
            trigger_shake(0.3, 10)
            trigger_hitstop(90)
        elif kind == "shield":
            spawn_ring(pos, color, max_radius=45, life=0.35)
        elif kind == "bird_flyby":
            ang = random.uniform(0, math.tau)
            spawn_burst(pos, color, count=5, speed=(90, 140), life=(0.3, 0.4), radius=(1, 2),
                        angle_range=(ang - 0.15, ang + 0.15))
        elif kind == "distant_chime":
            spawn_ring(pos, color, max_radius=26, life=1.1)
        elif kind == "light_flicker":
            spawn_burst(pos, color, count=1, speed=(0, 0), life=(0.25, 0.25), radius=(10, 10))
        elif kind == "npc_wander_extra":
            spawn_burst(pos, color, count=4, speed=(5, 18), life=(0.4, 0.6), radius=(1, 2))
        elif kind == "bleed_tick":
            # a few dark-red droplets falling away - reads as "wound", not an explosion
            spawn_burst(pos, color, count=6, speed=(20, 50), life=(0.3, 0.5), radius=(1, 2),
                        angle_range=(math.pi * 0.25, math.pi * 0.75))
        elif kind == "burn_tick":
            # bright embers flicking upward - visually distinct from bleed's droplets
            # even though the underlying mechanism (a DoT timer) is identical
            spawn_burst(pos, color, count=8, speed=(30, 90), life=(0.25, 0.45), radius=(1, 3),
                        angle_range=(-math.pi * 0.75, -math.pi * 0.25))
        elif kind == "vulnerable_mark":
            # a single thin gold ring - reads as "marked", not another burst
            spawn_ring(pos, color, max_radius=26, life=0.5)
        elif kind == "melee_swing":
            # a bright, fast fan-shaped sweep at a random facing - not aimed at
            # the actual target (the (kind,x,y,color) tuple carries no direction,
            # matching every other flavor kind here), reads as "a weapon just
            # swung through this spot" regardless of which way it's facing
            ang = random.uniform(0, math.tau)
            spawn_burst(pos, color, count=7, speed=(90, 170), life=(0.12, 0.2), radius=(1, 3),
                        angle_range=(ang - 0.5, ang + 0.5))
        elif kind == "ember_drift":
            # slow embers rising off the ground - ember_den's signature ambient look
            spawn_rise(pos, color, count=3, life=(1.2, 2.0), speed=(8, 20), radius=(1, 2), spread=6)
        elif kind == "cave_drip":
            # a single droplet falling straight down from the ceiling
            spawn_burst(pos, color, count=1, speed=(40, 70), life=(0.3, 0.4), radius=(1, 2),
                        angle_range=(math.pi / 2 - 0.05, math.pi / 2 + 0.05))
        elif kind == "frost_glint":
            # a brief stationary sparkle - frozen_crypt's signature ambient look
            spawn_burst(pos, color, count=1, speed=(0, 0), life=(0.4, 0.6), radius=(2, 3))
        elif kind == "dust_mote":
            # very slow, long-lived drifting motes - jungle_ruins/generic ambient look
            spawn_burst(pos, color, count=2, speed=(2, 8), life=(1.5, 2.5), radius=(1, 1))
        elif kind == "mist_wisp":
            # slow, wide, soft drift - sunken_grotto's signature ambient look
            spawn_burst(pos, color, count=3, speed=(3, 10), life=(1.5, 2.2), radius=(2, 4))
        elif kind == "sand_haze":
            # a low sideways-drifting haze - wind_spire's signature ambient look
            ang = random.choice((0.0, math.pi))
            spawn_burst(pos, color, count=3, speed=(15, 35), life=(0.8, 1.3), radius=(1, 2),
                        angle_range=(ang - 0.2, ang + 0.2))
        else:
            spawn_burst(pos, color, count=10)


# weighted (kind, color, weight) - unrecognized kinds fall through dispatch()'s
# generic spawn_burst() fallback above until the visual session gives each one
# its own distinct look (see the standing coordination message)
NEXUS_AMBIENT_KINDS = [
    ("bird_flyby", (200, 200, 220), 3),
    ("distant_chime", (180, 200, 255), 2),
    ("light_flicker", (255, 235, 180), 2),
    ("npc_wander_extra", (200, 180, 220), 1),
]

# per-dungeon-theme ambient flavor - one signature look each, distinct from
# the Nexus's social-hub kinds above (birds/chimes/npc-wander make no sense
# underground) and from WeatherFX's rain/snow/sand/ash (which is tied to the
# floor's ground TILE, not the theme identity, and is missing entirely for
# cave/wind_spire/generic). "generic" doubles as the fallback for any theme
# name not present here (mirrors world.py's own defensive `.get(..., "generic")`
# convention).
DUNGEON_AMBIENT_KINDS = {
    "ember_den": [("ember_drift", (255, 140, 60), 1)],
    "cave": [("cave_drip", (150, 190, 210), 1)],
    "frozen_crypt": [("frost_glint", (210, 235, 255), 1)],
    "jungle_ruins": [("dust_mote", (190, 210, 140), 1)],
    "sunken_grotto": [("mist_wisp", (170, 195, 185), 1)],
    "wind_spire": [("sand_haze", (215, 195, 150), 1)],
    "generic": [("dust_mote", (190, 190, 195), 1)],
}

# same idea for the open Realm, keyed by biome name (world.GROUND_TO_BIOME_NAME's
# values) instead of dungeon theme - deliberately sparse/reused kinds (a few
# biomes sharing "dust_mote") rather than inventing 10 bespoke looks, since the
# open Realm already has WeatherFX doing most of the per-ground-tile work.
REALM_AMBIENT_KINDS = {
    "ashlands": [("ember_drift", (255, 150, 70), 1)],
    "cave": [("cave_drip", (150, 190, 210), 1)],
    "tundra": [("frost_glint", (210, 235, 255), 1)],
    "ice": [("frost_glint", (210, 235, 255), 1)],
    "jungle": [("dust_mote", (190, 210, 140), 1)],
    "swamp": [("mist_wisp", (170, 195, 185), 1)],
    "desert": [("sand_haze", (225, 205, 160), 1)],
    "wasteland": [("sand_haze", (200, 190, 170), 1)],
    "forest": [("dust_mote", (190, 210, 160), 1)],
    "highlands": [("dust_mote", (200, 200, 190), 1)],
}


class AmbientEvents:
    """Random ambient-life/flavor events for a bounded place - a re-rolled
    cooldown after every trigger, explicitly NOT a fixed loop, so it reads as
    "stuff randomly happens" rather than a metronome. Dispatched through the
    shared vfx event pipeline so single-player and co-op render it identically.
    Generalized from the original Nexus-only NexusAmbience (kept below as a
    thin subclass for its existing call sites) so dungeons/the open Realm can
    get their own ambient flavor without a parallel copy of this logic."""

    def __init__(self, kinds, cooldown_range=(15, 45)):
        self.kinds = kinds
        self.cooldown_range = cooldown_range
        self.cd = random.uniform(*cooldown_range)

    def update(self, dt, bounds, kinds=None):
        """`kinds` optionally overrides self.kinds for just this call - used by
        the open-Realm ambience, whose flavor should follow whatever biome the
        player currently stands in rather than being fixed at construction."""
        self.cd -= dt
        if self.cd > 0:
            return
        self.cd = random.uniform(*self.cooldown_range)
        use_kinds = kinds if kinds is not None else self.kinds
        if not use_kinds:
            return
        pick_kinds = [k for k, _, _ in use_kinds]
        weights = [w for _, _, w in use_kinds]
        kind = random.choices(pick_kinds, weights=weights)[0]
        color = next(c for k, c, _ in use_kinds if k == kind)
        x0, y0, x1, y1 = bounds
        x, y = random.uniform(x0, x1), random.uniform(y0, y1)
        dispatch([(kind, x, y, color)])


class NexusAmbience(AmbientEvents):
    """The Nexus/Bazaar social-hub ambient set - unchanged behavior, now just
    a thin preset over the generalized AmbientEvents."""

    def __init__(self):
        super().__init__(NEXUS_AMBIENT_KINDS, cooldown_range=(15, 45))
