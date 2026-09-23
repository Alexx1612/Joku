# 04 — Dungeons, Bosses, Secret Quests, and Potions

Scope: Batch 1 Sections C, D, E, F+G, and K — the "endgame loop" foundational systems: how a themed dungeon instance is generated and populated, how you get into one (dungeon shards), what can hide inside one (a secret quest, Totems, a hidden room), what happens when its boss dies (portals, an optional harder second phase), and the potion consumable system. Ability mechanics (nova/heal/etc. and their telegraphing) are covered in `02-classes-combat-stats.md` — this file covers where/how a dungeon exists, not what you can cast inside it.

**Scope boundary note**: this file describes the *foundational* Batch 1 version of each system. Later batches (out of this document's scope) added further refinements on top — e.g. the boss's second-phase pocket room is now gated behind its own quest-driven "door opening" mechanic rather than being reachable immediately at boss death, and decorative props were later scattered throughout every room. Where current code has visibly moved past what's described here, a short note flags it without going into the later mechanic's own detail.

---

## 1. Per-theme dungeon generation (Batch 1 Section C)

### What it is

A "bonus room" (dungeon instance) is not one generic rectangular arena reused with a different color palette per theme — each of 7 themes (Cave Warren, Frozen Crypt, Jungle Ruins, Ember Den, Sunken Grotto, Wind Spire, Forgotten Vault/"generic") gets a genuinely different room-*shape* generation strategy, its own floor/wall tile, its own enemy roster + spawn weights, and its own boss pool.

### Why/how it was chosen

Framed in the plan as wanting dungeons to feel like distinct places, not palette swaps of one layout — the memory's own verification note makes this concrete: real floor-tile-count footprints across the 7 themes ranged 293-960 tiles for the *same* room-count target, which is presented as evidence of "real shape variety, not just palette swaps," i.e. the variety was treated as a thing to actually verify, not just assert.

### Implementation detail (verified against current `game/world.py` and `game/realm_sim.py:231-275`)

- `world.make_bonus_room(floor_tile, wall_tile, theme_name)` dispatches to one of three room-*placement* strategies based on `theme_name`:
  - `_place_rooms_rect` (baseline: generic/frozen_crypt/jungle_ruins/ember_den) — random non-overlapping rectangles, corridor-connected nearest-first.
  - `_place_rooms_cave` + `_carve_blob` (Cave Warren only) — organic rooms built from overlapping carved circles instead of hard rectangles.
  - `_place_rooms_chain` (`CHAIN_THEMES = {"sunken_grotto", "wind_spire"}`) — rooms placed in a deliberate path order via random heading swings (large swings = a winding chain for Sunken Grotto, small swings + a narrower 1-wide corridor width for Wind Spire's "long mostly-linear corridor" feel) — and, critically, chain-placed rooms are **never** re-sorted by the nearest-neighbor pass the other two strategies use, since re-sorting would destroy the deliberate winding/linear shape.
  - `ROOM_COUNT_BY_THEME`/`ROOM_SIZE_BY_THEME` further vary room count (5-9) and size per theme (Ember Den = fewer/larger rooms, Wind Spire = narrower).
- `DUNGEON_THEMES` (`game/realm_sim.py:244`) is the per-theme data table: a display label, floor/wall tile constants, an enemy kind+weight list, and a boss-kind pool. `THEME_FOR_KIND` maps a *portal-dropping enemy's own kind* to the theme its dropped portal opens into (see part 2) — so which dungeon you get is a direct function of which enemy you killed, not a random roll independent of what you were fighting.
- **Fixed, non-respawning mob pods**: every non-entrance/non-boss room gets 4-8 enemies spawned once, at generation time, from that theme's roster — tagged with a `room_idx` so a `_room_cleared_check()` (run on every kill) can flip that room's `cleared` bookkeeping flag once its pod is fully dead. This deliberately does **not** gate movement through the room — "rush vs. clear" is a real player choice, not something the game enforces, and a room with live mobs is always still walkable. The project's own history flags a real, found bug here: an *older*, separate ambient/proximity-based enemy spawner was still running unconditionally in every bonus room this whole time, silently contradicting the "fixed pods, no respawn" design goal — found and deleted, with the ambient spawner's own timer now explicitly gated to only run outside bonus rooms.
- **Destructible obstacles**: 1-2 per roughly half of a dungeon's middle rooms, a real `Obstacle` entity (not a wall tile) with 1 HP, no AI, resolved through the exact same `Bullet.hit_test` pipeline every other hit in the game uses (see file `02`). Obstacles are also included in the same line-of-sight/movement-solidity checks real wall tiles get, specifically so an enemy standing behind one can't "cheat" and shoot through it — a real, closed gap the project's own history documents finding and fixing.
- **Fog-of-war**: reuses the *same* per-client explored-tile set the minimap already tracks (no second, dungeon-specific copy of "have I seen this tile" state) — any tile not yet in that set renders as a flat, undifferentiated fog color instead of its real contents.

### Unity rebuild prompt

> Give your dungeon/instance generator a per-theme dispatch: a small set of named themes, each configured with its own floor/wall visual set, a distinct room-*shape* generation strategy (straight-edged rectangular rooms connected by corridors for a baseline theme; organic blob-carved rooms for a "cave" theme; a deliberately-ordered winding or near-linear chain of rooms, NOT re-sorted by nearest-neighbor distance, for "snaking path" themes), and its own enemy-spawn table + boss pool. Populate every non-entrance/non-boss room with a fixed, one-time set of enemies at generation — never an ongoing ambient spawner inside a dungeon instance — and let players choose to rush past a room's live enemies or clear it first, with no door/gate enforcing either choice; only track "was this room's pod fully cleared" as informational state. Scatter a handful of one-hit-destructible wall obstacles through some rooms, resolved through the exact same hit-detection your normal combat uses, and make sure they block sightlines/projectiles for AI exactly like a real wall does (an enemy should never be able to see or shoot through a destructible obstacle it hasn't destroyed). Implement fog-of-war by reusing your existing "which tiles has this player explored" tracking (from your minimap system) rather than maintaining a second, dungeon-specific copy of the same concept.

---

## 2. Dungeon Shards: carried, player-triggered portals (Batch 1 Section D)

### What it is

Killing an "elite"-rank enemy has a chance (`MOB_PORTAL_CHANCE`) to drop a **Dungeon Shard** item (a themed consumable, riding in the same loot bag as everything else that kill dropped) instead of instantly opening an ambient portal at the kill spot. Using the shard from the backpack, wherever/whenever the player likes, spawns a real `Portal` object at the player's current position.

### Why/how it was chosen

An explicit redesign away from an earlier "elite kill instantly pops open a portal at the kill location" behavior — the new version is described as matching the plan's own framing ("used later... to open a themed portal wherever the player happens to be standing"), i.e. turning an ambient, easy-to-miss event (a portal you might not even notice if it opens off-screen) into a real carried, deliberate-use item.

### Implementation detail (verified against current `game/items.py`, `game/entities.py:268-278`, `game/realm_sim.py`)

- `SLOT_SHARD = "shard"`, `Item.shard_theme` (which `DUNGEON_THEMES` key it opens), `make_dungeon_shard(theme_name, theme_label)` — follows the same factory-function pattern as every other consumable family.
- `Player.use_shard(index)` mirrors `use_potion`'s exact shape: pops the backpack slot, returns the theme key (or `None`) — but does **not** spawn the actual `Portal` itself, since `Player` has no reference to the active `RealmSim`. The caller (`main.py`/`server.py`) is responsible for the actual `Portal(p.pos, theme=theme_name, ...)` construction — a clean separation between "what does using this item consume/return" (pure `Player` logic) and "what world-state side effect does that trigger" (sim-level logic the `Player` class itself is deliberately kept ignorant of).
- Only usable while actually in the open Realm (not already inside a dungeon, not in the Nexus/Bazaar/Vault) — a no-op with an explicit rejection message in single-player, a silent no-op in co-op (there being no cheap private-message channel for a rejection notice was treated as an acceptable, documented minor gap rather than something worth building new infrastructure for).
- **Difficulty is pre-rolled and shown on the portal itself** (a later refinement within this same feature area, verified against current code): rather than rolling difficulty when the dungeon is finally entered, it's rolled **the instant the shard is used** and carried on the `Portal` object all the way through to the `RealmSim` that eventually gets created from it — so a player sees a colored Easy/Medium/Hard label on the portal *before* deciding whether to walk through, rather than committing blind. This was an explicit user choice made via a direct multiple-choice question (pre-rolled-and-labeled, over a "choose your difficulty" popup or a shard-rarity-based approach).

### Unity rebuild prompt

> Make a themed-dungeon-access item that a mid-tier enemy kill has a real chance to drop as a carried inventory item (not an instant ambient world event at the kill location). Using it from inventory spawns a portal at the player's current position, tagged with which dungeon theme it opens — roll that dungeon's difficulty tier at the moment the item is *used*, not when the resulting portal is later entered, and display the rolled difficulty as a visible label on the portal itself so players can see what they're about to walk into before committing. Keep the "does this item work here" zone check (only usable in your open-world zone, not while already inside an instance or in a safe hub) as a clean rejection with player feedback in single-player, and treat a co-op no-op-without-feedback as an acceptable simplification rather than building new UI just for that edge case.

---

## 3. The secret "???" quest, Totems, and a hidden loot room (Batch 1 Section E)

### What it is

~30% (`SECRET_QUEST_CHANCE`) of dungeon instances secretly hide one of 3 quest kinds, tracked live and shared across every player in that instance:
- `kill_goons` — hunt down a specific (randomly chosen) trash-mob kind from the dungeon's own roster.
- `kill_totems` — destroy 3 (`TOTEM_COUNT`) stationary, harmless, neutral "Totem" enemies scattered into the dungeon's fixed rooms.
- `boss_timer` — kill the main boss within a time limit (currently 150s) or the quest fails.

Completing one carves open a room that was reserved-but-left-as-solid-wall at generation time, revealing a genuinely harder "???" secret boss inside.

### Why/how it was chosen

A direct reference to RotMG's own "hidden bonus room" convention (explicitly named as such in the project's own comments). No single explicit user quote is recorded choosing these 3 specific quest kinds over others — they're presented in the plan as a small, deliberately extensible registry (a new kind is meant to be "a one-line add" to the registry plus a branch in two functions), i.e. the *design* choice being documented is "make this trivially extensible," not the specific 3 kinds themselves.

### Implementation detail (verified against current `game/world.py`, `game/realm_sim.py`)

- `world.make_bonus_room()` reserves one extra non-overlapping room, returned as `info["hidden_room"]` — its rect exists in the room-placement data, but its tiles are **never carved to floor** at generation time (they stay solid wall/rock). `world.reveal_hidden_room(grid, hidden_room, connect_to_center, floor_tile)` is a separate function that carves that room to real floor plus a connecting corridor — called by `RealmSim` only once a quest actually completes. "The quest completing" and "the room becoming physically enterable" are the *same event* — there's no separate door/key/switch object, the corridor's existence (or lack of it) IS the lock.
- `SECRET_QUEST_KINDS` is a small dict keyed by quest kind, each entry a plain data dict (`{"label": ..., "target": ...}` or a `time_limit`) — `_start_secret_quest()` dispatches per-kind setup once at instance creation (only if a `hidden_room` was actually reserved — no hidden room, no quest, since there'd be nothing to reveal), and `_progress_secret_quest()` is called from the exact same `_reward()` kill-processing choke point every other kill-triggered system (loot, XP, room-cleared bookkeeping) already runs through — no separate quest-kill-tracking code path.
- **`boss_timer` is checked separately** at the moment the tracked main boss actually dies (only counts as a completion if the timer hadn't already hit zero), and ticks down every simulation tick, explicitly failing the quest (a distinct `secret_quest_failed` flag, quest cleared, a feed announcement) if the timer runs out first — a genuine fail state, not just "the quest silently disappears."
- **A real correctness bug caught while wiring this, worth preserving as a lesson**: the existing "a boss died" bookkeeping unconditionally did `if enemy.rank == "boss": self.boss = None` — since the new secret "???" boss is *also* `rank == "boss"`, killing it would have incorrectly cleared the tracked MAIN boss reference even while the real boss was still alive, corrupting the "is the boss still alive" HUD indicator and incorrectly re-firing main-boss-only events. Fixed by guarding that specific bookkeeping with `enemy is self.boss` (identity check, not rank check) — any other boss-ranked kill (the secret boss, or a phase-2 variant, see part 4) takes a separate branch that still drops its own exit portal/announcement without touching the tracked main-boss reference.
- Totems: a genuinely stationary (`speed=0`), harmless (`neutral=True`, reuses the existing never-aggroes/harmless-contact enemy path), moderate-HP (`hp=60`) enemy kind — spawned into random *existing* fixed-pod rooms (`_spawn_totems()`), not new rooms of their own.

### Unity rebuild prompt

> Give a meaningful fraction (around 30%) of your dungeon instances a hidden shared-progress side-quest, rolled once at instance creation and only if a spare, reservable room slot exists to hold its reward. Implement at least 3 distinct quest-completion conditions sharing one small extensible data table and one shared kill-event choke point (don't build separate tracking code paths per quest kind): hunt a specific enemy type to a count, destroy a small number of stationary/harmless "totem" objects scattered through existing rooms, or defeat the main boss within a time limit (with a genuine, player-visible fail state if the timer expires, not a silent quest-disappears). Reserve the quest's reward room at generation time as existing-in-data but physically solid/unreachable, and make "carving it open" and "the quest completing" the exact same code path — no separate door/key object. When adding a secondary "boss-ranked" enemy anywhere in your game (a quest boss, a harder variant), audit every place your code currently assumes "a boss-ranked kill" means specifically "THE tracked main boss" — guard that bookkeeping by object identity, not by rank, or a secondary boss's death will silently corrupt your main boss-tracking state.

---

## 4. Boss second phase and the portal `kind` system (Batch 1 Sections F+G)

### What it is

Some dungeon bosses, on death, don't just drop a single "return to the Realm" portal — they can instead open a single portal into a reserved, harder "phase 2" encounter: a genuinely tougher variant of the same boss (more HP, more damage, faster fire rate — a real mechanical wrinkle, not just a palette swap) in its own separate room. Taking that portal is always optional. Separately, every `Portal` object in the game carries a `kind` tag (`entrance`/`realm_exit`/`phase2`/`dungeon_shard`/`ambient`) driving both its visual identity (see `05-art-vfx-pipeline.md`) and now, functionally, what happens when it's touched.

### Why/how it was chosen — including a real, user-driven mid-implementation revision

The FIRST implementation spawned **two** side-by-side portals at the boss's phase-1 death (a `realm_exit` and a separate `phase2` portal). The user reviewed this and asked for a change, quoted directly in memory: *"dont have the portal take you to another version of the portal"* and *"in the same portal"* — simplified afterward to exactly ONE portal appearing at phase-1 death (`kind="phase2"` if a pocket room was successfully reserved, else `kind="realm_exit"` if not) — phase 2 itself was not removed, just delivered through one portal choice instead of a side-by-side pair. This is a good example of the project's iterate-from-real-feedback pattern: ship the straightforward version, let the user react to how it actually feels, revise based on specific, quotable feedback rather than guessing preferences up front.

The SAME course-correction session also added two related changes, both explicitly driven by the user reviewing the first pass rather than being in the original plan:
1. **Portals became a deliberate action, not a walk-over trigger.** Standing on/near ANY `entities.Portal` (this does NOT apply to the older, separate Nexus/Bazaar/Vault tile-based zone transitions) now shows a "Press ENTER to enter" prompt instead of instantly teleporting the player — giving a moment to finish looting/positioning before committing to a zone change.
2. **Difficulty is pre-rolled and labeled on the portal** — see part 2 above; decided via an explicit multiple-choice question the user was asked directly, rather than assumed.

### Implementation detail (verified against current `game/entities.py:667-680` and `game/realm_sim.py`)

- `Portal.kind`: `"entrance" | "realm_exit" | "phase2" | "dungeon_shard" | "ambient"` — every `Portal(...)` construction site across the whole codebase passes the correct kind explicitly; a portal's kind has always been available to `net_state()`/co-op reconstruction, not client-side-only state.
- **Reserved pocket room**: like the hidden room in part 3, `make_bonus_room()` reserves a second extra room. Unlike the hidden room, this pocket's floor IS carved to real, walkable floor immediately at generation (the boss fight needs somewhere to actually happen) — but it is deliberately never corridor-connected to anything at generation time, so it's physically unreachable until the boss-death choreography (or, in current/later code, a quest-gated "door" — see this file's scope-boundary note) opens a path to it.
- **Boss-death choreography** (`RealmSim._reward()`): on the tracked main boss's phase-1 death, the entrance portal is always removed (a real, previously-unnoticed inconsistency with the plan's own "a boss room starts with exactly 1 portal" framing, fixed as part of this work). If a pocket room exists: a genuinely harder `f"{kind}_phase2"` `Enemy` spawns inside it, and `self.boss` is *re-pointed* at this new enemy — so its own eventual death falls through the identical final-death branch (single exit portal, achievement unlock) with zero duplicated logic, rather than a parallel "phase 2 death" code path.
- **Genuinely harder, not a reskin** (verified against current `game/entities.py:674-677`): `PHASE2_HP_MULT` (currently `1.75` — bumped up from an original `1.6`) AND `PHASE2_DMG_MULT` (currently `1.4` — bumped up from an original `1.3`), both by the SAME later difficulty-rework pass, confirming this is exactly the kind of number worth re-checking against live code rather than trusting a memory snapshot (an earlier draft of this doc caught the HP bump but missed that the damage multiplier was bumped alongside it - fixed after a direct line-by-line diff against current `game/entities.py`), plus a genuine mechanical wrinkle: `Enemy.fire_rate_mult` (`PHASE2_FIRE_RATE_MULT`, currently `0.6`, i.e. the phase-2 boss fires roughly 40% faster) — bigger numbers ALONE were explicitly judged insufficient for "a real second phase," a mechanical difference was required too.
- **A real balance bug caught and fixed while wiring this**: enemy-kind stat tables feed a one-time, module-load-time computation of each rank's difficulty range (used by `roll_loot`'s difficulty-nudge, see file `03`) — naively including the much-tankier phase-2 variants in the "boss" rank's own range computation would have silently *lowered* every ordinary (non-phase-2) boss's computed difficulty fraction, purely by the phase-2 variant existing in the same lookup table. Fixed by excluding `"_phase2"`-suffixed kinds from that ranking computation entirely, giving them a flat top-of-band score instead (see file `03`, part 2, for the general pattern this established). Phase-2 variants are also deliberately excluded from the game's normal random-boss-selection pool — they only ever come into existence via this specific choreography, never rolled as a dungeon's regular boss.

### Unity rebuild prompt

> Implement an optional boss "second phase" as: reserve a second special room at dungeon-generation time, carved to real walkable floor immediately but deliberately disconnected from the rest of the dungeon (solid walls on every side, no corridor). On the tracked main boss's death, if that room exists, spawn a noticeably harder variant of the same boss inside it (higher HP and damage multipliers PLUS at least one genuine mechanical change, such as a faster attack rate — never just bigger numbers) and re-point your "is the main boss still alive" tracking reference at this new enemy, so its eventual death reuses your existing boss-death logic rather than a parallel code path. Deliver access to this harder encounter through exactly ONE portal (not two side-by-side choices) — ship a working version, then be ready to simplify based on how it actually plays. Give every portal object in the game a `kind` tag that both a visual-identity system and gameplay logic key off of, and make every portal interaction an explicit player-confirmed action (a "press to enter" prompt on approach) rather than an automatic walk-over trigger, so players always get a moment to decide before a zone transition commits. When adding any new "harder variant" enemy kind to a difficulty-scoring system that other systems (like loot difficulty) already read from, explicitly exclude that variant from whatever ranking/normalization computation feeds those other systems, and give it a fixed top-of-range score instead — never let a new harder variant silently distort the computed difficulty of the enemies it now sits next to in the same data table.

---

## 5. The potion system: permanent stat potions + temporary draughts (Batch 1 Section K)

### What it is

Two parallel consumable-item families, both keyed on the same 6 core stats (`STAT_KEYS = ["att","deF","spd","dex","vit","wis"]`):
- **Permanent potions**: `+1` to one stat, forever, when drunk — capped at `PERMANENT_POTION_CAP` (20) total drinks per character, freely allocated across the 6 stats however the player likes.
- **Temporary draughts**: a much bigger (`TEMP_POTION_AMOUNT`, +6), non-permanent buff lasting `TEMP_POTION_DURATION` (60 seconds) — a completely separate item family/inventory slot, not counted against the permanent cap at all.

### Why/how it was chosen

Explicitly requested together with per-class leveling growth (file `02`, part 5) because the user judged the two "related and not complicated" and wanted them implemented in one combined pass — one of the few places in the project's history where a *scoping/grouping* decision (not just a feature ask) is directly attributed to the user's own words. The permanent cap is a deliberate anti-infinite-grinding design: potions are meant to be a real, finite, allocatable resource (a build choice — "put my 20 potions into ATT" vs. "spread them out"), not an unbounded numeric treadmill.

### Implementation detail (verified against current `game/items.py:621-657` and `game/entities.py:216-231`)

- `make_potion(stat_key)` and the separate `make_temp_potion(stat_key)` are both generalized from an original single-hardcoded-stat version into one-per-stat factories following the same pattern used everywhere else in the item system.
- `Player.potions_used` (a 6-entry counter dict) and `Player.temp_buffs` (`{stat: (amount, seconds_remaining)}`) are both serialized in `full_state()`/save-file/network round-trips — required for correctness, not a nice-to-have: without it, the permanent cap wouldn't survive a save/reload (a player could just log out and back in to reset their cap), and a co-op client's own displayed stats wouldn't reflect an active temp buff at all.
- `use_potion()` (`game/entities.py:216`): the `"consumable"` (permanent) branch checks `sum(potions_used.values()) >= PERMANENT_POTION_CAP` and, if capped, returns `False` **without consuming the item from the backpack** — a real, if minor, pre-existing gap is documented as fixed alongside this: `use_potion()`'s return value used to be silently ignored at its call sites, so a capped-out permanent potion drink previously showed the same generic "Used X" success message as an actual successful drink, with no indication anything had failed.
- `total_stat(key)` (file `02`, part 1) adds any active `temp_buffs` entry on top of gear/base stat — temp buffs are a pure additive layer over the permanent stat pipeline, never mutating the underlying base stat itself, which is exactly what makes them cleanly and automatically reversible when the timer expires.
- Both potion families now drop from mob kills at every enemy rank (see file `03`, part 2's `roll_loot` table), not exclusively from fishing as in an earlier version — "mobs also drop all kinds of potions," a deliberate widening of where this resource can come from.

### Unity rebuild prompt

> Implement two parallel consumable-item families sharing one set of core stat keys: a permanent-buff family (a small flat stat increase, consumed once, capped at a fixed total lifetime-uses-per-character count freely allocated across whichever stats the player chooses) and a separate temporary-buff family (a much larger but non-permanent, time-limited buff, tracked completely independently and never counted against the permanent cap). Store both the permanent-use counter and any active temporary buffs (amount + remaining duration) as part of your player's persisted save state and your multiplayer state-sync payload — a buff that doesn't survive a reload or isn't visible to other systems reading a player's current stats is a real correctness bug, not a minor gap. When a consumption attempt fails validation (cap reached), make sure the calling code actually checks and surfaces that failure to the player with a distinct message — never let a failed consumption silently show the same success feedback as a real one, and never destroy the consumed item on a failed attempt. Compute a player's effective/total stat value as base stat + equipped-gear bonuses + any active temporary buff, as a pure additive read at query time, never by mutating the underlying base stat — that's what makes a temporary buff cleanly and automatically reversible the instant its timer expires.
