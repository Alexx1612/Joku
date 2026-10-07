# Game data reference (per version)

A versioned snapshot of the game's data tables - sound effects, music,
achievements, class stats, abilities, pets, bosses, dungeons, story, side
quests, NPCs and areas - so there's a historical record as these change,
not just whatever's currently in the code. Numbers are read from the code
(file named in each heading). Update this alongside README.md's version
history when any of them change.

## Ends of V0.2 - "final final" content update (current - still v0.2)

Everything in the "Ends of V0.2" section below still applies, except where this section replaces it (story, tiers,
islands, dungeon list).

### Story (`game/story.py`, 7 acts)

| Act | Objectives |
|---|---|
| Prologue: Welcome, Sucker | Talk to Father Given (F); step through the Realm portal |
| Act I: The Grand Tour | Visit 5 big named places; spot the landmark in each outer biome; chat with 3 locals; catch a fish |
| Act II: Bouncer Problems | Defeat the Guardians of the Sunken Idol (forest), Buried Obelisk (desert), Frozen Watchpost (tundra), Drowned Shrine (swamp); clear 1 dungeon |
| Act III: Retail Therapy | Wear a T8+ item; clear 2 dungeons; finish a Heroic trial; forge an item at the Anvil |
| Act IV: The Deep End | Defeat 4 inner-biome Landmark Guardians; clear 2 Heroic dungeons |
| Act V: Last Call | Calm any 7 of the 10 big islands (level 20) |
| Finale: Closing Time | Defeat the Mad God in the Forge |

- `act_scale`: 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6.
- Old 5-act saves map `{0:0, 1:1, 2:3, 3:4, 4:6, 5:7}`.

**Pacing** (`tools/pacing_bot.py`, 4 classes x 2 seeds, simulated minutes):

Re-measured 2026-10-07 after precise combat, the night update and danger by distance (doc 39):

| Act | Median | Min | Max | Before (doc 32 first run) |
|---|---|---|---|---|
| Prologue | 0.5 | 0.5 | 0.5 | 0.5 |
| I: The Grand Tour | 9.7 | 8.7 | 11.4 | 9.9 |
| II: Bouncer Problems | 50.5 | 23.0 | 64.2 | 24.9 |
| III: Retail Therapy | 24.6 | 14.3 | 57.3 | 29.3 |
| IV: The Deep End | 7.9 | 4.4 | 23.5 | 17.3 |
| V: Last Call | 12.7 | 8.2 | 17.0 | 9.6 |
| Finale | 5.6 | 2.4 | 20.0 | 9.9 |
| **Total** | **105.4** | 92.8 | 173.3 | 100.8 (52.8-170.0) |

Act II roughly doubled: its landmark guardians stand in the inner biomes, and the mobs around them are now
danger-scaled up to x2.2 HP. The bot stalled on the forest / desert guardian in 5 of 8 runs and died up to 34 times
in a run, so a human will feel the centre. The guardians themselves stay on their act scaling.


### Tiers and loot sources (`game/items.py`)

| Tier | Badge | Source |
|---|---|---|
| T1-T11 | white / blue / purple / orange | normal loot (unchanged) |
| T12-T13 | cyan "mythic" | `LOOT_SOURCES`: heroic, island, mg_room_1..3 |
| T14 | red-hot "forged" | the Anvil only |
| Divine | cream `[Divine]` | mg_room_2 (15%), mg_room_3 (always) |

| Source | Boss extras | Elite extras |
|---|---|---|
| heroic | T11-12 (100%), T12-13 (35%), Forge Ingot (30%) | T12 (6%) |
| island | T12-13 (45%), Ingot (30%) | T12 (4%) |
| mg_room_1 | T12-13 (100%), Ingot (60%) | T12 (10%) |
| mg_room_2 | T13 (100%), Ingot (100%), Divine (15%) | - |
| mg_room_3 | T13 x2, Ingot, Divine (all 100%) | - |

New T12 / T13 / T14 names:

| Line | T12 | T13 | T14 |
|---|---|---|---|
| Wizard | Staff of Drowned Stars | Staff of the Seventh Tide | Anvil-Wrought Starstaff |
| Archer | Bow of the Salt Wind | Bow of the Longest Night | Anvil-Wrought Skybow |
| Warrior | Tidebreaker Greatsword | Blade of the Last Round | Anvil-Wrought Kingsblade |
| Priest | Rod of the Quiet Harbour | Staff of the Second Dawn | Anvil-Wrought Halo Staff |
| Rogue | Dagger of the Undertow | Fang of the Closing Bell | Anvil-Wrought Whisperfang |
| Necromancer | Staff of the Drowned Choir | Staff of the Final Toast | Anvil-Wrought Gravestaff |
| Paladin | Mace of the Harbour Light | Mace of the Last Call | Anvil-Wrought Judgement |
| Assassin | Kris of the Riptide | Blade of the Empty Glass | Anvil-Wrought Nightkris |
| Heavy armor | Harbourmaster's Plate | Plate of the Tidal Throne | Anvil-Wrought Bulwark |
| Light armor | Saltwind Leathers | Coat of the Last Current | Anvil-Wrought Shadowmail |
| Robe | Robe of the Drowned Library | Robe of the Night Bell | Anvil-Wrought Starmantle |
| Ring | Ring of the Undertow | Ring of the Closing Hour | Anvil-Wrought Signet |
| Abilities | "<T9 noun> of the Undertow" (x1.3) | - | "Anvil-Wrought <noun>" (x1.6) |

Divine items:

| Piece | Name(s) | Effect |
|---|---|---|
| Weapon | one per class, e.g. The Mad God's Bottle Opener (warrior), ... Party Bow (archer), ... Spare Wand (wizard) | T14 damage x1.15, Starfall (every 4th shot + 3 piercing star bolts) |
| Armor | Doorman Plate / Last-Orders Coat / Dressing Gown | T14+ stats, Second Wind (1 HP instead of death, 90 s cooldown) |
| Ring | The Mad God's Wedding Ring | att +10, wis +9, vit +6, def +4, dex +4, spd +3 |
| Ability | The Mad God's <noun> | T14 magnitude x1.25 |

### The Anvil (`game/forge.py`)

| Recipe | Input | Result |
|---|---|---|
| Temper | any 3 gear items of the same tier, mixed slots OK (not UT or Divine) | the next tier of the first item's line |
| Temper, T12-13 result | as above + 1 Forge Ingot | T12-T13 |
| Temper, T14 result | as above + 2 Forge Ingots | T14 |
| Reforge | 1 UT weapon + 2 Forge Ingots | "Reforged <name>": damage x1.2, proc kept; once only |

### Dungeons, Heroic and the Mad God's Room (`game/realm_sim.py`)

| Difficulty | HP | Cap | Loot rolls | How |
|---|---|---|---|---|
| Easy / Medium / Hard | x1.15 / x1.6 / x2.3 | 10 / 13 / 16 | 1 / 2 / 3 | rolled 55 / 32 / 13 |
| Heroic | x3.6 | 18 | 3 | Heroic Shards only |
| Godly | x3.0 | 18 | 2 | the Mad God's Room Key only |

| Heroic dungeon | Trial giver | Relic (x3) |
|---|---|---|
| Forgotten Vault (Heroic) | Barkeep Bitterwick | Vault Keystone |
| Cave Warren (Heroic) | Glimmer the Cartographer | Warren Lantern Shard |
| Frozen Crypt (Heroic) | Frostine | Crypt Frost Seal |
| Jungle Ruins (Heroic) | Fernleaf | Ruin Idol Eye |
| Ember Den (Heroic) | Cinder Pete | Cinder Crown Fragment |
| Sunken Grotto (Heroic) | Madame Murk | Grotto Black Pearl |
| Wind Spire (Heroic) | Brother Tipsy | Spire Wind Chime |

- **Heroic dungeons:** elites only, +2 rooms, bullets x1.25, cooldowns x0.8.
- **Heroic Shards:** drop from 15% of Hard clears of an unlocked theme and 25% of Heroic bosses.
- **Mad God's Room Key:** drops from 2% of Heroic bosses and 1% of calmed big islands (per player).
- **Mad God's Room forms:**

| Form | Base HP | Look | Moves |
|---|---|---|---|
| Mad God | 2200 | the Forge fight's figure | the Forge fight's moves |
| Unhinged | 4840 | four arms, violet robe | Unhinged Volley, Tantrum Wall, Throne Leap, Star Storm, Mad Dash (x3), Unhinged Nova |
| Absolutely Livid | 7040 | crimson wings | Livid Volley, Spiral of Spite, Meteor Hell, Rage Beam, Closing Walls, Livid Nova, Sycophants |

  - Livid enrages after 150 s.

**Level gates** (`game/gates.py`):

| Content | Requirement |
|---|---|
| Heroic | level 16 |
| Big islands | level 20 (warning below average T11 gear) |
| Mad God's Room | level 20 + a T12+ item equipped |

### World

| | Before | Now |
|---|---|---|
| Map | 1308 x 1308 | 1560 x 1560 (`CONTINENT_OFFSET` 330) |
| Island radius | 52 | 150 (islands ~252-267 tiles across) |
| Island plaza radius | 10 | 14 |
| Camps per island | 4 | 12 (two rings) |
| Camp HP | x1.6 | x3.2 |
| Wave HP | x1.0 | x2.6 |

- New Nexus NPC: Brother Hammerstein (the Anvil).
- Side quests: 30 -> 37 (the 7 Heroic trials).

### New music (`game/music.py`)

| Key | Title | Style |
|---|---|---|
| dungeon_heroic_generic | Vault of No Return | gallop, D harmonic minor, 132 |
| dungeon_heroic_cave | Warren Collapse | halftime, C phrygian, 104 |
| dungeon_heroic_frozen_crypt | Crypt Blizzard | punk, D# minor, 152 |
| dungeon_heroic_jungle_ruins | Idol's Wrath | tribal, F# phrygian, 144 |
| dungeon_heroic_ember_den | Caldera | punk, E harmonic minor, 184 |
| dungeon_heroic_sunken_grotto | Undertow Hymn | doom, F phrygian, 90 |
| dungeon_heroic_wind_spire | Eye of the Gale | gallop, G dorian, 160 |
| dungeon_mad_god_room | Throne of Nonsense | gallop, D phrygian-dominant, 140 |
| dungeon_mad_god_room_unhinged | Unhinged | punk, C# harmonic minor, 168 |
| dungeon_mad_god_room_livid | Absolutely Livid | punk, E phrygian, 192 |

### New sound effects (`game/audio.py` `EVENT_SOUND`, `play_event`)

| Key | When |
|---|---|
| forge_hammer | forging |
| forge_success | an item comes off the Anvil |
| forge_fail | a forge attempt fails |
| gate_denied | a level/gear gate refuses you |
| heroic_portal | a Heroic Shard or the Room Key opens a portal |
| harbour_bell | an island hub portal takes you across |
| mg_transform | the Mad God changes form |
| mg_enrage | Absolutely Livid enrages |
| divine_drop | a Divine item drops |
| mythic_drop | a T12+ item drops |
| starfall | the Divine weapon's Starfall bolts |
| second_wind | the Divine armor's Second Wind |
| trial_done | a Heroic trial is turned in |

### Gem forging (`game/gems.py`, doc 37)

| Stone | Element | On hit | Resonant (3 in one weapon) |
|---|---|---|---|
| Ruby | fire | burn | kills explode (60% dmg + burn, 90 px) |
| Sapphire | frost | slow (frostbite) | kills shatter (slow + 40% dmg, 100 px); 2 alike: shatter slows |
| Topaz | lightning | chain arcs | kills discharge into 2 foes (50%) |
| Emerald | venom | poison 16%/s x strength, spreads on death 90 px | spreads 160 px, full strength |
| Amethyst | arcane | homing + 1 pierce per stone | +2 pierce |
| Onyx | shadow | lifesteal | kills heal 6% max HP |
| Diamond | radiant | crit chance | crits x2.5 |

| Grade | Strength | Item tier | Set cost | Combine 3 -> next |
|---|---|---|---|---|
| Chipped | x0.55 | 2 | free | free |
| Flawed | x0.75 | 4 | free | free |
| Regular | x1.0 | 7 | free | free |
| Flawless | x1.35 | 10 | 1 Forge Ingot | 1 Forge Ingot |
| Perfect | x1.8 | 13 | 2 Forge Ingots | - |

Sockets: T0-4 = 1, T5-9 = 2, T10+ = 3, UT / Divine = 2. Same stones add up; 2 alike x1.15 (Attuned),
3 alike x1.3 (Resonant). Pry: the stone shatters.

Drops: elite 6%, boss 30% (night x1.5, Blood Moon x2); grade +1 for island / Heroic / Blood Moon and bosses,
+2 in the Mad God's Room. Gem veins: 7 per biome (highlands, desert, tundra, cave, ashlands, jungle), 2 charges,
1.4 s to mine, Chipped 62% / Flawed 32% / Regular 6%, regrow the morning after the next night.

New sounds: gem_set, gem_combine, gem_pry, gem_mine.

### Night horror (`game/realm_sim.py`, `game/night.py`, doc 35)

| | Before | Now |
|---|---|---|
| Day length | 240 s | 600 s: day 300, dusk 30, night 240 (Blood Moon 180), dawn 30 |
| Night darkness | ~59% max | light map; `luminosity` setting (default 0.5, night only) |
| Player light radius | 130 px | 175 px (x1.6 with the Light of RDV; 62% -> 100% over ~25 s as your eyes adapt) |
| Blood Moon chance | per night | 0.12 per nightfall, x2 on a full moon |
| Player fire rate | DEX only | x0.55 (`PLAYER_FIRE_RATE_MULT`) |
| Player hit damage | x1 | x1.8 (`PLAYER_DAMAGE_MULT`) |
| Aim-assist cone | 16 deg | 7 deg |
| Min spawn distance from a player | none (bug: tiles used as pixels) | 380 px |

Night rules (all hostile mobs; restored at dawn):

| | Aggro | Aggro in the dark | Leash | Speed | Damage | Cooldowns |
|---|---|---|---|---|---|---|
| Night | x1.6 | x2.0 | x1.5 | x1.15 | x1.2 | x0.85 |
| Blood Moon | x2.2 | x2.6 | x2.0 | x1.25 | x1.35 | x0.75 |

Night events (one per normal night):

| Event | Effect |
|---|---|
| The Fog | light x0.6, more Shade Stalkers |
| Something Is Hunting You | a buffed Shade Stalker hunts one player |
| The Lanterns Go Out | every lamp dark |
| Midnight Market | Ghost Merchant: 3 gear items -> 1 a tier higher |
| The Lamplighter | protect Old Wick (420 HP) from waves every 24 s; alive at dawn -> every helper gets the Light of RDV |

Night-only mobs: Lantern-Eater (snuffs lamps), Shade Stalker (invisible outside light), Night Mimic (a loot bag
until close), Hollow Watcher (shrieks, summons), The Red Harvester (Blood Moon boss, at half-night). Blood Moon
hordes: 6-10 moonlit mobs every 30 s, 11-14 tiles out. Surviving: +400 XP.

**The Light of RDV** (`items.make_rdv_ring`): UT ring, WIS +6, VIT +4, DEX +3. Light radius x1.6, and non-boss
monsters within 240 px drop aggro and back off.

**Weapon Shards** (`game/runes.py`): 12 slots, 4 active. Effects: bleed, burn, vulnerable, frostbite, chain, keen,
leech, splinter, seeker, impact, executioner, echo. Rarity x1.0 / 1.4 / 1.9 / 2.6 (weights 60/28/10/2); duplicate
effect +15% each. Drop: elite 4%, boss 25%; x2.5 at night, x4 under a Blood Moon. 3 of a rarity fuse into 1 of the
next at the Anvil. **Bag 2**: 12 more backpack slots.

Moon phases: 8 nights, 0 = new (darkest), 4 = full (+0.16 ambient light).

Night weather (`game/night_sky.py`), rolled each normal night:

| Weather | Weight | Ambient | Light radius | Extra |
|---|---|---|---|---|
| clear | 45 | x1.0 | x1.0 | shooting stars: 40% / 16 s, 30% of them fall |
| cloudy | 25 | x0.72 | x1.0 | moon hidden |
| rain | 18 | x0.62 | x0.85 | rain everywhere it can rain |
| storm | 12 | x0.55 | x0.8 | lightning every 6-16 s |

Night finds:

| Item | Where | Effect |
|---|---|---|
| Moonpetal | night herb (F), forest / highlands | heal 25%, +30% light for 120 s |
| Ghostbloom | night herb (F), swamp / jungle | heal 50%, +8 VIT for 60 s |
| Star Fragment | a fallen shooting star | 50% chance of an extra loot roll per kill for 240 s |

Owls: night-only neutral wildlife, 2 per player, fly off within 130 px.

New music: `realm_night` "Witching Hour" (C# harmonic minor, 70), `realm_blood_moon` "Red Harvest" (phrygian, 148).

New sounds: door_open, door_close, crickets, owl, howl, dawn_chorus, heartbeat, nightfall, dawn, blood_moon_rise,
night_fog, night_hunter, night_lanterns_out, night_market, night_lamplighter, night_blood_moon, mimic_snap,
watcher_shriek, lantern_snuff, harvester_roar, thunder, rain_start, rain_patter, shooting_star, owl_flap,
herb_pick.

### Danger by distance (`game/danger.py`, doc 39)

`f` = 1 - distance from the continent's centre / continent radius (1 = centre, 0 = coast; the ocean ring and the
islands are off this scale). Applied once to every hostile on the continent, night mobs included.

| Tier | f | Name |
|---|---|---|
| 1 | 0.0-0.2 | Calm |
| 2 | 0.2-0.4 | Mild |
| 3 | 0.4-0.6 | Wild |
| 4 | 0.6-0.8 | Deadly |
| 5 | 0.8-1.0 | Lethal |

| Stat | Coast (f=0) | Centre (f=1) | Formula |
|---|---|---|---|
| HP | x0.6 | x2.2 | 0.6 + 1.6 f^1.2 |
| Damage | x0.65 | x1.5 | 0.65 + 0.85 f |
| Speed | x0.92 | x1.08 | 0.92 + 0.16 f |
| Attack cooldowns | x1.15 | x0.85 | 1.15 - 0.30 f |
| Aggro range | x0.9 | x1.25 | 0.9 + 0.35 f |
| XP | x0.8 | x1.6 | 0.8 + 0.8 f |
| Extra loot roll | 0% | 54% | max(0, f - 0.4) x 0.9 |
| Elite Dungeon Shard | 5% | 13% | 0.05 + 0.08 f |
| Night mob spawn interval | x1.25 | x0.75 | 1.25 - 0.5 f |

Dungeon Shard difficulty by the tier it dropped in (Easy / Medium / Hard weights): unknown 55/32/13, tier 1 85/15/0,
tier 2 65/30/5, tier 3 40/42/18, tier 4 18/45/37, tier 5 5/35/60. At tier 5 an elite's shard is a Heroic shard 8% of
the time (killer level 16+).

### Calendar (`RealmSim.forecast_view`, `game/calendar_ui.py`)

7 nights ahead (`FORECAST_NIGHTS`). Each coming night's dice are pre-drawn; at nightfall they're resolved with the
rules in force (Blood Moon chance 12% + 3%/night since the last, x2 full moon, x live event, max 50%; weather
45/25/18/12; events fog / hunter / lanterns_out / market / lamplighter). Live-event slots: 25 min each, schedule
none, Double Loot, none, Happy Hour, none, Blood Moon Week, none, Two-for-One.

### Dawn / dusk light (`ui.draw_sky_grade`)

A vertical band 45% of the play area wide, peak +(44, 24, 6) additive, travelling left -> right over dusk's golden
hour (225-330 s) and right -> left over dawn's (540-645 s). Tints: golden (1.0, 0.92, 0.80), blue (0.86, 0.91, 1.0),
applied to the night darkness only.

## Ends of V0.2 (release tag `v0.2`)

### Sound effects (`game/audio.py`)

All synthesized at runtime - no audio files are loaded.

| Function | Used for |
|---|---|
| `play_shoot(cls_name)` | Firing your weapon - per-class tone |
| `play_hit()` | Player takes damage |
| `play_enemy_hit()` | An enemy takes damage (generic) |
| `play_mob_hit(family)` | An enemy takes damage, family-tinted (beast/undead/elemental/construct) |
| `play_mob_death(family)` | An enemy dies, family-tinted |
| `play_mob_bark(family)` | A mob's flavor-line vocalization (growl / moan / hiss / groan) |
| `play_pickup()` / `play_drop()` | Picking up / dropping an item |
| `play_death()` | The player dies |
| `play_levelup()` | Leveling up |
| weapon types for `play_shoot(cls_name)` | `audio.WEAPON_TYPE`: wizard staff, necromancer scepter, priest wand, archer bow, rogue dagger, assassin katar, warrior sword, paladin mace - each its own sound |
| `play_ability(style)` | Casting your ability - one sound per `vfx.ABILITY_STYLES` style (`audio.ABILITY_SOUND`: shatter, ruin, void, blight, corruption, reaper, thunder, storms, gale, mending, restoration, rebirth, aegis, ward, horn, smoke, shadow) |
| `play_enemy_attack(key)` | Enemy attack sounds (`audio.ENEMY_ATTACK_SOUND`): shot, shotgun, spray, burst, beam, wall, wave, homing, bubble, fire, throw, lob, slam, leap, dash, dash_windup, windup, summon, shell, root, boss_phase |
| `play_boss_spawn()` | A boss appears |
| `play_wish(jackpot)` | Wishing-fountain reroll (fanfare on a jackpot) |
| `play_theme(zone)` / `update_music()` | Start / crossfade the zone's music track (see Music) |
| `set_volumes(master, music, sfx, muted)` | Applies the options-menu volumes live |

SFX are rate-limited: the same sound at most every 0.045 s and at most 10 sounds per 0.12 s window
(`SFX_MIN_INTERVAL`, `SFX_WINDOW`, `SFX_WINDOW_BUDGET`).

Mob flavor lines have a 20 s `MIN_REBARK_INTERVAL` and only reach chat for
players within 600 px (`realm_sim.MOB_SPEECH_HEAR_RADIUS`).

### Music (`game/music.py`)

23 original tracks, each ~60 s, a whole number of bars and seamlessly
loopable, rendered on a background thread and cached as `.wav` in
`music_cache/`. Realm music follows the biome / big area / island you're in
(switch after 2 s there, ~1.5 s crossfade). All compositions are original -
no covers or borrowed melodies.

| Zone | Title | Style | BPM |
|---|---|---|---|
| Nexus | Hearthlight | ballad | 92 |
| Bazaar | Haggle Boogie | shuffle | 150 |
| Vault room | Counting Room | half-time | 84 |
| Forest | Greenwood Charge | rock | 124 |
| Desert | Mirage Road | rock | 112 |
| Tundra | Whiteout | half-time | 100 |
| Swamp | Bog Blues | shuffle | 88 |
| Highlands | Windcrest Gallop | gallop | 140 |
| Ashlands | Cinder Sprint | punk | 168 |
| Jungle | Canopy Drums | tribal | 118 |
| Wasteland | Rust Belt | half-time | 96 |
| Ice | Glass Cathedral | rock | 132 |
| Cave | Deep Echo | doom | 76 |
| Shard islands | Shard Surf | surf | 156 |
| Choir islands | Choir Tide | off-beat | 104 |
| Forgotten Vault (generic dungeon) | Forgotten Halls | rock | 108 |
| Cave Warren | Warren Crawl | doom | 84 |
| Frozen Crypt | Crypt Frost | half-time | 96 |
| Jungle Ruins | Idol Run | tribal | 126 |
| Ember Den | Magma Stomp | gallop | 150 |
| Sunken Grotto | Drowned Bells | off-beat | 98 |
| Wind Spire | Updraft | surf | 136 |
| The Forge (finale) | Closing Time | punk | 176 |

### Achievements (`game/achievements.py`)

| id | Title | Unlocked by |
|---|---|---|
| `first_blood` | the Bloodied | Land your first kill |
| `angler` | the Angler | Reel in your first catch while fishing |
| `egg_parent` | the Beastkeeper | Hatch your first pet |
| `high_roller` | the Lucky | Win an untiered item from the wishing fountain |
| `dungeoneer` | the Dungeoneer | Clear a bonus dungeon's boss |
| `veteran` | the Veteran | Reach level 10 |
| `godslayer` | the Godslayer | Slay a Mad God's Avatar in the open Realm |
| `reforger` | the Reforger | Help calm a flaring shard or singing spire |
| `legend` | the Legend | Reach level 20 |

### Class base stats (`game/entities.py` `CLASS_BASE`)

| Class | Armor | HP | MP | ATT | DEF | SPD | DEX | VIT | WIS | Signature growth stats |
|---|---|---|---|---|---|---|---|---|---|---|
| Wizard | robe | 100 | 100 | 10 | 5 | 25 | 15 | 10 | 30 | wis, att, vit, wis, dex |
| Archer | light | 90 | 70 | 15 | 10 | 35 | 25 | 15 | 10 | dex, att, spd, vit, dex |
| Warrior | heavy | 130 | 50 | 15 | 25 | 20 | 15 | 25 | 5 | deF, vit, att, deF, spd |
| Priest | robe | 100 | 120 | 5 | 10 | 25 | 10 | 15 | 35 | wis, vit, wis, spd, dex |
| Rogue | light | 85 | 60 | 12 | 8 | 40 | 30 | 12 | 8 | dex, spd, att, dex, vit |
| Necromancer | robe | 95 | 110 | 8 | 6 | 22 | 12 | 12 | 32 | wis, att, wis, vit, dex |
| Paladin | heavy | 140 | 80 | 10 | 22 | 18 | 12 | 22 | 18 | deF, vit, wis, deF, vit |
| Assassin | light | 80 | 65 | 14 | 6 | 38 | 32 | 10 | 8 | dex, att, dex, spd, vit |

Level cap 20. Per level-up: HP +16-22 / +12-17 / +9-13 and MP +4-7 / +5-8 /
+7-11 for heavy / light / robe; each signature stat +1-3, every other stat
+0-1 (random rolls). Priest's growth list swapped `deF` for `spd` in this
release (it used to out-grow every non-heavy class's defense).

Player damage taken = `dmg * 75 / (75 + DEF)` (`constants.player_defense`);
e.g. DEF 15 -> 83%, DEF 63 -> 54% of the hit. Armor-piercing shots (the Mad
God's volley and nova) skip it.

### Abilities (`game/items.py` `ABILITIES`)

Base magnitude listed; at cast damage effects are x2.5 and heal/shield x1.5
(`ABILITY_POWER_MULT`, applied by `ability_power()`), haste values are
seconds and unscaled.

| Class | T1 | T5 | T9 |
|---|---|---|---|
| Wizard | Orb of Shatter - nova 22 (55) | Orb of Ruin - nova 40 (100) | Orb of the Void - chain 56 (140), up to 4 targets |
| Necromancer | Skull of Blight - nova 20 (50) | Skull of Corruption - nova 35 (88) | Skull of the Reaper - drain 50 (125), heals 50% of damage |
| Archer | Quiver of Thunder - nova 17 (43) | Quiver of Storms - nova 32 (80) | Quiver of the Gale - freeze 37 (93), roots 2.5 s |
| Priest | Tome of Mending - heal 20 (30) | Tome of Restoration - heal 35 (53) | Tome of Rebirth - heal 55 (83) |
| Paladin | Aegis of Faith - heal 16 (24) | Aegis of Devotion - heal 28 (42) | Aegis of the Ward - shield 60 (90) for 8 s |
| Warrior | Rally Horn - haste 6 s | War Horn - haste 6 s | Horn of the Vanguard - haste 8 s |
| Rogue | Smoke Draught - haste 6 s | Shadow Draught - haste 6 s | Draught of the Void - haste 8 s |
| Assassin | Cloak of Shadows - haste 6 s | Veil of Night - haste 6 s | Veil of the Abyss - haste 8 s |

Each has its own visual style (`vfx.ABILITY_STYLES`: shatter, ruin, void,
blight, corruption, reaper, thunder, storms, gale, mending, restoration,
rebirth, aegis, ward, horn, smoke, shadow). Abilities never hit neutral
wildlife, NPCs or unshootable mobs.

### Pets (`game/items.py` `PET_KINDS`)

| Pet | Rarity | Specialty |
|---|---|---|
| Hatchling | common | heal |
| Imp Pup | common | attack |
| Wisp | uncommon | magic |
| Sentient Fish | uncommon | magic (fishing catch) |
| Griffin Cub | rare | attack |
| Moon Sprite | rare | heal |
| Spirit Fox | rare | magic |
| Phoenix Chick | legendary | heal |
| Tipsy Thunderbird | legendary | attack |
| Sommelier Serpent | legendary | magic |
| Hangover Hydra | mythic (fusion only) | heal |
| Last-Call Leviathan | mythic (fusion only) | attack |
| Brewmaster Djinn | mythic (fusion only) | magic |

- Ability level caps / start levels: common 10/3, uncommon 15/5, rare 20/7,
  legendary 30/10, mythic 40/14. Base at level 1: heal 8 hp / 6 s, magic
  6 mp / 6 s, attack 6 dmg / 2.6 s; +15% magnitude and x0.95 cooldown per
  level (a third as much past level 30).
- Feeding: 6 feed-XP per item tier, split across the 3 abilities; 30 XP per
  ability level. Egg drop weights: common 50, uncommon 25, rare 12,
  legendary 2 (mythic never drops).
- Bond level = `floor(sqrt(bond / 30))`, max 25: magnitude x(1 + 0.04 * level),
  cooldown x(1 - 0.01 * level); heal/mana cooldowns never below 1.5 s.
- Fusion: two maxed pets of the same rarity -> next rarity, bond summed.

### Enemies and bosses (`game/entities.py` `ENEMY_KINDS`)

28 trash-rank kinds (11 hostile + 17 neutral: 16 friendly wildlife and the
dungeon Totem), 33 elite and 24 boss-rank kinds (incl. phase-2 variants). Damage values
below already include the global x1.22 enemy damage multiplier.

| Boss | HP | Damage | Draw/hit scale |
|---|---|---|---|
| boss (Mad God's Avatar pool / Vault Guardian) | 1440 | 7-17 | 2.0 |
| frost_monarch | 1600 | 9-18 | 2.0 |
| ash_behemoth | 1300 | 10-21 | 2.0 |
| void_reaper | 1500 | 7-16 | 2.0 |
| thorn_warden | 1700 | 7-16 | 2.0 |
| sand_wyrm | 1350 | 10-20 | 2.0 |
| mad_god (Forge, phase 1) | 2200 | 6-12 | 2.0 |
| mad_god_phase2 | 3850 | 6-13 | 2.0 |

**Attack sets** (`game/enemy_attacks.py`: `ATTACKS` + `moves_for()`, which HARDENS elite/boss sets - x1.18/x1.2
bullet speed, x0.75/x0.72 cooldowns (x0.9 for moves already under 1.5 s), +1 bullet on fans, x1.2/x1.3 ring density
with the gaps kept, +2 on walls, a plain single shot becomes a tight double; bosses/mini-bosses also get the enraged
**Crossfire** combo (a predictive 3x burst while 3 ground zones land around you). `*` = enraged below 50% HP
(cooldowns x0.6 after the roar), `+` = phase-2 room only. Only DANGEROUS moves are telegraphed, shown in brackets:
line/dash = red, zone/cone/ring = orange; no bracket = no warning at all. These full sets are only used by SPECIAL
mobs - bosses, mini-bosses, island anchors, landmark guardians and anything fought inside a dungeon room; the same
kinds roaming the open Realm / islands use `basic_moves_for()` instead: their first 1-2 plain shots only (no
specials, no telegraphs, quiet sound; elites x1.08 speed / x0.9 cooldown). Trash has plain shots everywhere):

| Kind | Moves |
|---|---|
| cinder_colossus | Magma Slam [zone], Flame Sweep [cone], Ember Rain* [zone], Cinder Fist, Crossfire* [zone] |
| rubble_warlord | Triple Charge [dash], Boulder Toss [zone], Rally* [ring], Crossfire* [zone] |
| ashreach_revenant | Soul Spiral, Grave Hands [zone], Ash Orbit* [ring], Crossfire* [zone] |
| thornrock_colossus | Quake [zone], Thorn Wall [line], Root Burst* [zone], Pebble Fan, Crossfire* [zone] |
| ashenreach_devourer | Lunge Chain [dash], Maw Cone [cone], Split Spit*, Crossfire* [zone] |
| choir_sovereign | Choir Wall [line], Echo Volley, Crescendo* [ring], Crossfire* [zone] |
| coral_leviathan | Tidal Beam [line], Bubble Mines, Surge Charge* [dash], Crossfire* [zone] |
| tideglass_warden | Mirror Lances [line], Glass Orbit [ring], Shatter Nova* [ring], Crossfire* [zone] |
| driftbell_matriarch | Bell Toll [ring], Call the Tide [ring], Drift Homers*, Bell Chime, Crossfire* [zone] |
| abyssal_choirmaster | Dirge Wall [line], Abyss Pull, Silence* [zone], Low Note, Crossfire* [zone] |
| boss (Vault Guardian) | Aimed Shotgun, Grenade Barrage [zone], Gapped Spin* [ring], Crystal Rage+ [ring], Crossfire* [zone] |
| frost_monarch | Ice Lances [line], Blizzard, Hailstones, Frozen Floor* [zone], Glacial Nova+ [ring], Crossfire* [zone] |
| ash_behemoth | Behemoth Flame [cone], Magma Meteors [zone], Molten Charge* [dash], Eruption+ [zone], Crossfire* [zone] |
| void_reaper | Scythe Boomerangs, Blink Slash [dash], Summon Shades* [ring], Void Spiral+ [ring], Crossfire* [zone] |
| thorn_warden | Root Pulse [zone], Thorn Walls [line], Seed Mines*, Vine Lash+, Thorn Shot, Crossfire* [zone] |
| sand_wyrm | Sand Spit, Tail Sweep, Sandstorm* [ring], Dune Collapse+ [zone], Crossfire* [zone] |
| mad_god | Star Shotgun, Minion Grenades [zone], Blade Burst [ring], Gathering Power* [ring], Madness Spiral+ [ring], Crossfire* [zone] |
| Realm elites | thornling Seed Pods / Thorn; scorpion Pincer Spray / Stinger [line]; dune_stalker Sand Burrow [ring] / Dune Lunge [dash]; yeti Snowball / Avalanche Slam [zone]; frost_sprite Icicle Weave / Frost Blink; ghost Wisp Pair / Fade; troll Club Bolt / Boulder Lob [zone]; bog_crawler Poison Glob [zone] / Bog Spiral; skeleton Bone Boomerangs / Rattle Burst; harpy Feather Strafe / Talon Dive [dash]; cliff_strider Cliff Leap [zone] / Rock Chip; salamander Flamethrower [cone] / Spit; cinder_wisp Kindling / Flare Fan; panther Claw Flick / Pounce [dash]; vine_serpent Serpent Stream / Vine Snare [line]; ghoul Rot Orbs / Vomit [cone]; husk_wanderer Husk Wall [line] / Shamble Charge [dash]; frost_wraith Frost Sweep / Chill; glacier_shard Ice Lance [line] / Shard Split; cave_lurker Ambush / Lurker Lunge [dash]; deep_stalker Quick Shot / Sniper Shot [line] |
| Island elites | shard_sentinel Shard Burst / Cross Beam [ring]; echo_knight Echo Lance [line] / Echo Strike; shattered_golem Golem Slam [zone] / Splitting Stone; fracture_hound Fracture Bite / Zigzag Charge [dash]; stone_revenant Orbit Shards [ring] / Grave Chip; cinder_warden Warden Flame [cone] / Cinder Grenade [zone] / Call the Embers [ring]; coral_sentinel Coral Buckshot / Reef Spiral; drowned_custodian Undertow Slam [zone] / Anchor Toss; kelp_stalker Kelp Stream / Snare Bolt [line]; shellback_guardian Shell Up [ring] / Shell Shot; siren_wraith Lure / Siren Waves; choir_warden Choir Charge [dash] / Wave Arc [ring] / Call the Tide [ring] |
| Trash (plain shots, no telegraph) | imp Ember Flick; goblin Rock Throw; bat Screech Dart; ember_wisp Ember Pair; fury_shard Shard Triplet; rubble_crawler Heavy Pebble; spite_spirit Spite Wave; tide_wisp Drift Shot; pearl_acolyte Pearl Pair; brine_crawler Brine Boomerang; abyssal_chorister Hum Fan |

Bullet motions: straight, boomerang, sine, accel (speed up / slow to a stop / stop-and-re-aim mines), homing (capped
turn rate), split (bursts into shards when its life ends). Bosses and mini-bosses enrage below 50% HP with a 0.8 s
roar (no damage taken), then faster cooldowns.

Phase-2 variants of the six bosses: x1.75 HP, x1.4 damage, faster cooldowns, plus their `+` move. Island mini-bosses (x1.8 scale, 560-640 HP): cinder_colossus,
choir_sovereign, rubble_warlord, coral_leviathan, ashreach_revenant,
tideglass_warden, thornrock_colossus, driftbell_matriarch,
ashenreach_devourer, abyssal_choirmaster. Landmark guardians are drawn and
hit at x1.5. Enemy HP also scales with distance to the continent centre (up
to +120%) and x1.15 per completed story act (max x1.6).

### Dungeons (`game/realm_sim.py` `DUNGEON_THEMES`, `BONUS_DIFFICULTIES`)

| Theme | Boss pool |
|---|---|
| Forgotten Vault (generic) | all six bosses |
| Cave Warren | void_reaper |
| Frozen Crypt | frost_monarch |
| Jungle Ruins | boss, ash_behemoth, thorn_warden |
| Ember Den | ash_behemoth, sand_wyrm |
| Sunken Grotto | boss, thorn_warden |
| Wind Spire | boss, void_reaper, sand_wyrm |
| The Forge (story finale) | mad_god |

Difficulty: Easy HP x1.15 / cap 10 / 1 loot roll, Medium x1.6 / 13 / 2,
Hard x2.3 / 16 / 3. Secret "???" quest chance 30% (not in the Forge).
Dungeon Shards drop from 8% of elite kills (always from inner-biome
Landmark Guardians).

### Story (`game/story.py`)

| Act | Objectives |
|---|---|
| Prologue: Welcome, Sucker | Talk to Father Given (F); step through the Realm portal |
| Act I (old arc; now Act II "Bouncer Problems") | Defeat the Guardians of the Sunken Idol (forest), Buried Obelisk (desert), Frozen Watchpost (tundra), Drowned Shrine (swamp) |
| Act II: Last Call | Calm any 7 islands |
| Act III: The Deep End | Defeat 4 inner-biome Landmark Guardians; clear 3 dungeons |
| Finale: Closing Time | Defeat the Mad God in the Forge |

`act_scale`: 1.0, 1.15, 1.3, 1.45, 1.6 (then capped).

### Side quests (`game/sidequests.py`)

Board of 3 random quests drawn from the 15 giver-less ones; the other 15 are
given by NPCs. Quest items: Glowcap Mushroom, Camel Bell, Driftwood Rum,
Ember Core.

| Quest | Goal | Giver | Reward |
|---|---|---|---|
| Herd Whisperer | Stand among 3+ deer for 10 s | board | 160 XP, 1 Echo, elite loot |
| Hare Census | Stand near 2+ forest hares for 8 s | board | 120 XP, 1 Echo, elite loot |
| Birdwatcher | Stand near songbirds in 2 biomes | board | 180 XP, 1 Echo, elite loot |
| Pest Control | Slay 15 goblins | board | 220 XP, 1 Echo, elite loot |
| Yeti Tag | Defeat 3 yetis without dying | board | 260 XP, 2 Echoes, elite loot |
| Island Hopper | Set foot on 5 islands | board | 300 XP, 2 Echoes, elite loot |
| Chest Raider | Open 3 island chests | board | 260 XP, 2 Echoes, elite loot |
| Dungeon Crawl | Clear 2 dungeons | board | 400 XP, 2 Echoes, boss loot |
| Snack Time | Feed your pet 5 items | board | 120 XP, 1 Echo, elite loot |
| Night Watch | Survive a whole night in the Realm | board | 250 XP, 2 Echoes, elite loot |
| Lizard Race | Stand near 2+ desert lizards for 6 s | board | 130 XP, 1 Echo, elite loot |
| Heron Haiku | Talk to 3 marsh herons | board | 150 XP, 1 Echo, elite loot |
| Mini-boss Menace | Defeat 2 island mini-bosses | board | 450 XP, 3 Echoes, boss loot |
| Guardian Groupie | Defeat 2 Landmark Guardians | board | 400 XP, 2 Echoes, boss loot |
| World Boss Witness | Be near when a world boss falls | board | 500 XP, 3 Echoes, boss loot |
| Flamingo Gossip | Get gossip from the Gossiping Flamingos | Captain Driftwood | 140 XP, 1 Echo, elite loot |
| Tortoise Wisdom | Hear all 3 of the Tortoise's tales | Philosopher Tortoise | 200 XP, 2 Echoes, elite loot |
| Mossbeard's Mushrooms | Bring 6 Glowcaps from forest monsters | Old Mossbeard | 260 XP, 2 Echoes, elite loot |
| Sal's Lost Camel Bell | Find the bell in an island chest | Sandy Sal | 280 XP, 2 Echoes, elite loot |
| Ice Fishing Derby | Catch 5 things in tundra/ice | Frostine | 220 XP, 2 Echoes, elite loot |
| Captain's Rum Run | Bring 3 Driftwood Rum from island chests | Captain Driftwood | 320 XP, 2 Echoes, elite loot |
| Bog Brew | Slay 8 bog crawlers | Madame Murk | 240 XP, 2 Echoes, elite loot |
| Monk's Pilgrimage | Visit 4 landmarks | Brother Tipsy | 300 XP, 2 Echoes, elite loot |
| Hot Iron | Bring 3 Ember Cores (salamanders, cinder wisps) | Cinder Pete | 300 XP, 2 Echoes, elite loot |
| Fern Samples | Visit 3 jungle spots | Professor Fernleaf | 260 XP, 2 Echoes, elite loot |
| Scrap for Rusty | Defeat 10 husk wanderers | Rusty | 260 XP, 2 Echoes, elite loot |
| Map the Deep | Chart 3 cave spots | Glimmer | 280 XP, 2 Echoes, elite loot |
| Moth to a Flame | Stand near cave moths at night for 6 s | Mushroom Folk | 200 XP, 2 Echoes, elite loot |
| Barkeep's Tab | Talk to 5 different people | Barkeep Bitterwick | 200 XP, 2 Echoes, elite loot |
| Elk Escort | Walk with the Grand Elk Herd for 30 s | Grand Elk Herd | 240 XP, 2 Echoes, elite loot |

### NPCs and areas (`game/npcs.py`, `game/areas.py`)

| NPC | Where |
|---|---|
| Barkeep Bitterwick | Nexus tavern |
| Old Mossbeard | Tavern Town |
| Sandy Sal | Oasis Bazaar (desert) |
| Frostine the Ice Fisher | Frozen Lake Camp (tundra) |
| Captain Driftwood | the arrival beach |
| Madame Murk | Witch's Hollow (swamp) |
| Brother Tipsy | Mountain Monastery (highlands) |
| Cinder Pete | Forge Camp (ashlands) |
| Professor Fernleaf | Botanist's Glade (jungle) |
| Rusty the Scrap Golem | Scrapyard (wasteland) |
| Glimmer the Cartographer | Crystal Caverns (cave) |
| Grand Elk Herd (creatures) | Elk Meadow (forest) |
| Gossiping Flamingos (creatures) | a swamp vignette |
| Philosopher Tortoise (creature) | Oasis Bazaar |
| Mushroom Folk (creatures) | Crystal Caverns |

If an area doesn't fit on a map, its NPC stands at the biome's landmark
instead (`npcs.FALLBACK_LANDMARK`). Talk radius 72 px. Talkable wildlife:
deer, forest hare, songbird, desert lizard, marsh heron, cave moth, elk,
mountain goat, snow fox, scrap rat, tree frog, fire beetle, flamingo, ice
penguin, mushroom folk, tortoise.

Big areas (tiles): Tavern Town 50x46, Oasis Bazaar 46x44, Frozen Lake Camp
46x44, Witch's Hollow 44x42, Mountain Monastery 46x44, Forge Camp 44x42,
Botanist's Glade 44x42, Scrapyard 46x42, Crystal Caverns 44x42, Elk Meadow
48x44. Nexus districts: tavern, park, dockside, arena.

Islands (`realm_sim.ISLAND_NAMES`, ~100x100 tiles each): Emberball Shard,
Coral Colada Choir, Frostquiri Shard, Pearlini Spire, Bonshine Shard,
Tidricane Sanctum, Thorn-on-the-Rocks Shard, Driftai Cloister, Ashioned
Shard, Abyssal Rumnal. Each island's wave re-arms every 300 s.

### World, events and economy

- Realm 1308x1308 tiles (900x900 continent + 204-tile ocean ring each
  side), 200 lairs, day length 240 s, 30 Hz co-op tick.
- World boss every 15-25 min, HP x(2.4 + 0.18 x average level); Mad God's
  Avatar every 40 kills.
- Live events (25-min slots): none, Double Loot Weekend, none, Happy Hour
  (+50% XP), none, Blood Moon Week, none, Two-for-One Tuesday (double loot,
  +25% XP).
- Echoes: 1 per 1000 XP. Echo shop: +1 backpack slot 60 then 120 Echoes
  (max 2 extra), starting-XP boost 30 Echoes.
- Vault: 12 chests x 8 slots. Permanent potions: 20 per character;
  temporary potions +6 for 60 s. Trade confirm countdown 3 s.

## History of this file

- **v0.2 (first snapshot)**: 8 achievements, flat `+14 HP / +10 MP / +4 one
  stat` per level, four per-zone music themes.
- **Changes since, all still v0.2**: family-tinted mob barks with a 20 s
  re-bark limit; class-archetype growth ranges; the `reforger` achievement;
  per-zone ~20 s themes (Batch 14), then the 23 one-minute tracks above;
  pets, bosses, story, side quests, NPCs and areas added as listed.
- **"Final final" content update (still v0.2)**: the 7-act story (Act I renamed
  "The Grand Tour"), T12-T14 + Divine items, the Anvil, Heroic dungeons + trials,
  ~260-tile islands, the Mad God's Room, 10 new tracks, 13 new event sounds.

## Audio file exports

Sound effects are synthesized at runtime. `tools/export_audio.py` renders
every effect (plus one file per family variant of the mob sounds) to `.wav`
under `assets/audio_export/` for reference. They are `.wav`, not `.mp3`:
MP3 would need an external encoder, and the project is deliberately
pygame-only. Re-run the tool whenever the synthesis changes.
