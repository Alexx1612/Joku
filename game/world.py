"""
Tile world: a small safe "Nexus" hub (RotMG's social lobby) plus a large
procedurally scattered open-field "Godlands"-style realm map with biome
patches, where enemies spawn and roam.
"""
import math
import os
import random
import pygame
from game import constants as C

REALM_W, REALM_H = 900, 900  # an immense continent - 1.27x the tile area of the previous
# 800x800 size (and far bigger still vs. v0.1's original small island).
# Benchmarked before picking this number (see the v0.2 changelog entry in README.md):
# make_realm() scales roughly with tile area, so 1200x1200 (~4.4s) and 1600x1600
# (~7.8s) both blew well past the ~3s "feels like loading, not hanging" budget for a
# one-time realm-creation pause, even after optimizing the generator (see _warp's
# precomputed sin/cos tables and the guaranteed-land/guaranteed-water early-outs
# below, both added specifically to buy headroom for a bigger map). 900x900 measured
# ~2.6s for a full RealmSim() (map + all lairs populated) on this dev machine, which
# already has real background load - the margin matters given a corporate laptop can
# get slower under things like AV scans, not just a cleaner benchmark box.
NEXUS_W, NEXUS_H = 64, 50    # a spectacular, huge Nexus hub - grand fountain plaza + statues
BAZAAR_W, BAZAAR_H = 32, 22  # a bigger marketplace, RotMG's Bazaar-with-a-fountain-plaza scale
BONUS_W, BONUS_H = 60, 60  # a real multi-room dungeon, not one small arena
VAULT_ROOM_W, VAULT_ROOM_H = 20, 16  # a small, fixed, hand-authored room - a vault should
# feel like the same trusted space every visit, not a randomized generator

(GRASS, GRASS2, DIRT, ROCK, WATER, NEXUS_FLOOR, PORTAL,
 BAZAAR_FLOOR, STALL, VAULT_TILE, BAZAAR_PORTAL, SAND, SWAMP, SNOW,
 STONE, ASH, JUNGLE, WASTELAND, ICE, CAVE, NEXUS_FOUNTAIN, NEXUS_BANNER,
 NEXUS_STATUE, WALL_VAULT, WALL_CAVE, WALL_FROST, WALL_JUNGLE, WALL_EMBER,
 WALL_GROTTO, WALL_SPIRE, NEXUS_GARDEN, NEXUS_WELL, NEXUS_BOARD, CHEST,
 VAULT_GOLD, VAULT_GEMS, VAULT_PILLAR, VAULT_COBWEB, VAULT_BOOKSHELF,
 VAULT_CANDELABRA, VAULT_SACK, VAULT_POTTERY, VAULT_RUNE) = range(43)

TILE_COLORS = {
    GRASS: C.COL_GRASS, GRASS2: C.COL_GRASS_DARK, DIRT: C.COL_DIRT,
    ROCK: C.COL_ROCK, WATER: C.COL_WATER, NEXUS_FLOOR: C.COL_NEXUS_FLOOR,
    PORTAL: (150, 60, 200), BAZAAR_FLOOR: (110, 90, 60), STALL: (150, 100, 40),
    VAULT_TILE: (90, 80, 130), BAZAAR_PORTAL: (60, 140, 200),
    SAND: C.COL_SAND, SWAMP: C.COL_SWAMP, SNOW: C.COL_SNOW,
    STONE: C.COL_STONE, ASH: C.COL_ASH,
    JUNGLE: C.COL_JUNGLE, WASTELAND: C.COL_WASTELAND, ICE: C.COL_ICE, CAVE: C.COL_CAVE,
    NEXUS_FOUNTAIN: (70, 130, 200), NEXUS_BANNER: (140, 40, 60),
    NEXUS_STATUE: (150, 145, 130),
    # per-dungeon-theme wall tiles - see DUNGEON_THEMES in realm_sim.py, which
    # picks one of these instead of plain ROCK so each theme's rooms actually
    # look distinct, not just a different floor colour inside the same grey box
    WALL_VAULT: (120, 105, 85), WALL_CAVE: (40, 34, 52), WALL_FROST: (150, 180, 200),
    WALL_JUNGLE: (70, 90, 60), WALL_EMBER: (45, 30, 26), WALL_GROTTO: (55, 65, 55),
    WALL_SPIRE: (150, 145, 135),
    # Nexus decorative-but-walkable dressing - flat-color fallbacks, real art is
    # the visual session's job (see the standing coordination message)
    NEXUS_GARDEN: (60, 110, 55), NEXUS_WELL: (90, 100, 120), NEXUS_BOARD: (110, 85, 55),
    CHEST: (130, 100, 40),
    # Vault room dressing (make_vault_room()) - flat-color fallbacks, real
    # hand-painted art in assets/sprites/v0.2/decorations/vault/
    VAULT_GOLD: (230, 192, 72), VAULT_GEMS: (122, 60, 184), VAULT_PILLAR: (140, 136, 124),
    VAULT_COBWEB: C.COL_NEXUS_FLOOR, VAULT_BOOKSHELF: (74, 52, 32), VAULT_CANDELABRA: (200, 162, 69),
    VAULT_SACK: (138, 100, 56), VAULT_POTTERY: (184, 120, 90), VAULT_RUNE: (122, 60, 184),
}
SOLID = {ROCK, STALL, NEXUS_BANNER, NEXUS_STATUE,
         WALL_VAULT, WALL_CAVE, WALL_FROST, WALL_JUNGLE, WALL_EMBER, WALL_GROTTO, WALL_SPIRE,
         VAULT_PILLAR, VAULT_BOOKSHELF, VAULT_CANDELABRA}
INTERACTIVE = {PORTAL, VAULT_TILE, BAZAAR_PORTAL, CHEST}
# water is walkable but slows you down - RotMG-ish "wading" feel instead of an
# invisible wall at every shoreline. Snow/ice give weather a real (if small) foot
# in gameplay, not just a screen effect - trudging through snow is genuinely slower.
SPEED_MULT = {WATER: 0.8, NEXUS_FOUNTAIN: 0.8, SNOW: 0.93, ICE: 0.88}

# which weather effect a ground tile implies (purely client-side particles, except
# where noted in realm_sim.py) - "try to make more of this a real ecosystem" extends
# to the sky, not just the mobs on the ground
# Godlands-style biome regions, each with its own ground tile and enemy-lair flavour -
# ten distinct zones (not just patches) spread across the continent, RotMG's real
# "beaches/lowlands at the edges, godlands in the middle" gradient (see
# BIOME_TIER below and _generate_lairs' distance-from-center difficulty scaling)
(BIOME_FOREST, BIOME_DESERT, BIOME_TUNDRA, BIOME_SWAMP, BIOME_HIGHLANDS, BIOME_ASHLANDS,
 BIOME_JUNGLE, BIOME_WASTELAND, BIOME_ICE, BIOME_CAVE) = range(10)
BIOME_GROUND = {
    BIOME_FOREST: GRASS, BIOME_DESERT: SAND, BIOME_TUNDRA: SNOW, BIOME_SWAMP: SWAMP,
    BIOME_HIGHLANDS: STONE, BIOME_ASHLANDS: ASH, BIOME_JUNGLE: JUNGLE,
    BIOME_WASTELAND: WASTELAND, BIOME_ICE: ICE, BIOME_CAVE: CAVE,
}
# "outer" biomes (RotMG's Beaches/Lowlands) seed near the coast and are gentler;
# "inner" biomes (Godlands-tier) seed toward the continent's center and are tougher -
# see _generate_lairs for how this turns into an actual difficulty gradient
BIOME_TIER_OUTER = [BIOME_FOREST, BIOME_DESERT, BIOME_TUNDRA, BIOME_SWAMP]
BIOME_TIER_INNER = [BIOME_HIGHLANDS, BIOME_ASHLANDS, BIOME_JUNGLE, BIOME_WASTELAND, BIOME_ICE, BIOME_CAVE]
GROUND_TO_BIOME_NAME = {
    GRASS: "forest", SAND: "desert", SNOW: "tundra", SWAMP: "swamp", STONE: "highlands",
    ASH: "ashlands", JUNGLE: "jungle", WASTELAND: "wasteland", ICE: "ice", CAVE: "cave",
}

# Overworld decoration props (make_realm()'s scattered rocks/bushes/trees/etc.) -
# 10 biomes x N hand-painted prop kinds each (assets/sprites/v0.2/decorations/
# biomes/<biome>/tile_biome_<biome>_<kind>_0.png), all walkable (never added
# to SOLID - a randomly-generated 900x900 continent has no way to guarantee
# ambient clutter never blocks a critical path, unlike the small hand-authored
# Vault room). Allocated as plain ints from a running counter instead of
# hand-typed named constants (would be pure repetition) -
# BIOME_PROP_TILE[(biome_name, kind)] -> tile id is how make_realm() and the
# texture-loading below both look them up.
BIOME_PROP_KINDS = ["rock", "bush", "flowers", "boulder", "puddle", "skull", "stump", "grasstuft", "debris", "tree",
                     "vine", "small_pile", "moss_patch", "cracked_ground", "mushroom_cluster",
                     "root_tangle", "cobweb", "rune_marking", "fallen_log", "ash_pile", "gravel_patch",
                     "water_stain",
                     # 5 more (was 22, now 27) - kept to 5, not the 8 first considered, so
                     # 10 biomes x 27 kinds = 270 ids stays safely under the dungeon-prop
                     # block's 800 start with a real buffer (500+270=770), matching this
                     # file's own established id-spacing convention rather than crowding
                     # right up against the next block like the earlier 15->22 growth did
                     "pebbles", "wildflower_patch", "dead_tree", "berry_bush", "reed_cluster"]
# Per-biome WEIGHTED selection (mirrors BIOME_LAIR_KIND_SETS' existing weighted-
# random.choices pattern) instead of a uniform random.choice across the whole
# shared list - "more flowers/trees/rocks matching the biome" actually means
# something now: forest leans tree/bush/flowers, desert leans rock/boulder/
# gravel, swamp leans reed/puddle/moss, etc. A biome not listed here (or a
# kind not listed for it) falls back to weight 1, so nothing is ever excluded
# outright - just skewed toward what actually belongs there.
BIOME_PROP_WEIGHT_OVERRIDES = {
    "forest": {"tree": 6, "bush": 5, "flowers": 4, "wildflower_patch": 4, "berry_bush": 3, "grasstuft": 3},
    "desert": {"rock": 5, "boulder": 5, "gravel_patch": 4, "skull": 3, "cracked_ground": 3, "pebbles": 3},
    "swamp": {"puddle": 5, "moss_patch": 4, "reed_cluster": 5, "water_stain": 4, "mushroom_cluster": 3},
    "tundra": {"stump": 4, "dead_tree": 4, "debris": 3, "fallen_log": 3, "rock": 2},
    "highlands": {"rock": 5, "boulder": 5, "gravel_patch": 4, "pebbles": 4, "cracked_ground": 3},
    "ashlands": {"ash_pile": 6, "skull": 4, "cracked_ground": 4, "dead_tree": 4, "debris": 3},
    "jungle": {"tree": 6, "vine": 5, "mushroom_cluster": 4, "root_tangle": 4, "berry_bush": 3},
    "wasteland": {"skull": 5, "debris": 5, "gravel_patch": 4, "dead_tree": 3, "ash_pile": 3},
    "ice": {"rock": 3, "boulder": 3, "dead_tree": 3, "debris": 2},
    "cave": {"mushroom_cluster": 5, "cobweb": 5, "rune_marking": 3, "root_tangle": 3, "small_pile": 3},
}


def _biome_prop_weights(biome_name):
    overrides = BIOME_PROP_WEIGHT_OVERRIDES.get(biome_name, {})
    return [overrides.get(k, 1) for k in BIOME_PROP_KINDS]
BIOME_PROP_TILE = {}
# Starts at 500, NOT right after VAULT_RUNE=42 - deliberately leaves a large
# gap (43-499) for the shared tile-enum block above to keep growing without
# ever colliding with these. NOTE: this whole id block was RENUMBERED when
# BIOME_PROP_KINDS grew from 15 to 22 kinds (10 biomes x 22 = 220 ids, which
# would have overrun the dungeon-prop block's old 700 start) - these ids are
# never persisted (grids are regenerated fresh every RealmSim instance, never
# saved to disk or carried across a version), so renumbering the whole scheme
# here is safe. Current block map: biome props 500-769 (grew from 22 to 27
# kinds - kept to +5, not +8, specifically to preserve a real buffer before
# the next block), dungeon props 800-960, tall props 1000-1101, building
# walls 1150-1159 - each block leaves a real buffer before the next, matching
# this file's established spacing convention. Keep this comment's numbers in
# sync if any block grows again.
_next_biome_prop_id = 500
for _biome_name in GROUND_TO_BIOME_NAME.values():
    for _kind in BIOME_PROP_KINDS:
        BIOME_PROP_TILE[(_biome_name, _kind)] = _next_biome_prop_id
        _next_biome_prop_id += 1

# Flat-color fallback for every biome-prop id: reuse that biome's own ground
# tile color (already in TILE_COLORS) - a reasonable "blends with the biome"
# default for the rare case the PNG fails to load, given the hand-painted art
# (which always loads in practice) is what actually renders.
for (_biome_name, _kind), _tile_id in BIOME_PROP_TILE.items():
    _ground_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == _biome_name)
    TILE_COLORS[_tile_id] = TILE_COLORS[_ground_tile]

# Every tile id (ground OR decoration) resolved back to its owning biome name -
# fixes a real bug: weather used to be looked up by the EXACT tile id underfoot
# (WEATHER_FOR_GROUND, keyed only by the 10 base ground ids below), so standing
# on any decoration tile (a rock/bush/flower/etc - a DIFFERENT id) made the
# lookup return nothing and silently turn weather off mid-biome. Resolving
# through the biome NAME first means weather now stays stable across an
# entire biome region regardless of which exact tile is underfoot.
TILE_TO_BIOME_NAME = dict(GROUND_TO_BIOME_NAME)
for (_biome_name, _kind), _tile_id in BIOME_PROP_TILE.items():
    TILE_TO_BIOME_NAME[_tile_id] = _biome_name

WEATHER_FOR_BIOME = {
    "forest": "rain", "swamp": "rain", "jungle": "rain",
    "tundra": "snow", "ice": "snow",
    "desert": "sand", "wasteland": "sand",
    "ashlands": "ash",
    # "highlands"/"cave" intentionally absent - no weather, matching
    # WEATHER_FOR_GROUND's existing omission of STONE/CAVE
}


def weather_for_tile(tile_id):
    """Resolves ANY tile id - ground or decoration - to its biome's weather
    kind (or None). Use this instead of the old WEATHER_FOR_GROUND.get(tile)
    everywhere weather is looked up from the player's current tile."""
    return WEATHER_FOR_BIOME.get(TILE_TO_BIOME_NAME.get(tile_id))


# Dungeon-theme decoration props (make_bonus_room()) - 7 themes x N shared
# hand-painted prop kinds + 1 unique special per theme
# (assets/sprites/v0.2/decorations/dungeons/<theme>/tile_dungeon_<theme>_
# <kind>_0.png). Mirrors BIOME_PROP_TILE's pattern exactly. Starts at 800
# (see the renumbering note above biome props for why - was 700, bumped to
# leave room for biome props' now-larger 500-719 range).
# DUNGEON_THEME_FLOOR duplicates realm_sim.DUNGEON_THEMES' floor-tile choices
# locally (world.py can't import realm_sim - realm_sim imports world) purely
# so the fallback color loop below has something to key off of at import
# time; keep the two in sync if a theme's floor changes.
DUNGEON_THEME_FLOOR = {
    "generic": GRASS2, "cave": CAVE, "frozen_crypt": ICE, "jungle_ruins": JUNGLE,
    "ember_den": ASH, "sunken_grotto": SWAMP, "wind_spire": STONE,
}
DUNGEON_PROP_KINDS = ["torch", "rubble", "tapestry", "idol", "crate", "bones",
                       "crystal", "growth", "puddle", "chains",
                       "vine", "small_pile", "moss_patch", "cracked_ground", "mushroom_cluster",
                       "root_tangle", "cobweb", "rune_marking", "fallen_log", "ash_pile", "gravel_patch",
                       "water_stain"]
# one extra unique prop per theme, on top of the shared kinds above
DUNGEON_SPECIAL_KIND = {
    "generic": "urn", "cave": "stalactites", "frozen_crypt": "coffin",
    "jungle_ruins": "pillar", "ember_den": "vent", "sunken_grotto": "mushroom",
    "wind_spire": "tatters",
}
DUNGEON_PROP_TILE = {}
_next_dungeon_prop_id = 800
for _theme_name in DUNGEON_THEME_FLOOR:
    for _kind in DUNGEON_PROP_KINDS + [DUNGEON_SPECIAL_KIND[_theme_name]]:
        DUNGEON_PROP_TILE[(_theme_name, _kind)] = _next_dungeon_prop_id
        _next_dungeon_prop_id += 1

for (_dp_theme, _dp_kind), _dp_id in DUNGEON_PROP_TILE.items():
    TILE_COLORS[_dp_id] = TILE_COLORS[DUNGEON_THEME_FLOOR[_dp_theme]]

# unlike biome props (always walkable - see BIOME_PROP_TILE's comment), a
# hand-authored dungeon room CAN guarantee these never block the only path,
# so the bulkier/statue-like kinds are solid for a more physical-feeling room
DUNGEON_PROP_SOLID_KINDS = {"idol", "crate", "crystal", "coffin", "pillar", "urn"}
SOLID.update(tid for (_dp_theme, _dp_kind), tid in DUNGEON_PROP_TILE.items()
             if _dp_kind in DUNGEON_PROP_SOLID_KINDS)

# every torch prop tile id, across all dungeon themes - used by the night
# lightmap (ui.draw_day_night_overlay) to find nearby light sources
TORCH_TILE_IDS = {tid for (_dp_theme, _dp_kind), tid in DUNGEON_PROP_TILE.items() if _dp_kind == "torch"}


def nearby_torch_world_positions(tile_map, center_x, center_y, radius_tiles=6):
    """World-space (x, y) centers of every torch tile within radius_tiles of
    (center_x, center_y) - a small bounded scan (not the whole map), safe to
    call once per frame from the night-lightmap draw call."""
    cx, cy = int(center_x // C.TILE), int(center_y // C.TILE)
    positions = []
    for gy in range(max(0, cy - radius_tiles), min(tile_map.h, cy + radius_tiles + 1)):
        for gx in range(max(0, cx - radius_tiles), min(tile_map.w, cx + radius_tiles + 1)):
            if tile_map.grid[gy][gx] in TORCH_TILE_IDS:
                positions.append(((gx + 0.5) * C.TILE, (gy + 0.5) * C.TILE))
    return positions

# ------------------------------------------------------------ tall props --
# Semi-3D decoration: tiles rendered TALLER than one tile (see
# sprites.tall_prop_sprite, ~1.6x tile height) and anchored at their OWN
# bottom edge so they visually extend upward past their tile's top edge - a
# real height cue, not just a flat top-down texture. Placed inside the
# Part-1 landmark buildings (biomes, see stamp_lair_building below) AND now
# also inside dungeon rooms (see make_bonus_room's tall-prop placement) -
# TALL_PROP_TILE is keyed by (area_name, kind) where area_name is EITHER a
# biome name OR a dungeon theme name, both looked up the same way. Unlike
# BIOME_PROP_TILE/DUNGEON_PROP_TILE (which fully REPLACE a tile's texture,
# always 100% opaque, confirmed by direct measurement - see the decoration-
# sprite postmortem), a tall prop's own art has a genuinely transparent
# background and does NOT replace the floor - TileMap.draw() explicitly
# draws the underlying ground/floor tile first (via TALL_PROP_BASE_GROUND's
# reverse lookup), THEN defers the tall sprite itself to a y-sorted overlay
# pass drawn after the full tile-floor sweep. Starts at 1000 (see the
# renumbering note above biome props). NOT added to SOLID - a walkable
# decorative accent, matching every other prop kind's own default.
TALL_PROP_KINDS = ["totem", "pole", "pillar", "banner_pole", "brazier", "signpost"]  # purely
# decorative TILE kinds - "totem" here is unrelated to entities.ENEMY_KINDS["totem"]
# (a damageable enemy from the secret-quest system), different registry entirely,
# name overlap is coincidental
TALL_PROP_TILE = {}
TALL_PROP_BASE_GROUND = {}
_next_tall_prop_id = 1000
# dungeon theme names get a "dungeon:" prefix in this dict's key ONLY (never
# in DUNGEON_PROP_TILE/DUNGEON_THEME_FLOOR etc.) - a real bug caught while
# writing this: the "cave" BIOME and the "cave" DUNGEON THEME are both
# literally named "cave", so an unprefixed shared (area_name, kind) key
# would silently collide and overwrite one's ids with the other's, losing
# an entire area's worth of tall props with no error. stamp_lair_building()
# (biomes) keys lookups with the bare biome name as before, unaffected;
# make_bonus_room()'s dungeon-side tall-prop placement must use
# f"dungeon:{theme_name}" as the first element of the lookup tuple.
_tall_prop_areas = [(_name, _tile) for _tile, _name in GROUND_TO_BIOME_NAME.items()]  # (area_name, base_ground_tile)
_tall_prop_areas += [(f"dungeon:{_theme}", DUNGEON_THEME_FLOOR[_theme]) for _theme in DUNGEON_THEME_FLOOR]
for _area_name, _base_ground in _tall_prop_areas:
    for _kind in TALL_PROP_KINDS:
        TALL_PROP_TILE[(_area_name, _kind)] = _next_tall_prop_id
        TALL_PROP_BASE_GROUND[_next_tall_prop_id] = _base_ground
        TILE_COLORS[_next_tall_prop_id] = TILE_COLORS[_base_ground]  # flat fallback if art is ever missing
        _next_tall_prop_id += 1
TALL_PROP_TILE_IDS = set(TALL_PROP_TILE.values())
TALL_PROP_KIND_BY_ID = {v: k for (_area, k), v in TALL_PROP_TILE.items()}

# Nexus decoration props - a THIRD decoration architecture alongside biome/
# dungeon props: the Nexus is a single fixed hand-authored map (make_nexus()),
# not a randomly-classified area, so there's no (area_name, kind) multiplication
# here - just kind -> id directly. 7 flat ground-texture kinds (same fully-
# opaque tile-replacing convention as BIOME_PROP_TILE/DUNGEON_PROP_TILE - see
# the decoration-sprite postmortem for why "fully opaque" matters) plus 3 of
# the already-existing TALL_PROP_KINDS (banner_pole/brazier/signpost - fit a
# social hub; totem/pole/pillar are left as biome/dungeon-only, not added
# here) reusing the SAME shared TALL_PROP_TILE/TALL_PROP_BASE_GROUND
# mechanism via area_name="nexus" (no collision risk - no biome or dungeon
# theme is named "nexus", unlike the earlier "cave" biome-vs-theme scare).
# Starts at 1200 - the highest id in use anywhere (BUILDING_WALL_TILE,
# 1150-1159) leaves a safety buffer below this.
NEXUS_PROP_KINDS = ["banner_tapestry", "flower_bed", "cobblestone_patch", "lantern_glow",
                     "mosaic_tile", "ivy_patch", "well_stain"]
NEXUS_TALL_PROP_KINDS = ["banner_pole", "brazier", "signpost"]
NEXUS_PROP_TILE = {}
_next_nexus_prop_id = 1200
for _nx_kind in NEXUS_PROP_KINDS:
    NEXUS_PROP_TILE[_nx_kind] = _next_nexus_prop_id
    TILE_COLORS[_next_nexus_prop_id] = TILE_COLORS[NEXUS_FLOOR]
    _next_nexus_prop_id += 1
for _nx_kind in NEXUS_TALL_PROP_KINDS:
    TALL_PROP_TILE[("nexus", _nx_kind)] = _next_nexus_prop_id
    TALL_PROP_BASE_GROUND[_next_nexus_prop_id] = NEXUS_FLOOR
    TILE_COLORS[_next_nexus_prop_id] = TILE_COLORS[NEXUS_FLOOR]
    TALL_PROP_TILE_IDS.add(_next_nexus_prop_id)
    TALL_PROP_KIND_BY_ID[_next_nexus_prop_id] = _nx_kind
    _next_nexus_prop_id += 1

# The Echo Keeper (Batch 12) - a single interactive Nexus tile where a
# permadeath run's earned "Echoes" currency is spent on permanent, power-
# neutral unlocks (see game/accounts.py). Its own id, right after the Nexus
# prop block above (1200-1209) - _next_nexus_prop_id is already sitting at
# 1210 at this point, so this can't collide with anything.
ECHO_KEEPER_TILE = _next_nexus_prop_id
_next_nexus_prop_id += 1
TILE_COLORS[ECHO_KEEPER_TILE] = (80, 200, 190)
INTERACTIVE.add(ECHO_KEEPER_TILE)

# Landmark-building exterior walls (see stamp_lair_building below) - one
# hand-painted per-biome wall texture (a stone/wood/ice/etc. base with a
# darker "roof eave" band across its top ~14px, so a building reads as a
# real structure with a roof overhang, not the plain flat ROCK every other
# open-Realm rock outcrop uses) instead of reusing plain ROCK for these 10
# buildings specifically. Starts at 1150 (see the renumbering note above
# biome props - was 1000, bumped since tall props now occupy 1000-1101).
BUILDING_WALL_TILE = {}
_next_building_wall_id = 1150
for _biome_name in GROUND_TO_BIOME_NAME.values():
    _ground_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == _biome_name)
    BUILDING_WALL_TILE[_biome_name] = _next_building_wall_id
    TILE_COLORS[_next_building_wall_id] = TILE_COLORS[_ground_tile]  # flat fallback if art is ever missing
    _next_building_wall_id += 1
SOLID.update(BUILDING_WALL_TILE.values())
# A lair building's wall ring renders correctly (real texture, real two-tone
# shading) but visually blends into ambient natural rock/cliff SOLID tiles of
# a similar dark shade when they happen to sit nearby - confirmed by a real
# rendered screenshot comparison, not assumed - so a building doesn't read as
# "a constructed structure" at normal gameplay viewing distance even though
# up close its walls are perfectly visible. Used below to give building
# walls their own warmer, more saturated outline/shading distinct from
# natural stone, regardless of what's next to them.
BUILDING_WALL_TILE_IDS = set(BUILDING_WALL_TILE.values())

# ------------------------------------------------------- island zones -----
# "The Reforging" storyline (see RealmSim._stamp_islands): 10 small
# standalone island zones stamped as coastal peninsulas jutting out of the
# existing continent's own coastline, 5 "shard" (land-shattered, charged
# rubble/ember) + 5 "choir" (drowned temple, coral/pearl) themed. Each is a
# self-contained curated micro-zone with its own ground tile, decoration
# kinds, and a central landmark - NOT a biome (no entry in BIOME_GROUND/
# BIOME_TIER_*, never touched by the biome-affinity classification), and NOT
# a walled room like stamp_lair_building - an island is carved as an organic
# circular patch (see stamp_island below), reading as a real landmass rather
# than a building. Reuses existing, already-painted ground tiles (ASH for
# shard/ember, SAND for choir/beach) so islands look good with zero new
# ground-tile art, matching this file's own "ships correct on existing/
# procedural art" precedent (see BIOME_PROP_TILE's fallback-color comment).
ISLAND_GROUND = {"island_shard": ASH, "island_choir": SAND}
ISLAND_PROP_KINDS = {
    "island_shard": ["cracked_pillar", "ember_vent", "floating_shard_chunk", "rune_scorch",
                      "fury_crystal", "broken_statue", "ash_drift", "shard_brazier",
                      "rubble_pile", "scorched_banner"],
    "island_choir": ["coral_cluster", "pearl_shell", "drowned_altar", "kelp_strand",
                      "barnacle_rock", "tide_pool", "sunken_bell", "driftwood_arch",
                      "anemone_bloom", "choir_lantern"],
}
# the central landmark per island theme reuses an EXISTING TALL_PROP_KINDS
# kind (tall_prop_sprite() renders purely by kind, "one universal look per
# kind, not per-biome" - sprites.py:1081 - so no new art/kind is needed for
# the landmark itself, just a new (area_name, kind) tile id so the floor
# UNDER it renders as this island's own ground rather than an unrelated
# biome's, via TALL_PROP_BASE_GROUND below)
ISLAND_LANDMARK_KIND = {"island_shard": "totem", "island_choir": "pillar"}
ISLAND_PROP_TILE = {}
# Starts at 1300 (see the renumbering note above biome props - the highest
# id in use anywhere before this block is the Nexus's ~1210) - deliberately
# leaves a real buffer, matching this file's own spacing convention.
_next_island_id = 1300
for _isl_area, _isl_kinds in ISLAND_PROP_KINDS.items():
    for _isl_kind in _isl_kinds:
        ISLAND_PROP_TILE[(_isl_area, _isl_kind)] = _next_island_id
        _next_island_id += 1
for (_isl_area, _isl_kind), _isl_id in ISLAND_PROP_TILE.items():
    TILE_COLORS[_isl_id] = TILE_COLORS[ISLAND_GROUND[_isl_area]]
for _isl_area, _landmark_kind in ISLAND_LANDMARK_KIND.items():
    _isl_ground = ISLAND_GROUND[_isl_area]
    TALL_PROP_TILE[(_isl_area, _landmark_kind)] = _next_island_id
    TALL_PROP_BASE_GROUND[_next_island_id] = _isl_ground
    TILE_COLORS[_next_island_id] = TILE_COLORS[_isl_ground]
    TALL_PROP_TILE_IDS.add(_next_island_id)
    TALL_PROP_KIND_BY_ID[_next_island_id] = _landmark_kind
    _next_island_id += 1

# Colored wooden walkways connecting the mainland shore to each (now much
# farther out) island - "a walkway made of colored wood... each color for
# each island." One flat plank tile id per island INDEX (not per theme -
# every island gets its own distinct color regardless of shard/choir), 10
# total, starting at 1330 (a real buffer past the island-prop block above,
# which ends at 1322 - matches this file's own established spacing
# convention). Flat, fully-opaque ground-replacing tiles (same rendering
# convention as BIOME_PROP_TILE, not the transparent tall-prop convention -
# a plank is a floor surface, not a standalone object), and deliberately
# never added to SOLID since it's a walkable bridge over open water.
WALKWAY_PLANK_COLORS = [
    (160, 60, 50),    # 0 red-stained
    (190, 110, 40),   # 1 orange-stained
    (200, 170, 50),   # 2 yellow-stained
    (80, 140, 60),    # 3 green-stained
    (50, 140, 130),   # 4 teal-stained
    (60, 100, 170),   # 5 blue-stained
    (120, 80, 160),   # 6 purple-stained
    (190, 90, 140),   # 7 pink-stained
    (140, 100, 60),   # 8 natural wood brown
    (110, 110, 115),  # 9 weathered driftwood gray
]
WALKWAY_PLANK_TILE = {}
_next_walkway_id = 1330
for _wi, _wcolor in enumerate(WALKWAY_PLANK_COLORS):
    WALKWAY_PLANK_TILE[_wi] = _next_walkway_id
    TILE_COLORS[_next_walkway_id] = _wcolor
    _next_walkway_id += 1


def stamp_walkway(grid, from_tile, to_tile, plank_tile_id):
    """Carves a 2-tile-wide line of plank tiles connecting a mainland shore
    point to a relocated island's anchor. Not a perfectly straight ruled
    line - each tile along the path gets a small perpendicular jitter via
    _tile_hash (the same deterministic, non-gameplay-RNG trick already used
    elsewhere in this file for organic edges - see stamp_island), so it
    reads as a real rustic bridge, not a ruler-drawn stripe. plank_tile_id
    is never added to SOLID (see WALKWAY_PLANK_TILE above), since it's a
    walkable bridge over open water."""
    grid_h, grid_w = len(grid), len(grid[0])
    fx, fy = from_tile
    tx, ty = to_tile
    dist = math.hypot(tx - fx, ty - fy)
    if dist < 1:
        return
    dx, dy = (tx - fx) / dist, (ty - fy) / dist
    perp_x, perp_y = -dy, dx
    steps = max(1, int(dist))
    for i in range(steps + 1):
        t = i / steps
        px = fx + (tx - fx) * t
        py = fy + (ty - fy) * t
        jitter = (_tile_hash(int(px), int(py)) % 100) / 100.0 - 0.5  # -0.5..0.5 tiles
        px += perp_x * jitter
        py += perp_y * jitter
        for w_off in (0, 1):  # 2-tile-wide
            gx = int(round(px + perp_x * w_off))
            gy = int(round(py + perp_y * w_off))
            if 0 <= gx < grid_w and 0 <= gy < grid_h:
                grid[gy][gx] = plank_tile_id


LAIR_BUILDING_SIZE = (10, 14)  # (room_w, room_h) - shared by lair_building_rect and stamp_lair_building


def lair_building_rect(grid, center_tile):
    """Pure rect computation (no mutation) - the exact same clamped-position
    logic stamp_lair_building() uses to carve its room, extracted so a caller
    (RealmSim._stamp_biome_buildings) can check two candidate buildings for
    overlap BEFORE actually stamping either one, since two different biomes'
    "toughest lair" positions can legitimately land close enough together
    (especially near a biome-region border) that their rects would otherwise
    collide - whichever gets stamped second would silently overwrite the
    first one's walls/floor/props with no error."""
    grid_h, grid_w = len(grid), len(grid[0])
    room_w, room_h = LAIR_BUILDING_SIZE
    cx, cy = center_tile
    left = max(2, min(grid_w - room_w - 3, cx - room_w // 2))
    top = max(2, min(grid_h - room_h - 3, cy - room_h // 2))
    return pygame.Rect(left, top, room_w, room_h)


def stamp_lair_building(grid, center_tile, biome_name):
    """Carves a single walled 10x14 landmark building directly into an
    already-generated open-Realm grid, centered on `center_tile` (tx, ty) -
    a biome's toughest lair position (see RealmSim._stamp_biome_buildings).
    Reuses the exact same rect-fill technique make_bonus_room()'s single-
    room carving already uses, just stamped into EXISTING terrain instead of
    a fresh dungeon grid. Walled with plain ROCK (already SOLID, already
    gets TileMap.draw()'s edge-highlight treatment for free - no new
    wall-tile ID needed), floored with that biome's own ground tile (so the
    interior doesn't look alien, just enclosed), decorated with that biome's
    own BIOME_PROP_TILE kinds plus a few TALL_PROP_TILE totems/poles/pillars
    against the interior walls. Returns the room's pygame.Rect (tile space)
    so the caller can tighten the landmark lair's own spawn radius to fit
    inside it. Callers placing MULTIPLE buildings should check
    lair_building_rect() for overlap first - this function always carves
    unconditionally, it doesn't know about any other building."""
    rect = lair_building_rect(grid, center_tile)
    grid_h, grid_w = len(grid), len(grid[0])
    floor_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == biome_name)
    wall_tile = BUILDING_WALL_TILE[biome_name]

    for yy in range(rect.top - 1, rect.bottom + 1):
        for xx in range(rect.left - 1, rect.right + 1):
            if not (0 <= yy < grid_h and 0 <= xx < grid_w):
                continue
            on_border = yy in (rect.top - 1, rect.bottom) or xx in (rect.left - 1, rect.right)
            grid[yy][xx] = wall_tile if on_border else floor_tile

    prop_kinds = BIOME_PROP_KINDS
    prop_weights = _biome_prop_weights(biome_name)
    claimed = set()
    for _ in range(random.randint(4, 7)):
        px = random.randint(rect.left + 1, rect.right - 2)
        py = random.randint(rect.top + 1, rect.bottom - 2)
        if (px, py) in claimed:
            continue
        grid[py][px] = BIOME_PROP_TILE[(biome_name, random.choices(prop_kinds, weights=prop_weights)[0])]
        claimed.add((px, py))

    # tall totems/poles/pillars specifically against the interior walls (one
    # tile in from the border) so their upward-extending sprites read as
    # "part of the architecture" rather than floating in the open middle
    wall_adjacent = [(x, rect.top) for x in range(rect.left, rect.right)]
    wall_adjacent += [(x, rect.bottom - 1) for x in range(rect.left, rect.right)]
    random.shuffle(wall_adjacent)
    placed = 0
    for (px, py) in wall_adjacent:
        if placed >= random.randint(2, 4):
            break
        if (px, py) in claimed:
            continue
        grid[py][px] = TALL_PROP_TILE[(biome_name, random.choice(TALL_PROP_KINDS))]
        claimed.add((px, py))
        placed += 1

    return rect


ISLAND_RADIUS = 7  # tile radius of the circular island patch, before edge jitter


def stamp_island(grid, anchor_tile, theme):
    """Carves a small organic circular island patch (see ISLAND_GROUND/
    ISLAND_PROP_KINDS/ISLAND_LANDMARK_KIND above) directly into an already-
    generated open-Realm grid, centered on `anchor_tile` - unlike
    stamp_lair_building's clean walled rect, this converts every tile within
    a jittered radius (land OR water alike) to the theme's own ground tile,
    so the result reads as a real coastal landmass jutting into the sea
    rather than a room. `anchor_tile` should sit just past the mainland's
    coastline (see RealmSim._stamp_islands' coastline walk) so part of the
    circle still overlaps existing land - an island is always walkable from
    the mainland, never a fully isolated unreachable patch, matching how the
    user wants to be ABLE to walk there (the hub portal is just a shortcut).
    The edge jitter reuses `_tile_hash` (the same deterministic per-tile
    pseudo-randomness the texture-variant system uses) rather than `random`,
    so it never perturbs the gameplay RNG stream, matching this file's own
    established convention (see _art_rng's docstring above). Returns
    (stamped_rect, center_tile) - the caller needs the center tile to place
    the flare-spawn point and to target the hub portal at it."""
    grid_h, grid_w = len(grid), len(grid[0])
    ax, ay = anchor_tile
    ground_tile = ISLAND_GROUND[theme]
    prop_kinds = ISLAND_PROP_KINDS[theme]
    claimed = set()
    for yy in range(ay - ISLAND_RADIUS - 2, ay + ISLAND_RADIUS + 3):
        for xx in range(ax - ISLAND_RADIUS - 2, ax + ISLAND_RADIUS + 3):
            if not (0 <= yy < grid_h and 0 <= xx < grid_w):
                continue
            dist = math.hypot(xx - ax, yy - ay)
            jitter = (_tile_hash(xx, yy) % 300) / 100.0 - 1.5  # -1.5..+1.49, stable per-tile
            if dist <= ISLAND_RADIUS + jitter:
                grid[yy][xx] = ground_tile
                claimed.add((xx, yy))

    # Exactly one of each of the theme's 10 curated prop kinds (ISLAND_PROP_KINDS
    # above already lists exactly 10 per theme) - guarantees a real, full-variety
    # 10-decoration island instead of a random 7-10 subset that could repeat
    # kinds and skip others.
    scatter_candidates = [(xx, yy) for (xx, yy) in claimed if math.hypot(xx - ax, yy - ay) > 2]
    random.shuffle(scatter_candidates)
    for (px, py), kind in zip(scatter_candidates, prop_kinds):
        grid[py][px] = ISLAND_PROP_TILE[(theme, kind)]

    grid[ay][ax] = TALL_PROP_TILE[(theme, ISLAND_LANDMARK_KIND[theme])]

    xs = [p[0] for p in claimed] or [ax]
    ys = [p[1] for p in claimed] or [ay]
    rect = pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
    return rect, (ax, ay)


def ensure_island_decorations(grid, center_tile, theme):
    """Call this AFTER stamp_walkway() has run for this island - the plank
    walkway's landing point sits right at the island's edge (see the caller
    in RealmSim._stamp_islands), which is exactly where stamp_island()'s own
    decoration scatter can place a prop, so a walkway can silently overwrite
    one of the guaranteed 10 (confirmed: consistently drops to exactly 9,
    never fewer, one overwritten tile). Re-checks all 10 curated kinds are
    still present and refills any that got clobbered, onto any tile that's
    still the island's own plain ground (never overwriting the landmark or
    a walkway plank)."""
    grid_h, grid_w = len(grid), len(grid[0])
    ax, ay = center_tile
    ground_tile = ISLAND_GROUND[theme]
    prop_ids = {ISLAND_PROP_TILE[(theme, k)]: k for k in ISLAND_PROP_KINDS[theme]}
    found_kinds = set()
    plain_ground_candidates = []
    r = ISLAND_RADIUS + 3
    for yy in range(ay - r, ay + r + 1):
        for xx in range(ax - r, ax + r + 1):
            if not (0 <= yy < grid_h and 0 <= xx < grid_w):
                continue
            t = grid[yy][xx]
            if t in prop_ids:
                found_kinds.add(prop_ids[t])
            elif t == ground_tile and math.hypot(xx - ax, yy - ay) > 2:
                plain_ground_candidates.append((xx, yy))
    missing = [k for k in ISLAND_PROP_KINDS[theme] if k not in found_kinds]
    random.shuffle(plain_ground_candidates)
    for kind, (px, py) in zip(missing, plain_ground_candidates):
        grid[py][px] = ISLAND_PROP_TILE[(theme, kind)]


# ------------------------------------------------------- visual terracing --
# "Levels/stairs/walls for a more 3D look" (plan section 2) - deliberately a
# VISUAL effect only, not real elevation/collision: a terrace's interior and
# its cliff-lip ring are both perfectly normal, fully walkable 2D ground
# tiles (never added to SOLID) - the "3D" read comes entirely from reusing
# the SAME two-tone shaded-band/edge-outline trick TileMap.draw() already
# applies to any SOLID tile (see the `t in SOLID` block below), extended to
# also cover cliff-lip tiles specifically via CLIFF_EDGE_TILE_IDS - so a
# terrace's edge LOOKS like a real ledge without ever blocking movement or
# needing any "which floor is the player on" logic anywhere else in the
# game. NOTE (fork coordination): allocated at 1400+, clearly past every
# other block's current allocation in this file (island props reach ~1340) -
# a sibling change may also claim new ids around here; re-check for
# collisions when reconciling.
TERRACE_RADIUS = 5  # smaller than ISLAND_RADIUS/REALM_START_RADIUS - a modest landmark feature, not a zone
CLIFF_EDGE_TILE = {}
TERRACE_STAIR_TILE = {}
_next_terrace_id = 1400
for _biome_name in GROUND_TO_BIOME_NAME.values():
    _ground_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == _biome_name)
    CLIFF_EDGE_TILE[_biome_name] = _next_terrace_id
    TILE_COLORS[_next_terrace_id] = TILE_COLORS[_ground_tile]
    _next_terrace_id += 1
for _biome_name in GROUND_TO_BIOME_NAME.values():
    _ground_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == _biome_name)
    TERRACE_STAIR_TILE[_biome_name] = _next_terrace_id
    TILE_COLORS[_next_terrace_id] = TILE_COLORS[_ground_tile]
    _next_terrace_id += 1
CLIFF_EDGE_TILE_IDS = set(CLIFF_EDGE_TILE.values())  # checked by TileMap.draw() to extend the
# existing SOLID-only pseudo-3D shading to these (still non-solid) tiles too


def terrace_rect(anchor_tile):
    """Pure geometry (no mutation) - lets a caller check a candidate terrace
    for overlap against other landmarks BEFORE committing to it, same
    calling convention as lair_building_rect() above."""
    ax, ay = anchor_tile
    return pygame.Rect(ax - TERRACE_RADIUS, ay - TERRACE_RADIUS, TERRACE_RADIUS * 2, TERRACE_RADIUS * 2)


def stamp_terrace(grid, anchor_tile, biome_name):
    """Carves one small raised-looking terrace: a jittered-circle interior
    (same technique as stamp_island/stamp_realm_start) re-textured with the
    biome's OWN ground tile (no new tile id needed for the platform surface
    itself), ringed by a one-tile-wide walkable CLIFF_EDGE_TILE lip on its
    lower half (the shaded-band trick below reads as a drop-off there), with
    1-2 walkable TERRACE_STAIR_TILE tiles breaking the ring so it's always
    reachable on foot, not just visually implied. Returns the terrace's rect
    (tile space) so a caller can overlap-check it against other landmarks."""
    grid_h, grid_w = len(grid), len(grid[0])
    ax, ay = anchor_tile
    ground_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == biome_name)
    claimed = set()
    for yy in range(ay - TERRACE_RADIUS - 1, ay + TERRACE_RADIUS + 2):
        for xx in range(ax - TERRACE_RADIUS - 1, ax + TERRACE_RADIUS + 2):
            if not (0 <= yy < grid_h and 0 <= xx < grid_w):
                continue
            dist = math.hypot(xx - ax, yy - ay)
            jitter = (_tile_hash(xx, yy) % 200) / 100.0 - 1.0  # -1.0..+0.99, same stable-jitter idiom
            if dist <= TERRACE_RADIUS + jitter:
                grid[yy][xx] = ground_tile
                claimed.add((xx, yy))

    # cliff lip: a ring on the LOWER half only (dy > 0) - reads as one real
    # downhill edge rather than a fully-enclosed rim on every side, matching
    # how the researched "terraces connect via one bridge/stair edge" pattern
    # actually looks (an edge you approach from one side, not a walled pit)
    edge_ring = [(xx, yy) for (xx, yy) in claimed
                 if (yy - ay) > 0 and TERRACE_RADIUS - 1 <= math.hypot(xx - ax, yy - ay) <= TERRACE_RADIUS]
    stair_tile = TERRACE_STAIR_TILE[biome_name]
    cliff_tile = CLIFF_EDGE_TILE[biome_name]
    if edge_ring:
        edge_ring.sort(key=lambda p: p[0])  # deterministic left-to-right order
        stair_count = min(2, len(edge_ring))
        stair_positions = {edge_ring[i * (len(edge_ring) - 1) // max(1, stair_count - 1 if stair_count > 1 else 1)]
                            for i in range(stair_count)} if stair_count else set()
        for (xx, yy) in edge_ring:
            grid[yy][xx] = stair_tile if (xx, yy) in stair_positions else cliff_tile

    xs = [p[0] for p in claimed] or [ax]
    ys = [p[1] for p in claimed] or [ay]
    return pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


# ---------------------------------------------------- discoverable landmarks --
# One hand-placed, non-combat point of interest per biome (10 total) - pure
# exploration reward, not a lair. Deliberately reuses the ALREADY-REGISTERED
# TALL_PROP_TILE kinds (totem/pole/pillar/banner_pole/brazier/signpost, see
# TALL_PROP_KINDS above) instead of allocating any new tile ids - a landmark
# is just a small themed arrangement of existing decoration props around a
# clearing of the biome's own ground tile, so there is zero tile-id
# collision risk with any other concurrent change to this file.
LANDMARK_RADIUS = 3  # smaller than TERRACE_RADIUS - a single POI, not a zone
LANDMARK_DEFS = {
    "forest": {"name": "the Sunken Idol",
               "lore": "Moss-choked totems ring a stone long since swallowed by roots.",
               "kinds": ["pillar", "pole", "pole"]},
    "desert": {"name": "the Buried Obelisk",
               "lore": "Sand hisses off an obelisk half-buried, its carvings worn to whispers.",
               "kinds": ["totem", "pillar", "signpost"]},
    "tundra": {"name": "the Frozen Watchpost",
               "lore": "A frost-rimed signpost still points toward a camp no one returned to.",
               "kinds": ["signpost", "pole", "brazier"]},
    "swamp": {"name": "the Drowned Shrine",
              "lore": "Reeds curl around a shrine sinking slowly into the mire.",
              "kinds": ["totem", "pillar", "pole"]},
    "highlands": {"name": "the Wind-Worn Cairn",
                  "lore": "Stones stacked by hands long gone, rattling faintly in the wind.",
                  "kinds": ["pillar", "pillar", "totem"]},
    "ashlands": {"name": "the Charred Altar",
                 "lore": "An altar scorched black, ash still drifting from embers no one lit.",
                 "kinds": ["brazier", "totem", "pillar"]},
    "jungle": {"name": "the Vine-Wrapped Ruin",
               "lore": "Vines strangle a pillar carved with a face the jungle has almost erased.",
               "kinds": ["totem", "pillar", "pole"]},
    "wasteland": {"name": "the Rusted Beacon",
                  "lore": "A beacon long dark, its brazier crusted with rust and old rain.",
                  "kinds": ["brazier", "signpost", "pole"]},
    "ice": {"name": "the Glacial Monument",
            "lore": "A monument entombed in blue ice, its inscription frozen mid-sentence.",
            "kinds": ["pillar", "totem", "signpost"]},
    "cave": {"name": "the Forgotten Totem Circle",
             "lore": "Totems in a ring face inward, toward something no longer there.",
             "kinds": ["totem", "totem", "pillar"]},
}


def landmark_rect(anchor_tile):
    """Pure geometry (no mutation) - same overlap-check calling convention as
    lair_building_rect()/terrace_rect() above."""
    ax, ay = anchor_tile
    return pygame.Rect(ax - LANDMARK_RADIUS, ay - LANDMARK_RADIUS, LANDMARK_RADIUS * 2, LANDMARK_RADIUS * 2)


def stamp_landmark(grid, anchor_tile, biome_name):
    """Clears a small circular patch of the biome's own ground tile (same
    jittered-circle technique as stamp_terrace/stamp_realm_start) and rings
    it with that biome's themed prop cluster (LANDMARK_DEFS), evenly spaced
    at deterministic angles (same idiom as stamp_realm_start's marker ring).
    Returns the landmark's rect (tile space) so a caller can overlap-check
    it against other landmarks before committing to it."""
    grid_h, grid_w = len(grid), len(grid[0])
    ax, ay = anchor_tile
    ground_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == biome_name)
    claimed = set()
    for yy in range(ay - LANDMARK_RADIUS - 1, ay + LANDMARK_RADIUS + 2):
        for xx in range(ax - LANDMARK_RADIUS - 1, ax + LANDMARK_RADIUS + 2):
            if not (0 <= yy < grid_h and 0 <= xx < grid_w):
                continue
            dist = math.hypot(xx - ax, yy - ay)
            jitter = (_tile_hash(xx, yy) % 200) / 100.0 - 1.0
            if dist <= LANDMARK_RADIUS + jitter:
                grid[yy][xx] = ground_tile
                claimed.add((xx, yy))

    defn = LANDMARK_DEFS.get(biome_name)
    if defn:
        kinds = defn["kinds"]
        n = len(kinds)
        for i, kind in enumerate(kinds):
            angle = (2 * math.pi * i) / n
            px = ax + round(math.cos(angle) * (LANDMARK_RADIUS - 1))
            py = ay + round(math.sin(angle) * (LANDMARK_RADIUS - 1))
            if (px, py) in claimed:
                grid[py][px] = TALL_PROP_TILE[(biome_name, kind)]

    xs = [p[0] for p in claimed] or [ax]
    ys = [p[1] for p in claimed] or [ay]
    return pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


# Track C (Batch 14): curated biome decoration "vignettes" - 20 guaranteed,
# hand-composed small prop clusters per biome, distinct from the existing
# generic ambient scatter (that stays exactly as-is). Each vignette reuses
# ONLY already-registered BIOME_PROP_TILE kinds (zero new tile ids, zero
# collision risk) arranged in a small deliberate pattern around an anchor,
# so it reads as one composed "scene" (a mushroom ring, a fallen-log
# clearing, etc.) instead of another independent random single-tile pick.
# Two alternating templates per biome for variety across the 20 instances.
BIOME_VIGNETTE_RADIUS = 2
BIOME_VIGNETTE_TEMPLATES = {
    "forest": [
        [("wildflower_patch", 0, 0), ("mushroom_cluster", -1, -1), ("mushroom_cluster", 1, -1),
         ("mushroom_cluster", -1, 1), ("mushroom_cluster", 1, 1)],  # a mushroom ring around a flower patch
        [("tree", 0, 0), ("fallen_log", 1, 0), ("berry_bush", -1, 1), ("grasstuft", 0, 1)],  # fallen-log clearing
    ],
    "desert": [
        [("puddle", 0, 0), ("gravel_patch", -1, 0), ("gravel_patch", 1, 0), ("pebbles", 0, 1)],  # a drying watering hole
        [("boulder", 0, 0), ("rock", 1, 1), ("skull", -1, 1), ("cracked_ground", 0, 1)],  # sun-bleached remains
    ],
    "swamp": [
        [("reed_cluster", 0, -1), ("reed_cluster", 0, 1), ("reed_cluster", -1, 0), ("puddle", 0, 0)],  # reed marsh
        [("moss_patch", 0, 0), ("mushroom_cluster", 1, 0), ("water_stain", -1, 1)],  # mossy sinkhole
    ],
    "tundra": [
        [("dead_tree", 0, 0), ("stump", 1, 0), ("debris", -1, 1)],  # frost graveyard
        [("fallen_log", 0, 0), ("rock", 1, -1), ("debris", -1, -1)],  # windfall thicket
    ],
    "highlands": [
        [("boulder", 0, 0), ("rock", -1, -1), ("rock", 1, -1), ("gravel_patch", 0, 1)],  # rock formation
        [("pebbles", 0, 0), ("boulder", 1, 1), ("cracked_ground", -1, 1)],  # scree slope
    ],
    "ashlands": [
        [("ash_pile", 0, -1), ("ash_pile", 0, 1), ("ash_pile", -1, 0), ("skull", 0, 0)],  # ash mound
        [("dead_tree", 0, 0), ("cracked_ground", 1, 0), ("debris", -1, 1)],  # scorched stand
    ],
    "jungle": [
        [("vine", 0, -1), ("vine", 0, 1), ("root_tangle", -1, 0), ("mushroom_cluster", 1, 0)],  # vine thicket
        [("tree", 0, 0), ("berry_bush", 1, 1), ("root_tangle", -1, -1)],  # canopy root cluster
    ],
    "wasteland": [
        [("skull", 0, 0), ("debris", 1, 0), ("debris", -1, 0), ("dead_tree", 0, 1)],  # bone pile
        [("gravel_patch", 0, 0), ("ash_pile", 1, 1), ("skull", -1, -1)],  # blasted waste
    ],
    "ice": [
        [("boulder", 0, 0), ("rock", 1, 0), ("dead_tree", -1, 1)],  # ice ridge
        [("debris", 0, 0), ("rock", 0, 1), ("boulder", 1, -1)],  # frost-shattered rubble
    ],
    "cave": [
        [("mushroom_cluster", 0, -1), ("mushroom_cluster", 0, 1), ("cobweb", -1, 0), ("rune_marking", 0, 0)],  # fungal grotto
        [("small_pile", 0, 0), ("cobweb", 1, 1), ("root_tangle", -1, -1)],  # forgotten cache
    ],
}


def biome_vignette_rect(anchor_tile):
    """Pure geometry (no mutation) - same overlap-check calling convention as
    lair_building_rect()/terrace_rect()/landmark_rect() above."""
    ax, ay = anchor_tile
    r = BIOME_VIGNETTE_RADIUS
    return pygame.Rect(ax - r, ay - r, r * 2 + 1, r * 2 + 1)


def stamp_biome_vignette(grid, anchor_tile, biome_name, template_idx=0):
    """Stamps one small curated prop cluster (see BIOME_VIGNETTE_TEMPLATES)
    centered on anchor_tile, using only already-registered BIOME_PROP_TILE
    kinds. Returns the vignette's rect (tile space) for overlap-checking,
    matching stamp_landmark's own return-value convention."""
    grid_h, grid_w = len(grid), len(grid[0])
    ax, ay = anchor_tile
    templates = BIOME_VIGNETTE_TEMPLATES.get(biome_name)
    if not templates:
        return biome_vignette_rect(anchor_tile)
    template = templates[template_idx % len(templates)]
    for kind, dx, dy in template:
        xx, yy = ax + dx, ay + dy
        if 0 <= yy < grid_h and 0 <= xx < grid_w:
            grid[yy][xx] = BIOME_PROP_TILE[(biome_name, kind)]
    return biome_vignette_rect(anchor_tile)


REALM_START_RADIUS = 9  # tile radius of the stamped starting-area plaza


def stamp_realm_start(grid, anchor_tile, biome_name):
    """Carves a small circular 'starting area' plaza around the Realm's own
    arrival point (see RealmSim._stamp_island_hub) - guarantees enough
    clear, walkable land for the island-link portal ring to be placed on
    at DETERMINISTIC, evenly-spaced positions, instead of each portal
    independently searching for a random nearby spot (which could - and
    did - land two portals on top of each other). Uses the same circular
    jittered-edge carve as stamp_island (see ISLAND_RADIUS/_tile_hash),
    just filled with the local biome's own ground tile instead of an island
    theme, so the plaza blends into the coastline it's placed on rather
    than reading as a foreign zone. A light ring of signpost/banner_pole
    tall props near the outer edge marks it as a real place, not just an
    anonymous patch of ground."""
    grid_h, grid_w = len(grid), len(grid[0])
    ax, ay = anchor_tile
    ground_tile = next(g for g, name in GROUND_TO_BIOME_NAME.items() if name == biome_name)
    claimed = set()
    for yy in range(ay - REALM_START_RADIUS - 2, ay + REALM_START_RADIUS + 3):
        for xx in range(ax - REALM_START_RADIUS - 2, ax + REALM_START_RADIUS + 3):
            if not (0 <= yy < grid_h and 0 <= xx < grid_w):
                continue
            dist = math.hypot(xx - ax, yy - ay)
            jitter = (_tile_hash(xx, yy) % 300) / 100.0 - 1.5
            if dist <= REALM_START_RADIUS + jitter:
                grid[yy][xx] = ground_tile
                claimed.add((xx, yy))
    # markers at 8 DETERMINISTIC, evenly-spaced compass angles (not a random
    # pick among edge candidates) - reads as a deliberately symmetric hub,
    # similar in spirit to the Nexus's own radially-symmetric statue/banner
    # placement, rather than an arbitrary scatter
    marker_kinds = ["signpost", "banner_pole"]
    n_markers = 8
    for i in range(n_markers):
        angle = (2 * math.pi * i) / n_markers
        mx = ax + round(math.cos(angle) * (REALM_START_RADIUS - 1))
        my = ay + round(math.sin(angle) * (REALM_START_RADIUS - 1))
        if (mx, my) in claimed:
            grid[my][mx] = TALL_PROP_TILE[(biome_name, marker_kinds[i % 2])]
    return pygame.Rect(ax - REALM_START_RADIUS, ay - REALM_START_RADIUS,
                        REALM_START_RADIUS * 2, REALM_START_RADIUS * 2)


# ---------------------------------------------------------- tile textures --
# Flat-colour tiles are cheap but look inert. Pre-rendering a handful of
# textured variants per tile type (once, cached) is just as cheap to draw
# (one blit, same as before) but reads far richer. Textures are drawn at
# SUPER x the final size with denser detail, then smoothscale'd back down -
# supersampling, the organic-texture equivalent of the sprites' Scale2x
# pass: more quality at the same on-screen tile footprint, not a bigger
# tile (TILE is load-bearing for the movement-speed formulas, so its
# world-unit size can't change without rebalancing the whole game).
# A dedicated RNG is used here instead of the shared `random` module so
# generating art at import time can't perturb the gameplay RNG stream
# (enemy spawns, loot rolls).
_TILE_VARIANTS = 4
_art_rng = random.Random(20260918)
SUPER = 4
_SPRITE_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sprites", "v0.2")


def _tint(color, delta):
    return tuple(max(0, min(255, c + delta)) for c in color)


def _load_tile_variants(name_prefix, procedural_variants, subdir="tiles"):
    """Hand-painted PNG tile variants (assets/sprites/v0.2/<subdir>/tile_<name>_N.png,
    made with the pixel-mcp tool) load in front of the procedural textures below,
    one file at a time, falling back to the matching procedural variant if a
    given file is missing or fails to load - a partial art set never breaks
    the tile grid."""
    out = []
    for i, fallback in enumerate(procedural_variants):
        path = os.path.join(_SPRITE_DIR, subdir, f"tile_{name_prefix}_{i}.png")
        surf = None
        if os.path.isfile(path):
            try:
                # convert_alpha (not convert) - ground/wall tiles are always fully
                # opaque so this is visually identical for them, but decorative
                # props (banners, statues, garden clusters, wells, boards) rely on
                # a transparent background to blend into the floor tile beneath.
                surf = pygame.transform.smoothscale(pygame.image.load(path).convert_alpha(), (C.TILE, C.TILE))
            except Exception:
                surf = None
        out.append(surf if surf is not None else fallback)
    return out


def _finish(surf):
    return pygame.transform.smoothscale(surf, (C.TILE, C.TILE))


def _make_grass_tex(dark):
    base = C.COL_GRASS_DARK if dark else C.COL_GRASS
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(base)
    blade, shadow, hi = _tint(base, 24), _tint(base, -22), _tint(base, 42)
    for _ in range(30):
        x, y = _art_rng.randint(4, big - 5), _art_rng.randint(10, big - 5)
        col = _art_rng.choices([blade, shadow, hi], weights=[5, 4, 2])[0]
        length = _art_rng.randint(6, 15)
        sway = _art_rng.randint(-4, 4)
        pygame.draw.line(surf, col, (x, y), (x + sway, y - length), 2)
    for _ in range(8):
        x, y = _art_rng.randint(4, big - 5), _art_rng.randint(4, big - 5)
        pygame.draw.circle(surf, _tint(base, -14), (x, y), _art_rng.randint(2, 4))
    return _finish(surf)


def _make_dirt_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_DIRT)
    dark, light, deep = _tint(C.COL_DIRT, -34), _tint(C.COL_DIRT, 26), _tint(C.COL_DIRT, -50)
    for _ in range(4):
        x, y = _art_rng.randint(6, big - 7), _art_rng.randint(6, big - 7)
        pygame.draw.circle(surf, deep, (x, y), _art_rng.randint(3, 6))
    for _ in range(26):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        col = dark if _art_rng.random() < 0.6 else light
        pygame.draw.circle(surf, col, (x, y), _art_rng.randint(1, 3))
    return _finish(surf)


def _make_rock_tex(base_color=None):
    base_color = C.COL_ROCK if base_color is None else base_color
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(base_color)
    dark, light = _tint(base_color, -42), _tint(base_color, 38)
    # a couple of jagged crack lines (multi-segment, not a single straight stroke)
    for _ in range(_art_rng.randint(2, 3)):
        x, y = _art_rng.randint(8, big - 16), _art_rng.randint(8, big - 16)
        for _seg in range(_art_rng.randint(2, 4)):
            nx, ny = x + _art_rng.randint(-14, 14), y + _art_rng.randint(6, 16)
            pygame.draw.line(surf, dark, (x, y), (nx, ny), 2)
            x, y = nx, ny
    # a soft highlight edge suggesting an angled facet catching the light
    hx, hy = _art_rng.randint(6, big // 2), _art_rng.randint(6, big // 2)
    pygame.draw.line(surf, light, (hx, hy), (hx + _art_rng.randint(10, 22), hy), 2)
    for _ in range(10):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, dark if _art_rng.random() < 0.5 else light, (x, y), 1)
    return _finish(surf)


def _make_nexus_tex(variant):
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_NEXUS_FLOOR)
    dark = _tint(C.COL_NEXUS_FLOOR, -20)
    light = _tint(C.COL_NEXUS_FLOOR, 16)
    pygame.draw.rect(surf, light, (3, 3, big - 6, big - 6), width=3)
    if variant == 0:
        pygame.draw.line(surf, dark, (0, big // 2), (big, big // 2), 2)
        pygame.draw.line(surf, dark, (big // 2, 0), (big // 2, big), 2)
    return _finish(surf)


def _make_water_tex(phase):
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_WATER)
    light, deep = _tint(C.COL_WATER, 38), _tint(C.COL_WATER, -30)
    for i, frac in enumerate((0.25, 0.5, 0.75)):
        y = int(big * frac + 10 * math.sin(phase + i * 2.1))
        pygame.draw.line(surf, light, (0, y), (big, y), 2)
        pygame.draw.line(surf, deep, (0, y + 6), (big, y + 6), 2)
    return _finish(surf)


def _make_sand_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_SAND)
    dark, light = _tint(C.COL_SAND, -30), _tint(C.COL_SAND, 26)
    for _ in range(4):
        y = _art_rng.randint(6, big - 6)
        x0 = _art_rng.randint(0, big // 3)
        pygame.draw.arc(surf, light, (x0, y - 6, big // 2, 12), 3.4, 6.0, 2)
    for _ in range(24):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, dark if _art_rng.random() < 0.5 else light, (x, y), 1)
    return _finish(surf)


def _make_swamp_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_SWAMP)
    murk, ooze = _tint(C.COL_SWAMP, -22), _tint(C.COL_SWAMP, 20)
    for _ in range(5):
        x, y = _art_rng.randint(6, big - 7), _art_rng.randint(6, big - 7)
        pygame.draw.circle(surf, murk, (x, y), _art_rng.randint(3, 7))
    for _ in range(14):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, ooze, (x, y), 1)
    return _finish(surf)


def _make_snow_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_SNOW)
    shadow, sparkle = _tint(C.COL_SNOW, -28), _tint(C.COL_SNOW, 20)
    for _ in range(3):
        x, y = _art_rng.randint(6, big - 7), _art_rng.randint(6, big - 7)
        pygame.draw.circle(surf, shadow, (x, y), _art_rng.randint(4, 8))
    for _ in range(16):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, sparkle, (x, y), 1)
    return _finish(surf)


def _make_stone_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_STONE)
    dark, light = _tint(C.COL_STONE, -32), _tint(C.COL_STONE, 30)
    for _ in range(5):
        x, y = _art_rng.randint(4, big - 5), _art_rng.randint(4, big - 5)
        pygame.draw.polygon(surf, dark, [
            (x, y), (x + _art_rng.randint(4, 10), y + _art_rng.randint(-4, 4)),
            (x + _art_rng.randint(-2, 6), y + _art_rng.randint(4, 10))])
    for _ in range(12):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, light if _art_rng.random() < 0.5 else dark, (x, y), 1)
    return _finish(surf)


def _make_ash_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_ASH)
    ember, soot = (200, 90, 40), _tint(C.COL_ASH, -20)
    for _ in range(4):
        x, y = _art_rng.randint(6, big - 7), _art_rng.randint(6, big - 7)
        pygame.draw.circle(surf, soot, (x, y), _art_rng.randint(3, 6))
    for _ in range(8):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        col = ember if _art_rng.random() < 0.35 else _tint(C.COL_ASH, 18)
        pygame.draw.circle(surf, col, (x, y), 1)
    return _finish(surf)


def _make_jungle_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_JUNGLE)
    leaf, shadow, flower = _tint(C.COL_JUNGLE, 34), _tint(C.COL_JUNGLE, -26), (200, 120, 160)
    for _ in range(20):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, leaf if _art_rng.random() < 0.6 else shadow, (x, y), _art_rng.randint(2, 4))
    for _ in range(3):
        x, y = _art_rng.randint(4, big - 5), _art_rng.randint(4, big - 5)
        pygame.draw.circle(surf, flower, (x, y), 2)
    return _finish(surf)


def _make_wasteland_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_WASTELAND)
    crack, dust = _tint(C.COL_WASTELAND, -34), _tint(C.COL_WASTELAND, 22)
    for _ in range(3):
        x, y = _art_rng.randint(6, big - 12), _art_rng.randint(6, big - 12)
        for _seg in range(_art_rng.randint(2, 3)):
            nx, ny = x + _art_rng.randint(-10, 10), y + _art_rng.randint(4, 12)
            pygame.draw.line(surf, crack, (x, y), (nx, ny), 1)
            x, y = nx, ny
    for _ in range(14):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, dust, (x, y), 1)
    return _finish(surf)


def _make_ice_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_ICE)
    crack, shine = _tint(C.COL_ICE, -40), (240, 250, 255)
    for _ in range(3):
        x, y = _art_rng.randint(4, big - 5), _art_rng.randint(4, big - 5)
        pygame.draw.line(surf, crack, (x, y), (x + _art_rng.randint(-12, 12), y + _art_rng.randint(-12, 12)), 1)
    for _ in range(10):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, shine, (x, y), 1)
    return _finish(surf)


def _make_cave_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill(C.COL_CAVE)
    glow, dark = (140, 100, 220), _tint(C.COL_CAVE, -24)
    for _ in range(4):
        x, y = _art_rng.randint(4, big - 5), _art_rng.randint(4, big - 5)
        pygame.draw.circle(surf, dark, (x, y), _art_rng.randint(3, 6))
    for _ in range(6):
        x, y = _art_rng.randint(2, big - 3), _art_rng.randint(2, big - 3)
        pygame.draw.circle(surf, glow, (x, y), 1)
    return _finish(surf)


def _make_fountain_tex(phase):
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill((70, 130, 200))
    deep, foam = _tint((70, 130, 200), -34), (220, 240, 255)
    cx = cy = big // 2
    for i, r in enumerate((big * 0.42, big * 0.3, big * 0.18)):
        rr = r + 5 * math.sin(phase + i * 1.7)
        pygame.draw.circle(surf, deep, (cx, cy), int(rr), 2)
    for _ in range(10):
        ang = _art_rng.uniform(0, math.tau)
        rad = _art_rng.uniform(4, big * 0.46)
        x, y = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
        pygame.draw.circle(surf, foam, (int(x), int(y)), 1)
    return _finish(surf)


def _make_statue_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill((60, 58, 66))
    stone, hi, gold = (150, 145, 130), (190, 186, 172), (210, 180, 90)
    cx = big // 2
    pygame.draw.rect(surf, stone, (cx - big * 0.22, big * 0.1, big * 0.44, big * 0.62), border_radius=6)
    pygame.draw.circle(surf, hi, (cx, int(big * 0.22)), int(big * 0.16))
    pygame.draw.rect(surf, stone, (cx - big * 0.32, big * 0.68, big * 0.64, big * 0.22), border_radius=4)
    pygame.draw.line(surf, gold, (cx - big * 0.3, big * 0.7), (cx + big * 0.3, big * 0.7), 2)
    return _finish(surf)


def _make_banner_tex():
    big = C.TILE * SUPER
    surf = pygame.Surface((big, big))
    surf.fill((90, 30, 40))
    cloth, gold, dark = (170, 50, 65), (210, 180, 90), (60, 18, 26)
    pygame.draw.rect(surf, cloth, (big * 0.2, 0, big * 0.6, big), border_radius=4)
    pygame.draw.rect(surf, gold, (big * 0.2, big * 0.08, big * 0.6, 4))
    pygame.draw.rect(surf, gold, (big * 0.2, big * 0.8, big * 0.6, 4))
    pygame.draw.circle(surf, gold, (big // 2, int(big * 0.45)), int(big * 0.12), 2)
    pygame.draw.rect(surf, dark, (0, 0, big * 0.18, big))
    pygame.draw.rect(surf, dark, (big * 0.82, 0, big * 0.18, big))
    return _finish(surf)


_GRASS_TEX = _load_tile_variants("forest", [_make_grass_tex(False) for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_GRASS2_TEX = [_make_grass_tex(True) for _ in range(_TILE_VARIANTS)]
_DIRT_TEX = [_make_dirt_tex() for _ in range(_TILE_VARIANTS)]
_ROCK_TEX = [_make_rock_tex() for _ in range(_TILE_VARIANTS)]
_NEXUS_TEX = [_make_nexus_tex(i) for i in range(2)]
_WATER_FRAMES = [_make_water_tex(p) for p in (0.0, math.tau / 3, 2 * math.tau / 3)]
_SAND_TEX = _load_tile_variants("desert", [_make_sand_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_SWAMP_TEX = _load_tile_variants("swamp", [_make_swamp_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_SNOW_TEX = _load_tile_variants("tundra", [_make_snow_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_STONE_TEX = _load_tile_variants("highlands", [_make_stone_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_ASH_TEX = _load_tile_variants("ashlands", [_make_ash_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_JUNGLE_TEX = _load_tile_variants("jungle", [_make_jungle_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_WASTELAND_TEX = _load_tile_variants("wasteland", [_make_wasteland_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_ICE_TEX = _load_tile_variants("ice", [_make_ice_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_CAVE_TEX = _load_tile_variants("cave", [_make_cave_tex() for _ in range(_TILE_VARIANTS)], subdir="tiles/biomes")
_FOUNTAIN_TEX = [_make_fountain_tex(p) for p in (0.0, math.tau / 3, 2 * math.tau / 3)]
_BANNER_TEX = _load_tile_variants("nexus_banner", [_make_banner_tex() for _ in range(4)], subdir="decorations/nexus")
_STATUE_TEX = _load_tile_variants("nexus_statue", [_make_statue_tex() for _ in range(4)], subdir="decorations/nexus")
# Nexus decorative-but-walkable dressing (NEXUS_GARDEN/WELL/BOARD) - no
# procedural generator existed for these yet (flat TILE_COLORS fill only),
# so the "fallback" here is just a flat tint of the tile's TILE_COLORS
# entry - hand-painted art (assets/sprites/v0.2/tiles/tile_nexus_<x>_N.png)
# loads in front of it exactly like every other _load_tile_variants tile.
def _flat_tex(color):
    surf = pygame.Surface((C.TILE, C.TILE))
    surf.fill(color)
    return surf


_GARDEN_TEX = _load_tile_variants("nexus_garden", [_flat_tex(TILE_COLORS[NEXUS_GARDEN]) for _ in range(3)], subdir="decorations/nexus")
_WELL_TEX = _load_tile_variants("nexus_well", [_flat_tex(TILE_COLORS[NEXUS_WELL]) for _ in range(2)], subdir="decorations/nexus")
_BOARD_TEX = _load_tile_variants("nexus_board", [_flat_tex(TILE_COLORS[NEXUS_BOARD]) for _ in range(2)], subdir="decorations/nexus")

# 7 new Nexus decoration kinds (see NEXUS_PROP_TILE above) - same one-hand-
# painted-variant-per-id pattern as _BIOME_PROP_TEX/_DUNGEON_PROP_TEX below.
_NEXUS_PROP_TEX = {}
for _np_kind, _np_id in NEXUS_PROP_TILE.items():
    _NEXUS_PROP_TEX[_np_id] = _load_tile_variants(
        f"nexus_{_np_kind}", [_flat_tex(TILE_COLORS[_np_id])], subdir="decorations/nexus")

# Vault room dressing (make_vault_room()) - same flat-fallback + hand-painted-
# art-in-front pattern as the Nexus dressing just above.
_VAULT_GOLD_TEX = _load_tile_variants("vault_gold", [_flat_tex(TILE_COLORS[VAULT_GOLD]) for _ in range(2)], subdir="decorations/vault")
_VAULT_GEMS_TEX = _load_tile_variants("vault_gems", [_flat_tex(TILE_COLORS[VAULT_GEMS]) for _ in range(2)], subdir="decorations/vault")
_VAULT_PILLAR_TEX = _load_tile_variants("vault_pillar", [_flat_tex(TILE_COLORS[VAULT_PILLAR])], subdir="decorations/vault")
_VAULT_COBWEB_TEX = _load_tile_variants("vault_cobweb", [_flat_tex(TILE_COLORS[VAULT_COBWEB]) for _ in range(2)], subdir="decorations/vault")
_VAULT_BOOKSHELF_TEX = _load_tile_variants("vault_bookshelf", [_flat_tex(TILE_COLORS[VAULT_BOOKSHELF])], subdir="decorations/vault")
_VAULT_CANDELABRA_TEX = _load_tile_variants("vault_candelabra", [_flat_tex(TILE_COLORS[VAULT_CANDELABRA])], subdir="decorations/vault")
_VAULT_SACK_TEX = _load_tile_variants("vault_sack", [_flat_tex(TILE_COLORS[VAULT_SACK]) for _ in range(2)], subdir="decorations/vault")
_VAULT_POTTERY_TEX = _load_tile_variants("vault_pottery", [_flat_tex(TILE_COLORS[VAULT_POTTERY])], subdir="decorations/vault")
_VAULT_RUNE_TEX = _load_tile_variants("vault_rune", [_flat_tex(TILE_COLORS[VAULT_RUNE])], subdir="decorations/vault")

# Overworld biome decoration props (make_realm()) - 100 tile ids (see
# BIOME_PROP_TILE above), each with exactly one hand-painted variant, loaded
# in a loop rather than 100 hand-typed _load_tile_variants(...) lines.
_BIOME_PROP_TEX = {}
for (_bp_biome, _bp_kind), _bp_id in BIOME_PROP_TILE.items():
    _BIOME_PROP_TEX[_bp_id] = _load_tile_variants(
        f"biome_{_bp_biome}_{_bp_kind}", [_flat_tex(TILE_COLORS[_bp_id])],
        subdir=f"decorations/biomes/{_bp_biome}")

# Dungeon-theme decoration props (make_bonus_room()) - 77 tile ids (see
# DUNGEON_PROP_TILE above), same one-hand-painted-variant-per-id pattern.
_DUNGEON_PROP_TEX = {}
for (_dp_theme, _dp_kind), _dp_id in DUNGEON_PROP_TILE.items():
    _DUNGEON_PROP_TEX[_dp_id] = _load_tile_variants(
        f"dungeon_{_dp_theme}_{_dp_kind}", [_flat_tex(TILE_COLORS[_dp_id])],
        subdir=f"decorations/dungeons/{_dp_theme}")

# Island decoration props (RealmSim._stamp_islands) - 20 tile ids (see
# ISLAND_PROP_TILE above), same one-hand-painted-variant-per-id pattern.
_ISLAND_PROP_TEX = {}
for (_isl_biome, _isl_kind), _isl_tid in ISLAND_PROP_TILE.items():
    _ISLAND_PROP_TEX[_isl_tid] = _load_tile_variants(
        f"island_{_isl_biome}_{_isl_kind}", [_flat_tex(TILE_COLORS[_isl_tid])],
        subdir=f"decorations/islands/{_isl_biome}")

# Walkway plank tiles (WALKWAY_PLANK_TILE above) - 10 tile ids, one per
# island index, same one-hand-painted-variant-per-id pattern (falls back to
# a flat color texture if no PNG is painted, so this ships correct with
# zero new art required).
_WALKWAY_PLANK_TEX = {}
for _wi, _wtid in WALKWAY_PLANK_TILE.items():
    _WALKWAY_PLANK_TEX[_wtid] = _load_tile_variants(
        f"walkway_plank_{_wi}", [_flat_tex(TILE_COLORS[_wtid])], subdir="decorations/walkways")

# Per-dungeon-theme wall textures (see DUNGEON_THEMES in realm_sim.py) - hand-painted
# variants load in front of these same as the biome floors above, falling back to a
# tinted version of the plain rock-crack generator per theme colour.
_WALL_VAULT_TEX = _load_tile_variants("wall_vault", [_make_rock_tex(TILE_COLORS[WALL_VAULT]) for _ in range(2)], subdir="tiles/walls")
_WALL_CAVE_TEX = _load_tile_variants("wall_cave", [_make_rock_tex(TILE_COLORS[WALL_CAVE]) for _ in range(2)], subdir="tiles/walls")
_WALL_FROST_TEX = _load_tile_variants("wall_frost", [_make_rock_tex(TILE_COLORS[WALL_FROST]) for _ in range(2)], subdir="tiles/walls")
_WALL_JUNGLE_TEX = _load_tile_variants("wall_jungle", [_make_rock_tex(TILE_COLORS[WALL_JUNGLE]) for _ in range(2)], subdir="tiles/walls")
_WALL_EMBER_TEX = _load_tile_variants("wall_ember", [_make_rock_tex(TILE_COLORS[WALL_EMBER]) for _ in range(2)], subdir="tiles/walls")
_WALL_GROTTO_TEX = _load_tile_variants("wall_grotto", [_make_rock_tex(TILE_COLORS[WALL_GROTTO]) for _ in range(2)], subdir="tiles/walls")
_WALL_SPIRE_TEX = _load_tile_variants("wall_spire", [_make_rock_tex(TILE_COLORS[WALL_SPIRE]) for _ in range(2)], subdir="tiles/walls")

# Landmark-building exterior wall textures (see BUILDING_WALL_TILE above) -
# one hand-painted variant per biome, same loading pattern as the dungeon
# WALL_* textures just above, falling back to a tinted procedural rock
# texture for the (never-painted) second variant slot.
_BUILDING_WALL_TEX = {
    _building_biome: _load_tile_variants(f"building_wall_{_building_biome}",
                                          [_make_rock_tex(TILE_COLORS[_building_id]) for _ in range(2)],
                                          subdir="tiles/walls")
    for _building_biome, _building_id in BUILDING_WALL_TILE.items()
}


def _load_single(path_rel, size):
    """Like _load_tile_variants but for one fixed-name PNG rather than a
    numbered variant set - used for one-off interactive props (CHEST) that
    render outside the normal per-tile-type texture list. Returns None on
    any failure so the caller keeps its existing fallback rendering."""
    path = os.path.join(_SPRITE_DIR, path_rel)
    if not os.path.isfile(path):
        return None
    try:
        return pygame.transform.smoothscale(pygame.image.load(path).convert_alpha(), size)
    except Exception:
        return None


_CHEST_SPRITE = _load_single(os.path.join("decorations", "vault", "chest.png"), (36, 30))

_TEX_BY_TILE = {GRASS: _GRASS_TEX, GRASS2: _GRASS2_TEX, DIRT: _DIRT_TEX,
                 SAND: _SAND_TEX, SWAMP: _SWAMP_TEX, SNOW: _SNOW_TEX,
                 STONE: _STONE_TEX, ASH: _ASH_TEX,
                 JUNGLE: _JUNGLE_TEX, WASTELAND: _WASTELAND_TEX, ICE: _ICE_TEX, CAVE: _CAVE_TEX,
                 ROCK: _ROCK_TEX, NEXUS_FLOOR: _NEXUS_TEX,
                 NEXUS_BANNER: _BANNER_TEX, NEXUS_STATUE: _STATUE_TEX,
                 NEXUS_GARDEN: _GARDEN_TEX, NEXUS_WELL: _WELL_TEX, NEXUS_BOARD: _BOARD_TEX,
                 VAULT_GOLD: _VAULT_GOLD_TEX, VAULT_GEMS: _VAULT_GEMS_TEX, VAULT_PILLAR: _VAULT_PILLAR_TEX,
                 VAULT_COBWEB: _VAULT_COBWEB_TEX, VAULT_BOOKSHELF: _VAULT_BOOKSHELF_TEX,
                 VAULT_CANDELABRA: _VAULT_CANDELABRA_TEX, VAULT_SACK: _VAULT_SACK_TEX,
                 VAULT_POTTERY: _VAULT_POTTERY_TEX, VAULT_RUNE: _VAULT_RUNE_TEX,
                 WALL_VAULT: _WALL_VAULT_TEX, WALL_CAVE: _WALL_CAVE_TEX, WALL_FROST: _WALL_FROST_TEX,
                 WALL_JUNGLE: _WALL_JUNGLE_TEX, WALL_EMBER: _WALL_EMBER_TEX,
                 WALL_GROTTO: _WALL_GROTTO_TEX, WALL_SPIRE: _WALL_SPIRE_TEX}
_TEX_BY_TILE.update(_BIOME_PROP_TEX)
_TEX_BY_TILE.update(_DUNGEON_PROP_TEX)
_TEX_BY_TILE.update(_NEXUS_PROP_TEX)
_TEX_BY_TILE.update(_ISLAND_PROP_TEX)
_TEX_BY_TILE.update(_WALKWAY_PLANK_TEX)
_TEX_BY_TILE.update({BUILDING_WALL_TILE[_b]: _tex for _b, _tex in _BUILDING_WALL_TEX.items()})


def _tile_hash(tx, ty):
    n = (tx * 374761393 + ty * 668265263) & 0xffffffff
    n = (n ^ (n >> 13)) * 1274126177 & 0xffffffff
    return n ^ (n >> 16)


def coastline_radius(angle):
    """The Realm's own organic coastline shape at a given angle from map
    center (a sum of a few sine terms at different angle-frequencies, same
    "cheap coherent-ish noise" trick as _warp below) - module-level (not a
    make_realm()-local closure like before) specifically so RealmSim's
    island-placement code can call the SAME formula make_realm() actually
    used to carve the coastline, instead of duplicating or guessing at it.
    make_realm() itself now just aliases its local `island_radius` name to
    this function - the returned values are bit-for-bit identical to before
    this was extracted, since max_r here is computed from the same
    REALM_W/REALM_H module constants make_realm() already uses for its own
    local max_r."""
    max_r = min(REALM_W, REALM_H) / 2 - 3
    r = max_r * 0.78
    r += max_r * 0.13 * math.sin(angle * 3 + 1.3)
    r += max_r * 0.08 * math.sin(angle * 5 + 0.7)
    r += max_r * 0.05 * math.sin(angle * 7 + 2.1)
    r += max_r * 0.04 * math.sin(angle * 11 + 0.4)
    return max(max_r * 0.4, r)


def make_realm():
    """
    One immense continent (water ocean all around, organic coastline via
    layered sine noise on the radius, not a circle), carved into ten distinct
    Godlands-style biome regions via a smooth noise-field classification
    (Whittaker-diagram-style: each biome "wins" wherever its own field is
    locally highest), not nearest-seed Voronoi - a straight-line
    nearest-neighbor rule mathematically produces regular polygon (diamond/
    rhombus) cells when seeds sit at roughly evenly-spaced angles, which is
    exactly the earlier version of this function did and the shape the
    biomes visibly showed. Comparing independent smooth fields instead of
    point distances has no straight bisector lines to produce in the first
    place, so the boundaries follow the noise texture instead. The four
    "outer" biomes (Forest/Desert/Tundra/Swamp) are only eligible in the
    outer radius band; the six "inner" ones (Highlands/Ashlands/Jungle/
    Wasteland/Ice/Cave) only in the inner band - mirroring RotMG's real
    beaches-at-the-edge, Godlands-in-the-middle structure, and setting up the
    distance-from-center difficulty gradient applied in _generate_lairs().
    Decorated with the usual rock/dirt/pond patches on top for texture
    variety within each region.
    """
    w, h = REALM_W, REALM_H
    cx, cy = w / 2, h / 2
    max_r = min(w, h) / 2 - 3

    island_radius = coastline_radius

    # Which radius band a tile falls in decides which 4 (outer) or 6 (inner) biome
    # types are even eligible there - a smooth, explicit radial rule instead of
    # emergent seed placement, matching the original's "beaches at the edge,
    # Godlands in the middle" intent directly. INNER_CUTOFF was tuned (see the
    # biome-territory histogram check run after this change) to land roughly the
    # same ~70/30 outer/inner land-area split the old seed-radius-band version
    # produced. Wobbled by a small slice of _warp's own output (see below) so the
    # tier boundary itself isn't a perfect circle either.
    INNER_CUTOFF = 0.5

    # _warp(x, y) is cheap coherent-ish noise from a handful of sine waves at
    # different frequencies/phases (same trick as island_radius's coastline) -
    # it warps the (x, y) used for the nearest-seed distance check, turning what
    # would otherwise be dead-straight Voronoi polygon edges into wavy, natural-
    # looking biome boundaries. Every term is of the form sin(freq*x + freq*y +
    # phase), which the angle-sum identity sin(a+b) = sin(a)cos(b) + cos(a)sin(b)
    # splits into a pure-x factor times a pure-y factor - so instead of calling
    # math.sin() ~700k times (once per land tile, each with 4 terms) we call it
    # ~2*(w+h) times up front to fill small per-row/per-column tables, then every
    # tile's warp is just a handful of table lookups and multiply-adds. This was
    # the single largest chunk of make_realm()'s runtime by profiling (roughly a
    # third of total wall-clock at 1200x1200), which matters once the continent
    # is big enough that generation time becomes a real one-time loading pause.
    sx1 = [math.sin(x * 0.045) for x in range(w)]
    cx1 = [math.cos(x * 0.045) for x in range(w)]
    sy1 = [math.sin(y * 0.02) for y in range(h)]
    cy1 = [math.cos(y * 0.02) for y in range(h)]
    sx2 = [math.sin(x * 0.017 + 2.1) for x in range(w)]
    cx2 = [math.cos(x * 0.017 + 2.1) for x in range(w)]
    sy2 = [math.sin(y * 0.031) for y in range(h)]
    cy2 = [math.cos(y * 0.031) for y in range(h)]
    sx3 = [math.sin(x * 0.008 + 1.7) for x in range(w)]
    sx4 = [math.sin(x * 0.11 + 4.2) for x in range(w)]
    cx4 = [math.cos(x * 0.11 + 4.2) for x in range(w)]
    sy4 = [math.sin(y * 0.09) for y in range(h)]
    cy4 = [math.cos(y * 0.09) for y in range(h)]
    syy1 = [math.sin(y * 0.045 + 1.1) for y in range(h)]
    cyy1 = [math.cos(y * 0.045 + 1.1) for y in range(h)]
    sxx1 = [math.sin(x * 0.02) for x in range(w)]
    cxx1 = [math.cos(x * 0.02) for x in range(w)]
    syy2 = [math.sin(y * 0.017 + 0.4) for y in range(h)]
    cyy2 = [math.cos(y * 0.017 + 0.4) for y in range(h)]
    sxx2 = [math.sin(x * 0.031) for x in range(w)]
    cxx2 = [math.cos(x * 0.031) for x in range(w)]
    syy3 = [math.sin(y * 0.008 + 3.3) for y in range(h)]
    syy4 = [math.sin(y * 0.11 + 1.6) for y in range(h)]
    cyy4 = [math.cos(y * 0.11 + 1.6) for y in range(h)]
    sxx4 = [math.sin(x * 0.09) for x in range(w)]
    cxx4 = [math.cos(x * 0.09) for x in range(w)]

    def _warp(x, y):
        wx = (18 * (sx1[x] * cy1[y] + cx1[x] * sy1[y])
              + 26 * (sx2[x] * cy2[y] - cx2[x] * sy2[y])
              + 34 * sx3[x]
              + 7 * (sx4[x] * cy4[y] + cx4[x] * sy4[y]))
        wy = (18 * (syy1[y] * cxx1[x] - cyy1[y] * sxx1[x])
              + 26 * (syy2[y] * cxx2[x] + cyy2[y] * sxx2[x])
              + 34 * syy3[y]
              + 7 * (syy4[y] * cxx4[x] - cyy4[y] * sxx4[x]))
        return wx, wy

    # a bit of per-tile dither noise, independent of the warp above - used to softly
    # blend the two closest biomes near a boundary instead of a razor-sharp edge,
    # like a real ecotone rather than a country border on a map
    def _dither(x, y):
        return (math.sin(x * 0.31 + y * 0.27) + math.sin(x * 0.53 - y * 0.19 + 1.3)) * 0.25 + 0.5

    # Each biome type gets its own smooth "affinity" field instead of a seed point -
    # wherever a biome's field is locally the highest among its tier's other fields,
    # that biome wins. A field is the sum of 3 plane waves (sin(x*fx+y*fy+phase)) at
    # random, meaningfully different (fx, fy) directions per term - a SINGLE plane
    # wave has dead-straight parallel level sets (which would just reintroduce the
    # straight-edge problem in a different orientation), but summing several
    # non-parallel ones makes the level sets genuinely curve, so there's no straight
    # bisector line for two competing biomes to share in the first place - unlike
    # nearest-seed Voronoi, which always has one. Built with the same angle-sum-
    # identity table trick as _warp above for the same reason: this is evaluated for
    # several biomes on every land tile, so raw math.sin() calls here would undo the
    # earlier perf work that keeps make_realm() inside its ~3s budget.
    AFFINITY_OCTAVES = 5  # was a flat 3 independent-random terms (no octave relationship
    # between them) - the real fBm/multi-octave technique researched for this rehaul:
    # each successive octave's frequency DOUBLES and its amplitude HALVES relative to a
    # single randomized base frequency, so a biome's field is coarse large-scale shape
    # (low octave, high amplitude) with progressively finer detail layered on top (high
    # octave, low amplitude) - real terrain-generation practice for "organic, not
    # regular/lobed" region shapes, confirmed via research, versus the old flat sum of
    # 3 EQUALLY-weighted, independently-random-frequency terms (which stayed closer to
    # its predecessor's still-fairly-regular boundaries - "diamond shapes" - since so
    # few terms of comparable strength rarely cancel into a genuinely organic outline).
    # Each octave still gets its own independently-randomized DIRECTION/phase (this
    # codebase's affinity field is a sum of plane waves, not a single coherent noise
    # function sampled at different scales, so per-octave direction variety is what
    # actually produces multi-directional, non-parallel level-set curvature - see the
    # comment above this function for why a single shared direction would fail).
    def _affinity_tables(is_inner):
        xa_list, xb_list, yc_list, yd_list = [], [], [], []
        # base frequency picked the same way as before (still controls overall biome
        # region SIZE, unrelated to the octave count/detail level above).
        # DIAGNOSIS (real bug, confirmed by rendering actual biome-classification
        # screenshots, not guessed): the inner tier's 6 biomes compete for a disk of
        # radius INNER_CUTOFF*max_r while the outer tier's 4 compete for the much
        # bigger remaining annulus - inner-tier CELLS end up ~4-5x smaller in area
        # than outer-tier cells (6 biomes in ~1/4 the land area vs 4 biomes in ~3/4),
        # so an inner cell only ever samples a small, nearly-linear fraction of the
        # SAME wavelength range used for outer cells - a plane wave looks like a
        # straight ramp over a small enough slice of its own cycle, which is exactly
        # what was still reading as flat/diamond-edged boundaries between inner
        # biomes even with 5 octaves layered on top (screenshots showed this clearly:
        # outer-tier lobes curve organically, inner-tier boundaries stayed visibly
        # more angular/straight-edged). Fix: scale the inner tier's frequency up by
        # ~2.1x (sqrt of that ~4.5x area ratio, so linear/wavelength scale matches
        # cell size) so inner biomes get the same relative curvature-per-cell as
        # outer ones, instead of literally the same absolute wavelength range.
        freq = random.uniform(0.004, 0.0133) * (2.1 if is_inner else 1.0)
        amplitude = 1.0
        for _octave in range(AFFINITY_OCTAVES):
            theta = random.uniform(0, math.tau)
            fx, fy = freq * math.cos(theta), freq * math.sin(theta)
            phase = random.uniform(0, math.tau)
            xa_list.append([amplitude * math.sin(x * fx + phase) for x in range(w)])
            xb_list.append([amplitude * math.cos(x * fx + phase) for x in range(w)])
            yc_list.append([math.cos(y * fy) for y in range(h)])
            yd_list.append([math.sin(y * fy) for y in range(h)])
            freq *= 2.0
            amplitude *= 0.5
        return xa_list, xb_list, yc_list, yd_list

    _affinity_by_biome = {}
    for bt in BIOME_TIER_OUTER:
        _affinity_by_biome[bt] = _affinity_tables(is_inner=False)
    for bt in BIOME_TIER_INNER:
        _affinity_by_biome[bt] = _affinity_tables(is_inner=True)

    def _affinity(bt, x, y):
        xa, xb, yc, yd = _affinity_by_biome[bt]
        total = 0.0
        for i in range(AFFINITY_OCTAVES):
            total += xa[i][x] * yc[i][y] + xb[i][x] * yd[i][y]
        return total

    TIE_MARGIN = 0.22  # widened from 0.15 (which was itself narrowed from an original 0.5
    # per an earlier, explicit "biomes feel too combined/salt-and-peppered" complaint) -
    # this rehaul specifically asked for smoother, less hard-cut region borders, so this
    # nudges back toward a real blended ecotone band WITHOUT fully reverting to the old
    # 0.5 that caused that earlier complaint - a deliberate middle ground, not a revert.
    # Deep inside a region the runner-up's affinity is far behind and this never triggers.

    grid = [[WATER for _ in range(w)] for _ in range(h)]
    land = [[False] * w for _ in range(h)]
    # island_radius() always returns a value in [max_r*0.4, max_r*1.08] (the low end
    # from its own clamp, the high end since its wave amplitudes sum to 0.78+0.13+
    # 0.08+0.05+0.04=1.08 at most) - so tiles inside the smaller radius are land and
    # tiles outside the bigger one are water REGARDLESS of angle, without ever calling
    # island_radius/atan2/hypot for them. This matters a lot once the continent gets
    # big: profiling showed island_radius/_warp's trig calls dominating make_realm()'s
    # runtime, and skipping the coastline check entirely for the guaranteed-land core
    # and guaranteed-water corners (together a meaningful fraction of every tile) cuts
    # real wall-clock time without changing a single output tile.
    guaranteed_land_r = max_r * 0.4
    guaranteed_water_r = max_r * 1.08
    for y in range(h):
        for x in range(w):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            if dist > guaranteed_water_r:
                continue
            if dist > guaranteed_land_r and dist > island_radius(math.atan2(dy, dx)):
                continue
            wx, wy = _warp(x, y)
            # the affinity tables are indexed by integer tile coordinate, so the
            # warped sample point needs clamping into range (unlike the old
            # distance-based check, which was happy with an out-of-grid float) -
            # only matters within a few dozen tiles of the coastline/map edge,
            # where it just mildly steadies the sampled field rather than
            # distorting anything that reads as "the middle of a biome"
            xi = max(0, min(w - 1, int(x + wx)))
            yi = max(0, min(h - 1, int(y + wy)))

            dist_frac = dist / max_r + wx * 0.001  # small wobble so the tier
            # boundary (see INNER_CUTOFF) isn't a perfect circle either
            tier = BIOME_TIER_INNER if dist_frac < INNER_CUTOFF else BIOME_TIER_OUTER

            best_bt, best_v = tier[0], -float("inf")
            second_bt, second_v = tier[0], -float("inf")
            for bt in tier:
                v = _affinity(bt, xi, yi)
                if v > best_v:
                    second_bt, second_v = best_bt, best_v
                    best_v, best_bt = v, bt
                elif v > second_v:
                    second_v, second_bt = v, bt
            # only near-tied boundaries get dithered - deep inside a region the
            # gap to the runner-up biome is huge and this never triggers
            gap = best_v - second_v
            if gap < TIE_MARGIN and _dither(x, y) < 0.5 * (1.0 - gap / TIE_MARGIN):
                best_bt = second_bt
            grid[y][x] = BIOME_GROUND[best_bt]
            land[y][x] = True

    _BASE_GROUND_TILES = set(BIOME_GROUND.values())

    # scattered single-tile decoration props (one of each biome's 10 hand-
    # painted kinds - rock/bush/flowers/boulder/puddle/skull/stump/grasstuft/
    # debris/tree) - placed BEFORE the patch step below so grid[y][x] is
    # still the pure biome-ground tile when the biome is looked up. Sparser
    # than the patches (single tiles, not radius-2-4 areas), reads as
    # "occasional interesting detail" across the continent rather than
    # clutter - see BIOME_PROP_TILE/BIOME_PROP_KINDS near the top of the file.
    #
    # Placed via a seed-and-spread pass rather than independent per-tile
    # sampling: real vegetation/rock fields cluster (trees compete for
    # light/water, undergrowth fills canopy gaps) instead of sprinkling
    # uniformly, so a handful of cluster centers are picked on land first,
    # then each cluster's share of props is scattered around its center with
    # a density that falls off with distance (closer = more likely). Total
    # placed count is still budgeted against the same decor_prop_count as
    # before, so density/perf stays roughly the same as the old uniform pass.
    decor_prop_count = round(10 * (w * h) / (70 * 70))
    num_clusters = max(1, decor_prop_count // 6)
    placed = 0
    for _ in range(num_clusters):
        cx = cy = None
        for _try in range(30):
            tx, ty = random.randint(2, w - 3), random.randint(2, h - 3)
            if land[ty][tx]:
                cx, cy = tx, ty
                break
        if cx is None:
            continue
        cluster_share = max(1, round(decor_prop_count / num_clusters))
        cluster_radius = random.uniform(4.0, 9.0)
        attempts = 0
        cluster_placed = 0
        # generous retry budget per cluster (water/off-biome misses are
        # common near coastlines) so the total placed count still lands
        # close to decor_prop_count, matching the old pass's density.
        while cluster_placed < cluster_share and attempts < cluster_share * 4:
            attempts += 1
            # random.random() ** 1.5 biases samples toward the center -
            # the "falloff" that makes clusters read as a dense core
            # thinning out at the edges, not a flat disc.
            r = cluster_radius * (random.random() ** 1.5)
            ang = random.uniform(0, math.tau)
            px = int(cx + r * math.cos(ang))
            py = int(cy + r * math.sin(ang))
            if not (2 <= px <= w - 3 and 2 <= py <= h - 3):
                continue
            if not land[py][px]:
                continue
            biome_name = GROUND_TO_BIOME_NAME.get(grid[py][px])
            if biome_name is None:
                continue
            kind = random.choices(BIOME_PROP_KINDS, weights=_biome_prop_weights(biome_name))[0]
            grid[py][px] = BIOME_PROP_TILE[(biome_name, kind)]
            cluster_placed += 1
            placed += 1

    # decorative patches (rock outcrops, dirt clearings, small ponds) - land only,
    # never overwrite the ocean, so the coastline stays clean. What kind of patch can
    # appear depends on the underlying biome, so a tundra region gets icy rock instead
    # of a random patch of grass, an ashland gets cracked rock instead of a pond, etc.
    # Guarded to never overwrite a decoration prop placed just above.
    decor_by_ground = {
        GRASS: [GRASS2, DIRT, ROCK, WATER],
        SAND: [DIRT, ROCK, WATER],
        SNOW: [STONE, ROCK, WATER],
        SWAMP: [DIRT, WATER, WATER],
        STONE: [ROCK, DIRT],
        ASH: [ROCK, DIRT],
        JUNGLE: [GRASS, DIRT, WATER],
        WASTELAND: [ROCK, DIRT],
        ICE: [SNOW, ROCK],
        CAVE: [ROCK, DIRT],
    }
    patch_count = round(26 * (w * h) / (70 * 70))
    for _ in range(patch_count):
        px, py = random.randint(2, w - 3), random.randint(2, h - 3)
        if not land[py][px] or grid[py][px] not in _BASE_GROUND_TILES:
            continue
        options = decor_by_ground.get(grid[py][px], [GRASS2, DIRT, ROCK, WATER])
        tile = random.choice(options)
        radius = random.randint(2, 4)
        for yy in range(py - radius, py + radius + 1):
            for xx in range(px - radius, px + radius + 1):
                if (0 <= xx < w and 0 <= yy < h and land[yy][xx]
                        and grid[yy][xx] in _BASE_GROUND_TILES
                        and (xx - px) ** 2 + (yy - py) ** 2 <= radius * radius):
                    grid[yy][xx] = tile

    # keep the arrival point clear and guaranteed walkable regardless of biome/patch RNG
    for y in range(h // 2 - 2, h // 2 + 3):
        for x in range(w // 2 - 2, w // 2 + 3):
            grid[y][x] = GRASS
    return grid


def make_nexus():
    """A spectacular, huge hub: a grand central fountain plaza around the Realm
    portal, ringed by statues at its four corners, with banner pillars lining
    all four walls - RotMG's Nexus as a real landmark-filled social space, not
    a bare rectangle with a couple of portals in it. Grown from the original
    36x28 to 64x50 with garden clusters, a minor well, and an announcement
    board scattered around the plaza - all walkable, so the extra space reads
    as a real place to wander, not just padding."""
    grid = [[NEXUS_FLOOR for _ in range(NEXUS_W)] for _ in range(NEXUS_H)]
    for x in range(NEXUS_W):
        grid[0][x] = ROCK
        grid[NEXUS_H - 1][x] = ROCK
    for y in range(NEXUS_H):
        grid[y][0] = ROCK
        grid[y][NEXUS_W - 1] = ROCK
    mid_y, mid_x = NEXUS_H // 2, NEXUS_W // 2

    # a bigger fountain ring than before, with a decorative outer rim
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            d2 = dx * dx + dy * dy
            if d2 <= 16:
                grid[mid_y + dy][mid_x + dx] = NEXUS_FOUNTAIN
    grid[mid_y][mid_x] = PORTAL

    # a walled hallway running north from just past the fountain's own edge,
    # with the Vault and Bazaar portals recessed as MIRRORED alcoves in its
    # side walls (not sitting directly on the fountain's row like before) -
    # a real architectural feature, and more symmetric: both portals are now
    # the same distance from the hallway's centerline, one to each side,
    # instead of asymmetric relative to the garden/well/board placements below.
    hall_half_w = 4
    hall_top, hall_bottom = mid_y - 13, mid_y - 6
    for y in range(hall_top, hall_bottom + 1):
        grid[y][mid_x - hall_half_w - 1] = ROCK
        grid[y][mid_x + hall_half_w + 1] = ROCK
        for x in range(mid_x - hall_half_w, mid_x + hall_half_w + 1):
            grid[y][x] = NEXUS_FLOOR
    alcove_y = (hall_top + hall_bottom) // 2
    grid[alcove_y][mid_x - hall_half_w - 1] = VAULT_TILE
    grid[alcove_y][mid_x + hall_half_w + 1] = BAZAAR_PORTAL

    # four statues guarding the corners of the fountain plaza
    for sy, sx in ((-5, -5), (-5, 5), (5, -5), (5, 5)):
        grid[mid_y + sy][mid_x + sx] = NEXUS_STATUE

    # banner pillars along all four walls, not just the top/bottom
    for x in range(3, NEXUS_W - 3, 4):
        grid[2][x] = NEXUS_BANNER
        grid[NEXUS_H - 3][x] = NEXUS_BANNER
    for y in range(4, NEXUS_H - 4, 4):
        grid[y][2] = NEXUS_BANNER
        grid[y][NEXUS_W - 3] = NEXUS_BANNER

    # garden clusters in the four quadrants, well off the main plaza and paths
    for gy, gx in ((-16, -22), (-16, 22), (16, -22), (16, 22)):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx * dx + dy * dy <= 5:
                    yy, xx = mid_y + gy + dy, mid_x + gx + dx
                    if 1 <= yy < NEXUS_H - 1 and 1 <= xx < NEXUS_W - 1:
                        grid[yy][xx] = NEXUS_GARDEN

    # a minor second well, off to one side of the plaza
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            if dx * dx + dy * dy <= 1:
                grid[mid_y - 12][mid_x] = NEXUS_WELL
                grid[mid_y - 12 + dy][mid_x + dx] = NEXUS_WELL

    # an announcement board near the entrance
    grid[mid_y + 12][mid_x - 1] = NEXUS_BOARD
    grid[mid_y + 12][mid_x] = NEXUS_BOARD
    grid[mid_y + 12][mid_x + 1] = NEXUS_BOARD

    # the Echo Keeper - a single tile a few steps from the board, in the
    # walkable plaza between the board and the garden clusters
    grid[mid_y + 12][mid_x + 5] = ECHO_KEEPER_TILE

    # scattered decoration props (see NEXUS_PROP_TILE/NEXUS_TALL_PROP_KINDS) -
    # random positions across whatever's STILL plain NEXUS_FLOOR at this point,
    # so this never overwrites the fountain/portals/statues/banners/gardens/
    # well/board placed above
    all_nexus_kinds = NEXUS_PROP_KINDS + NEXUS_TALL_PROP_KINDS
    placed = 0
    target_count = random.randint(15, 25)
    attempts = 0
    while placed < target_count and attempts < target_count * 8:
        attempts += 1
        px, py = random.randint(1, NEXUS_W - 2), random.randint(1, NEXUS_H - 2)
        if grid[py][px] != NEXUS_FLOOR:
            continue
        kind = random.choice(all_nexus_kinds)
        tile_id = (TALL_PROP_TILE[("nexus", kind)] if kind in NEXUS_TALL_PROP_KINDS
                   else NEXUS_PROP_TILE[kind])
        grid[py][px] = tile_id
        placed += 1
    return grid


def make_vault_room():
    """A small, fixed, hand-authored room - not a randomized generator, so the
    Vault feels like the same trusted space every visit. A perimeter of
    vault-themed walls, a portal back to the Nexus, and VAULT_CHEST_COUNT
    chests laid out in two rows to walk up to and interact with."""
    from game.items import VAULT_CHEST_COUNT
    grid = [[NEXUS_FLOOR for _ in range(VAULT_ROOM_W)] for _ in range(VAULT_ROOM_H)]
    for x in range(VAULT_ROOM_W):
        grid[0][x] = WALL_VAULT
        grid[VAULT_ROOM_H - 1][x] = WALL_VAULT
    for y in range(VAULT_ROOM_H):
        grid[y][0] = WALL_VAULT
        grid[y][VAULT_ROOM_W - 1] = WALL_VAULT

    mid_x = VAULT_ROOM_W // 2
    grid[VAULT_ROOM_H - 2][mid_x] = PORTAL  # back to the Nexus

    cols = 4
    start_x = mid_x - (cols - 1)
    for i in range(VAULT_CHEST_COUNT):
        row, col = divmod(i, cols)
        cy = 3 + row * 3
        cx = start_x + col * 2
        if 1 <= cy < VAULT_ROOM_H - 1 and 1 <= cx < VAULT_ROOM_W - 1:
            grid[cy][cx] = CHEST

    # Room dressing - gold/gem/sack clutter and furniture flanking the chest
    # rows, clear of the portal's approach. Guarded (bounds + "don't
    # overwrite a chest/portal") so this stays safe if VAULT_CHEST_COUNT or
    # the chest layout above ever changes.
    decorations = [
        (3, 4, VAULT_PILLAR), (16, 4, VAULT_BOOKSHELF),
        (16, 11, VAULT_CANDELABRA), (3, 11, VAULT_CANDELABRA),
        (3, 7, VAULT_GOLD), (16, 10, VAULT_GOLD),
        (16, 7, VAULT_GEMS), (3, 10, VAULT_GEMS),
        (1, 1, VAULT_COBWEB), (18, 1, VAULT_COBWEB),
        (4, 12, VAULT_SACK), (15, 4, VAULT_SACK),
        (14, 12, VAULT_POTTERY), (10, 11, VAULT_RUNE),
    ]
    for dx, dy, tile in decorations:
        if 1 <= dy < VAULT_ROOM_H - 1 and 1 <= dx < VAULT_ROOM_W - 1 and grid[dy][dx] == NEXUS_FLOOR:
            grid[dy][dx] = tile
    return grid


def make_bazaar():
    """A bigger marketplace than the original cramped 20x14 - a real central fountain
    plaza (same NEXUS_FOUNTAIN tile as the Nexus's) ringed by market stalls, RotMG's
    Bazaar-as-a-second-social-hub scale rather than a single narrow aisle."""
    grid = [[BAZAAR_FLOOR for _ in range(BAZAAR_W)] for _ in range(BAZAAR_H)]
    for x in range(BAZAAR_W):
        grid[0][x] = ROCK
        grid[BAZAAR_H - 1][x] = ROCK
    for y in range(BAZAAR_H):
        grid[y][0] = ROCK
        grid[y][BAZAAR_W - 1] = ROCK

    mid_y, mid_x = BAZAAR_H // 2, BAZAAR_W // 2
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx * dx + dy * dy <= 5:
                grid[mid_y + dy][mid_x + dx] = NEXUS_FOUNTAIN

    # four rows of market stalls to walk between, framing the fountain plaza
    for x in range(3, BAZAAR_W - 3, 3):
        grid[3][x] = STALL
        grid[6][x] = STALL
        grid[BAZAAR_H - 7][x] = STALL
        grid[BAZAAR_H - 4][x] = STALL
    for x in range(3, BAZAAR_W - 3, 5):
        grid[2][x] = NEXUS_BANNER
        grid[BAZAAR_H - 3][x] = NEXUS_BANNER

    grid[mid_y][2] = PORTAL  # back to Nexus
    return grid


BONUS_ROOM_COUNT = 6  # fallback used by any theme not listed in ROOM_COUNT_BY_THEME

# per-theme room counts/sizes so dungeons are genuinely varied, not just a
# reskinned identical layout (see realm_sim.DUNGEON_THEMES for the theme keys)
ROOM_COUNT_BY_THEME = {
    "generic": 7, "frozen_crypt": 7, "jungle_ruins": 8,
    "cave": 8, "ember_den": 5, "sunken_grotto": 8, "wind_spire": 9,
}
ROOM_SIZE_BY_THEME = {
    "ember_den": (10, 15),  # fewer, larger rooms, tightly linked
    "wind_spire": (6, 9),   # narrower chambers - reads as "climbing a spire"
}
DEFAULT_ROOM_SIZE = (7, 11)
# themes whose rooms are placed as a directional CHAIN (each room offset from
# the previous one) instead of independently-scattered rectangles
CHAIN_THEMES = {"sunken_grotto", "wind_spire"}


def _carve_corridor(grid, a, b, floor_tile=GRASS2, width=2):
    """Carves an L-shaped, `width`-tile-wide walkable path between two (tx, ty)
    points, so every room is guaranteed reachable from the entrance. Returns
    a list of `width` (tx, ty) tiles spanning the corridor's full width at
    its midpoint (or None if nothing was actually carved) - callers that
    don't need it (most) just ignore the return value; make_bonus_room's
    breakable-wall placement uses it to find real tiles that are actually
    part of THIS corridor, since the L-shape's bend direction is randomized
    here and not knowable from outside."""
    (ax, ay), (bx, by) = a, b
    h, w = len(grid), len(grid[0])
    carved = []  # only tiles that were NOT already floor before this call - i.e. the real
    # corridor-only stretch between the two rooms, not the parts of the L-path that
    # happen to pass back through either room's own already-floor interior

    def carve_h(y0, x0, x1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for dy in range(width):
                yy = y0 + dy
                if 0 <= yy < h and 0 <= x < w:
                    if grid[yy][x] != floor_tile:
                        carved.append((x, yy))
                    grid[yy][x] = floor_tile

    def carve_v(x0, y0, y1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for dx in range(width):
                xx = x0 + dx
                if 0 <= y < h and 0 <= xx < w:
                    if grid[y][xx] != floor_tile:
                        carved.append((xx, y))
                    grid[y][xx] = floor_tile

    if random.random() < 0.5:
        carve_h(ay, ax, bx)
        carve_v(bx, ay, by)
    else:
        carve_v(ax, ay, by)
        carve_h(by, ax, bx)

    if not carved:
        return None
    # the `width` consecutive tiles starting at the midpoint span the corridor's
    # FULL width at that point (append order groups them together, see carve_h/
    # carve_v above) - orientation-agnostic, unlike guessing horizontal-vs-vertical
    # from outside this function
    mid = (len(carved) // 2) - (len(carved) // 2) % width
    return carved[mid:mid + width]


def _place_rooms_rect(w, h, count, size_range):
    """Baseline placement (generic/frozen_crypt/jungle_ruins/ember_den):
    random non-overlapping rectangles, connected nearest-first afterward."""
    lo, hi = size_range
    rooms = []
    attempts = 0
    while len(rooms) < count and attempts < 400:
        attempts += 1
        rw, rh = random.randint(lo, hi), random.randint(lo, hi)
        rx, ry = random.randint(2, w - rw - 3), random.randint(2, h - rh - 3)
        rect = pygame.Rect(rx, ry, rw, rh)
        if any(rect.inflate(4, 4).colliderect(r) for r in rooms):
            continue
        rooms.append(rect)
    return rooms


def _place_rooms_chain(w, h, count, size_range, winding):
    """sunken_grotto/wind_spire: each room is placed relative to the PREVIOUS
    one along a wandering (grotto) or mostly-straight (spire) heading, instead
    of independently-scattered rectangles - reads as one continuous chain of
    rooms rather than a scattered floor plan. Already in path order, so the
    caller should NOT re-sort these with the nearest-neighbor pass."""
    lo, hi = size_range
    rooms = []
    rw, rh = random.randint(lo, hi), random.randint(lo, hi)
    cx, cy = w * 0.15, h * 0.5
    angle = random.uniform(-30, 30)
    for _ in range(count):
        rx = int(max(2, min(w - rw - 3, cx - rw / 2)))
        ry = int(max(2, min(h - rh - 3, cy - rh / 2)))
        rect = pygame.Rect(rx, ry, rw, rh)
        # A winding chain can curl back on itself and overlap an EARLIER room in
        # the same dungeon - confirmed via adversarial testing to occasionally
        # (~0.14% of sunken_grotto instances) let a solid decoration prop land
        # on the boss room's own tile and seal it shut, an unbeatable dungeon.
        # Nudge the heading away and retake a step (not a totally fresh random
        # spot, which would break the "one continuous chain" look this function
        # exists for) until clear - same overlap-avoidance IDEA
        # _place_rooms_rect/_place_rooms_cave already use, just re-aimed instead
        # of re-rolled from scratch, since a chain's next room is always relative
        # to the previous one.
        retries = 0
        while any(rect.inflate(2, 2).colliderect(r) for r in rooms) and retries < 30:
            retries += 1
            angle = max(-85, min(85, angle + random.uniform(50, 130) * random.choice((-1, 1))))
            step = random.uniform(14, 20)
            cx = max(rw + 2, min(w - rw - 3, cx + math.cos(math.radians(angle)) * step))
            cy = max(rh + 2, min(h - rh - 3, cy + math.sin(math.radians(angle)) * step))
            rx = int(max(2, min(w - rw - 3, cx - rw / 2)))
            ry = int(max(2, min(h - rh - 3, cy - rh / 2)))
            rect = pygame.Rect(rx, ry, rw, rh)
        if any(rect.inflate(2, 2).colliderect(r) for r in rooms):
            # the angle-deflection retries above can still fail near a map edge -
            # cx/cy get clamped back toward roughly the same spot on every retry
            # regardless of the new angle, so 30 retries can exhaust themselves
            # while barely moving (confirmed via adversarial testing: both
            # real failures were near a grid corner). Guaranteed-to-terminate
            # fallback: search genuinely random positions anywhere in the grid
            # (same technique _place_rooms_rect already uses successfully) - a
            # rare visible "break" in the chain's continuity once in a great
            # while is far better than an unbeatable, sealed-shut dungeon.
            for _ in range(200):
                fx = random.randint(2, w - rw - 3)
                fy = random.randint(2, h - rh - 3)
                candidate = pygame.Rect(fx, fy, rw, rh)
                if not any(candidate.inflate(2, 2).colliderect(r) for r in rooms):
                    rect = candidate
                    cx, cy = rect.centerx, rect.centery
                    break
        rooms.append(rect)
        step = random.uniform(14, 20)
        angle += random.uniform(-70, 70) if winding else random.uniform(-15, 15)
        angle = max(-80, min(80, angle))
        cx = max(rw + 2, min(w - rw - 3, cx + math.cos(math.radians(angle)) * step))
        cy = max(rh + 2, min(h - rh - 3, cy + math.sin(math.radians(angle)) * step))
        rw, rh = random.randint(lo, hi), random.randint(lo, hi)
    return rooms


def _place_rooms_cave(w, h, count):
    """cave theme: room CENTERS placed like the rect baseline, but the actual
    carve (see _carve_blob) unions a few overlapping circles instead of a
    hard rectangle for a genuinely organic, irregular silhouette."""
    rooms = []
    attempts = 0
    while len(rooms) < count and attempts < 400:
        attempts += 1
        radius = random.randint(4, 6)
        cx = random.randint(radius + 2, w - radius - 3)
        cy = random.randint(radius + 2, h - radius - 3)
        rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
        if any(rect.inflate(4, 4).colliderect(r) for r in rooms):
            continue
        rooms.append(rect)
    return rooms


def _carve_blob(grid, rect, floor_tile):
    """Carves 3-4 overlapping circles inside/around `rect` for an organic
    cave-room silhouette instead of _carve_corridor's clean rectangle fill."""
    h, w = len(grid), len(grid[0])
    cx, cy = rect.centerx, rect.centery
    base_r = max(rect.w, rect.h) / 2
    blobs = [(cx, cy, base_r)]
    for _ in range(random.randint(2, 3)):
        ang = random.uniform(0, 360)
        dist = base_r * random.uniform(0.3, 0.6)
        ox = cx + math.cos(math.radians(ang)) * dist
        oy = cy + math.sin(math.radians(ang)) * dist
        blobs.append((ox, oy, base_r * random.uniform(0.55, 0.8)))
    for yy in range(max(0, rect.top - 3), min(h, rect.bottom + 3)):
        for xx in range(max(0, rect.left - 3), min(w, rect.right + 3)):
            for bx, by, br in blobs:
                if (xx - bx) ** 2 + (yy - by) ** 2 <= br * br:
                    grid[yy][xx] = floor_tile
                    break


def make_bonus_room(floor_tile=None, wall_tile=None, theme_name="generic"):
    """
    A real multi-room dungeon (not one small arena) a mob-death portal leads
    into: several chambers carved out of solid rock and connected by
    corridors, ending in a dedicated boss room at the far end - RotMG-style
    "vault"/dungeon structure. Returns (grid, info):
    - "entrance"/"boss_room": center tile of each (where the return portal
      sits / where the boss spawns) - unchanged from before.
    - "rooms": every OTHER (non-entrance, non-boss) room's center + tile
      rect, for realm_sim to populate with a fixed, non-respawning mob pod.
    - "obstacle_spots": a handful of (tx, ty) tile coords inside some of
      those rooms for destructible one-shot wall props.

    floor_tile/wall_tile/theme_name: which enemy dropped the portal decides
    the dungeon's theme (see realm_sim.DUNGEON_THEMES) - a Cave Warren looks,
    feels, AND IS SHAPED differently than a Frozen Crypt, not just a
    re-skinned generic room (see ROOM_COUNT_BY_THEME/CHAIN_THEMES above).
    """
    floor_tile = GRASS2 if floor_tile is None else floor_tile
    wall_tile = ROCK if wall_tile is None else wall_tile
    w, h = BONUS_W, BONUS_H
    grid = [[wall_tile for _ in range(w)] for _ in range(h)]

    count = ROOM_COUNT_BY_THEME.get(theme_name, BONUS_ROOM_COUNT)
    size_range = ROOM_SIZE_BY_THEME.get(theme_name, DEFAULT_ROOM_SIZE)
    is_cave = theme_name == "cave"
    is_chain = theme_name in CHAIN_THEMES

    if is_cave:
        rooms = _place_rooms_cave(w, h, count)
    elif is_chain:
        rooms = _place_rooms_chain(w, h, count, size_range, winding=(theme_name == "sunken_grotto"))
    else:
        rooms = _place_rooms_rect(w, h, count, size_range)
    if not rooms:  # astronomically unlikely, but never leave an unwalkable dungeon
        rooms = [pygame.Rect(w // 2 - 4, h // 2 - 4, 8, 8)]

    if is_chain:
        # already placed in path order - a nearest-neighbor re-sort would
        # defeat the whole point of a deliberate winding/linear chain
        path = rooms
    else:
        # order into a path starting from the first room, each next room is the
        # nearest not-yet-connected one - keeps corridors short and non-crossing-ish,
        # and makes the LAST room the one furthest along the path: the boss room
        path = [rooms[0]]
        remaining = rooms[1:]
        while remaining:
            last = path[-1]
            nxt = min(remaining, key=lambda r: (r.centerx - last.centerx) ** 2 + (r.centery - last.centery) ** 2)
            path.append(nxt)
            remaining.remove(nxt)

    for r in path:
        if is_cave:
            _carve_blob(grid, r, floor_tile)
        else:
            for yy in range(r.top, r.bottom):
                for xx in range(r.left, r.right):
                    grid[yy][xx] = floor_tile
    corridor_width = 1 if theme_name == "wind_spire" else 2
    # a subset of inter-room corridors get a tougher, wider destructible wall
    # blocking them - the room graph is never actually gated (every corridor
    # still gets carved to real floor first), so a dungeon is always solvable
    # even before anything is destroyed; this just makes a few connections
    # "break the wall to get through" instead of a free walk. Skip the FIRST
    # connection (entrance -> room 1) so the dungeon is never blocked at the
    # very start.
    wall_obstacle_spots = []
    for i in range(1, len(path)):
        mid = _carve_corridor(grid, path[i - 1].center, path[i].center, floor_tile=floor_tile, width=corridor_width)
        if i > 1 and mid and random.random() < 0.4:
            wall_obstacle_spots.extend(mid)  # spans the corridor's full width - no sidestepping around it

    entrance, boss_room = path[0], path[-1]
    grid[entrance.centery][entrance.centerx] = PORTAL

    # fixed, non-respawning mob pods (see realm_sim.RealmSim) live in every
    # room that's neither the entrance nor the boss room
    middle_rooms = path[1:-1]
    rooms_info = [{"center": (r.centerx, r.centery), "rect": (r.left, r.top, r.w, r.h)} for r in middle_rooms]

    # a couple of destructible one-shot wall obstacles scattered inside about
    # half the middle rooms - a player-facing shortcut/loot-teaser element,
    # never placed in the entrance or boss room
    obstacle_spots = []
    for r in middle_rooms:
        if random.random() < 0.5:
            continue
        for _ in range(random.randint(1, 2)):
            ox = random.randint(r.left + 1, r.right - 2)
            oy = random.randint(r.top + 1, r.bottom - 2)
            if grid[oy][ox] == floor_tile:
                obstacle_spots.append((ox, oy))

    # hand-painted decoration props (see DUNGEON_PROP_TILE above) - 1-3 per
    # middle room, baked straight into the grid same as Vault's decorations
    # list, never in the entrance/boss room and never on an obstacle_spots
    # tile (an Obstacle entity spawns there later; a decoration underneath
    # would just be immediately hidden/overwritten)
    prop_theme = theme_name if theme_name in DUNGEON_THEME_FLOOR else "generic"
    prop_kinds = DUNGEON_PROP_KINDS + [DUNGEON_SPECIAL_KIND[prop_theme]]
    claimed = set(obstacle_spots)
    for r in middle_rooms:
        for _ in range(random.randint(1, 3)):
            px = random.randint(r.left + 1, r.right - 2)
            py = random.randint(r.top + 1, r.bottom - 2)
            if (px, py) in claimed or grid[py][px] != floor_tile:
                continue
            kind = random.choice(prop_kinds)
            grid[py][px] = DUNGEON_PROP_TILE[(prop_theme, kind)]
            claimed.add((px, py))

    # tall totems/poles/pillars/banners/braziers/signposts (see TALL_PROP_TILE
    # above) - previously ONLY ever appeared in the open-Realm landmark
    # buildings (stamp_lair_building), dungeons got none at all. ~35% chance
    # per middle room, placed against a wall-adjacent tile (top/bottom row of
    # the room) same "reads as architecture, not floating in the open middle"
    # idea stamp_lair_building already uses for its own tall props. Uses the
    # "dungeon:" -prefixed key (see TALL_PROP_TILE's own comment) since a
    # bare theme name can collide with an identically-named biome (e.g. "cave").
    tall_prop_area = f"dungeon:{prop_theme}"
    for r in middle_rooms:
        if random.random() >= 0.35:
            continue
        wall_adjacent = [(x, r.top) for x in range(r.left, r.right)]
        wall_adjacent += [(x, r.bottom - 1) for x in range(r.left, r.right)]
        random.shuffle(wall_adjacent)
        for (px, py) in wall_adjacent:
            if (px, py) in claimed or grid[py][px] != floor_tile:
                continue
            grid[py][px] = TALL_PROP_TILE[(tall_prop_area, random.choice(TALL_PROP_KINDS))]
            claimed.add((px, py))
            break

    # a hidden room, RESERVED but left as solid wall (not carved into floor)
    # at generation - only connected later via reveal_hidden_room(), and only
    # if this instance's secret quest (see realm_sim.SECRET_QUEST_KINDS) is
    # actually rolled AND completed. Placed with the same non-overlapping-rect
    # check as the baseline rooms; simply omitted (None) if no spot is found -
    # not every dungeon instance needs one.
    hidden_room = None
    for _ in range(40):
        hw, hh = random.randint(6, 9), random.randint(6, 9)
        hx, hy = random.randint(2, w - hw - 3), random.randint(2, h - hh - 3)
        rect = pygame.Rect(hx, hy, hw, hh)
        if any(rect.inflate(4, 4).colliderect(r) for r in path):
            continue
        hidden_room = {"center": (rect.centerx, rect.centery), "rect": (rect.left, rect.top, rect.w, rect.h)}
        break

    # the boss's second-phase pocket - a genuinely SEPARATE walled-off section of
    # this SAME grid, floor carved right now (unlike hidden_room, which stays wall
    # until a quest reveals it) but deliberately never corridor-connected at
    # GENERATION time - a real wall of solid rock on every side keeps it
    # unreachable on foot until RealmSim's phase-2-access quest actually
    # completes (see _maybe_open_phase2_door), at which point open_phase2_door()
    # (right below reveal_hidden_room, same idea) carves the connecting corridor.
    phase2_pocket = None
    all_reserved = list(path) + ([pygame.Rect(*hidden_room["rect"])] if hidden_room else [])
    for _ in range(40):
        pw, ph = random.randint(7, 10), random.randint(7, 10)
        px, py = random.randint(2, w - pw - 3), random.randint(2, h - ph - 3)
        rect = pygame.Rect(px, py, pw, ph)
        if any(rect.inflate(4, 4).colliderect(r) for r in all_reserved):
            continue
        for yy in range(rect.top, rect.bottom):
            for xx in range(rect.left, rect.right):
                grid[yy][xx] = floor_tile
        phase2_pocket = {"center": (rect.centerx, rect.centery), "rect": (rect.left, rect.top, rect.w, rect.h)}
        break

    return grid, {"entrance": (entrance.centerx, entrance.centery),
                  "boss_room": (boss_room.centerx, boss_room.centery),
                  "rooms": rooms_info,
                  "obstacle_spots": obstacle_spots,
                  "wall_obstacle_spots": wall_obstacle_spots,
                  "hidden_room": hidden_room,
                  "phase2_pocket": phase2_pocket}


def open_phase2_door(grid, phase2_pocket, connect_to_center, floor_tile, theme_name="generic"):
    """Carves a corridor connecting the boss's ALREADY-floor-carved phase-2
    pocket (see make_bonus_room's "phase2_pocket" - unlike hidden_room, its
    room interior is real floor from generation, just never corridor-
    connected to anything) to `connect_to_center` - called once by RealmSim
    the instant its phase-2-access quest actually opens the door (see
    realm_sim.RealmSim._maybe_open_phase2_door). Turning solid rock into a
    corridor at this exact moment IS "the door opening" - no separate door
    tile/sprite needed, same mechanic reveal_hidden_room already uses for its
    own reveal moment, just aimed at a different room/trigger."""
    _carve_corridor(grid, phase2_pocket["center"], connect_to_center, floor_tile=floor_tile, width=2)


def reveal_hidden_room(grid, hidden_room, connect_to_center, floor_tile, theme_name="generic"):
    """Carves a previously-reserved hidden room (see make_bonus_room's
    "hidden_room" info) into real floor plus a corridor connecting it to
    `connect_to_center` - called once by RealmSim the moment a dungeon's
    secret quest completes.

    `theme_name` is optional (defaults to "generic") so an existing call
    site that doesn't pass it still works unchanged - pass the dungeon's
    real theme to get correctly-themed decoration props instead of the
    generic-theme look. A handful of hand-painted dungeon-decoration props
    (see DUNGEON_PROP_TILE) are scattered into the room as a reveal payoff -
    ONLY the always-walkable kinds are used (never idol/crate/crystal/
    coffin/pillar/urn), since this is a small room with exactly one
    corridor in and a decoration landing on it would risk softlocking the
    room shut."""
    rl, rt, rw, rh = hidden_room["rect"]
    for yy in range(rt, rt + rh):
        for xx in range(rl, rl + rw):
            grid[yy][xx] = floor_tile
    _carve_corridor(grid, hidden_room["center"], connect_to_center, floor_tile=floor_tile, width=2)

    prop_theme = theme_name if theme_name in DUNGEON_THEME_FLOOR else "generic"
    prop_kinds = [k for k in DUNGEON_PROP_KINDS + [DUNGEON_SPECIAL_KIND[prop_theme]]
                  if k not in DUNGEON_PROP_SOLID_KINDS]
    cx, cy = hidden_room["center"]
    for _ in range(random.randint(3, 5)):
        px = random.randint(rl + 1, rl + rw - 2)
        py = random.randint(rt + 1, rt + rh - 2)
        if (px, py) == (cx, cy) or grid[py][px] != floor_tile:
            continue
        kind = random.choice(prop_kinds)
        grid[py][px] = DUNGEON_PROP_TILE[(prop_theme, kind)]


_ARCH_STONE = (58, 54, 50)
_ARCH_STONE_LIGHT = (82, 77, 71)


def _draw_archway_tile(surf, cx, cy, kind_color, t_ms):
    """The tile-drawn twin of entities.Portal._draw_archway - same stone-
    pillar-and-lintel silhouette with a glowing colored doorway interior, for
    the two "portal-like" tile cells (Vault, Bazaar-return) that aren't
    Portal objects. Kept as its own small function (not shared code across
    modules) since it draws against a tile's fixed center point/time rather
    than a moving entity's pulsing radius - the visual result matches, the
    inputs don't."""
    r = int(C.TILE * 0.34 + 2 * math.sin(t_ms / 260.0))
    pillar_w = max(3, int(r * 0.4))
    pillar_h = int(r * 2.1)
    top = cy - pillar_h // 2
    glow = tuple(max(0, c - 30) for c in kind_color)
    ring = kind_color
    core = tuple(min(255, c + 60) for c in kind_color)

    glow_d = int(r * 3.2)
    glow_surf = pygame.Surface((glow_d, glow_d), pygame.SRCALPHA)
    pygame.draw.circle(glow_surf, (*glow, 100), (glow_d // 2, glow_d // 2), int(r * 1.3))
    surf.blit(glow_surf, (cx - glow_d // 2, cy - glow_d // 2))

    pygame.draw.rect(surf, _ARCH_STONE, (cx - r - pillar_w, top, pillar_w, pillar_h), border_radius=2)
    pygame.draw.rect(surf, _ARCH_STONE, (cx + r, top, pillar_w, pillar_h), border_radius=2)
    pygame.draw.rect(surf, _ARCH_STONE_LIGHT, (cx - r - pillar_w, top, pillar_w, 4))
    pygame.draw.rect(surf, _ARCH_STONE_LIGHT, (cx + r, top, pillar_w, 4))
    arch_rect = (cx - r - pillar_w, top - r, (r + pillar_w) * 2, r * 2)
    pygame.draw.arc(surf, _ARCH_STONE, arch_rect, 0, math.pi, max(3, pillar_w))

    inner_rect = (cx - r, top, r * 2, pillar_h)
    pygame.draw.ellipse(surf, ring, inner_rect)
    pad = max(2, pillar_w // 2)
    pygame.draw.ellipse(surf, core, (cx - r + pad, top + pad, r * 2 - pad * 2, pillar_h - pad * 2))


class TileMap:
    def __init__(self, grid):
        self.grid = grid
        self.h = len(grid)
        self.w = len(grid[0])

    def is_solid(self, wx, wy):
        tx, ty = int(wx // C.TILE), int(wy // C.TILE)
        if tx < 0 or ty < 0 or tx >= self.w or ty >= self.h:
            return True
        return self.grid[ty][tx] in SOLID

    def tile_at(self, wx, wy):
        tx, ty = int(wx // C.TILE), int(wy // C.TILE)
        if 0 <= ty < self.h and 0 <= tx < self.w:
            return self.grid[ty][tx]
        return None

    def speed_multiplier(self, wx, wy):
        return SPEED_MULT.get(self.tile_at(wx, wy), 1.0)

    def near_water(self, wx, wy, radius=1.5):
        """True if a WATER tile is within `radius` tiles - used by fishing so you
        have to actually stand at the water's edge, not just anywhere on land."""
        tx, ty = int(wx // C.TILE), int(wy // C.TILE)
        r = int(radius) + 1
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                xx, yy = tx + dx, ty + dy
                if 0 <= yy < self.h and 0 <= xx < self.w and self.grid[yy][xx] == WATER:
                    if (dx * dx + dy * dy) ** 0.5 <= radius + 1:
                        return True
        return False

    def has_line_of_sight(self, x0, y0, x1, y1):
        """Steps along the straight line between two world points at half-tile
        increments, returning False the moment it crosses a SOLID tile - used so
        enemies only aggro onto a player they can actually see, not through a
        rock outcrop or a dungeon wall."""
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        if dist < 1:
            return True
        steps = max(1, int(dist / (C.TILE * 0.5)))
        for i in range(1, steps):
            t = i / steps
            if self.is_solid(x0 + dx * t, y0 + dy * t):
                return False
        return True

    def bounds(self):
        return (C.TILE, C.TILE, (self.w - 1) * C.TILE, (self.h - 1) * C.TILE)

    def center_world_pos(self):
        return pygame.Vector2(self.w * C.TILE / 2, self.h * C.TILE / 2)

    def draw_backdrop(self, surf, cam):
        """Large "outside the walls" background, drawn before the tile floor so a
        room reads as sitting inside a bigger world instead of ending in hard black
        past its last tile. Flat-color gradient + drifting silhouette blobs as the
        fallback - a slow parallax offset (not a fixed loop) so it feels alive
        without needing real art yet; the visual session owns the final look."""
        sw, sh = surf.get_size()
        surf.fill((15, 17, 27))
        steps = 24
        top, bottom = (22, 26, 42), (12, 13, 20)
        for i in range(steps):
            t = i / (steps - 1)
            color = tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3))
            band_h = sh // steps + 1
            pygame.draw.rect(surf, color, (0, sh * i // steps, sw, band_h))
        parallax = (cam.pos.x * 0.04) % (sw * 1.2)
        for i in range(-1, 3):
            bx = int(i * sw * 0.6 - parallax)
            pygame.draw.circle(surf, (28, 32, 50), (bx + sw // 4, int(sh * 0.78)), int(sh * 0.42))
            pygame.draw.circle(surf, (21, 24, 39), (bx + sw * 3 // 4, int(sh * 0.85)), int(sh * 0.32))

    def draw(self, surf, cam, screen_size, fog=None):
        """fog: None means fully visible (Nexus/Bazaar/open Realm, as always).
        Otherwise a set of (tx, ty) explored-tile coordinates - any tile NOT
        in it is drawn as unrevealed fog instead of its real contents. Used to
        gate dungeon rooms behind actual exploration (see MinimapState.explored,
        which this reuses directly rather than tracking a second copy)."""
        from game import sprites  # local import - only needed for the tall-prop
        # overlay pass below; kept local rather than a new module-level import
        sw, sh = screen_size
        top_left = cam.inverse((0, 0))
        x0 = max(0, int(top_left.x // C.TILE) - 1)
        y0 = max(0, int(top_left.y // C.TILE) - 1)
        x1 = min(self.w, x0 + sw // C.TILE + 3)
        y1 = min(self.h, y0 + sh // C.TILE + 3)
        t_ms = pygame.time.get_ticks()
        water_idx = int(t_ms / 260)
        # (screen_y, tile_id, screen_x) for every tall totem/pole/pillar tile seen
        # this pass - drawn AFTER the full tile-floor sweep below, sorted by
        # screen_y, so each one's sprite (taller than one tile, bottom-anchored)
        # extends upward past its own tile's top edge without needing full
        # entity-vs-prop Y-sorting (see TALL_PROP_TILE's own module comment for
        # the honest scope note on what this does/doesn't handle).
        tall_prop_draws = []
        for ty in range(y0, y1):
            for tx in range(x0, x1):
                px, py = cam((tx * C.TILE, ty * C.TILE))
                if fog is not None and (tx, ty) not in fog:
                    pygame.draw.rect(surf, (5, 5, 8), (px, py, C.TILE, C.TILE))
                    continue
                t = self.grid[ty][tx]
                color = TILE_COLORS[t]
                if t == WATER:
                    surf.blit(_WATER_FRAMES[(water_idx + tx + ty) % len(_WATER_FRAMES)], (px, py))
                elif t == NEXUS_FOUNTAIN:
                    surf.blit(_FOUNTAIN_TEX[(water_idx + tx + ty) % len(_FOUNTAIN_TEX)], (px, py))
                elif t == CHEST and _CHEST_SPRITE is not None:
                    # floor showing under/around the chest, same as a plain floor tile,
                    # plus a faint pulse ring (still reads as "interactive") under the art
                    pygame.draw.rect(surf, TILE_COLORS[NEXUS_FLOOR], (px, py, C.TILE, C.TILE))
                    ring_r = int(C.TILE * 0.32 + 4 * math.sin(t_ms / 240.0))
                    pygame.draw.circle(surf, _tint(color, 60), (px + C.TILE // 2, py + C.TILE // 2), ring_r, 2)
                    cw, ch = _CHEST_SPRITE.get_size()
                    surf.blit(_CHEST_SPRITE, (px + C.TILE // 2 - cw // 2, py + C.TILE - ch + 4))
                elif t in (VAULT_TILE, BAZAAR_PORTAL):
                    # Same "dungeon door" archway look every entities.Portal now
                    # uses (see entities.Portal._draw_archway) - neither of these
                    # is a Portal object (they're plain tile-grid cells), so this
                    # is a standalone equivalent drawn as a tile overlay instead
                    # of the generic pulsing-rect INTERACTIVE treatment below.
                    pygame.draw.rect(surf, TILE_COLORS[NEXUS_FLOOR], (px, py, C.TILE, C.TILE))
                    _draw_archway_tile(surf, px + C.TILE // 2, py + C.TILE // 2, color, t_ms)
                elif t in INTERACTIVE:
                    pulse = 1.0 + 0.18 * math.sin(t_ms / 300.0)
                    pygame.draw.rect(surf, tuple(min(255, int(c * pulse)) for c in color), (px, py, C.TILE, C.TILE))
                    ring_r = int(C.TILE * 0.32 + 4 * math.sin(t_ms / 240.0))
                    pygame.draw.circle(surf, _tint(color, 60), (px + C.TILE // 2, py + C.TILE // 2), ring_r, 2)
                elif t in TALL_PROP_TILE_IDS:
                    # draw the underlying biome ground tile first (same texture-or-
                    # flat-color logic as the generic else-branch below, just keyed
                    # on the prop's BASE ground id, not its own tile id) - unlike
                    # BIOME_PROP_TILE/DUNGEON_PROP_TILE, a tall prop's own sprite has
                    # a real transparent background and does NOT replace the floor.
                    # The sprite itself is deferred to the y-sorted pass after this
                    # whole loop so it can extend upward past this tile's top edge.
                    base_id = TALL_PROP_BASE_GROUND[t]
                    base_variants = _TEX_BY_TILE.get(base_id)
                    if base_variants:
                        surf.blit(base_variants[_tile_hash(tx, ty) % len(base_variants)], (px, py))
                    else:
                        pygame.draw.rect(surf, TILE_COLORS[base_id], (px, py, C.TILE, C.TILE))
                    tall_prop_draws.append((py, t, px))
                else:
                    variants = _TEX_BY_TILE.get(t)
                    if variants:
                        surf.blit(variants[_tile_hash(tx, ty) % len(variants)], (px, py))
                    else:
                        pygame.draw.rect(surf, color, (px, py, C.TILE, C.TILE))
                if t in SOLID or t in CLIFF_EDGE_TILE_IDS:
                    # ground shadow: a soft dark crescent tinted over the tile's own
                    # ALREADY-drawn bottom third - reads the same as a shadow cast at
                    # the wall's base, a near-free "this has real height" cue this
                    # codebase didn't have anywhere before (a literal draw-order
                    # reorder to paint a shadow fully underneath the texture would be
                    # a much bigger diff here for the same visible result).
                    shadow_h = C.TILE // 3
                    shadow = pygame.Surface((C.TILE, shadow_h), pygame.SRCALPHA)
                    pygame.draw.ellipse(shadow, (0, 0, 0, 70), (0, 0, C.TILE, shadow_h * 2))
                    surf.blit(shadow, (px, py + C.TILE - shadow_h))
                    # only outline the SIDE facing open ground, not every edge of every
                    # solid tile - reads as "the wall cluster has a visible silhouette"
                    # instead of a distracting grid over solid rock, per the user's
                    # "walls should have an outline so I can see them" request.
                    is_building_wall = t in BUILDING_WALL_TILE_IDS
                    # a warmer, brighter gold outline for a constructed wall (vs. the
                    # cooler pale outline every other solid/cliff tile keeps) so a
                    # building reads as "built" at a glance even next to natural rock
                    # of a similar base texture - see the note above BUILDING_WALL_TILE_IDS.
                    edge_col = (230, 190, 90) if is_building_wall else (235, 225, 195)
                    if not (ty > 0 and self.grid[ty - 1][tx] in SOLID):
                        pygame.draw.line(surf, edge_col, (px, py), (px + C.TILE, py), 2)
                    south_open = not (ty < self.h - 1 and self.grid[ty + 1][tx] in SOLID)
                    if south_open:
                        pygame.draw.line(surf, edge_col, (px, py + C.TILE), (px + C.TILE, py + C.TILE), 2)
                        # two-tone wall face: south is the side facing the viewer/open
                        # ground in this top-down view - darken its bottom ~30% into a
                        # real "front face in shadow" band, not just a thin line.
                        # Building walls get a visibly stronger/warmer band than plain
                        # natural rock so they read with more weight, not just a
                        # thin-line difference that's easy to miss while moving.
                        band_h = int(C.TILE * 0.3)
                        band = pygame.Surface((C.TILE, band_h), pygame.SRCALPHA)
                        band.fill((40, 25, 0, 100) if is_building_wall else (0, 0, 0, 60))
                        surf.blit(band, (px, py + C.TILE - band_h))
                    if not (tx > 0 and self.grid[ty][tx - 1] in SOLID):
                        pygame.draw.line(surf, edge_col, (px, py), (px, py + C.TILE), 2)
                    if not (tx < self.w - 1 and self.grid[ty][tx + 1] in SOLID):
                        pygame.draw.line(surf, edge_col, (px + C.TILE, py), (px + C.TILE, py + C.TILE), 2)

        tall_prop_draws.sort(key=lambda item: item[0])
        for py, tile_id, px in tall_prop_draws:
            kind = TALL_PROP_KIND_BY_ID.get(tile_id)
            if kind is None:
                continue
            sprite = sprites.tall_prop_sprite(kind)
            if sprite is None:
                continue
            sx = px + (C.TILE - sprite.get_width()) // 2
            sy = py + C.TILE - sprite.get_height()
            surf.blit(sprite, (sx, sy))


class Camera:
    def __init__(self, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.pos = pygame.Vector2(0, 0)
        # RotMG has a real Q/E-rotate-the-view feature (confirmed on the wiki's
        # Controls page) - angle is in degrees. __call__ stays pure translation
        # (it's used to draw onto the PRE-rotation world buffer in
        # render_rotated_world(); the buffer image itself gets rotated once,
        # which is what actually turns the tiles/sprites, not per-point math).
        # inverse() DOES need to account for it, since it maps a point on the
        # final (rotated) screen back to world space, e.g. for mouse aiming.
        self.angle = 0.0

    def follow(self, target_pos):
        self.pos = pygame.Vector2(target_pos)

    def rotate(self, delta_deg):
        self.angle = (self.angle + delta_deg) % 360

    def reset_rotation(self):
        self.angle = 0.0

    def __call__(self, world_pos):
        # rotation-aware: this is what makes an entity (player/enemy/bullet) drawn
        # with its normal upright sprite still land in the correct spot on a
        # rotated view - like RotMG itself, the MAP turns, characters don't tilt.
        # A no-op when self.angle == 0, which is always true for the throwaway
        # buffer camera render_rotated_world() uses to pre-render the tile floor
        # (that image gets rotated as a whole afterward, not per-tile), so this
        # same method stays correct for both call sites.
        rel = pygame.Vector2(world_pos[0] - self.pos.x, world_pos[1] - self.pos.y)
        if self.angle:
            rel = rel.rotate(-self.angle)
        return (int(rel.x + self.screen_w / 2), int(rel.y + self.screen_h / 2))

    def inverse(self, screen_pos):
        rel = pygame.Vector2(screen_pos[0] - self.screen_w / 2, screen_pos[1] - self.screen_h / 2)
        if self.angle:
            rel = rel.rotate(self.angle)
        return self.pos + rel


_rotation_buffer = None  # cached (surface, camera) reused across frames - avoids
_rotation_buffer_cam = None  # reallocating a ~1500x1500 surface every rotated frame
ROTATE_RENDER_SCALE = 0.5  # rotate a half-resolution copy of the buffer, then scale the
# rotated result back up - see render_rotated_world()'s comment for the measured cost


def render_rotated_world(dest_surf, cam, draw_fn, bg_color=(18, 18, 22)):
    """
    Draws the world at zero rotation onto an oversized offscreen buffer via
    draw_fn(buffer_surf, buffer_cam) - every existing entity.draw(surf, cam)
    call works completely unchanged - then rotates the WHOLE composed image
    by the camera's angle and blits the centred, screen-sized crop onto
    dest_surf. This is what makes the tile floor (not just sprite positions)
    actually turn with the camera instead of showing gaps/seams.
    Skips the buffer entirely (draws straight to dest_surf) when angle == 0,
    so the common case has zero extra cost.
    """
    global _rotation_buffer, _rotation_buffer_cam
    if not cam.angle:
        draw_fn(dest_surf, cam)
        return
    # The buffer only needs to be as big as the destination's own DIAGONAL to
    # guarantee no empty corners after an arbitrary rotate-then-center-crop -
    # that's the true worst case (a diagonal-sized source still fully covers
    # a WxH crop after any rotation angle). The previous flat 1.5x-of-the-longer-
    # side was noticeably bigger than that bound (e.g. ~2049px vs. a ~1594px
    # diagonal at 1366x820), so every rotated frame was both drawing the tile
    # floor over ~65% more area AND running pygame.transform.rotate() (a real
    # per-pixel cost, not free) on that much more surface than necessary.
    size = int(math.hypot(dest_surf.get_width(), dest_surf.get_height()) * 1.05)
    if _rotation_buffer is None or _rotation_buffer.get_width() != size:
        _rotation_buffer = pygame.Surface((size, size))
        _rotation_buffer_cam = Camera(size, size)
    buf = _rotation_buffer
    buf.fill(bg_color)
    buffer_cam = _rotation_buffer_cam
    buffer_cam.follow(cam.pos)
    draw_fn(buf, buffer_cam)
    # pygame.transform.rotate() is the REAL cost here (measured ~19ms/frame on a
    # ~1670px buffer alone - far more than drawing the tiles into it, ~4.6ms) -
    # this was the actual cause of "rotating the camera lags hard." Rotating a
    # much smaller version of the same image and scaling the result back up is
    # dramatically cheaper (rotate cost scales with area) and, since this is a
    # tile floor rather than fine text, the softened edges from the round-trip
    # scale aren't visually noticeable - measured ~11ms/frame total (draw + both
    # scales + rotate) at ROTATE_RENDER_SCALE=0.5 vs. ~24ms/frame unscaled.
    small_size = max(1, int(size * ROTATE_RENDER_SCALE))
    small = pygame.transform.scale(buf, (small_size, small_size))
    rotated = pygame.transform.rotate(small, cam.angle)
    rw, rh = rotated.get_size()
    rotated = pygame.transform.scale(rotated, (int(rw / ROTATE_RENDER_SCALE), int(rh / ROTATE_RENDER_SCALE)))
    rw, rh = rotated.get_size()
    dest_surf.blit(rotated, (dest_surf.get_width() // 2 - rw // 2, dest_surf.get_height() // 2 - rh // 2))
