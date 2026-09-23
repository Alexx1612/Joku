# 01 — Core Architecture

Scope: the foundational engineering shape of the game — how single-player and co-op share one simulation, how the game loop is organized, and the networking model. This is "Batch 1" territory: the load-bearing structure everything else in this document set stacks on top of.

---

## 1. The shared-simulation split: `main.py` / `server.py` / `coop_client.py` / `RealmSim`

### What it is

The game ships two ways to play from one codebase:
- **Single-player**: `main.py` runs a `Game` object that owns a pygame window, reads local input, and drives a `RealmSim` instance directly, in-process.
- **Co-op**: `server.py` runs a headless `ServerState` that owns one or more `RealmSim` instances (one per active zone-instance: the Realm, each bonus dungeon, etc.) and drives them on a fixed tick; any number of `coop_client.py` processes connect over TCP, send input, and render whatever snapshot the server broadcasts.

The critical design decision is that **`game/realm_sim.py`'s `RealmSim` class contains ALL of the actual game logic** — enemy AI, aggro/leash, loot rolls, boss triggers, ability resolution, dungeon quest tracking, day/night, fishing, everything that "the game" actually *is* — and neither `main.py` nor `server.py` reimplements any of it. `RealmSim` "knows nothing about pygame input or rendering" (its own docstring, `game/realm_sim.py:9`): it's fed a `dict[pid -> Player]` each tick, mutates world state, and produces event lists (`self.events`, `self.vfx_events`, `self.damage_popups`) that a caller — either `main.py`'s draw loop or `server.py`'s snapshot builder — consumes to actually show something.

`main.py` is not "single-player code duplicating what the server does" — it is a *thin* wrapper: it holds one `RealmSim`, feeds it the one local player, calls the same `RealmSim` methods (`player_fire`, `use_ability`, `update`) the server calls, and draws the result directly (no serialization round-trip needed since there's no network in single-player). `coop_client.py` is drawing a *reconstruction* of remote state from JSON snapshots (via lightweight `Ghost*` mirror classes — `GhostBullet`, `GhostPortal`, `GhostObstacle`, etc. — that often literally reuse the real class's own `.draw()` method, e.g. `GhostObstacle.draw = Obstacle.draw`, so a single class's rendering code serves both the authoritative in-process object and the network-reconstructed one).

### Why/how it was chosen

This is the project's own explicit, load-bearing design principle, stated directly in `realm_sim.py`'s module docstring: *"Keeping the enemy AI / loot / boss-trigger / mob-portal logic in exactly one place means co-op and single-player can never silently drift apart into two different games."* The memory record doesn't attribute this to a specific user request — it reads as an architectural decision made early and never revisited, which is itself telling: every subsequent feature (bosses, quests, potions, abilities) was built as "add a branch to `RealmSim`, wire the two thin callers to call it," never as parallel single-player/co-op implementations. The master tracking file's own testing discipline enforces this: virtually every section's "verified" note explicitly checks *both* a direct `RealmSim` call chain *and* the real `server.ServerState()`/`server.step()`/`server._apply_action()` chain, treating a feature as unverified until both paths are exercised.

### Implementation detail

- **`main.py`** (`class Game`, `main.py:64`): a single `Game` object owns a state machine —
  ```python
  (STATE_INTRO, STATE_NAME_ENTRY, STATE_CLASS_SELECT, STATE_NEXUS, STATE_REALM, STATE_BONUS,
   STATE_BAZAAR, STATE_VAULT_ROOM, STATE_VAULT, STATE_DEAD) = range(10)   # main.py:45-46
  ```
  Each state has its own update/draw branch. `STATE_REALM`/`STATE_BONUS` are the two states that actually run a `RealmSim` (`self.realm_sim` / `self.bonus_sim`); Nexus/Bazaar/Vault-room are separate, simpler tile-map states with no combat simulation. The 60 FPS main loop calls `Game.update(dt)` then `Game.draw()` every frame; `update()` dispatches on `self.state`.

- **`server.py`**: headless — no pygame window, `SDL_VIDEODRIVER=dummy` under the hood where needed for any pygame-dependent math (e.g. `pygame.Vector2`). Zone constants mirror `main.py`'s states:
  ```python
  ZONE_NEXUS, ZONE_BAZAAR, ZONE_VAULT_ROOM, ZONE_REALM, ZONE_BONUS, ZONE_DEAD = (...)   # server.py:39
  ```
  `class Session` (`server.py:43`) is one connected player's server-side state (which zone they're in, their `Player` object, their pending action queue). `class ServerState` (`server.py:109`) owns the actual `RealmSim` instance(s) — critically, **co-op supports multiple concurrent dungeon instances** (a later-batch addition, out of this document's scope, but the *architectural* hook for it — one `RealmSim` per zone-instance rather than one global `RealmSim` — is exactly why that extension was possible without a rewrite). `def step(state, dt)` (`server.py:243`) is the server's fixed-tick update: it calls into each active `RealmSim.update()`, processes each `Session`'s queued actions via `_apply_action()`, and rebuilds each connected client's snapshot.
  - Tick rate: `NET_TICK_HZ = 30` (`game/constants.py:18`) — the server simulates at 30Hz while clients render at 60 FPS, a real (if small) source of co-op input latency (documented in the project's own "Known limitations": "No client-side movement prediction... co-op has ~1 tick + network latency of input lag").

- **`coop_client.py`**: connects over plain TCP, sends input as JSON actions (`{"action": "equip", ...}`, `{"action": "enter_portal"}`, etc. — the *same* action names/shapes `server.py`'s `_apply_action()` dispatches on), receives a JSON snapshot every server tick, and reconstructs local mirror objects to draw. Movement is **client-trusted**: the client computes its own intended movement and sends a direction vector; the server does not independently validate it against a movement-speed cap (explicitly documented as a real limitation, not an oversight — "fine for playing with friends, not hardened against cheating").

- **Networking framing** (`game/netmsg.py`): newline-delimited JSON over a raw TCP socket, shared by both `server.py` and `coop_client.py` — each message is one JSON object, sent as `json.dumps(msg) + "\n"`, read by buffering until a `\n` is seen. No length-prefixing, no binary framing, no encryption/auth (again, documented as an explicit, accepted limitation for a "share with friends you trust" co-op mode).

### Unity rebuild prompt

> Build the simulation core as a single, engine-agnostic C# class (e.g. `RealmSim`) that owns ALL gameplay mutation — enemy AI/state, loot rolls, boss/quest triggers, ability resolution — and exposes only: (1) a per-tick `Update(float dt, Dictionary<string, PlayerState> players)` method, and (2) plain-data event queues (a list of feed-text events, a list of "vfx" events as `(kind, x, y, color)` tuples, a list of floating damage-number events) that get cleared and repopulated every tick. This class must have ZERO references to Unity's rendering, input, or networking APIs — no `MonoBehaviour`, no `Update()` callback tied to a GameObject, no direct scene manipulation. Then build exactly two thin callers: a single-player `GameController` (a MonoBehaviour that owns one `RealmSim` in-process, feeds it local input every frame, and reads its Transform/sprite updates directly from `RealmSim`'s live objects) and a co-op pair — a headless dedicated-server process running `RealmSim` on a fixed tick (e.g. 30Hz via a manual timer, not Unity's frame-locked `Update`) that serializes its public state to JSON/a binary format each tick, and a client that deserializes that snapshot into lightweight "ghost" representations for rendering only, sending its own input back as small action messages over a raw socket (or Unity Netcode's transport layer if preferred, but keep the wire messages equivalent to plain JSON actions like `{"action":"fire","dir":...}`). The single hard invariant to preserve: single-player and co-op must never contain two different copies of game logic — if you ever find yourself writing "how enemies aggro" in two places, stop and refactor back into the shared `RealmSim`.

---

## 2. Zone / instance model

### What it is

The game world is not one continuous scene — it's a small fixed set of *zone kinds* (Nexus hub, Bazaar, Vault room, open Realm, Bonus/dungeon room), where the Realm and each Bonus room are procedurally regenerated fresh **instances** (a new `RealmSim` + freshly generated tilemap) rather than a persistent shared world. Nexus/Bazaar/Vault are simpler, fixed, non-simulated tile maps (no `RealmSim` needed — no enemies, no combat) that exist mainly as hub/social/storage spaces.

### Why/how it was chosen

This mirrors real RotMG's own "Nexus is one static hub, the Realm is a big shared instance, dungeons are private instances" structure — an explicit design goal from the project's start (see the README's framing: "a top-down bullet-hell MMO-lite... inspired by Realm of the Mad God"). No single memory entry records an explicit user quote choosing this over, say, one persistent open world, but it's implicit in every subsequent feature request being phrased in terms of "the Nexus," "the Realm," "a bonus room" as pre-existing, distinct concepts from very early in the project's history.

### Implementation detail

- Nexus/Bazaar/Vault-room generation lives in `game/world.py` (`make_nexus()`, `make_bazaar()`, `make_vault_room()` — the latter covered in file `03-items-loot-vault.md`).
- The open Realm is generated by `world.make_realm()` — a large procedurally-warped continent (out of this foundational document's scope in its later-batch specifics like biome landmark buildings, but the base generation — coastline warp, Voronoi-style biome regions, per-biome ecosystem lair placement — is foundational Batch 1/pre-Batch-1 work).
- A Bonus room (dungeon instance) is generated by `world.make_bonus_room(theme_name, floor_tile, wall_tile)` — see `04-dungeons-bosses-quests-abilities-potions.md` for full detail; the key architectural point here is that **each bonus-room entry creates a brand new `RealmSim`**, so a dungeon's enemies/state have no relationship to the open Realm's — walking back out and back in again gets you a fresh instance, not the same one resumed.
- Co-op's later extension to multiple *concurrent* dungeon instances (different parties in different bonus rooms simultaneously) is out of this document's scope, but only exists because `ServerState` was already structured as "a dict of active `RealmSim`s keyed by instance," not a single global one — a direct payoff of the shared-core architecture in section 1.

### Unity rebuild prompt

> Model the world as a small enum of zone *kinds* (Hub, Market, Storage, OpenWorld, Instance) where OpenWorld and Instance zones are backed by a freshly-generated simulation object on entry (a new procedurally generated level/scene-data plus a new instance of your `RealmSim` equivalent), while Hub/Market/Storage are simple static scenes with no combat simulation attached. Entering an Instance-kind zone (a dungeon) must always construct a brand-new simulation instance, never resume; support multiple concurrent Instance-kind simulations running in parallel on the server (e.g. a `Dictionary<InstanceId, RealmSim>`) from day one, even in single-player, so the co-op case (many parties in many different dungeons at once) is a natural extension rather than a later refactor.

---

## 3. The single-player game loop in detail

### What it is

`Game.update(dt)` / `Game.draw()`, called once per frame at (up to) 60 FPS via pygame's own clock. Per-state update branches handle: menu/name-entry input, class selection, Nexus/Bazaar idle wandering + NPC interactions, and the two "live simulation" states (Realm, Bonus) which additionally step the owned `RealmSim`.

### Implementation detail

Representative per-tick responsibilities inside the Realm/Bonus branch of `Game.update()`:
1. Read local keyboard/mouse state, translate to a movement vector and aim direction (with camera-rotation compensation — see `Player.update()`'s `cam_angle` param, `game/entities.py:280`).
2. Call `self.player.update(dt, keys, world_bounds, is_solid=..., speed_mult_fn=..., cam_angle=...)` — local player movement + regen tick.
3. Call `self.realm_sim.update(dt)` (or the bonus-room equivalent) — everything else (enemy AI, bullet resolution, loot, quest progress).
4. Handle firing (`realm_sim.player_fire(...)`) and ability casts (`realm_sim.use_ability(...)`) on the relevant input edges.
5. Drain `sim.events`/`sim.vfx_events`/`sim.damage_popups` into the local feed/VFX/floating-text systems.
6. Advance camera (`self.cam.follow(p.pos)`), apply any active screen-shake offset.
7. Check level-up/death/portal-prompt/quest-complete transitions and change `self.state` accordingly.

`Game.draw()` mirrors this: draw the tilemap (with fog-of-war if in a bonus room), draw entities/bullets/bags/portals/obstacles, draw the local player, draw VFX, draw the HUD.

### Unity rebuild prompt

> Implement your single-player controller's per-frame update as a strict pipeline: (1) sample input, (2) advance the local player's own movement/regen state, (3) advance the shared simulation by `Time.deltaTime`, (4) issue any fire/ability actions the input edge-triggered this frame directly into the simulation, (5) drain the simulation's event queues into your VFX/floating-text/camera-shake systems, (6) update the camera, (7) check for state transitions (level-up, death, a portal prompt becoming available, a quest completing) and switch scenes/UI mode accordingly. Keep rendering entirely separate from this update pass — a render pass should only ever *read* the simulation's current state, never mutate it.

---

## 4. Formulas module as the single source of truth

### What it is

`game/constants.py` holds every core numeric formula as a small, pure, independently-testable function — no class/entity ties to it directly; `Player`/`Enemy` call into it. This keeps every place that computes damage, speed, or regen mathematically identical, rather than each entity type reimplementing its own version.

### Why/how it was chosen

The module's own docstring states these are "the real Realm of the Mad God (Exalt) formulas, reproduced from public wiki documentation" — an explicit design goal (not a user request captured verbatim in memory, but stated as fact in the code itself and reinforced by the README: "every gameplay number comes from formulas published on the RotMG wiki, re-derived independently"). Later balance passes (e.g. enemy HP/damage scaling, ability magnitude bumps) are explicitly flagged in memory as *not* wiki-grounded and are called out honestly as "tuned by feel" rather than misattributed to the wiki — a documented project norm worth preserving: **be honest in comments/docs about which numbers are reproduced-from-source vs. tuned-by-feel**.

### Implementation detail (verified against current `game/constants.py`)

```python
DMG   = random(min,max) * (ATT + 25) / 50
DEF   reduces incoming damage 1:1, floor is 10% of the roll getting through (player); per-rank floor for enemies
SPD   tiles/sec = 5.6 * (SPD + 53.5) / 75
DEX   attacks/sec = 6.5 * (DEX + 17.3) / 75
VIT   HP regen/sec = 0.2407 * (VIT + 8.3)
WIS   MP regen/sec = 0.12 * (WIS + 4.2)
```
- `damage_roll(min_dmg, max_dmg, att)` → `round(random.randint(min_dmg,max_dmg) * (att+25)/50)`, floored at 1.
- `apply_defense(damage, deF, floor_frac=0.1, whole=True)` → `max(damage - deF, damage * floor_frac)`, rounded to an integer minimum of 1 *unless* `whole=False` — the `whole=False` escape hatch exists specifically for continuous damage-over-time ticks (bleed/burn), where forcing "at least 1 whole point of damage" on every single per-frame fractional tick would silently multiply a DoT's real damage-per-second by however many ticks per second it's evaluated at.
- `xp_to_next(level)` → `int(5 * level**1.7 + 8)` — an explicitly steepened curve, "tuned ~4x faster than the v0 curve so a level 1-20 co-op run is a single evening, not a grind."
- Enemies do NOT use the player's flat `floor_frac=0.1` — they use a **per-rank** floor (`ENEMY_DEFENSE_FLOOR = {"trash": 0.12, "elite": 0.15, "boss": 0.2}`, `game/entities.py:660`) so a boss's damage can never be trivialized as much as a trash mob's can, and a flat, roster-wide `ENEMY_DMG_MULT` (currently `1.22`) is applied once at module-load time to every `ENEMY_KINDS` entry's damage range — a single tunable knob for "the whole roster hits harder," rather than 30 individually-hand-tuned numbers.

### Unity rebuild prompt

> Create a single static/pure-function utility class (no MonoBehaviour, no per-instance state) holding every core combat formula as a standalone function: `RollDamage(int min, int max, int att)`, `ApplyDefense(float damage, int def, float floorFraction, bool wholeNumber)`, `TilesPerSecond(int spd)`, `AttacksPerSecond(int dex)`, `HpRegenPerSecond(int vit)`, `MpRegenPerSecond(int wis)`, `XpToNextLevel(int level)`. Reproduce the exact coefficients given above so the game *feels* like the same RPG math. Give damage-over-time ticks a non-integer-floored variant of the defense formula (a `bool wholeNumber` parameter that skips rounding-up-to-at-least-1) so a DoT's effective damage-per-second isn't accidentally inflated by tick rate. Document in comments which numbers are literally reproduced from an external reference vs. locally tuned, so future balance passes don't misattribute a "feel" number as a verified one.
