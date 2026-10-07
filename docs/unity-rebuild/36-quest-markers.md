# 36 - Quest markers

"V0.2 final final" session, after doc 35. The user asked: "show markers on map for when i click on a quest i can have
the show marker for it and it shows me on the map where to go".

## How it works for the player
- **Toggle:** every quest in the Quest Log (J, or Options -> Quest Log) has a **Show marker / Hide marker** button. You can also click a quest's line to select it and press **T**. A quest with no fixed place, like Snack Time (pets), shows a disabled "No location" instead.
- **Limit:** up to **3** quests are tracked at once. Tracking a 4th drops the oldest. Each quest has its own colour (gold, cyan, pink).
- **Where markers appear:**
  - **Minimap:** a pulsing diamond, or an arrow on the map's edge when the target is outside the crop.
  - **Full map (M):** the same, at full size.
  - **World:** a bobbing pin over the target, labelled with the quest's name, when it's on screen. Otherwise an arrow sits at the edge of the play area with the distance in tiles. It's drawn after the night darkness, so it reads at night.
  - **Tracker:** a list at the bottom left: colour, quest name, distance in tiles or a where-to-go note.
- **HUD quest log:** tracked quests show their coloured diamond.
- **Updates:** markers follow the current objective. A finished side quest moves to its turn-in NPC, and a handed-in quest drops off the list.

## Target resolution (`game/quest_markers.py`)
- **Tracked ids:** `"story"` (the current act's first unfinished objective that has a place) or `"side:<quest id>"`. They are stored in `Player.tracked_quests` and saved through `full_state`. Old saves load with none.
- **Where a quest points:** `side_target(q)` gives the turn-in NPC once a quest is ready, the giver for Heroic trials (their relics drop in dungeons), and otherwise the quest's own target.
- **Candidate places:** `candidates(target, world)` returns `(zone, x, y, label)` places, built on `codex.where_for_target` / `markers_for` plus:
  - **Nexus NPCs:** Father Given, Hammerstein (the Anvil), Bitterwick, and the Mad God via Father Given.
  - **Aliases:** `areas` -> the big named places, `island_chests` -> islands.
  - **`locals`:** the Realm NPCs.
  - **`heroic_trials`:** the trial givers.
  - **`water`:** the nearest WATER tile, searched up to 60 tiles from the player.
  - **Live NPC positions** override their home spots when they're in view.
- **Zone handling** in `resolve()`:

| You are in | Target is in the Realm | Target is in the Nexus |
|---|---|---|
| the Realm | nearest candidate | note: "in the Nexus - press R" |
| the Nexus | the Realm portal tile | that NPC |
| Bazaar / Vault room | that zone's portal back | that zone's portal back |
| a dungeon | note: "leave the dungeon (R)" | same |

- **No location:** `gear`, `pets`, `world_boss`, `dungeons`, `heroic_dungeons` and `dungeon:*` give "no fixed location".

## Wiring
- **Journal:** `game/journal.py` adds "select" and "track" actions to the Quest Log layout. `ctx["tracked"]` and `ctx["on_track"]` come from each client, and T toggles the selected quest.
- **Minimap:** `minimap.draw_corner(..., quest_marks=)` and `draw_full_map(..., quest_marks=)` call `quest_markers.draw_on_map`, which clamps off-map markers to the map's edge.
- **World:** `quest_markers.draw_world` and `draw_tracker` are called from `main._draw_quest_markers_world` and `coop_client._draw_quest_markers_world`.
- **Co-op:** the client resolves everything from its own snapshot data: quest logs, NPCs in view, realm areas and the deterministic Nexus layout. Toggling sends a `track_quests {ids}` action, so the server saves the ids with the character, and the first snapshot after joining loads them.

## Tests
`tests/check_quest_markers.py` covers:
- toggling and the cap of 3
- saving and loading, plus the server action
- resolution: a Realm NPC, a mob's biome, the Nexus from the Realm, the Realm from the Nexus (the portal), hubs, dungeons, the Anvil, the shoreline, turn-in, pruning
- the Quest Log button and the T key
- edge clamping on the map and in the world
- the minimap, full map and tracker drawing
- the single-player game drawing markers in the Nexus and the Realm
- the co-op client sending `track_quests` and drawing markers

Screenshots: `screenshots/2026-10-07/quest_markers/`.
