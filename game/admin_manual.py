"""
The chat-command manual: what every /command does, in plain words, with examples - what /help
<command> shows, and what /help all prints for everything (game/admin.py renders it).

MANUAL[name] = (what it does - one or two sentences, [(example, what that example does), ...])
tests/check_admin_commands.py makes sure every registered command has an entry here.
"""

MANUAL = {
    # ------------------------------------------------------------------ everyday
    "help": ("Shows the command list. With a category it shows each command's description and an example; "
             "with a command name it shows that command's full manual page (this one).",
             [("/help", "the categories and every command name"),
              ("/help items", "every item command, with a description and an example each"),
              ("/help 3", "page 3 (the third category)"),
              ("/help give", "the full manual page for /give"),
              ("/help all", "the whole manual, every command, in one scrollable panel")]),
    "nexus": ("Takes you back to the Nexus from wherever you are. In a dungeon it leaves the dungeon (same as R).",
              [("/nexus", "home to the Nexus fountain")]),
    "realm": ("From the Nexus: steps you into the Realm without walking to the big portal.",
              [("/realm", "into the Godlands, at the arrival beach")]),
    "vault": ("From the Nexus: opens your Vault room (the chests that survive permadeath).",
              [("/vault", "into the Vault room")]),
    "bazaar": ("From the Nexus: the Bazaar, where players leave items in shared chests.",
               [("/bazaar", "into the Bazaar")]),
    "trade": ("Co-op: asks the nearest player to trade. You both put items in, both accept, a short countdown "
              "runs, then the items swap.",
              [("/trade", "invite whoever is closest to a trade")]),
    "accept": ("Co-op: answers a trade invite someone sent you.",
               [("/accept", "open the trade window with them"), ("/decline", "say no")]),
    "crew": ("Co-op: crews are small groups with their own chat colour and name tag.",
             [("/crew create Snacks", "start a crew called Snacks"), ("/crew join Snacks", "join it"),
              ("/crew leave", "leave your crew")]),
    "msg": ("Co-op: a private message only that player sees. /w and /tell do the same.",
            [("/msg Bob meet me at the anvil", "whisper to Bob"), ("/w Bob hi", "same thing, shorter")]),
    # ------------------------------------------------------------------ player
    "xp": ("Gives you XP. You level up exactly as if you'd earned it (stats roll as usual).",
           [("/xp 500", "500 XP"), ("/xp 100000", "enough to go straight to level 20")]),
    "level": ("Sets your level (1-20) by giving the XP needed - every level-up rolls its stats normally.",
              [("/level 10", "become level 10"), ("/lvl 20", "max level")]),
    "maxstats": ("Level 20 and every stat at a high cap (HP 770, MP 385) - a quick 'endgame ready' character.",
                 [("/maxstats", "max everything"), ("/max", "same")]),
    "stat": ("Sets one base stat to an exact value (gear and potions still add on top).",
             [("/stat att 60", "attack 60"), ("/stat hp 500", "max HP 500"), ("/stat spd 75", "speed 75")]),
    "heal": ("Full HP and MP, and clears slow / root.", [("/heal", "topped up")]),
    "god": ("Invulnerable: nothing can hurt you. Toggle it, or say on / off.",
            [("/god", "toggle"), ("/god on", "invulnerable"), ("/god off", "mortal again")]),
    "speed": ("Multiplies your walking speed (1 = normal). Handy for crossing the map.",
              [("/speed 3", "three times as fast"), ("/speed 1", "back to normal")]),
    "noclip": ("Walk through walls, water and doors. Toggle, or on / off.",
               [("/noclip", "toggle"), ("/ghost off", "solid again")]),
    "kill": ("Kills you on the spot - to test death, the death recap and permadeath. The character is deleted!",
             [("/kill", "you die (really)")]),
    "clearbag": ("Empties your backpack. With 'all' also Bag 2 and the Shards tab. There's no undo.",
                 [("/clearbag", "backpack only"), ("/clearbag all", "every bag")]),
    "echoes": ("Adds Echoes to your account - the Echo Keeper's currency for permanent unlocks.",
               [("/echoes 500", "500 Echoes")]),
    "potions": ("Resets the counter that caps how many permanent stat potions you can drink.",
                [("/potions reset", "drink potions again")]),
    "buffs": ("Lists your timed buffs (Moonpetal, Star Fragment, potions...) and how long each has left; "
              "'clear' removes them all.",
              [("/buffs", "list them"), ("/buffs clear", "remove them")]),
    # ------------------------------------------------------------------ items
    "give": ("Gives you any item. You type a few words of its name and it finds the closest match (fuzzy "
             "search); add a tier and/or a count.",
             [("/give staff", "a staff for your class"), ("/give ring 12", "a tier-12 ring"),
              ("/give health potion 5", "five health potions"), ("/i forge ingot 3", "three Forge Ingots")]),
    "tier": ("Equips a full gear set of that tier for your class (weapon, armor, ring, ability). Your old gear "
             "goes into your bags.",
             [("/tier 8", "a T8 set"), ("/tier 14", "the Anvil-only T14 set"), ("/tier divine", "Divine gear")]),
    "gem": ("Gives gemstones to set into your weapon at the Anvil (Forge > Stonework).",
            [("/gem ruby", "one regular Ruby"), ("/gem sapphire perfect 3", "three Perfect Sapphires"),
             ("/gem all flawed", "one Flawed stone of every kind")]),
    "shard": ("Gives Weapon Shards for the Shards tab (each adds an effect to your shots).",
              [("/shard burn", "a Burning shard"), ("/shard keen epic 2", "two epic Keen Edge shards"),
               ("/shard all", "one of every effect")]),
    "ingots": ("Gives Forge Ingots - needed at the Anvil for T12+ tempering, reforging and the best stonework.",
               [("/ingots", "one ingot"), ("/ingots 10", "ten")]),
    "key": ("Gives the Mad God's Room Key (use it in the Realm to open the endgame room).",
            [("/key", "one key")]),
    "dshard": ("Gives a Dungeon Shard - use it from your backpack in the Realm and a portal to that dungeon opens.",
               [("/dshard frozen_crypt", "a shard for the Frozen Crypt"), ("/dshard list", "every dungeon theme")]),
    "heroicshard": ("Gives a Heroic Shard: opens the much harder Heroic version of that dungeon.",
                    [("/hshard ember_den", "a Heroic Ember Den shard")]),
    "egg": ("Gives a pet egg (use it from the backpack to hatch it).",
            [("/egg list", "every pet kind"), ("/egg spirit_fox", "a Spirit Fox egg")]),
    "pet": ("Hatches a pet straight away (your current pet is replaced); 'none' removes it.",
            [("/pet wisp", "a Wisp pet now"), ("/pet none", "no pet")]),
    # ------------------------------------------------------------------ world
    "goto": ("Goes straight to a zone - no portal needed.",
             [("/goto realm", "into the Realm"), ("/goto vault", "the Vault room"),
              ("/goto forge", "the Forge dungeon (the story's finale)")]),
    "tp": ("Teleports you: to tile coordinates, or to anything by name - a named area, an island, an NPC, a "
           "biome, a boss, the arrival beach or (co-op) another player.",
           [("/tp 650 650", "tile (650, 650)"), ("/tp tavern town", "the Tavern Town area"),
            ("/tp island 3", "the third island"), ("/tp hammerstein", "next to Brother Hammerstein"),
            ("/tp spawn", "the arrival beach")]),
    "island": ("Teleports you to one of the big islands' landmark plaza (numbered from 1).",
               [("/island 1", "the first island"), ("/island 10", "the last one")]),
    "time": ("Sets the time of day. Night starts at 330 s and dawn at 540 s of the 600 s day.",
             [("/time night", "nightfall"), ("/time goldenhour", "the warm light before dusk"),
              ("/time 450", "exactly 450 s into the day")]),
    "day": ("Jumps to midday - full daylight, the night's monsters gone.", [("/day", "noon, full daylight")]),
    "night": ("Jumps to nightfall - a fresh night with its own event, weather and Blood Moon roll.",
              [("/night", "night falls now")]),
    "skip": ("Skips to the start of the next phase: day -> dusk -> night -> dawn -> day.",
             [("/skip", "the next phase")]),
    "reveal": ("Reveals the whole minimap and full map (no more fog of war).", [("/reveal", "see everything")]),
    "liveevent": ("Forces a live event (normally they rotate every 25 minutes), turns them off, or back to the "
                  "normal schedule.",
                  [("/liveevent list", "the events"), ("/le double_loot", "Double Loot now"),
                   ("/le off", "no event"), ("/le auto", "back to the schedule")]),
    # ------------------------------------------------------------------ night
    "bloodmoon": ("Starts a Blood Moon night right now ('off' = a normal night instead).",
                  [("/bloodmoon", "the Blood Moon rises"), ("/bm off", "a normal night")]),
    "nightevent": ("Starts a fresh night with the night event you choose.",
                   [("/nightevent fog", "The Fog"), ("/ne lamplighter", "protect Old Wick tonight"),
                    ("/event market", "the Midnight Market")]),
    "weather": ("Sets tonight's weather (starts a night if it's day).",
                [("/weather storm", "rain + lightning"), ("/weather clear", "shooting stars")]),
    "moon": ("Sets the moon phase: 0 new, 2 first quarter, 4 full, 6 last quarter.",
             [("/moon 4", "a full moon (Blood Moons twice as likely)"), ("/moon 0", "the darkest night")]),
    "forecast": ("Shows the coming nights exactly as the Calendar (K) shows them; reroll them, make one a "
                 "Blood Moon, or calm them all.",
                 [("/forecast", "the next 7 nights"), ("/forecast blood 2", "night #2 becomes a Blood Moon"),
                  ("/forecast reroll", "brand-new nights"), ("/forecast calm", "no Blood Moons")]),
    "lightning": ("A lightning strike near you: the whole screen flashes, then thunder.",
                  [("/lightning", "a strike")]),
    "star": ("A shooting star now; 'fall' makes it land as a Star Fragment near you.",
             [("/star", "a shooting star"), ("/star fall", "a Star Fragment lands nearby")]),
    # ------------------------------------------------------------------ mobs
    "spawn": ("Spawns monsters in a ring about 5 tiles around you; 'moonlit' makes them the tougher night variant.",
              [("/spawn goblin", "one goblin"), ("/spawn shade_stalker 4", "four Shade Stalkers"),
               ("/spawn goblin 3 moonlit", "three moonlit goblins")]),
    "boss": ("Summons a boss next to you (a random world boss if you don't name one).",
             [("/boss", "a random world boss"), ("/boss red_harvester", "the Red Harvester")]),
    "killall": ("Kills every hostile around you - they drop loot and count for quests.",
                [("/killall", "everything near you"), ("/nuke 40", "everything within 40 tiles")]),
    "clearmobs": ("Removes every hostile around you - no loot, no credit (a clean slate).",
                  [("/clearmobs", "remove them"), ("/clear 20", "within 20 tiles")]),
    # ------------------------------------------------------------------ dungeons & story
    "dungeon": ("Puts you straight into any dungeon at the difficulty you choose (skips the level / gear gates).",
                [("/dungeon list", "every dungeon"), ("/dg frozen_crypt hard", "the Frozen Crypt on Hard"),
                 ("/dg frozen_crypt heroic", "its Heroic version")]),
    "mgroom": ("Puts you into the Mad God's Room (three forms back to back).", [("/mgroom", "the endgame")]),
    "act": ("Jumps the story to an act (0 = Prologue); saved on your account.",
            [("/act 3", "Act III"), ("/act 0", "back to the Prologue")]),
    "quest": ("Side quests: list them, finish one (or all), reset them, or take one.",
              [("/quest list", "every side quest and its id"), ("/q done all", "finish every active quest"),
               ("/quest give yeti_tag", "take that quest"), ("/quest reset", "start them all over")]),
    "achievement": ("Unlocks an achievement (and its title).",
                    [("/achievement list", "every achievement"), ("/ach all", "all of them")]),
    # ------------------------------------------------------------------ debug
    "stats": ("Everything about your character: stats, gear, buffs and flags.", [("/stats", "the full sheet")]),
    "pos": ("Where you are: tile and pixel coordinates, the zone and the biome.", [("/pos", "your position")]),
    "seed": ("Shows the random seed, or sets one so the same fight / the same drop happens again.",
             [("/seed", "the current seed"), ("/seed 42", "use seed 42")]),
    "fps": ("Shows or hides the FPS counter.", [("/fps", "toggle")]),
    "hitboxes": ("Draws the real hit circles of players, monsters and bullets (to check a dodge).",
                 [("/hb", "toggle")]),
    "danger": ("The danger tier where you stand (Calm .. Lethal, or 'Isle: ...' on an island) and exactly what "
               "it does to monsters here.",
               [("/danger", "the danger report")]),
}


def lines_for(cmd):
    """[(text, kind)] for one command's manual page - kind: 'what' / 'head' / 'ex' / 'ex_what'."""
    what, examples = MANUAL.get(cmd.name, (cmd.desc, []))
    out = [("What it does: " + what, "what")]
    if examples:
        out.append(("Examples:", "head"))
        for ex, does in examples:
            out.append((f"  {ex}", "ex"))
            out.append((f"      -> {does}", "ex_what"))
    return out
