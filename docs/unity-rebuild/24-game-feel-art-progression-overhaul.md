# Batches 12-13: Game-Feel/Juice Research Pass, Character/Mob Art & Animation, Progression & Fishing Overhaul

## Context

Two linked batches, both explicitly research-driven rather than starting
from a fixed feature list.

**Batch 12** began with "rethink all the game and search online for
techniques to improve the game feels and gameplay and graphics" - real web
research (screen-shake/hit-stop/particle "juice," bullet-hell polish
conventions, ROTMG's own 2025-2026 public dev priorities, roguelite
meta-progression, procedural-terrain/vegetation realism, 2D lighting,
co-op retention mechanics, input-forgiveness techniques) produced 10
design ideas + 10 features, which collapsed into 15 concrete engineering
tracks after checking each against what the game already had (several
"ideas" turned out to already exist correctly - see the per-track notes
below). The user asked for maximum fork parallelism ("try using multiple
agents forks for everything... still look in depth for everything"),
so all 15 tracks (paired down to genuinely-small ones, split up the
substantial ones) ran as 13 parallel git-worktree forks.

**Batch 13** followed immediately ("search for character design and
remodeling things that are too simple... fork their creation per mob...
update stats... make fishing give much more things... an animation for
it"). Three more read-only research forks (pixel-art/animation technique
research, a factual catalog of every sprite's complexity/animation state,
a factual read of the stat-growth and fishing code) fed a second plan.
**A key correction happened here before any code was touched**: the
sprite-catalog fork read only the *procedural* generation code in
`sprites.py` and concluded most enemies/bosses were heavily-reused
placeholders - but a `Glob` check of the actual shipped `assets/sprites/
v0.2/` PNGs showed real bespoke hand-painted art already existed for
every player class, the 14 base enemy shapes, the 10 signature per-biome
mobs, and all 6 bosses + their phase-2 art (that art was added in an
earlier, unrelated session batch; the procedural code is a fallback path
that was never removed and still has stale comments describing it as a
placeholder). The genuine gap was narrower: 26 mob kinds (6 neutral
wildlife + 20 "Reforging" island guardians) that still fell back to
reused procedural shapes with no bespoke art at all, plus a universal
"zero enemies of any kind animate" gap that was orthogonal to art
quality entirely. That correction reshaped the batch from "redesign
everything" to "redesign these 26, animate all 63."

**Process notes worth their own callout:**

- **Two-wave fork workflow, not one**: Batch 12's 13 forks were fully
  integrated and verified (25/25 tests) BEFORE Batch 13's 8 forks were
  even launched, deliberately - both batches touch the same hot files
  (`entities.py`, `realm_sim.py`, `items.py`, `main.py`, `coop_client.py`),
  and running two waves of unrelated edits to the same files concurrently
  would have made integration effectively unsolvable. Batch 13's forks
  were told explicitly that their worktrees would NOT see Batch 12's
  (by-then-integrated) changes - forks always branch from the last real
  git commit, never from another session's uncommitted working-tree
  changes - so every Batch 13 fork's contribution to a Batch-12-touched
  file needed hand-merging during integration, not a clean `git apply`.
  This was expected going in, not a surprise.
- **Session interruptions mid-batch**: partway through Batch 13's first
  launch, most of the 8 forks hit a session rate limit and 2 more were
  cut off by a session restart. All were resumable - `SendMessage` to
  each fork's agent ID with "continue from where you left off" picked
  back up from real partial progress already written into each fork's
  worktree (confirmed via a fresh `git diff` before resuming, not assumed).
  The 3 forks that failed before ever creating a worktree were relaunched
  from scratch instead, since there was nothing to resume.
- **Integration discipline held across 21 total forks**: every fork's
  diff was integrated one file at a time, in ascending order of how many
  forks touched that file (single-owner files first, `main.py`/
  `coop_client.py` last), recompiling and rerunning the full check suite
  after each single fork's contribution - never batching several forks'
  patches before testing. Across all 21 forks (13 + 8), not one produced
  a genuine logic conflict with another - every hand-merge was purely
  import-line or insertion-point context shifting, never two forks
  editing the same semantic thing differently. Final result: 33 total
  regression check scripts, all green, including a dedicated overlapping-
  text/HUD-collision pass (this project has hit that exact bug class
  before - Batch 10's island-hub portal labels) covering every new
  on-screen text surface this batch added.

## Batch 12 tracks

### 1. Juice trio: hit-stop + screen-shake + impact particles

**What/why**: screen-shake already existed (`vfx.trigger_shake`) but was
only wired to two effects; hit-stop (a brief freeze on impact) didn't
exist anywhere. Research consistently flags this exact combination as
the cheapest, highest-impact game-feel change available.

**How**: `vfx.trigger_hitstop(ms)`/`apply_hitstop(dt) -> dt` uses a
wall-clock timer (not scaled by the `dt` it modifies, so it can't hang).
Called once per frame in both `main.py` and `coop_client.py` right after
computing raw `dt`. Safe in co-op because the client never runs the
authoritative sim - freezing its local `dt` only pauses local rendering/
animation smoothing, never the server tick; in single-player it also
briefly pauses the real sim, which is the intended effect and isn't
networked. Two new vfx_event kinds (`hit_enemy`/`hit_player`, boss-aware)
emitted from the three real hit call sites in `realm_sim.py`, each
triggering a scaled particle burst + shake + hitstop in `vfx.dispatch()`.

### 2. Echo currency for permadeath

**What/why**: soften permadeath (Hades-style meta-currency) without
trivializing runs - never raw combat power.

**How**: `game/accounts.py` gained an `echoes` int field (same
atomic-tmp-then-replace save pattern `friends.py` already used) and an
`unlocks` dict. A new Nexus "Echo Keeper" tile (reusing the existing
Vault/Bazaar F-key interaction pattern) opens a small shop overlay
offering fixed, permanent, power-neutral unlocks: +1 backpack slot
(persisted through `full_state()`/`from_full_state()` - a real bug was
caught and fixed here, since without persisting `backpack_size` a
purchased slot would silently vanish on next load) and a small
starting-XP boost (tuned down from an initial 200 to 10 XP after
verifying 200 would have leveled a fresh character ~5 times, violating
the power-neutral constraint).

### 3. Roaming World Boss incursion

**What/why**: a rare, server-wide event drawing scattered co-op players
together, mirroring WoW/Black Desert-style world events.

**How**: `RealmSim._tick_world_boss(dt)`, mirroring the existing
island-event-timer pattern. On a randomized 15-25 minute cooldown, spawns
one of the 6 existing boss kinds (tagged `is_world_boss`, ~2.4x base HP
scale - tougher than the every-40-kill boss) at a point far from any
spawn, broadcasts via the same `(pid=None, msg, color)` announcement
convention already used for Blood Moon/Mad God Avatar events. Reuses the
generic `Enemy` HP-bar draw code with zero new rendering.

### 4-5. Tactical weather + difficulty signpost

**What/why**: give two of the four weather kinds one real gameplay hook
(not just cosmetics), and let dungeon shard portals show a suggested
level, echoing ROTMG's own 2025 "Combat Power" rework.

**How**: the existing `mm.reveal(p.pos)` fog-of-war calls already
accepted an optional radius - a smaller radius is passed when the
player's current-tile weather is `"snow"`. `auto_aim_direction`'s
`cone_deg` keyword is narrowed when weather is `"sand"`. Both are
small, per-biome, surgical changes. `PORTAL_DIFFICULTY_SUGGESTED_LEVEL`
maps Easy/Medium/Hard to "Lv 1+"/"Lv 8+"/"Lv 15+", appended to the
existing color-coded portal label.

### 6. UT "socket" system

**What/why**: UT mechanics (boomerang motion, bleed/burn/vulnerable DoTs)
were resolved by exact item-NAME lookup against 4 hardcoded dicts in
`player_fire` - `Item.proc` was flavor text only, never mechanical.

**How**: new `Item.socketed_proc` field + `identify_proc_kind(item)`
helper resolving which of the 4 name-sets a UT belongs to. A backpack
interaction consumes a spare UT onto a different weapon, setting
`target.socketed_proc`; `player_fire` checks this field FIRST, falling
back to the original name-based lookup for never-resocketed natives - a
socketed weapon behaves identically downstream to a native one. One
weapon holds one socket at a time; re-socketing overwrites.

### 7. Clustered biome-prop placement

**What/why**: the sparse whole-map decoration pass sampled every prop's
position fully independently and uniformly - real vegetation clusters
(a finding straight from the terrain-generation research).

**How**: replaced the independent-per-tile loop with a seed-and-spread
pass - pick `~count/6` cluster centers on land, scatter each cluster's
share with a `random()**1.5` radius bias (denser near center). Verified
with a real Clark-Evans nearest-neighbor statistic: ~0.28 (strongly
clustered) vs. ~1.0-1.03 for an empirical uniform-random control on the
same land mask, at unchanged total prop count (1650) and realm-gen time
(~2.1s).

### 8. Lightweight Crew system

**What/why**: a low-cost co-op retention lever - far short of a full
guild system.

**How**: new `game/crews.py` mirrors `friends.py`'s exact atomic-save
JSON pattern (`crews/<name>.json` + a `crews/_members.json` reverse
index). `/crew create|join|leave` chat commands (matching the existing
`/nexus`/`/trade` slash-command convention), a crew tag shown in the
peer hover tooltip, `increment_boss_kills` hooked into boss-death
finalization. Co-op-client-only, like `friends.py` - single-player has
no concept of other players. Known limitation: crew tags resolve
correctly only when peers share local `crews/` data (same trust model as
friends) - a real cross-machine crew tag needs a server-side protocol
field, out of scope here.

### 9. Host-settable rotating live events

**What/why**: give a small friend-group server a reason to return
without building real live-ops infrastructure.

**How**: `game/live_events.py` resolves `ACTIVE_EVENT` from an
`RR_EVENT` environment variable at import time, with a small dict of
named events -> multipliers (`double_loot`: doubles the loot-roll count
via a real second independent roll, not inflated per-item odds past
1.0; `blood_moon_week`: raises the Blood Moon base chance). Both
`main.py` and `server.py` import it identically - no duplicated
`argparse` wiring. `roll_loot`/blood-moon chance only ever run inside
`RealmSim` (owned by `main.py`/`server.py`), so `coop_client.py` only
needs to read `active_label()` for its Nexus banner display, confirmed
by tracing the actual call graph rather than assumed.

### 10. Discoverable landmarks

**What/why**: answer the "big procedural world feels empty between
points of interest" critique from the terrain research - the continent
is 900x900 tiles now, exploring it should be motivated beyond grinding
lairs.

**How**: one hand-placed POI per biome (10 total), stamped during the
existing biome-buildings pass (reusing its `placed_rects` overlap-
avoidance list), each a small prop cluster + a fixed lore string. A
per-player, SESSION-ONLY (not persisted - matching "exploration reward
doesn't need to survive permadeath") proximity check fires a one-time
feed message + guaranteed small loot bag on first approach.

### 11. Per-source night lightmap

**What/why**: replace the flat full-screen darken overlay with real
localized light.

**How**: `draw_day_night_overlay` keeps the same dark base fill (and
Blood Moon tint) but now blits a single pre-baked, radius-cached radial-
gradient sprite with `BLEND_RGBA_SUB` at the player's position and any
nearby torch tiles (`world.nearby_torch_world_positions()`, wired in by
the integration pass since the implementing fork's file scope didn't
include `main.py`/`coop_client.py`). Measured faster than the old flat
fill (~2.02ms vs. ~2.13ms/frame), not slower - the cached-sprite-per-
radius approach pays its build cost once per process lifetime.

### 12. Ranged-mob attack telegraph + buffered fire input

**What/why**: readability parity with the existing boss telegraph system,
and eliminate "I clicked but nothing happened" near a cooldown edge.

**How**: ranged enemies get a brief additive rim-light glow in the last
~0.2s before their existing fire-cooldown reaches 0 (pure visual read of
`_fire_cd`, changes zero damage timing - deliberately NOT a wind-up
state-machine restructure of instant melee contact damage, which would
have been a real combat-balance change out of proportion for a
readability feature). A ~100ms input buffer on firing: an early click
while `can_fire()` is still false starts/refreshes a short timer;
firing happens automatically the instant cooldown clears while the
buffer is live. Co-op's buffer lives server-side only (`server.py`),
since firing there is already server-authoritative - `coop_client.py`
only ever sends a raw fire-intent bool.

### 13. Universal dash/roll with i-frames

**What/why**: the one bullet-hell genre staple this game was missing.

**How**: new `Player` fields (`_dash_cd`/`_dash_time`/`_dash_vec`/
`_dash_iframes`) mirroring the existing `ability_cd` cooldown-gate
pattern, all inside `Player.net_update()` (the single function this
codebase already shares between single-player and co-op, per its own
architecture convention - the same reason Batch 11's walk-cycle
animation lived there). `take_damage()` short-circuits to 0 while
`_dash_iframes > 0`. Movement still passes through the existing
`_circle_clear` wall-collision check. Tuned to a 0.18s/~2.5-tile burst
on a 2s cooldown (measured: 81.5px covered vs. 34.4px for normal walking
over the same window) - a real burst, not a teleport. Bound to Left
Shift (confirmed unbound). Co-op needed one small hand-written connector
in `server.py` reading the client's `dash` input flag and calling
`try_dash()`, since the implementing fork's scope didn't include
`server.py`.

### 14. Bullet/particle pooling - measured, not built

**What/why**: house style (established by the 900x900 map-size decision)
is "benchmark before optimizing," and research found no pooling exists
but also no evidence of an actual measured problem.

**How**: a real stress benchmark (`tests/check_bullet_particle_perf.py`)
simulates ~220 aggro'd ranged enemies / ~350 bullets in flight / 6
players and measures `RealmSim.update`'s real CPU time via
`time.process_time()` (switched from wall-clock after wall-clock proved
flaky under this session's own heavy parallel-fork CPU contention).
Result: ~10-13ms/tick, comfortably under the ~23.3ms budget derived from
the documented 30Hz co-op tick rate. No pooling was added - the
benchmark itself is now a permanent regression guard.

## Batch 13 tracks

### P. Universal enemy idle/walk/attack animation

**What/why**: every enemy kind, regardless of art quality, had zero
draw-time animation - a static blit plus tint overlays only. Likely the
single highest-impact "simple -> polished" change available per the
animation research, since idle/walk motion reads as polish even on
identical art.

**How**: `Enemy` already had a `self._t` accumulator (used only for boss
bullet-pattern math and the moonlit pulse) - the new animation instead
uses the wall clock (`pygame.time.get_ticks()`), matching Player's
existing Batch-11 animation and letting a co-op `GhostEnemy` (which
reuses `Enemy.draw` as a class attribute but never runs `update()`)
degrade gracefully to idle-sway via `getattr(..., default)` reads rather
than crashing. New `_is_moving`/`_move_dir` fields are set explicitly at
every movement branch (idle wander is deliberately excluded - it drifts
position slightly as "liveness" but should read as idle-sway, not a
walk-cycle; encoding this at each branch is simpler and more robust than
inferring it from a position-delta threshold). A brief squash-and-stretch
anticipation pose plays via `_fire_pose_t`, set the instant an enemy
actually fires. Integration merged this directly into `Enemy.draw()`
alongside Batch 12's pre-fire telegraph glow - both now coexist in the
same method (glow reads `_pretelegraph`, animation reads `_is_moving`/
`_fire_pose_t`, neither interferes with the other).

### Q1-Q5. Mob redesign, by body-plan archetype

**What/why**: 26 mob kinds (6 neutral wildlife, 20 "Reforging" island
guardians) had no bespoke art at all and silently reused an unrelated
existing shape with just a new palette - confirmed by an asset `Glob`
check finding zero matching PNGs, not assumed from code alone. A "deer"
was a recolored yeti; a "songbird" was a recolored bat.

**How**: rather than 26 fully bespoke hand-authored ASCII grids, or a
literal one-fork-per-mob split, the batch used the pixel-art research's
own recommendation - a small library of parametrized body-plan
archetype functions, varied by proportion/palette/appendage per mob -
split across 5 forks by rough shared archetype:
- **Q1** (ember_wisp, fury_shard, spite_spirit, tide_wisp, cave_moth):
  three archetype generators (`_wisp_grid`, `_shard_grid`, `_moth_grid`)
  - a moth doesn't fit a wisp-blob shape, so it got its own generator
  rather than being force-fit.
- **Q2** (songbird, marsh_heron, siren_wraith, abyssal_chorister,
  choir_warden): two sub-families, a perching/wading-bird archetype and
  a robed ethereal-singer archetype, sharing key conventions within each
  family but not across them.
- **Q3** (deer, forest_hare, desert_lizard, brine_crawler,
  rubble_crawler): one quadruped "chassis" (4-leg and 6-leg-crawler
  stances) with a distinguishing head-topper feature slot (antlers/ears/
  frill/shell-spikes) per mob - the deer-vs-yeti regression is directly
  tested by name.
- **Q4** (echo_knight, shard_sentinel, stone_revenant, cinder_warden,
  pearl_acolyte): one humanoid-guardian template (peaked head, torso
  with one distinct "regalia" accent, tapered legs/hem) varied by accent
  placement and proportions.
- **Q5** (shattered_golem, fracture_hound, coral_sentinel,
  drowned_custodian, kelp_stalker, shellback_guardian): two archetype-
  assembly functions, `_construct_body` (blocky/chunky/armored) and
  `_lowslung_body` (elongated, forward head, trailing spine/tail).

Every one of the 26 is verified pixel-distinct from the others and from
all 14 pre-existing base shapes via a real pixel-diff test per fork
(not just "it rendered without crashing"). Integration merged all 5
forks' `ENEMY_GRIDS` dict entries and new grid/palette constants into
`game/sprites.py` sequentially, verifying the dict stayed at 63 total
kinds with 26 confirmed-unique target grids after each merge.

### R. Goofy fishing items

**What/why**: the fishing loot table's 45%-of-all-catches "junk" tier
was a plain stat potion - zero humor, a wasted opportunity on the most
common outcome.

**How**: new item factories in `game/items.py` - an Old Boot (+1 DEF),
a Rubber Duck Ring (+1 WIS, squeaks on fire), a Cursed Ring of Buyer's
Remorse (+2 ATT/-2 DEF, a REAL mechanical tradeoff, not just flavor
text), a Tangled Fishing Net (a genuinely weak 1-2 damage "weapon"), a
Waterlogged Sandwich (+1 VIT), and a Sentient Fish Egg (a real hatchable
pet). A plain stat potion stays in the weighted pool too, so junk isn't
always a joke.

### S. Fishing animation

**What/why**: casting and the bite window were 100% invisible - the only
visual feedback anywhere was a particle burst on the rare 5% jackpot tier.

**How**: `RealmSim._find_fishing_bobber_pos` locates the nearest real
water tile within fishing range for the bobber's world position, stored
in `player.fishing_state["bobber"]`. New vfx event kinds (`fish_cast`,
`fish_bite`, `fish_splash`) fire at the right moments in the existing
cast/bite/catch state machine - `fish_splash` now fires on every catch
tier, not just the rare one. `vfx.draw_fishing_bobber` renders a line
from the player to the bobber plus an idle `sin(t)` bob, switching to a
sharp dip + red exclamation mark once the bite window opens.
`fishing_state` was added to `Player.full_state()`/`net_state()` (and
their reconstructors) so co-op peers render each other's bobbers
correctly from network snapshots, not just the local player.

## Verification & integration process

Same bar as every prior batch, at larger scale: `python -m py_compile`
across every touched file, `import main, coop_client, game.realm_sim,
server` after every merge step, and the full `tests/run_all_checks.py`
suite re-run after each SINGLE fork's contribution to each file was
integrated - never batching. Final count: 33 regression check scripts
(12 pre-existing + 13 from Batch 12 + 8 from Batch 13), all green, plus
a dedicated extension to `tests/check_hud_and_overlap.py` specifically
covering every new on-screen text surface this batch introduced (the
longer difficulty+level portal label at real dense island-hub spacing,
the live-event Nexus banner against the hint text, the peer tooltip's
new crew-tag line growing the box correctly, the Echo Keeper shop modal
against the corner-anchored day/night clock) - all confirmed non-
overlapping via real rendered-rect collision checks, not eyeballing.
A real in-game visual pass (`SDL_VIDEODRIVER=dummy` + `pygame.image.
save()`) confirmed the 26 redesigned sprites render as genuinely
distinct shapes and the fishing bobber's casting/biting states are
visually distinguishable.
