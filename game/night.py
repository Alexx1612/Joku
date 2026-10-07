"""
The night director (night-horror update): everything that makes the Realm's night
dangerous, run by RealmSim once per tick (open Realm only).

* Night rules - at night every hostile mob hunts harder: bigger aggro range (more so
  when its target stands outside every light), longer leash, faster, harder hits,
  quicker attacks. Restored at dawn.
* Night mobs (entities.NIGHT_MOB_KINDS) - spawned around players out of the light,
  gone at dawn:
    Lantern-Eater   walks to the nearest lit lamp and snuffs it until dawn
    Shade Stalker   only visible inside light (drawn as a shimmer + eyes outside it)
    Night Mimic     sits disguised as a loot bag until a player comes close
    Hollow Watcher  a rooted eye: seeing a player makes it shriek, waking the dark
* Night events - one per (non-Blood-Moon) night: The Fog, Something Is Hunting You,
  The Lanterns Go Out, Midnight Market.
* The Blood Moon - the big scary night (3 minutes): hordes ring every exposed player
  every BLOOD_HORDE_EVERY seconds, everything is moonlit and angrier still, and at the
  halfway mark The Red Harvester rises. Its kills roll the "blood_moon" loot source.

Pure sim logic: it only appends to the sim's events / vfx_events / sound_events and
its enemy list - clients learn about it through RealmSim.clock_info().
"""
import random

import pygame

from game.constants import TILE

# night rules: (aggro, aggro when the target is outside every light, leash, speed, damage, cooldown)
NIGHT_RULES = dict(aggro=1.6, aggro_dark=2.0, leash=1.5, speed=1.15, dmg=1.2, cd=0.85)
BLOOD_RULES = dict(aggro=2.2, aggro_dark=2.6, leash=2.0, speed=1.25, dmg=1.35, cd=0.75)
NIGHT_MOB_CAP = 3          # night mobs alive near one player (Blood Moon: x2)
NIGHT_SPAWN_EVERY = 7.0
NIGHT_SPAWN_WEIGHTS = {"shade_stalker": 40, "lantern_eater": 25, "night_mimic": 20, "hollow_watcher": 15}
LIGHT_SAFE_TILES = 4       # a spawn point never lands this close to a light
SNUFF_RADIUS = 44          # a Lantern-Eater this close to a lamp snuffs it
WATCHER_SHRIEK_CD = 20.0
WATCHER_CALL_RADIUS = 650
EVENTS = ("fog", "hunter", "lanterns_out", "market", "lamplighter")
EVENT_TEXT = {
    "fog": ("The Fog rolls in. You can barely see your own hands. Something else can.", (170, 180, 200)),
    "hunter": ("Something is hunting {name}. It won't stop until dawn - or until it's dead.", (210, 120, 255)),
    "lanterns_out": ("The Lanterns Go Out. Every lamp in the Realm gutters and dies.", (255, 170, 90)),
    "market": ("A bell rings somewhere far off: the Midnight Market is open in {place}.", (140, 230, 210)),
    "lamplighter": ("Old Wick the Lamplighter is out lighting lamps in {place} - and the dark has noticed. "
                    "Keep him alive till dawn.", (255, 214, 120)),
}
LAMPLIGHTER_HP = 420
LAMPLIGHTER_WAVE_EVERY = 24.0
LAMPLIGHTER_HELP_RADIUS = 900.0
FOG_LIGHT_MULT = 0.6
BLOOD_HORDE_EVERY = 30.0
BLOOD_HORDE_SIZE = (6, 10)
BLOOD_HORDE_RING = (11, 14)  # tiles from the player - a ring closing in from just off-screen
BLOOD_SURVIVOR_XP = 400


class NightDirector:
    def __init__(self, sim):
        self.sim = sim
        self.event = None          # tonight's event key (or "blood_moon")
        self.hunted_pid = None
        self.snuffed = set()       # (tx, ty) lamp tiles a Lantern-Eater put out (until dawn)
        self._spawn_cd = 3.0
        self._horde_cd = 8.0
        self._harvester_done = False
        self._night_t = 0.0
        self._was_night = False
        self.market_pos = None
        self._rule_mobs = set()
        self.ward = None  # the Lamplighter event: {"npc", "hp", "wave_cd", "helpers"}

    # ------------------------------------------------------------ queries --
    @property
    def lanterns_out(self):
        return self.event == "lanterns_out"

    def light_mult(self):
        """Player light radius multiplier tonight (The Fog shrinks it)."""
        return FOG_LIGHT_MULT if self.event == "fog" else 1.0

    def info(self):
        """The bits clients need (rides in RealmSim.clock_info)."""
        return {"event": self.event, "hunted": self.hunted_pid, "lanterns_out": self.lanterns_out,
                "light_mult": self.light_mult(), "snuffed": sorted(self.snuffed)[:200]}

    def _in_light(self, pos):
        sim = self.sim
        for (lx, ly, r, _c) in sim.light_sources_near(pos, 8):
            if (lx - pos.x) ** 2 + (ly - pos.y) ** 2 <= (r * 0.8) ** 2:
                return True
        return False

    # --------------------------------------------------------------- tick --
    def tick(self, dt, alive):
        sim = self.sim
        night = sim.is_night
        if night and not self._was_night:
            self._begin_night(alive)
        elif not night and self._was_night:
            self._end_night(alive)
        self._was_night = night
        self._apply_rules(night)
        if not night or not alive:
            return
        self._night_t += dt
        exposed = [p for p in alive if not getattr(p, "sheltered", False)]
        self._tick_spawns(dt, exposed)
        self._tick_behaviours(dt, alive)
        if self.ward is not None:
            self._tick_lamplighter(dt, alive)
        if sim.blood_moon_active:
            self._tick_blood_moon(dt, exposed, alive)

    # --------------------------------------------------------- night start --
    def _begin_night(self, alive):
        sim = self.sim
        self._night_t = 0.0
        self._harvester_done = False
        self._horde_cd = 10.0
        self.snuffed.clear()
        self.hunted_pid = None
        if sim.blood_moon_active:
            self.event = "blood_moon"
            sim.events.append((None, "The Blood Moon rises. Find a door and shut it - or fight until dawn.",
                               (235, 60, 60)))
            sim.sound_events.append(("sfx", "blood_moon_rise", *self._any_pos(alive)))
            return
        planned = (getattr(sim, "tonight", None) or {}).get("event")  # from the calendar (RealmSim.forecast)
        self.event = planned if planned in EVENTS else random.choice(EVENTS)
        if getattr(self, "force_event", None) in EVENTS:  # /nightevent (game/admin.py) beats the calendar
            self.event = self.force_event
        self.force_event = None
        text, col = EVENT_TEXT[self.event]
        place = "the Realm"
        if self.event == "hunter" and alive:
            victim = random.choice(alive)
            self.hunted_pid = victim.pid
            text = text.format(name=getattr(victim, "name", "someone"))
            self._spawn_hunter(victim)
        elif self.event == "market":
            place = self._open_market()
            text = text.format(place=place)
        elif self.event == "lamplighter":
            place = self._start_lamplighter()
            text = text.format(place=place)
        sim.events.append((None, text, col))
        sim.sound_events.append(("sfx", f"night_{self.event}", *self._any_pos(alive)))
        sim.sound_events.append(("sfx", "nightfall", *self._any_pos(alive)))

    def _end_night(self, alive):
        sim = self.sim
        if self.event == "blood_moon":
            for p in alive:
                p.gain_xp(BLOOD_SURVIVOR_XP)
                sim.events.append((p.pid, f"You survived the Blood Moon. +{BLOOD_SURVIVOR_XP} XP", (255, 200, 140)))
        if self.event == "market":
            sim.npcs = [n for n in sim.npcs if n.npc_id != "ghost_merchant"]
            self.market_pos = None
        if self.ward is not None:
            self._finish_lamplighter(alive)
        self.event = None
        self.hunted_pid = None
        self.snuffed.clear()
        sim.sound_events.append(("sfx", "dawn", *self._any_pos(alive)))

    def _any_pos(self, alive):
        if alive:
            return alive[0].pos.x, alive[0].pos.y
        return 0.0, 0.0

    # ------------------------------------------------------------ rules --
    def _apply_rules(self, night):
        sim = self.sim
        rules = BLOOD_RULES if (night and sim.blood_moon_active) else NIGHT_RULES if night else None
        for e in sim.enemies:
            if e.neutral or not e.alive:
                continue
            base = getattr(e, "_day_stats", None)
            if rules is None:
                if base is not None:
                    e.aggro_range, e.leash_range, e.speed, e.dmg, e.fire_rate_mult = base
                    e._day_stats = None
                continue
            if base is None:
                base = e._day_stats = (e.aggro_range, e.leash_range, e.speed, tuple(e.dmg), e.fire_rate_mult)
            dark = not getattr(e, "_target_in_light", False)
            e.aggro_range = base[0] * (rules["aggro_dark"] if dark else rules["aggro"])
            e.leash_range = base[1] * rules["leash"]
            e.speed = base[2] * rules["speed"]
            e.dmg = (max(1, int(round(base[3][0] * rules["dmg"]))), max(1, int(round(base[3][1] * rules["dmg"]))))
            e.fire_rate_mult = base[4] * rules["cd"]

    # --------------------------------------------------------- night mobs --
    def _spawn_point(self, p, lo=10, hi=20):
        sim = self.sim
        for _ in range(8):
            pos = sim._find_spawn_pos_near(p.pos, min_px=lo * TILE, max_px=hi * TILE,
                                           avoid_players=sim._story_players)
            if pos is None:
                continue
            if self._in_light(pos) or sim.is_sheltered_tile(pos):
                continue
            if any(a["rect"].collidepoint(int(pos.x // TILE), int(pos.y // TILE)) for a in sim.areas):
                continue  # towns stay a little safer
            return pos
        return None

    def _make(self, kind, pos):
        from game.entities import Enemy
        e = Enemy(kind, pos, level_scale=self.sim.story_scale)
        e.loot_source = "blood_moon" if self.sim.blood_moon_active else "night"
        if kind == "night_mimic":
            e._disguised = True
        if self.sim.blood_moon_active:
            e.moonlit = True
        self.sim.enemies.append(e)
        return e

    def _tick_spawns(self, dt, exposed):
        from game.entities import NIGHT_MOB_KINDS
        self._spawn_cd -= dt
        if self._spawn_cd > 0 or not exposed:
            return
        self._spawn_cd = NIGHT_SPAWN_EVERY * (0.6 if self.sim.blood_moon_active else 1.0)
        f = self.sim.danger_at(exposed[0].pos) if hasattr(self.sim, "danger_at") else None
        if f is not None:  # the heart of the Realm is busier after dark (x1.25 slower at the coast .. x0.75)
            self._spawn_cd *= 1.25 - 0.5 * f
        cap = NIGHT_MOB_CAP * (2 if self.sim.blood_moon_active else 1)
        weights = dict(NIGHT_SPAWN_WEIGHTS)
        if self.event == "fog":
            weights["shade_stalker"] *= 2
        if self.event == "lanterns_out":
            weights["lantern_eater"] *= 2
        kinds, w = list(weights), list(weights.values())
        for p in exposed:
            near = sum(1 for e in self.sim.enemies
                       if e.alive and e.kind in NIGHT_MOB_KINDS and e.pos.distance_to(p.pos) < 1100)
            if near >= cap:
                continue
            pos = self._spawn_point(p)
            if pos is not None:
                self._make(random.choices(kinds, weights=w)[0], pos)

    def _spawn_hunter(self, victim):
        pos = self._spawn_point(victim, 12, 22)
        if pos is None:
            return
        h = self._make("shade_stalker", pos)
        h.hp_max = h.hp = int(h.hp_max * 2.2)
        h.hunt_pid = victim.pid
        h.aggro = True
        h.loot_rank_override = "boss"

    def _tick_behaviours(self, dt, alive):
        sim = self.sim
        by_pid = {p.pid: p for p in alive}
        for e in sim.enemies:
            if not e.alive:
                continue
            k = e.kind
            if k == "lantern_eater":
                self._lantern_eater(e)
            elif k == "night_mimic" and getattr(e, "_disguised", False):
                if any(p.pos.distance_to(e.pos) < 75 for p in alive) or e.hp < e.hp_max:
                    e._disguised = False
                    e.aggro = True
                    sim.events.append((None, "The loot bag has TEETH.", (230, 120, 120)))
                    sim.vfx_events.append(("mimic_reveal", e.pos.x, e.pos.y, (200, 60, 80)))
                    sim.sound_events.append(("sfx", "mimic_snap", e.pos.x, e.pos.y))
            elif k == "hollow_watcher":
                e._shriek_cd = getattr(e, "_shriek_cd", 0.0) - dt
                if e._shriek_cd <= 0:
                    seen = next((p for p in alive if not getattr(p, "sheltered", False)
                                 and p.pos.distance_to(e.pos) < 460
                                 and sim.has_line_of_sight(e.pos.x, e.pos.y, p.pos.x, p.pos.y)), None)
                    if seen is not None:
                        e._shriek_cd = WATCHER_SHRIEK_CD
                        sim.events.append((None, "A Hollow Watcher SHRIEKS. Everything in the dark turns toward you.",
                                           (230, 80, 90)))
                        sim.sound_events.append(("sfx", "watcher_shriek", e.pos.x, e.pos.y))
                        sim.vfx_events.append(("boss_phase", e.pos.x, e.pos.y, (200, 40, 60)))
                        for o in sim.enemies:
                            if o.alive and not o.neutral and o.pos.distance_to(e.pos) < WATCHER_CALL_RADIUS:
                                o.aggro = True
            hunt = getattr(e, "hunt_pid", None)
            if hunt is not None:
                target = by_pid.get(hunt)
                if target is not None and not getattr(target, "sheltered", False):
                    e.aggro = True
        # who stands in light (the night rules hunt the ones in the dark harder)
        lit = {p.pid: self._in_light(p.pos) for p in alive}
        for e in sim.enemies:
            if e.alive and not e.neutral and alive:
                nearest = min(alive, key=lambda q: q.pos.distance_squared_to(e.pos))
                e._target_in_light = lit.get(nearest.pid, False)

    def _lantern_eater(self, e):
        sim = self.sim
        from game import world
        best, bd = None, 520.0
        for (lx, ly, _r, _c) in world.nearby_lights(sim.realm_map, e.pos.x, e.pos.y, 16, lit=not self.lanterns_out):
            t = (int(lx // TILE), int(ly // TILE))
            if t in self.snuffed:
                continue
            d = e.pos.distance_to((lx, ly))
            if d < bd:
                best, bd = (lx, ly, t), d
        if best is None:
            return
        if not e.aggro:
            e.home_pos = pygame.Vector2(best[0], best[1])  # it walks to the light
        if bd <= SNUFF_RADIUS + 30:
            self.snuffed.add(best[2])
            sim.vfx_events.append(("lamp_snuff", best[0], best[1], (255, 190, 90)))
            sim.sound_events.append(("sfx", "lantern_snuff", best[0], best[1]))

    # --------------------------------------------------------- the market --
    def _open_market(self):
        sim = self.sim
        from game import npcs as npcs_mod
        if not sim.areas:
            return "the Realm"
        a = random.choice(sim.areas)
        c = pygame.Vector2((a["rect"].centerx + 0.5) * TILE, (a["rect"].centery + 0.5) * TILE)
        pos = npcs_mod._walkable_near(sim.realm_map, c, 8)
        sim.npcs = [n for n in sim.npcs if n.npc_id != "ghost_merchant"]
        sim.npcs.append(npcs_mod.NPC("ghost_merchant", pos))
        self.market_pos = pos
        return a["name"]

    # ------------------------------------------------------ the Lamplighter --
    def _start_lamplighter(self):
        sim = self.sim
        from game import npcs as npcs_mod
        if not sim.areas:
            return "the Realm"
        a = random.choice(sim.areas)
        c = pygame.Vector2((a["rect"].centerx + 0.5) * TILE, (a["rect"].centery + 0.5) * TILE)
        n = npcs_mod.NPC("lamplighter", npcs_mod._walkable_near(sim.realm_map, c, 8))
        n.hp_frac = 1.0
        sim.npcs = [q for q in sim.npcs if q.npc_id != "lamplighter"] + [n]
        self.ward = {"npc": n, "hp": float(LAMPLIGHTER_HP), "wave_cd": 12.0, "helpers": set(), "area": a["name"]}
        return a["name"]

    def _tick_lamplighter(self, dt, alive):
        sim, w = self.sim, self.ward
        n = w["npc"]
        if w["hp"] <= 0:
            return
        for p in alive:
            if p.pos.distance_to(n.pos) < LAMPLIGHTER_HELP_RADIUS:
                w["helpers"].add(p.pid)
        # he relights snuffed lamps as he passes them
        for t in list(self.snuffed):
            if pygame.Vector2((t[0] + 0.5) * TILE, (t[1] + 0.5) * TILE).distance_to(n.pos) < 3 * TILE:
                self.snuffed.discard(t)
        # the dark sends waves at him
        w["wave_cd"] -= dt
        if w["wave_cd"] <= 0:
            w["wave_cd"] = LAMPLIGHTER_WAVE_EVERY
            from game.entities import Enemy
            for i in range(4 if not sim.blood_moon_active else 6):
                ang = 360.0 * i / 4 + random.uniform(-20, 20)
                pos = n.pos + pygame.Vector2(1, 0).rotate(ang) * random.uniform(10, 14) * TILE
                if sim.is_solid(pos.x, pos.y):
                    continue
                kind = random.choice(("shade_stalker", "lantern_eater", "shade_stalker"))
                e = self._make(kind, pos)
                e.ward_target = True
                e.aggro = True
            sim.events.append((None, "Shapes close in on the Lamplighter!", (255, 190, 110)))
        # mobs that reach him (or hit him) hurt him
        hurt = 0.0
        for e in sim.enemies:
            if e.alive and not e.neutral and e.pos.distance_to(n.pos) < 34:
                hurt += 14.0 * dt
        keep = []
        for b in sim.bullets:
            if b.owner == "enemy" and b.pos.distance_to(n.pos) < 16:
                hurt += b.dmg
                continue
            keep.append(b)
        sim.bullets = keep
        if hurt:
            w["hp"] -= hurt
            n.hp_frac = max(0.0, w["hp"] / LAMPLIGHTER_HP)
        if w["hp"] <= 0:
            n.hp_frac = 0.0
            sim.events.append((None, "Old Wick the Lamplighter has fallen. The lamps go dark one by one...",
                               (230, 120, 110)))
            sim.npcs = [q for q in sim.npcs if q is not n]
            sim.vfx_events.append(("lamp_snuff", n.pos.x, n.pos.y, (255, 190, 90)))

    def _finish_lamplighter(self, alive):
        sim, w = self.sim, self.ward
        self.ward = None
        sim.npcs = [q for q in sim.npcs if q.npc_id != "lamplighter"]
        if w["hp"] <= 0:
            return
        from game.items import make_rdv_ring
        for p in alive:
            if p.pid not in w["helpers"]:
                continue
            ring = make_rdv_ring()
            if not p.try_pickup(ring):
                bag2 = getattr(p, "backpack2", None)
                if bag2 is not None and len(bag2) < getattr(p, "backpack2_size", 12):
                    bag2.append(ring)
                elif getattr(p, "sidequests", None) is not None:
                    p.sidequests.pending_items.append(ring)
            sim.events.append((p.pid, "Dawn. Old Wick presses a warm ring into your hand: the Light of RDV!",
                               (255, 224, 140)))
            sim.vfx_events.append(("divine_drop", p.pos.x, p.pos.y, (255, 224, 140)))
            sim.sound_events.append(("sfx", "trial_done", p.pos.x, p.pos.y))

    # ------------------------------------------------------ the Blood Moon --
    def _tick_blood_moon(self, dt, exposed, alive):
        sim = self.sim
        self._horde_cd -= dt
        if self._horde_cd <= 0 and exposed:
            self._horde_cd = BLOOD_HORDE_EVERY
            for p in exposed:
                self._horde(p)
        from game import realm_sim as rs
        half = (rs.NIGHT_END - rs.NIGHT_START) / rs.BLOOD_MOON_NIGHT_SPEED / 2
        if not self._harvester_done and self._night_t >= half and alive:
            self._harvester_done = True
            target = max(alive, key=lambda q: (getattr(getattr(q, "story", None), "act", 0), q.level))
            pos = self._spawn_point(target, 8, 14) or pygame.Vector2(target.pos) + pygame.Vector2(260, 0)
            from game.entities import Enemy
            h = Enemy("red_harvester", pos, level_scale=sim.story_scale)
            h.loot_source = "blood_moon"
            h.moonlit = True
            h.aggro = True
            sim.enemies.append(h)
            sim.events.append((None, "The Red Harvester rises under the Blood Moon. It has come for the harvest.",
                               (255, 50, 60)))
            sim.vfx_events.append(("boss_appear", pos.x, pos.y, (230, 30, 40)))
            sim.sound_events.append(("sfx", "harvester_roar", pos.x, pos.y))

    def _horde(self, p):
        sim = self.sim
        from game import realm_sim as rs
        from game.entities import Enemy, ENEMY_KINDS
        ground = sim.realm_map.tile_at(p.pos.x, p.pos.y)
        sets = rs.BIOME_LAIR_KIND_SETS.get(ground) or [(list(rs.ENEMY_POOL), list(rs.ENEMY_WEIGHTS))]
        pool = [k for kinds, _w in sets for k in kinds if not ENEMY_KINDS.get(k, {}).get("neutral")]
        if not pool:
            return
        n = random.randint(*BLOOD_HORDE_SIZE)
        for i in range(n):
            ang = 360.0 * i / n + random.uniform(-12, 12)
            dist = random.uniform(*BLOOD_HORDE_RING) * TILE
            pos = p.pos + pygame.Vector2(1, 0).rotate(ang) * dist
            if sim.is_solid(pos.x, pos.y) or sim.is_sheltered_tile(pos):
                continue
            e = Enemy(random.choice(pool), pos, level_scale=sim.story_scale * 1.3)
            e.moonlit = True
            e.aggro = True
            e.loot_source = "blood_moon"
            e.blood_horde = True
            sim.enemies.append(e)
        sim.vfx_events.append(("horde_ring", p.pos.x, p.pos.y, (220, 40, 50)))
        sim.events.append((p.pid, "The Blood Moon sends its horde.", (235, 70, 70)))
