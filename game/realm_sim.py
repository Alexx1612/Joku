"""
Shared realm simulation core.

Both the single-player Game (main.py) and the co-op server (server.py)
drive one of these per active realm instance. Keeping the enemy AI /
loot / boss-trigger / mob-portal logic in exactly one place means co-op
and single-player can never silently drift apart into two different games.

A RealmSim knows nothing about pygame input or rendering - it is fed a
dict of {pid: Player} each tick and produces (a) mutated world state the
caller draws, and (b) a list of "events" (feed messages) for that tick.
"""
import math
import random

import pygame

from game import world
from game import achievements
from game import vfx
from game.entities import (Enemy, Bag, Portal, Obstacle, _mk_bullet, RANK_XP, BOSS_KINDS, BAG_MERGE_RADIUS,
                            BAG_MERGE_WINDOW, find_nearby_bag as _find_nearby_bag, bag_by_id as _bag_by_id,
                            withdraw_from_bag as _withdraw_from_bag)
from game.items import (roll_loot, BAG_COLOR_FOR, _random_tiered, _random_egg, _random_ut, make_potion,
                         make_dungeon_shard, UT_WEAPONS, STAT_KEYS)
from game.constants import TIER_COLORS, TILE
from game.audio import sound_family  # pure classification lookup, no pygame.mixer side effects -
# safe to use here even though this module is shared with the (headless) co-op server

ENEMY_POOL = ["imp", "bat", "ghost", "skeleton", "goblin", "scorpion", "yeti", "troll", "harpy", "salamander",
              "panther", "ghoul", "frost_wraith", "cave_lurker",
              "thornling", "dune_stalker", "frost_sprite", "bog_crawler", "cliff_strider",
              "cinder_wisp", "vine_serpent", "husk_wanderer", "glacier_shard", "deep_stalker"]
ENEMY_WEIGHTS = [16, 12, 7, 5, 14, 6, 3, 3, 7, 6, 6, 5, 5, 5,
                 4, 4, 4, 4, 4, 4, 4, 4, 4, 4]
MOB_PORTAL_CHANCE = 0.08  # elite kills have this chance to open a bonus-room portal

AUTO_AIM_CONE_DEG = 16
AUTO_AIM_RANGE = 520

# Class balance constants (see player_fire) - grounded against the real RotMG
# wiki: Archer is mid-pack DPS there (tied 5th of the roster), not top, so
# 3.0 brings this project's measured ~88 DPS multi-shot down to ~29 - right at
# the average of Wizard/Warrior/Rogue's own measured DPS (~17/38/32) instead
# of above all of them. Priest's wands pierce by default in real RotMG (not
# gated behind a rare UT like Wizard/Necromancer keep here), so PRIEST_PIERCE
# is always-on.
ARCHER_MULTISHOT_DMG_DIVISOR = 3.0
PRIEST_PIERCE = 2
PRIEST_HEAL_ON_HIT = 3       # HP restored to nearby allies per Priest hit (tiered weapons)
PRIEST_HEAL_RADIUS = 90      # smaller than SUPPORT_RADIUS - a passive combat trickle, not a full heal spell

# one existing UT per class gets the new boomerang projectile motion (see
# entities.Bullet) - a genuine new projectile TYPE, not just a new look.
# Picked as the 2nd UT in each class's list; the specific choice is arbitrary,
# the mechanic is what matters here (visual redesign is the art session's job)
BOOMERANG_UT_NAMES = {cls_name: uts[1][0] for cls_name, uts in UT_WEAPONS.items()}

# the other 3 UTs per class (indices 0/2/3) each get their own status effect on
# hit, via the exact same "match by name" pattern as the boomerang pick above -
# so all 4 UTs per class end up mechanically distinct, not just the boomerang one.
BLEED_UT_NAMES = {cls_name: uts[0][0] for cls_name, uts in UT_WEAPONS.items()}
BURN_UT_NAMES = {cls_name: uts[2][0] for cls_name, uts in UT_WEAPONS.items()}
VULNERABLE_UT_NAMES = {cls_name: uts[3][0] for cls_name, uts in UT_WEAPONS.items()}

BLEED_DURATION = 4.0
BLEED_DPS_FRACTION = 0.35     # bleed ticks for this fraction of the triggering hit's own damage, per second
BURN_DURATION = 3.0
BURN_DPS_FRACTION = 0.45      # shorter, harder-hitting DoT than bleed - reads as a different effect, not a
# recolor of the same number, even though the underlying mechanism (Enemy.bleed_time/burn_time) is identical
VULNERABLE_DURATION = 5.0
VULNERABLE_MULT = 1.3         # incoming damage multiplier while vulnerable_time > 0 (see Enemy.take_damage) -
# the "armor pierce" UT proc reinterpreted, since enemies have no DEF stat to actually reduce

# ambient wildlife (unshootable, never aggros - see entities.ENEMY_KINDS' unshootable flag) -
# "run away if you shoot near them": any PLAYER bullet within FLEE_TRIGGER_RADIUS of one
# triggers a flee state for FLEE_DURATION, checked once per tick in RealmSim.update()
FLEE_DURATION = 3.0
FLEE_TRIGGER_RADIUS = 60

# neutral mobs are physically pushable - "walk into a peaceful animal and it
# glides away" (see RealmSim.update's player-contact block) - a short,
# decelerating shove distinct from FLEE_* above (that's a reaction to being
# shot AT from a distance; this is a direct physical bump).
PUSH_DURATION = 0.5
PUSH_SPEED = 260
# aggressive mobs also get nudged on contact now (alongside their normal
# damage, not instead of it) - a smaller/shorter shove than the neutral-mob
# one above, reading as a minor knockback rather than a way to juggle a real
# enemy around. The player itself never gains any push state, under any
# circumstance - Player has no push fields and take_damage() never moves
# self.pos, so there is nothing to "turn off" to keep this one-directional.
AGGRO_PUSH_DURATION = 0.3
AGGRO_PUSH_SPEED = 130

# ---------------------------------------------------------- day/night cycle --
# Only the open Realm has a sky - bonus dungeons are always torch-lit. A full
# cycle is short enough to actually see both within one play session; nights
# are genuinely more dangerous (faster spawns, and a rare Blood Moon that ramps
# both danger and reward), not just a screen filter.
DAY_LENGTH = 240.0
BLOOD_MOON_CHANCE = 0.12  # rolled once each time night falls
MOONLIT_CHANCE = 0.10     # each night spawn has this chance to be a tougher "Moonlit" variant

# --------------------------------------------------------------------- fishing --
FISH_RANGE = 2.0          # tiles from a WATER tile you can cast from
FISH_CAST_TIME = (1.5, 3.0)
FISH_BITE_WINDOW = 1.0
FISH_COOLDOWN = 5.0


def auto_aim_direction(origin, raw_dir, enemies, cone_deg=AUTO_AIM_CONE_DEG, max_range=AUTO_AIM_RANGE):
    """
    Snaps a raw mouse-aim direction onto the nearest enemy within a narrow
    cone in front of it, if any - a soft aim-assist rather than full
    auto-targeting, so manual aim still matters but near-misses still land.
    Used identically by single-player (main.py) and the co-op client so
    aim assist behaves the same in both modes.
    """
    if raw_dir.length_squared() < 1e-6 or not enemies:
        return raw_dir
    raw_n = raw_dir.normalize()
    cos_thresh = math.cos(math.radians(cone_deg))
    best, best_dist = None, None
    for e in enemies:
        to_e = e.pos - origin
        dist = to_e.length()
        if dist < 1 or dist > max_range:
            continue
        if raw_n.dot(to_e / dist) >= cos_thresh and (best is None or dist < best_dist):
            best, best_dist = e, dist
    if best is None:
        return raw_n
    return (best.pos - origin).normalize()

# The open realm is explored, not treadmilled: enemies live in fixed "lairs"
# scattered across the map and are ALL populated up-front when the realm is
# created, so wandering the continent finds monsters immediately instead of
# waiting for a proximity trigger to spawn them in. Lairs are also kept a
# minimum distance from the arrival point so you're never ambushed the
# instant you step off the beach.
LAIR_COUNT = 200  # scaled up for the 900x900 continent (was 16 on the original small island,
# 160 on the old 800x800 one) - kept proportional to map AREA (900x900 is 1.27x the
# tile area of 800x800, and 160*1.27=~200) so lair density per tile stays about the
# same as the map grows, instead of the world feeling emptier at a bigger size.
# Deliberately NOT scaled further to match 1200x1200/1600x1600-sized lair counts
# (which would be ~360/~640): _spawn_enemy_lair()'s eligible-lair scan recounts each
# lair's live enemies with a full pass over self.enemies, so its cost is
# O(lair_count * enemy_count) - benchmarking that scan at the larger, area-scaled
# lair counts showed it spiking to 22ms (1200x1200) and over 100ms (1600x1600) per
# call, i.e. a real multi-frame stutter at the 30Hz co-op tick budget (33ms/tick)
# every time a lair needs to replenish. At LAIR_COUNT=200/cap=800 that same scan
# measured ~6.6ms - comfortably inside budget - which is the actual reason the
# realm didn't grow past 900x900 net of both the generation-time AND the sim-cost
# constraints, not just generation time alone.
MIN_LAIR_DIST_FROM_SPAWN = 730  # scaled with REALM_W/REALM_H (was 650 @ 800x800) so the
# "no lairs near spawn" ring stays the same fraction of the continent
LAIR_CAP = 4
REALM_ENEMY_CAP = LAIR_COUNT * LAIR_CAP  # a hard ceiling on total live enemies at once
# Minecraft-mob-spawner-style trickle: a lair that's lost enemies to combat does NOT
# instantly refill while you're camping right on top of it - it only starts trickling
# replacements back, one at a time, once no player is within LAIR_RESPAWN_SIGHT_RANGE,
# no faster than once per LAIR_RESPAWN_INTERVAL seconds per lair.
LAIR_RESPAWN_SIGHT_RANGE = 700
LAIR_RESPAWN_INTERVAL = 5.0
# Profiled: Enemy.update() (movement/wander/aggro/firing) is ~79% of RealmSim.update()'s
# total cost with the continent's ~800 pre-populated enemies, REGARDLESS of whether any
# player is anywhere near most of them - ticking (and rendering) enemies nobody is close
# to is pure waste. Any enemy farther than this from every player is left fully dormant
# (no update() call at all) for that tick - a bit bigger than a screen diagonal so nothing
# visibly "wakes up" right at the edge of view.
ACTIVE_SIM_RADIUS = 1600
# a fresh respawn (replacing a killed enemy) still won't drop in on top of a player
MIN_SPAWN_DIST_FROM_PLAYER = 140
LAIR_KIND_SETS = [
    (["imp"], [1]), (["bat"], [1]), (["ghost"], [1]), (["skeleton"], [1]),
    (["imp", "bat"], [55, 45]), (["ghost", "skeleton"], [50, 50]),
    (ENEMY_POOL, ENEMY_WEIGHTS),
]
# each biome is its own little ecosystem with TWO signature elites (a different
# bullet/movement pattern each - see entities.ENEMY_KINDS) plus the generic
# trash it shares with the rest of the continent - anything not covered below
# falls back to the generic mix above
BIOME_LAIR_KIND_SETS = {
    world.GRASS: [(["goblin"], [1]), (["thornling"], [1]), (["goblin", "imp"], [65, 35]),
                  (["goblin", "bat"], [60, 40]), (["thornling", "goblin"], [55, 45]),
                  (["forest_hare"], [1]), (["songbird"], [1]), (["deer"], [1])],  # ambient wildlife
    world.SAND: [(["scorpion"], [1]), (["dune_stalker"], [1]), (["imp"], [1]),
                 (["imp", "scorpion"], [50, 50]), (["dune_stalker", "scorpion"], [55, 45]),
                 (["desert_lizard"], [1])],  # ambient wildlife
    world.SNOW: [(["yeti"], [1]), (["frost_sprite"], [1]), (["ghost"], [1]),
                 (["ghost", "yeti"], [55, 45]), (["frost_sprite", "yeti"], [55, 45]),
                 (["deer"], [1])],  # ambient wildlife
    world.SWAMP: [(["troll"], [1]), (["bog_crawler"], [1]), (["skeleton"], [1]),
                  (["skeleton", "troll"], [55, 45]), (["bog_crawler", "troll"], [55, 45]),
                  (["marsh_heron"], [1])],  # ambient wildlife
    world.STONE: [(["harpy"], [1]), (["cliff_strider"], [1]), (["harpy", "bat"], [60, 40]),
                  (["cliff_strider", "harpy"], [55, 45]), (["deer"], [1])],  # ambient wildlife
    world.ASH: [(["salamander"], [1]), (["cinder_wisp"], [1]), (["salamander", "imp"], [60, 40]),
                (["cinder_wisp", "salamander"], [55, 45])],
    world.JUNGLE: [(["panther"], [1]), (["vine_serpent"], [1]), (["panther", "goblin"], [55, 45]),
                   (["vine_serpent", "panther"], [55, 45]), (["songbird"], [1])],  # ambient wildlife
    world.WASTELAND: [(["ghoul"], [1]), (["husk_wanderer"], [1]), (["ghoul", "skeleton"], [55, 45]),
                       (["husk_wanderer", "ghoul"], [55, 45]),
                       (["desert_lizard"], [1])],  # ambient wildlife
    world.ICE: [(["frost_wraith"], [1]), (["glacier_shard"], [1]), (["frost_wraith", "yeti"], [55, 45]),
                (["glacier_shard", "frost_wraith"], [55, 45])],
    world.CAVE: [(["cave_lurker"], [1]), (["deep_stalker"], [1]), (["cave_lurker", "bat"], [60, 40]),
                 (["deep_stalker", "cave_lurker"], [55, 45]),
                 (["cave_moth"], [1])],  # ambient wildlife
}

# "The Reforging" storyline: 10 small standalone island zones (see
# RealmSim._stamp_islands/world.stamp_island), 5 "shard" (land-shattered,
# charged-rubble/echo-construct) + 5 "choir" (drowned temple, coral/pearl),
# alternating placement around the map. Deliberately separate from
# BIOME_LAIR_KIND_SETS - these guardian kinds only ever spawn via an island
# flare/song event (_tick_island_events), never randomly in the wild.
ISLAND_THEMES = {
    "island_shard": {
        "guardians": ["ember_wisp", "fury_shard", "rubble_crawler", "spite_spirit",
                       "shard_sentinel", "echo_knight", "shattered_golem",
                       "fracture_hound", "stone_revenant"],
        "anchor": "cinder_warden",
        "color": (255, 140, 40),
        "verb": "flaring",
    },
    "island_choir": {
        "guardians": ["tide_wisp", "pearl_acolyte", "brine_crawler", "abyssal_chorister",
                       "coral_sentinel", "drowned_custodian", "kelp_stalker",
                       "shellback_guardian", "siren_wraith"],
        "anchor": "choir_warden",
        "color": (90, 200, 210),
        "verb": "singing",
    },
}
ISLAND_NAMES = ["Emberfall Shard", "Coral Choir", "Frostbite Shard", "Pearlsong Spire",
                "Bonewaste Shard", "Tideglass Sanctum", "Thornrock Shard",
                "Driftbell Cloister", "Ashenreach Shard", "Abyssal Hymnal"]
ISLAND_QUEST_INTERVAL = 300.0  # 5 minutes, per island independently
ISLAND_WAVE_SIZE = 4           # guardians per flare/song wave, always including that theme's anchor mob

# Bonus rooms (mob-death portals) come in three difficulty tiers - RotMG-style
# "vault"/dungeon difficulty, at v0 scale: tougher enemies and a richer loot
# roll, weighted so Easy is the common case and Hard is a rare, worthwhile risk.
BONUS_DIFFICULTIES = [
    {"name": "Easy", "weight": 55, "enemy_scale": 1.15, "cap": 10, "loot_rolls": 1},
    {"name": "Medium", "weight": 32, "enemy_scale": 1.6, "cap": 13, "loot_rolls": 2},
    {"name": "Hard", "weight": 13, "enemy_scale": 2.3, "cap": 16, "loot_rolls": 3},
]

# Dungeon themes ("try to make more dungeons for each mob to drop almost"): which
# enemy dropped the mob-portal decides which themed dungeon it leads into - its
# own floor tile, its own signature enemy roster (instead of the generic
# continent-wide mix), and its own boss pool, so a Cave Warren actually looks
# and plays differently from a Frozen Crypt instead of being the same room with
# a different coat of paint. THEME_FOR_KIND maps a portal-dropping enemy's kind
# to the theme its portal opens into; anything not listed falls back to "generic".
DUNGEON_THEMES = {
    "generic": dict(label="Forgotten Vault", floor=world.GRASS2, wall=world.WALL_VAULT,
                     kinds=ENEMY_POOL, weights=ENEMY_WEIGHTS, bosses=BOSS_KINDS),
    "cave": dict(label="Cave Warren", floor=world.CAVE, wall=world.WALL_CAVE,
                  kinds=["cave_lurker", "bat", "ghoul", "deep_stalker", "husk_wanderer"],
                  weights=[30, 20, 20, 15, 15], bosses=["void_reaper"]),
    "frozen_crypt": dict(label="Frozen Crypt", floor=world.ICE, wall=world.WALL_FROST,
                          kinds=["frost_wraith", "yeti", "ghost", "glacier_shard", "frost_sprite"],
                          weights=[25, 25, 15, 20, 15], bosses=["frost_monarch"]),
    "jungle_ruins": dict(label="Jungle Ruins", floor=world.JUNGLE, wall=world.WALL_JUNGLE,
                          kinds=["panther", "goblin", "harpy", "vine_serpent", "thornling"],
                          weights=[25, 25, 15, 20, 15], bosses=["boss", "ash_behemoth", "thorn_warden"]),
    "ember_den": dict(label="Ember Den", floor=world.ASH, wall=world.WALL_EMBER,
                       kinds=["salamander", "imp", "skeleton", "cinder_wisp"],
                       weights=[30, 25, 20, 25], bosses=["ash_behemoth", "sand_wyrm"]),
    "sunken_grotto": dict(label="Sunken Grotto", floor=world.SWAMP, wall=world.WALL_GROTTO,
                           kinds=["troll", "skeleton", "scorpion", "bog_crawler"],
                           weights=[30, 25, 20, 25], bosses=["boss", "thorn_warden"]),
    "wind_spire": dict(label="Wind Spire", floor=world.STONE, wall=world.WALL_SPIRE,
                        kinds=["harpy", "scorpion", "bat", "cliff_strider", "dune_stalker"],
                        weights=[25, 20, 15, 20, 20], bosses=["boss", "void_reaper", "sand_wyrm"]),
}
THEME_FOR_KIND = {
    "cave_lurker": "cave", "ghoul": "cave", "deep_stalker": "cave", "husk_wanderer": "cave",
    "frost_wraith": "frozen_crypt", "yeti": "frozen_crypt", "glacier_shard": "frozen_crypt",
    "frost_sprite": "frozen_crypt",
    "panther": "jungle_ruins", "goblin": "jungle_ruins", "vine_serpent": "jungle_ruins",
    "thornling": "jungle_ruins",
    "salamander": "ember_den", "imp": "ember_den", "cinder_wisp": "ember_den",
    "troll": "sunken_grotto", "skeleton": "sunken_grotto", "bog_crawler": "sunken_grotto",
    "harpy": "wind_spire", "scorpion": "wind_spire", "cliff_strider": "wind_spire", "dune_stalker": "wind_spire",
}

# ------------------------------------------------------ secret dungeon quest --
# A dungeon instance has a chance to hide a "???" secret quest (RotMG's classic
# hidden-bonus-room convention) - progress is SHARED across every player in the
# instance (same convention as kill_count/loot), tracked at the _reward()
# choke point since it already sees every kill. Completing one carves a
# corridor to the reserved-but-unconnected "hidden_room" (see
# world.make_bonus_room/reveal_hidden_room) and drops a harder "???" secret
# boss inside it. A small, extensible registry - a new quest kind is a one-line
# add to SECRET_QUEST_KINDS plus a branch in _start_secret_quest/_reward.
SECRET_QUEST_CHANCE = 0.3
SECRET_QUEST_KINDS = {
    # "kill_goons" has no fixed "target" here anymore - a flat number can't be
    # guaranteed completable given fixed, never-respawning per-room pods (a
    # rare kind might spawn far fewer than a flat target across the whole
    # dungeon). The real per-instance target is computed by
    # _pick_achievable_goon_target() and stored in self._secret_quest_target.
    "kill_goons": {"label": "Hunt down its goons"},
    "kill_totems": {"label": "Destroy the totems", "target": 3},  # TOTEM_COUNT is
    # always exactly spawned (see _spawn_totems) - no feasibility issue here
    "boss_timer": {"label": "Slay the boss swiftly", "time_limit": 150.0},
}
TOTEM_COUNT = 3

# ------------------------------------------------------- phase-2 access quest --
# Separate from the optional 30%-chance secret quest above - every dungeon that
# reserved a phase2_pocket (see world.make_bonus_room) gets this quest, always,
# so reaching the boss's harder second form is a real tracked objective rather
# than free/automatic. Deliberately a single simple kind (kill_goons) rather
# than mirroring all 3 of SECRET_QUEST_KINDS - this one needs to always exist
# and read clearly on its own HUD panel, not add more quest-design surface.
PHASE2_QUEST_KIND = "kill_goons"
PHASE2_QUEST_LABEL = "Clear the way to its lair"
# no fixed target constant - see _pick_achievable_goon_target()/self._phase2_quest_target,
# same feasibility reasoning as SECRET_QUEST_KINDS["kill_goons"] above

# breakable inter-room walls (see world.make_bonus_room's wall_obstacle_spots) -
# a real Obstacle, same "solid + destructible" mechanics as the existing loot-
# teaser crates, just tougher (a corridor gate should take a few real hits, not
# vanish in one) - see entities.Obstacle's kind="rubble_wall" for its distinct look
WALL_OBSTACLE_HP = 30


class RealmSim:
    def __init__(self, bonus=False, theme="generic", difficulty_name=None):
        self.is_bonus_room = bonus
        self._entrance_pos = None
        self._boss_room_pos = None
        theme_key = theme if theme in DUNGEON_THEMES else "generic"
        self.theme_key = theme_key
        self.theme = DUNGEON_THEMES.get(theme, DUNGEON_THEMES["generic"])
        self.theme_name = self.theme["label"]
        self.rooms = []      # [{"rect": pygame.Rect, "enemies": [Enemy,...], "cleared": bool}, ...] - fixed,
        # non-respawning mob pods per dungeon room (bonus rooms only; always empty in the open Realm)
        self.obstacles = []  # destructible one-shot wall props (bonus rooms only)
        if bonus:
            grid, dinfo = world.make_bonus_room(floor_tile=self.theme["floor"], wall_tile=self.theme["wall"],
                                                 theme_name=theme_key)
            self.realm_map = world.TileMap(grid)
            ex, ey = dinfo["entrance"]
            bx, by = dinfo["boss_room"]
            self._entrance_pos = pygame.Vector2(ex * TILE + TILE / 2, ey * TILE + TILE / 2)
            self._boss_room_pos = pygame.Vector2(bx * TILE + TILE / 2, by * TILE + TILE / 2)
            self._ambient_bounds = (0, 0, len(grid[0]) * TILE, len(grid) * TILE)
            self._ambient = vfx.AmbientEvents(vfx.DUNGEON_AMBIENT_KINDS.get(theme_key,
                                                                              vfx.DUNGEON_AMBIENT_KINDS["generic"]))
        else:
            self.realm_map = world.TileMap(world.make_realm())
        self.enemies = []
        self.bullets = []
        self.ground_items = []
        self.portals = []
        self.islands = []  # [{"idx","pos","theme","label","cooldown","alive_guardians"}, ...] -
        # "The Reforging" storyline, open-Realm only (see _stamp_islands) - stays empty for bonus rooms
        self.boss = None
        self.kill_count = 0
        self.next_boss_at = 40
        self.spawn_cd = 1.0
        self.events = []          # [(pid_or_None, message, color)] produced THIS tick
        self.pending_ability_effects = []  # [{"effect","pos","timer","radius","magnitude","caster_pid"}, ...] -
        # telegraphed ability casts (see use_ability()/TELEGRAPH_DELAY) waiting to actually resolve; persists
        # ACROSS ticks (unlike the per-tick lists below), so it's NOT touched by begin_tick()
        self.portal_entries = []  # [(pid, theme, kind, difficulty, portal_id), ...] players who touched a portal THIS tick
        # difficulty_name: pre-rolled at the moment a Dungeon Shard was USED (see main.py/server.py's
        # shard-use handler) so it can be shown as a label on the portal before anyone steps through -
        # falls back to a fresh roll here only if none was supplied (e.g. tests, or any future caller
        # that doesn't pre-roll one)
        _diff_by_name = {d["name"]: d for d in BONUS_DIFFICULTIES}
        if bonus:
            self.difficulty = _diff_by_name.get(difficulty_name) or random.choices(
                BONUS_DIFFICULTIES, weights=[d["weight"] for d in BONUS_DIFFICULTIES])[0]
        else:
            self.difficulty = None
        self.damage_popups = []   # [(x, y, amount, color)] floating combat text produced THIS tick
        self.vfx_events = []      # [(kind, x, y, color)] burst/ring effects produced THIS tick - see game/vfx.py
        self.sound_events = []    # [(kind, family, x, y)] mob hit/death/bark sounds produced THIS tick - see
        # game/audio.py. Position is carried so the client can distance-cull before playing (a continent-wide
        # sim can easily have combat/idle-barks happening far from the player - without culling, every one of
        # those plays at full volume as if it were right next to you, which read as "random sounds").
        self.mob_speech_events = []  # [(kind, text)] a mob just started a NEW flavor line this tick - pushed
        # into the persistent chat log (not just the in-world speech bubble) by main.py/coop_client.py
        # day/night only matters in the open Realm - a bonus dungeon has no sky
        self.day_time = random.uniform(0, DAY_LENGTH) if not bonus else 0.0
        self.blood_moon_active = False
        self._was_night = False
        self._nights_since_blood_moon = 0  # pity-counter - see _update_day_night
        self._ember_cd = self.EMBER_TICK
        self._beach_spawn = None if bonus else self._find_beach_spawn()
        self.lairs = [] if bonus else self._generate_lairs()
        self._hidden_room = None
        self._phase2_pocket = None
        self.secret_quest = None          # None | one of SECRET_QUEST_KINDS' keys
        self.secret_quest_progress = 0
        self.secret_quest_failed = False
        self.secret_quest_done = False
        self._quest_goon_kind = None
        self._quest_timer = 0.0
        self._secret_quest_target = 0     # set by _pick_achievable_goon_target - always <= actual spawned count
        self.phase2_quest = None          # None | PHASE2_QUEST_KIND, always started (not RNG-gated
        # like secret_quest) whenever a phase2_pocket exists - see _start_phase2_quest
        self.phase2_quest_progress = 0
        self.phase2_quest_done = False
        self._phase2_quest_goon_kind = None
        self._phase2_quest_target = 0     # set by _pick_achievable_goon_target - always <= actual spawned count
        self.phase2_door_open = False     # True once world.open_phase2_door has actually carved the corridor
        self._phase1_dead = False         # True once the main (phase-1) boss's death has been finalized -
        # the door only ever opens once BOTH this and phase2_quest_done are true, whichever finishes last
        self._phase1_boss_kind = None     # set by _spawn_dungeon_boss - which f"{kind}_phase2" to spawn later
        if not bonus:
            self._stamp_biome_buildings()
            self._stamp_islands()
            self._populate_all_lairs()
        else:
            self._spawn_dungeon_boss()
            # a real, permanent (non-expiring) exit portal at the entrance room, so
            # leaving is always as simple as "touch a portal", exactly like getting in -
            # no separate Enter-to-interact tile logic needed
            self.portals.append(Portal(self._entrance_pos, life=float("inf"), kind="entrance"))
            self._populate_fixed_rooms(dinfo)
            self._hidden_room = dinfo.get("hidden_room")
            self._phase2_pocket = dinfo.get("phase2_pocket")
            if self._hidden_room and random.random() < SECRET_QUEST_CHANCE:
                self._start_secret_quest()
            if self._phase2_pocket is not None:
                self._start_phase2_quest()

    def _pick_achievable_goon_target(self, min_frac=0.6):
        """Counts actual spawned occurrences per kind across the fixed-pod
        enemies (self.enemies - _populate_fixed_rooms already ran by the time
        this is ever called), picks a target kind weighted by how many
        actually exist (never a zero-count kind), and returns (kind, target)
        where target is always between 1 and that kind's REAL count
        inclusive. Fixed pods never respawn, so a flat/guessed target that
        happens to exceed the real spawned count would otherwise permanently
        soft-lock a "kill N of this kind" quest for that dungeon instance -
        this makes it always completable by construction, not by luck."""
        counts = {}
        for e in self.enemies:
            if e.alive and e.kind in self.theme["kinds"]:
                counts[e.kind] = counts.get(e.kind, 0) + 1
        available = [(k, c) for k, c in counts.items() if c > 0]
        if not available:
            return None, 0
        kinds = [k for k, _ in available]
        weights = [c for _, c in available]
        kind = random.choices(kinds, weights=weights)[0]
        actual = counts[kind]
        target = max(1, min(actual, round(actual * min_frac)))
        return kind, target

    def _start_secret_quest(self):
        kind = random.choice(list(SECRET_QUEST_KINDS.keys()))
        self.secret_quest = kind
        cfg = SECRET_QUEST_KINDS[kind]
        if kind == "kill_goons":
            self._quest_goon_kind, self._secret_quest_target = self._pick_achievable_goon_target()
            if self._quest_goon_kind is None:
                # no fixed-pod enemies existed to build this around (astronomically
                # unlikely - every theme populates several middle rooms) - fall back
                # to a kind never present rather than leave a misleading label; the
                # quest simply never progresses, matching a harmless no-op
                self._quest_goon_kind = "__none__"
        elif kind == "kill_totems":
            self._spawn_totems()
        elif kind == "boss_timer":
            self._quest_timer = cfg["time_limit"]
        self.events.append((None, f'A whisper echoes: "{cfg["label"]}..."', (200, 170, 255)))

    def _spawn_totems(self):
        """Places TOTEM_COUNT stationary, damageable Totem enemies into random
        fixed-pod rooms (see _populate_fixed_rooms) - functionally just
        decoration you can damage, per the plan; they ride along with that
        room's own pod and count toward its "cleared" tracking too."""
        if not self.rooms:
            return
        for _ in range(TOTEM_COUNT):
            room_idx = random.randrange(len(self.rooms))
            rect = self.rooms[room_idx]["rect"]
            tx = random.randint(rect.left + 1, rect.right - 2)
            ty = random.randint(rect.top + 1, rect.bottom - 2)
            pos = pygame.Vector2(tx * TILE + TILE / 2, ty * TILE + TILE / 2)
            totem = Enemy("totem", pos)
            totem.room_idx = room_idx
            self.enemies.append(totem)
            self.rooms[room_idx]["enemies"].append(totem)

    def _complete_secret_quest(self):
        self.secret_quest = None
        self.secret_quest_done = True
        if not self._hidden_room:
            return
        entrance_tile = (int(self._entrance_pos.x // TILE), int(self._entrance_pos.y // TILE))
        world.reveal_hidden_room(self.realm_map.grid, self._hidden_room, entrance_tile, self.theme["floor"],
                                  theme_name=self.theme_key)
        hcx, hcy = self._hidden_room["center"]
        boss_pos = pygame.Vector2(hcx * TILE + TILE / 2, hcy * TILE + TILE / 2)
        boss_kind = random.choice(self.theme["bosses"])
        # 1.4x the usual boss scaling - a genuinely harder "???" secret boss,
        # not a re-tint (rank/aggro already come out "boss"/True from ENEMY_KINDS)
        secret_boss = Enemy(boss_kind, boss_pos, level_scale=self.difficulty["enemy_scale"] * 1.4)
        self.enemies.append(secret_boss)
        self.vfx_events.append(("boss_appear", boss_pos.x, boss_pos.y, (220, 90, 255)))
        self.events.append((None, "A hidden door grinds open somewhere in the dungeon...", (200, 170, 255)))

    def _populate_fixed_rooms(self, dinfo):
        """RotMG-style dungeon rooms: every non-entrance, non-boss room gets a
        FIXED roster of 4-8 enemies from this theme's kinds/weights, spawned
        once here and never replenished (see update()'s spawn gate, which
        skips ambient spawning entirely for bonus rooms now that this exists).
        Rooms are passable whether or not their pod is still alive - nothing
        here gates movement, just tracks a "cleared" flag for later hooks."""
        for room in dinfo["rooms"]:
            rx, ry, rw, rh = room["rect"]
            rect = pygame.Rect(rx, ry, rw, rh)
            room_state = {"rect": rect, "enemies": [], "cleared": False}
            self.rooms.append(room_state)
            for _ in range(random.randint(4, 8)):
                tx = random.randint(rect.left + 1, rect.right - 2)
                ty = random.randint(rect.top + 1, rect.bottom - 2)
                pos = pygame.Vector2(tx * TILE + TILE / 2, ty * TILE + TILE / 2)
                kind = random.choices(self.theme["kinds"], weights=self.theme["weights"])[0]
                e = Enemy(kind, pos, level_scale=self.difficulty["enemy_scale"])
                e.room_idx = len(self.rooms) - 1
                self.enemies.append(e)
                room_state["enemies"].append(e)
        for (ox, oy) in dinfo.get("obstacle_spots", []):
            pos = pygame.Vector2(ox * TILE + TILE / 2, oy * TILE + TILE / 2)
            self.obstacles.append(Obstacle(pos))
        for (wx, wy) in dinfo.get("wall_obstacle_spots", []):
            pos = pygame.Vector2(wx * TILE + TILE / 2, wy * TILE + TILE / 2)
            self.obstacles.append(Obstacle(pos, hp=WALL_OBSTACLE_HP, kind="rubble_wall"))

    def is_solid_at(self, wx, wy):
        """Same as realm_map.is_solid, plus a check against live destructible
        obstacles (empty list outside bonus rooms, so this is a free no-op
        everywhere else) - obstacles block movement for players AND enemies
        (see is_solid() below, which Enemy._move() calls via duck-typing)."""
        if self.realm_map.is_solid(wx, wy):
            return True
        for ob in self.obstacles:
            if ob.alive and pygame.Vector2(wx, wy).distance_to(ob.pos) < ob.radius:
                return True
        return False

    # Enemy.update()/_move() take a "tile_map"-shaped object and only ever call
    # .is_solid(x,y) / .has_line_of_sight(x0,y0,x1,y1) on it - passing `self`
    # (see the enemy tick loop below) instead of self.realm_map means an
    # obstacle blocks enemy movement/sight/fire exactly like a real wall does,
    # without Enemy needing to know obstacles exist at all.
    def is_solid(self, wx, wy):
        return self.is_solid_at(wx, wy)

    def has_line_of_sight(self, x0, y0, x1, y1):
        if not self.realm_map.has_line_of_sight(x0, y0, x1, y1):
            return False
        if not self.obstacles:
            return True
        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq < 1:
            return True
        for ob in self.obstacles:
            if not ob.alive:
                continue
            t = max(0.0, min(1.0, ((ob.pos.x - x0) * dx + (ob.pos.y - y0) * dy) / length_sq))
            px, py = x0 + dx * t, y0 + dy * t
            if math.hypot(ob.pos.x - px, ob.pos.y - py) < ob.radius:
                return False
        return True

    def _room_cleared_check(self, room_idx):
        if room_idx is None or room_idx >= len(self.rooms):
            return
        room = self.rooms[room_idx]
        if not room["cleared"] and all(not e.alive for e in room["enemies"]):
            room["cleared"] = True

    def spawn_point(self):
        if self.is_bonus_room:
            # offset from the entrance portal's exact position - spawning ON it would
            # immediately trigger the portal-touch check (< 22px) the instant you
            # arrive, bouncing you straight back out before you ever see the dungeon
            return pygame.Vector2(self._entrance_pos.x, self._entrance_pos.y + TILE * 1.5)
        if self._beach_spawn is not None:
            return pygame.Vector2(self._beach_spawn)
        return self.realm_map.center_world_pos()

    def _spawn_dungeon_boss(self):
        kind = random.choice(self.theme["bosses"])
        self._phase1_boss_kind = kind  # remembered for _maybe_open_phase2_door's f"{kind}_phase2" spawn later
        self.boss = Enemy(kind, self._boss_room_pos, level_scale=self.difficulty["enemy_scale"])
        self.enemies.append(self.boss)
        self.vfx_events.append(("boss_appear", self.boss.pos.x, self.boss.pos.y, (255, 140, 0)))

    def _find_beach_spawn(self):
        # RotMG-flavoured touch for this island map: arrive on the shore rather
        # than dropped in the dead center, so the coastline is the first thing
        # you see and the interior biomes are something you walk inland to find.
        grid = self.realm_map.grid
        w, h = self.realm_map.w, self.realm_map.h
        cx = w / 2
        candidates = []
        for y in range(2, h - 2):
            row, row_above, row_below = grid[y], grid[y - 1], grid[y + 1]
            for x in range(2, w - 2):
                t = row[x]
                if t == world.WATER or t in world.SOLID:
                    continue
                if world.WATER in (row[x - 1], row[x + 1], row_above[x], row_below[x]):
                    candidates.append((x, y))
        if not candidates:
            return self.realm_map.center_world_pos()
        # prefer a shore tile south of center and close to the map's x-midline,
        # so the spawn point is easy to find again and roughly consistent in feel
        best = max(candidates, key=lambda c: c[1] - abs(c[0] - cx) * 0.5)
        x, y = best
        return pygame.Vector2(x * TILE + TILE / 2, y * TILE + TILE / 2)

    def _generate_lairs(self):
        # Lairs are scattered anywhere across the continent EXCEPT too close to the
        # arrival point - the old "guarantee a few lairs right next to spawn" design
        # got flipped: you should be able to step off the beach without being
        # ambushed, and the continent is now big enough that lairs everywhere still
        # means you're never far from finding something (that's what pre-populating
        # them immediately in _populate_all_lairs() is for, instead of a "wait for a
        # trigger" spawn-on-approach model).
        lairs = []
        w, h = self.realm_map.w, self.realm_map.h
        spawn = self._beach_spawn or self.realm_map.center_world_pos()
        center = self.realm_map.center_world_pos()
        max_r_world = min(w, h) / 2 * TILE
        for _ in range(LAIR_COUNT):
            pos = None
            for _try in range(30):
                tx = random.randint(5, w - 6)
                ty = random.randint(5, h - 6)
                candidate = pygame.Vector2(tx * TILE + TILE / 2, ty * TILE + TILE / 2)
                # water is walkable now (see world.SPEED_MULT) but lairs still shouldn't
                # sit out in open water - is_solid() alone no longer excludes it
                if (not self.realm_map.is_solid(candidate.x, candidate.y)
                        and self.realm_map.tile_at(candidate.x, candidate.y) != world.WATER
                        and candidate.distance_to(spawn) >= MIN_LAIR_DIST_FROM_SPAWN):
                    pos = candidate
                    break
            if pos is None:
                continue
            tile_here = self.realm_map.tile_at(pos.x, pos.y)
            kind_sets = BIOME_LAIR_KIND_SETS.get(tile_here, LAIR_KIND_SETS)
            kinds, weights = random.choice(kind_sets)
            # RotMG's real beaches-to-Godlands gradient: lairs near the continent's
            # center are tougher than ones near the coast, on top of whatever the
            # biome's own mob roster already implies - up to +120% HP/level dead center
            dist_frac = min(1.0, pos.distance_to(center) / max_r_world)
            difficulty_scale = 1.0 + (1.0 - dist_frac) * 1.2
            lairs.append({"pos": pos, "kinds": kinds, "weights": weights, "cap": LAIR_CAP,
                          "difficulty_scale": difficulty_scale, "respawn_cd": 0.0})
        return lairs

    def _stamp_biome_buildings(self):
        """Gives each biome ONE real landmark building (10 total, one per
        biome) at its toughest lair - see world.stamp_lair_building for the
        actual wall/floor/decoration carving. Picking the toughest lair
        (highest difficulty_scale, already computed by _generate_lairs) as
        the landmark reuses existing per-lair data with no new calculation.
        Must run AFTER _generate_lairs() but BEFORE _populate_all_lairs() so
        the tightened spawn radius set below actually takes effect."""
        toughest_by_biome = {}
        second_by_biome = {}  # each biome's SECOND-toughest lair - used below to place
        # that biome's visual terrace (plan section 2) at a position distinct from its
        # landmark building, never the same lair
        for lair in self.lairs:
            biome_name = world.GROUND_TO_BIOME_NAME.get(self.realm_map.tile_at(lair["pos"].x, lair["pos"].y))
            if biome_name is None:
                continue
            current = toughest_by_biome.get(biome_name)
            if current is None or lair["difficulty_scale"] > current["difficulty_scale"]:
                second_by_biome[biome_name] = current  # demote the old #1 to #2
                toughest_by_biome[biome_name] = lair
            else:
                prev_second = second_by_biome.get(biome_name)
                if prev_second is None or lair["difficulty_scale"] > prev_second["difficulty_scale"]:
                    second_by_biome[biome_name] = lair
        # real bug caught in testing: two different biomes' "toughest lair" positions
        # can land close enough together (especially near a biome-region border) that
        # their building rects collide - whichever got stamped second would silently
        # overwrite the first one's walls/floor/props with no error, quietly losing an
        # entire building. Check every candidate against every ALREADY-stamped rect
        # (with a 2-tile margin so buildings don't even end up wall-to-wall) before
        # committing to it; skip (don't stamp) on collision rather than corrupt an
        # earlier building - a rare skipped biome is far better than a silently
        # destroyed one.
        placed_rects = []
        for biome_name, lair in toughest_by_biome.items():
            center_tile = (int(lair["pos"].x // TILE), int(lair["pos"].y // TILE))
            candidate_rect = world.lair_building_rect(self.realm_map.grid, center_tile)
            if any(candidate_rect.inflate(4, 4).colliderect(r) for r in placed_rects):
                continue
            rect = world.stamp_lair_building(self.realm_map.grid, center_tile, biome_name)
            placed_rects.append(rect)
            # keep this lair's own mobs inside the room it now lives in, instead of
            # scattering across the default wide 20-150 tile radius (see the
            # _populate_all_lairs call site that reads these two keys back)
            lair["spawn_min_tiles"] = 2
            lair["spawn_max_tiles"] = max(rect.w, rect.h) // 2

        # visual terracing (plan section 2 - "levels/stairs/walls for a more
        # 3D look") - one per biome, at that biome's SECOND-toughest lair so
        # it's never the same spot as its landmark building, reusing the
        # SAME placed_rects overlap-avoidance check above (a terrace never
        # overlaps a building, and vice versa, since both checks share this
        # one list). A biome with only one lair (no real second-toughest one
        # exists) simply gets no terrace rather than risking reusing/
        # overlapping the building's own lair - a rare skip, not a bug.
        for biome_name, lair in second_by_biome.items():
            if lair is None:
                continue
            center_tile = (int(lair["pos"].x // TILE), int(lair["pos"].y // TILE))
            candidate_rect = world.terrace_rect(center_tile)
            if any(candidate_rect.inflate(4, 4).colliderect(r) for r in placed_rects):
                continue
            rect = world.stamp_terrace(self.realm_map.grid, center_tile, biome_name)
            placed_rects.append(rect)

    def _stamp_islands(self):
        """"The Reforging" storyline: stamps 10 small standalone island zones
        as coastal peninsulas evenly spaced by angle around the map
        perimeter, alternating shard/choir theme (see world.stamp_island/
        ISLAND_THEMES/ISLAND_NAMES). Must run after _stamp_biome_buildings()
        (grid/coastline finished) but before _populate_all_lairs(), same
        hook-point reasoning as that method's own docstring. Also stamps a
        small ring of persistent "island_link" hub portals near
        self._beach_spawn (see _stamp_island_hub) - the fast-travel shortcut
        the user asked for, alongside every island always being reachable on
        foot (an island's anchor always overlaps the mainland's own
        coastline - see world.stamp_island)."""
        grid = self.realm_map.grid
        grid_h, grid_w = len(grid), len(grid[0])
        cx, cy = grid_w / 2, grid_h / 2
        n = len(ISLAND_NAMES)
        placed_centers = []
        for i, name in enumerate(ISLAND_NAMES):
            theme = "island_shard" if i % 2 == 0 else "island_choir"
            angle = (2 * math.pi * i) / n
            dx, dy = math.cos(angle), math.sin(angle)
            # walk outward from the map center until hitting water - that's the
            # real mainland coastline at this angle, and last_land is the exact
            # shore point the walkway below connects FROM
            x, y = cx, cy
            last_land = (int(cx), int(cy))
            for _ in range(max(grid_w, grid_h)):
                x += dx
                y += dy
                ix, iy = int(x), int(y)
                if not (0 <= ix < grid_w and 0 <= iy < grid_h):
                    break
                if grid[iy][ix] == world.WATER:
                    break
                last_land = (ix, iy)
            # anchor a real distance PAST the coastline - reusing
            # world.coastline_radius (the SAME smooth formula make_realm()
            # itself used to carve the coastline shape) as the base, rather
            # than the raw walked last_land distance, since a small inland
            # pond/decoration-patch water tile can make the walk above stop
            # well short of the true coastline (confirmed empirically: at
            # some angles the walked distance and the formula's value matched
            # exactly, at others the walk stopped over 100 tiles early on an
            # inland pond) - the smooth formula is immune to that noise. A
            # fixed water-gap (12% of the map's own size) pushes the anchor a
            # real distance further out into open water at EVERY angle,
            # scaling with map size rather than being a guessed constant -
            # islands now read as clearly out at the map's edges, not just a
            # few tiles off the coast. The growing gap back to the mainland
            # shore is bridged by a real colored plank walkway
            # (world.stamp_walkway, below) instead of a short hop.
            water_gap = min(grid_w, grid_h) * 0.12
            target_r = world.coastline_radius(angle) + water_gap
            margin = world.ISLAND_RADIUS + 3
            ax = min(max(int(cx + dx * target_r), margin), grid_w - margin)
            ay = min(max(int(cy + dy * target_r), margin), grid_h - margin)
            if any(math.hypot(ax - c[0], ay - c[1]) < world.ISLAND_RADIUS * 2.5 for c in placed_centers):
                continue  # too close to an already-placed island - rare, skip rather than overlap it
            rect, center_tile = world.stamp_island(grid, (ax, ay), theme)
            # stop the walkway at the island's EDGE, not its exact center -
            # targeting center_tile directly would lay planks straight over
            # the landmark tile stamp_island just placed there (a real bug
            # caught by actually checking the island's core tile afterward,
            # not just "did it run without crashing")
            dist_to_center = math.hypot(center_tile[0] - last_land[0], center_tile[1] - last_land[1])
            edge_frac = max(0.0, (dist_to_center - world.ISLAND_RADIUS) / dist_to_center) if dist_to_center > 0 else 0.0
            walkway_end = (last_land[0] + (center_tile[0] - last_land[0]) * edge_frac,
                           last_land[1] + (center_tile[1] - last_land[1]) * edge_frac)
            world.stamp_walkway(grid, last_land, walkway_end, world.WALKWAY_PLANK_TILE[i])
            placed_centers.append(center_tile)
            center_world = pygame.Vector2(center_tile[0] * TILE + TILE / 2, center_tile[1] * TILE + TILE / 2)
            # cooldown starts at 0 (not a delay) so every island's first guardian
            # wave is already live the moment a fresh Realm is generated - a
            # player's very first entry finds them already spawned, not waiting
            # through an initial timer; every wave AFTER this one still refreshes
            # on the normal 5-minute ISLAND_QUEST_INTERVAL via _progress_island_event
            self.islands.append({"idx": len(self.islands), "pos": center_world, "theme": theme,
                                  "label": name, "cooldown": 0.0,
                                  "alive_guardians": 0})
        self._stamp_island_hub()

    def _stamp_island_hub(self):
        """A real "starting area" plaza around the Realm's own arrival point
        (see world.stamp_realm_start), with one persistent island_link portal
        per island placed at DETERMINISTIC, evenly-spaced points around a
        ring inside it - not independent random nearby-spot searches per
        portal (the earlier approach), which had no separation guarantee
        between portals and could - and did - land two right on top of each
        other."""
        if not self.islands or self._beach_spawn is None:
            return
        anchor_tile = (int(self._beach_spawn.x // TILE), int(self._beach_spawn.y // TILE))
        biome_name = world.GROUND_TO_BIOME_NAME.get(self.realm_map.tile_at(self._beach_spawn.x, self._beach_spawn.y))
        if biome_name is None:
            biome_name = "forest"  # sane fallback - _find_beach_spawn always lands on real biome ground in practice
        world.stamp_realm_start(self.realm_map.grid, anchor_tile, biome_name)
        hub_center = pygame.Vector2(anchor_tile[0] * TILE + TILE / 2, anchor_tile[1] * TILE + TILE / 2)
        n = len(self.islands)
        ring_radius = (world.REALM_START_RADIUS - 3) * TILE  # inside the plaza, clear of the outer marker props
        for i, isl in enumerate(self.islands):
            angle = (2 * math.pi * i) / n
            slot = hub_center + pygame.Vector2(1, 0).rotate_rad(angle) * ring_radius
            self.portals.append(Portal(slot, life=float("inf"), kind="island_link",
                                        target_pos=(isl["pos"].x, isl["pos"].y), label=isl["label"]))

    def _populate_all_lairs(self):
        """Fills every lair up to its cap right away, so the continent is already
        alive with monsters the moment you arrive - no waiting for a proximity
        trigger to spawn things in as you explore."""
        for idx, lair in enumerate(self.lairs):
            for _ in range(lair["cap"]):
                # a landmark lair (see _stamp_biome_buildings) sets BOTH of these to
                # keep its mobs inside its stamped building - min_tiles must also be
                # overridden, not just max_tiles: random.uniform(20, 5) doesn't error,
                # it just silently inverts, which would have let enemies spawn up to
                # the OLD default 20 tiles away despite a tight max_tiles
                pos = self._find_spawn_pos_near(lair["pos"], min_tiles=lair.get("spawn_min_tiles", 20),
                                                 max_tiles=lair.get("spawn_max_tiles", 150))
                if pos is None:
                    continue
                kind = random.choices(lair["kinds"], weights=lair["weights"])[0]
                enemy = Enemy(kind, pos, level_scale=lair["difficulty_scale"], home_pos=lair["pos"])
                enemy.lair_idx = idx
                self.enemies.append(enemy)

    def _find_spawn_pos_near(self, anchor, min_tiles=20, max_tiles=150, avoid_players=()):
        for _try in range(20):
            ang = random.uniform(0, 360)
            dist = random.uniform(min_tiles, max_tiles)
            pos = anchor + pygame.Vector2(1, 0).rotate(ang) * dist
            if self.realm_map.is_solid(pos.x, pos.y) or self.realm_map.tile_at(pos.x, pos.y) == world.WATER:
                continue
            if any(pos.distance_to(p.pos) < MIN_SPAWN_DIST_FROM_PLAYER for p in avoid_players):
                continue
            return pos
        return None

    # ------------------------------------------------------------- update --
    @property
    def light_level(self):
        """1.0 = high noon, 0.0 = pitch black midnight - a smooth sinusoid over
        DAY_LENGTH, not a hard on/off flip."""
        if self.is_bonus_room:
            return 1.0
        frac = self.day_time / DAY_LENGTH
        return (math.cos(frac * math.tau) + 1) / 2

    @property
    def is_night(self):
        return not self.is_bonus_room and self.light_level < 0.35

    def _update_day_night(self, dt):
        if self.is_bonus_room:
            return
        self.day_time = (self.day_time + dt) % DAY_LENGTH
        night_now = self.is_night
        if night_now and not self._was_night:
            # a pity-counter lifecycle rather than a flat independent roll every
            # single night - the longer it's been since the last Blood Moon, the
            # more likely the next one is (capped), so it's a real, structured
            # cadence instead of pure chance every time
            effective_chance = min(0.5, BLOOD_MOON_CHANCE + self._nights_since_blood_moon * 0.03)
            self.blood_moon_active = random.random() < effective_chance
            if self.blood_moon_active:
                self._nights_since_blood_moon = 0
                self.events.append((None, "A Blood Moon rises over the Godlands...", (220, 60, 60)))
            else:
                self.events.append((None, "Night falls. The Godlands grow more dangerous.", (140, 150, 210)))
        elif not night_now and self._was_night:
            if not self.blood_moon_active:
                self._nights_since_blood_moon += 1
            self.blood_moon_active = False
            self.events.append((None, "Dawn breaks over the Godlands.", (255, 210, 140)))
        self._was_night = night_now

    def begin_tick(self):
        """Resets the per-tick event/popup/portal-entry lists - the CALLER must do this
        exactly once per tick, BEFORE processing any player actions (equip, use_ability,
        loot, fish, wish...), not inside update(). Those actions run before update() in
        the co-op server's step() (discrete actions, then continuous sim tick); if
        update() itself did the reset, it would silently wipe any feed message an
        action generated earlier in the same tick before the snapshot ever saw it -
        exactly the bug this method exists to avoid."""
        self.events = []
        self.portal_entries = []
        self.damage_popups = []
        self.vfx_events = []
        self.sound_events = []
        self.mob_speech_events = []

    def update(self, dt, players):
        """players: dict[pid, Player], shared by every caller (1 in single-player, N in co-op).
        Caller must have already called begin_tick() this tick (see its docstring)."""
        alive = [p for p in players.values() if p.alive]
        self._update_day_night(dt)
        self._update_fishing(dt, players)
        self._update_weather_damage(dt, alive)

        if not self.is_bonus_room:
            for lair in self.lairs:
                if lair["respawn_cd"] > 0:
                    lair["respawn_cd"] -= dt
            self._tick_island_events(dt)

        if self.is_bonus_room:
            self._ambient.update(dt, self._ambient_bounds)

        if self.secret_quest == "boss_timer":
            self._quest_timer -= dt
            if self._quest_timer <= 0:
                self.secret_quest = None
                self.secret_quest_failed = True
                self.events.append((None, "The whisper falls silent... too slow.", (150, 140, 160)))

        cap = self.difficulty["cap"] if self.is_bonus_room else REALM_ENEMY_CAP
        self.spawn_cd -= dt
        # bonus-room trash is now a FIXED per-room pod (see _populate_fixed_rooms,
        # called once at generation) that never replenishes - only the open Realm's
        # lair ecosystem keeps ambient-spawning here
        if not self.is_bonus_room and self.spawn_cd <= 0 and len(self.enemies) < cap and alive:
            night_mult = 0.55 if self.is_night else 1.0
            self.spawn_cd = random.uniform(0.6, 1.4) * night_mult
            self._spawn_enemy(alive)

        for e in self.enemies:
            if not alive:
                break
            target = min(alive, key=lambda p: p.pos.distance_to(e.pos))
            if not self.is_bonus_room and target.pos.distance_to(e.pos) > ACTIVE_SIM_RADIUS:
                continue  # dormant - too far from every player to be worth simulating this tick
            # passing `self` (not self.realm_map) so an enemy's sight/fire/movement
            # collision ALSO respects live destructible obstacles, not just real wall
            # tiles - see is_solid()/has_line_of_sight() below, which duck-type the
            # same interface Enemy._move()/update() already expect from a TileMap
            e.update(dt, target.pos, self.bullets, tile_map=self)
            if e.alive and e.bleed_time > 0:
                tick_dmg = e.bleed_dps * dt
                killed = e.take_damage(tick_dmg, whole=False)
                self.damage_popups.append((e.pos.x, e.pos.y, round(e._last_hit_damage), (200, 30, 30)))
                if killed:
                    self._reward(e, players.get(e.status_source_pid))
            if e.alive and e.burn_time > 0:
                tick_dmg = e.burn_dps * dt
                killed = e.take_damage(tick_dmg, whole=False)
                self.damage_popups.append((e.pos.x, e.pos.y, round(e._last_hit_damage), (255, 130, 30)))
                if killed:
                    self._reward(e, players.get(e.status_source_pid))
            if not e.alive:
                continue  # a DoT tick just finished it off - skip the rest of this
                # iteration (speech/root-pulse/contact-damage) same as _resolve_bullet_hits
                # already implicitly does for a bullet-killed enemy (it never re-enters here)
            if e._bark_pending:
                e._bark_pending = False
                self.sound_events.append(("mob_bark", sound_family(e.kind), e.pos.x, e.pos.y))
            if e._speech_pending:
                e._speech_pending = False
                # only neutral mobs and bosses clutter the persistent chat log - a
                # regular aggro'd trash/elite mob's line still shows as an in-world
                # bubble (unaffected), just doesn't also spam the chat history
                if e.neutral or e.rank == "boss":
                    self.mob_speech_events.append((e.kind, e.speech))
            if e._root_pulse:
                e._root_pulse = False
                for p in alive:
                    if p.pos.distance_to(e.pos) <= self.ROOT_PULSE_RADIUS:
                        p.root_time = max(p.root_time, self.ROOT_DURATION)
                        self.events.append((p.pid, "Rooted by thorns!", (140, 220, 100)))
            for p in alive:
                if e.pos.distance_to(p.pos) < e.radius + p.radius and e.contact_cd <= 0:
                    e.contact_cd = 0.5
                    if e.neutral and e.speed > 0:
                        # a peaceful, mobile animal you physically bump into gets a
                        # short glide-away shove instead of a (harmless, dmg=(0,0))
                        # damage tick - speed>0 excludes the stationary totem
                        # decoration (also neutral) from being physically pushable
                        push_dir = e.pos - p.pos
                        if push_dir.length_squared() < 1:
                            push_dir = pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
                        e._push_vec = push_dir.normalize() * PUSH_SPEED
                        e._push_total = PUSH_DURATION
                        e.push_time = PUSH_DURATION
                    else:
                        real = p.take_damage(random.randint(*e.dmg))
                        self.events.append((p.pid, f"-{real} hp", (230, 90, 90)))
                        self.damage_popups.append((p.pos.x, p.pos.y, real, (255, 90, 90)))
                        if e.speed > 0:
                            # a small nudge alongside the damage - "a little bit of
                            # movement for aggressive mobs too" - never applied to
                            # the player, only to the enemy that just hit them
                            push_dir = e.pos - p.pos
                            if push_dir.length_squared() < 1:
                                push_dir = pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
                            e._push_vec = push_dir.normalize() * AGGRO_PUSH_SPEED
                            e._push_total = AGGRO_PUSH_DURATION
                            e.push_time = AGGRO_PUSH_DURATION

        self.tick_pets(dt, players)
        self._resolve_pending_ability_effects(dt)
        self.bullets = [b for b in self.bullets if b.update(dt)]
        self._trigger_wildlife_flee()
        self._resolve_bullet_hits(players)
        self._maybe_spawn_boss(alive)

        self.enemies = [e for e in self.enemies if e.alive]
        self.ground_items = [g for g in self.ground_items if g.update(dt)]
        self.portals = [pt for pt in self.portals if pt.update(dt)]
        # no more auto-pickup-by-walking-over: see find_nearby_bag() - a bag now waits
        # for you to actually choose to open it (right-click), showing what's inside via
        # a drag-and-drop window, same idea as RotMG's loot bags
        self._check_portal_entry(alive)

    def _spawn_enemy(self, alive):
        # bonus rooms no longer ambient-spawn here at all (see update()'s spawn
        # gate) - their trash is a fixed per-room pod from _populate_fixed_rooms
        self._spawn_enemy_lair(alive)

    def _spawn_enemy_lair(self, alive):
        # the continent is pre-populated on arrival (_populate_all_lairs); this just
        # replenishes lairs that have lost enemies to combat - Minecraft-mob-spawner
        # style: a lair you just cleared does NOT instantly refill while you're still
        # standing on it. It only becomes eligible again once no player is within
        # LAIR_RESPAWN_SIGHT_RANGE, and even then trickles back at most one enemy per
        # LAIR_RESPAWN_INTERVAL seconds (per lair, via its own respawn_cd) - so you
        # come back to a lair that's quietly refilled, not one that never emptied.
        eligible = []
        for i, lair in enumerate(self.lairs):
            count = sum(1 for e in self.enemies if getattr(e, "lair_idx", None) == i)
            if count >= lair["cap"] or lair["respawn_cd"] > 0:
                continue
            if any(p.pos.distance_to(lair["pos"]) <= LAIR_RESPAWN_SIGHT_RANGE for p in alive):
                continue
            eligible.append(i)
        if not eligible:
            return
        idx = random.choice(eligible)
        lair = self.lairs[idx]
        pos = self._find_spawn_pos_near(lair["pos"], avoid_players=alive)
        if pos is None:
            return
        kind = random.choices(lair["kinds"], weights=lair["weights"])[0]
        avg_level = sum(p.level for p in alive) / len(alive)
        scale = (1.0 + (avg_level - 1) * 0.08) * lair["difficulty_scale"]
        moonlit = self.is_night and random.random() < MOONLIT_CHANCE
        if moonlit:
            scale *= 2.0 if self.blood_moon_active else 1.6
        enemy = Enemy(kind, pos, scale, home_pos=lair["pos"])
        enemy.lair_idx = idx
        enemy.moonlit = moonlit
        self.enemies.append(enemy)
        lair["respawn_cd"] = LAIR_RESPAWN_INTERVAL

    def _maybe_spawn_boss(self, alive):
        if self.is_bonus_room or not alive or self.boss is not None:
            return
        if self.kill_count >= self.next_boss_at:
            self.next_boss_at += 40
            avg_level = sum(p.level for p in alive) / len(alive)
            anchor = random.choice(alive).pos
            kind = random.choice(BOSS_KINDS)
            self.boss = Enemy(kind, anchor + pygame.Vector2(0, -300), 1.0 + avg_level * 0.15)
            self.enemies.append(self.boss)
            self.events.append((None, "A Mad God's Avatar has appeared!", (255, 140, 0)))
            self.vfx_events.append(("boss_appear", self.boss.pos.x, self.boss.pos.y, (255, 140, 0)))

    def _tick_island_events(self, dt):
        """"The Reforging" storyline: every ISLAND_QUEST_INTERVAL seconds, per
        island independently, a quiet island "flares"/"sings" and spawns a
        themed guardian wave at its own landmark - modeled directly on the
        existing per-lair LAIR_RESPAWN_INTERVAL timer pattern (island-scoped
        instead of lair-scoped) and announced the same way _maybe_spawn_boss
        announces a world boss. Open-Realm only (see the guard at this
        method's call site in update()). While a wave is still up, the
        cooldown is frozen (not decremented) - _progress_island_event resets
        it to a fresh ISLAND_QUEST_INTERVAL only once every guardian in that
        wave is dead, so the event doesn't silently re-arm mid-fight."""
        for isl in self.islands:
            if isl["alive_guardians"] > 0:
                continue
            isl["cooldown"] -= dt
            if isl["cooldown"] > 0:
                continue
            theme = ISLAND_THEMES[isl["theme"]]
            wave = [theme["anchor"]] + [random.choice(theme["guardians"]) for _ in range(ISLAND_WAVE_SIZE - 1)]
            for kind in wave:
                pos = self._find_spawn_pos_near(isl["pos"], min_tiles=2, max_tiles=6)
                if pos is None:
                    pos = pygame.Vector2(isl["pos"])
                enemy = Enemy(kind, pos)
                enemy.island_idx = isl["idx"]
                self.enemies.append(enemy)
                isl["alive_guardians"] += 1
            self.events.append((None, f"{isl['label']} is {theme['verb']}! Defenders have appeared.",
                                 theme["color"]))
            self.vfx_events.append(("boss_appear", isl["pos"].x, isl["pos"].y, theme["color"]))

    def _progress_island_event(self, enemy, killer):
        """Tap point for an island guardian's death (called from _reward()
        alongside _progress_secret_quest/_progress_phase2_quest) - decrements
        that island's live-guardian count (tagged at spawn via
        enemy.island_idx, mirroring the existing lair_idx tagging
        precedent); once the whole wave is dead, rolls one guaranteed
        elite-tier bonus loot bag at the island's core (reusing the exact
        same roll_loot/_spawn_loot_bag path every other elite kill already
        uses), grants the `reforger` achievement, announces completion, and
        re-arms that island's cooldown for the next flare/song."""
        idx = getattr(enemy, "island_idx", None)
        if idx is None or idx >= len(self.islands):
            return
        isl = self.islands[idx]
        isl["alive_guardians"] = max(0, isl["alive_guardians"] - 1)
        if isl["alive_guardians"] > 0:
            return
        isl["cooldown"] = ISLAND_QUEST_INTERVAL
        cls_for_bonus = killer.cls_name if killer else "wizard"
        bonus_items = roll_loot(cls_for_bonus, "elite", 1.0)
        if bonus_items:
            self._spawn_loot_bag(bonus_items, enemy.pos)
        if killer:
            self._grant_achievement(killer, "reforger")
        theme = ISLAND_THEMES[isl["theme"]]
        self.events.append((None, f"{isl['label']} has been calmed. The Reforging continues.", theme["color"]))

    def _trigger_wildlife_flee(self):
        """Ambient unshootable wildlife "runs away if you shoot near them" - any
        PLAYER bullet within FLEE_TRIGGER_RADIUS of one arms its flee state. Cheap
        in practice since unshootable wildlife is a sparse, low-weight roster entry
        (see BIOME_LAIR_KIND_SETS), not a common enemy count."""
        wildlife = [e for e in self.enemies if e.alive and e.unshootable]
        if not wildlife:
            return
        for b in self.bullets:
            if b.owner == "enemy":
                continue
            for e in wildlife:
                if b.pos.distance_to(e.pos) <= FLEE_TRIGGER_RADIUS:
                    e.flee_time = FLEE_DURATION
                    e._flee_from = pygame.Vector2(b.pos)

    def _resolve_bullet_hits(self, players):
        remaining = []
        for b in self.bullets:
            consumed = False
            if b.owner == "enemy":
                for p in players.values():
                    if p.alive and b.hit_test(p.pos, p.radius):
                        real = p.take_damage(b.dmg)
                        self.events.append((p.pid, f"-{real} hp", (230, 90, 90)))
                        self.damage_popups.append((p.pos.x, p.pos.y, real, (255, 90, 90)))
                        consumed = True
                        break
            else:
                killer = players.get(b.owner)
                for e in self.enemies:
                    if e.unshootable:
                        continue  # ambient wildlife - bullets pass straight through, never a valid target
                    if e.alive and b.hit_test(e.pos, e.radius):
                        killed = e.take_damage(b.dmg)
                        self.damage_popups.append((e.pos.x, e.pos.y, e._last_hit_damage, (255, 220, 90)))
                        if b.status_effect == "bleed":
                            e.bleed_time = BLEED_DURATION
                            e.bleed_dps = b.dmg * BLEED_DPS_FRACTION
                            e.status_source_pid = b.owner
                            self.vfx_events.append(("bleed_tick", e.pos.x, e.pos.y, (200, 30, 30)))
                        elif b.status_effect == "burn":
                            e.burn_time = BURN_DURATION
                            e.burn_dps = b.dmg * BURN_DPS_FRACTION
                            e.status_source_pid = b.owner
                            self.vfx_events.append(("burn_tick", e.pos.x, e.pos.y, (255, 130, 30)))
                        elif b.status_effect == "vulnerable":
                            e.vulnerable_time = VULNERABLE_DURATION
                            e.vulnerable_mult = VULNERABLE_MULT
                            e.status_source_pid = b.owner  # consistent with bleed/burn above, even
                            # though vulnerable deals no direct damage itself today (no live bug from
                            # the omission, found via audit - kept consistent for whichever future
                            # code path might read status_source_pid expecting it to always be current)
                            self.vfx_events.append(("vulnerable_mark", e.pos.x, e.pos.y, (230, 200, 90)))
                        if not killed:
                            self.sound_events.append(("mob_hit", sound_family(e.kind), e.pos.x, e.pos.y))
                        if killed:
                            self._reward(e, killer)
                        if killer is not None and killer.cls_name == "priest":
                            # Actually building the "staff attacks heal allies on hit" behavior
                            # CLASS_DESC already promises for Priest but the game never wired up
                            # (UT procs, including this one, are flavor-text only per the README's
                            # Known Limitations) - modest, passive, every hit, not just UT weapons.
                            self._priest_heal_on_hit(killer, players)
                        if b.pierce > 0:
                            b.pierce -= 1
                        else:
                            consumed = True
                        break
                if not consumed:
                    for ob in self.obstacles:
                        if ob.alive and b.hit_test(ob.pos, ob.radius):
                            ob.take_damage(b.dmg)
                            self.vfx_events.append(("death", ob.pos.x, ob.pos.y, (150, 130, 100)))
                            if b.pierce > 0:
                                b.pierce -= 1
                            else:
                                consumed = True
                            break
            if not consumed:
                remaining.append(b)
        self.bullets = remaining
        self.obstacles = [ob for ob in self.obstacles if ob.alive]

    def _priest_heal_on_hit(self, caster, players):
        """A small passive heal to every nearby ally on every Priest hit - see
        player_fire's priest branch. PRIEST_HEAL_RADIUS is deliberately smaller
        than the ability's own SUPPORT_RADIUS: this is a combat-uptime trickle,
        not a substitute for actually casting Tome of Mending."""
        healed_any = False
        for ally in players.values():
            if ally.alive and ally.hp < ally.hp_max and ally.pos.distance_to(caster.pos) <= PRIEST_HEAL_RADIUS:
                ally.hp = min(ally.hp_max, ally.hp + PRIEST_HEAL_ON_HIT)
                healed_any = True
        if healed_any:
            self.vfx_events.append(("heal", caster.pos.x, caster.pos.y, (110, 230, 140)))

    def _grant_achievement(self, player, ach_id):
        changed, title = achievements.unlock(player.name, ach_id)
        if changed:
            player.title = title
            self.events.append((player.pid, f"Achievement unlocked: {player.name} {title}!", (255, 215, 90)))

    def _reward(self, enemy, killer):
        self.kill_count += 1
        death_color = (255, 140, 0) if enemy.rank == "boss" else (255, 200, 120)
        self.vfx_events.append(("death", enemy.pos.x, enemy.pos.y, death_color))
        self.sound_events.append(("mob_death", sound_family(enemy.kind), enemy.pos.x, enemy.pos.y))
        self._room_cleared_check(getattr(enemy, "room_idx", None))
        cls_for_loot = killer.cls_name if killer else "wizard"
        if killer:
            killer.kills += 1
            killer.gain_xp(RANK_XP[enemy.rank])
            if killer.kills == 1:
                self._grant_achievement(killer, "first_blood")
        loot_rolls = self.difficulty["loot_rolls"] if self.is_bonus_room else 1
        if enemy.moonlit:
            loot_rolls += 1  # a Moonlit kill always rolls at least one extra bag
        rolled_items = []
        for _ in range(loot_rolls):
            for bag_color, item in roll_loot(cls_for_loot, enemy.rank, enemy.difficulty_fraction):
                rolled_items.append((bag_color, item))
                if item.is_ut:
                    self.events.append((None, f"{item.name} dropped!", TIER_COLORS["ut"]))
        # a Dungeon Shard rides in the SAME loot bag as everything else this kill
        # dropped, instead of an ambient portal that pops up at the (soon-forgotten)
        # kill spot - it's a real carried item now, used later from the backpack
        # wherever the player happens to be standing (see Player.use_shard)
        dropped_shard_label = None
        if not self.is_bonus_room and enemy.rank == "elite" and random.random() < MOB_PORTAL_CHANCE:
            theme_name = THEME_FOR_KIND.get(enemy.kind, "generic")
            dropped_shard_label = DUNGEON_THEMES[theme_name]["label"]
            rolled_items.append(("brown", make_dungeon_shard(theme_name, dropped_shard_label)))
        if rolled_items:
            self._spawn_loot_bag(rolled_items, enemy.pos)
        self._progress_secret_quest(enemy)
        self._progress_phase2_quest(enemy)
        self._progress_island_event(enemy, killer)
        if enemy.rank == "boss":
            if enemy is self.boss:
                is_phase1 = not enemy.kind.endswith("_phase2")
                if self.secret_quest == "boss_timer" and self._quest_timer > 0 and is_phase1:
                    # "slay the boss swiftly" is judged on phase 1 going down within
                    # the limit, regardless of whether a phase 2 follows
                    self._complete_secret_quest()
                if self.is_bonus_room and is_phase1:
                    # the entrance portal's job (a way IN) is done the moment the main
                    # boss goes down at all - remove it whether or not a phase 2
                    # follows, matching "boss room starts with just the entrance
                    # portal" -> "on phase-1 death, remove the entrance portal"
                    self.portals = [pt for pt in self.portals if pt.kind != "entrance"]
                # Every main-boss death (phase-1 OR its later phase-2 continuation,
                # if any) now takes this SAME final path - phase-2 access is entirely
                # door/quest-gated (see _maybe_open_phase2_door), not a special portal
                # branch here anymore, so there's nothing left to special-case.
                self.boss = None
                if killer:
                    self._grant_achievement(killer, "dungeoneer" if self.is_bonus_room else "godslayer")
                if self.is_bonus_room:
                    # drop a fresh portal right where the boss died, instead of instantly
                    # ejecting the party - lets everyone finish looting first, and it's a
                    # second guaranteed way out beyond the entrance/R in case that's a
                    # long walk back. Phase-1 ALWAYS drops one now (even when a phase2
                    # pocket exists) - the later phase-2 death drops its OWN independent
                    # one too via this same branch, a safety net in case the first
                    # despawns (Portal.life=180s) before the player gets back to it.
                    self.portals.append(Portal(enemy.pos, life=180.0, kind="realm_exit"))
                    self.events.append((None, "The boss dropped a portal back to the Realm!", (255, 200, 90)))
                else:
                    self.events.append((None, "The avatar has been destroyed!", (255, 140, 0)))
                if is_phase1:
                    self._phase1_dead = True
                    self._maybe_open_phase2_door()
            else:
                # a boss-ranked kill that ISN'T the tracked main boss - the hidden
                # dungeon's "???" secret boss (see _complete_secret_quest). Loot/XP
                # already happened above via RANK_XP/roll_loot; this only needs its
                # own exit portal, not the main-boss bookkeeping/achievements.
                self.portals.append(Portal(enemy.pos, life=180.0, kind="realm_exit"))
                self.events.append((None, "The hidden boss falls! A portal opens.", (255, 200, 90)))
        elif dropped_shard_label:
            self.events.append((None, f"A Dungeon Shard ({dropped_shard_label}) dropped!", (190, 120, 230)))

    def _progress_secret_quest(self, enemy):
        if self.secret_quest == "kill_goons" and enemy.kind == self._quest_goon_kind:
            self.secret_quest_progress += 1
            if self.secret_quest_progress >= self._secret_quest_target:
                self._complete_secret_quest()
        elif self.secret_quest == "kill_totems" and enemy.kind == "totem":
            self.secret_quest_progress += 1
            if self.secret_quest_progress >= TOTEM_COUNT:
                self._complete_secret_quest()

    def _start_phase2_quest(self):
        kind, target = self._pick_achievable_goon_target()
        if kind is None:
            # no fixed-pod enemies existed to build a quest around (astronomically
            # unlikely) - don't leave phase-2 access permanently blocked on a quest
            # that could never even start; treat it as trivially already satisfied
            self.phase2_quest_done = True
            return
        self.phase2_quest = PHASE2_QUEST_KIND
        self._phase2_quest_goon_kind = kind
        self._phase2_quest_target = target
        self.events.append((None, f'A whisper echoes: "{PHASE2_QUEST_LABEL}..."', (255, 170, 140)))

    def _progress_phase2_quest(self, enemy):
        if self.phase2_quest != PHASE2_QUEST_KIND or enemy.kind != self._phase2_quest_goon_kind:
            return
        self.phase2_quest_progress += 1
        if self.phase2_quest_progress >= self._phase2_quest_target:
            self.phase2_quest = None
            self.phase2_quest_done = True
            self._maybe_open_phase2_door()

    def _maybe_open_phase2_door(self):
        """Only actually opens once BOTH the quest is done AND the phase-1 boss
        is confirmed dead - whichever of those two finishes last is the one
        that triggers this (see its two call sites: _progress_phase2_quest and
        _reward()'s phase-1 finalize branch). Keeps the intended difficulty
        curve intact (no early access to the harder phase-2 boss) while still
        letting the quest itself track/complete at any point during the run."""
        if self.phase2_door_open or not (self.phase2_quest_done and self._phase1_dead
                                          and self._phase2_pocket is not None):
            return
        self.phase2_door_open = True
        boss_room_tile = (int(self._boss_room_pos.x // TILE), int(self._boss_room_pos.y // TILE))
        world.open_phase2_door(self.realm_map.grid, self._phase2_pocket, boss_room_tile,
                                self.theme["floor"], theme_name=self.theme_key)
        pcx, pcy = self._phase2_pocket["center"]
        boss_pos = pygame.Vector2(pcx * TILE + TILE / 2, pcy * TILE + TILE / 2)
        self.boss = Enemy(f"{self._phase1_boss_kind}_phase2", boss_pos, level_scale=self.difficulty["enemy_scale"])
        self.enemies.append(self.boss)
        self.vfx_events.append(("boss_appear", boss_pos.x, boss_pos.y, (255, 90, 60)))
        self.events.append((None, "A passage rumbles open - the way to the boss's lair is clear!",
                             (255, 120, 90)))

    LOOT_RADIUS = 45
    LOOT_PREVIEW_RADIUS = 160  # the nearby-loot HUD panel shows bags within this range

    def _spawn_loot_bag(self, rarity_item_pairs, pos):
        """Pools items into one Bag - reuses a nearby, still-open, recently-created bag
        if one exists (so back-to-back kills near each other share a bag, matching
        RotMG's loot-bag feel), otherwise starts a fresh one. More than BAG_CAPACITY
        items overflow into additional bags rather than being lost. `rarity_item_pairs`
        is a list of (bag_color_key, Item) as returned by items.roll_loot()."""
        remaining = list(rarity_item_pairs)
        while remaining:
            target = next((b for b in self.ground_items
                            if not b.is_full() and b.age <= BAG_MERGE_WINDOW
                            and b.pos.distance_to(pos) <= BAG_MERGE_RADIUS), None)
            if target is None:
                drop_pos = pos + pygame.Vector2(random.uniform(-8, 8), random.uniform(-8, 8))
                target = Bag([], drop_pos)
                self.ground_items.append(target)
            while remaining and target.add_item(remaining[0][1], rarity_key=remaining[0][0]):
                remaining.pop(0)

    def nearby_ground_items(self, pos, radius=LOOT_PREVIEW_RADIUS):
        """Bags close enough to preview in the nearby-loot HUD panel, nearest first."""
        items = [g for g in self.ground_items if g.pos.distance_to(pos) <= radius]
        items.sort(key=lambda g: g.pos.distance_to(pos))
        return items

    def find_nearby_bag(self, pos, pid):
        """The closest bag in range that `pid` is allowed to open (right-click) - opens
        a drag-and-drop window rather than instantly granting an item, see ui.draw_bag_window."""
        return _find_nearby_bag(self.ground_items, pos, pid, radius=self.LOOT_RADIUS)

    def bag_by_id(self, bag_id):
        return _bag_by_id(self.ground_items, bag_id)

    def withdraw_from_bag(self, bag_id, idx, player):
        """Drags/clicks one item out of an open bag into the player's backpack."""
        item = _withdraw_from_bag(self.ground_items, bag_id, idx, player)
        if item is not None:
            self.events.append((player.pid, f"Picked up {item.display_name}", item.color))
        return item

    def _check_portal_entry(self, alive):
        for p in alive:
            for pt in self.portals:
                if pt.pos.distance_to(p.pos) < 22:
                    # pt.id lets co-op group multiple players who touch the SAME physical
                    # portal into the SAME dungeon instance (see server.py's
                    # ServerState.portal_instance_map) instead of each getting their own -
                    # single-player (main.py) only ever reads indices 0-3 of this tuple,
                    # so extra fields are safe, backward-compatible additions here.
                    # pt.target_pos is only ever non-None for "island_link" portals (see
                    # RealmSim._stamp_islands) - every other kind swaps to/from a separate
                    # RealmSim instance instead of repositioning within this one.
                    self.portal_entries.append((p.pid, pt.theme, pt.kind, pt.difficulty, pt.id, pt.target_pos))
                    break

    # -------------------------------------------------------------- weather --
    EMBER_TICK = 4.0
    EMBER_DMG = 1

    def _update_weather_damage(self, dt, alive):
        """The one real (non-cosmetic) weather gameplay hook: standing in the Ashlands
        during a Blood Moon means embers occasionally rain down and scorch you a
        little. Everywhere else weather is purely a client-side visual (see
        game/weather.py) plus the SNOW/ICE speed penalty already in world.SPEED_MULT."""
        if self.is_bonus_room or not self.blood_moon_active:
            return
        self._ember_cd -= dt
        if self._ember_cd > 0:
            return
        self._ember_cd = self.EMBER_TICK
        for p in alive:
            if self.realm_map.tile_at(p.pos.x, p.pos.y) == world.ASH:
                real = p.take_damage(self.EMBER_DMG)
                self.events.append((p.pid, "Embers scorch you!", (230, 120, 60)))
                self.damage_popups.append((p.pos.x, p.pos.y, real, (230, 120, 60)))

    # -------------------------------------------------------------- fishing --
    def _near_water(self, pos):
        return not self.is_bonus_room and self.realm_map.near_water(pos.x, pos.y, radius=FISH_RANGE)

    def _update_fishing(self, dt, players):
        for p in players.values():
            fs = p.fishing_state
            if fs is None:
                continue
            fs["timer"] -= dt
            if fs["phase"] == "casting" and fs["timer"] <= 0:
                fs["phase"] = "biting"
                fs["timer"] = FISH_BITE_WINDOW
                self.events.append((p.pid, "A fish is biting! Press F!", (140, 210, 255)))
            elif fs["phase"] == "biting" and fs["timer"] <= 0:
                p.fishing_state = None
                p.fish_cd = FISH_COOLDOWN
                self.events.append((p.pid, "The fish got away...", (170, 170, 180)))

    FISH_TABLE_WEIGHTS = [45, 30, 20, 5]  # junk / tiered gear / egg / UT-ish rare

    def fish_action(self, player):
        """Space is for abilities, F is for fishing/wishing - press near a WATER tile
        to cast, then press again during the brief bite window to reel it in. Every
        outcome is pushed through self.events (the single feed pipeline both single
        -player and co-op read from - see RealmSim.begin_tick()) rather than also
        being returned for the caller to push a second time; the return value here
        is just (item_or_None, message) for a caller that wants to react immediately
        (e.g. playing a sound), not for re-displaying the message itself."""
        if player.fishing_state is None:
            if not self._near_water(player.pos):
                msg = "You need to be near water to fish"
                self.events.append((player.pid, msg, (220, 150, 90)))
                return None, msg
            if player.fish_cd > 0:
                return None, None
            player.fishing_state = {"phase": "casting", "timer": random.uniform(*FISH_CAST_TIME)}
            msg = "You cast your line..."
            self.events.append((player.pid, msg, (150, 190, 220)))
            return None, msg
        if player.fishing_state["phase"] == "casting":
            msg = "Not yet... wait for the bite"
            self.events.append((player.pid, msg, (170, 170, 180)))
            return None, msg
        # phase == "biting": a successful reel
        player.fishing_state = None
        player.fish_cd = FISH_COOLDOWN
        roll = random.choices(["junk", "tiered", "egg", "rare"], weights=self.FISH_TABLE_WEIGHTS)[0]
        if roll == "junk":
            item = make_potion(random.choice(STAT_KEYS))
        elif roll == "tiered":
            item = _random_tiered(player.cls_name, lo=1, hi=7)
        elif roll == "egg":
            item = _random_egg()
        else:
            item = _random_ut(player.cls_name)
            self.vfx_events.append(("jackpot", player.pos.x, player.pos.y, item.color))
        if not player.try_pickup(item):
            msg = "Caught something, but your bag is full!"
            self.events.append((player.pid, msg, (220, 150, 90)))
            return None, msg
        self._grant_achievement(player, "angler")
        msg = f"You caught {item.display_name}!"
        self.events.append((player.pid, msg, item.color))
        return item, msg

    # -------------------------------------------------------------- input --
    def player_fire(self, p, direction, bullets_out_owner=None):
        """
        Builds the bullet(s) for one shot from player `p` aimed at `direction`,
        matching the per-class weapon behaviour. Returns the list of Bullets
        (already appended to self.bullets) so a caller can also broadcast them.
        """
        from game.constants import damage_roll
        p._fire_flash_t = p.FIRE_FLASH_DURATION  # brief recoil-nudge + tint - see Player.draw()
        dmg = damage_roll(p.weapon.min_dmg, p.weapon.max_dmg, p.total_stat("att"))
        motion = ("boomerang" if p.weapon.is_ut and p.weapon.name == BOOMERANG_UT_NAMES.get(p.cls_name)
                  else "straight")
        status_effect = None
        if p.weapon.is_ut:
            if p.weapon.name == BLEED_UT_NAMES.get(p.cls_name):
                status_effect = "bleed"
            elif p.weapon.name == BURN_UT_NAMES.get(p.cls_name):
                status_effect = "burn"
            elif p.weapon.name == VULNERABLE_UT_NAMES.get(p.cls_name):
                status_effect = "vulnerable"
        # per-class projectile shape hint (see sprites.bullet_surface) - a real shape
        # difference per category, not just the color each branch below already sets
        shape = {"archer": "arrow", "warrior": "blade", "paladin": "blade",
                 "rogue": "star", "assassin": "star", "priest": "holy",
                 "necromancer": "bone"}.get(p.cls_name, "orb")  # wizard falls through to "orb"
        made = []
        if p.cls_name == "archer":
            # Archer is the only class that fires 3 simultaneous bullets/shot - without
            # a compensating cut, that's a straight 3x damage multiplier no other class
            # gets (measured ~88 DPS vs ~17-38 DPS for everyone else at matching gear).
            # ARCHER_MULTISHOT_DMG_DIVISOR brings realized DPS down to ~29 - matching real
            # RotMG, where Archer is mid-pack DPS (tied 5th of the roster), not the top -
            # rather than 2-5x every other class here. The spread itself is untouched,
            # it's Archer's identity, not the problem.
            per_bullet_dmg = max(1, round(dmg / ARCHER_MULTISHOT_DMG_DIVISOR))
            for off in (-6, 0, 6):
                made.append(_mk_bullet(p.pos, direction.rotate(off), 420, per_bullet_dmg, (120, 230, 140),
                                        owner=p.pid, radius=4, motion=motion, status_effect=status_effect, shape=shape))
        elif p.cls_name in ("warrior", "paladin"):
            # melee "sword swing": short range on purpose, but 0.18s (47px) was so short
            # you had to be nearly on top of the target to ever land it - bumped to a
            # usable ~100px, still clearly shorter than ranged classes or rogue/assassin's 75px.
            # A boomerang UT gets a longer lifetime instead of the usual 0.4s - otherwise
            # there's no time left in its life to ever curve back and land a return hit.
            color = (230, 230, 240) if p.cls_name == "warrior" else (140, 180, 255)
            melee_life = 0.9 if motion == "boomerang" else 0.4
            made.append(_mk_bullet(p.pos, direction, 260, int(dmg * 1.4), color, owner=p.pid, radius=8,
                                    lifetime=melee_life, motion=motion, status_effect=status_effect, shape=shape))
            self.vfx_events.append(("melee_swing", p.pos.x, p.pos.y, color))
        elif p.cls_name in ("rogue", "assassin"):
            color = (200, 200, 60) if p.cls_name == "rogue" else (200, 60, 60)
            melee_life = 0.9 if motion == "boomerang" else 0.22
            made.append(_mk_bullet(p.pos, direction, 340, dmg, color, owner=p.pid, radius=5,
                                    lifetime=melee_life, motion=motion, status_effect=status_effect, shape=shape))
            self.vfx_events.append(("melee_swing", p.pos.x, p.pos.y, color))
        elif p.cls_name == "priest":
            # Priest's own branch, split out from the wizard/necromancer fallback below -
            # "piercing shots" is Priest's real RotMG identity, always on (not gated
            # behind owning a UT weapon like wizard/necromancer keep), giving Priest a
            # mechanical distinction instead of behaving identically to Wizard.
            made.append(_mk_bullet(p.pos, direction, 380, dmg, (255, 235, 150), owner=p.pid,
                                    pierce=PRIEST_PIERCE, radius=5, motion=motion, status_effect=status_effect, shape=shape))
        else:
            pierce = 2 if p.weapon.is_ut else 0
            color = (150, 120, 255) if p.cls_name == "wizard" else (150, 255, 180)  # necromancer
            made.append(_mk_bullet(p.pos, direction, 380, dmg, color, owner=p.pid, pierce=pierce, radius=5,
                                    motion=motion, status_effect=status_effect, shape=shape))
        self.bullets.extend(made)
        return made

    ABILITY_GCD = 1.0     # global cooldown so an ability can't be spammed even with MP to spare
    NOVA_RADIUS = 110
    SUPPORT_RADIUS = 130  # heal/haste range from the caster
    TELEGRAPH_DELAY = 0.45  # nova/chain/drain/freeze: seconds between cast (warning vfx) and actual
    # impact - a real, dodgeable window instead of an instant undodgeable AoE (RotMG bullet-hell convention)

    def use_ability(self, caster, target_pos, allies):
        """Space bar: casts whatever's in the caster's ability slot. `allies` is every
        player who should be eligible for a heal/haste (self in single-player, every
        co-op teammate in the same zone on the server). Returns (ok, feed_message)."""
        it = caster.ability
        if it is None or not it.effect:
            return False, "No ability equipped"
        if caster.ability_cd > 0:
            return False, None
        if caster.mp < it.mp_cost:
            return False, "Not enough MP"
        caster.mp -= it.mp_cost
        caster.ability_cd = self.ABILITY_GCD

        if it.effect in ("nova", "chain", "drain", "freeze"):
            # telegraphed, not instant: an immediate WARNING vfx marks exactly
            # where the impact will land, but the actual damage/effect doesn't
            # resolve until TELEGRAPH_DELAY later - a real, dodgeable window
            # (RotMG bullet-hell convention) instead of an undodgeable instant AoE
            self.vfx_events.append((f"{it.effect}_warning", target_pos[0], target_pos[1], it.color))
            self.pending_ability_effects.append({
                "effect": it.effect, "pos": pygame.Vector2(target_pos), "timer": self.TELEGRAPH_DELAY,
                "radius": self.NOVA_RADIUS, "magnitude": it.magnitude, "caster": caster,
            })
        elif it.effect == "heal":
            self.vfx_events.append(("heal", caster.pos.x, caster.pos.y, (110, 230, 140)))
            for ally in allies:
                if ally.alive and ally.pos.distance_to(caster.pos) <= self.SUPPORT_RADIUS:
                    healed = min(it.magnitude, ally.hp_max - ally.hp)
                    ally.hp += healed
                    if healed > 0:
                        self.damage_popups.append((ally.pos.x, ally.pos.y, int(healed), (110, 230, 140)))
        elif it.effect == "haste":
            self.vfx_events.append(("haste", caster.pos.x, caster.pos.y, (255, 230, 120)))
            for ally in allies:
                if ally.alive and ally.pos.distance_to(caster.pos) <= self.SUPPORT_RADIUS:
                    ally.haste_time = max(ally.haste_time, it.magnitude)
        elif it.effect == "shield":
            self.vfx_events.append(("shield", caster.pos.x, caster.pos.y, (100, 160, 230)))
            for ally in allies:
                if ally.alive and ally.pos.distance_to(caster.pos) <= self.SUPPORT_RADIUS:
                    ally.shield_hp = it.magnitude
                    ally.shield_time = self.SHIELD_DURATION
        self.events.append((caster.pid, f"{it.display_name}!", it.color))
        return True, f"{it.display_name}!"

    def _resolve_pending_ability_effects(self, dt):
        """Ticks every telegraphed nova/chain/drain/freeze cast (see
        use_ability()) and actually applies its damage/effect the moment its
        timer expires - called once per update() tick."""
        remaining = []
        for pe in self.pending_ability_effects:
            pe["timer"] -= dt
            if pe["timer"] > 0:
                remaining.append(pe)
                continue
            self._impact_ability_effect(pe)
        self.pending_ability_effects = remaining

    def _impact_ability_effect(self, pe):
        effect, pos, magnitude, caster, radius = pe["effect"], pe["pos"], pe["magnitude"], pe["caster"], pe["radius"]
        if effect == "nova":
            self.vfx_events.append(("nova", pos.x, pos.y, (170, 130, 255)))
            for e in self.enemies:
                if e.pos.distance_to(pos) <= radius:
                    killed = e.take_damage(magnitude)
                    self.damage_popups.append((e.pos.x, e.pos.y, e._last_hit_damage, (170, 130, 255)))
                    if killed:
                        self._reward(e, caster)
        elif effect == "chain":
            hit_ids = set()
            current = pygame.Vector2(pos)
            self.vfx_events.append(("chain", current.x, current.y, (140, 200, 255)))
            for _ in range(self.CHAIN_HOPS):
                cand = [e for e in self.enemies if id(e) not in hit_ids
                        and e.pos.distance_to(current) <= (radius if not hit_ids else self.CHAIN_RANGE)]
                if not cand:
                    break
                e = min(cand, key=lambda e: e.pos.distance_to(current))
                hit_ids.add(id(e))
                killed = e.take_damage(magnitude)
                self.damage_popups.append((e.pos.x, e.pos.y, e._last_hit_damage, (140, 200, 255)))
                self.vfx_events.append(("chain", e.pos.x, e.pos.y, (140, 200, 255)))
                if killed:
                    self._reward(e, caster)
                current = e.pos
        elif effect == "drain":
            total = 0
            self.vfx_events.append(("drain", pos.x, pos.y, (170, 40, 60)))
            for e in self.enemies:
                if e.pos.distance_to(pos) <= radius:
                    killed = e.take_damage(magnitude)
                    total += e._last_hit_damage  # lifesteal scales with REAL damage dealt, not the raw magnitude
                    self.damage_popups.append((e.pos.x, e.pos.y, e._last_hit_damage, (170, 40, 60)))
                    if killed:
                        self._reward(e, caster)
            if total > 0 and caster.alive:
                healed = min(total * 0.5, caster.hp_max - caster.hp)
                caster.hp += healed
                if healed > 0:
                    self.damage_popups.append((caster.pos.x, caster.pos.y, int(healed), (110, 230, 140)))
        elif effect == "freeze":
            self.vfx_events.append(("freeze", pos.x, pos.y, (150, 220, 255)))
            for e in self.enemies:
                if e.pos.distance_to(pos) <= radius:
                    killed = e.take_damage(magnitude)
                    self.damage_popups.append((e.pos.x, e.pos.y, e._last_hit_damage, (150, 220, 255)))
                    e.frozen_time = max(e.frozen_time, self.FREEZE_DURATION)
                    if killed:
                        self._reward(e, caster)

    CHAIN_HOPS = 4
    CHAIN_RANGE = 150
    FREEZE_DURATION = 2.5
    SHIELD_DURATION = 8.0
    ROOT_PULSE_RADIUS = 170  # the Thorn Warden's root pulse
    ROOT_DURATION = 2.5

    def tick_pets(self, dt, players):
        """Advances every connected player's pet - separate from update() since
        it needs the live enemy list (for "attack" pets) and each owning Player."""
        for p in players.values():
            if p.pet is not None:
                # a pet's heal/magic/attack abilities each run on their own cooldown
                # (see entities.Pet.update) and can ALL fire within the same tick, so
                # this is a list of 0+ events now, not a single Optional one
                for ev in p.pet.update(dt, p, self.enemies, self.bullets):
                    self.vfx_events.append(ev[:4])
                    if len(ev) > 4 and ev[4] > 0:
                        # heal/mana carry the real restored amount as a 5th field -
                        # surface it as a floating number over the player, same as
                        # every other heal source (priest, ability casts) already does
                        self.damage_popups.append((ev[1], ev[2], int(round(ev[4])), ev[3]))
