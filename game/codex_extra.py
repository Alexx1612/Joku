"""
Dictionary (game/codex.py) entries for everything the "v0.2 final final" session added: the
night (cycle, darkness, safe houses, aggression, events, Blood Moon, moon, weather, stars,
herbs, wildlife), the Calendar, danger by distance, quest markers, precise combat, and the
gear/crafting side (tiers, the Anvil, Weapon Shards, Gemstones, gem veins, Divine items, keys,
night finds). Numbers are read from the code, so the entries stay true when values change.
"""

WORLD_CAT = "world"
GEAR_CAT = "gear"


def _help(eid, cat, title, text, stats=(), sprite=None):
    return dict(id=eid, cat=cat, title=title, sprite=sprite, stats=list(stats), text=text,
                where={"biomes": [], "areas": []})


def _secs(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else f"{s} s"


def world_entries():
    from game import realm_sim as rs, night as nm, night_sky as ns, danger, items, settings
    out = []
    night_len = rs.NIGHT_END - rs.NIGHT_START + (rs.NIGHT_START - rs.NIGHTFALL_T) + (rs.DAYBREAK_T - rs.NIGHT_END)
    out.append(_help("help:day_night", WORLD_CAT, "Day and night",
        f"A full day in the Realm lasts {_secs(rs.DAY_LENGTH)}: day, a {_secs(rs.NIGHT_START - rs.DUSK_START)} dusk, "
        f"about {_secs(night_len)} of night, then a {_secs(rs.DAWN_END - rs.NIGHT_END)} dawn. A Blood Moon night "
        f"runs {rs.BLOOD_MOON_NIGHT_SPEED}x faster (about 3 minutes). The time bar at the top of the dock shows "
        "where you are in the day (gold = day, orange = dusk/dawn, navy = night, crimson = Blood Moon), a moving "
        "sun or moon, tonight's moon phase, and a big countdown: NIGHT FALLS IN m:ss / DAWN IN m:ss. In the last "
        "30 seconds before dark it pulses red, and a small copy appears at the top of the screen. Dungeons have "
        "no night.",
        stats=[("Day", _secs(rs.DAY_LENGTH)), ("Night", "~4:00 (Blood Moon ~3:00)")]))
    out.append(_help("help:darkness", WORLD_CAT, "Darkness, light and Luminosity",
        "At night the world goes properly dark. You carry a light around you; lamp posts, campfires, braziers, "
        "lit windows, fireflies, glowing creatures and fallen stars light their own pools. Walls, trees and "
        "closed doors cast real shadows. Your eyes adjust: right after dark your light is small and it widens "
        "over ~25 seconds; stepping out of a bright lamp into the dark dazzles you for a moment.\n\n"
        f"Options > Display > Luminosity (default {int(settings.DEFAULTS.get('luminosity', 0.5) * 100)}%) only "
        "changes how dark the night is: 0% is pitch black outside your light, 100% is almost daylight."))
    out.append(_help("help:safe_houses", WORLD_CAT, "Safe houses and doors",
        "Every hut, the tavern, the halls and the little wayside shacks in each biome have real doors. Press F "
        "next to a door to open or close it - any player can. Monsters can't open doors and can't walk through "
        "one, open or shut, and their shots stop at closed doors.\n\nStand inside a house with ALL its doors "
        "shut and you're SHELTERED: monsters can't see or target you, night spawns and night events skip you, "
        "and you regenerate faster. The HUD says 'SAFE - Sheltered'."))
    r, b = nm.NIGHT_RULES, nm.BLOOD_RULES
    out.append(_help("help:night_rules", WORLD_CAT, "Night: the monsters get bolder",
        f"At night every hostile notices you from x{r['aggro']} as far (x{r['aggro_dark']} if you stand in the "
        f"dark), chases x{r['leash']} as far, moves x{r['speed']} faster, hits x{r['dmg']} harder and attacks "
        f"x{1 / r['cd']:.2f} as often. Under a Blood Moon: x{b['aggro']} / x{b['aggro_dark']} / x{b['leash']} / "
        f"x{b['speed']} / x{b['dmg']}. Everything goes back to normal at dawn.\n\nNight-only monsters come out "
        "of the dark, never inside a light: the Lantern-Eater (puts lamps out until dawn), the Shade Stalker "
        "(invisible outside any light), the Night Mimic (a loot bag... until it isn't) and the Hollow Watcher "
        "(shrieks, summons shades, calls everything near). They melt away at dawn. Night kills drop Weapon "
        f"Shards x{items.RUNE_SOURCE_MULT['night']} as often (x{items.RUNE_SOURCE_MULT['blood_moon']} under a "
        "Blood Moon)."))
    out.append(_help("help:night_events", WORLD_CAT, "Night events",
        "Every normal night brings one event, announced at nightfall (the Calendar, K, tells you which):\n"
        f"- The Fog: your light shrinks to x{nm.FOG_LIGHT_MULT}, and twice the Shade Stalkers.\n"
        "- Something Is Hunting: a buffed Stalker 'Hunter' tracks one player until dawn - kill it for bonus loot.\n"
        "- The Lanterns Go Out: every lamp (and every window) is dark tonight.\n"
        "- Midnight Market: the Ghost Merchant appears in a named area - trade 3 gear items for 1 mystery item a "
        "tier higher. He's gone at dawn.\n"
        f"- The Lamplighter: protect Old Wick ({nm.LAMPLIGHTER_HP} HP) from the waves the dark sends every "
        f"{int(nm.LAMPLIGHTER_WAVE_EVERY)} s; everyone who helped (came within {int(nm.LAMPLIGHTER_HELP_RADIUS)} px) "
        "gets the Light of RDV at dawn."))
    out.append(_help("help:blood_moon", WORLD_CAT, "The Blood Moon",
        f"Each nightfall there's a {int(rs.BLOOD_MOON_CHANCE * 100)}% Blood Moon chance (+3% for every night "
        f"since the last one, max 50%; x{rs.FULL_MOON_BLOOD_MULT} under a full moon; more during Blood Moon "
        f"Week). The night goes red and shorter. Every {int(nm.BLOOD_HORDE_EVERY)} s a horde of "
        f"{nm.BLOOD_HORDE_SIZE[0]}-{nm.BLOOD_HORDE_SIZE[1]} moonlit monsters closes in on everyone who isn't "
        "sheltered, a heartbeat pounds, blood rains - and halfway through, THE RED HARVESTER rises near the "
        "furthest-along player. Blood Moon kills roll the best night loot. Survive to dawn: "
        f"+{nm.BLOOD_SURVIVOR_XP} XP."))
    out.append(_help("help:moon", WORLD_CAT, "The moon",
        "The moon moves one phase a night through 8 phases (New, Waxing Crescent, First Quarter, Waxing Gibbous, "
        "Full, Waning Gibbous, Last Quarter, Waning Crescent). A full moon lights the night noticeably and makes "
        "a Blood Moon twice as likely; a new moon leaves it darkest. Clouds hide the moon whatever its phase. "
        "The time bar and the Calendar show the phase."))
    w = dict(ns.NIGHT_WEATHER)
    tot = sum(w.values())
    out.append(_help("help:weather", WORLD_CAT, "Night weather",
        "Each normal night rolls its weather:\n"
        f"- Clear ({w['clear'] * 100 // tot}%): shooting stars cross the sky.\n"
        f"- Cloudy ({w['cloudy'] * 100 // tot}%): the moon is hidden; the night is x{ns.CLOUD_DARK['cloudy']} as bright.\n"
        f"- Rain ({w['rain'] * 100 // tot}%): it rains everywhere it can, x{ns.CLOUD_DARK['rain']} as bright, and "
        f"every light reaches x{ns.WEATHER_LIGHT_MULT['rain']} as far.\n"
        f"- Storm ({w['storm'] * 100 // tot}%): rain plus lightning every {int(ns.LIGHTNING_EVERY[0])}-"
        f"{int(ns.LIGHTNING_EVERY[1])} s - each strike lights the WHOLE screen for a moment (look around!), "
        "then thunder.\nThe weather clears at dawn. A Blood Moon is always clear. Biome weather (snow in the "
        "tundra, sand in the desert, ash in the Ashlands) still shows during the day."))
    out.append(_help("help:shooting_stars", WORLD_CAT, "Shooting stars and Star Fragments",
        f"On clear nights a shooting star has a {int(ns.STAR_CHANCE * 100)}% chance every {int(ns.STAR_EVERY)} s. "
        f"About {int(ns.STAR_FALL_CHANCE * 100)}% of them FALL: a glowing Star Fragment lands "
        f"{ns.STAR_FALL_RING[0]}-{ns.STAR_FALL_RING[1]} tiles away, and the feed tells you which way (\"north-east "
        "of you\"). It glows like a lamp until someone picks it up. Use it: for 4 minutes every kill has a "
        f"{int(rs.STAR_LUCK_CHANCE * 100)}% chance of an extra loot roll."))
    out.append(_help("help:night_herbs", WORLD_CAT, "Night-blooming herbs",
        "Two herbs only bloom at night and glow softly in the dark: Moonpetal (pale blue, forest and highlands) "
        "and Ghostbloom (see-through green, swamp and jungle). Walk up and press F to pick one. Moonpetal heals "
        "25% and widens your light by 30% for 2 minutes; Ghostbloom heals 50% and gives +8 VIT for a minute. "
        "They wilt at dawn."))
    out.append(_help("help:night_life", WORLD_CAT, "Life at night",
        "Day animals (deer, songbirds, hares, elk...) curl up and sleep at night (z z); fireflies drift through "
        "forest, swamp and jungle; owls perch in the trees with glowing amber eyes, hoot, and flap off if you "
        "come close (you can talk to one first). Town folk walk home at dusk and come back out at dawn, and "
        "every house's windows glow. In the tundra your breath mists and the frost glints in the moonlight. "
        "Crickets, owls and distant howls fill the night; a bird chorus greets the dawn."))
    out.append(_help("help:golden_hour", WORLD_CAT, "Golden hour, blue hour, dawn mist",
        "In the last minutes before dusk and the first after dawn, low sunlight rakes across the land: a soft "
        "band of warm light travels from the left edge to the right over dusk's golden hour, and from right to "
        "left over dawn's (the sun comes up in the east). Just after sunset and just before sunrise the dark "
        "turns a cool blue ('blue hour'). Low mist hangs around for a minute at sunrise."))
    out.append(_help("help:calendar", WORLD_CAT, "The Calendar (K)",
        f"Press K for the Calendar: the next {rs.FORECAST_NIGHTS} nights - when each one falls, the moon's phase, "
        "the weather, the night's event, and every BLOOD MOON in red - plus the live-event schedule (Double "
        "Loot, Happy Hour, Blood Moon Week, Two-for-One) with when each starts. The Realm keeps to its schedule: "
        "what the Calendar shows is what happens (a live event that starts in between can still make a Blood "
        "Moon more likely). Works in co-op too."))
    lo, hi = danger.mults(0.0), danger.mults(1.0)
    out.append(_help("help:danger", WORLD_CAT, "Danger: the closer to the centre, the deadlier",
        "The Realm gets more dangerous the closer you get to the CENTRE of the continent, and gentler toward the "
        "coast - for every monster, night monsters included. The minimap shows where you stand (Calm, Mild, "
        "Wild, Deadly, Lethal with 1-5 pips) and the full map (M) draws the rings.\n\n"
        f"From the coast to the centre: HP x{lo['hp']:.1f} -> x{hi['hp']:.1f}, damage x{lo['dmg']:.2f} -> "
        f"x{hi['dmg']:.1f}, speed x{lo['speed']:.2f} -> x{hi['speed']:.2f}, attack rate x{1 / lo['cd']:.2f} -> "
        f"x{1 / hi['cd']:.2f}, notice range x{lo['aggro']:.1f} -> x{hi['aggro']:.2f}.\n\n"
        f"It pays: XP x{lo['xp']:.1f} -> x{hi['xp']:.1f}, up to a {int(hi['loot_extra'] * 100)}% chance of an extra "
        f"loot roll, elites drop Dungeon Shards {int(lo['portal'] * 100)}% -> {int(hi['portal'] * 100)}% of the "
        "time - and a shard remembers where it dropped: shards from the coast open mostly Easy dungeons (never "
        "Hard), shards from the centre mostly HARD ones, and at Lethal an elite's shard is sometimes a HEROIC "
        f"shard ({int(danger.HEROIC_SHARD_CHANCE_T5 * 100)}%, level {danger.HEROIC_MIN_LEVEL}+). At night, night "
        "monsters also come more often near the centre.\n\nThe big islands are separate - they're the level-20 "
        "endgame with their own scaling.",
        stats=[("Coast", "Calm"), ("Centre", "Lethal")]))
    out.append(_help("help:quest_markers", WORLD_CAT, "Quest markers",
        "In the Quest Log, press 'Show marker' on a quest (or click it and press T) to track it - up to 3 at once, "
        "each in its own colour. Tracked quests show a pin on the minimap, on the full map (M) and in the world, "
        "or an arrow at the edge of the screen with the distance in tiles. A list at the bottom left says how far "
        "each one is. If the target is somewhere else (the Nexus, a dungeon), the marker points to the way "
        "there. Your tracked quests are saved with your character."))
    out.append(_help("help:lamplighter", WORLD_CAT, "The Lamplighter and the Light of RDV",
        "Some nights Old Wick the Lamplighter comes out to relight the lamps - and the dark sends Shade Stalkers "
        "and Lantern-Eaters after him in waves. His health bar floats above him. Keep him alive until dawn and "
        "everyone who helped gets the Light of RDV ('Real Diagonal Vision'): a UT ring (WIS +6, VIT +4, DEX +3) "
        f"that makes your light reach x{items.RDV_VISION} as far (Shade Stalkers too) and makes every non-boss "
        f"monster within {int(rs.RDV_FEAR_RADIUS)} px lose its nerve - it stops, cancels its attack and backs "
        "away. If Old Wick falls, the lamps go dark and nobody gets a ring.",
        sprite={"src": "item", "key": "ring", "tint": (255, 224, 140)}))
    out.append(_help("help:precise_combat", WORLD_CAT, "Precise combat",
        "You fire a bit slower but every hit lands much harder (about x1.8), so overall damage is about the "
        "same - but a hit matters, and a miss costs. Aim assist only nudges your shots a few degrees. Big hits "
        "(top of your weapon's range, or crits) crack louder and pop a bigger number."))
    out.append(_help("help:chat_commands", WORLD_CAT, "Chat commands",
        "Press Enter and type /help to see every chat command, grouped by category; /help <command> explains "
        "one. Everyday ones: /nexus /realm /vault /bazaar /trade, and in co-op /w <name> <msg>, /crew. The "
        "testing (admin) commands - give XP, items, set the time, the weather, spawn monsters, open dungeons, "
        "teleport... - work in single-player, and on a co-op server started with --admin."))
    return out


def gear_entries():
    from game import items, gems, runes, forge  # noqa: F401  (forge: the Anvil's recipes)
    out = []
    out.append(_help("help:tiers", GEAR_CAT, "Tiers and loot sources",
        "Gear goes from T1 to T14. T1-T11 drop all over the Realm and in dungeons; T12-T13 (mythic, cyan bags) "
        "come from Heroic dungeons, the big islands, the Mad God's Room, the night and the Blood Moon; T14 is "
        "never dropped - only tempered at the Anvil. UT items (pink) have special effects; Divine items (gold bags) are the "
        "very best. Where a monster lives decides its loot table - the islands, Heroic dungeons, the night and "
        "the Blood Moon each roll their own, better tables. Near the centre of the continent kills can roll an "
        "extra bag (see Danger)."))
    out.append(_help("help:anvil", GEAR_CAT, "Brother Hammerstein's Anvil",
        "In the Nexus tavern. Talk to him (F) to:\n- Temper: any 3 gear items of the same tier -> 1 of the next "
        "tier (T12+ costs Forge Ingots).\n- Reforge a UT for a fresh roll (costs Ingots).\n- Fuse 3 Weapon Shards "
        "of one rarity into 1 of the next.\n- Stonework: set Gemstones into your weapon, combine 3 stones into a "
        "better one, or pry one out.\nForge Ingots drop from Heroic bosses, big-island bosses and the Mad God's "
        "Room.", sprite={"src": "item", "key": "ingot", "tint": (255, 200, 120)}))
    out.append(_help("help:gems", GEAR_CAT, "Gemstones",
        "Seven stones, each an element: Ruby (fire), Sapphire (frost), Topaz (lightning), Emerald (venom), "
        "Amethyst (arcane), Onyx (shadow) and Diamond (radiant). Five grades - Chipped, Flawed, Regular, "
        f"Flawless, Perfect - are x{gems.GRADE_MULT['chipped']} to x{gems.GRADE_MULT['perfect']} as strong.\n\n"
        "Brother Hammerstein sets stones INTO your weapon: T0-4 weapons have 1 socket, T5-9 have 2, T10+ have 3 "
        "(UT and Divine weapons 2). A set stone stays with that weapon (trade, vault, co-op). Stones of a kind "
        f"stack: 2 alike are ATTUNED (x{gems.ATTUNED_MULT}), 3 are RESONANT (x{gems.RESONANT_MULT} plus a bonus). "
        "The weapon glows in its first stone's colour, its shots leave that element's trail, hits burst in it, "
        "and you carry a little aura of it.\n\nStones drop from elites "
        f"({int(gems.GEM_DROP_CHANCE['elite'] * 100)}%) and bosses ({int(gems.GEM_DROP_CHANCE['boss'] * 100)}%) - "
        "better grades from the islands, Heroic dungeons, the Blood Moon and the Mad God's Room - or mine them "
        "from gem veins.", sprite={"src": "item", "key": "gem_ruby_regular", "tint": (235, 60, 55)}))
    for kind, (name, element, col, _fx, what) in gems.STONES.items():
        out.append(dict(id=f"item:gem:{kind}", cat=GEAR_CAT, title=name,
                        sprite={"src": "item", "key": f"gem_{kind}_regular", "tint": col},
                        stats=[("Element", element.title()), ("Grades", "Chipped .. Perfect")],
                        text=f"{name}: {what}.\n\nResonant (3 {name}s in one weapon): {gems.RESONANT[kind]}.",
                        where={"biomes": [], "areas": []}))
    out.append(_help("help:stonework", GEAR_CAT, "Stonework at the Anvil",
        "'Stonework: gems and sockets...' on Brother Hammerstein's menu:\n"
        "- Set a stone from your backpack into your EQUIPPED weapon (a Flawless stone costs "
        f"{gems.SET_INGOTS['flawless']} Forge Ingot, a Perfect {gems.SET_INGOTS['perfect']}).\n"
        "- Combine 3 identical stones into 1 of the next grade (Flawless -> Perfect costs "
        f"{gems.COMBINE_INGOTS['flawless']} Ingot).\n- Pry out the last stone set - it shatters.\nTwo alike hum "
        "together; three SING."))
    out.append(_help("help:gem_veins", GEAR_CAT, "Gem veins",
        "Glittering rocks in the highlands, desert, tundra, caves, the Ashlands and the jungle - each biome has "
        "its own mix of stones. Stand next to one and press F: a short dig (walk away to cancel), then a "
        "Chipped, Flawed or (rarely) Regular stone. A vein gives 2 stones, then goes dull until the morning "
        "after the next night."))
    out.append(_help("help:divine", GEAR_CAT, "Divine items",
        "The rarest gear in the game, only from the Mad God's Room (its last form always drops one). The Divine "
        "weapon calls down Starfall bolts; the Divine armor gives you a Second Wind when you'd die. Gold bags "
        "and a beam of light mark them."))
    out.append(_help("help:keys", GEAR_CAT, "Shards and keys",
        "Dungeon Shards drop from elites - use one in the Realm to open a portal to that monster's dungeon. A "
        "shard remembers how dangerous the land it dropped in was: shards from the centre open harder dungeons "
        "(see Danger). Heroic Shards open Heroic dungeons (level 16+); finish a dungeon's Heroic trial quest for "
        "your first. The Mad God's Room Key (rare: Heroic bosses, calmed big islands) opens the Mad God's Room "
        "(level 20, a T12+ item equipped)."))
    out.append(dict(id="item:light_of_rdv", cat=GEAR_CAT, title="Light of RDV",
                    sprite={"src": "item", "key": "ring", "tint": (255, 224, 140)},
                    stats=[("Slot", "Ring (UT)"), ("Stats", "WIS +6, VIT +4, DEX +3")],
                    text=items.make_rdv_ring().description + "\n\nThe Lamplighter's reward - see 'The "
                         "Lamplighter and the Light of RDV'.",
                    where={"biomes": [], "areas": []}))
    for maker, eid in ((items.make_moonpetal, "item:moonpetal"), (items.make_ghostbloom, "item:ghostbloom"),
                       (items.make_star_fragment, "item:star_fragment"), (items.make_forge_ingot, "item:forge_ingot"),
                       (items.make_mad_god_key, "item:mad_god_key")):
        it = maker()
        out.append(dict(id=eid, cat=GEAR_CAT, title=it.name,
                        sprite={"src": "item", "key": it.shape, "tint": it.color},
                        stats=[("Kind", it.slot.replace("_", " ").title())], text=it.description,
                        where={"biomes": [], "areas": []}))
    return out
