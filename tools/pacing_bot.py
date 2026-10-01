"""
Headless pacing bot: plays the 7-act story through the REAL game objects and
reports how long each act takes in simulated minutes.

    python tools/pacing_bot.py --cls wizard --seed 1
    python tools/pacing_bot.py --runs "wizard,warrior,archer,priest" --seeds 1,2

What is real: RealmSim (open Realm, dungeons, Heroic dungeons, islands, the Forge),
enemy AI + attacks, bullets, damage, XP, loot rolls, the story/side-quest/dialogue/
forge code. Combat is stepped at DT seconds per tick with the bot auto-aiming
(sim.player_fire), kiting to its weapon's reach, side-stepping incoming bullets,
casting its ability and fleeing at low HP.

What is simplified:
  * long travel is a "teleport-walk": the player is placed at the destination and
    distance / walk speed x TRAVEL_DETOUR is added to the clock (enemies at the
    destination still fight back for real)
  * a trip to the Nexus (the Anvil / Bitterwick) costs NEXUS_TRIP seconds
  * death: counted, then the bot respawns at full HP after DEATH_PENALTY seconds
    (a human would reroll - permadeath - but that measures luck, not pacing)
  * an objective with no progress for STUCK_AFTER simulated seconds is force-credited
    and reported as "stuck"
"""
import argparse
import math
import os
import random
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("RR_NO_MUSIC", "1")
os.environ.setdefault("RR_EVENT_ROTATION", "off")

import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((64, 64))

from game import accounts, characters, achievements  # noqa: E402

accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_bot_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_bot_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_bot_ach_")

from game import story, sidequests, dialogue, npcs as npcs_mod, gates, forge, world  # noqa: E402
from game import realm_sim as rs  # noqa: E402
from game.realm_sim import RealmSim, DUNGEON_THEMES, THEME_FOR_KIND, FORGE_DIFFICULTY  # noqa: E402
from game.entities import Player, ENEMY_KINDS  # noqa: E402
from game.constants import TILE  # noqa: E402
from game import items as I  # noqa: E402

DT = 1 / 20
TRAVEL_DETOUR = 1.35
NEXUS_TRIP = 90.0
DEATH_PENALTY = 60.0
STUCK_AFTER = 20 * 60.0
FIGHT_RADIUS = 520.0
LOOT_RADIUS = 260.0


def _power_throttle_off():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
        import _timing
        _timing.disable_power_throttling()
    except Exception:
        pass


class Stuck(Exception):
    pass


class Bot:
    def __init__(self, cls_name, seed, verbose=False):
        random.seed(seed)
        self.verbose = verbose
        self.cls = cls_name
        self.p = Player(cls_name, f"Bot{seed}", pid="bot")
        self.p.story = story.StoryProgress(0)
        self.p.sidequests = sidequests.SideQuestProgress()
        self.realm = RealmSim(story_act=0)
        self.p.pos = self.realm.spawn_point()
        self.clock = 0.0
        self.deaths = 0
        self.stuck = []
        self.act_times = {}
        self._act_started = 0.0
        self._strafe = 1
        self._strafe_t = 0.0
        self._push_on = 0.0  # > 0: walk the path even with enemies around (stalled at a gate / wall)
        self._loot_t = 0.0
        self._obj_key = None
        self._obj_since = 0.0
        self.forges = 0
        self.dungeon_minutes = []
        self.dungeons = {"normal": 0, "heroic": 0}
        self.reach = self._measure_reach()

    # ----------------------------------------------------------------- utils --
    def log(self, *a):
        if self.verbose:
            print(f"[{self.clock / 60:6.1f}m L{self.p.level:2d} A{self.p.story.act}]", *a, flush=True)

    def _measure_reach(self):
        made = self.realm.player_fire(self.p, pygame.Vector2(1, 0))
        reach = max((b.vel.length() * b.life for b in made), default=300.0)
        for b in made:
            if b in self.realm.bullets:
                self.realm.bullets.remove(b)
        return reach

    def travel(self, sim, pos):
        pos = pygame.Vector2(pos)
        d = self.p.pos.distance_to(pos)
        self.clock += d / max(1.0, self.p.speed()) * TRAVEL_DETOUR
        self.p.pos = npcs_mod._walkable_near(sim.realm_map, pos, max_r=20)
        self.p.fishing_state = None

    def bounds(self, sim):
        return (0, 0, sim.realm_map.w * TILE, sim.realm_map.h * TILE)

    # --------------------------------------------------------------- combat --
    def hostiles(self, sim, radius=FIGHT_RADIUS):
        p = self.p
        return [e for e in sim.enemies if e.alive and not e.neutral and e.pos.distance_to(p.pos) <= radius]

    def step(self, sim, goal=None, prefer=None):
        """One DT tick: move (kite / dodge / flee / walk to goal), shoot, cast, sim.update."""
        p = self.p
        near = self.hostiles(sim)
        cands = [e for e in near if prefer is None or prefer(e)] or near
        target = min(cands, key=lambda e: e.pos.distance_squared_to(p.pos)) if cands else None
        move = pygame.Vector2(0, 0)
        self._push_on = max(0.0, self._push_on - DT)
        mover = None if (self._push_on > 0 and goal is not None) else target
        self._strafe_t -= DT
        if self._strafe_t <= 0:
            self._strafe, self._strafe_t = -self._strafe, random.uniform(0.8, 2.0)
        if mover is not None:
            to = mover.pos - p.pos
            d = to.length() or 1.0
            u = to / d
            want = self.reach * 0.7
            if p.hp < p.hp_max * 0.3:
                move = -u + u.rotate(90) * 0.5 * self._strafe
            elif d > want:
                move = u + u.rotate(90) * 0.3 * self._strafe
            elif d < want * 0.5:
                move = -u + u.rotate(90) * 0.6 * self._strafe
            else:
                move = u.rotate(90) * self._strafe
        elif goal is not None:
            to = pygame.Vector2(goal) - p.pos
            if to.length_squared() > 16:
                move = to
        # side-step the nearest incoming enemy bullet
        best = None
        for b in sim.bullets:
            if b.owner != "enemy":
                continue
            rel = p.pos - b.pos
            if rel.length_squared() > 110 * 110 or b.vel.length_squared() < 1:
                continue
            if rel.dot(b.vel) <= 0:
                continue
            if best is None or rel.length_squared() < best[0]:
                best = (rel.length_squared(), b)
        if best is not None:
            v = best[1].vel.normalize()
            side = v.rotate(90)
            if side.dot(p.pos - best[1].pos) < 0:
                side = -side
            move = move * 0.4 + side * 1.2
        if move.length_squared() > 0:
            move = move.normalize()
        p.net_update(DT, move, self.bounds(sim), is_solid=sim.is_solid)
        if target is not None and p.weapon is not None and p.can_fire():
            d = target.pos.distance_to(p.pos)
            if d <= self.reach * 1.05:
                p.register_fire()
                sim.player_fire(p, (target.pos - p.pos).normalize())
        elif target is None and p.weapon is not None and p.can_fire() and sim.obstacles:
            # nothing to fight: break any crate / rubble wall in the way
            obs = [o for o in sim.obstacles if o.alive and o.pos.distance_to(p.pos) < max(90, self.reach)]
            if obs:
                ob = min(obs, key=lambda o: o.pos.distance_to(p.pos))
                p.register_fire()
                sim.player_fire(p, (ob.pos - p.pos).normalize() if ob.pos != p.pos else pygame.Vector2(1, 0))
        ab = p.ability
        if ab is not None and p.ability_cd <= 0 and p.mp >= ab.mp_cost:
            if ab.effect in ("heal", "shield") and p.hp < p.hp_max * 0.6:
                sim.use_ability(p, p.pos, [p])
            elif ab.effect == "haste" and target is not None:
                sim.use_ability(p, p.pos, [p])
            elif ab.effect in ("nova", "chain", "drain", "freeze") and target is not None \
                    and target.pos.distance_to(p.pos) < 260:
                sim.use_ability(p, target.pos, [p])
        sim.begin_tick()
        sim.update(DT, {p.pid: p})
        self.clock += DT
        self._loot_t -= DT
        if self._loot_t <= 0:
            self._loot_t = 1.0
            self.loot(sim)
        if not p.alive or p.hp <= 0:
            self.deaths += 1
            self.log("died")
            p.alive = True
            p.hp, p.mp = p.hp_max, p.mp_max
            self.clock += DEATH_PENALTY
            if sim.is_bonus_room:
                p.pos = sim.spawn_point()
        self.check_stuck()

    def fight_until(self, sim, done, cap, goal=None, prefer=None):
        t0 = self.clock
        while not done():
            if self.clock - t0 > cap:
                return False
            self.step(sim, goal=goal() if callable(goal) else goal, prefer=prefer)
        self.sweep(sim)
        return True

    def sweep(self, sim, secs=15.0):
        """After a kill: walk over to the nearby bags (still fighting anything that's close) and pick them up."""
        t0 = self.clock
        while self.clock - t0 < secs:
            bags = [b for b in sim.ground_items if b.pos.distance_to(self.p.pos) < 900 and b.items
                    and getattr(b, "owner_pid", None) in (None, self.p.pid)]
            if not bags:
                break
            bag = min(bags, key=lambda b: b.pos.distance_to(self.p.pos))
            if bag.pos.distance_to(self.p.pos) < LOOT_RADIUS:
                self.loot(sim)
                continue
            if self.hostiles(sim, 220):
                self.step(sim)
            else:  # nothing close: just walk there
                self.step(sim, goal=bag.pos, prefer=lambda e: False)
                self._walk(sim, bag.pos)
        self.loot(sim)

    def _walk(self, sim, pos):
        d = self.p.pos.distance_to(pos)
        if d > LOOT_RADIUS * 0.8:
            self.clock += (d - LOOT_RADIUS * 0.5) / max(1.0, self.p.speed())
            self.p.pos = pygame.Vector2(pos)

    # ------------------------------------------------------------ inventory --
    def _value(self, it):
        if it is None:
            return -1
        if it.divine:
            return 20
        if it.is_ut:
            return 10.5
        return it.tier

    def loot(self, sim):
        p = self.p
        for bag in list(sim.ground_items):
            if bag.pos.distance_to(p.pos) > LOOT_RADIUS:
                continue
            if getattr(bag, "owner_pid", None) not in (None, p.pid):
                continue
            for it in list(bag.items):
                bag.items.remove(it)
                self.take(it)
            if not bag.items:
                sim.ground_items.remove(bag)

    def take(self, it):
        p = self.p
        if it.slot == I.SLOT_SHARD or it.slot == I.SLOT_MATERIAL or it.quest_key:
            self.log("picked up", it.name)
        if it.slot == "consumable":
            p.backpack.append(it)
            if not p.use_potion(len(p.backpack) - 1):
                p.backpack.pop()
            return
        if it.slot in (I.SLOT_WEAPON, I.SLOT_ARMOR, I.SLOT_RING, I.SLOT_ABILITY):
            cur = getattr(p, it.slot)
            if self._value(it) > self._value(cur):
                setattr(p, it.slot, it)
                if cur is not None:
                    self._stash(cur)
                return
        self._stash(it)

    def _keep_score(self, it):
        if it.slot in (I.SLOT_SHARD, "quest", I.SLOT_MATERIAL):
            return 1000
        if it.slot in (I.SLOT_WEAPON, I.SLOT_ARMOR, I.SLOT_RING, I.SLOT_ABILITY) and not it.is_ut and not it.divine:
            same = sum(1 for b in self.p.backpack if b.slot == it.slot and b.tier == it.tier and not b.is_ut)
            return it.tier + 10 * same  # items that complete a forge triple are worth more
        if it.is_ut:
            return 12
        return 0

    def _stash(self, it):
        p = self.p
        p.backpack.append(it)
        while len(p.backpack) > p.backpack_size:
            worst = min(p.backpack, key=self._keep_score)
            p.backpack.remove(worst)

    # ------------------------------------------------------------- stuck --
    def check_stuck(self):
        sp = self.p.story
        act = sp.current()
        if act is None:
            return
        key = (sp.act, tuple(sorted((k, len(v)) for k, v in sp.done.items())))
        if key != self._obj_key:
            self._obj_key, self._obj_since = key, self.clock
            return
        if self.clock - self._obj_since > STUCK_AFTER:
            raise Stuck()

    def force_next(self):
        sp = self.p.story
        act = sp.current()
        for o in act["objectives"]:
            if sp._count(o) < o["need"]:
                keys = o["keys"] or [f"forced{i}" for i in range(o["need"])]
                for k in keys:
                    if sp._count(o) >= o["need"]:
                        break
                    sp.on_event(o["kind"], k if o["keys"] else None)
                self.stuck.append(f"act{sp.act if sp.current() is act else sp.act - 1}:{o['id']}")
                break
        self._obj_key, self._obj_since = None, self.clock

    # ------------------------------------------------------------ objectives --
    def next_objective(self):
        """The first unfinished objective that can be worked on right now (e.g. forge as soon
        as a recipe exists, a dungeon as soon as a shard is in the bag), else the first unfinished one."""
        sp = self.p.story
        act = sp.current()
        if act is None:
            return None
        todo = [o for o in act["objectives"] if sp._count(o) < o["need"]]
        for o in todo:
            if self._actionable(o):
                return o
        return todo[0] if todo else None

    def _actionable(self, o):
        k = o["kind"]
        if k == "forge":
            return bool(forge.forge_options(self.p))
        if k == "dungeon":
            return bool(self._shards(heroic=False))
        if k == "heroic_dungeon":
            return self.p.level >= gates.HEROIC_LEVEL and bool(self._shards(heroic=True))
        if k == "heroic_unlock":
            t = self._trial()
            return (t is not None and self.p.sidequests.ready(t[1], self.p)) or                 (t is not None and any(x.shard_theme == t[0] for x in self._shards(heroic=False))) or                 (t is None and bool(self._shards(heroic=False)))
        if k == "equip_tier":
            return False
        return True

    def run(self, cap_minutes=400):
        sp = self.p.story
        last_act = sp.act
        self._act_started = 0.0
        while not sp.finished and self.clock < cap_minutes * 60:
            o = self.next_objective()
            try:
                self.do(o)
            except Stuck:
                self.log("STUCK on", o["id"])
                self.force_next()
            if sp.act != last_act:
                for a in range(last_act, sp.act):
                    self.act_times[a] = self.act_times.get(a, 0.0) + (self.clock - self._act_started)
                    self._act_started = self.clock
                self.log("-> act", sp.act, story.ACTS[sp.act]["title"] if sp.act < story.FINAL_ACT else "done")
                last_act = sp.act
        return self

    def do(self, o):
        k = o["kind"]
        getattr(self, "obj_" + k)(o)

    # prologue
    def obj_talk(self, o):
        self.clock += 20
        self.p.story.on_event("talk")

    def obj_zone(self, o):
        self.clock += 10
        self.p.story.on_event("zone", "realm")

    # Act I - the Grand Tour
    def obj_area(self, o):
        seen = set(self.p.story.done.get(o["id"], []))
        cands = [a for a in self.realm.areas if a["key"] not in seen]
        a = min(cands, key=lambda a: self.p.pos.distance_to(pygame.Vector2(a["rect"].center) * TILE))
        self.travel(self.realm, pygame.Vector2(a["rect"].center) * TILE)
        self._settle(self.realm, 3.0)

    def obj_landmark(self, o):
        seen = set(self.p.story.done.get(o["id"], []))
        cands = [lm for lm in self.realm.landmarks if lm["biome"] in o["keys"] and lm["biome"] not in seen]
        lm = min(cands, key=lambda lm: self.p.pos.distance_to(lm["pos"]))
        self.travel(self.realm, lm["pos"] + pygame.Vector2(4 * TILE, 0))
        self._settle(self.realm, 3.0)

    def _settle(self, sim, secs):
        """Stand (and fight whatever is here) for a moment - side-quest / story ticks run."""
        sim._near_cd = 0
        t0 = self.clock
        while self.clock - t0 < secs or self.hostiles(sim, 300):
            self.step(sim)
            if self.clock - t0 > 240:
                break

    def obj_npc(self, o):
        seen = set(self.p.story.done.get(o["id"], []))
        cands = [n for n in self.realm.npcs if n.npc_id not in seen]
        n = min(cands, key=lambda n: self.p.pos.distance_to(n.pos))
        self.travel(self.realm, n.pos + pygame.Vector2(40, 0))
        self._settle(self.realm, 1.0)
        dialogue.start_conversation(self.p, npc=n)
        self.clock += 20

    def obj_fish(self, o):
        sim = self.realm
        self.travel(sim, sim.spawn_point())
        # find a spot next to the water
        for r in range(0, 30):
            if sim._near_water(self.p.pos):
                break
            self.p.pos += pygame.Vector2(0, TILE)
        while len(self.p.backpack) >= self.p.backpack_size:
            self.p.backpack.remove(min(self.p.backpack, key=self._keep_score))
        t0 = self.clock
        while self.p.story.wants("fish") and self.clock - t0 < 300:
            if self.p.fishing_state is None or self.p.fishing_state.get("phase") == "biting":
                sim.fish_action(self.p)
            self.step(sim)

    # combat acts
    def obj_guardian(self, o):
        sp = self.p.story
        seen = set(sp.done.get(o["id"], []))
        biomes = [b for b in (o["keys"] or story.OUTER_BIOMES) if b not in seen]
        lm = min((lm for lm in self.realm.landmarks if lm["biome"] in biomes),
                 key=lambda lm: self.p.pos.distance_to(lm["pos"]))
        self.gear_up_for(story.act_scale(sp.act))
        self.travel(self.realm, lm["pos"] + pygame.Vector2(2 * TILE, 0))
        biome = lm["biome"]
        before = len(sp.done.get(o["id"], []))

        def done():
            return len(sp.done.get(o["id"], [])) > before or sp.current() is None \
                or o not in sp.current()["objectives"]
        self.fight_until(self.realm, done, 8 * 60, goal=lm["pos"],
                         prefer=lambda e: getattr(e, "story_guardian", None) == biome)

    def gear_up_for(self, _scale):
        pass  # the bot equips upgrades as it loots; nothing extra to do here

    # dungeons
    def _shards(self, heroic=None):
        out = [it for it in self.p.backpack if it.slot == I.SLOT_SHARD and it.shard_theme != rs.MAD_GOD_ROOM]
        if heroic is True:
            out = [it for it in out if it.shard_theme.startswith("heroic_")]
        elif heroic is False:
            out = [it for it in out if not it.shard_theme.startswith("heroic_")]
        return out

    def run_dungeon(self, theme, difficulty):
        ok, msg = gates.can_enter(self.p, theme)
        if not ok:
            return False
        sim = RealmSim(bonus=True, theme=theme, difficulty_name=difficulty, story_act=self.p.story.act)
        back = pygame.Vector2(self.p.pos)
        self.p.pos = sim.spawn_point()
        path = self._path(sim, sim.spawn_point(), sim.boss.pos)
        wp = [0]

        stall = {"wp": -1, "t": self.clock}

        def goal():
            while wp[0] < len(path) and self.p.pos.distance_to(path[wp[0]]) < 40:
                wp[0] += 1
            if wp[0] != stall["wp"]:
                stall["wp"], stall["t"] = wp[0], self.clock
            elif self.clock - stall["t"] > 45 and wp[0] < len(path):
                # navigation simplification (like the overworld teleport-walk): a long stall means the
                # bot's crude pathing is stuck on a gate/corner - step to the next waypoints, break any
                # rubble gate there, and pay the time a player would spend doing that by hand
                nxt = path[min(len(path) - 1, wp[0] + 3)]
                for ob in getattr(sim, "obstacles", ()):
                    if ob.alive and ob.pos.distance_to(nxt) < 120:
                        ob.alive = False
                self.clock += 10 + self.p.pos.distance_to(nxt) / max(1.0, self.p.speed())
                self.p.pos = pygame.Vector2(nxt)
                stall["t"] = self.clock
            elif wp[0] >= len(path) and sim.boss is not None and self.clock - stall["t"] > 45:
                # at the end of the path but the boss wandered off: walk to it
                self.clock += self.p.pos.distance_to(sim.boss.pos) / max(1.0, self.p.speed())
                self.p.pos = sim.boss.pos + (self.p.pos - sim.boss.pos).normalize() * 200                     if self.p.pos != sim.boss.pos else pygame.Vector2(sim.boss.pos)
                stall["t"] = self.clock
            elif self.clock - stall["t"] > 6 and wp[0] < len(path) and self.p.weapon is not None                     and self.p.can_fire():
                # no waypoint progress for a while: a rubble gate is in the way - shoot along the path
                to = path[wp[0]] - self.p.pos
                if to.length_squared() > 1:
                    self.p.register_fire()
                    sim.player_fire(self.p, to.normalize())
                    self._push_on = 2.0
            if wp[0] >= len(path) and sim.boss is not None:
                return sim.boss.pos
            return path[min(wp[0], len(path) - 1)] if path else None
        boss_kind = sim.boss.kind
        t_in = self.clock
        won = False
        try:
            won = self.fight_until(sim, lambda: sim.boss is None, 20 * 60, goal=goal)
            self.loot(sim)
        finally:
            self.dungeon_minutes.append((self.clock - t_in) / 60)
            extra = ""
            if not won and sim.boss is not None:
                extra = (f" (boss hp {sim.boss.hp / sim.boss.hp_max:.0%}, "
                         f"dist {self.p.pos.distance_to(sim.boss.pos):.0f}, kills {sim.kill_count}, "
                         f"wp {wp[0]}/{len(path)})")
            self.log(f"dungeon {theme} [{difficulty}] boss {boss_kind}: {'cleared' if won else 'gave up'}{extra}")
            self.p.pos = back
            self.p.hp = max(self.p.hp, 1)
            self.clock += 20  # portal in/out
            self.dungeons["heroic" if sim.is_heroic else "normal"] += int(won)
        return won

    def _path(self, sim, a, b):
        """BFS over walkable tiles (dungeon maps are small): list of waypoint world positions."""
        grid = sim.realm_map
        sx, sy = int(a.x // TILE), int(a.y // TILE)
        gx, gy = int(b.x // TILE), int(b.y // TILE)
        from collections import deque
        prev = {(sx, sy): None}
        q = deque([(sx, sy)])
        while q:
            c = q.popleft()
            if c == (gx, gy):
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n in prev or not (0 <= n[0] < grid.w and 0 <= n[1] < grid.h):
                    continue
                wx, wy = n[0] * TILE + TILE / 2, n[1] * TILE + TILE / 2
                if grid.is_solid(wx, wy):
                    continue
                prev[n] = c
                q.append(n)
        if (gx, gy) not in prev:
            return [pygame.Vector2(b)]
        out = []
        c = (gx, gy)
        while c is not None:
            out.append(pygame.Vector2(c[0] * TILE + TILE / 2, c[1] * TILE + TILE / 2))
            c = prev[c]
        out.reverse()
        return out[::3] + [out[-1]]

    def use_a_shard(self, prefer_theme=None, heroic=False):
        shards = self._shards(heroic=heroic)
        if prefer_theme:
            pref = [s for s in shards if s.shard_theme == prefer_theme]
            shards = pref or ([] if heroic else shards)
        if not shards:
            return False
        s = shards[0]
        self.p.backpack.remove(s)
        diff = rs.shard_difficulty(s.shard_theme)
        return self.run_dungeon(s.shard_theme, diff) or True

    def farm(self, theme=None, secs=180):
        """Kill Realm lairs (elites drop Dungeon Shards / gear / XP) - near-ish lairs whose
        kinds open `theme` if given, else the toughest lairs the bot can handle."""
        kinds = {k for k, t in THEME_FOR_KIND.items() if t == theme} if theme else None
        def hostile(l):
            return l.get("island_camp") is None and not all(ENEMY_KINDS[k].get("neutral") for k in l["kinds"])
        lairs = [l for l in self.realm.lairs if hostile(l) and (kinds is None or kinds & set(l["kinds"]))]
        if not lairs:
            lairs = [l for l in self.realm.lairs if hostile(l)]
        lair = random.choice(sorted(lairs, key=lambda l: self.p.pos.distance_to(l["pos"]))[:6])
        self.log("farm", theme or "any", "lair", lair["kinds"][:3], "shards", [x.shard_theme for x in self._shards()])
        self.travel(self.realm, lair["pos"])
        t0 = self.clock
        while self.clock - t0 < secs:
            self.step(self.realm, goal=lair["pos"])

    def obj_dungeon(self, o):
        if not self.use_a_shard(heroic=False):
            self.farm(secs=150)

    def obj_equip_tier(self, o):
        self.realm._near_cd = 0
        self._settle(self.realm, 1.0)
        if not self.p.story.wants("equip_tier"):
            return
        if not self.use_a_shard(heroic=False):
            self.farm(secs=150)

    def obj_forge(self, o):
        if forge.forge_options(self.p):
            self.clock += NEXUS_TRIP
            while True:
                conv = dialogue.start_conversation(self.p, npc=npcs_mod.NPC("hammerstein", pygame.Vector2(0, 0)))
                if not conv.view()["options"][0].startswith(("Temper", "Reforge")):
                    break
                conv.choose(0)
                self.forges += 1
                self.clock += 5
            self.reequip()
            self.log("forged, now", [b.display_name for b in self.p.backpack])
            return
        if not self.use_a_shard(heroic=False):
            self.farm(secs=150)

    def reequip(self):
        for it in list(self.p.backpack):
            if it.slot in (I.SLOT_WEAPON, I.SLOT_ARMOR, I.SLOT_RING, I.SLOT_ABILITY) and                     self._value(it) > self._value(getattr(self.p, it.slot)):
                self.p.backpack.remove(it)
                self.take(it)

    def _trial(self):
        """The active (or best) Heroic trial: (theme, qid, giver, relic)."""
        sq = self.p.sidequests
        for theme, (qid, giver, relic, _l) in sidequests.HEROIC_TRIALS.items():
            if qid in sq.active:
                return theme, qid, giver, relic
        return None

    def _talk(self, npc_id, pick):
        """Travel to an NPC (Realm or Nexus) and pick the first option that `pick` accepts."""
        n = next((n for n in self.realm.npcs if n.npc_id == npc_id), None)
        if n is None:
            self.clock += NEXUS_TRIP
            n = npcs_mod.NPC(npc_id, pygame.Vector2(0, 0))
        else:
            self.travel(self.realm, n.pos + pygame.Vector2(40, 0))
            self.clock += 20
        conv = dialogue.start_conversation(self.p, npc=n)
        opts = conv.view()["options"]
        idx = next((i for i, lab in enumerate(opts) if pick(lab)), None)
        if idx is not None:
            conv.choose(idx)
        return conv

    def obj_heroic_unlock(self, o):
        t = self._trial()
        if t is None:
            themes = [s.shard_theme for s in self._shards(heroic=False)
                      if s.shard_theme in sidequests.HEROIC_TRIALS]
            if not themes:
                self.farm(secs=150)
                return
            theme = max(set(themes), key=themes.count)
            qid, giver, relic, label = sidequests.HEROIC_TRIALS[theme]
            conv = self._talk(giver, lambda lab: lab.startswith("Heroic trial"))
            conv.choose(0)  # I'll do it!
            self.log("accepted", qid)
            return
        theme, qid, giver, relic = t
        if self.p.sidequests.ready(qid, self.p):
            self._talk(giver, lambda lab: lab.startswith("I've done"))
            self.log("trial turned in", qid)
            return
        if not self.use_a_shard(prefer_theme=theme):
            self.farm(theme=theme, secs=150)

    def obj_heroic_dungeon(self, o):
        if self.p.level < gates.HEROIC_LEVEL:
            if not self.use_a_shard(heroic=False):
                self.farm(secs=150)
            return
        if self.use_a_shard(heroic=True):
            return
        # no Heroic Shard: Hard clears of an unlocked theme can drop one
        unlocked = [t for t in sidequests.HEROIC_TRIALS if sidequests.heroic_unlocked(self.p.sidequests, t)]
        if not unlocked:
            self.obj_heroic_unlock(o)
            return
        if not self.use_a_shard(prefer_theme=None, heroic=False):
            self.farm(theme=random.choice(unlocked), secs=150)

    def obj_island(self, o):
        if self.p.level < gates.ISLAND_LEVEL:
            if not self.use_a_shard(heroic=True) and not self.use_a_shard(heroic=False):
                self.farm(secs=150)
            return
        sp = self.p.story
        done = set(sp.done.get(o["id"], []))
        isl = min((i for i in self.realm.islands if i["idx"] not in done),
                  key=lambda i: self.p.pos.distance_to(i["pos"]))
        self.travel(self.realm, isl["pos"] + pygame.Vector2(0, 3 * TILE))
        before = len(sp.done.get(o["id"], []))

        def calmed():
            return len(sp.done.get(o["id"], [])) > before or sp.current() is None \
                or o not in sp.current()["objectives"]
        self.fight_until(self.realm, calmed, 10 * 60, goal=isl["pos"],
                         prefer=lambda e: getattr(e, "island_idx", None) == isl["slot"])

    def obj_mad_god(self, o):
        self.clock += NEXUS_TRIP
        sim = RealmSim(bonus=True, theme="forge", difficulty_name=FORGE_DIFFICULTY, story_act=self.p.story.act)
        back = pygame.Vector2(self.p.pos)
        self.p.pos = sim.spawn_point()
        path = self._path(sim, sim.spawn_point(), sim.boss.pos)
        wp = [0]

        stall = {"wp": -1, "t": self.clock}

        def goal():
            while wp[0] < len(path) and self.p.pos.distance_to(path[wp[0]]) < 40:
                wp[0] += 1
            if wp[0] != stall["wp"]:
                stall["wp"], stall["t"] = wp[0], self.clock
            elif self.clock - stall["t"] > 45 and wp[0] < len(path):
                # navigation simplification (like the overworld teleport-walk): a long stall means the
                # bot's crude pathing is stuck on a gate/corner - step to the next waypoints, break any
                # rubble gate there, and pay the time a player would spend doing that by hand
                nxt = path[min(len(path) - 1, wp[0] + 3)]
                for ob in getattr(sim, "obstacles", ()):
                    if ob.alive and ob.pos.distance_to(nxt) < 120:
                        ob.alive = False
                self.clock += 10 + self.p.pos.distance_to(nxt) / max(1.0, self.p.speed())
                self.p.pos = pygame.Vector2(nxt)
                stall["t"] = self.clock
            elif wp[0] >= len(path) and sim.boss is not None and self.clock - stall["t"] > 45:
                # at the end of the path but the boss wandered off: walk to it
                self.clock += self.p.pos.distance_to(sim.boss.pos) / max(1.0, self.p.speed())
                self.p.pos = sim.boss.pos + (self.p.pos - sim.boss.pos).normalize() * 200                     if self.p.pos != sim.boss.pos else pygame.Vector2(sim.boss.pos)
                stall["t"] = self.clock
            elif self.clock - stall["t"] > 6 and wp[0] < len(path) and self.p.weapon is not None                     and self.p.can_fire():
                # no waypoint progress for a while: a rubble gate is in the way - shoot along the path
                to = path[wp[0]] - self.p.pos
                if to.length_squared() > 1:
                    self.p.register_fire()
                    sim.player_fire(self.p, to.normalize())
                    self._push_on = 2.0
            if wp[0] >= len(path) and sim.boss is not None:
                return sim.boss.pos
            return path[min(wp[0], len(path) - 1)]
        try:
            self.fight_until(sim, lambda: self.p.story.finished, 25 * 60, goal=goal)
        finally:
            self.p.pos = back


def play(cls_name, seed, verbose=False):
    t0 = time.time()
    bot = Bot(cls_name, seed, verbose=verbose).run()
    return dict(cls=cls_name, seed=seed, acts=bot.act_times, total=bot.clock, finished=bot.p.story.finished,
                level=bot.p.level, deaths=bot.deaths, stuck=bot.stuck, forges=bot.forges,
                dungeons=dict(bot.dungeons), wall=time.time() - t0,
                gear={s: (getattr(bot.p, s).display_name if getattr(bot.p, s) else "-")
                      for s in ("weapon", "armor", "ring", "ability")})


def _fmt(r):
    acts = " ".join(f"{a}:{r['acts'].get(a, 0) / 60:5.1f}" for a in range(story.FINAL_ACT))
    return (f"{r['cls']:<11} seed {r['seed']}: total {r['total'] / 60:6.1f} min | {acts} | L{r['level']} "
            f"deaths {r['deaths']} dungeons {r['dungeons']} forges {r['forges']} stuck {r['stuck'] or '-'} "
            f"| wall {r['wall']:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cls", default="wizard")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--runs", default=None, help="comma-separated classes; with --seeds")
    ap.add_argument("--seeds", default="1,2")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    _power_throttle_off()
    if not a.runs:
        r = play(a.cls, a.seed, a.verbose)
        print(_fmt(r))
        return
    results = []
    for cls_name in a.runs.split(","):
        for seed in (int(s) for s in a.seeds.split(",")):
            r = play(cls_name.strip(), seed, a.verbose)
            print(_fmt(r), flush=True)
            results.append(r)
    print("\nper act (simulated minutes, median / min / max):")
    for i in range(story.FINAL_ACT):
        v = [r["acts"].get(i, 0) / 60 for r in results]
        print(f"  {story.ACTS[i]['title']:<28} {statistics.median(v):6.1f} {min(v):6.1f} {max(v):6.1f}")
    tot = [r["total"] / 60 for r in results]
    print(f"  {'TOTAL':<28} {statistics.median(tot):6.1f} {min(tot):6.1f} {max(tot):6.1f}")
    print(f"  finished {sum(r['finished'] for r in results)}/{len(results)}, "
          f"stuck: {[s for r in results for s in r['stuck']] or 'none'}")


if __name__ == "__main__":
    main()
