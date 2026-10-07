# 38 - Admin / testing commands

"V0.2 final final" session. A chat-command toolbox for testing everything fast: XP and levels, any item, the time of day, Blood Moons, weather, night events, mobs, dungeons, story acts, quests and debug overlays. Type them in chat (Enter, then `/command`). `/help` lists them all in-game.

## How it works
- **One registry:** `game/admin.py` defines every command as `Command(name, aliases, usage, desc, category, handler, side)`. `/help` and these docs are built from it. `tools/gen_admin_docs.py` regenerates the tables below and in the README.
- **Contexts:** handlers take a `ctx`, so the same code runs everywhere:

  | Context | Mode | What it wraps |
  |---|---|---|
  | `SPCtx` | single-player | `main.Game` |
  | `ServerCtx` | co-op server | `ServerState` + the typing player's `Session` |
  | `ClientCtx` | co-op client | the client-only commands |

- **Where a command runs:**
  - In single-player, everything runs locally.
  - In co-op, the client sends `{"action": "admin", "text": ...}`. The server runs it with `ServerCtx` and answers `{"type": "admin_result", "title", "panel", "lines"}`.
  - Client-only commands run where they're typed: `/help`, `/reveal`, `/fps`, `/hitboxes`, `/pos`.
- **Co-op gate:** the server accepts admin commands only when started with `--admin` (`python server.py --admin`, or the env var `RR_ADMIN=1`). Otherwise the reply is "Admin commands are off on this server". The welcome message tells clients whether admin is on, and `/help` says so. Every admin command is printed in the server console.
- **Output:**
  - Up to 4 short lines go to the feed.
  - Longer output (`/help`, lists, `/stats`) opens the **command panel**: an opaque, scrollable box left of the dock. Use the mouse wheel or PgUp/PgDn to scroll; Esc or a click outside closes it. It shrinks to fit short output.
- **Engine hooks** (small, inert unless used):

  | Hook | Where | Used by |
  |---|---|---|
  | `Player.god` | `take_damage` returns 0 | `/god` |
  | `Player.admin_speed` | multiplies `speed()` | `/speed` |
  | `Player.noclip` | `net_update` ignores walls | `/noclip` |
  | `RealmSim.force_blood_moon` | | `/bloodmoon` |
  | `NightDirector.force_event` | | `/nightevent` |
  | `NightSky.force_weather` | | `/weather` |
  | `NightSky._shooting_star(fall=...)` | | `/star` |

  `/bloodmoon`, `/weather` and `/nightevent` end tonight cleanly and start a fresh nightfall with the forced setting.
- **`/give`** fuzzy-searches a catalog of every item the game can make:
  - every class's weapons, armor, rings and abilities at every tier
  - UTs and Divine items
  - potions and eggs
  - dungeon and Heroic shards
  - gemstones and Weapon Shards
  - key, ingot, herbs, Star Fragment, Light of RDV
  - fishing junk

  It tries an exact name, then a prefix, then all-words, then a close match. A trailing number is a tier, two numbers are tier + count, and `x5` is a count. `/give list <words>` shows the matches.
- **Overflow:** items that don't fit go to Bag 2, then a bag at your feet (or pending rewards in a hub).

## Commands
<!-- admin-table:start -->
#### Player

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/buffs [clear]` | - | list (or clear) your timed buffs | server, --admin |
| `/clearbag [all]` | /clearinv | empty the backpack (and Bag 2 + Shards with 'all') | server, --admin |
| `/echoes <amount>` | - | add Echoes to your account (the Echo Keeper's currency) | server, --admin |
| `/god [on\|off]` | /invuln | invulnerable: no damage at all | server, --admin |
| `/heal` | - | full HP and MP, clears slow/root | server, --admin |
| `/kill` | /suicide | kill yourself (tests death / permadeath - the character is deleted!) | server, --admin |
| `/level <1-20>` | /lvl | level up to that level (stats roll as normal) | server, --admin |
| `/maxstats` | /max | level 20 and every stat at a high cap (HP 770, MP 385) | server, --admin |
| `/noclip [on\|off]` | /ghost | walk through walls, water and doors | server, --admin |
| `/potions reset` | - | reset the permanent-potion cap counter | server, --admin |
| `/speed <0.25-10>` | /fast | walk-speed multiplier (1 = normal) | server, --admin |
| `/stat <att\|def\|spd\|dex\|vit\|wis\|hp\|mp> <value>` | - | set one base stat | server, --admin |
| `/xp <amount>` | - | gain XP (levels up as normal) | server, --admin |

#### Items

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/dshard <theme> [count]` | /dungeonshard | give a normal Dungeon Shard (use it in the Realm to open a portal) | server, --admin |
| `/egg <pet kind\|list>` | - | give a pet egg | server, --admin |
| `/gem <stone\|all> [grade] [count]` | /gems, /stone | give gemstones (ruby, sapphire, topaz, emerald, amethyst, onyx, diamond; chipped..perfect) | server, --admin |
| `/give <item name or words> [tier] [count]` | /i, /item | give yourself any item (fuzzy search) | server, --admin |
| `/heroicshard <theme> [count]` | /hshard | give a Heroic Shard (opens that dungeon's Heroic version) | server, --admin |
| `/ingots [count]` | /ingot | give Forge Ingots (the Anvil's currency) | server, --admin |
| `/key [count]` | /mgkey | give the Mad God's Room Key | server, --admin |
| `/pet <pet kind\|none>` | - | hatch a pet straight away (replaces your current one) | server, --admin |
| `/shard <effect\|all> [rarity] [count]` | /rune, /shards | give Weapon Shards (bleed, burn, chain, keen, leech, echo...; common..mythic) | server, --admin |
| `/tier <1-14 \| divine>` | /gear, /kit | equip a full gear set of that tier for your class (old gear goes to your bags) | server, --admin |

#### World & time

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/day` | - | jump to midday | server, --admin |
| `/goto <nexus\|realm\|vault\|bazaar\|forge>` | /zone | go straight to a zone (no portal needed) | server, --admin |
| `/island <1-N>` | - | teleport to an island's landmark plaza | server, --admin |
| `/liveevent <name\|off\|auto\|list>` | /le | force a live event (double loot, Blood Moon week...) | server, --admin |
| `/night` | - | jump to nightfall (a fresh night: events, weather, Blood Moon roll) | server, --admin |
| `/reveal` | /map | reveal the whole minimap / full map | your client |
| `/skip` | - | skip to the start of the next phase (day -> dusk -> night -> dawn -> day) | server, --admin |
| `/time <day\|goldenhour\|dusk\|night\|midnight\|dawn\|morning\|seconds 0-600>` | /t | set the time of day (night starts at 330 s, dawn at 540 s) | server, --admin |
| `/tp <x> <y> (tiles) \| /tp <area, island, NPC, biome, boss, spawn, player>` | /teleport | teleport (by tile coordinates or by name) | server, --admin |

#### Night & weather

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/bloodmoon [on\|off]` | /bm | start a Blood Moon night now (off: a normal night instead) | server, --admin |
| `/forecast [reroll \| blood <n> \| calm]` | /calendar, /fc | the coming nights (as the Calendar, K, shows them); reroll them, make night n a Blood Moon, or none | server, --admin |
| `/lightning` | /bolt | a lightning strike near you (flash + thunder) | server, --admin |
| `/moon <0-7>` | - | set the moon phase (0 new .. 4 full .. 7) | server, --admin |
| `/nightevent <fog\|hunter\|lanterns_out\|market\|lamplighter>` | /event, /ne | start a fresh night with that night event | server, --admin |
| `/star [fall]` | - | a shooting star now ('fall' drops a Star Fragment nearby) | server, --admin |
| `/weather <clear\|cloudy\|rain\|storm>` | - | tonight's weather (starts a night if it's day) | server, --admin |

#### Mobs

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/boss [kind]` | - | summon a boss next to you (random world boss if no kind) | server, --admin |
| `/clearmobs [radius tiles]` | /clear | remove every hostile mob (no loot) | server, --admin |
| `/killall [radius tiles]` | /nuke | kill every hostile mob (with loot and kill credit) | server, --admin |
| `/spawn <mob kind> [count] [moonlit]` | /summon, /mob | spawn mobs around you (5 tiles out) | server, --admin |

#### Dungeons & story

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/achievement <id\|all\|list>` | /ach | unlock an achievement (and its title) | server, --admin |
| `/act <0-7>` | /story | jump the story to that act (0 = Prologue; saved on the account) | server, --admin |
| `/dungeon <theme\|list> [easy\|medium\|hard\|heroic\|godly]` | /dg | enter any dungeon straight away (skips level / gear gates) | server, --admin |
| `/mgroom` | /madgod | enter the Mad God's Room (3 forms) | server, --admin |
| `/quest list \| done <id\|all> \| reset \| give <id>` | /q | side quests: list, complete, reset, accept | server, --admin |

#### Debug

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/danger` | - | the danger tier where you stand and what it does to monsters here | server, --admin |
| `/fps [on\|off]` | - | toggle the FPS counter | your client |
| `/hitboxes [on\|off]` | /hb | draw the real hit circles of players, mobs and bullets | your client |
| `/pos` | /where, /coords | your position (tiles and pixels), zone and biome | your client |
| `/seed [n]` | - | show or set the random seed (reproduce a fight / a drop) | server, --admin |
| `/stats` | /me, /info | everything about your character (stats, gear, buffs, flags) | server, --admin |

#### Everyday commands

| Command | Also | What it does | In co-op |
|---|---|---|---|
| `/accept  /decline` | - | co-op: answer a trade invite | everyone |
| `/bazaar` | - | from the Nexus: the Bazaar | everyone |
| `/crew create\|join\|leave <name>` | - | co-op: crews | everyone |
| `/help [page \| category \| command]` | /?, /commands | list every command (paged by category) | your client |
| `/msg <name> <text>` | - | co-op: whisper (also /w, /tell) | everyone |
| `/nexus` | - | go back to the Nexus (also leaves a dungeon) | everyone |
| `/realm` | - | from the Nexus: into the Realm | everyone |
| `/trade` | - | co-op: trade with the nearest player | everyone |
| `/vault` | - | from the Nexus: open your vault | everyone |
<!-- admin-table:end -->

## Tests
`tests/check_admin_commands.py`:
- **Coverage:** every admin command has a sample, and `/help` lists them all.
- **Single-player:** all ~100 sample lines run without errors or "Usage" replies.
- **Effects:**
  - xp / level, fuzzy `/give`, `/tier`
  - god, speed
  - time, Blood Moon on/off, weather, night event
  - spawn / killall, tp by tiles and by name
  - dungeon / mgroom / goto, reveal, hitboxes
  - the chat path and the panel's Esc
- **Co-op server:** refuses without `--admin`; with it, ~90 server-side lines run, ending with `/kill` reaching the permadeath path.
- **Co-op client:** the client-side commands run on a client.

Screenshots: `screenshots/2026-10-07/admin_commands/`.
