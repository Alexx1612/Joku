# 03 — Items, Loot, Vault, and Loot Bags

Scope: the item data model, tiered/untiered loot rolling, account-persistent Vault storage, and the loot-bag ground-pickup system (Batch 1 Sections A and B).

---

## 1. Item data model: tiered vs. untiered, and 4 loot-bag rarity bands

### What it is

Every equippable/consumable thing in the game is one `Item` dataclass. Items are either **tiered** (T1-T11ish, numbered, power scales with number) or **untiered/"UT"** (unique, named, `tier` irrelevant, each carrying a distinct `proc`/mechanic — see file `02`'s status-effects/boomerang section). Ground loot bags come in 3 rarity colors — brown (common), purple (mid, "soulbound"-flavored), white (rarest, UT-tier) — mirroring RotMG's own convention.

### Why/how it was chosen

Directly modeled on RotMG's own item system, stated explicitly in the module's own docstring: *"modelled on RotMG's tiered vs. untiered (UT) equipment and its brown / purple / white loot-bag rarity bands."* The project draws an explicit, self-documented line between what's *mechanically* reproduced from the public wiki (tier bands, the brown/purple/white system, the stat formulas in `constants.py`) versus what's original invention (the specific item *names*, since transcribing the real wiki's full multi-hundred-entry-per-class item tables was out of scope) — this honesty-about-sourcing is a recurring, deliberate project norm, not incidental.

### Implementation detail (verified against current `game/items.py:19-75`)

```python
@dataclass
class Item:
    name: str; slot: str; tier: int; shape: str
    is_ut: bool = False
    stat_bonus: dict = field(default_factory=dict)
    min_dmg: int = 0; max_dmg: int = 0
    proc: str = ""
    effect: str = ""; mp_cost: int = 0; magnitude: int = 0   # ability items only
    description: str = ""
    pet_kind: str = ""      # egg items only
    shard_theme: str = ""   # shard items only
```
- `tier_band(tier)`: 1-3 → `t_low`, 4-6 → `t_mid`, 7-9 → `t_high`, 10+ → `t_top`. `Item.band` returns `"ut"` instead if `is_ut`. `Item.color` looks that band up in a shared `TIER_COLORS` palette (`game/constants.py`) — one place controls "what color badge does this item's rarity show," used identically everywhere an item icon renders.
- **`slot`** doubles as a dispatch key across the whole codebase — `"weapon"/"armor"/"ring"/"ability"/"egg"` for equip-slot items, plus two *consumable*-family slots layered on later: `"consumable"` (permanent stat potions) and `"shard"` (dungeon shards) — every system that needs to know "what kind of thing is this and what happens when you use it" (inventory UI, `use_potion`/`use_shard`, network serialization) switches on this one string field rather than maintaining a parallel type hierarchy.
- `to_json()`/`from_json()` round-trip every field — this is the ONE serialization format used for three completely different purposes: the on-disk Vault save file, the on-disk per-character save file (backpack/equipped items), and the co-op wire format for sending item data to a client. One format, one bug surface, instead of three.
- Every weapon/armor/ring/ability/UT/potion/egg/shard is constructed via a small factory function (`make_starter_weapon`, `make_potion(stat_key)`, `make_dungeon_shard(theme, label)`, etc.) rather than `Item(...)` literals scattered everywhere — new item families explicitly follow "mirrors `make_potion()`'s exact pattern" as their own design note, i.e. the factory-function shape itself is a reused convention across features built at very different times.

### Unity rebuild prompt

> Model every game item as one data class/struct with a `Slot` enum (Weapon/Armor/Ring/Ability/Egg/Consumable/Shard/...), a tier integer, an `IsUnique` bool, a small stat-bonus dictionary, and family-specific optional fields (min/max damage for weapons, an ability effect+cost+magnitude, a pet-kind reference for eggs, a themed-dungeon reference for shards) — one flat class rather than a type hierarchy, so a generic inventory/equip/serialization system never needs a type switch beyond the `Slot` field. Give unique/tiered items a distinct color-badge lookup keyed by a small tier-band function (thresholds around tier 3/6/9) plus a separate top color for uniques. Implement full-fidelity serialization for this one Item type once, and reuse that exact serialization for account storage, character-save persistence, AND network transmission — never let those three drift into separate formats.

---

## 2. Loot rolling: `roll_loot()` and per-mob difficulty

### What it is

Killing an enemy rolls a list of `(rarity_key, Item)` drops via `roll_loot(cls_name, enemy_rank, difficulty)`, where `enemy_rank` is `"trash" | "elite" | "boss"` and `difficulty` is a continuous `0.0..1.0` fraction of "how tough was this specific enemy, relative to others of its same rank" — used to nudge which end of a tier range a roll draws from, without touching drop *chances* or bag *colors* at all.

### Why/how it was chosen

The rank-based odds/tier-range table is presented as intentionally "bumped up from the v0 rates so co-op runs feel generous rather than grindy" — an explicit tuning-for-fun-over-realism choice. The later `difficulty`-weighted nudge (documented in this same function's own docstring) fixes a real, specifically-identified fairness bug: two mobs of the same rank used to roll from an *identical* tier range even when one was measurably tougher to actually kill (a tanky troll and a squishier frost_sprite, both "elite," dropping from the same band) — the fix only ever raises the floor of the range for tougher mobs of a rank, and the weakest mob of each rank is explicitly left completely untouched (still the full original range), so the change is purely additive, never a nerf.

### Implementation detail (verified against current `game/items.py:522-572`)

```python
trash:  18% brown tiered(1-3),           4% brown egg,  6% brown potion
elite:  55% brown tiered(1-7),  35% purple tiered(5-11), 12% purple egg,
        10% brown potion, 6% brown temp-potion
boss:   ALWAYS 2x purple tiered(7-11), 65% white UT, 35% white egg,
        30% purple potion, 20% purple temp-potion
```
- `difficulty` comes from `entities.difficulty_fraction(kind)` — computed once at module load from each `ENEMY_KINDS` entry's HP, average per-hit damage × fire aggressiveness, and speed, normalized within its own rank (`0.0` = weakest of that rank, `0.5` if the whole rank is tied/singleton, `1.0` = strongest). A `"_phase2"` boss variant always returns a flat `1.0` (top of its band) rather than participating in the ranking — deliberately excluded from the ranking computation itself, because naively including a much-tankier phase-2 variant in the "boss" rank's HP range would have silently *lowered* every ordinary boss's own computed difficulty (and therefore its loot), just by existing in the same dict — a real balance bug caught and fixed while wiring boss phase-2, not a hypothetical.
- Which CLASS a drop's gear pool comes from is *usually* the killer's own class, but not always: a separate cross-class-drop roll can substitute a different class's pool ~40% of the time (see file `02`'s class-identity note); armor resolves to that substituted class's own Heavy/Light/Robe archetype, but rings are class-agnostic in both this project and real RotMG, so they're unaffected by any of this.

### Unity rebuild prompt

> Implement loot rolling as one function taking (killer's class, enemy rank, a continuous 0-1 "how tough was this specific enemy for its rank" difficulty score) and returning a list of (rarity, item) pairs. Give each of your 3 rank tiers its own independent table of (chance, tier-range, rarity-color) rows, tuned generously rather than realistically if the goal is a fun cooperative pace. Use the difficulty score ONLY to shift which end of a tier range a roll draws from (raise the floor for tougher mobs of the same rank) — never let it change drop chances or rarity colors, and always leave the weakest example of each rank on the full, untouched range so no existing mob's drops get worse. Compute each enemy type's difficulty score once at data-load time from its own combat stats (HP, damage output, fire rate, speed), normalized within its own rank — and explicitly exclude any "harder variant of an existing enemy" (a boss's empowered second phase, etc.) from that normalization computation, giving such variants a fixed top-of-band score instead, so a new hard variant can never accidentally drag down the computed difficulty (and therefore the loot) of the enemies it was computed alongside.

---

## 3. The Vault: account-persistent storage, 10 chests, drag-and-drop

### What it is

A fixed, hand-authored room (not procedurally generated — "so the Vault feels like the same trusted space every visit") reachable from a Nexus tile, containing `VAULT_CHEST_COUNT` (10, grown from an original 7 "per user request") walk-up chests, each holding `VAULT_CHEST_SIZE` (8) item slots — 80 slots total, persisted **per player name**, surviving permadeath (a fresh character still has their old Vault contents).

### Why/how it was chosen

A direct RotMG convention (an out-of-Realm account bank that survives character death) — the project's own comment states the room is deliberately hand-authored rather than generated specifically so repeat visits feel consistent, and the chest count was explicitly bumped from the wiki-authentic 7 to 10 at the user's specific request (a documented "changed a real-game number because the user asked," distinct from the project's usual "reproduce the wiki number" default).

### Implementation detail (verified against current `game/world.py:1282` and `game/items.py:724-758`)

- `world.make_vault_room()`: a fixed-size grid, walled perimeter (`WALL_VAULT`), one `PORTAL` tile back to the Nexus, and 10 `CHEST` tiles laid out in a 4-column grid pattern (`row, col = divmod(i, 4)`), flanked by decorative furniture placed via an explicit `(x, y, tile)` list guarded against ever overwriting a chest or the portal tile — a defensive pattern the project reuses for every hand-authored room's decoration pass, so a layout tweak later can never silently clobber a functional tile.
- Persistence (`game/items.py:724-758`): one JSON file per player name at `vaults/<sanitized-name>.json` (`_vault_path()` strips the name down to alphanumeric/`-`/`_` characters only, defaulting to `"player"` if that leaves nothing — a basic but real path-injection guard against an adversarial or garbage player name). `save_vault()` writes to a `.tmp` file and `os.replace()`s it over the real path — an atomic-write pattern that prevents a crash mid-save from corrupting/truncating the real Vault file.
- Interaction: opening a chest shows an 8-slot grid (a specific chest "paged in," `self.vault_chest` tracks which); deposit/withdraw is drag-and-drop, the *same* drag system used for the backpack/equip grid and loot bags — not a separate click-only Vault-specific interaction (this was itself a Batch 1 upgrade from an earlier click-only version, unified onto the one drag-and-drop system used everywhere else in the inventory UI).

### Unity rebuild prompt

> Build the Vault as one fixed (never randomly generated) room layout with N walk-up chest objects (start with the real game's convention of a handful of chests per chest-bank, e.g. 7-10), each holding a fixed number of item slots. Persist Vault contents in one file per player identity (sanitize the identity string to a safe filename charset before using it in a path), written via a write-to-temp-then-atomic-rename pattern so a crash mid-save can't corrupt the file. Make Vault deposit/withdraw use the exact same drag-and-drop interaction your backpack/equip-slot UI already uses — don't build a second, chest-specific click interaction; a player should be able to drag an item between the backpack and any open chest slot exactly like dragging between backpack and equip slots.

---

## 4. Loot bags: pooled ground drops, not one pickup per item

### What it is

A kill's loot (which may be several items at once, especially a boss) drops as ONE ground `Bag` object holding up to `BAG_CAPACITY` (8) items, colored by the rarest thing inside it (brown/purple/white — independent of any single item's own tier-color), rather than spawning a separate pickup per dropped item. Bags within `BAG_MERGE_RADIUS` (50px) of an existing, still-fresh (`BAG_MERGE_WINDOW`, 3s) bag absorb into it instead of spawning a new one — so several kills in quick succession near each other pool into one bag. Bags despawn after `BAG_LIFETIME` (120s = 2 minutes).

### Why/how it was chosen

An explicit RotMG-authenticity goal (the "one 8-slot bag per drop-event, colored by rarity" convention is a direct real-game reference), replacing an earlier "one ground item per drop" system — the despawn timer itself was deliberately bumped up from an original 45-second single-item timer to the current 2 minutes as part of this same conversion, giving players more real time to notice and collect a bag's full contents.

### Implementation detail (verified against current `game/entities.py:1275-1354`)

- `Bag._RARITY_RANK = {"brown": 0, "purple": 1, "white": 2}` — `add_item()` only ever *upgrades* a bag's displayed color (never downgrades it) as higher-rarity items merge in, matching "the bag's own color reflects the rarest thing inside it."
- **Self-pickup immunity**: a manually-dropped item lands exactly on the dropper's own feet; without a guard, the very next tick's proximity-pickup check would let them instantly re-grab their own drop, making "drop" and "no-op" functionally identical for the dropper (documented as a real, found-and-fixed bug). `Bag.dropped_by` + a 1-second `self_pickup_immune` timer solves this *only* for the original dropper — anyone else standing there can grab it instantly, no immunity for them.
- **Networking pattern**: `Bag.net_state()` sends only a lightweight summary (position, item count, the bag's own color, and the *first* item's name/tier-color as a preview) to every client in range — a client only receives the FULL item list (for the actual drag-and-drop loot window) via a separate, dedicated message sent specifically to whoever opens that one bag. This is the same "ghost summary broadcast to everyone, full detail sent on-demand to whoever actually interacts" pattern the Vault's own co-op sync uses — a reusable networking shape for "a container many players can see exists, but only one player at a time is actually looking inside."

### Unity rebuild prompt

> Replace "one pickup object per dropped item" with one shared loot-bag/container object per drop-event, capable of holding several items (start with a per-bag capacity around 8), colored by the single rarest item's rarity tier rather than an average or the first item. When a new drop happens within a short time window and small radius of an already-open, still-fresh bag, merge into that bag instead of spawning a new one. Give a manually-dropped item's own dropper a brief personal pickup-immunity window (so they don't instantly reclaim their own drop) while leaving it immediately grabbable by anyone else. For multiplayer, broadcast only a lightweight summary of each visible bag (position, item count, its color, maybe a one-item preview) to everyone nearby, and send the full item list only to whichever specific player actually opens that bag to loot it — don't broadcast full item contents of every visible container to every nearby player on every network tick.
