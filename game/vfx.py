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
_shake_mag = 0.0
_shake_time = 0.0
_shake_total = 1.0


def spawn_burst(pos, color, count=18, speed=(50, 190), life=(0.35, 0.75), radius=(2, 4), angle_range=(0, math.tau)):
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
    pos = pygame.Vector2(pos)
    for _ in range(count):
        start = pos + pygame.Vector2(random.uniform(-spread, spread), random.uniform(-4, 4))
        vel = pygame.Vector2(random.uniform(-12, 12), -random.uniform(*speed))
        lf = random.uniform(*life)
        _particles.append({"pos": start, "vel": vel, "life": lf,
                            "max_life": lf, "color": color, "radius": random.uniform(*radius)})


def spawn_ring(pos, color, max_radius=70, life=0.45):
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
    src, dst = pygame.Vector2(src), pygame.Vector2(dst)
    for i in range(count):
        t0 = i / max(1, count)
        _particles.append({"pos": src.lerp(dst, t0), "vel": (dst - src) * (1.0 / max(life, 0.05)),
                            "life": life * (1 - t0), "max_life": life * (1 - t0),
                            "color": color, "radius": 3})


def trigger_shake(duration, magnitude):
    global _shake_mag, _shake_time, _shake_total
    if magnitude < _shake_mag:
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


# ------------------------------------------------------------- dispatch --
# Structured (kind, x, y, color) tuples - RealmSim.vfx_events, in-process for
# single-player, or the equivalent field off the co-op snapshot - both funnel
# through this one place so the two renderers never have to duplicate the
# actual effect design, only how they source the event list.
_ABILITY_RING_RADIUS = {"nova": 90, "freeze": 90, "drain": 90, "chain": 40, "heal": 60, "haste": 50, "mana": 55}


def dispatch(vfx_events):
    for kind, x, y, color in vfx_events:
        pos = (x, y)
        if kind == "death":
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
