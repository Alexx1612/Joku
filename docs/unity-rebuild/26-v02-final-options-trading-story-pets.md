# v0.2 Final Fixes: Options Menu, Trading Overhaul, Story Campaign, Pet Rework

## Context

Commit `cafd86c`. The v0.2-end handoff listed three sizeable efforts:
1. A player-interaction overhaul.
2. A real critical-path story.
3. A pet rework where investment matters.

User decisions that still bind the design:
- **Story:** soft gates (nothing is locked), with a quest log to guide you. Death is a per-act checkpoint. Tone is goofy.
- **Pets:** no per-player quests.

Everything runs in both single-player (`main.py`) and co-op (`server.py` is authoritative, `coop_client.py` displays).

## 1. Options menu and persisted settings

- **`game/settings.py`** holds one JSON file, `settings.json`, next to the game. Saves are atomic (tmp file, then `os.replace`).
  `RR_SETTINGS_PATH` overrides the location; tests use a temp file.
  - Missing keys, wrong types and out-of-range values fall back to the defaults. A corrupt file means all defaults and
    never blocks startup.
- **Defaults:**

| key | default | values |
|---|---|---|
| master_volume / music_volume / sfx_volume | 1.0 | 0..1 |
| muted | false | bool |
| screen_shake / hit_stop | true | bool (turning one off also cancels an effect in progress) |
| particles | "high" | off / low (x0.4 count, weather cap 14) / high (weather cap 35) |
| fps_cap | 60 | 30, 60, 120, 0 (unlimited) |
| show_fps / auto_fire / fullscreen | true / false / false | bool |
| panel_offsets | {} | dragged HUD panel offsets (doc 27) |

- **Applying:** `settings.change(key, value)` persists and applies live (`apply()` pushes to `audio.set_volumes`,
  `vfx.configure` and `weather.set_particle_level`).
  - Music gain = master x music, SFX gain = master x sfx, and mute sets both to 0.
- **Menu:** `game/options_menu.py` is the shared model, opened with the O key. A row is one of toggle, slider (±10%), cycle or action.
  - Keyboard: Up/Down (W/S) select, Left/Right (A/D) change, Enter/Space activate.
  - Mouse: click a row, or click a slider bar to set it to that point.
  - Each client adds its own rows: fullscreen, reset camera, the full-map toggle, and "Abandon run" (single-player) or "Disconnect" (co-op).
- **Esc with nothing open** shows a quit confirmation. Enter/Y quits, Esc/N stays.

## 2. Trading (co-op)

Constants in `server.py`:

| TRADE_RANGE | invite life | confirm countdown | idle timeout | max items/side |
|---|---|---|---|---|
| 110 px (the trade cancels beyond 2.5x) | 20 s | 3.0 s | 90 s | 8 |

- **Consent:** `trade_request` (optional `pid`) creates an invite for the target and does NOT open a trade.
  - The target answers with `trade_invite_accept` or `trade_invite_decline`, or `/accept` / `/decline` in chat.
  - If A and B request each other, the trade opens immediately.
  - The invite dies if either player disconnects, dies, walks out of range or starts another trade.
  - The requester gets `trade_notice` messages: sent, declined, expired or cancelled.
- **Offers stay in the backpack:** an offer holds references to the player's own backpack items; nothing is removed.
  - Every tick, offered items that have left the backpack are pruned and both accepts reset.
  - Execute re-validates everything and checks room as `len(bp) - given + received <= backpack_size`.
  - If there's no room, the trade does NOT cancel. Accepts reset and the status line reads "`<name>`'s backpack is too full".
  - Cancel therefore has nothing to refund, so item loss is impossible.
- **Anti-scam countdown:** once both sides accept, a 3 s countdown starts, and any change resets it.
- **Snapshot:** each viewer gets `trade` = other_name, my_offer, their_offer, my_offer_idx, my_accept, their_accept,
  timer and status, plus `trade_invite`.
- **UI:** click or drag a backpack item onto "my offer" to offer it, and click an offered item to take it back.
  Offered backpack slots get a gold outline.
- **Shift+click:** puts a backpack item in the open Vault or chest, or offers it in the open trade.

## 3. Player-to-player

- **Right-click peer menu:** Chat, Trade, Teleport, Add/Remove Friend, **Inspect** and **Invite to Crew**.
  - **Inspect** shows name, class, level, the 4 equipped items with tooltips, and stats. The peer snapshot carries a compact equipment list.
  - **Invite to Crew** only appears if you're in a crew. It whispers `/crew join <name>`, because there's no server invite action.
- **Drag safety:** any in-progress drag is cancelled on every zone or state change, and when the Vault, trade or options open, or on Esc.

## 4. Story campaign (`game/story.py`)

**Acts** (with the current pacing constants from doc 27):

| # | Title | Objectives |
|---|---|---|
| 0 | Prologue: Welcome, Sucker | talk to Father Given (F); enter the Realm |
| 1 | Act I: The Rim Job | defeat the Landmark Guardian of each outer biome: forest, desert, tundra, swamp |
| 2 | Act II: Last Call | calm any `ISLANDS_NEEDED` = 7 distinct islands |
| 3 | Act III: The Deep End | defeat `INNER_GUARDIANS_NEEDED` = 4 inner-biome guardians; clear `DUNGEONS_NEEDED` = 3 dungeons |
| 4 | Finale: Closing Time | defeat the Mad God in the Forge (phase 1, then phase 2) |

- **Text:** each act has `intro`, `hint` and `done` lines, all original goofy writing, spoken by Father Given and shown in the quest log.
- **Events:** RealmSim emits per-player story events `(pid, kind, key)`, with kinds talk, zone, guardian, island,
  dungeon and mad_god. The owner drains them into `StoryProgress.on_event`.
  - **Credit:** island and guardian kills credit everyone within 1200 px plus the killer. A dungeon clear credits
    everyone in that dungeon.
- **Persistence:**
  - Account-wide `story_act` in `accounts/<name>.json` (default 0, never lowered) is the checkpoint.
  - Per-character objective counts live in `Player.full_state()["story"]` and are lost on permadeath.
  - A new character resumes at the account act with empty counts.
- **Landmark Guardians:**
  - **Spawning:** reaching a landmark wakes its guardian, but only for a player whose current act needs it, and only
    once per landmark per sim. After it dies, the next player who needs it can wake it again.
  - **Stats:** a guardian is the biome's signature elite with HP x `LANDMARK_GUARDIAN_HP_SCALE` (4.0) x act_scale.
  - **Drop:** inner guardians always drop a Dungeon Shard.
- **Difficulty:** `act_scale(act) = 1 + 0.15 * act`, capped at act 4 (1.0, 1.15, 1.30, 1.45, 1.60). It multiplies the
  HP of every spawn (lairs, islands, bosses, dungeon enemies, guardians), using the furthest-along player present in that sim.
- **Father Given (F near him in the Nexus):** says the act intro once, then hints. Talking beats the fountain wish when
  you're next to him. In the Finale, talking sends you straight into a private Forge instance.
- **The Forge:** theme `forge` in `DUNGEON_THEMES`, a short 4-room layout whose boss pool is `["mad_god"]`.
  - When phase 1 dies, `mad_god_phase2` spawns on the spot.
  - Killing phase 2 marks the story complete, sets account `story_act` to 5, and shows skippable scrolling credits (Enter/Esc). Free play follows.
- **UI:**
  - The quest log toggles expanded/collapsed with **J** (Q already rotates the camera). It's drawn in the Nexus, Realm and Bazaar.
  - Bonus rooms keep their own dungeon quest panel.
  - An act-complete banner is centred on screen, and story feed lines go to the item feed.
  - Co-op snapshots carry `quest_log`, story lines and banners.

### Mad God

| kind | HP | dmg (post-mult) | deF | fire_rate_mult |
|---|---|---|---|---|
| mad_god | 2200 | 6-12 | 13 | 1.0 |
| mad_god_phase2 | 3850 (x1.75) | 6-13 (x1.15) | 23 | 0.6 (fires faster) |

Pattern `mad_god`: interval 0.35 s, base bullet speed 220. Each shot does the following:
- **Ring:** 6 bullets at `spin + 60*i`, where `spin = (t*90) % 360`. Phase 2 adds a counter-rotating ring at `-spin*1.3`.
- **Aimed volley:** every 2nd shot (every 3rd in phase 2), 3 bullets at the player, offset -14/0/+14 degrees, speed x1.25,
  **armor-piercing**.
- **Nova:** when the phase timer expires (re-rolled 2.5-4 s), 16 bullets at `22.5*i + spin/2`, speed x1.3, **armor-piercing**.

`armor_pierce` bullets skip the player's defense entirely (`Player.take_damage(dmg, pierce_armor=True)`); a shield still
absorbs them. Measured against a still level-20 player it deals about 41-48 hp/s in phase 1 and about 63 hp/s in phase 2, and
about 11-20 hp/s while strafing. A regression test fails if phase 1 drops to 20 hp/s or below.

## 5. Pet rework

The base system (3 abilities heal/magic/attack, each levelled by feeding) is from doc 20. New in this round:
- **Rarities** (`PET_RARITY_MAX_LEVEL` / `PET_RARITY_START_LEVEL`): common 10/3, uncommon 15/5, rare 20/7,
  legendary 30/10, **mythic 40/14**. Mythic is fusion-only and never drops as an egg.
- **Kinds:** hatchling, imp_pup (common); wisp, sentient_fish (uncommon); griffin_cub, moon_sprite, spirit_fox (rare);
  phoenix_chick, tipsy_thunderbird, sommelier_serpent (legendary); hangover_hydra (heal), last_call_leviathan (attack),
  brewmaster_djinn (magic) (mythic). Each kind reuses an enemy sprite with a tint.
- **Bond:** every feed adds the item's full feed XP to `bond`, even when the pet is capped. Fusion sums both pets' bond.
  - `bond_level = min(25, floor(sqrt(bond / 30)))`.
- **Ability stats:**
  - `lvl_gain = 0.15*(min(L,30)-1) + 0.05*max(0, L-30)`
  - `magnitude = round(base_mag * (1+lvl_gain) * (1 + 0.04*bond_level))` (up to x2 from bond)
  - `cooldown = max(floor, base_cd * 0.95^(L-1) * (1 - 0.01*bond_level))`, where floor is 1.5 s for heal/magic and 0.5 s for attack.
  - Base values (L1): heal 8 hp / 6.0 s, magic 6 mp / 6.0 s, attack 6 dmg / 2.6 s.
- **Carriers:** "Pack" (the `pack_pet` action) turns the active pet into a backpack item "`<Name>` Carrier" (SLOT_EGG, shape
  `carrier`, `pet_state` = the full pet state: levels, xp, bond).
  - Using a carrier unpacks that exact pet.
  - Hatching or unpacking while a pet is out puts the current pet in a carrier in the used item's own slot, so it never fails for lack of room.
  - `Item.pet_state` round-trips through JSON, saves, the Vault, trades and bags.
- **Fusion:** drop a carrier on the active pet (the existing `feed_pet` action path).
  - **Requirements:** both pets have the same rarity and every ability at that rarity's max.
  - **Result:** the next rarity, keeping the active pet's family if a kind of that rarity shares it (otherwise a random
    one). The specialty starts at no less than the new rarity's start level, and the other two start at old max // 2.
    Bond is summed, and a pink VFX burst plays.
  - **Rejections** (not maxed, rarity mismatch, mythic) consume nothing and give a reason message.
- **Measured sustain** (heal hp/s): maxed common 5.0, maxed legendary with no bond 28.7, legendary at bond 12 42.0,
  mythic at bond 25 62.7.
