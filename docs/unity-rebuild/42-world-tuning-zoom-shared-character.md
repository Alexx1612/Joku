# 42 - Zoom, closer aggro, a tougher night, island danger, more buildings, one character everywhere

"V0.2 final final fin" session, after doc 41. These are your follow-up requests, made while batches A and B were being built:

> "make the difference between mobs during the day and night to be a bigger difference (outer big island is the
> easiest while the middle is top notch hard, same as islands, also add more building and things to islands and map,
> also make it possible that what character i create in the singleplayer world to be used also in multiplayer)"
>
> "make it so the map can zoom 10x and also make the mobs agro from a bit closer not from half a screen away and
> also try to zoom in on the screen or make all bigger cause i can see the player that way (maybe 1.25x everything)"

Decided with you:
- **Islands:** both. They're ranked by distance from the arrival beach, **and** each one gets a shore-to-centre gradient.
- **Characters:** they carry over, then they're shared.

## World zoom (`game/view_scale.py`)
**Options → Display → Zoom:** 100 / 110 / **125%** (default) / 150%.

**Only the world is magnified:** the tiles, you, the monsters, bullets, effects and the night lighting. The HUD, the dock and every window stay at full size.

**How it works:**
- `world_begin` swaps in a small canvas (screen ÷ zoom) and sets the camera to zoom 1.
- The world draws onto it, and `world_end` smoothscales it onto the screen.
- Then the HUD draws on top at full resolution.

**The camera:** outside that pass, `Camera.zoom` = zoom. `cam(pos)` and `cam.inverse(mouse)` work in real screen pixels, so these line up exactly with the scaled-up world:
- mouse aim
- a bag window over its bag
- the labels

Headless runs (`SDL_VIDEODRIVER=dummy`: the suite and the screenshot tools) stay at 100% unless `RR_ZOOM` is set.

**Why it changed mid-session:** the first version scaled the WHOLE frame (HUD included). You reported "zoom is not matching with the hud and gui", and a capture of the real window showed why:
- the 656 px canvas was too short for the dock, so the backpack rows fell off the bottom
- the HUD panels drifted

The centred feed messages are still centred on the play area and wrapped to it.

## Map zoom up to 10×
- The full map and the corner minimap now go up to **10×**.
- Zoom steps **multiply** (×1.2 per notch), so 1× → 10× takes 13 notches instead of 36.
- The Quest Map's zoom cap is also 10×.

## Closer aggro, a much tougher night (`game/night.py`, `entities.AGGRO_SCALE`)
- **Aggro:** every non-boss now notices you from **×0.75** of its table aggro range. A goblin's goes from 220 to 165 px.
- **Night aggro:** the multiplier is now ×1.3 (×1.55 in the dark), down from ×1.6 / ×2.0.
- **Worst case** (dark, Blood Moon, the heart of the Realm): a goblin now notices you from 392 px, less than half the screen. It used to be about 750 px.
- **Night stats:** the night is now a different game. `NIGHT_RULES` / `BLOOD_RULES`:

  | | HP | damage | attack rate | speed | aggro (lit / dark) | leash |
  |---|---|---|---|---|---|---|
  | night | **×1.5** (new) | ×1.45 (was 1.2) | ×1.33 (cd ×0.75) | ×1.2 | ×1.3 / ×1.55 | ×1.5 |
  | Blood Moon | **×2.0** (new) | ×1.75 (was 1.35) | ×1.61 (cd ×0.62) | ×1.3 | ×1.6 / ×1.9 | ×2.0 |

- **HP handling:**
  - Night HP scales `hp_max` and keeps each mob's share of health (`night._set_hp_max`).
  - Dawn puts it back, still proportional.
  - The day stats (`_day_stats`) now carry `hp_max`, and the danger scaling of an already-night-scaled mob scales that too.
- The Dictionary's night-rules page reads the new numbers automatically.

## Island danger (`game/danger.py`)
- **Registration:** `danger.set_islands(centres, beach)` runs once the islands exist: in `RealmSim.__init__` after `_stamp_islands`, and on co-op clients from the realm areas.
- **The formula:** `island_frac(x, y)` = 0.45 × rank + 0.55 × (shore → centre).
  - **rank:** 0 for the island nearest the arrival beach, 1 for the furthest.
  - **shore → centre:** 0 at an island's shore, 1 at its centre.
  - It's None off the islands.
- **`island_mults(g)`** sits on top of the islands' own level-20 scaling:

  | | nearest shore | furthest centre |
  |---|---|---|
  | HP | ×0.7 | ×1.7 |
  | damage | ×0.8 | ×1.35 |
  | attack cooldowns | ×1.1 | ×0.85 |
  | XP | ×0.9 | ×1.6 |
  | extra loot roll | 0% | 49% |

- **Stored separately:** island mobs keep `e.island_danger`, separate from the continent's `e.danger`, so the continent-only shard-difficulty and Heroic-shard rules don't apply out there. `_danger_mults` and the extra-loot roll read it.
- **HUD:** the minimap's danger label says **"Isle: Calm .. Lethal"** on an island.

## More buildings (`RealmSim._stamp_hamlets`, `_stamp_island_outposts`)
- **Shared helpers:**
  - `_stamp_house` (the old shack code, now shared) builds a doored, plank-floored shelter registered as a safe house.
  - `_clear_spot` checks the ground is clear.
  - `_scatter_props` places big props and skips any that don't fit the ground.
- **More wayside shelters:** `SHACKS_PER_BIOME` 2 → **3** (30 shacks).
- **A hamlet in every biome** (10): two doored houses, a well, a campfire, two lamp posts, a market stall, barrels, a bench and a hay bale.
- **Every big island** gets:
  - an **outpost**: a doored house, a tent, a campfire, two lamp posts, barrels and a signboard
  - a **lone shelter**

  Both sit 34-95 tiles from the island's centre and stay clear of the mob camps.
- **Totals on a typical map:** 82 shelters, up from about 32.
- **`_repair_house_doors`** runs after all the stamping and puts back any shelter door a later decoration landed on (a rare random-map collision the new test once caught).

## One character in single-player and co-op (`game/characters.py`)
- **On the same PC** this already worked: single-player and a locally-run server share the save folder, so the same name means the same file.
- **On a remote server:**
  - **Join:** the co-op client sends its local save with the `join` message.
  - **Server checks:** `characters.validate` rebuilds the upload and refuses anything malformed or impossible:
    - level 1-20
    - each stat 0-300
    - HP/MP up to 10k
    - bag sizes in range
    - item tiers 0-14
    - at most 400 kB
  - **Which copy wins:** `pick_for_join` keeps whichever copy (the server's or the upload) has come further (level, then xp, then kills).
- **While you play:** the client mirrors the server's copy of you into its own save every 10 s, on disconnect and on quit (`CoopClient._mirror_character`). The next single-player run carries on from there.
- **A co-op death deletes it.** Permadeath is the same everywhere.
- **Not shared:** the Vault stays per machine, because it's account storage the server keeps on its side.

## `/help` explains every command (`game/admin_manual.py`)
You asked: "explain //help commands in greater detail so i know what they can do (with examples and telling me what the command does".

`MANUAL[name] = (what it does, [(example, what that example does), ...])` covers **all 64 commands**, everyday and admin.

| You type | You get |
|---|---|
| `/help` | the categories and every command name |
| `/help <category>` or its number | each command's usage, what it does and an example |
| `/help <command>` | the full page: usage, aliases, "What it does", every example with "-> what happens", plus the old details |
| `/help all` | the whole manual, about 335 lines, scrollable |

`/man`, `/manual` and `/helpp` work as aliases.

`check_admin_commands` makes sure every registered command has a manual entry with examples.

## Where each quest has already been (`story._places`, `sidequests` "names")
**Story objectives that count places** (areas, landmarks, islands, NPCs, guardians, dungeons) now carry:
- `seen`: the readable names of where they already counted you
- for a fixed set of places, `todo`: where you haven't been yet

**Side quests:**
- They remember a readable label for each distinct thing that counted (`active[qid]["names"]`, saved).
- The sim's `reach` events pass labels: the landmark name, the island name, "the Jungle spot at (x, y)".
- Biomes, NPCs and topics get readable fallbacks.

**In the Quest Log:**
- under each objective: **"Been there: …"** (green) and **"Not yet: …"** (grey)
- under each side quest: **"Done so far: …"**

`codex.place_name` / `place_candidates` do the naming. Co-op gets it through the existing quest-log snapshot fields.

## Your own map pins (`game/map_pins.py`)
**Placing:** click the full map (M), the Quest Map or the Dictionary's little map to drop a pin. Click a pin again to remove it.

**Limit:** 5 pins; the oldest goes when you add another.

**Where they show:** pins are world-px `[x, y, "Pin n"]` saved with the character (`Player.map_pins`), and they appear wherever quest markers do, in green:
- on the world, with an edge arrow and the distance in tiles
- in the tracker list
- on the corner minimap and the full map
- on the Quest Map and the Dictionary's map

**Co-op:** the client sends `map_pins` and the server stores the cleaned list on you, so they're saved with you.

## Tests
**`tests/check_world_tuning.py`** (also `check_visited_places_and_map_pins`: "Been there / Not yet / Done so far" in the Quest Log, pins added and removed through the full map, Quest Map and Dictionary clicks, the 5-pin limit, the save round-trip, and the server action):
- **Zoom:**
  - the canvas is 1093×656 at 125%
  - a click in window pixels lands on the right canvas row
  - the Options panel fits
  - the setting is validated
- **10× maps:** reached in 13 notches.
- **Aggro:** the scale applies, bosses are exempt, and the worst night case is under half the screen.
- **Island danger:**
  - the ranks run 0 → 1
  - the shore is easier than the centre, and the far centre is the hardest
  - real island mobs are scaled and pay more
  - the HUD shows "Isle:"
- **Settlements:**
  - hamlets and outposts exist
  - every shelter door is a door tile
  - nothing is stamped over the new houses
  - the outposts are on the islands
- **One character:**
  - validate and pick
  - a **real join over a socket pair** adopts the uploaded character and saves it on disconnect
  - an impossible upload gives a fresh character
  - the client mirror writes the file, and a death deletes it
- **The heartbeat's shape and the swelling red ambient.**

**Updated tests:**
- `check_night_horror`: the night rules from the constants; dawn keeps a wounded mob's share of HP.
- `check_quest_log_dictionary`: the Quest Map zoom cap is 10.
- `check_settings`: rows never overlap, in two columns.

## Screenshots
- `screenshots/2026-10-08/zoom_125/` (6): the Realm at 125% and at 100%, plus Options, Dictionary, Calendar and Forge (the HUD is never zoomed).
- `quest_places_and_pins/` (5): the Quest Log's Been there / Not yet, and pins in the world, on the full map, on the Quest Map and on the Dictionary map.
- `world_settlements/` (7): three hamlets, three island outposts (the minimap says "Isle: …"), and an outpost at night.
