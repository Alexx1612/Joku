# 37 - Gem forging: stones set into weapons

"V0.2 final final" session, after doc 35. Logic is in `game/gems.py` (pure, no pygame); visuals are in `game/gem_art.py`;
the Anvil menu is in `game/dialogue.py`.

## Research
| Source | What we took from it |
|---|---|
| [Diablo II gems](https://diablo2.diablowiki.net/Gem) | Chipped -> Perfect grades; the effect depends on what the stone is set into; **a socketed item takes the colour of its first gem**; same gems stack additively |
| [Enshrouded weapon gems](https://hacktheminotaur.com/enshrouded/enshrouded-gems-list/) | Gems as slot-in procs: life leech, elemental explosions, debuffs |
| [Stardew Valley Forge](https://stardewvalleywiki.com/Forge) | Forge a weapon a limited number of times, one gem each, plus a currency (here, Forge Ingots for the top grades) |
| [Enchantment swords VFX](https://www.unrealengine.com/marketplace/en-US/product/enchantment-swords-vfx) | A coloured aura on the weapon plus elemental trails tell the player at a glance that it's augmented |

## How it differs from Weapon Shards (doc 35)
| | Weapon Shards | Gemstones |
|---|---|---|
| Where | the Shards tab, swapped freely | forged INTO one weapon at the Anvil |
| Follows | whatever weapon you hold | that weapon (trade, vault, co-op) |
| Removal | drag it out | pry it out; the stone shatters |
| Stacking | best + 15% per extra copy | additive, then Attuned x1.15 (2 alike) / Resonant x1.3 (3 alike) with a bonus |

When both give the same effect, the stronger counts in full plus half the weaker (`gems.merge_fx`).

## Stones (`gems.STONES`)
| Stone | Element | Effect on a hit | Resonant (3 alike) |
|---|---|---|---|
| Ruby | fire | burn | kills explode in fire (60% hit dmg + burn, 90 px) |
| Sapphire | frost | frostbite slow | kills shatter: slow + 40% dmg (100 px); 2 alike already slow |
| Topaz | lightning | chain arcs | kills discharge into the 2 nearest foes (50%) |
| Emerald | venom | poison DoT (16% hit dmg/s x strength) that spreads on death (90 px) | spreads 160 px at full strength |
| Amethyst | arcane | homing + 1 pierce per stone | +2 pierce |
| Onyx | shadow | lifesteal | kills heal 6% max HP |
| Diamond | radiant | crit chance | crits x2.5 instead of x2 |

**Grades:** Chipped / Flawed / Regular / Flawless / Perfect have strength x0.55 / 0.75 / 1.0 / 1.35 / 1.8 and item tiers 2 / 4 / 7 / 10 / 13.

**Sockets** (`socket_count`):
- T0-4 weapons have 1, T5-9 have 2, T10+ have 3.
- UT and Divine weapons have 2.

## The Anvil's Stonework menu
"Stonework: gems and sockets..." on Brother Hammerstein's menu (`gems.stonework_options` / `apply_stonework`) offers three actions:
- **Set:** set a backpack stone into the EQUIPPED weapon. A Flawless costs 1 Forge Ingot, a Perfect costs 2.
- **Combine:** 3 identical stones become 1 of the next grade. Flawless -> Perfect costs 1 Ingot.
- **Pry:** pry out the last stone set. It shatters.

**Co-op:** the server owns the conversation, so this is authoritative with nothing extra.

**Feedback:** sounds `gem_set`, `gem_combine` and `gem_pry`, and a `gem_forge` burst of sparks in the stone's colour at the Anvil.

## Visuals (`game/gem_art.py`)
- **Stone icons:** cut stones with more facets and sparkle the better the grade. A Chipped stone has a broken corner, a Flawed one a crack, and a Diamond is a brilliant cut.
- **Gemmed weapon icon** (`sprites.icon_of`): a glow rim in the first stone's colour and one pip per socket.
- **Shots:** the first stone colours the shot (as in D2). Each element has its own trail:

  | Stone | Trail |
  |---|---|
  | Ruby | rising embers |
  | Sapphire | frost motes and glints |
  | Topaz | a flickering double lightning tail |
  | Emerald | venom drips |
  | Amethyst | a twin violet/pink helix |
  | Onyx | dark smoke |
  | Diamond | prismatic glints |

  Every shot also has a coloured halo (it reads on snow and on grass) and a white-hot core. The trail is drawn from position and time only, so co-op ghosts match (snapshot field `gem`).
- **On hit:** `vfx gem_hit`, per element: embers, ice shards, sparks, a venom cloud, an arcane pull, smoke, a prism.
- **On kill:** `vfx gem_burst`: fire explosion, frost shatter, venom spread, and a soul stream flowing back to the wielder.
- **Player aura:** element motes orbit a player whose weapon has stones, with a glow at the weapon hand. Peers see it too.

## Getting stones
- **Drops:** elites 6%, bosses 30% (`GEM_DROP_CHANCE`).
  - Night drops are x1.5, Blood Moon x2.
  - Island, Heroic and Blood Moon sources roll +1 grade; the Mad God's Room rolls +2; bosses roll +1.
- **Gem veins** (`RealmSim.gem_veins`):
  - **Placement:** 7 per biome in highlands, desert, tundra, cave, ashlands and jungle, each biome with its own stone mix. They are placed with a private RNG, so the rest of world generation is unchanged.
  - **Mining:** F within 64 px starts a 1.4 s channel (pick clinks, chips flying, a progress bar). Walking away cancels it.
  - **Yield:** a Chipped (62%), Flawed (32%) or Regular (6%) stone.
  - **Regrowth:** 2 charges, then the vein goes dull until the morning after the next night.
  - **Co-op:** the server F action is `fish`, and the snapshot carries `gem_veins` and `mining`.

## Save / net
- **Weapon data:** `Item.gems = [[kind, grade], ...]`, and stones are `Item(slot="gem", gem_kind, gem_grade)`. Both ride `to_json`, so saves, trades, the vault and co-op snapshots carry them.
- **Old saves** load with no stones.

## Tests
`tests/check_gem_forging.py` covers:
- sockets per tier
- set / combine / pry, including the real Anvil conversation
- additive / Attuned / Resonant stacking and the merge with shards
- per-element hit effects and on-kill effects (ruby burst, venom spread, onyx heal, amethyst pierce)
- icon / trail / aura / vein / vfx rendering and caching
- sounds
- drops and grade boosts
- vein mining, cancel, depletion and regrowth
- the save round-trip and co-op peers

Screenshots: `screenshots/2026-10-07/gem_forging/` (`tools/shots_gem_forging.py`).
