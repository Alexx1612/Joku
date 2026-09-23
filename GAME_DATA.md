# Game data reference (per version)

A versioned snapshot of the audio sound effects, achievements, and per-class
base stats - so there's a historical record as these change, not just
whatever's currently in the code. Update this alongside README.md's own
version changelog when any of the three lists below change.

## v0.2 (current - everything below is still v0.2, not a new version)

### Audio sound effects (`game/audio.py`)

All procedurally synthesized at runtime - no audio files anywhere.

| Function | Used for |
|---|---|
| `play_shoot(cls_name)` | Firing your weapon - per-class tone |
| `play_hit()` | Player takes damage |
| `play_enemy_hit()` | An enemy takes damage (generic, pre-family-sound pass) |
| `play_mob_hit(family)` | An enemy takes damage, family-tinted (beast/undead/elemental/construct) |
| `play_mob_death(family)` | An enemy dies, family-tinted |
| `play_mob_bark(family)` | A mob's idle/aggro flavor-line vocalization, family-tinted |
| `play_pickup()` | Picking up an item |
| `play_drop()` | Dropping an item |
| `play_death()` | The player dies |
| `play_levelup()` | Leveling up |
| `play_ability()` | Casting your equipped ability |
| `play_boss_spawn()` | A boss appears |
| `play_wish(jackpot)` | Wishing-fountain reroll (fanfare variant on a jackpot) |
| `play_theme(zone)` | Per-zone background music (Nexus/Bazaar/Realm/Dungeon) |

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
| `legend` | the Legend | Reach level 20 |

### Class base stats (`game/entities.py`'s `CLASS_BASE`)

| Class | HP | MP | ATT | DEF | SPD | DEX | VIT | WIS | Growth cycle (per level-up) |
|---|---|---|---|---|---|---|---|---|---|
| Wizard | 100 | 100 | 10 | 5 | 25 | 15 | 10 | 30 | wis, att, vit, wis, dex |
| Archer | 90 | 70 | 15 | 10 | 35 | 25 | 15 | 10 | dex, att, spd, vit, dex |
| Warrior | 130 | 50 | 15 | 25 | 20 | 15 | 25 | 5 | deF, vit, att, deF, spd |
| Priest | 100 | 120 | 5 | 10 | 25 | 10 | 15 | 35 | wis, vit, wis, deF, dex |
| Rogue | 85 | 60 | 12 | 8 | 40 | 30 | 12 | 8 | dex, spd, att, dex, vit |
| Necromancer | 95 | 110 | 8 | 6 | 22 | 12 | 12 | 32 | wis, att, wis, vit, dex |
| Paladin | 140 | 80 | 10 | 22 | 18 | 12 | 22 | 18 | deF, vit, wis, deF, vit |
| Assassin | 80 | 65 | 14 | 6 | 38 | 32 | 10 | 8 | dex, att, dex, spd, vit |

At v0.2, every level-up applies a flat `+14 hp_max / +10 mp_max` plus `+4` to
one stat picked from the class's own growth cycle above (same flat amount
for every class - not yet class-differentiated beyond which stat is picked).

## Changes since the table above (still v0.2 - not bumped to v0.3 yet)

The user has confirmed this is still v0.2; nothing here has been promoted to
a new version number. Class base stats and achievements are unchanged so
far. Audio has one change so far:

- `play_mob_bark(family)` was rebuilt from a flat tone "blip" into a real
  animal-vocalization shape per family (`_BARK_PROFILE`/`_bark_wave` in
  `game/audio.py`) - a low carrier tone with fast/shallow pitch vibrato mixed
  with noise, tuned per family so beast reads as a growl ("grr"), undead as a
  long low moan/hiss, elemental as a crackling hiss, and construct as a slow
  mechanical groan. Also: mob flavor lines now have a hard `MIN_REBARK_INTERVAL`
  (20s, `game/entities.py`'s `Enemy`) between re-triggers, no longer mention
  the mob's name in their speech bubble, and render in yellow instead of the
  player-chat dark text.

Rendered audio exports of every sound effect above (see "Audio file exports"
below) live in `assets/audio_export/` for reference/archival - the game
itself still synthesizes every sound at runtime, these are just saved copies.

This section will keep growing as the rest of the in-progress batch (loot
bags, vault, dungeons, bosses, quests, abilities, potions, leveling rework,
social/chat features) lands - the per-class stat growth rework specifically
(Section L of the batch plan) will replace the "flat +14/+10, one rotating
stat" line above with real class-differentiated growth ranges, at which
point this file's class-stats table will be filled in for real (and a
version bump to v0.3 would happen in README.md, not silently here).

## Audio file exports

Every sound effect is normally synthesized at runtime (no audio files are
loaded by the game - see `game/audio.py`'s module docstring). Per the user's
request to also have the sounds saved as files, `tools/export_audio.py`
renders every effect above to a real audio file under `assets/audio_export/`
(one file per effect, plus one per family variant for the family-tinted
mob sounds). **These are saved as `.wav`, not `.mp3`**: producing an actual
MP3 needs a real encoder (`ffmpeg`/`lameenc`/etc.), and neither is installed
in this environment - adding one would also be the project's first real
external dependency (it's deliberately pygame-only today, see audio.py's
docstring). WAV needs no extra dependency (Python's built-in `wave` module)
and is lossless, so it's the honest substitute rather than silently
mislabeling a `.wav` as `.mp3`. Re-run `tools/export_audio.py` any time the
sound synthesis changes to refresh the exported files.
