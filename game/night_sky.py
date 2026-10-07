"""
The night sky and what lives under it (night realism pass 2) - the simulation side:

- Night weather: each normal night rolls clear / cloudy / rain / storm. Clouds hide the moon and
  darken the night, rain dims every light a little, and a storm throws lightning that lights the
  whole screen for a moment (with thunder).
- Shooting stars streak over clear nights; now and then one falls to the ground as a glowing
  Star Fragment (use it: extra loot chance until dawn).
- Night-blooming herbs (Moonpetal in forest / highlands, Ghostbloom in swamp / jungle) glow in
  the dark and can only be gathered at night (F).
- Owls perch in the trees at night, hoot, and fly off when you come close.

RealmSim owns one NightSky (sim.sky) and ticks it; clients get sky_info() inside clock_info.
The client-side drawing lives in game/sky_fx.py.
"""
import math
import random

import pygame

from game.constants import TILE

NIGHT_WEATHER = (("clear", 45), ("cloudy", 25), ("rain", 18), ("storm", 12))
WEATHER_TEXT = {
    "cloudy": ("Clouds roll in over the moon. It's going to be a dark one.", (170, 180, 205)),
    "rain": ("It starts to rain. Lamps hiss and dim.", (150, 180, 220)),
    "storm": ("A storm rolls in. Thunder, somewhere close.", (200, 205, 255)),
}
CLOUD_DARK = {"clear": 1.0, "cloudy": 0.72, "rain": 0.62, "storm": 0.55}  # x the night's ambient light
WEATHER_LIGHT_MULT = {"rain": 0.85, "storm": 0.8}  # x every player's light radius
LIGHTNING_EVERY = (6.0, 16.0)
LIGHTNING_RANGE = 12 * TILE
STAR_EVERY = 16.0          # a chance at a shooting star this often on a clear night
STAR_CHANCE = 0.4
STAR_FALL_CHANCE = 0.3     # ...and the chance that one actually lands
STAR_FALL_RING = (14, 28)  # tiles from a player
STAR_LIGHT = (150, (200, 220, 255))
HERBS_PER_PLAYER = 3
HERB_GROUNDS = {"moonpetal": ("forest", "highlands"), "ghostbloom": ("swamp", "jungle")}
HERB_PICK_RADIUS = 46
OWLS_PER_PLAYER = 2
OWL_BIOMES = ("forest", "highlands", "tundra", "jungle", "swamp")
OWL_SPOOK_RADIUS = 130
OWL_FLY_SPEED = 230
OWL_FLY_TIME = 2.6
SPAWN_EVERY = 3.0
NEAR = 900


def _dir_word(v):
    """'north' / 'south-east' / ... for an offset (screen y grows south)."""
    ang = math.degrees(math.atan2(-v.y, v.x)) % 360
    names = ("east", "north-east", "north", "north-west", "west", "south-west", "south", "south-east")
    return names[int((ang + 22.5) // 45) % 8]


class NightSky:
    def __init__(self, sim):
        self.sim = sim
        self.weather = "clear"
        self._was_night = False
        self._bolt_cd = random.uniform(*LIGHTNING_EVERY)
        self.bolt = None        # [seq, x, y] - the latest lightning strike
        self._bolt_seq = 0
        self._star_cd = STAR_EVERY * 0.5
        self.star = None        # [seq, angle, fall] - the latest shooting star
        self._star_seq = 0
        self.fallen = []        # [{"pos": Vector2, "bag": Bag}] - glowing star fragments on the ground
        self._spawn_cd = 0.0

    # ------------------------------------------------------------ queries --
    def ambient_mult(self):
        return CLOUD_DARK.get(self.weather, 1.0)

    def light_mult(self):
        return WEATHER_LIGHT_MULT.get(self.weather, 1.0)

    def info(self):
        return {"sky": self.weather, "bolt": self.bolt, "star": self.star,
                "sky_dark": self.ambient_mult()}

    def lights(self):
        """Fallen star fragments still lying on the ground glow."""
        alive = []
        for f in self.fallen:
            if f["bag"] in self.sim.ground_items and f["bag"].items:
                alive.append(f)
        self.fallen = alive
        return [(f["pos"].x, f["pos"].y, STAR_LIGHT[0], STAR_LIGHT[1]) for f in alive]

    # ------------------------------------------------------------ ticking --
    def tick(self, dt, alive):
        sim = self.sim
        night = sim.is_night
        if night and not self._was_night:
            self._begin_night(alive)
        elif not night and self._was_night:
            if self.weather != "clear" and alive:
                sim.events.append((None, "The weather clears with the dawn.", (220, 210, 170)))
            self.weather = "clear"
        self._was_night = night
        if not night or not alive:
            return
        if self.weather == "storm":
            self._bolt_cd -= dt
            if self._bolt_cd <= 0:
                self._bolt_cd = random.uniform(*LIGHTNING_EVERY)
                self._strike(random.choice(alive))
        if self.weather == "clear" and not sim.blood_moon_active:
            self._star_cd -= dt
            if self._star_cd <= 0:
                self._star_cd = STAR_EVERY
                if random.random() < STAR_CHANCE:
                    self._shooting_star(alive)
        self._spawn_cd -= dt
        if self._spawn_cd <= 0:
            self._spawn_cd = SPAWN_EVERY
            self._spawn_herbs(alive)
            self._spawn_owls(alive)
        self._tick_owls(dt, alive)

    def _begin_night(self, alive):
        sim = self.sim
        if sim.blood_moon_active:
            self.weather = "clear"  # the Blood Moon owns the sky
            return
        kinds, weights = zip(*NIGHT_WEATHER)
        planned = (getattr(sim, "tonight", None) or {}).get("weather")  # from the calendar
        self.weather = planned if planned in kinds else random.choices(kinds, weights)[0]
        if getattr(self, "force_weather", None) in CLOUD_DARK:  # /weather (game/admin.py) beats the calendar
            self.weather = self.force_weather
        self.force_weather = None
        if self.weather in WEATHER_TEXT:
            text, col = WEATHER_TEXT[self.weather]
            sim.events.append((None, text, col))
            if alive:
                p = alive[0]
                sim.sound_events.append(("sfx", "thunder" if self.weather == "storm" else "rain_start",
                                         p.pos.x, p.pos.y))

    def _strike(self, p):
        sim = self.sim
        pos = p.pos + pygame.Vector2(1, 0).rotate(random.uniform(0, 360)) * random.uniform(3 * TILE, LIGHTNING_RANGE)
        self._bolt_seq += 1
        self.bolt = [self._bolt_seq, round(pos.x), round(pos.y)]
        sim.sound_events.append(("sfx", "thunder", pos.x, pos.y))
        sim.vfx_events.append(("lightning", pos.x, pos.y, (220, 225, 255)))

    def _shooting_star(self, alive, fall=None):
        sim = self.sim
        self._star_seq += 1
        if fall is None:  # (/star forces it - game/admin.py)
            fall = random.random() < STAR_FALL_CHANCE and len(self.fallen) < 2
        ang = random.uniform(15, 50) * random.choice((1, -1))
        self.star = [self._star_seq, round(ang, 1), 1 if fall else 0]
        p = random.choice(alive)
        sim.sound_events.append(("sfx", "shooting_star", p.pos.x, p.pos.y))
        if not fall:
            return
        pos = None
        for _ in range(20):
            cand = p.pos + pygame.Vector2(1, 0).rotate(random.uniform(0, 360)) * \
                random.uniform(*STAR_FALL_RING) * TILE
            if not sim.is_solid(cand.x, cand.y) and sim.realm_map.tile_at(cand.x, cand.y) is not None:
                pos = cand
                break
        if pos is None:
            return
        from game.items import make_star_fragment
        before = list(sim.ground_items)
        sim._spawn_loot_bag([("white", make_star_fragment())], pos)
        bag = next((b for b in sim.ground_items if b not in before), None)
        if bag is not None:
            self.fallen.append({"pos": pygame.Vector2(bag.pos), "bag": bag})
        sim.vfx_events.append(("star_land", pos.x, pos.y, STAR_LIGHT[1]))
        for q in alive:
            sim.events.append((q.pid, f"A shooting star falls to the ground - {_dir_word(pos - q.pos)} of you!",
                               (205, 225, 255)))

    # --------------------------------------------------- herbs and owls --
    def _count_near(self, kind, p):
        return sum(1 for e in self.sim.enemies if e.kind == kind and e.alive and e.pos.distance_to(p.pos) < NEAR)

    def _spawn_herbs(self, alive):
        sim = self.sim
        from game.entities import Enemy
        for p in alive:
            have = self._count_near("moonpetal", p) + self._count_near("ghostbloom", p)
            if have >= HERBS_PER_PLAYER:
                continue
            pos = sim._find_spawn_pos_near(p.pos, min_px=7 * TILE, max_px=24 * TILE, avoid_players=alive,
                                           safe_px=5 * TILE)
            if pos is None:
                continue
            biome = sim._biome_at(pos)
            kind = next((k for k, bs in HERB_GROUNDS.items() if biome in bs), None)
            if kind is None:
                continue
            e = Enemy(kind, pos)
            e.home_pos = pygame.Vector2(pos)
            sim.enemies.append(e)

    def _spawn_owls(self, alive):
        sim = self.sim
        from game.entities import Enemy
        for p in alive:
            if self._count_near("owl", p) >= OWLS_PER_PLAYER:
                continue
            pos = sim._find_spawn_pos_near(p.pos, min_px=8 * TILE, max_px=20 * TILE, avoid_players=alive,
                                           safe_px=6 * TILE)
            if pos is None or sim._biome_at(pos) not in OWL_BIOMES:
                continue
            e = Enemy("owl", pos)
            e.home_pos = pygame.Vector2(pos)
            e._hoot_cd = random.uniform(4, 18)
            sim.enemies.append(e)

    def _tick_owls(self, dt, alive):
        sim = self.sim
        for e in sim.enemies:
            if e.kind != "owl" or not e.alive:
                continue
            fly = getattr(e, "_flying", None)
            if fly is None:
                near = min(alive, key=lambda q: q.pos.distance_squared_to(e.pos))
                if near.pos.distance_to(e.pos) < OWL_SPOOK_RADIUS:
                    away = e.pos - near.pos
                    away = away.normalize() if away.length_squared() > 1 else pygame.Vector2(0, -1)
                    e._flying = [away.rotate(random.uniform(-25, 25)), 0.0]
                    sim.sound_events.append(("sfx", "owl_flap", e.pos.x, e.pos.y))
                    continue
                e._hoot_cd = getattr(e, "_hoot_cd", 10.0) - dt
                if e._hoot_cd <= 0:
                    e._hoot_cd = random.uniform(14, 30)
                    sim.sound_events.append(("sfx", "owl", e.pos.x, e.pos.y))
            else:
                d, t = fly
                fly[1] = t + dt
                e.pos += d * OWL_FLY_SPEED * dt  # flying - walls don't matter
                if fly[1] >= OWL_FLY_TIME:
                    e.alive = False
        sim.enemies = [e for e in sim.enemies if e.alive or e.kind != "owl"]

    def gather_herb(self, player):
        """F next to a night herb: pick it."""
        sim = self.sim
        best, bd = None, HERB_PICK_RADIUS
        for e in sim.enemies:
            if e.alive and e.kind in HERB_GROUNDS:
                d = e.pos.distance_to(player.pos)
                if d <= bd:
                    best, bd = e, d
        if best is None:
            return False
        from game import items as I
        it = I.make_moonpetal() if best.kind == "moonpetal" else I.make_ghostbloom()
        best.alive = False
        sim.enemies = [e for e in sim.enemies if e is not best]
        if not player.try_pickup(it):
            sim._spawn_loot_bag([("brown", it)], best.pos, owner_pid=player.pid)
            sim.events.append((player.pid, f"You pick a {it.name} - your bags are full, it's on the ground.",
                               (200, 230, 255)))
        else:
            sim.events.append((player.pid, f"You pick a {it.name}. It glows in your hand.", (200, 230, 255)))
        sim.vfx_events.append(("herb_pick", best.pos.x, best.pos.y,
                               (170, 210, 255) if best.kind == "moonpetal" else (150, 255, 200)))
        sim.sound_events.append(("sfx", "herb_pick", best.pos.x, best.pos.y))
        sim._side_event(player, "herb", best.kind, 1, {})
        return True
