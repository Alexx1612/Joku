# Game data reference (per version)

A versioned snapshot of the game's data tables - sound effects, music,
achievements, class stats, abilities, pets, bosses, dungeons, story, side
quests, NPCs and areas - so there's a historical record as these change,
not just whatever's currently in the code. Numbers are read from the code
(file named in each heading). Update this alongside README.md's version
history when any of them change.

## Ends of V0.2 (current - still v0.2, release tag `v0.2`)

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

**Attack sets** (`game/enemy_attacks.py` `ATTACKS`; `*` = added when enraged below 50% HP, `+` = phase-2 room only;
telegraph in brackets: line/dash = red, zone/cone = orange, homing = purple, no bracket = glow on the mob only):

| Kind | Moves |
|---|---|
| boss (Vault Guardian) | Aimed Shotgun, Grenade Barrage [zone], Gapped Spin* [ring], Crystal Rage+ [ring] |
| frost_monarch | Ice Lances [line], Blizzard, Frozen Floor* [zone], Glacial Nova+ [ring] |
| ash_behemoth | Behemoth Flame [cone], Magma Meteors [zone], Molten Charge* [dash], Eruption+ [zone] |
| void_reaper | Scythe Boomerangs, Blink Slash [dash], Summon Shades*, Void Spiral+ [ring] |
| thorn_warden | Root Pulse [zone], Thorn Walls [line], Thorn Shot, Seed Mines*, Vine Lash+ |
| sand_wyrm | Sand Spit, Tail Sweep, Sandstorm* [ring], Dune Collapse+ [zone] |
| mad_god | Star Shotgun, Minion Grenades [zone], Blade Burst [ring], Gathering Power* [ring], Madness Spiral+ [ring] |
| cinder_colossus | Magma Slam [zone], Flame Sweep [cone], Cinder Fist, Ember Rain* [zone] |
| choir_sovereign | Choir Wall [line], Echo Volley, Crescendo* [ring] |
| rubble_warlord | Triple Charge [dash], Boulder Toss [zone], Rally* (summon) |
| coral_leviathan | Tidal Beam [line], Bubble Mines, Surge Charge* [dash] |
| ashreach_revenant | Soul Spiral, Grave Hands [zone], Ash Orbit* [ring] |
| tideglass_warden | Mirror Lances [line], Glass Orbit [ring], Shatter Nova* [ring] |
| thornrock_colossus | Quake [zone], Thorn Wall [line], Pebble Fan, Root Burst* [zone] |
| driftbell_matriarch | Bell Toll [ring], Call the Tide (summon), Bell Chime, Drift Homers* |
| ashenreach_devourer | Lunge Chain [dash], Maw Cone [cone], Split Spit* |
| abyssal_choirmaster | Dirge Wall [line], Abyss Pull, Low Note, Silence* [zone] |
| Realm elites & trash | goblin Rock Throw / Rock Lob [zone]; imp Ember Flick / Cinder Triplet; bat Screech Swoop [dash]; thornling Seed Pods / Thorn; scorpion Pincer Spray / Stinger [line]; dune_stalker Sand Burrow / Dune Lunge [dash]; yeti Snowball / Avalanche Slam [zone]; frost_sprite Icicle Weave / Frost Blink; ghost Wisp Pair / Fade; troll Club Bolt / Boulder Lob [zone]; bog_crawler Poison Glob [zone] / Bog Spiral; skeleton Bone Boomerangs / Rattle Burst; harpy Feather Strafe / Talon Dive [dash]; cliff_strider Cliff Leap [zone] / Rock Chip; salamander Flamethrower [cone] / Spit; cinder_wisp Kindling / Flare Fan; panther Pounce [dash]; vine_serpent Serpent Stream / Vine Snare [line]; ghoul Rot Orbs / Vomit [cone]; husk_wanderer Husk Wall [line] / Shamble Charge [dash]; frost_wraith Frost Sweep / Chill; glacier_shard Ice Lance [line] / Shard Split; cave_lurker Ambush / Lurker Lunge [dash]; deep_stalker Sniper Shot [line] |
| Island elites & trash | cinder_warden Warden Flame [cone] / Cinder Grenade [zone] / Call the Embers; choir_warden Choir Charge [dash] / Wave Arc / Call the Tide; shard_sentinel Cross Beam; echo_knight Echo Strike; shattered_golem Golem Slam [zone] / Splitting Stone; fracture_hound Zigzag Charge [dash]; stone_revenant Orbit Shards / Grave Chip; coral_sentinel Coral Buckshot / Reef Spiral; drowned_custodian Anchor Toss; kelp_stalker Kelp Stream / Snare Bolt [line]; shellback_guardian Shell Up / Shell Shot; siren_wraith Siren Waves; ember_wisp Ember Trail / Wisp Dart [dash]; fury_shard Shard Triplet; rubble_crawler Grenade [zone] / Pebble; spite_spirit Spite Orb; tide_wisp Drift Shot; pearl_acolyte Pearl Stop; brine_crawler Bubble Lob [zone] / Brine Spit; abyssal_chorister Sound Wall [line] / Hum |

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
| Act I: The Rim Job | Defeat the Guardians of the Sunken Idol (forest), Buried Obelisk (desert), Frozen Watchpost (tundra), Drowned Shrine (swamp) |
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

## Audio file exports

Sound effects are synthesized at runtime. `tools/export_audio.py` renders
every effect (plus one file per family variant of the mob sounds) to `.wav`
under `assets/audio_export/` for reference. They are `.wav`, not `.mp3`:
MP3 would need an external encoder, and the project is deliberately
pygame-only. Re-run the tool whenever the synthesis changes.
