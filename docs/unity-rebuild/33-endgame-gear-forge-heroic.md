# 33 - Endgame gear, the Anvil, Divine items, Heroic dungeons, level gates

"V0.2 final final" session.

## 1. Tiers (`game/items.py`)
- Every weapon line (8 classes), armor type (heavy / light / robe) and the shared ring table now runs T1-T14.
- Ability lines run 1 / 5 / 9 / **12** / **14**. The new tiers upgrade the class's T9 capstone: magnitude x1.3 / x1.6, MP +10 / +15.
- Weapon damage uses the T11 damage x 1.12 / 1.25 / 1.42.

| Tier | `tier_band` | Badge colour | Where it comes from |
|---|---|---|---|
| 12-13 | `t_mythic` | cyan (70, 225, 215) | the new loot sources below |
| 14 | `t_forged` | red-hot (255, 80, 95) | never drops; the Anvil makes it |
| Divine | `divine` (`Item.divine`, `divine_proc`) | cream (255, 246, 196), `[Divine]` prefix | the Mad God's Room |

- New bag colours: `cyan` and `gold`.
- Normal loot (`_roll_loot_once`) still stops at T11.
- **Loot sources:** `roll_loot(cls, rank, difficulty, source)` adds `LOOT_SOURCES[source][rank]` rows `(bag, what, tier range, chance)` on top of the normal roll. They ride only the first of a kill's loot rolls.

| Source | Boss | Elite |
|---|---|---|
| `heroic` | T11-12 always, T12-13 at 35%, ingot at 30% | T12 at 6% |
| `island` | T12-13 at 45%, ingot at 30% | T12 at 4% |
| `mg_room_1` | T12-13 always, ingot at 60% | T12 at 10% |
| `mg_room_2` | T13, ingot, Divine at 15% | - |
| `mg_room_3` | T13 x2, ingot, Divine always | - |

- **Forge Ingot:** slot `material`, shape `ingot`.
- **Divine items** (`make_divine(cls, piece)`):
  - **Weapon:** T14 damage x1.15 plus **Starfall**: every 4th shot also fires 3 piercing star bolts (`realm_sim.player_fire`).
  - **Armor:** T14-plus stats plus **Second Wind**: a killing blow leaves you at 1 HP with 2 s of invulnerability, once per 90 s (`Player.take_damage`). The sim turns it into a banner, VFX and sound.
  - **Ring:** big all-round stats.
  - **Ability:** the T14 spell at x1.25.

## 2. The Anvil (`game/forge.py`, NPC `hammerstein` in the Nexus at `nexus:anvil`)
- **Temper:** 3 backpack items of the same slot and tier (not UT or Divine) become the next tier of the FIRST item's line.
  - Ingots needed depend on the result tier: 0 up to T11, 1 for T12-13, 2 for T14.
- **Reforge:** 1 UT weapon + 2 ingots become "Reforged <name>", with damage x1.2 and the proc stored in `socketed_proc` so the rename keeps it. It can only happen once.
- **Dialogue:** `forge_options(player)` lists up to 3 recipes, best first. They are the first options of Hammerstein's dialogue. `apply_forge` removes the inputs by identity, so a stale recipe is refused. Forging plays `forge_success` and counts for Act III.
- **Co-op:** the server owns the Conversation, so forging is authoritative there. The dialogue message carries `sfx`.

## 3. Heroic dungeons (`game/realm_sim.py`)
- **Themes:** `DUNGEON_THEMES["heroic_<key>"]` for all 7 non-Forge themes. Each keeps the base look and bosses, and adds:
  - elite-only kinds
  - `HEROIC_EXTRA_ROOMS` (+2 rooms, via `make_bonus_room(room_bonus=)`)
  - the "Heroic" difficulty: HP x3.6, 3 loot rolls, weight 0 (never rolled)
  - `bullet_speed_mult` 1.25 and `fire_rate_mult` x0.8 on every enemy
  - the `heroic` loot source
  - its own track `dungeon_heroic_<key>`
  - a crimson screen vignette (`vfx.draw_heroic_tint`)
  - a crimson aura on every Heroic mob (`Enemy._heroic`, sent as `hero` in `net_state`)
  - "HEROIC" in the dock header
- **Unlock** (`game/sidequests.HEROIC_TRIALS`): one "Heroic Trial" deliver quest per theme, offered by that dungeon's local:

| Dungeon | Giver |
|---|---|
| Forgotten Vault | Barkeep Bitterwick |
| Cave Warren | Glimmer |
| Frozen Crypt | Frostine |
| Jungle Ruins | Fernleaf |
| Ember Den | Cinder Pete |
| Sunken Grotto | Madame Murk |
| Wind Spire | Brother Tipsy |

  - Bring 3 relics. They drop only inside that theme's normal dungeon: the boss drops 1 (2 on Hard), and elites drop one 10% of the time (`quest_drops(theme=, difficulty=, is_boss=)`).
  - Turn-in unlocks the dungeon (the quest id goes in `sidequests.done`, so saves need no new field), gives a first Heroic Shard, and credits `heroic_unlock`.
- **Heroic Shards:** a Hard clear of an unlocked theme drops one 15% of the time; a Heroic boss drops one 25% of the time. `shard_difficulty()` always opens them at "Heroic".
- Heroic clears count for Act IV (`heroic_dungeon`).

## 4. Level gates (`game/gates.py`)
`can_enter(player, theme)` returns `(ok, message)`.

| Content | Requirement |
|---|---|
| Heroic dungeons | level 16+ |
| Big islands | level 20+ (a warning below average T11 gear) |
| Mad God's Room | level 20+ and a T12+ or Divine item equipped |

- Checked in `main.enter_bonus_room`, in `server` on `enter_portal`, and on island_link portals (`island_link_check`).
- A refusal plays `gate_denied`.

## 5. Sounds and effects
- **Sounds** (`audio.EVENT_SOUND`, played with `play_event`; sim sound events are `("sfx", key, x, y)`):
  forge_hammer, forge_success, forge_fail, gate_denied, heroic_portal, harbour_bell, mg_transform, mg_enrage,
  divine_drop, mythic_drop, starfall, second_wind, trial_done. All are layered synthesized notes.
- **VFX:** divine_second_wind, forge_sparks, heroic_portal, mg_transform, divine_drop, mythic_drop, harbour_ferry.
- **Icons:** `ingot` and `key`.
