# Batch 14: Island Identity & Mini-Bosses, Curated Vignettes, GUI Dock, Music, Echo Economy, Bazaar Chests, Portal Doors

## Context

Commit `92c3086`. This batch came after Batches 12-13 (doc 24). It was a mix of content ("make the islands feel like
places"), bug fixes found by diagnosis (terrain diamonds, building walls blending into rock), and
UX polish (a RotMG-style right-hand dock). The terrain part was later replaced completely in the
v0.2-final round, so see doc 27 for the current generator. The rest below is still current.

## 1. Island identity ("The Reforging" islands)

10 islands sit in a ring off the coast. Each one has a name, a theme, a mini-boss, 10 curated props and a
return portal. Data is in `game/realm_sim.py` and `game/world.py`.

| idx | Name | Theme | Mini-boss kind | HP | Pattern | Dmg (post-mult) | deF |
|---|---|---|---|---|---|---|---|
| 0 | Emberball Shard | island_shard | cinder_colossus | 600 | spread | 10-20 | 4 |
| 1 | Coral Colada Choir | island_choir | choir_sovereign | 590 | volley | 9-18 | 4 |
| 2 | Frostquiri Shard | island_shard | rubble_warlord | 560 | charge | 9-18 | 3 |
| 3 | Pearlini Spire | island_choir | coral_leviathan | 610 | burst | 10-20 | 4 |
| 4 | Bonshine Shard | island_shard | ashreach_revenant | 580 | spiral | 9-18 | 3 |
| 5 | Tidricane Sanctum | island_choir | tideglass_warden | 580 | spiral | 10-20 | 3 |
| 6 | Thorn-on-the-Rocks Shard | island_shard | thornrock_colossus | 620 | burst | 11-21 | 4 |
| 7 | Driftai Cloister | island_choir | driftbell_matriarch | 560 | volley | 9-18 | 3 |
| 8 | Ashioned Shard | island_shard | ashenreach_devourer | 600 | charge | 10-20 | 4 |
| 9 | Abyssal Rumnal | island_choir | abyssal_choirmaster | 640 | spread | 10-20 | 4 |

- **Theme by index:** even indices are `island_shard` (anchor `cinder_warden`, verb "flaring"), odd are `island_choir`
  (anchor `choir_warden`, verb "singing").
- **Rank:** all mini-bosses are rank `boss`, with `aggro_range` and `leash_range` = 99999 (they never leash).
- **Event loop (`_tick_island_events`):** each island re-arms on its own `ISLAND_QUEST_INTERVAL` = 300 s timer.
  - When armed, it spawns the mini-boss plus `ISLAND_ESCORT_SIZE` = 2 escorts from the theme's guardian pool, and
    announces "`<name>` is `<verb>`! `<Boss>` has awoken!".
  - Killing the whole wave drops an elite loot bag, grants the `reforger` achievement to the killer, announces
    "`<name>` has been calmed. The Reforging continues.", and re-arms the 300 s cooldown.
- **Island index fix (v0.2-final):** `idx` is the NAME index, not `len(self.islands)`. A skipped placement must not
  shift every later island's name and boss.
- **Curated props:** exactly 10 per island, taken from `world.ISLAND_PROP_KINDS[theme]`.
  - `island_shard`: cracked_pillar, ember_vent, floating_shard_chunk, rune_scorch, fury_crystal, broken_statue,
    ash_drift, shard_brazier, rubble_pile, scorched_banner.
  - `island_choir`: coral_cluster, pearl_shell, drowned_altar, kelp_strand, barnacle_rock, tide_pool, sunken_bell,
    driftwood_arch, anemone_bloom, choir_lantern.
  - Each (theme, kind) pair gets its own tile id, so the floor under it is the island's ground. The centre landmark is
    a tall prop: `totem` for shard islands, `pillar` for choir islands (`ISLAND_LANDMARK_KIND`).
  - **Placement (current, doc 27):** two rings around the landmark.
- **Fast travel:** island_link portals in the beach "hub ring" teleport you on the same map to each island
  (`kind="island_link"`, `target_pos`). Each island also has a RETURN island_link portal at its own position that
  leads back to its hub slot. Consumers branch only on `kind` + `target_pos`.

## 2. Curated biome vignettes

- **Count:** 20 per biome (`VIGNETTES_PER_BIOME`), up to 60 placement attempts each.
- **Templates:** each is a small hand-authored scene from `world.BIOME_VIGNETTE_TEMPLATES[biome]`, stamped with
  `BIOME_VIGNETTE_RADIUS` = 2 (5x5 footprint).
- **Placement rules (current, doc 27):**
  - only in clearings, on plain ground of the vignette's own biome;
  - at least `VIGNETTE_SPACING` = 16 tiles apart, enforced with a bucket grid of 16-tile cells;
  - anchors come from a pre-scanned candidate list, so small biomes still reach 20.
- **Overlap:** vignettes share the `placed_rects` overlap list with buildings, terraces and landmarks.

## 3. Building-wall visual fix

`BUILDING_WALL_TILE` was always solid and shaded, but it blended into natural rock tiles. Constructed walls now draw
a warmer, brighter **gold outline** on their exposed edges (`world.py`, in the wall-shading pass). Unity: use a
separate wall material with an edge highlight or outline shader, and never the rock material.

## 4. Minimap bounds

Entity dots (portals, enemies, peers) are clamped into the minimap square, in both the corner map and the full map. They can no longer draw outside the frame.
Unity: clamp marker UV to [0,1] before placing it, or mask the minimap with a RectMask2D.

## 5. Right-dock GUI and the Tab switcher

This is a RotMG-style dock on the right edge. The v0.2-final round later wrapped it all in one frame (doc 27).
Top to bottom:
1. **Day/night clock:** 200x58, right-aligned to the minimap. A sun on the left and a moon on the right, with a marker at
   `x = (1 - light_level)`. The label reads Day, Night (light < 0.35) or Blood Moon, and the frame turns red during a blood moon.
2. **Corner minimap:** `CORNER_SIZE` = 148 px, at y = 74, with +/- zoom buttons (1.0-8.0x, 0.5 steps) and an
   "M: full map" hint.
3. **Player panel:** 260x170. Shows class, level and title, HP/MP/XP bars, the 6 stats and the pet name.
4. **Tab strip:** 22 px, with "Inventory | Pet [Tab]". Tab toggles the slot below.
5. **Switched slot:** either the inventory (4 equip slots in one row, then a 4-wide backpack grid) or the pet panel.
   Only one draws per frame.

- **Layout rules:**
  - `DOCK_PAD` = 14 from the right edge.
  - Every HUD element stays at least `SCREEN_EDGE_MARGIN` = 4 px from every screen edge; a test enforces this.
- **Pet feed target:** while dragging an item in inventory mode, the "Pet" tab becomes the "Feed pet" drop target.
  This was fixed in v0.2-final; the old target covered the equip bar.

## 6. Music: Vault theme, ~20 s arrangements, per-dungeon tracks

All music is procedural and original (`game/audio.py`), never covers.
- **Zone themes** (`_THEME_BUILDERS`): nexus, bazaar, realm, dungeon, and the new **vault**.
- **Arrangements:** each theme was extended to about 20 s so the loop repeats less often.
- **Per-dungeon tracks** (`_DUNGEON_VARIANT_BUILDERS`): cave, frozen_crypt, jungle_ruins, ember_den, sunken_grotto,
  wind_spire. The zone key is `dungeon_<theme>`, and `generic` or unknown themes fall back to "dungeon".
  - The co-op client only receives the dungeon's label, so it maps it back to a key with `dungeon_zone_for_label`.
- `play_theme(zone)` is safe to call every frame; it restarts only when the zone changes.
- Volumes go through the options menu (doc 26).

## 7. Echo currency: passive accrual plus a death bonus

- **Passive:** `ECHO_XP_PER_ECHO` = 1000. The player keeps `_echo_xp_progress`, which counts all XP earned this life
  and never resets. Every 1000 XP immediately banks 1 echo to the account (`accounts.add_echoes`) and increments
  `_echoes_this_life`. This happens in `RealmSim._reward`.
- **Death bonus:** `accounts.award_echoes_for_death(name, echoes_this_life)` adds `2 * echoes_this_life` on
  permadeath. The old flat `max(1, level // 2)` is gone.
- **Persistence:** both counters are saved in the character file (`echo_xp_progress`, `echoes_this_life`).
- **Spending:** the Echo Keeper shop in the Nexus (Nexus prop `ECHO_KEEPER_TILE`) sells account unlocks such as
  backpack slots and a starting-XP boost. It is single-player only.

## 8. Bazaar chests

- `entities.BazaarChest(Bag)` is a permanent shared container. It never expires and is never culled when empty.
- There are 4 of them, at Bazaar tiles (5,9), (27,9), (5,13) and (27,13) (`BAZAAR_CHEST_TILE_POSITIONS`), created once by
  `spawn_bazaar_chests()` on the authority (single-player game or server). Clients mirror them.
- **Interaction:** through the existing floating ground-bag window, not the Vault's full-screen modal.
  - Withdraw is the normal bag withdraw.
  - Deposit is the `chest_deposit` action (`deposit_to_bag`), which the server accepts only for a BazaarChest.
  - Co-op ghost: `GhostChest` carries `bag_color` (brown) and a name such as "Gold chest".

## 9. Unified "dungeon door" portal visuals

- **The door:** every portal kind (realm_exit, dungeon_shard, island_link, bonus, ...) plus the Vault and Bazaar entrance
  tiles draw the same stone archway. It uses a neutral grey frame shared by every kind, with a kind-coloured swirl inside
  (`Portal.KIND_COLORS`).
- **Co-op:** the client's `GhostPortal` subclasses `Portal` to reuse this drawing (doc 27 has the crash fix).
- **Unity:** use one door prefab with a tinted swirl material per kind.
