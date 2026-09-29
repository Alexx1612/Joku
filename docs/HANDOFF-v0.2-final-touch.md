# Handoff: "v0.2 final touch" session → next session

Project: **Realm Reforged**, a Python 3.12 + pygame RotMG-like (single-player `main.py`, authoritative co-op
`server.py` + `coop_client.py`, shared simulation in `game/realm_sim.py` / `game/entities.py`).
Repo `C:\Users\alexandru.mirea\PycharmProjects\ROTMG`, GitHub `Alexx1612/Joku`, branch `main`.
Current version: **"Ends of V0.2"** - release https://github.com/Alexx1612/Joku/releases/tag/v0.2
(Windows `.exe` ×3 + `join.bat`, Linux `RealmReforged-linux-x86_64.tar.gz` with `play.sh` / `host.sh` / `join.sh`).
The user explicitly said **don't start v0.3** unless they ask.

## Where to look first
- `README.md` - full, current feature reference, controls, download/run (Windows + Linux), co-op from
  different homes, saves, project structure, tests, release process, known limitations.
- `GAME_DATA.md` - numbers/tables generated from the code (classes, abilities, enemies + attack sets, bosses,
  pets, story, 30 side quests, NPCs, areas, music, SFX).
- `docs/unity-rebuild/00-INDEX.md` → docs 00-30: every feature in creation order, detailed enough to rebuild
  the game in Unity. Docs 25-30 cover everything from this session.

## What this session did (commits `cafd86c` … `92c25df` + release updates)
1. **Options menu & interaction** - persisted `settings.json`; trading with consent, offers stay in backpack
   (no item loss); Inspect; crew invite; drag hardening.
2. **Story campaign** (`game/story.py`) - Prologue → Act I-III → Forge vs Mad God, account-wide act
   checkpoints, per-act HP scaling, J quest log; pacing tuned by bot playthroughs (~66 min median).
3. **Pets** - bond, carriers (Pack), fusion, mythic tier, pets follow in hubs.
4. **Balance** - percentage player defense curve (`constants.player_defense`), priest growth fix, Mad God tuned.
5. **Crash fixes** - drag/portal crash root cause (firing with no weapon) found by fuzzing; co-op Ghost* draw
   crashes; vault-room draw IndexError; far-away mob chat; vault items lost when leaving with a chest open.
6. **World** - terrain rewrite (rotated value-noise fBm + domain warp, Whittaker biomes, rivers/lakes);
   1308×1308 map, ten ~100×100 islands; 10 big named areas; 96×72 Nexus; big multi-tile trees/props with
   canopy fade; decoration rework (groves/clearings); hand-painted art now actually loads in the real game;
   building doors; bosses 2× (mini-bosses 1.8×, guardians 1.5×).
7. **Living world (Batch 15)** - 11 NPCs + talkable creatures, real dialogue menus (`game/dialogue.py`),
   30 side quests (`game/sidequests.py`), Quest Log / Dictionary / Quest Map (`game/journal.py`,
   `game/codex.py`), co-op personal loot + shared credit, island chests.
8. **UI/UX** - framed right dock, wide minimap/clock, draggable quest log + chat (`game/panel_drag.py`),
   chat cursor/selection/copy/history + right-click names + cross-zone `/msg` (`game/chat_input.py`),
   Esc closes windows then asks before quitting, 12-chest vault, zone banners (`game/zone_banner.py`).
9. **Music** - 23 original ~60 s loopable rock tracks per zone/biome/island/dungeon (`game/music.py`,
   background-rendered + cached in `music_cache/`).
10. **Combat feel** (`game/enemy_attacks.py`) - named attack sets; **special attacks only for special mobs**
    (bosses, mini-bosses, world boss, Mad God, story guardians, island anchors, and any mob inside a dungeon);
    everyday open-Realm/island mobs fire 1-2 plain shots with no warning. Telegraphs (red lines, orange ground
    zones) only for dangerous moves. Screen shake only when the local player is hit by something that matters,
    big slams and boss phases. Distinct original SFX per weapon type / ability / attack kind.
11. **Sprites** - fixed stretching/blur (aspect-preserving, crisp scaling), redrew 31 unreadable characters
    (bosses, Mad God, 7 mini-bosses, 12 mobs, 10 NPCs); every pet has its own base sprite.
12. **Saves & releases** - `game/paths.py`: saves live **next to the executable** (they used to reset every
    launch of the exes). `.github/workflows/release.yml` ("build-release"): pushing/force-pushing a `v*` tag
    builds Windows + Linux (Ubuntu 22.04) with the tracked `RealmReforged*.spec` files, launch-tests server,
    game and co-op client on both OSes, and uploads to the release. Linux binaries need glibc 2.35+
    (Ubuntu 22.04+).
13. **Docs** - README and GAME_DATA rewritten; Unity docs 25-30; `.gitignore` reviewed.

## Conventions the user wants (keep following them)
- Run `python tests/run_all_checks.py` after **every batch** of changes (66 check scripts, all passing at
  handoff) plus headless screenshots (`SDL_VIDEODRIVER=dummy` + `pygame.image.save`, then actually look at
  them) for visual work. Checkpoint-commit locally when green.
- **All art and music must be wholly original** - no covers or copied melodies/sprites.
- **Don't commit/push/release without the user's OK** (this session was explicitly approved to push and
  update the release at the end).
- Releases must work on **Windows and Linux/Ubuntu**; co-op is cross-platform (plain TCP port 50777).
- The user likes big batches done by parallel forks, but verify every fork's work yourself afterwards.
- Goofy tone for in-game writing (drink-pun islands, Father Given).

## Known open items (not bugs blocking play)
- In a long-lived process that already holds a big world, building a second full `RealmSim()` is ~3× slower
  (pre-existing; the startup budget test measures a fresh process).
- The first trip into the Realm in co-op sends the ~5 MB map as plain JSON; zlib compression would cut it to
  ~0.1 MB (both server and client need the change).
- `game/music.py` uses stdlib `audioop` (removed in Python 3.13; a slower fallback exists).
- The ~1 h story length is from bot playthroughs, not a human.
