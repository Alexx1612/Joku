# Batch 15: Living World (NPCs, Dialogue, Side Quests, Journal, Fixes & UI, Big World)

## Context

Batch 15 was planned in `~/.claude/plans/i-want-to-do-distributed-leaf.md` (user request, 2026-09-25).
It is uncommitted at the time of writing, on top of the doc-27 round. Decisions the user made:
- the map grows to ~1300x1300;
- co-op uses personal loot with shared credit;
- damage spells get x2.5;
- build order: dialogue and quests, then fixes and UI, then the world.

All numbers below were read from the current code.

## 1. NPCs and friendly creatures (game/npcs.py)

- `NPCS` holds 15 entries: 11 people and 4 talkable creature groups. Each has `name` and `area`, where the area is an area key.
  - **People:** Barkeep Bitterwick (`nexus:tavern`), Old Mossbeard (`area:tavern_town`), Sandy Sal (`area:oasis_bazaar`),
    Frostine the Ice Fisher (`area:frozen_lake_camp`), Captain Driftwood (`spawn` beach), Madame Murk (`area:witchs_hollow`),
    Brother Tipsy (`area:mountain_monastery`), Cinder Pete (`area:forge_camp`), Professor Fernleaf (`area:botanists_glade`),
    Rusty the Scrap Golem (`area:scrapyard`), Glimmer the Cartographer (`area:crystal_caverns`).
  - **Creature groups:** Grand Elk Herd (`area:elk_meadow`), Gossiping Flamingos (`vignette:swamp`),
    Philosopher Tortoise (`area:oasis_bazaar`), Mushroom Folk (`area:crystal_caverns`).
  - `FALLBACK_LANDMARK`: if a big area doesn't fit on a seed, that NPC falls back to its biome landmark.
- **Talking:** `TALK_RADIUS` = 72 world units, then press F. NPCs can't be damaged: they aren't in the enemy list, and bullets,
  abilities and pets never target them.
- **Wildlife talk:** `WILDLIFE_TALK` lets 16 neutral kinds speak in "animal speak". That's the 6 original kinds (deer,
  forest_hare, songbird, desert_lizard, marsh_heron, cave_moth) plus 10 new ambient kinds, one per biome: elk, mountain_goat,
  snow_fox, scrap_rat, tortoise, tree_frog, fire_beetle, flamingo, ice_penguin and mushroom_folk.
  `WILDLIFE_DEFAULT` gives a finite 3-line fallback.
- **Sprites:** new grids in `sprites.py`, recolored from existing art (all original).

## 2. Dialogue (game/dialogue.py, ui.draw_dialogue)

- **Tree:** a tree is made of nodes `{text, options:[{label, next | action}]}`, driven by a `Conversation`.
  - `MAX_OPTIONS` = 5 answers per node. The last option is always `BYE` ("Bye."), and sub-topics also get `BACK`.
  - Each chat topic can be heard once. After that it collapses and is hidden, so a conversation always ends.
  - Actions: give quest, turn in quest, end.
- **GUI:**
  - A bottom-centre panel with a portrait, the NPC's line and numbered option buttons.
  - Choose with a click or the 1-5 keys. Esc means Bye.
  - While it's open it blocks movement and firing.
- **Co-op:** the server is authoritative. The client sends `dialogue_choice` / `dialogue_close`, and the server applies quest
  grants and turn-ins and returns the next node.

## 3. Side quests (game/sidequests.py)

- **Structure:** `QUESTS` holds 30 quests.
  - 15 have `giver=None` and form the random board pool (`BOARD_POOL`). `BOARD_SIZE` = 3 are offered at a time.
  - 15 are given by NPCs: driftwood x2, tortoise, mossbeard, sal, frostine, murk, tipsy, pete, fernleaf, rusty, glimmer,
    mushroom_folk, bitterwick and elk_herd.
- **Rewards:** XP 120-500, Echoes 1-3, and an `elite` or `boss` loot roll. If the backpack is full, the loot waits until
  there is room.
  - Board quests: herd_whisperer, hare_census, birdwatcher, pest_control (15), yeti_tag (3), island_hopper (5),
    chest_raider (3), dungeon_crawl (2), snack_time (5), night_watch, lizard_race, heron_haiku, miniboss_menace (2),
    guardian_groupie (2), world_boss_witness.
  - NPC quests: flamingo_gossip, tortoise_wisdom (3), mossbeard_mushrooms (6), camel_bell, ice_fishing (5), rum_run (3),
    bog_brew (8), pilgrimage (4), hot_iron (3), fern_samples (3), scrap_for_rusty (10), map_the_deep (3),
    moth_to_a_flame (6), barkeeps_tab (5), elk_escort (30).
- **Quest items** (`QUEST_ITEMS`): glowcap, camel_bell, driftwood_rum, ember_core. Delivery quests turn these in through
  the giver's dialogue.
- **Standing near a group:** you're "next to" a group within `NEAR_RADIUS` = 170 world units. RealmSim scans for this every
  `NEAR_TICK` = 0.5 s.
- **Event hooks** use the same `(kind, key)` format as the story system:
  - kill (in `RealmSim._reward`)
  - standing near a wildlife group
  - talking
  - reaching a landmark, island or vignette
  - opening an island chest
  - fishing
  - feeding a pet
  - clearing a dungeon
  - surviving a night
  - being near a world boss kill
- **Persistence:** `SideQuestProgress` is saved per character in `Player.full_state`, and old saves load fine.
  Active side quests also show in the small J log.

## 4. Journal windows (game/journal.py, game/codex.py)

Both windows are opened from new rows in the O menu. The shared window code lives in `journal.py`; the Dictionary content
comes from `codex.py`.

- **Quest Log:**
  - A scrollable modal with the story act, active side quests and completed quests.
  - Blue target names open that entry in the Dictionary.
  - A per-quest "Map" button opens the Quest Map.
  - A plain click on the J HUD log also opens it.
- **Dictionary:**
  - Nine `CATEGORIES`: Mobs, Bosses, Friendly creatures, NPCs, Portals & Dungeons, Areas, Pets & mechanics, Items & UT,
    Story. About 214 entries, built from the game's own tables.
  - A search box (`SEARCH_MAX` = 40 characters) supporting typing, Backspace and Ctrl+A/C/V.
  - Each entry shows the sprite, stats (hp, dmg, speed, rank, pattern text, deF, xp), lore, and a "where to find" mini
    realm map. Map labels are computed with `LABEL_CELL` = 12 tiles.
  - Help pages cover pets (hatching, feeding, bond, carriers, fusion, mythic), UT sockets, story checkpoints, side quests,
    co-op personal loot, Echoes, live events and trading.
- **Quest Map:**
  - A fully revealed realm showing the player dot, biome/landmark/island/NPC labels, pulsing quest markers and hover
    tooltips.
  - Mouse wheel zooms, right-drag pans.
  - Co-op receives realm area info once, together with the map.
- **Esc** steps back one window at a time. It never quits from inside these windows.

## 5. Co-op fairness and island chests

- **Contributors:** each enemy has `contributors` (pid -> damage dealt). On death, every contributor gets XP, story credit and
  side-quest credit, plus their own loot bag (`_spawn_loot_bag(..., owner_pid=pid)`).
- **Bag visibility:** each player's snapshot contains only shared bags (`owner_pid` None) and their own. The server refuses
  pickups from other players' bags. Single-player behaves as before.
- **Island chests:** one per island. Each player can open it once, and it refills when that island is calmed. It gives good
  loot plus quest items (camel_bell, driftwood_rum) while the matching quest is active. In co-op the chest contents are
  personal.

## 6. Phase 2 fixes and UI

- **Spells:** `items.ABILITY_POWER_MULT` = nova/chain/drain/freeze x2.5, heal/shield x1.5. It's applied at cast time
  (`ability_power`), so abilities in old saves are buffed too.
  - Spells and pets skip neutral, unshootable and dead enemies.
  - `vfx.ABILITY_STYLES` gives each of the 24 named abilities its own look, in 17 styles: crystal shards, dark implosion,
    void chain lightning, poison cloud, spreading rot, scythe arc + soul stream, thunderbolts, storm bolts, gale + frost,
    escalating holy pillars, golden dome, shield bubble, horn sound-waves, smoke puff, shadow cloak.
- **Mob chat distance:** mob speech events carry x, y, and `realm_sim.audible_mob_speech` only relays lines within
  `MOB_SPEECH_HEAR_RADIUS` = 600. This applies in single-player and in each player's co-op snapshot.
- **Esc/quit:** Esc closes the topmost window: journal, dialogue, map, shop, options, bag, vault chest, trade/invite,
  context menu, inspect, friends. With nothing open it shows the quit prompt. In the prompt, Esc, Enter or Y quit and N stays.
- **Chat:**
  - **Input line** (`game/chat_input.py`, `MAX_LEN` = 1000, `HISTORY_CAP` = 50): a real cursor, Shift/mouse selection,
    Ctrl+A/C/X/V and Up/Down history.
  - **Chat log:** the top strip drags the panel. Click-drag selects lines and Ctrl+C copies them. A plain click no longer
    opens chat.
  - **Names:** right-click a name for the player menu. Trade, Teleport and Inspect are greyed out when that player isn't
    in your zone.
  - **Whispers:** `/msg "Name" text` and `/w` reach a player in any zone. The server looks the name up across all sessions.
- **Vault:** `VAULT_CHEST_COUNT` = 12 chests x `VAULT_CHEST_SIZE` 8 = `VAULT_SLOTS` 96. That's 3 rows of chests in the vault
  room, each with its own skin.
  - F or Enter next to a chest opens only that chest, as a bag-style window. The full-screen tab page is gone.
  - Old save files are padded to 96 slots and load fine.
- **HUD:**
  - The day/night clock is 272x74, with the zone name and kills in its top strip.
  - The minimap is `CORNER_W`x`CORNER_H` = 266x148.
  - Hubs show a "Safe zone" header.
  - The backpack bottom is at 786 px, within the 820 px screen.

## 7. World: map, islands, areas, big props, bosses

- **Map:** `REALM_W/H` = 1308 = `CONTINENT_SIZE` 900 + 2 x `CONTINENT_OFFSET` 204.
  - The continent is generated exactly as in doc 27, then embedded in an ocean ring.
  - `CONTINENT_R` = 447 drives lair difficulty.
  - Spawn, lair and vignette scans only cover the continent.
  - A full `RealmSim()` takes about 1.2 s (budget 3 s).
  - The co-op map JSON is about 5.5 MB, sent uncompressed. zlib would cut it to about 0.1 MB (an optional follow-up).
- **Islands:** 10 islands, each about 88-98 tiles across with an organic lobed coast (`ISLAND_RADIUS` = 52).
  - Each has a beach ring and a themed interior biome.
  - A central plaza holds the mini-boss arena, the 10 curated props and the landmark.
  - `ISLAND_CAMP_COUNT` = 4 camps per island, each with `ISLAND_CAMP_CAP` = 5 mobs at HP scale `ISLAND_CAMP_SCALE` = 1.6.
  - Each island has its chest, a walkway laid over water only, and hub/return portals.
  - Placement is always inside the map bounds, with no overlaps and at least 16 tiles of water to the mainland. The spawn
    is never on an island.
- **Big areas** (`game/areas.py` `AREA_DEFS`/`LAYOUTS`): 10 stamped places, 42x42 to 50x46 tiles.
  - The places: Tavern Town (outer ring, safe), Oasis Bazaar, Frozen Lake Camp, Witch's Hollow, Mountain Monastery,
    Forge Camp, Botanist's Glade, Scrapyard, Crystal Caverns and Elk Meadow.
  - Each has roads, huts with doorways and fences with gates. No lairs sit inside.
  - The area rects are registered for approach clearing, and the Dictionary and Quest Map know about them.
- **Nexus:** `NEXUS_W/H` = 96x72, with the fountain plaza, a tavern district (Barkeep inside), a garden park with a pond, a
  dockside with piers and boats, and an arena plaza (`areas.NEXUS_DISTRICTS`). The prop scatter is seeded, so the client and
  server build the same layout.
- **Big props** (`game/big_props.py` `KINDS`): 34 kinds drawn in code. Each is (sprite w x h, footprint, height, has_canopy).
  - Trees: oak, pine, palm, dead_big, jungle_giant, snow_pine and mushroom_tree, with sprites 76x128 to 140x150.
    crystal_spire is also listed in `TREE_KINDS`, but it has no canopy.
  - Also: 2x2 boulders, tents, stalls, wells, furnaces, a bell tower, boats and more.
  - Only a tree's trunk tile is solid, and groves hold about 550-670 per map.
  - **Canopy overlay:** a map with `tmap.canopy_overlay = True` draws only the trunks in the floor pass. The clients then call
    `tmap.draw_canopies(surf, cam, player_pos)` after entities, and a canopy the local player stands under is faded.
    This is wired in both clients, in the hubs and in the realm.
- **Boss scale** (entities.py): optional per-kind `scale` multiplies both the sprite (`sprites.enemy_sprite(kind, scale)`) and
  the hit radius.
  - Main, phase-2, world and Mad God bosses use `BOSS_SCALE` = 2.0. Island mini-bosses use `MINI_BOSS_SCALE` = 1.8. Landmark
    guardians use `GUARDIAN_SCALE` = 1.5, set per instance and sent as `scale` in `Enemy.net_state`.
  - Terrain movement uses a radius capped at `ENEMY_MOVE_RADIUS_CAP` = 26, so big bosses still fit through corridors.

## 8. Tests added

- `check_dialogue_and_sidequests.py`
- `check_quest_log_dictionary.py`
- `check_phase2_fixes.py`
- `check_big_islands.py`
- `check_areas_trees_bosses.py`

All 66 check scripts pass.
