"""
Purely cosmetic per-biome weather particles (rain/snow/sand/ash), derived from
whichever BIOME the local player is currently standing in (resolved from any
tile - ground or decoration - back to its owning biome) - see
world.weather_for_tile()/WEATHER_FOR_BIOME. Resolving through the biome name
first (rather than the exact tile id) means weather stays stable across a
whole region even when the player is standing on a decoration tile, not just
bare ground.
No server sync needed: every client derives its own weather from its own player's
position, so this stays cheap and never touches the authoritative simulation
(except for the one small real gameplay hook - snow/ice slowing movement - which
lives in world.SPEED_MULT instead, not here).
"""
import random
import pygame

from game import constants as C

MAX_PARTICLES = 35  # halved from 70 - user asked to cut down weather VFX load
_WEATHER_CAP = {"off": 0, "low": 14, "high": MAX_PARTICLES}
_particle_cap = MAX_PARTICLES  # options-menu particle level (game/settings.py)


def set_particle_level(level):
    global _particle_cap
    _particle_cap = _WEATHER_CAP.get(level, MAX_PARTICLES)


class WeatherFX:
    def __init__(self):
        self.kind = None
        self.particles = []  # [x, y, speed, length_or_radius]

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self.particles = []

    def update(self, dt, kind):
        self.set_kind(kind)
        if self.kind is None:
            self.particles = []
            return
        if len(self.particles) > _particle_cap:
            del self.particles[_particle_cap:]
        while len(self.particles) < _particle_cap:
            self.particles.append(self._spawn())
        for p in self.particles:
            self._advance(p, dt)

    def _spawn(self, y=None):
        x = random.uniform(0, C.SCREEN_W)
        y = random.uniform(-20, C.SCREEN_H) if y is None else y
        if self.kind == "rain":
            return [x, y, random.uniform(420, 560), random.uniform(8, 14)]
        if self.kind == "snow":
            return [x, y, random.uniform(30, 70), random.uniform(1, 3)]
        if self.kind == "sand":
            return [x, y, random.uniform(160, 260), random.uniform(1, 2)]
        if self.kind == "ash":
            return [x, y, random.uniform(20, 45), random.uniform(1, 3)]
        return [x, y, 0, 1]

    def _advance(self, p, dt):
        if self.kind == "rain":
            p[1] += p[2] * dt
            p[0] -= p[2] * 0.15 * dt
        elif self.kind == "snow":
            p[1] += p[2] * dt
            p[0] += 25 * pygame.math.Vector2(1, 0).rotate(p[1]).x * dt
        elif self.kind == "sand":
            p[0] -= p[2] * dt
            p[1] += p[2] * 0.08 * dt
        elif self.kind == "ash":
            p[1] += p[2] * dt
            p[0] += 15 * pygame.math.Vector2(1, 0).rotate(p[1] * 2).x * dt
        if p[1] > C.SCREEN_H + 10 or p[1] < -30 or p[0] < -20 or p[0] > C.SCREEN_W + 20:
            new = self._spawn(y=-10 if self.kind in ("rain", "snow", "ash") else None)
            p[:] = new

    def draw(self, surf):
        if self.kind is None:
            return
        if self.kind == "rain":
            col = (150, 180, 220, 140)
            for x, y, speed, length in self.particles:
                pygame.draw.line(surf, col[:3], (x, y), (x - 3, y - length), 1)
        elif self.kind == "snow":
            col = (240, 245, 250)
            for x, y, speed, r in self.particles:
                pygame.draw.circle(surf, col, (int(x), int(y)), int(r))
        elif self.kind == "sand":
            col = (196, 170, 100)
            for x, y, speed, r in self.particles:
                pygame.draw.circle(surf, col, (int(x), int(y)), int(r))
        elif self.kind == "ash":
            col = (120, 100, 90)
            for x, y, speed, r in self.particles:
                pygame.draw.circle(surf, col, (int(x), int(y)), int(r))


LABELS = {"rain": "Light rain", "snow": "Snowfall", "sand": "Sandstorm", "ash": "Ashfall"}

# Tactical hooks - one small, real gameplay effect per relevant weather kind,
# deliberately narrow (not a universal "weather slows everyone" change):
# a Tundra/Ice blizzard (snow) shrinks fog-of-war reveal range, a Desert/
# Wasteland sandstorm (sand) throws off soft aim assist. minimap.reveal()'s
# radius param and realm_sim.auto_aim_direction()'s cone_deg param both
# already accept an override at their call sites in main.py/coop_client.py -
# these two helpers compute that override from the current weather kind.
BLIZZARD_REVEAL_RADIUS_SCALE = 0.6
SANDSTORM_AIM_CONE_SCALE = 0.6


def reveal_radius_for(kind, base_radius):
    """Scales the minimap fog-of-war reveal radius for the current weather.
    Always returns an int - minimap.reveal() uses it directly as a range()
    bound, which raises TypeError on a float (e.g. 10 * 0.6 == 6.0)."""
    if kind == "snow":
        return round(base_radius * BLIZZARD_REVEAL_RADIUS_SCALE)
    return base_radius


def aim_cone_for(kind, base_cone_deg):
    """Scales the soft-aim-assist cone angle for the current weather."""
    if kind == "sand":
        return base_cone_deg * SANDSTORM_AIM_CONE_SCALE
    return base_cone_deg
