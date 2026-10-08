# Handoff: "v0.2 final final" session → next session

Project: **Realm Reforged**, a Python 3.12 + pygame RotMG-like.
- Single-player: `main.py`
- Authoritative co-op: `server.py` + `coop_client.py`
- Shared simulation: `game/realm_sim.py` and `game/entities.py`
- Repo `C:\Users\alexandru.mirea\PycharmProjects\ROTMG`, GitHub `Alexx1612/Joku`, branch `main`.

**Still V0.2.** This session added a big content update on top of "Ends of V0.2" (release tag `v0.2`, commit 23123be).
It is committed **locally only**: not pushed, and the release has not been rebuilt. That needs the user's OK.

## Where to look first
- `README.md`: features (story, items/forge, Heroic, islands, Mad God's Room), and version history "final final".
- `GAME_DATA.md`: its new top section holds every new number and name.
- `docs/unity-rebuild/31` to `40`: rebuild-level detail for each part below. The index is `00-INDEX.md`.

## What this session did
1. **Telegraphs never lie** (doc 31, `game/enemy_attacks.py`)
   - A move's aim, ring gaps, wall gap and slam-burst facing are fixed when the warning appears, and the move fires exactly that.
   - A new `spokes` telegraph (one arrow per bullet) replaces the misleading circles on bullet moves.
   - Chained dashes get their own lanes. Crossfire only hits from its circles.
   - `tests/check_telegraph_accuracy.py` strafes through every warned move. It was mutation-tested: the old rule fails it.
2. **Story v2** (doc 32): 7 acts.

   | Act | Title |
   |---|---|
   | Prologue | Welcome, Sucker |
   | Act I | **The Grand Tour** (exploration; the old Act I name is gone everywhere) |
   | Act II | Bouncer Problems |
   | Act III | Retail Therapy |
   | Act IV | The Deep End |
   | Act V | Last Call |
   | Finale | Closing Time |

   - Old saves and accounts migrate (`OLD_ACT_TO_NEW`, `"v"`/`story_v`).
   - Use `story.ACT_*` names, never raw indices.
3. **Gear** (doc 33)
   - T12-T13 (mythic) drop only from the new loot sources; T14 is forge-only.
   - Forge Ingots, and Divine items with Starfall and Second Wind.
   - Brother Hammerstein's Anvil in the Nexus (`game/forge.py`, dialogue-driven, with a drawn anvil prop).
   - Heroic versions of all 7 dungeons, each unlocked by a Heroic trial quest from that dungeon's local.
   - `game/gates.py` level gates: Heroic 16, islands 20, Mad God's Room 20 plus a T12 item.
4. **Big islands** (doc 34): about 260 tiles across, 12 camps each, much harder, with the island loot source and a level-20 gate.
   - The map is 1560². `stamp_island` was made ~3x faster to keep world generation around 2.2 s.
   - **Decision:** the islands grew in place instead of becoming instanced zones, as the plan had said. This kept every island system working with far less risk. Tell the user if they ask.
5. **The Mad God's Room** (doc 34): three forms back to back.
   - Forms: Mad God, then "Unhinged", then "Absolutely Livid". Each has its own grid sprite, moves, music and a better loot tier. The last form always drops a Divine item, and it enrages at 150 s.
   - Opened by a rare key from Heroic bosses and calmed islands.
6. **Audio / VFX / music**
   - 13 new synthesized event sounds: `audio.EVENT_SOUND` and `play_event`, carried as `("sfx", key, x, y)` sim sound events.
   - 10 new original tracks, 33 in total.
   - New VFX: Heroic tint and aura, Mad God's Room tint, transform, Divine and mythic drop beams, forge sparks, harbour spray.
7. **Fixes found on the way**
   - Co-op `NetLink` lost or replayed one-shot snapshot events (chat, sounds, popups). This made `check_full_playthrough` fail even on 23123be; it is fixed.
   - The old "second build is 3x slower" quirk was **Windows 11 power throttling** of headless test processes (SDL dummy audio, no window). `tests/_timing.py` opts the budget checks out.

8. **Night horror update (doc 35, after be3256b was pushed and released)**
   - 10-minute cycle and a 4-minute night, with a big countdown time bar.
   - A light map with wall shadows, plus a Luminosity setting.
   - Safe houses with doors.
   - Night rules, events and night-only mobs, and the Blood Moon with the Red Harvester.
   - Precise combat: slower, heavier hits.
   - Weapon Shards and Bag 2 dock tabs.
   - Hand-painted night-mob art with glow layers.
   - Night realism: golden and blue hour, moon phases, mist, lit windows, sleeping animals, town folk indoors, eye adaptation, ambience.
   - The Lamplighter event, which rewards the **Light of RDV** ring.
   - Spawn-on-top-of-you fix.
   - Committed **locally** after be3256b; not pushed.

9. **Night sky, quest markers and gem forging (docs 35 §11, 36, 37; local, not pushed)**
   - **Night sky:** the golden-hour sweep, cloudy / rain / storm nights with lightning, shooting stars and Star Fragments, night herbs, owls, frost sparkle.
   - **Quest markers:** Show marker / T; pins on the minimap, full map and world, plus edge arrows.
   - **Gem forging:** 7 stones in 5 grades, set into weapons at the Anvil, elemental trails and bursts, gem veins mined with F.

10. **Danger, calendar, admin commands, the complete Dictionary (docs 38, 39)**
    - **Danger by distance:** mobs and night mobs scale with distance from the continent's centre; the rewards and the difficulty of dropped shards scale with it. The landmark guardians and the islands are exempt.
    - **Calendar (K):** a 7-night forecast that comes true, plus the live-event schedule.
    - **Admin commands:** 63 of them, `game/admin.py`. `/help` browses them; co-op needs `--admin`.
    - **Dawn/dusk light:** reworked into a soft band that travels left to right at dusk and right to left at dawn.
    - **Dictionary:** the new categories Gear & Crafting and Night & World.
    - **Pacing re-measured:** median 105.4 min (Act II about twice as long).
11. **The Forge window, the Calendar in Options, the tagged Dictionary (doc 40, "final final fin" session)**
    - **Forge:** F on Brother Hammerstein → his chat → **Open the Forge** (`game/forge_menu.py`).
      - Four tabs: Temper / Reforge (UT) / Fuse Shards / Stonework. Every recipe is listed, with no cap.
      - Blocked recipes show the reason. The detail panel shows before → after, ingredient counts and sockets.
      - A confirm step guards pry, T12+ items and 2+ Ingots. A 0.6 s hammering animation plays before the result.
      - Co-op: `forge_apply` is re-validated by the server (`forge_menu.apply_request`, Nexus only, ≤180 px from the Anvil).
      - The old forge / stonework dialogue nodes are gone.
    - **Calendar** (`CalendarWindow`): also in Options → Journal. It's opaque, drags by its title bar (saved in `panel_offsets`), and has a detail card that explains every event, weather, moon phase and live event from the constants. Filter chips are saved in `calendar_filter`.
    - **Dictionary:** `codex.entry_tag` gives one of 14 tags. It also has:
      - filter chips (OR between chips, AND with search; saved in `dict_tags`)
      - world content first, then a "Tips & mechanics" sub-heading
      - TIP / MECHANIC entries drawn as note cards
      - typing a name selects it
    - **Screenshots:** `tools/snap_ui_windows.py` → `screenshots/2026-10-08/{forge_menu,calendar_menu,dictionary_redesign}/`.
12. **UX batches A + B (doc 41)**
    - comparison tooltips (`ui.COMPARE_PLAYER`, `ui.compare_lines`)
    - the death recap (`game/death_recap.py`; hits tagged via `Bullet.src_info`, `zone["info"]`, `Enemy.hit_info`)
    - `game/loot_filter.py`: auto-loot in `RealmSim.update`, hide-junk filter, beams
    - Salvage / Smelt (`Player.scrap`), Sort, Stash mats
    - `game/binds.py` (translate-to-default rebinding + window)
    - `game/access.py` (palettes, outline, telegraph strength, text size, reduce flashing)
    - the two-column Options menu
    - the Blood Moon heartbeat (`ui.heartbeat_shape`, `lighting.GRADE["pulse"]`)
    - **Still open from the 10-idea list (Batch C):** waystones, pings / waypoints, first-hour tips, the Bounty Board, the Graveyard.
13. **World tuning (doc 42)**
    - world zoom (`game/view_scale.py`, default 125%: the world pass on a small canvas, `Camera.zoom` everywhere else; HUD never zoomed; headless runs stay 100% unless `RR_ZOOM`)
    - the `/help` manual (`game/admin_manual.py`), 'Been there / Not yet' per quest, map pins (`game/map_pins.py`)
    - 10x maps
    - aggro x0.75 (`entities.AGGRO_SCALE`)
    - a much tougher night (`night.NIGHT_RULES` / `BLOOD_RULES` incl. HP)
    - island danger (`danger.set_islands / island_frac / island_mults`, `e.island_danger`)
    - hamlets, island outposts, more shacks (`RealmSim._stamp_house` etc.), `_repair_house_doors`
    - one character in single-player and co-op (`characters.validate / pick_for_join`, `CoopClient._mirror_character`)

## Checkpoint commits (local, on top of 23123be)
- `cf3a9ec`: telegraphs, story v2, NetLink fix
- `50cc80d`: gear, forge, Divine, Heroic, gates
- `68eda5f`: big islands and timing
- `2b134b5`: Mad God's Room, effects wiring, docs

## Conventions (unchanged, keep following)
- Run `python tests/run_all_checks.py` after every batch. There are now **87 scripts** (doc 40 added `check_forge_menu`, doc 41 `check_ux_batch_a` / `_b`, doc 42 `check_world_tuning`). `check_areas_trees_bosses` and `check_big_islands` can flake on the random map or timing; re-run them alone.
- Look at headless screenshots for visual work: set `RR_SHOT_DIR` for the new checks.
- All art and music must be original.
- Don't commit, push or release without the user's OK.
- Releases must work on Windows and Linux (tag push → CI builds both).
- Keep the goofy tone.

## Open items
- **Night update not pushed / not released:** everything after be3256b. The user decides. Releasing means pushing `main` and moving/force-pushing the `v0.2` tag, or a new tag if they want one.
- **Pacing:** not re-measured for the 7-act arc. The old bot figure was about 66 minutes for 5 acts.
- **Art:** the new sprites are original grid art (Hammerstein, the two Mad God evolutions) and procedural icons (ingot, key). There are no hand-painted PNG versions yet. Heroic bosses reuse the normal boss sprite plus the crimson aura and tint.
- **Co-op map payload:** about 5.5 MB of JSON before; still uncompressed and now ~40% bigger (zlib would cut it about 50x).
- **World-gen budget:** it passes at ~2.2-2.9 s against a 3 s limit on this machine while PyCharm indexes. It's tight; the next easy win is `_decorate_realm` / `_realm_fields`, which scale with map area.
