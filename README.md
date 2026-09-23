# Realm Reforged (v0.2)

A from-scratch, original-code prototype inspired by **Realm of the Mad God**
(RotMG) - a top-down bullet-hell MMO-lite, now with real co-op. No RotMG
assets, sprites, or code were used; every sprite is procedurally generated
pixel art (and every sound effect/music track is a procedurally synthesized
waveform), and every gameplay number comes from formulas published on the
RotMG wiki, re-derived independently in `game/constants.py`.

## Version history

### v0.1 - first working pass
- 8 classes, each with a real RotMG stat profile and distinct weapon behaviour.
- The real ATT/DEF/SPD/DEX/VIT/WIS formulas driving damage, mitigation, move
  speed, attack speed, and regen.
- A basic Nexus / Realm / Bazaar / Vault loop, tiered + untiered (UT) loot,
  and permadeath.
- A small island map with basic enemy spawning.
- A first working co-op pass: `server.py` + `coop_client.py` over a plain
  TCP/JSON protocol.

### v0.2 - everything since (this is the current version)
Bigger world, living AI, and a long list of systems added on top of v0.1 -
all still under the v0.2 umbrella (v0.3 hasn't started yet, see below).

**World & exploration**
- An immense continent (900x900 tiles, up from 800x800) with an organic,
  domain-warped coastline and **ten** Voronoi-style biome regions (Forest,
  Desert, Tundra, Swamp, Highlands, Ashlands, Jungle, Wasteland, Ice, Cave) -
  warped with layered sine noise plus a dithered "ecotone" blend at
  boundaries so biomes bleed into each other instead of meeting at a
  razor-sharp edge. 900x900 was picked by actually benchmarking, not
  guessing: 1200x1200 (~4.4s) and 1600x1600 (~7.8s) both blew past a ~3s
  "feels like loading, not hanging" budget for realm generation even after
  optimizing the generator itself (precomputed sin/cos tables for the
  boundary-warp noise, plus early-outs for tiles that are guaranteed land or
  guaranteed ocean regardless of angle) - 900x900 measured ~2.6s for a full
  realm (map + all ~200 lairs populated) with real background load on the
  dev machine. Lair count scales with map area (200 lairs, up from 160) to
  keep the world feeling equally alive at the bigger size, but deliberately
  not further: the co-op lair-replenishment scan is O(lair_count x
  enemy_count), and scaling lair count all the way up to match 1200x1200/
  1600x1600 pushed that scan past 20-100ms - a real stutter against the 30Hz
  co-op tick budget. Also fixed two perf/correctness issues found while
  verifying the bigger map: the full-map screen (M key) was scaling the
  *entire* continent to a huge offscreen surface every frame just to show a
  player-sized window of it (~40ms/frame, worse than one 60fps frame budget,
  and it gets worse as the map grows) - fixed to crop to the visible region
  before scaling (~4-5ms/frame now, and flat regardless of map size); and a
  co-op networking bug where the realm's tile map (a multi-MB one-time JSON
  message) could be silently and permanently lost for a session if a faster,
  smaller snapshot from a tick or two later overwrote it before the client
  ever read it - fixed by buffering the map separately from the "latest
  snapshot wins" logic the instant it's seen on the wire.
- Biomes are tiered by distance from the continent's center (outer = gentler
  Beaches/Lowlands-style zones, inner = tougher Godlands-style zones), each
  with its own signature ecosystem mobs and a real distance-based difficulty
  gradient (up to +120% enemy HP dead-center).
- A **day/night cycle** (smooth sinusoid, ~4 minutes per full cycle): nights
  spawn enemies faster and roll a chance of tougher, better-loot "Moonlit"
  variants; nights also have a rare **Blood Moon** event with even higher
  danger/reward and ambient ember damage in the Ashlands.
- A **weather system**: rain/snow/sand/ash particle effects tied to the
  biome you're standing in, plus a real (not just cosmetic) speed penalty
  wading through snow/ice.
- A real multi-room dungeon structure for mob-death bonus portals, now in
  **7 distinct themes** (Cave Warren, Frozen Crypt, Jungle Ruins, Ember Den,
  Sunken Grotto, Wind Spire, Forgotten Vault) - which enemy dropped the
  portal decides the theme, each with its own floor texture, signature mob
  roster, and boss pool, ending in a dedicated boss room. Rooms have real
  per-theme SHAPE, not a re-tinted floor - a Cave Warren's rooms are organic
  carved blobs, a Sunken Grotto winds through a snaking chain of chambers, a
  Wind Spire climbs a long, mostly-linear corridor of narrower rooms. Most
  rooms hold a fixed, non-respawning pod of 4-8 enemies (clear it or rush
  past, nothing gates the doorway either way), some hide a one-shot
  destructible wall obstacle, and dungeon rooms use real fog-of-war on the
  live view itself (not just the minimap) - a room's contents stay hidden
  until you've actually walked in. Every room is also hand-decorated with
  themed props (torches, rubble, tapestries, idols, crates, bones,
  crystals, growth, puddles, chains, plus one unique special per theme).
- **Dungeon Shards, not ambient portals**: elite kills have a chance to drop
  a carried Dungeon Shard item instead of instantly opening a portal at the
  kill spot - use it from the backpack whenever/wherever you like to tear
  open a themed portal, everyone nearby can walk in together. The dungeon's
  Easy/Medium/Hard difficulty (scaling enemy toughness, enemy cap, and how
  many times loot is rolled per kill) is rolled the instant the shard is
  used and shown as a color-coded label floating on the portal itself.
- **A secret "???" quest, sometimes**: about 30% of dungeons hide one of
  three quests (hunt down a specific trash mob, destroy 3 stationary
  Totems, or beat the boss within a time limit), tracked live in a
  right-docked HUD panel. Completing it carves open a hidden, freshly
  decorated loot room with a harder "???" boss inside.
- **A genuinely harder second phase on some bosses**: killing a dungeon's
  main boss can open a single portal into a reserved pocket room holding a
  visibly darker, ~60% tankier, ~40% faster-firing version of the same
  boss (real bespoke "enraged" art per boss - a glow halo, bloomed
  highlights, and crack/vein detailing, not a flat recolor) - optional, a
  Realm-exit is always available at the pocket boss's own death too.
- **Portals are a deliberate action, not a walk-over trigger**: standing on
  or near any portal shows a "Press ENTER to enter" prompt in the
  bottom-right corner instead of instantly teleporting you. Every portal
  kind (entrance/realm-exit/phase-2/shard-opened) reads as visually
  distinct - a different color AND shape (a rotating vortex, a calm light
  beam, a jagged spiked rift, a torn crack), not just a re-tinted circle.
- A living, pre-populated ecosystem: every lair is populated the moment the
  realm is created (not spawned-on-approach), idle-wanders near home,
  aggros/leashes realistically, and quietly refills over time.
- A zoomable, fog-of-war minimap (corner + full-map M key, +/- or scroll to
  zoom) that only reveals tiles you've actually explored.
- A bigger, fountain-plaza Nexus (with banner pillars) and a bigger Bazaar
  (its own fountain plaza + market stalls), both well beyond their original
  cramped size.

**RPG systems**
- **Loot scaled by individual mob difficulty, not just rank**: two mobs of the
  same rank (trash/elite/boss) used to roll from the identical tier range even
  when one was much tougher to actually fight - a tanky troll and a squishier
  frost_sprite, both elites, dropped from the same band. Each of the 24 regular
  mobs and 6 bosses now gets a difficulty score from its HP, average per-hit
  damage x how aggressively its bullet pattern fires, and speed
  (`entities.difficulty_fraction`), which raises the FLOOR of the tier range
  `roll_loot()` draws from for tougher mobs of a rank - the weakest mob of each
  rank is untouched (still the full original range), so nothing gets nerfed,
  only the tougher end of the roster pulls ahead. Bag rarity odds (brown/
  purple/white) and drop chances are unaffected. Example: troll vs.
  frost_sprite (both elite) used to average the same tier (4.9); now troll
  averages tier 6.9 while frost_sprite stays at 4.9 - see
  `tests/check_loot_difficulty.py`.
- Full item descriptions/flavor text on every weapon, armor, ring, ability,
  potion, and egg - not just stat numbers.
- Active class abilities (Space to cast) with **7 distinct effect kinds**:
  nova, heal, haste, and four "capstone" ultimate effects - chain lightning,
  lifesteal drain, freeze/root, and a damage-absorbing shield.
- **Pets, hatched from eggs**: 7 pet kinds across common/uncommon/rare/
  legendary rarity, each passively healing, restoring mana, or attacking the
  nearest enemy on a cooldown - both power and cooldown scale with rarity
  through one shared formula.
- **Achievements & titles**: 8 achievements (first kill, first dungeon
  clear, hatching a pet, a fishing catch, a wishing-fountain jackpot,
  slaying a Realm avatar, hitting level 10/20) persisted per character name,
  with the most recently unlocked title shown next to your name.
- **Fishing**: stand at the water's edge, press F to cast, then press again
  during a brief bite window to reel in tiered loot, an egg, or a rare UT.
- **A wishing fountain** in the Nexus: press F on the fountain to sacrifice
  your lowest-tier item for a reroll - mostly a sidegrade, sometimes an
  upgrade or downgrade, rarely an untiered jackpot (with its own fanfare).
- **A RotMG-style Vault**: no longer an instant popup - the Nexus's Vault
  tile now leads into a real, fixed, hand-authored Vault room with **10**
  chest tiles to walk up to. Opening a chest shows the familiar 8-slot-per-
  chest screen (80 slots total) with tabs to page between chests, drag-and-
  drop deposit/withdraw (the same system as backpack/bags, not click-only),
  and a dedicated "Close Vault" button - not Enter/Escape, which could
  otherwise feel stuck if you were still standing on a chest when you
  closed it.
- **Loot bags, not single ground items**: everything a kill drops (one item
  or several, on a boss) pools into one RotMG-style 8-slot bag instead of a
  separate pickup per drop, colored brown/purple/white by the rarest thing
  inside - back-to-back kills near each other pool into the same bag too.
  Right-click to open a bag's contents in a small drag-and-drop window;
  bags despawn after 2 minutes.
- **A bigger, livelier Nexus (64x50, up from 36x28)**: garden clusters, a
  minor well, and an announcement board scattered around the plaza, a
  drifting parallax backdrop so it doesn't end in hard black past the walls,
  and random ambient events (a bird flyby, a distant chime, a light
  flicker, extra NPC wandering) on an unpredictable cooldown - not a fixed
  loop.
- **Neutral wildlife**: forest hares and cave moths wander the Godlands and
  never fight back, even when attacked - pure ambient life and a trash-tier
  kill, not a threat.
- **Mobs have a voice**: each enemy's hit/death sounds are pitched by a
  sound "family" (beast/undead/elemental/construct), and non-neutral mobs
  occasionally bark a short flavour line in a speech bubble, guaranteed once
  on aggro and a small chance per second afterward.
- **A persistent, always-on chat log** faded in on the left side of the
  screen (last 12 messages, sender name included), separate from the
  ephemeral in-world speech bubbles above players' heads - both now support
  messages up to 1000 characters with real word-wrap instead of a 48-140
  character hard cut.
- **Cross-class drops and 3 armor archetypes**: any class can drop another
  class's weapon/ability/armor about 40% of the time (kill an enemy on
  Archer, sometimes walk away with Priest gear), and armor itself now comes
  in the three real-RotMG archetypes - Heavy (Warrior/Paladin), Light
  (Archer/Assassin/Rogue), Robe (Wizard/Necromancer/Priest) - instead of one
  shared table.
- **A boomerang projectile**: one existing UT weapon per class now fires a
  bullet that travels out and curves back toward where it was fired from,
  able to land a second hit on the way back - a real new projectile motion,
  not just a different color.
- **All 4 UTs per class are mechanically distinct**: alongside the boomerang
  UT above, the other 3 each apply a status effect on hit - bleed (a DoT),
  burn (a shorter, harder-hitting DoT), or vulnerable (a temporary incoming-
  damage multiplier, since enemies have no DEF stat to actually pierce).
- **Telegraphed abilities**: Nova/Chain/Drain/Freeze no longer resolve the
  instant you cast them - a warning ring marks exactly where the impact
  will land, with a real, dodgeable ~0.45s window before it actually goes
  off. Damage was bumped up to compensate for the new dodge window, so a
  landed cast still feels like a real burst on a real cooldown.
- **A permanent + temporary potion system**: 6 stat potions (one per
  ATT/DEF/SPD/DEX/VIT/WIS) give a permanent +1 when drunk, capped at 20
  drinks total per character (freely allocated across the 6 stats) so
  stacking is a real, finite choice, not infinite grinding. A separate
  temporary-draught family gives a much bigger (+6), ~60-second buff
  instead, uncapped. Both families now drop from mobs at every rank, not
  fishing-only.
- **Per-class level-up growth, not one identical curve**: HP/MP growth now
  scales with each class's own Heavy/Light/Robe armor archetype (a Warrior
  ends up meaningfully tankier by level 20 than a Wizard, who ends up with
  meaningfully more MP instead), and every one of the 6 core stats rolls a
  little every level - a class's own "signature" stats (the same ones its
  starting stat profile already emphasizes) grow faster than the rest.
- **Visible progress**: an XP bar (with the exact `current/needed` numbers)
  next to your level, and being healed or given mana (from a pet, Priest,
  or an ability) now visibly rises off your character as a burst of
  sparkles instead of only being visible through the HP/MP bars moving.

**Co-op**
- **Trading with a confirmation timer**: `/trade` a nearby player, drag
  items in, both Accept, then a 3-second countdown (any change resets it,
  same anti-scam behaviour as the real game) before the swap actually
  happens. Auto-cancels on disconnect, death, distance, or idle timeout.
- A full chat system: Enter to open a pop-up chat box, slash commands
  (`/nexus`, `/realm`, `/vault`, `/bazaar`, `/trade`, `/help`), and messages
  shown as speech bubbles above the speaking player.
- Hover tooltips on other players (class, level, gear, stats, HP, title).
- Interest management (enemies/bullets/items are only sent to clients within
  range) so the server stays responsive with a large, busy world.

**Combat feel & presentation**
- Soft aim assist, auto-fire toggle, floating damage numbers, hit-flash.
- **A real projectile shape per class**, not just a color - Archer fires
  arrows, Warrior/Paladin fire blades, Rogue/Assassin fire throwing stars,
  Priest fires a holy cross-in-ring, Necromancer fires bones, Wizard fires
  an orb (enemy bullets keep the original plain bolt look).
- **Every character, monster, and boss is hand-painted**, not flat
  procedural shapes - all 8 classes, all 27 regular enemy kinds, all 6
  bosses (each with a distinct "enraged" phase-2 look - a glow halo,
  bloomed highlights, and crack/vein detailing, not a flat recolor), the
  Totem quest-enemy, and the destructible dungeon Obstacle prop. Nexus,
  Vault, every biome, and every dungeon theme are scattered with matching
  hand-painted decoration props (banners/statues/gardens, chests/pillars/
  bookshelves, rocks/bushes/trees, torches/rubble/crystals/idols, etc.) -
  not empty floor tiles. Item icons (weapons, armor, rings, eggs, the 6
  potion colors + their bigger/glowing temporary-draught versions, and
  dungeon shards) are hand-painted or procedurally shaded to match, not
  placeholder squares.
- **Four distinct per-room music tracks** (Nexus, Bazaar, Realm, Dungeon),
  each a procedurally synthesized multi-voice piece (lead + bass +
  percussion) with its own tempo/key/instrumentation, switching
  automatically as you move between zones - not one single looping theme.
- A full procedural sound effects set (no audio files anywhere), including
  a wishing-fountain jackpot fanfare.
- Q/E camera rotation, a resizable/fullscreen window that actually widens
  your view instead of just scaling up, click-and-drag inventory, ground-
  item tooltips + a nearby-loot preview panel (RotMG's "proximity menu"),
  and an interactive options menu (O key).

### v0.3 - not started yet
Nothing yet - the next batch of ideas (more mob-sprite polish, a wandering
Nexus NPC, a standing automated test suite, and whatever else comes up)
will land here once it's actually built and tested, not before.

## Play solo

```
.venv\Scripts\python.exe main.py
```

That's it - single-player needs nothing else running.

## Play co-op with a friend

One person **hosts** (runs the server); everyone, including the host,
**joins as a client**.

**1. Host: start the server.**

```
.venv\Scripts\python.exe server.py
```

Leave this window open - it's the shared world. It prints the port it's
listening on (default `50777`).

**2. Host: find the IP your friend should connect to.**

- Same house / same WiFi (LAN): run `ipconfig` (Windows) in another terminal
  and use the "IPv4 Address" (something like `192.168.1.23`).
- Over the internet: you'll need to either port-forward `50777` on your
  router to your PC, or use a tunnel tool (e.g. `ngrok tcp 50777`) and share
  the address it gives you. This is a plain, unencrypted LAN-style protocol
  with no accounts - treat it like a Minecraft LAN game, only share the
  address with people you trust.

**3. Everyone (including the host): launch the client.**

```
.venv\Scripts\python.exe coop_client.py --host <server-ip> --port 50777 --name YourName
```

- Playing on the same PC as the server? Use `--host 127.0.0.1`.
- `--name` is just a display name (shown above your character, and on the
  hover tooltip other players see when they mouse over you).
- Pick a class on the screen that opens, hit Enter, and you're in the
  shared Nexus with everyone else who's connected.

**Stopping the server**: `Ctrl+C` in its terminal. Everyone's session ends
(their client will show a "Disconnected" screen).

## Controls (both modes)

| Key | Action |
|---|---|
| WASD / arrows | Move |
| Mouse | Aim (soft-assisted - see below) |
| Left click (hold) | Fire, rate scales with your DEX |
| 1-8 / click a backpack slot | Use/equip that item |
| Click + drag | Drag items between backpack/equip slots, or drag off the bar to drop on the ground |
| I | Toggle auto-fire (fires continuously without holding the mouse button) |
| Enter | Confirm menus / step through a portal you're standing near ("Press ENTER" prompt) / interact with a Vault or Bazaar tile |
| R | Nexus (teleport to hub) while in the Realm or Bonus Room |
| Q / E | Rotate the camera (a real RotMG feature, confirmed on its wiki's Controls page) |
| X | Reset camera rotation |
| M | Full map (scroll wheel or +/- to zoom); a small corner minimap is always visible |
| F11 / native maximize button | Toggle fullscreen - actually widens the view, not just a bigger window |
| O | Open the options menu - Up/Down to move, Enter to activate (toggles + a controls reference) |
| Esc | Quit / leave the Vault / close the menu / close the full map |

## Features

### Core RPG systems
- **8 classes**: Wizard, Archer, Warrior, Priest, Rogue, Necromancer,
  Paladin, Assassin - each with a distinct weapon behaviour and stat
  profile, picked from a stat-comparison character-select screen (live
  ATT/DEF/SPD/DEX/VIT/WIS bars per class, RotMG character-creation style).
- **Real stat formulas**: ATT/DEF/SPD/DEX/VIT/WIS drive damage, mitigation,
  move speed, attack speed, and regen exactly per the public wiki's
  formulas (`game/constants.py`) - verified numerically, including that
  weapon damage really does scale with ATT (`DMG = roll(min,max) *
  (ATT+25)/50`) uniformly across every class's fire behaviour, and that VIT
  regen has no hidden cap (tested up to VIT 100+ from gear stacking).
- **Enemy HP scaled up** (~2.2x trash/elite, ~1.6x boss vs. the original
  v0.2 numbers) to feel closer to real RotMG Godlands HP pools - the old
  numbers let most trash die in one hit, which didn't feel like RotMG at
  all - while stopping well short of the real game's late-game grind, since
  this is still meant to be beatable in a single co-op session.
- **Fast levelling**: a steeper XP curve and bigger per-level stat gains
  than a "realistic" RotMG pace - a level 1-20 run is an evening, not weeks.
- **Tiered + untiered loot**: multiple weapon/armor/ring tiers per class,
  rare named UT items with unique procs, and brown/purple/white bag rarity
  odds bumped up for a generous co-op pace.
- **Permadeath**: hitting 0 HP ends that character for good.

### World
*(Map size/biome count/lair count are covered in "Version history > v0.2"
above, which stays the single up-to-date source for those numbers - not
repeated here to avoid the two drifting out of sync again.)*
- **A biome-flavoured, persistent ecosystem**: each biome leans toward its
  own signature mobs (a Desert biome leans Scorpions, a Tundra leans Yetis,
  and so on), paired with a generic trash mob for flavour - so exploring the
  continent actually feels like visiting different zones with different
  residents. Every lair is populated with monsters the moment the realm is
  created - the world is already alive when you arrive, you're not waiting
  for things to spawn in as you explore - and a killed lair quietly refills
  over time (never right on top of a player) once no one's nearby.
- **A zoomable map**: a small corner minimap is always visible, and the full
  map (M key) shows the whole continent - both use real fog-of-war, only
  revealing tiles you've actually walked near, exactly like RotMG's map
  screen builds up as you explore. Scroll wheel or +/- to zoom the full map;
  opening it pauses your own actions like a real menu screen.
- **Living enemy AI**: enemies idle-wander near their lair (liveness instead
  of standing frozen), **aggro** onto a player who gets close enough, chase
  while aggro'd, and **leash** back home and go idle again if kited too far
  away - a real notice/chase/give-up state machine, not just "always beeline."
- **The Nexus, a Vault, and a Bazaar**: the Nexus hub has three tiles - the
  Realm portal, a Vault (account-wide item storage that persists across
  permadeath, click to deposit/withdraw), and a Bazaar (a shared trade-floor
  room where you can genuinely drop items on the ground for others to grab -
  there's no formal player-shop/currency system yet).
*(Dungeon Shards, per-theme room shapes, the secret "???" quest, boss
phase-2, and the portal Enter-prompt are all covered in "Version history >
v0.2" above too, for the same reason - not repeated here.)*
- **Bullet-hell enemies + a boss**: aimed shots, spreads, ring-bursts, an
  erratic-flight bat, and a multi-phase spiral/nova boss every 40 kills.

### Combat feel
- **Soft aim assist**: if an enemy is within a narrow cone in front of your
  mouse aim and in range, your shot snaps onto it - manual aim still
  matters, but near-misses land. Same behaviour in single-player and co-op.
- **Auto-fire toggle (I key)**: keeps firing (still aimed with the mouse and
  the same soft assist) without needing to hold the mouse button down. Off
  by default.
- **Floating combat damage numbers** and a **hit-flash** on enemies, in
  addition to the existing HP-bar feedback.
- **Full sound**: procedurally synthesized (no audio files) sound effects
  for firing (a distinct tone per class), taking damage, hitting an enemy,
  picking up an item, levelling up, a boss appearing, and dying - plus a
  short looping original background theme. Impact sounds (hit/death/boss)
  use a proper percussive envelope (fast attack, exponential decay) layered
  with a second harmonic or noise burst for a punchier feel than a flat
  tone. All audio is best-effort and can never crash the game if no sound
  device is available.
- **Q/E camera rotation, X to reset** - RotMG really does have this
  (confirmed on its wiki's Controls page). Implemented by rendering the
  world onto an oversized offscreen buffer and rotating that whole image,
  so the tile floor itself turns seamlessly, not just entity positions -
  mouse aim accounts for the rotation too. The HUD stays screen-anchored
  (it doesn't spin with the world).
- **A docked, translucent controls overlay (O to toggle)** - RotMG's own
  options/controls screen is opened with "O"; this mirrors that, but is
  deliberately a small panel off to one side instead of a full-screen
  modal, so it never blocks the play area.

### Co-op
- **Real client-server co-op**: `server.py` you host once, `coop_client.py`
  everyone (including the host) connects with. The server is authoritative
  for enemies/damage/loot/XP; movement is client-trusted (fine for playing
  with friends, not hardened against cheating).
- **Hover tooltips on other players**: mouse over a nearby player (in the
  Nexus or the Realm) to see their class, level, equipped gear (with tier
  colours), stats, and current HP - mirrors RotMG's "hover a name" info.

### Presentation
*(Hand-painted character/monster/boss/decoration art is covered in
"Version history > v0.2 > Combat feel & presentation" above - not
repeated here.)*
- **A real, resizable window**: drag an edge or click the native maximize
  button (next to minimize/close) - not just F11. Either way, the render
  canvas is resized to match the window pixel-for-pixel rather than being
  scaled, so going fullscreen/bigger actually shows more of the world (a
  wider field of view), and mouse aim always lines up correctly at any
  size - no more misaimed shots in fullscreen.
- **A right-docked inventory**, RotMG-style: the equip grid and backpack sit
  right below the corner minimap on the right edge of the screen, instead of
  a bottom-left bar. The Vault screen keeps its own independent layout since
  it's a separate full-page view, not part of the live HUD.
- **Click-and-drag inventory**: drag items between backpack and equip slots
  (invalid drops, like a ring onto the weapon slot, are cancelled), or drag
  an item off the bar entirely to drop it on the ground in the Realm, a
  Bonus Room, or the Bazaar. A brief pickup-immunity keeps you from
  instantly re-grabbing your own drop, while anyone else can grab it right
  away.
- **Ground-item tooltips**: hover a dropped bag (yours, a monster's, or a
  co-op peer's) to see what's inside before deciding whether to walk over
  and grab it, instead of only finding out after an automatic pickup.
- **An actual interactive options menu (O key)**: Up/Down to move, Enter to
  activate - toggle auto-fire or fullscreen, reset the camera, jump straight
  to the full map, or abandon the run - with the controls reference still
  shown below it, not just a read-only list.

## Structure

```
main.py            single-player game loop and states
server.py           co-op server: owns the shared Nexus/Bazaar/Realm/Bonus-room state
coop_client.py       co-op client: connects to server.py, renders server snapshots
game/constants.py   screen/tile constants + the RotMG stat formulas
game/sprites.py     procedural pixel-art generation (auto-outlined, auto-shaded ASCII grids)
game/audio.py       procedural sound effects + theme (raw waveform synthesis, no assets)
game/items.py       item/tier/loot-table definitions + Vault persistence
game/entities.py    Player, Enemy, Bullet, Bag, Portal, Obstacle (+ network (de)serialization)
game/realm_sim.py   shared realm/combat simulation used by BOTH main.py and server.py
                     (lair spawning, aggro/leash AI hooks, aim assist, dungeon generation/quests)
game/world.py       tile map generation (Nexus/Bazaar/Realm/Bonus room) + camera
game/minimap.py     fog-of-war exploration tracking + corner/full-map rendering
game/ui.py          HUD, inventory bar, Vault screen, class-select, peer tooltips
game/vfx.py         burst/ring/rise particle effects + screen-shake (heals, deaths, abilities, etc.)
game/weather.py     rain/snow/sand/ash particle effects tied to the current biome
game/accounts.py    username-only account identity (accounts/<name>.json)
game/characters.py  per-character save/load (level/xp/gear/backpack, characters/<name>.json)
game/friends.py     per-account friends list (friends/<name>.json)
game/clipboard.py   tkinter-based copy/paste for the in-game chat box
game/netmsg.py      newline-delimited JSON framing over TCP, shared by server/client
tools/export_audio.py   renders every procedural sound effect to a real .wav file
```

## Known limitations

- No client-side movement prediction: your own position is whatever the
  last server snapshot said, so co-op has ~1 tick + network latency of
  input lag. Unnoticeable on a LAN, noticeable over a slow connection.
- No auth, no encryption, movement is client-trusted. Fine for playing with
  friends; don't expose the port to the open internet without understanding
  that risk.
- The Bazaar is a shared drop-and-grab room, not a real player-shop/
  currency economy.
- Priest's passive ally-heal-on-hit is now wired into combat (a small trickle
  on every tiered/UT weapon hit); Paladin's identically-worded "mace hits
  heal on contact" class description is still flavour text only. Every
  class's 4 UTs are now mechanically distinct, though not each 1:1 with its
  own flavor text - one fires a boomerang (travels out, curves back), and
  the other three each apply one of bleed/burn/vulnerable (a DoT, a
  faster-ticking DoT, or a temporary incoming-damage multiplier) on hit.
  Every OTHER UT-specific proc description beyond those 4 mechanics remains
  flavour text only, not yet its own distinct mechanic.
- Item names are original, RotMG-style tiered gear names (the real wiki's
  item tables run into the hundreds of entries per class) - the *mechanics*
  (tier bands, stat formulas, bag rarity odds) are reproduced from the wiki.
- Balance numbers (drop rates, spawn caps, XP curve, aggro/leash ranges) are
  tuned by feel.

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
