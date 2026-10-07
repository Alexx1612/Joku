# 35 - Night horror, precise combat, Weapon Shards / Bag 2, night realism and the Light of RDV

"V0.2 final final" session, after doc 34. Everything here sits on top of the Realm's existing day/night code.

## 1. The cycle and the time bar (`realm_sim`)
- **Cycle:** `DAY_LENGTH` = 600 s. The day runs until `DUSK_START` 300, the night is `NIGHT_START` 330 to `NIGHT_END` 540, and the dawn ends at `DAWN_END` 570.
  `NIGHTFALL_T` 315 / `DAYBREAK_T` 555 are where the light crosses 0.5. That gives ~4 minutes of `light < 0.5`.
- **Blood Moon:** `BLOOD_MOON_NIGHT_SPEED` = 1.4, so its night lasts ~3 minutes.
- **Helpers:** `day_phase_at(t)` / `sim.phase()` return day/dusk/night/dawn. `clock_info()` returns the phase,
  `until`/`left` (the countdown), night/blood flags, the night event, `light_mult`, and the realism fields (section 8).
  Co-op snapshots carry it.
- **Time bar:** `ui.draw_day_night_clock` is a segmented strip:
  - gold for day, orange for dusk and dawn, navy for night, crimson for a Blood Moon
  - a moving sun/moon icon, plus a moon-phase disc at the top right
  - a big "NIGHT FALLS IN m:ss" / "DAWN IN m:ss" label that pulses red in the last 30 s before night

  `ui.draw_night_countdown` puts a compact copy at the top centre during dusk, night and dawn.

## 2. Darkness, lights and Luminosity (`game/lighting.py`, `ui.draw_day_night_overlay`)
- **Light map:** a multiplied light map, built at 1/3 resolution and smooth-scaled up.
  - **Ambient:** `lighting.ambient_color(light, luminosity, blood)` is moon-blue, or crimson on a Blood Moon.
  - **Lights:** every light is added with flicker and a per-source colour: lamps amber, fireflies green-gold, glowing mobs in their own hue.
- **Luminosity:** `settings["luminosity"]` defaults to 0.5 and is a slider under Display. It affects night darkness only: 0 is pitch black outside lights, 1 is nearly clear.
- **Player light:** `ui.PLAYER_LIGHT_RADIUS` = 175 px, centred on the player's real screen position.
- **Wall occlusion:** the player light and the nearest lights cast rays over the tile grid. Walls, trees and closed doors cast real shadows. The result is cached per tile/doors version.
- **Light sources:** `sim.light_sources_near(pos, tiles)` returns:
  - lamp posts, campfires, braziers and lanterns (`world.nearby_lights`)
  - glowing creatures (`entities.GLOWING_KINDS`)
  - fireflies: neutral swarms in forest, swamp and jungle at night only
  - house windows at night (section 8)
- **Emissive layer:** night mobs' `enemy_<kind>_glow.png` (eyes, lure, scythe edge) is drawn after the darkness with additive blending, so you see eyes beyond your light (`ui.draw_night_emissives`).

## 3. Safe houses and doors
- **Doors:** `world.DOOR_CLOSED` (2600, solid) / `DOOR_OPEN` (2601). F next to a door toggles it for any player.
  Co-op uses the server `toggle_door` action. The snapshot `doors` list is patched into the client tilemap, and the map is never resent.
- **Mobs:** they use `sim.enemy_view`, which treats every door tile as a wall. They never path through, and their bullets stop at closed doors.
- **Houses:** `sim.safe_houses = [{rect, interior, doors}]` lists every hut, tavern and hall, plus wayside shacks in each biome.
- **Sheltered:** a player on interior tiles with every door of that house closed is sheltered:
  - mobs can't target or see them
  - night spawns and events skip them
  - faster regen
  - a "SAFE - Sheltered" badge

## 4. Night rules, events, night mobs, the Blood Moon (`game/night.py` `NightDirector`)
- **Night rules:** `NIGHT_RULES` = aggro x1.6 (x2.0 in the dark), leash x1.5, speed x1.15, damage x1.2, cooldowns x0.85.
  On a Blood Moon, `BLOOD_RULES` = 2.2 / 2.6 / 2.0 / 1.25 / 1.35 / 0.75. Everything is restored at dawn.
- **Events:** one per non-Blood-Moon night (`EVENTS`):

| Event | Effect |
|---|---|
| The Fog | light x0.6 (`FOG_LIGHT_MULT`), fog veil, more stalkers |
| Something Is Hunting You | a buffed Shade Stalker "Hunter" tracks one player |
| The Lanterns Go Out | every lamp is dark |
| Midnight Market | the Ghost Merchant trades 3 gear items for 1 a tier higher |
| **The Lamplighter** | section 9 |

- **Night mobs** (`entities.NIGHT_MOB_KINDS`; night-only, spawned out of the light, gone at dawn):

| Mob | What it does |
|---|---|
| Lantern-Eater | snuffs lamps until dawn |
| Shade Stalker | invisible outside any light |
| Night Mimic | a loot bag until you get close |
| Hollow Watcher | shrieks, summons and calls nearby mobs |

- **Blood Moon:**
  - **Chance:** `BLOOD_MOON_CHANCE` = 0.12, doubled on a full moon.
  - **Hordes:** a horde of 6-10 moonlit mobs every 30 s, in a ring 11-14 tiles out.
  - **Boss:** **The Red Harvester** at the halfway mark (Reap, scythe walls, blood rain).
  - **Feel:** red darkness, a heartbeat, blood rain.
  - **Rewards:** the `blood_moon` loot source, and +400 XP for surviving.
- **Music:** "Witching Hour" for a normal night, "Red Harvest" for the Blood Moon.

## 5. Precise combat
- `entities.PLAYER_FIRE_RATE_MULT` = 0.55 on the attack interval.
- `realm_sim.PLAYER_DAMAGE_MULT` = 1.8 on rolled damage. DPS is about the same, but every hit counts double.
- Aim assist cone `AUTO_AIM_CONE_DEG` goes 16 -> 7.
- Heavy hits get a bigger popup, a heavier sound and a little more hit-stop.

## 6. Weapon Shards (`game/runes.py`, item slot `"rune"`)
- **Slots:** 12 in the dock's **Shards** tab. The top 4 are active sockets that apply to the equipped weapon.
- **Effects:** bleed, burn, vulnerable, frostbite, chain, keen, leech, splinter, seeker, impact, executioner, echo.
- **Rarity:** common / rare / epic / mythic, with magnitude x1.0 / 1.4 / 1.9 / 2.6. When the same effect is socketed twice, the best rarity counts, plus 15% per extra.
- **Drops:** elites 4%, bosses 25%. Night kills drop them at x2.5 the rate and Blood Moon kills at x4 (`items.RUNE_SOURCE_MULT`).
- **Fusing:** the Anvil fuses 3 shards of the same rarity into 1 of the next rarity.
- **Old saves:** `socketed_proc` and UT procs still work.

## 7. Bag 2 and the four dock tabs
- **Tabs:** Items -> Bag 2 -> Shards -> Pet. Cycle them with Tab, or click a tab. Dragging an item onto a tab label switches to it.
- **Bag 2:** `Player.backpack2` (12 slots). Pickups overflow into it when the main backpack is full.
- **Co-op:** the generic server `move_item {from, to}` action moves items between every container.

## 8. Night realism pass
Research sources:
- [day/night cycle design](https://salivity.github.io/game-development/article/how-game-developers-create-realistic-day-night-cycles)
- [the cycle as a design tool](https://www.designthegame.com/learning/tutorial/day-night-cycles-powerful-design-tool-game-development)
- [a real-time cycle devlog](https://usagishima.net/2021/04/13/devlog-2-real-time-day-night-cycle/)
- [golden hour](https://en.wikipedia.org/wiki/Golden_hour_(photography))
- [top-down 2D light and shadow](https://catlikecoding.com/godot/true-top-down-2d/4-light-and-shadow/)

What it adds:

| Idea | Where |
|---|---|
| **Golden hour**: a warm colour grade for ~75 s before dusk and after dawn, plus a low-sun glow on the west (dusk) or east (dawn) edge | `sim.sky_grade()`, `ui.draw_sky_grade`, `lighting.set_grade` |
| **Blue hour**: a cool tint just after the sun sets and just before it rises | same |
| **Moon phases**: an 8-night cycle (`night_count`). A full moon lights the night (+`MOON_LIGHT`) and doubles the Blood Moon chance; a new moon is darkest. Phase disc on the time bar | `moon_phase()`, `lighting.ambient_color` |
| **Dawn mist**: low mist for about a minute around sunrise | `ui.draw_dawn_mist` |
| **Lit windows**: every house glows amber from inside at night | `house_light_points()`, `clock_info["house_lights"]` |
| **Day animals sleep** at night: no wandering, a drifting "z z" | `DIURNAL_WILDLIFE`, `Enemy._asleep`, snapshot `zz` |
| **Town folk go indoors** at night and come back out at dawn | `sim._npc_schedules()` |
| **Eye adaptation**: your light starts at 62% at nightfall and widens over ~25 s; leaving a bright lamp dazzles you back to 72% | `game/eyes.py` |
| **Night ambience**: crickets, an owl, distant howls under a Blood Moon, a bird chorus at dawn | `audio.night_ambience` |

## 9. The Lamplighter and the Light of RDV ("real diagonal vision")
- **The event:** "The Lamplighter" is a night event. Old Wick (`npcs.NPCS["lamplighter"]`, an original sprite) appears in a named area and relights snuffed lamps he walks past.
- **Waves:** every 24 s the dark sends a wave of 4 Shade Stalkers or Lantern-Eaters (6 on a Blood Moon) flagged `ward_target`. They go for him, not for players.
- **His health:** 420 HP, shown as a bar above him. The bar is drawn after the darkness, and co-op gets it as snapshot `hpf`. Contact and enemy bullets hurt him.
- **Helpers:** any player who comes within 900 px of him during the night counts as a helper.
- **At dawn, if he survived:** every helper gets the **Light of RDV** (`items.make_rdv_ring`). It goes to the backpack, then Bag 2, then pending items.
  - It's a UT ring: WIS +6, VIT +4, DEX +3, `aura="rdv"`.
  - **Vision:** your light radius is x1.6 (`RDV_VISION`), and so is the radius in which Shade Stalkers become visible.
  - **Fear:** any non-boss monster within 240 px (`RDV_FEAR_RADIUS`) loses its nerve. It drops aggro, cancels its wind-up and backs away (`sim._rdv_scared`).
- **If he dies:** the lamps go dark and nobody gets a ring.

## 10. Mobs no longer spawn on top of you
`_find_spawn_pos_near(anchor, min_px, max_px, avoid_players, safe_px)` was being passed tiles as pixels.
- **Fix:** every caller now passes pixels.
- **Floor:** no hostile spawn lands within `MIN_SPAWN_DIST_FROM_PLAYER` = 380 px of any player.
- **Blood Moon:** hordes spawn in a ring 11-14 tiles out.

## 11. Night realism pass 2: the sky and what lives under it (`game/night_sky.py`, `game/sky_fx.py`)
- **Golden-hour light:** superseded by doc 39 §3. It is now a soft vertical band of warm light that travels left to right over dusk and right to left over dawn. The screen-wide glow was too strong.
- **Night weather:** each normal night rolls one of four kinds (`NIGHT_WEATHER`):

  | Weather | Chance | Ambient light | Moon | Light radius |
  |---|---|---|---|---|
  | clear | 45 | x1.0 | normal | x1.0 |
  | cloudy | 25 | x0.72 | hidden | x1.0 |
  | rain | 18 | x0.62 | hidden | x0.85 |
  | storm | 12 | x0.55 | hidden | x0.8 |

  It's announced at nightfall and clears at dawn. Rainy and stormy nights rain everywhere except snow, sand and ash biomes (`SkyFX.rain_kind`), with a rain patter sound.
- **Lightning:** storms strike every 6-16 s within 12 tiles of a player. The darkness lifts (`SkyFX.light_boost`) with a second flicker, a jagged bolt is drawn, and a cold wash and thunder play. Co-op uses the `bolt` sequence in `clock_info`.
- **Shooting stars:** on clear, non-Blood-Moon nights there's a 40% chance every 16 s. 30% of those fall: a glowing Star Fragment lands 14-28 tiles away, and each player gets "...falls to the ground - north-east of you!". The fragment glows as a light source until picked up.
  - **Using it:** a 50% chance of an extra loot roll on every kill for 4 minutes (`STAR_LUCK_CHANCE`).
- **Night-blooming herbs:** Moonpetal (forest, highlands) and Ghostbloom (swamp, jungle). They're night-only glowing plants, 3 near each player. F picks one (`NightSky.gather_herb`; co-op uses the server `fish` action). You can't talk to them.
  - **Moonpetal:** heals 25% and gives +30% light for 2 minutes.
  - **Ghostbloom:** heals 50% and gives +8 VIT for 1 minute.
- **Owls:** night-only, 2 near each player, perched in forest, highlands, tundra, jungle and swamp. Their amber eyes glow in the dark and they hoot now and then. If you come within 130 px they flap off and vanish.
- **Frost sparkle:** on snow and ice at night, frost glints twinkle in the moonlight around you (drawn above the darkness).
- **New sounds:** thunder, rain_start, rain_patter, shooting_star, owl_flap, herb_pick. **New VFX:** lightning, star_land, herb_pick.
- **Fix:** the top countdown hides while a zone title card is showing. The two used to overlap.

## Tests
- `check_night_horror`
- `check_night_lightmap`
- `check_night_art`
- `check_combat_precision`
- `check_weapon_shards`
- `check_dock_tabs`
- `check_night_sky`: golden sweep, weather, lightning, shooting stars and fragments, luck, herbs, owls, frost, sounds
- `check_night_realism`: grade, moon, windows, sleeping animals, NPC schedules, eyes, ambience, RDV, the Lamplighter, the spawn floor

## Not done (ideas for later)
All six earlier ideas are now built (section 11).
