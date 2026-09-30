# 34 - The big islands and the Mad God's Room

"V0.2 final final" session.

## 1. Big islands (in place, not instanced)
The islands are made bigger where they already are, rather than moved into instances. This keeps the island waves,
chests, walkways, hub portals, music and codex working unchanged.
- **Size:** `world.ISLAND_RADIUS` goes 52 -> **150**. Each island's lobed outline spans about 252-267 tiles, and the plaza radius is 14.
- **Map:** `CONTINENT_OFFSET` goes 204 -> 330, so the map is 1560x1560 instead of 1308x1308. Only the ocean ring grew.
- **Placement:** `ISLAND_MIN_RING` sets a floor on each island's distance from the centre, so that neighbours 36° apart
  can never collide where the coast dips (the chord between them always clears 2.1R). It is switchable for a test.
- **Camps:** 12 per island in two rings (0.38 and 0.7 of the coast radius). Camp mobs have x3.2 HP (`ISLAND_CAMP_SCALE`).
- **Waves:** anchor or mini-boss waves have x2.6 HP (`ISLAND_WAVE_SCALE`) and spawn within 12-60 tiles of the landmark.
- **Loot:** every island kill uses the `island` source. The calm bonus is a boss-rank roll with the island source, and island chests roll it too.
- **Level-20 gate:** `RealmSim._gate_islands` puts an under-20 player back at their last off-island spot, with a
  reminder every 4 s. The beach-plaza hub portals refuse them too.
- **Speed:** `stamp_island` samples the coast outline into 2048 angle buckets and span-fills the part of each row that is certainly inland, so only the coastline band gets per-tile maths. It is ~3x faster, and world gen stays around 2.2 s.
- **Timing checks:** Windows 11 power-throttles a headless test process (SDL dummy audio, no window) about 3.8x after a
  few seconds. That was the old "second build is 3x slower" quirk. `tests/_timing.disable_power_throttling()` opts the budget checks out.

## 2. The Mad God's Room (`realm_sim.MAD_GOD_ROOM`)
- **Access:**
  - Opened by the **Mad God's Room Key** (`items.make_mad_god_key`, a shard-slot key). It drops from Heroic bosses (2% per player) and calmed big islands (1% per player).
  - The portal opens at "Godly" difficulty: HP x3.0, 2 loot rolls, weight 0 (never rolled).
  - Entry needs level 20 and a T12+ item equipped.
- **Room:** the Forge's layout, props and ambience (`base="forge"`), with a violet-gold vignette. There is no secret quest and no phase-2 door.
- **Forms** (`MG_ROOM_FORMS`), fought back to back:

| Form | HP | Look | Moves |
|---|---|---|---|
| Mad God | 2200 | the Forge fight's figure | the Forge fight's moves |
| "Unhinged" | x2.2 | four arms, violet robe | Unhinged Volley, Tantrum Wall, Throne Leap, Star Storm, Mad Dash (x3), Unhinged Nova |
| "Absolutely Livid" | x3.2 | crimson wings, burning crown | Livid Volley, Spiral of Spite, Meteor Hell, Rage Beam, Closing Walls, Livid Nova, Sycophants |

  - All three forms have their own grid sprites and move sets, and hit the 50% enrage like any boss.
- **Transform:** `_mg_next_form` spawns the next form on the spot, invulnerable for 1.6 s and silent until then. It plays
  `mg_transform` (VFX and sound) with a boss line. `theme_name` changes to "The Mad God's Room: <form>", which switches the
  banner and the music (`music_key` / `DUNGEON_LABEL_TO_KEY` for co-op). The three tracks are Throne of Nonsense, Unhinged and Absolutely Livid.
- **Enrage:** the last form enrages once after 150 s (fire rate x0.6).
- **Loot:** each form's `loot_source` is `mg_room_1`, `mg_room_2` or `mg_room_3` (doc 33). Only the last form's death ends the room and opens the exit portal.
- **Test:** `tests/check_mad_god_room.py`.

## 3. Speed and network size (follow-up)
| | Before | After |
|---|---|---|
| Fresh-process `RealmSim()` (seeds 11 / 7, throttling off) | 1.53 / 1.64 s | 1.34 / 1.42 s |
| Co-op realm map payload | 8.08 MB of JSON (was ~5.5 MB at the old 1308² size) | 0.17 MB |

- **World generation:**
  - `stamp_island` now uses a per-process polar table (`_island_polar`: angle bucket and distance for every offset around an island's centre, shared by all 10 islands) instead of `atan2`/`sqrt` per tile.
  - It inlines the tile hash and only scans each row out to that row's widest possible extent.
  - Tile-for-tile output is identical (checked against the old function on all 10 islands).
  - `areas._score` binds its lookups locally; its results are identical.
- **Map payload** (`game/netmap.py`):
  - The grid is packed as unsigned 16-bit tiles, zlib level 6, base64, under the same `"map"` key: `{"enc": "z16", "w", "h", "data"}`.
  - The server encodes it fresh for every client entering an instance. It is not cached, because dungeon doors and secret rooms carve the grid at runtime.
  - `NetLink._recv_loop` decodes it off the lock.
  - `decode_map` still accepts a plain list.
  - `tests/check_netmap.py` checks the round-trip, the size and bad payloads.

