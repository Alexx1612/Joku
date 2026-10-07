# 39 - Danger by distance, the Calendar, the low-sun light band, the complete Dictionary

"V0.2 final final" session, after doc 38 (admin commands).

## 1. Danger by distance (`game/danger.py`)
The user asked: "mobs much more dangerous closer to the center of the map but easier for the edges ... same for night mobs
and portals they drop, monsters inside the center drop much more dangerous dungeons".

- **Measure:** `danger_frac(x, y, map_w, map_h)` is `1 - distance from the map centre / world.CONTINENT_R`, so 1.0 at the
  centre and 0.0 at the continent's radius.
  - Beyond `OCEAN_SLACK` (x1.06) it returns **None**: the ocean ring and the big islands keep their own level-20 scaling (doc 34).
  - Dungeons also return None (`RealmSim.danger_at`).
- **Tiers** (`tier(frac)`, 1-5): Calm, Mild, Wild, Deadly, Lethal, each 20% of the radius.
- **Applying it:** `RealmSim._apply_danger()` runs once per hostile (`_danger_done`), every tick, just before the night
  director. It covers every spawn path (lairs, waves, guardians, world bosses, night mobs, hordes, admin spawns) without
  touching each one.
  - If the night rules already captured the mob's `_day_stats`, those are scaled too, so dawn restores the
    danger-scaled stats.
  - Neutral wildlife is untouched.

| From coast (0) to centre (1) | Multiplier |
|---|---|
| HP | 0.6 + 1.6 f^1.2 (x0.6 .. x2.2) |
| damage | 0.65 + 0.85 f (x0.65 .. x1.5) |
| speed | 0.92 + 0.16 f |
| attack cooldowns (`fire_rate_mult`) | 1.15 - 0.30 f |
| aggro range | 0.9 + 0.35 f |
| XP | 0.8 + 0.8 f |
| extra loot roll chance | max(0, f - 0.4) x 0.9 (0 .. 54%) |
| elite Dungeon Shard chance | 0.05 + 0.08 f (5% .. 13%), replacing `MOB_PORTAL_CHANCE` on the continent |

- **Continent lairs:** these used their own HP gradient (`difficulty_scale`, up to +120%). They now spawn at
  `hp_scale` 1.0 and let the danger pass do the scaling. `difficulty_scale` is kept only to rank lairs for the landmark
  buildings. Island camps keep `ISLAND_CAMP_SCALE`.
- **Dungeons from the centre:** a dropped shard stores its tier (`Item.danger`, saved in JSON).
  - `Player.use_shard` remembers it, and `shard_difficulty(theme, tier)` weights Easy/Medium/Hard by
    `SHARD_DIFFICULTY_WEIGHTS`. Tier 1 is 85/15/0; tier 5 is 5/35/60.
  - At tier 5 a level-16+ killer's shard is Heroic 8% of the time (`HEROIC_SHARD_CHANCE_T5`).
  - The shard's tooltip says what to expect.
- **Night:** night mobs get the same scaling, and night spawns come x1.25 slower at the coast and x0.75 at the centre
  (`night._tick_spawns`).
- **HUD:**
  - Under the minimap: the tier name plus 5 pips in its colour.
  - On the full map (M): rings at the tier boundaries, each band labelled at the four compass points, "Calm" outside
    the last ring.
  - Both appear only on the Realm map (`minimap.REALM_MIN_TILES`). Co-op clients compute them locally.

## 2. The Calendar (`RealmSim.forecast_view`, `game/calendar_ui.py`, K)
- **How nights are decided:** each coming night is fixed ahead of time but resolved at nightfall.
  - `RealmSim.forecast` holds `FORECAST_NIGHTS` (7) entries of pre-drawn dice: `u_blood`, `u_weather`, `u_event`.
  - At nightfall the first entry is popped and `_resolve_night` turns it into tonight. It uses the rules in force:
    the Blood Moon chance (with pity counter, full-moon x2 and the live-event multiplier), the `night_sky.NIGHT_WEATHER`
    weights and `night.EVENTS`.
  - The result goes to `sim.tonight`, and the night director and night sky read its event and weather.
  - Admin commands and tests can still force anything. `reroll_forecast()` draws fresh dice.
- **What `forecast_view()` shows:** it resolves every entry the same way, simulating the pity counter forward and
  checking the live event due at each predicted nightfall (`live_events.multiplier_at`). So the Calendar is exactly
  what happens; `tests/check_danger_and_calendar` plays 3 nights to prove it.
- **When each night falls:** nightfalls are `_seconds_to_nightfall()` plus whole days (a Blood Moon day is shorter).
- **Co-op:** `clock_info["forecast"]` is a compact list refreshed once a second, plus `night_no`.
- **Live events:** `live_events.upcoming(n)` lists the fixed real-time schedule slots (`multiplier_at` reads the
  multiplier at a future time).
- **The window** (K, Esc closes, single-player and co-op):
  - 7 rows: night number / "Tonight", time until it falls, a moon phase disc and name, a weather icon and name, the event
    name with a one-line hint. Blood Moon rows are red.
  - The next 5 live-event slots, with when each starts.

## 3. Dawn and dusk light (`ui.draw_sky_grade`)
- **History:** the first version was a warm gradient at one screen edge. The user asked for it "around the screen, moving
  west to east"; that came out too strong and screen-wide. They then clarified it should come "from left to right (or
  right to left) and not that bright and screen wide to simulate reality".
- **Now:** a soft vertical band of warm light, `SUN_BAND_WIDTH` 0.45 of the play area, full height, additive
  `SUN_BAND_COLOR` (44, 24, 6) at its centre, fading to nothing at its edges.
  - It travels **left to right over dusk's golden hour** and **right to left over dawn's**, because the sun comes up in
    the east (`sky_grade()["sun_x"]`).
- **No full-screen tint:** in daylight there's none now. `GOLDEN_TINT` / `BLUE_TINT` were halved, and they only colour
  the darkness through `lighting.set_grade`.

## 4. The Dictionary is complete (`game/codex_extra.py`)
- **New categories:** "Gear & Crafting" and "Night & World" (`codex.CATEGORIES`, 11 now).
- **Night & World (18):** day and night, darkness and Luminosity, safe houses, night aggression and night mobs, night
  events, the Blood Moon, the moon, weather, shooting stars, herbs, life at night, golden and blue hour, the Calendar,
  Danger, quest markers, the Lamplighter and the Light of RDV, precise combat, chat commands.
- **Gear & Crafting (22):** tiers and loot sources, the Anvil, Gemstones plus all 7 stones, Stonework, gem veins, Divine
  items, shards and keys, Weapon Shards and Bag 2 (moved here), and the Light of RDV, Moonpetal, Ghostbloom, Star
  Fragment, Forge Ingot and Mad God's Room Key.
- **Numbers come from the constants** (`NIGHT_RULES`, `NIGHT_WEATHER`, `danger.mults`, `gems.*`...), so the text follows
  rebalancing.
- **Mob entries:**
  - Herbs say "pick it"; the owl entry is its own.
  - Night-only mobs say NIGHT ONLY and "Found: anywhere in the Realm at night".
  - Every non-boss hostile (and the Red Harvester) mentions the danger scaling.
- **Guard:** `tests/check_dictionary_complete` fails if a monster, NPC or any listed system ships without an entry.

## Tests
- `check_danger_and_calendar`:
  - the gradient and tiers; applied once; wildlife and dungeons untouched
  - it survives the night rules
  - XP, loot and shard rewards: shard difficulty by tier, Heroic at tier 5, the JSON round trip
  - the forecast comes true over 3 nights
  - the clock, Calendar UI and HUD draw
- `check_dictionary_complete`
- `check_night_sky`: now checks that the band is local, full-height and gentle, and that dawn moves right to left
