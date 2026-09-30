# Realm Reforged - Ends of V0.2

A from-scratch, original-code game inspired by **Realm of the Mad God**
(RotMG) - a top-down bullet-hell MMO-lite you can play solo or in real
client-server co-op. No RotMG assets, sprites, music or code are used: all
art is original (hand-painted PNGs plus procedurally generated pixel art),
every sound effect and all 33 music tracks are original procedurally
synthesized compositions (no covers, no borrowed melodies), and the stat
formulas are re-derived independently from the public RotMG wiki in
`game/constants.py`.

**Current version: "Ends of V0.2"** - the last release of the v0.2 line
(GitHub release tag `v0.2`). There is no v0.3 yet: everything below is v0.2.

Contents: [Download & play](#download--play-no-python-needed) ·
[Run from source](#run-from-source) · [Play co-op](#play-co-op) ·
[Controls](#controls) · [Features](#features) · [Where saves live](#where-saves-live) ·
[Project structure](#project-structure) · [Tests](#tests) ·
[Build & release](#build--release) · [Known limitations](#known-limitations) ·
[Version history](#version-history) · [Bugs found and fixed](#bugs-found-and-fixed-during-development)

## Download & play (no Python needed)

Every release ships standalone builds for **Windows** and **Linux (x86_64,
e.g. Ubuntu 22.04+)** - the game and all its assets are bundled, nothing else
to install. Get them from the [latest release](https://github.com/Alexx1612/Joku/releases/tag/v0.2).

| You want to... | Windows | Linux |
|---|---|---|
| Play solo | double-click `RealmReforged.exe` | `./play.sh` |
| Host co-op | `RealmReforged-Server.exe` | `./host.sh` |
| Join co-op | `join.bat <host> <name>` (or `RealmReforged-CoopClient.exe --host <host> --name <name>`) | `./join.sh <host> <name>` |

`join.bat` asks for the host address and your name if you just double-click it.

**Linux**: download `RealmReforged-linux-x86_64.tar.gz`, then

```
tar -xzf RealmReforged-linux-x86_64.tar.gz
cd RealmReforged-linux
./play.sh                      # solo
./host.sh                      # host a co-op server (port 50777)
./join.sh 100.64.0.7 Alex      # join a server
```

**Linux compatibility**: the Linux binaries are built on Ubuntu 22.04, so they run on
Ubuntu 22.04 or newer (and other x86_64 distros with glibc 2.35+; older ones such as
Ubuntu 20.04 can run the game from source instead - see below). If a launcher says
"Permission denied", run `chmod +x *.sh RealmReforged*` once. Every release build is
smoke-tested on both Windows and Linux (server, game and co-op client must start).

**Cross-platform co-op works**: a Linux client can join a Windows server and
vice versa - it's the same plain TCP protocol. Everyone just needs builds
from the **same release** (mixing versions isn't supported).

**Saves** (characters, accounts, vaults, friends, crews, `settings.json`,
the music cache) are written **next to the executable/scripts**. In co-op,
characters live on the **host's** PC - always use the same host, and keep
that folder when you update to a new release.

### Playing with a friend from different homes

1. **Easiest - a free virtual LAN (no router setup):** both install
   [Tailscale](https://tailscale.com) (or ZeroTier / Radmin VPN) and join the
   same network. The host's PC gets an address like `100.x.y.z` (see the
   Tailscale tray/`tailscale ip -4`).
2. **Or port forwarding:** on the host's router forward **TCP 50777** to the
   host PC, and give your friend your public IP. (Doesn't work behind CGNAT;
   exposes the port publicly - the server has no passwords.)
3. Host starts the server (`RealmReforged-Server.exe` / `./host.sh`) and
   allows it through the firewall (Windows asks on first run; on Ubuntu with
   ufw: `sudo ufw allow 50777/tcp`).
4. Everyone, including the host, joins with the client: host uses
   `127.0.0.1`, friends use the Tailscale/public address.

The first trip into the Realm downloads the ~5 MB world map once, so it can
take a few seconds over the internet.

## Run from source

Needs Python 3.12 (3.13+ lacks the stdlib `audioop` the music renderer uses -
a slower pure-Python fallback kicks in) and `pygame==2.6.1`
(`requirements.txt`).

```
# Windows
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe main.py

# Linux / macOS
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Single-player needs nothing else running.

## Play co-op

One person **hosts** (runs the server); everyone, including the host,
**joins as a client**.

1. **Host: start the server** - `python server.py` (or the Server build).
   Leave it running - it is the shared world. Options: `--host 0.0.0.0`
   (default, all interfaces), `--port 50777` (default).
2. **Host: share an address** - same Wi-Fi: the LAN IPv4 (`ipconfig` /
   `ip -4 addr`); over the internet: see "Playing with a friend from
   different homes" above.
3. **Everyone: launch the client** -
   `python coop_client.py --host <address> --port 50777 --name YourName`
   (host uses `--host 127.0.0.1`). Pick a class, press Enter, and you are in
   the shared Nexus.

`Ctrl+C` stops the server; clients show a "Disconnected" screen. The server
is authoritative for enemies, damage, loot, XP, trades, quests and saves; it
ticks at 30 Hz and only sends each client what is within ~1400 px of them.

## Controls

The in-game **O** menu shows the same list (`game/ui.py` `HELP_LINES`).

| Key | Action |
|---|---|
| WASD / arrows | Move |
| Mouse / left click (hold) | Aim (soft aim-assist near enemies) / fire - rate scales with DEX, a click just before the cooldown clears still registers |
| I | Toggle auto-fire |
| Space | Class ability at the mouse position |
| Left Shift | Dash / roll - 0.18 s burst of 2.5 tiles with i-frames, 2 s cooldown |
| 1-8 / double-click a slot | Use / equip that backpack item |
| Click + drag | Move items between backpack, equip slots, ground bags and vault chests; drop off the dock onto the ground; drag onto the Pet tab / pet panel to feed the pet |
| Shift + click | Quick-move: deposit into an open vault chest / Bazaar chest, or offer in an open trade |
| Right-click | Drop the hovered backpack item, else open the nearest ground bag; in co-op, right-click a player (or their name in chat) for Whisper / Trade / Inspect / Teleport / Friend / Crew invite |
| Tab | Switch the right dock between Inventory and Pet |
| F | Context action: talk to an NPC or animal nearby, open a vault chest, fish at water, wish at the Nexus fountain, talk to Father Given |
| J | Expand / collapse the small HUD quest log (click it to open the full Quest Log) |
| Enter | Open chat (with history) / step through the portal you're standing on / open a vault chest |
| R | Back to the Nexus (Realm) / leave the dungeon |
| Q / E, X | Rotate the camera, reset rotation |
| M | Full map (scroll wheel or +/- to zoom; right-drag pans the Quest Map) |
| L | Friends panel (co-op) |
| O | Options menu (volumes, effects, FPS cap, auto-fire, fullscreen, Quest Log, Dictionary...) |
| F11 | Fullscreen (shows more of the world, not a scaled image) |
| 1-5 in a dialogue | Pick that answer (or click it) |
| Esc | Close the top-most window (dialogue, journal, map, shop, options, bag, vault chest, trade, menus); with nothing open, asks "quit?" - Esc / Enter / Y quits, N stays |

**Chat** (Enter): real text cursor (Left/Right/Home/End, Backspace/Delete),
Shift+arrows or mouse drag to select, Ctrl+A / C / X / V, Up/Down to recall
earlier messages. The chat **log** panel is selectable too (click-drag, then
Ctrl+C) without entering chat mode; drag its top strip to move it.
Commands: `/nexus` `/realm` `/vault` `/bazaar` `/trade` `/help`, and in co-op
`/msg "Name" text` (also `/w`, `/whisper`, `/tell` - reaches a player in any
zone), `/accept` / `/decline` (trade invites) and
`/crew create|join|leave <name>`.

## Features

### Classes, stats and combat
- **8 classes** - Wizard, Archer, Warrior, Priest, Rogue, Necromancer,
  Paladin, Assassin - chosen on a stat-comparison select screen. Base stats
  and growth cycles are listed in [GAME_DATA.md](GAME_DATA.md).
- **Real stat formulas** (`game/constants.py`): ATT scales damage
  (`roll * (ATT+25)/50`), DEX attack speed, SPD move speed, VIT/WIS regen.
  **Player defense is a percentage curve**: damage taken =
  `dmg * 75 / (75 + DEF)` (so tanks are tougher but never immune); enemies
  use flat subtraction with a per-rank floor.
- **Levelling to 20** with class-archetype growth: HP +16-22 / +12-17 / +9-13
  per level and MP +4-7 / +5-8 / +7-11 (heavy / light / robe), signature stats
  +1-3, others +0-1.
- **Abilities** (Space), 3 tiers per class (T1/T5/T9), damage x2.5 and
  heal/shield x1.5 at cast (`items.ABILITY_POWER_MULT`), each with its own
  visual (17 styles in `vfx.ABILITY_STYLES`: crystal shards, void chain
  lightning, thunderbolts, poison clouds, scythe arcs, holy pillars, domes,
  horn sound-waves, smoke, shadow...). Wizard/Necromancer/Archer:
  nova -> nova -> chain / drain / freeze; Priest heals; Paladin heals ->
  shield; Warrior/Rogue/Assassin party haste. Abilities are telegraphed and
  never hit friendly creatures or NPCs.
- **Enemy attacks** (`game/enemy_attacks.py`): **every everyday mob roaming
  the open Realm and the islands - of any rank - only fires plain shots**
  (aimed, predictive, small 3-fans, 2-shot volleys, heavy bolts, sine shots,
  boomerangs; varied per kind, elites a little harder) with no warning.
  **Special mobs** - bosses (dungeon, phase 2, world boss, Mad God), island
  mini-bosses, the island anchors, landmark story guardians and every mob
  fought INSIDE a dungeon room - carry named attack sets and are genuinely hard: faster, denser patterns (gaps always kept),
  shotgun fans, bullet walls with a gap, beams, homing/accelerating/splitting
  bullets, mines, lobbed ground AoEs, dashes and leaps, summons, root pulses.
  Mini-bosses have 3-4 named moves, dungeon bosses 4-6 (e.g. the Vault
  Guardian's Aimed Shotgun / Grenade Barrage / Gapped Spin / Crystal Rage);
  below 50% HP they enrage (roar, new moves incl. the **Crossfire** combo,
  cooldowns x0.6) and phase-2 rooms add a final move.
- **Telegraphs only for dangerous attacks**: ground AoEs, slams/novas, beams
  and lance lines, dashes/leaps and boss specials show a colour-coded warning -
  **red** aim lines and dash lanes, **orange** ground circles/cones/ring
  warnings. Ordinary shots (from anyone) come with no hint - keep moving.
- **Juice**: impact particles, damage numbers, hit flash, idle/walk/attack
  animation, a per-light-source night lightmap. **Screen shake is reserved for
  what matters**: getting hit yourself (scaled by damage; bigger for boss
  hits), nearby slams/landings (fades with distance) and boss phase changes /
  deaths - never for your own shots, abilities or pet fusion, never for other
  players' hits in co-op, and no shake when a far-away world boss spawns.
- **Sound**: original synthesized SFX per weapon type (staff, scepter, wand,
  bow, dagger, katar, sword, mace), per ability style (17) and per enemy
  attack kind (shot, shotgun, spray, beam, lob, slam, leap, dash wind-up,
  homing, wall, summon, shell, root, boss phase, ...), rate-limited so big
  fights don't clip.
- **Permadeath** - a dead character is deleted; account unlocks, Echoes,
  achievements, the vault and completed story acts survive.

### Items and loot
- 14 weapon tiers per class, 14 armors per archetype (heavy / light / robe),
  14 rings, 5 ability tiers per class (1 / 5 / 9 / 12 / 14), and 4 untiered
  (UT) weapons per class with distinct procs (bleed, boomerang, burn,
  vulnerable). 40% of drops can be for another class.
- **Tiers**: normal loot tops out at T11. **T12-T13** (cyan "mythic" badge)
  only drop in Heroic dungeons, on the big islands and in the Mad God's Room.
  **T14** (red-hot badge) never drops - it's forged.
- **Brother Hammerstein's Anvil** (Nexus, talk with F): *temper* 3 items of
  the same slot and tier into one of the next tier (Forge Ingots needed from
  T12 up), or *reforge* a UT with 2 Ingots (+20% damage, proc kept).
- **Divine items** (the Mad God's Room): a Divine weapon per class
  (*Starfall*: every 4th shot adds 3 piercing star bolts), Divine armor
  (*Second Wind*: a killing blow leaves you at 1 HP, once per 90 s), a Divine
  ring and Divine abilities.
- **Loot bags** (brown / purple / white by rarity), rolled per mob
  difficulty; ground-bag tooltips; right-click to open.
- **UT sockets**: drag a spare UT onto a weapon and confirm with Enter to
  transplant its proc (both slots highlight while pending).
- **Potions**: permanent +1 stat potions (20 per character max) and
  temporary +6 potions (60 s).
- Goofy fishing junk (boots, rubber duck rings...), Dungeon Shards,
  quest items (Glowcap Mushroom, Camel Bell, Driftwood Rum, Ember Core).

### Pets
- 13 pet kinds across common / uncommon / rare / legendary / **mythic**
  (hatched from eggs; mythic only by fusion). Every pet runs heal, mana and
  attack abilities on their own cooldowns; feed items (drag onto the pet)
  to level each ability up to the rarity cap (10 / 15 / 20 / 30 / 40).
- **Bond**: lifetime feed-XP (counts even when maxed); bond level (max 25)
  gives up to x2 power and -25% cooldowns (heal/mana cooldown never below
  1.5 s). Pets follow you in hubs too, and never attack friendly creatures.
- **Carriers**: the Pack button turns your pet into a tradable, vaultable
  item that keeps levels and bond; use it to unpack.
- **Fusion**: drop a maxed carrier onto your maxed active pet of the same
  rarity -> a pet of the next rarity with the combined bond.

### Story campaign (`game/story.py`)
Seven acts that go exploration -> combat -> gear -> the deep end -> the big
islands -> the Mad God:
- **Prologue: Welcome, Sucker** - talk to Father Given in the Nexus, enter the Realm.
- **Act I: The Grand Tour** - sightseeing: visit 5 of the big named places,
  spot the landmark in each outer biome, chat with 3 locals, catch a fish.
- **Act II: Bouncer Problems** - defeat the Landmark Guardians of the 4 outer
  biomes (forest, desert, tundra, swamp) and clear a dungeon (every
  guardian drops a Dungeon Shard).
- **Act III: Retail Therapy** - wear a T8+ item, clear 2 more dungeons,
  finish a Heroic trial quest and forge something at the Anvil.
- **Act IV: The Deep End** - defeat 4 inner-biome Landmark Guardians and clear
  2 Heroic dungeons (level 16+).
- **Act V: Last Call** - calm any 7 of the 10 big islands (level 20).
- **Finale: Closing Time** - Father Given sends you to the Forge to fight the
  Mad God (two phases, armor-piercing volley and nova), then credits and free play.
- **After the story**: the **Mad God's Room** (see World).
- Completed acts are checkpointed on your account (they survive permadeath);
  enemy HP scales x1.1 per completed act (up to x1.6). Old saves from the
  5-act arc are moved onto the new arc automatically. Quest log: **J** (HUD)
  or the full Quest Log.

### NPCs, dialogue and side quests
- **11 NPCs** - Barkeep Bitterwick (Nexus tavern), Old Mossbeard, Sandy Sal,
  Frostine the Ice Fisher, Captain Driftwood (arrival beach), Madame Murk,
  Brother Tipsy, Cinder Pete, Professor Fernleaf, Rusty the Scrap Golem,
  Glimmer the Cartographer - plus **4 talkable creature groups** (Grand Elk
  Herd, Gossiping Flamingos, Philosopher Tortoise, Mushroom Folk) and 16
  kinds of friendly wildlife you can talk to. Press **F** near them.
- **Dialogue menus** (`game/dialogue.py`): numbered answers, each topic
  heard once (conversations are finite), quests offered and handed in
  there, always a "Bye".
- **30 side quests** (`game/sidequests.py`): a random board of 3 plus
  NPC-given quests, rewarding XP, Echoes and a loot roll. Kinds: stand among
  wildlife groups, talk to creatures, kill counts, visit islands/landmarks/
  spots, open island chests, deliver quest items, fish, feed your pet,
  clear dungeons, survive a night, witness a world boss. Full list in
  [GAME_DATA.md](GAME_DATA.md).
- **Journal** (`game/journal.py`, O menu): the **Quest Log** (scrollable:
  story act, active and completed side quests; blue target names open the
  Dictionary, "Map" opens the Quest Map), the **Dictionary** (200+ entries
  in 9 categories - mobs, bosses, friendly creatures, NPCs, portals &
  dungeons, areas, pets & mechanics, items & UT, story - with search,
  sprite, stats, text and a where-to-find mini map, plus help pages for
  pets, sockets, story, side quests, co-op loot, Echoes, events and
  trading), and the **Quest Map** (fully revealed, labelled, pulsing quest
  markers with hover tooltips, wheel zoom, right-drag pan).

### World
- **The Realm**: 1560 x 1560 tiles - a 900 x 900 continent in an ocean ring.
  Terrain is layered value-noise fBm (each octave rotated) with a 2-level
  domain warp; 10 biomes (outer: forest, desert, tundra, swamp; inner:
  highlands, ashlands, jungle, wasteland, ice, cave) picked from a
  Whittaker-style temperature x moisture table; rivers and lakes flow
  downhill (priority-flood). Difficulty rises toward the centre (up to
  +120% enemy HP). 200 pre-populated lairs that aggro, leash and refill.
- **10 big named areas** (42x42-50x46 tiles, safe from lairs): Tavern Town,
  Oasis Bazaar, Frozen Lake Camp, Witch's Hollow, Mountain Monastery, Forge
  Camp, Botanist's Glade, Scrapyard, Crystal Caverns, Elk Meadow.
- **10 big islands** (~260 x 260 tiles each, drink-pun names such as Coral
  Colada Choir or Tidricane Sanctum) - **level-20 content**: the tide pushes
  anyone lower back off the beach, and the hub portals refuse them. Each has
  its own biome, 12 tough mob camps, a mini-boss arena (a wave "awakens" every
  5 minutes), a personal treasure chest, a walkway to the mainland and
  hub/return portals; island kills can drop mythic T12-T13 gear and Forge
  Ingots.
- **Landmarks and guardians**: one landmark per biome plus a doored lair
  building and a terrace; 20 curated decoration vignettes per biome.
- **Big multi-tile trees and props** (34 kinds in `game/big_props.py`):
  solid trunk, walk-under canopy that fades when you're beneath it; groves
  and clearings placed with Poisson-disk + density noise.
- **Nexus** (96 x 72): fountain plaza, Father Given, the Echo Keeper, a
  tavern, garden park, harbour and arena plaza, portals to the Realm, Bazaar
  and Vault. **Bazaar**: shared drop-and-grab room with permanent chests.
  **Vault room**: 12 permanent chests (8 slots each), opened one at a time.
- **Heroic dungeons**: a much harder version of every dungeon (elites only,
  more rooms, 3.6x HP, faster bullets, a crimson tint and aura, their own
  music, mythic loot). Unlock one by finishing that dungeon's **Heroic trial**
  (the local who lives near it wants 3 of the dungeon's relics); Heroic Shards
  then re-drop from Hard clears and Heroic bosses. Level 16+.
- **The Mad God's Room** (endgame): the Mad God, then **Unhinged**, then
  **Absolutely Livid**, back to back - each form has its own look, attacks,
  music and better loot; the last one always drops a Divine item. Opened by
  the rare Mad God's Room Key (Heroic bosses, calmed big islands); level 20
  and a T12+ item equipped.
- **Honest telegraphs**: every warned attack fires exactly where its warning
  pointed (ring gaps, wall gaps, lanes, cones and slam bursts are fixed when
  the warning appears); bullet rings and sweeps are shown as arrows (spokes)
  instead of a misleading circle.
- **Dungeons** from Dungeon Shards (8% elite drop): Forgotten Vault, Cave
  Warren, Frozen Crypt, Jungle Ruins, Ember Den, Sunken Grotto, Wind Spire,
  plus the story's Forge. Easy / Medium / Hard (HP x1.15 / 1.6 / 2.3),
  fog-of-war rooms, a 30% chance of a secret "???" quest and hidden boss,
  and a tougher phase-2 boss (x1.75 HP, x1.4 damage, faster fire).
- **Bosses**: an every-40-kills Mad God's Avatar, a roaming World Boss every
  15-25 minutes, 10 island mini-bosses. Bosses are drawn and hit at 2x size
  (mini-bosses 1.8x, guardians 1.5x).
- **Day/night** (4-minute cycle, Moonlit variants, rare Blood Moon),
  biome **weather** (blizzards shrink vision, sandstorms), **live events**
  rotating every 25 minutes (Double Loot Weekend, Happy Hour +50% XP,
  Blood Moon Week, Two-for-One Tuesday; `RR_EVENT` forces one).
- **Zone banners** fade in when you enter a zone, biome, area, island or
  dungeon (1.2 s dwell, 25 s repeat suppression, cross-fade).

### Economy
- **Echoes** (account-wide): 1 per 1000 XP earned plus a bonus on death.
  The **Echo Keeper** (Nexus) sells +1 backpack slots (60 / 120 Echoes, max
  2) and a starting-XP boost (30 Echoes).
- **Wishing fountain** (F in the fountain): sacrifices your lowest-tier item
  for a reroll, with a chance of a UT jackpot.
- Bazaar chests, trading, and 9 achievements that grant titles.

### Co-op
- Authoritative server with **personal loot + shared credit**: everyone who
  damaged a mob gets XP, story and side-quest credit and their own loot bag
  only they can see and open.
- **Trading** with invite / accept, offers that stay in your backpack until
  the swap, a 3 s confirm countdown and clear reasons when a trade can't
  complete; **Inspect** another player's gear; **friends** (L), **crews**,
  cross-zone **whispers**, **teleport** to a player, player hover tooltips.
- Everyone follows their own storyline; co-op Echo shop; per-player island
  chests.

### Music and sound
23 original ~60-second loopable rock tracks, one per zone, biome, island
theme and dungeon, rendered in the background and cached to `music_cache/`;
realm music follows your biome/area with a 2 s hysteresis and a ~1.5 s
crossfade. Track list in [GAME_DATA.md](GAME_DATA.md). Sound effects are
synthesized at runtime; `tools/export_audio.py` exports them as `.wav`.

### UI and options
- A framed right dock: day/night clock with zone name and kills, a wide
  radar minimap, player panel, Inventory/Pet tabs, equipment and backpack.
- Draggable chat and HUD quest log (positions saved), a draggable-and-
  resizable game window, FPS counter.
- **Options (O)**: master / music / SFX volume, mute, fullscreen, FPS cap
  (30 / 60 / 120 / unlimited), show FPS, screen shake, hit-stop, particles
  (off / low / high), auto-fire, plus Quest Log, Dictionary, reset camera,
  full map, leave. Saved to `settings.json`.

## Where saves live

`game/paths.py` decides the data folder: **next to the executable** in a
PyInstaller build, the **project folder** when running from source, or
`RR_DATA_DIR` if set. Inside it: `accounts/` (Echoes, unlocks, story act),
`characters/` (level, gear, backpack, pet, quests), `vaults/`,
`achievements/`, `friends/`, `crews/`, `settings.json` and `music_cache/`
(all gitignored). In co-op, these live on the host.

## Project structure

```
main.py              single-player game loop and states
server.py            co-op server (authoritative world, 30 Hz, interest management)
coop_client.py       co-op client (renders server snapshots, sends input/actions)
game/accounts.py     username accounts, Echoes, unlocks, Echo shop rows, story act checkpoint
game/achievements.py 9 achievements -> titles
game/areas.py        the 10 big realm areas + Nexus districts (stamped layouts)
game/audio.py        sound effects + music playback (volumes, crossfades)
game/big_props.py    multi-tile trees/props art, trunks and canopies
game/characters.py   per-character save/load
game/chat_input.py   chat input line: cursor, selection, clipboard, history
game/clipboard.py    copy/paste helper
game/codex.py        Dictionary entries built from the game's own tables
game/constants.py    screen/tile/net constants + stat and defense formulas
game/crews.py        crew tags + shared boss-kill counter
game/dialogue.py     finite dialogue trees + conversation state
game/entities.py     Player, Enemy (kinds/bosses/scales), Pet, Bullet, Bag, Portal, NexusBot...
game/friends.py      per-account friends list
game/items.py        weapons/armor/rings/abilities/UTs, loot rolls, pets, potions, vault storage
game/journal.py      Quest Log, Dictionary and Quest Map windows
game/live_events.py  rotating live-event schedule and multipliers
game/minimap.py      fog-of-war minimap and full map
game/music.py        23 procedural rock tracks, background render + disk cache
game/netmsg.py       newline-delimited JSON framing over TCP
game/npcs.py         NPC / talkable-creature definitions and placement
game/options_menu.py O-menu rows and input handling
game/panel_drag.py   draggable HUD panels
game/paths.py        where saves/settings live (next to the executable when frozen)
game/prop_art.py     procedural art for props without a painted PNG
game/realm_sim.py    shared Realm/dungeon simulation (lairs, combat, loot, islands, bosses, events)
game/settings.py     persisted options (settings.json)
game/sidequests.py   30 side quests, board, rewards, quest items
game/sprites.py      sprite loading + procedural pixel-art generation
game/story.py        story acts, objectives, checkpoints, act scaling, credits
game/ui.py           HUD, dock, panels, dialogue, trade, vault, menus, banners
game/vault.py        vault chest helpers
game/vfx.py          particles, ability styles, shake/hit-stop, fishing animation
game/weather.py      biome weather particles + tactical weather
game/world.py        terrain generation, tile maps, Nexus/Bazaar/Vault maps, camera, drawing
game/zone_banner.py  zone-entry banner state machine
tools/export_audio.py   export sound effects to .wav
tests/               63 regression check scripts (tests/check_*.py)
packaging/           Linux play/host/join.sh, Windows join.bat
docs/unity-rebuild/  feature-by-feature docs for rebuilding the game in Unity (00-29)
```

## Tests

```
.venv\Scripts\python.exe tests\run_all_checks.py        # Windows
.venv/bin/python tests/run_all_checks.py                # Linux
```

`run_all_checks.py` finds every `tests/check_*.py` and runs each as its own
headless process (`SDL_VIDEODRIVER=dummy`, throwaway settings, no music
rendering, no event rotation) and prints a PASS/FAIL summary - currently
**71/71**. The checks are plain asserts that drive the real game objects:
single-player `Game`, the co-op server's action handler and real
client-server sockets, rendered screenshots, timing budgets (e.g. world
generation < 3 s) and fixed-seed input fuzzing.

## Build & release

Releases are built by GitHub Actions (`.github/workflows/release.yml`,
workflow `build-release`): **push (or force-move) a `v*` tag**, or run it by
hand with `gh workflow run build-release -f tag=v0.2`. It builds the three
PyInstaller specs (`RealmReforged*.spec`) on Windows and Ubuntu 22.04,
smoke-tests that the server starts, and uploads the three `.exe` files,
`join.bat` and `RealmReforged-linux-x86_64.tar.gz` to that release.
To build locally: `pip install pyinstaller==6.22.3` then
`pyinstaller --noconfirm --clean RealmReforged.spec` (same for the Server
and CoopClient specs); output lands in `dist/`.

## Known limitations

- No client-side movement prediction: co-op input lag is one server tick
  plus network latency (fine on a LAN or Tailscale, noticeable on slow links).
- No auth or encryption, and movement is client-trusted - play with friends,
  don't expose the port to strangers.
- The co-op world map is still sent whole once per zone instance, but
  zlib-packed (`game/netmap.py`): ~0.17 MB instead of ~8 MB of JSON.
- Only Windows and Linux x86_64 builds (no macOS build; macOS can run from
  source). The Linux build is smoke-tested in CI but has had less real play.
- Python 3.13+ removed `audioop`; the music renderer falls back to a much
  slower pure-Python path there. The builds use Python 3.12.
- World generation takes ~1.4 s at startup. (The old "second build is 3x
  slower" note was Windows 11 power-throttling headless test processes, not
  the game - the timing checks now opt out of it, see `tests/_timing.py`.)
- Story length hasn't been re-measured for the 7-act arc (the old 5-act arc
  measured ~66 min by a scripted bot); the new acts and the endgame add a lot.
- Some UT/class flavour text is still just flavour (e.g. Paladin's
  "mace hits heal"); only the four UT proc kinds are real mechanics.
- Balance numbers (drop rates, spawn caps, XP curve) are tuned by feel.

## Version history

### v0.1 - first working pass
8 classes with RotMG stat profiles and the real stat formulas, a Nexus /
Realm / Bazaar / Vault loop, tiered + UT loot, permadeath, a small island
map, and a first co-op pass (`server.py` + `coop_client.py` over TCP/JSON).

### v0.2 - everything since (release tag `v0.2`)
Built in batches; each has a detailed doc in `docs/unity-rebuild/`.

- **Foundations (batches 1-7, docs 01-15)**: loot bags, vault chests,
  7 themed multi-room dungeons from Dungeon Shards, secret "???" quests,
  phase-2 bosses, telegraphed abilities, potions, per-class growth, a big
  biome continent with lairs, aggro/leash AI, day/night, Blood Moon,
  weather, co-op social suite (whispers, friends, context menus, hover
  tooltips), interest management, multiple concurrent co-op dungeon
  instances, fog-of-war minimap.
- **Wildlife, pets and The Reforging (batches 8-11, docs 20-23)**: neutral
  wildlife, mouse-driven HUD, multi-ability pets, the Reforging islands and
  portal hub, trading, precise collision, player animation, day/night clock.
- **Game feel and progression (batches 12-13, commit 2359371, doc 24)**:
  hit-stop/shake/particles, world boss, UT sockets, crews, live events,
  dash/roll, 26 mob redesigns, universal enemy animation, fishing overhaul.
  (That commit was titled "v0.3", but it is part of v0.2.)
- **Batch 14 (92c3086, doc 25)**: drink-pun islands with mini-bosses,
  curated decorations, right dock + Tab, per-zone music, Echo accrual,
  Bazaar chests, dungeon doors.
- **v0.2 final fixes (cafd86c, doc 26)**: options menu, trading overhaul,
  story campaign, pet bond/carriers/fusion.
- **Balance/terrain/UI round (doc 27)** and **Batch 15 "living world"
  (doc 28)**, released together as **Ends of V0.2 (65552b4)**.

### Ends of V0.2 - "final final" content update (current, still v0.2)
- **Honest telegraphs** (doc 31): no attack re-aims after its warning; spoke
  telegraphs for bullet moves; chained-dash lanes; Crossfire only hits from
  its circles; a test fires every warned move at a strafing player.
- **Story v2** (doc 32): Act I renamed **The Grand Tour** and turned into an
  exploration act; 7 acts total; old saves migrate.
- **Gear** (doc 33): T12-T14, the Anvil (temper / reforge), Forge Ingots,
  Divine items; **Heroic dungeons** with trial quests; level gates.
- **Big islands + the Mad God's Room** (doc 34).
- **Sound, music, effects**: 13 new synthesized event sounds, 10 new
  original tracks (7 Heroic dungeons + 3 Mad God's Room forms), new VFX.
- **Fix**: co-op clients lost (or replayed) one-shot events - chat lines,
  sounds, popups - when snapshots arrived faster/slower than frames.

### Ends of V0.2 (release tag `v0.2`)
- **Living world**: 11 NPCs + talkable creatures with real dialogue menus,
  30 side quests, Quest Log / Dictionary / Quest Map.
- **World**: terrain rewrite (organic biomes, rivers, lakes), 1308 x 1308
  map with ten 100 x 100 islands, 10 big named areas, a 96 x 72 Nexus, big
  multi-tile trees, 2x bosses, doored buildings.
- **Combat & balance**: percentage defense curve, spells x2.5 with 17
  distinct visuals, pets and spells ignore friendlies, Mad God tuning,
  story pacing from bot playthroughs.
- **Co-op**: personal loot + shared credit, island chests, cross-zone
  `/msg`, co-op Echo shop.
- **UI**: framed dock, wide clock/minimap, zone banners, chat
  cursor/selection/copy + right-click names, draggable panels, 12-chest
  vault, new Esc/quit flow, live-event rotation.
- **Music**: 23 original ~1-minute loopable rock tracks.
- **Follow-ups on the same release (30fb143, d09df8d)**: saves now live next
  to the executable (they used to reset every launch of the builds), Linux
  builds via GitHub Actions, Linux/Windows launch scripts, cross-platform
  co-op docs.

## Bugs found and fixed during development

Kept here because a couple were genuinely subtle and worth remembering:

- **The actual crash reported "when next to many mobs"**: a leftover generic
  fallback lair kind-set paired 4 enemy names with an 8(+)-entry weight list
  from an earlier balance pass, so `random.choices(kinds, weights=...)`
  would raise `ValueError: number of weights does not match the population`
  the moment a lair happened to generate on a plain decorative tile (not one
  of the named biome grounds) - rare on the old small island, much more
  likely once the continent grew to 64 lairs. Fixed by pairing that fallback
  with the full enemy pool and its matching weights.
- **Co-op could silently stall once the world got busy**: the server sent
  literally every enemy in the realm to every client, every tick. That was
  fine at the old ~22-enemy cap, but with the continent now pre-populated up
  to ~250 enemies, each snapshot ballooned and a client that couldn't drain
  its socket fast enough would back up the server's send calls - which looks
  exactly like "actions stopped working" (an equip/drop message would sit
  unprocessed). Fixed with simple interest management: each client only
  gets enemies/bullets/ground-items within ~1400px of their own position.
- **Dropping an item made you instantly re-pick it up**: a manually-dropped
  item lands exactly on the dropper's own feet, and the pickup check runs
  again the very next tick - so without a fix, "drop" and "pick back up"
  were functionally the same action for whoever dropped it (anyone else
  standing there could still grab it fine). Fixed with a brief self-pickup
  immunity window scoped to the dropper's pid specifically - everyone else
  can still grab it immediately.
- **Fullscreen could throw off mouse aim**: the old fullscreen toggle
  rendered onto a fixed-size canvas and scaled it up to fill the display,
  but `pygame.mouse.get_pos()` reports coordinates in real window space -
  so aim math done against the (smaller) canvas size was quietly wrong by
  the scale factor. Fixed by making the canvas always match the window
  pixel-for-pixel instead of scaling, which also means fullscreen now shows
  more of the world rather than just a bigger version of the same view.
- **Bullet tunneling at low tick rates**: the co-op server ticks at a lower
  rate than the 60fps client, so a fast bullet's per-tick movement could
  exceed its own hit radius, letting it pass through a point-blank target
  before ever being collision-checked. Fixed with swept (segment-based)
  collision instead of an end-of-tick-position-only check.
- **Bonus rooms never actually spawned enemies** - the spawn condition had
  an inverted guard (`not is_bonus_room`) left over from before bonus rooms
  supported spawning at all, so the "denser loot" room was silently always
  empty. Caught while wiring up difficulty tiers.
- **Lair placement left the player with nothing nearby**: early lair
  generation scattered all lairs uniformly across the (now much bigger)
  map, so a fresh spawn point could have zero enemies within detection
  range. Fixed by guaranteeing a few lairs close to spawn.
- Sending the realm's full tile grid on every network tick (~300KB/s per
  client) could make a client's socket fall behind and act on stale
  positions - looked exactly like "shots keep missing." Fixed to send the
  map once per zone-instance instead of every tick.
- The stereo-sound bug: the mixer was asked to initialize as mono but
  silently came back stereo, and the generated buffers were still mono -
  played back, that misreads two consecutive mono samples as one stereo
  L/R frame, which would have made every sound effect play at roughly
  double speed/pitch. Fixed by querying the mixer's *actual* channel count
  after init and building buffers to match, rather than what was requested.
- The camera-rotation buffer's tile-culling initially used a hardcoded
  screen-size constant instead of the actual (larger) buffer size, which
  would have left the buffer's edges undrawn - showing as background-colour
  gaps at the screen corners once rotated. Fixed by passing the real
  surface size into the tile-culling call.

Found in the "Ends of V0.2" round:

- **The long-standing "dragged an item into a portal and it crashed" bug**:
  found by seeded input fuzzing - dragging the equipped weapon onto the
  ground and then firing read the damage of a weapon that no longer
  existed. In co-op it happened inside the server tick and froze everyone.
  Firing is now skipped while no weapon is equipped.
- **Hand-painted art never showed in the real game**: the clients imported
  `game.world` before a display existed, so every PNG load failed silently
  and fell back to flat tiles (the tests always opened a display first).
- **Saves reset on every launch of the released builds**: a one-file
  PyInstaller build unpacks into a new temp folder each run, and the save
  paths were relative to the module files. Fixed with `game/paths.py`.
- **Co-op client crashes** the first time a portal, a loot bag or a Bazaar
  chest was drawn (the `Ghost*` stand-ins lacked fields `draw()` needed).
- **Vault-room crash**: the big-prop overhang scan wasn't clamped to the map
  when the camera sat right of a map narrower than the view.
- **Far-away wildlife lines in chat**: mob speech had no position; it now
  only reaches players within 600 px.
- **Island index drift**: a skipped island placement shifted every later
  island's name and mini-boss.
- **Pet feed target covering the equip bar** (drops onto equip slots fed
  the pet), and the **Echo shop reopening** on the next frame while you
  still stood on its tile.
