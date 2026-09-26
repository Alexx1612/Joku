# Post-v0.2 Round: Defense Balance, Story Pacing, Crash Fixes, Dock Frame, Terrain Rewrite, Decorations, Doors, Draggable Panels

## Context

This is the round after `cafd86c`. It is uncommitted at the time of writing. It started from a "what's next" list:
1. Defense balance.
2. A story playthrough.
3. Pets in hubs.
4. Dead code.
5. The long-unreproduced drag-into-portal crash.

User requests added mid-round: frame the whole right dock, rewrite terrain generation from documented techniques,
rework the decorations, add doors to buildings, and make the quest log and chat draggable. The facts below come from the current code.

## 1. Player defense curve (game/constants.py, entities.py)

- **Old behaviour:** flat subtraction, `max(dmg - deF, dmg*0.1)`. Enemy hits never grow with level (average raw hit: trash ~4, elite ~9,
  boss ~13), so every level-20 class sat on the 10% floor and was effectively immune.
- **New, players only:** `player_defense(dmg, deF) = dmg * 75 / (75 + deF)`, rounded with a minimum of 1 (a 0-damage hit stays 0).
  Enemies keep `apply_defense` with their per-rank floors.
- **Priest fix:** Priest's per-level growth list had `deF` as a signature stat (about 49 deF at level 20 on a robe class). It
  was replaced with `spd`.
- **Result at level 20, no gear:** Wizard 83%, Archer 80%, Priest 79%, Warrior 54%, Paladin 56% of each raw hit.
- **Mad God:** armor-piercing shots skip this curve. Its base damage was retuned to (5, 10) raw (doc 26).

## 2. Story pacing (measured by a scripted bot playthrough)

- **Constants** (`game/story.py`): `ISLANDS_NEEDED` = 7, `INNER_GUARDIANS_NEEDED` = 4, `DUNGEONS_NEEDED` = 3.
- **Shards:** inner Landmark Guardians always drop a Dungeon Shard. Before, Act III depended on the 8% elite drop.
- **Measurement:** 16 bot runs (4 classes x 4 seeds), median total 66 min (range 35-101).
  - Per act: Act I 22, Act II 13, Act III 16, Finale 4 minutes.
  - Humans should take longer.

## 3. Hub pets

Pets now follow the owner in the Nexus, Bazaar and Vault room. The hub update calls `pet.update(dt, owner, [], [])`: with no
enemies, only follow plus heal/mana run. This happens in the single-player hub update and in `server.step` for hub zones.
Before, only RealmSim ticked pets, so a pet stayed frozen off-screen in hubs.

## 4. Crash fixes found by fuzzing (tests/check_drag_fuzz_regressions.py)

1. **Firing with no weapon.** Dragging the equipped weapon onto the ground, then shooting, raised an `AttributeError` in
   `player_fire`. This was the real cause of the reported drag-into-portal crash, and in co-op it killed the server tick.
   Firing is now skipped while `weapon is None` (single-player `_handle_firing`, server `_maybe_fire`).
2. **`GhostPortal`** now subclasses `Portal`. It had borrowed only `draw`, which needs the class colours and helpers.
3. **`GhostBag`** has its own count-based `draw`.
4. **`GhostChest`** gets a `bag_color` and a name.

The fuzz harness sends random mouse and keyboard input plus forced zone changes mid-drag, headless, with fixed seeds.

## 5. Right-dock frame and HUD layout (game/ui.py)

- **`draw_dock_frame`:** one ornate bordered backdrop, `dock_frame_rect(player)`, behind the whole right dock:
  clock/header, zone info, minimap, player panel, tabs and inventory/pet.
  - **Size:** left = panel x0 - 6 - 8, top = 4, right = screen width - 4, bottom = the lowest backpack or pet-panel rect + 8.
  - **Draw order:** in the Realm it's drawn after the night overlay and weather, so it's never darkened or rained on.
- **Zone info column** (`zone_info_rect`): the space left of the minimap holds the zone name (wrapped, font M or S),
  a divider, the kill counter and "BOSS ACTIVE". These used to overlap the clock.
- **Clock:** moved to y = 10, height 58.
- **Dungeons:** there's no clock; `draw_dungeon_header` shows "Dungeon" and "R or portal: leave" in that slot.
- **Dungeon quest panel:** its width grows to fit the longest row, and it docks left of the frame beside the player panel.
  The story log uses the same slot outside dungeons.

## 6. Terrain generator rewrite (game/world.py `make_realm`)

**Root cause of the old "diamonds":**
- Each biome's affinity field was a few very long plane waves, nearly linear across one region. The argmax of
  near-linear fields gives convex polygons.
- The domain warp was weak and fixed, the tier split was a circle, and the coastline was a 4-harmonic star.

**Pipeline** (pure Python, fields on a coarse grid of `COARSE` = 6 tiles per sample, bilinear upsample):
1. **Noise:** value-noise fBm (hashed random lattice, smoothstep interpolation, frequency x2 and amplitude x0.5 per octave).
   **Each octave's lattice is rotated by its own random angle** about the map centre, which removes the square-lattice
   look of value noise. Source: Red Blob Games, "Making maps with noise".
2. **Two-level domain warp** (Inigo Quilez, "Domain warping"): warp1 has 3 octaves at freq 1/38 and strength 9 cells
   (~55 tiles); warp2 has 3 octaves at 1/30, sampled at the warped point, strength 14 cells (~85 tiles).
3. **Elevation:**
   - `n = (elev_fbm - 0.5)*1.7 + 0.5`, from 5 octaves at 1/34.
   - `e = 0.6*n + 0.4*(1 - d^2) - 0.10`, where d is the warped distance from centre divided by the max radius; beyond
     d = 0.93, `e -= (d - 0.93)*6` (always ocean at the rim).
   - **Sea level** is the elevation quantile giving `LAND_FRACTION` = 0.47 land, picked per seed.
4. **Tier field:** `tier = e + 0.45*(1 - d)`. The top `INNER_TIER_SHARE` = 40% of land by tier becomes inner-tier
   (Godlands-style) biomes, so the tier boundary is a noise contour that stays central. Lair difficulty stays radial.
5. **Biomes:** a Whittaker-style temperature x moisture table with **quantile thresholds**, so all 10 always appear with
   controlled area. Temperature is 3 octaves at 1/46; moisture is 4 octaves at 1/26, plus a bonus near fresh water.
   - **Outer tier:** tundra = the coldest 24%; the rest splits by moisture into desert (driest 33%), forest, and swamp (wettest 30%).
   - **Inner tier:** cave = the top 16% of tier (the peaks); of the rest, ice = the coldest 17%. The rest splits at median
     temperature, then within each half at median moisture: hot and dry = ashlands, hot and wet = jungle, cool and dry =
     wasteland, cool and wet = highlands.
6. **Rivers and lakes:**
   - **Flow:** priority-flood depression filling from the map border (heapq; Barnes et al. 2014, arXiv:1511.04463)
     gives each cell a downhill parent. Flow accumulates in reverse pop order, weighted by rain (0.5 + moisture).
   - **Rivers:** cells with at least `RIVER_FLOW_CELLS` = 240 become river and are rasterised as meandering WATER, with width growing with flow.
   - **Lakes:** filled depressions deeper than `LAKE_DEPTH` = 0.05 become lakes. Water is walkable at 0.8x speed, so no land is cut off.
   - Source: Amit Patel's polygon map generation and Red Blob's mapgen4.
7. **Side info:** `LAST_REALM_INFO` = {coast: a `COAST_BINS` = 720 per-angle max land radius table, ocean: a bytearray of
   ocean-connected water, coarse fields}. RealmSim keeps its own `realm_info`.
   - `coastline_radius(angle, info)` interpolates the table, and `is_ocean(info, tx, ty)` reads the mask.
   - **Beach spawn:** accepts only water next to the ocean.
   - **Island walkways:** walk inward from the open sea, never across land.
8. **Ground patches:** only non-biome tiles (DIRT, GRASS2, ROCK), so a patch never changes a biome lookup.

**Performance:** make_realm about 0.55-0.6 s at 900x900; a full RealmSim about 1.2 s including decoration.

## 7. Decoration rework (game/world.py `_decorate_realm`, game/prop_art.py)

- **Art-loading bug:** PNG art was loaded at import time, before the game window existed, so it silently fell back to
  flat colours. Almost none of the hand-painted tiles or props had ever shown in the real game.
  - PNGs now load without a window and are converted on the first map draw. Map drawing got about 4.6x faster.
- **`game/prop_art.py`:** original code-drawn sprites for the 25 prop kinds that had no PNG. A painted PNG with the same
  name wins.
- **Groves and clearings:** a low-frequency density noise marks each biome's `cover` share as groves.
  - Inside groves, props keep a per-biome minimum spacing `r` (Bridson Poisson-disk), tighter at the core.
  - Big props (trees, boulders) fill cores, small ones (flowers, pebbles) sit at the edges, and a light scatter covers clearings.
  - Similar kinds clump together.
- **Per-biome parameters:**

| biome | r | cover | rock | patch | clear |
|---|---|---|---|---|---|
| forest | 1.7 | 0.46 | 0 | 0.035 | 0.30 |
| jungle | 1.5 | 0.56 | 0 | 0.03 | 0.30 |
| swamp | 2.1 | 0.42 | 0 | 0.02 | 0.25 (pools 0.05) |
| tundra | 3.3 | 0.32 | 0.012 | 0.02 | 0.12 |
| desert | 4.6 | 0.26 | 0.018 | 0.02 | 0.10 |
| highlands | 3.0 | 0.36 | 0.03 | 0.025 | 0.16 |
| ashlands | 3.5 | 0.32 | 0.018 | 0.025 | 0.14 |
| wasteland | 3.8 | 0.30 | 0.018 | 0.03 | 0.14 |
| ice | 4.2 | 0.26 | 0.022 | 0.015 | 0.10 |
| cave | 2.7 | 0.38 | 0.028 | 0.02 | 0.16 |

- **Grove kinds** (`GROVE_KINDS[biome]` = (core weights, edge weights)): for example, forest cores are tree 7, bush 4,
  berry_bush 3, stump 1, fallen_log 1; forest edges are flowers, wildflower_patch, grasstuft and so on. Water-loving kinds
  (reed_cluster, puddle, moss_patch, water_stain) prefer wet spots.
- **Rock outcrops:** noise-shaped solid ROCK blobs with a rim of rock, pebbles, boulders or gravel, kept away from water and the coast.
- **Vignettes and islands:** vignettes go in clearings (doc 25), and island props form two rings around the landmark.
- **Clearance pass:** after all structures are placed, solid rock near buildings, terraces, landmarks, lairs, walkway
  landings and the arrival plaza turns into DIRT. A test checks that every landmark, island and lair is reachable on foot.
- **Baked squares:** 214 of 220 biome prop PNGs had their baked background square flood-filled to transparent. Props are
  drawn over their biome's own ground tile.
- **Forest ground:** the four tile variants now share one base green (they used to make a checkerboard).
- **Totals:** about 9.7k props and 2.3-2.6k solid rock tiles per map. Groves are about 7x denser than clearings.

## 8. Building doors (world.stamp_lair_building)

Every landmark building gets a 3-tile doorway in the wall facing the map centre, with 2 tiles of floor forced open
outside it. All 200 lairs are reachable from spawn.

## 9. Draggable quest log and chat (game/panel_drag.py)

- **Dragging:** press on the panel and move more than 5 px to drag it. A plain click on chat still opens chat.
- **Storage:** positions are clamped on-screen and saved as `settings.panel_offsets` (single-player and co-op), applied through `ui.PANEL_OFFSETS`.
- **Dungeons:** the dungeon quest panel shares the quest log's offset.

## 10. Live events, co-op Echo shop, socket highlight

- **Live events (`game/live_events.py`):** now rotate on a fixed real-time schedule, `EVENT_WINDOW` = 25 min per slot.
  - The schedule is [none, double_loot, none, happy_hour, none, blood_moon_week, none, two_for_one].
  - Events: double_loot (loot x2), blood_moon_week (blood moon chance x2.5), happy_hour (XP x1.5), two_for_one (loot x2, XP x1.25).
  - `RR_EVENT` forces one event and `RR_EVENT_ROTATION=off` disables the schedule. The server sends the active event in
    snapshots; clients don't compute it.
- **Co-op Echo shop:** server-authoritative purchase action spends the account's Echoes (game/accounts.py) and applies
  the unlock to the session player; both modes build the shop rows from one shared accounts helper. The shop only
  re-opens after stepping off and back onto the Echo Keeper tile (Enter on Close no longer opens chat).
- **Socket highlight:** while a UT proc socket is pending (ENTER to confirm), the source item and target weapon get
  violet slot frames in the backpack (draw_inventory `highlighted=`). The quest log is hidden while the Echo shop or
  options menu is open.
