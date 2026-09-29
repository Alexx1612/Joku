# Ends of V0.2 follow-ups: music, zone banners, save location, release pipeline

## Context

Covers the work that landed after doc 28 was written, all part of the "Ends
of V0.2" release (commits 65552b4, 30fb143, d09df8d): the one-minute music
system, zone-entry banners, where saves live in a packaged build, the
Windows + Linux release pipeline, and one draw-crash fix. Numbers are read
from the current code.

## 1. Music (game/music.py, game/audio.py)

- **23 tracks** in `TRACKS`: Nexus, Bazaar, Vault, the 10 realm biomes, the 2
  island themes (shard / choir) and 8 dungeon themes (generic, cave, frozen
  crypt, jungle ruins, ember den, sunken grotto, wind spire, forge). Each
  spec is data only: title, key, scale (`SCALES`), tempo, groove style,
  per-section chord progressions and a melody seed. Melodies are a seeded
  random walk over the scale with chord-tone targeting, so no track
  reproduces an existing song (a firm project rule).
- **Length and loop**: `TARGET_SECONDS = 60`, rounded to a whole number of
  bars (tests accept 55-65 s). Songs are rendered circularly: the last
  `TAIL_SECONDS = 2.5` of ringing notes fold back onto the first samples, so
  the loop point is continuous and bar-aligned.
- **Rendering**: `RATE = 22050` Hz mono 16-bit. Each note is a repeated
  single-cycle wavetable with a segment-wise envelope (stdlib `audioop.mul` /
  `audioop.add`), so a track renders in ~0.03 s. `audioop` is gone in Python
  3.13+; a slower pure-Python fallback exists.
- **Cache + background thread**: rendered `.wav` files go to `music_cache/`
  (next to `settings.json`, or `RR_MUSIC_CACHE`), keyed by a hash of
  `music.py` + the spec + the rate, so editing one song invalidates only its
  entry. A worker thread renders on demand; `request(zone)` returns
  immediately (None until ready), so the game loop never waits.
- **Switching**: realm music follows the biome, big area or island under the
  player through `music.Hysteresis(dwell=2.0)`; `audio.update_music()`
  crossfades with `MUSIC_FADE_MS = 1500`. Portal/zone changes switch
  directly. `RR_NO_MUSIC=1` (set by the test runner) disables worker and
  playback.
- **Unity**: author the tracks as looping AudioClips (or keep the procedural
  generator in a native plugin) and drive them from a two-source crossfading
  music player with the same 2 s dwell.

## 2. Zone-entry banners (game/zone_banner.py, ui.draw_zone_banners)

- `ZoneTracker.observe(dt, zone_kind, key, title, subtitle, music_zone)` is
  called every frame by both clients with the player's current place:
  hub (`hub_place`), dungeon with difficulty (`dungeon_place`), or realm
  biome / big area / island (`realm_place`; `biome_near` looks up to 6 tiles
  around for places without a biome tile, like the arrival plaza).
- A `Card` fades in `FADE_IN = 0.4` s, holds `HOLD = 1.8` s, fades out
  `FADE_OUT = 0.6` s. A place is accepted after `DWELL = 1.2` s
  (`ZONE_DWELL = 0.25` s for portal/zone changes) and is never re-announced
  within `REPEAT_S = 25` s. A new card arriving while one is visible makes
  the old one fade from its current alpha over `CROSSFADE = 0.35` s while
  the new one fades in; at most two are drawn.
- Biome display names: the `ice` biome shows as "Glacier" and `cave` as
  "Crystal Deep". The card sits top-centre, clear of the dock frame, the
  hub hint line and the item feed; the story act banner draws lower.

## 3. Where saves live (game/paths.py)

- A PyInstaller one-file build unpacks itself into a new temporary folder on
  every launch, so any path built from `os.path.dirname(__file__)` pointed
  there - characters, vaults, accounts, friends, crews and `settings.json`
  silently reset on each start of the released builds.
- `paths.data_dir()`: `RR_DATA_DIR` if set; else the executable's folder when
  `sys.frozen`; else the project root. `data_path(*parts)` joins onto it.
  Used by accounts, characters, achievements, items (vaults), friends,
  crews and settings (the music cache follows the settings folder).
- `tests/check_data_paths.py` fakes `sys.frozen` / `sys.executable` in a
  subprocess and asserts every save path is under the executable's folder,
  and under the project folder when run from source.
- **Unity**: use `Application.persistentDataPath` (or a folder next to the
  player build for a "portable" mode) - never a path inside the app bundle.

## 4. Release pipeline and packaging

- `.github/workflows/release.yml` (workflow `build-release`) runs on a pushed
  `v*` tag or by hand (`gh workflow run build-release -f tag=v0.2`), on
  `windows-latest` and `ubuntu-22.04`, Python 3.12:
  `pip install -r requirements.txt pyinstaller==6.22.3`, build the three
  specs, smoke-test that the server listens on a port, then
  `gh release upload --clobber`.
- Windows uploads `RealmReforged.exe`, `RealmReforged-Server.exe`,
  `RealmReforged-CoopClient.exe` and `packaging/windows/join.bat` (asks for
  host and name if double-clicked). Linux uploads
  `RealmReforged-linux-x86_64.tar.gz`: the three binaries plus
  `packaging/linux/play.sh`, `host.sh`, `join.sh <host> <name>`.
- The three `RealmReforged*.spec` files are now tracked (they had been
  caught by a `*.spec` ignore rule, which broke the first CI run);
  `.gitattributes` keeps `*.sh` LF and `*.bat` CRLF; `requirements.txt`
  pins `pygame==2.6.1`.
- Co-op is plain TCP JSON on port 50777, so Windows and Linux builds play
  together; all players need the same release.

## 5. Small-map draw crash (game/world.py TileMap.draw)

- The big-prop overhang scan (which catches canopies anchored just
  off-screen) built its left column strip as
  `range(max(0, x0 - 3), x0)` without clamping to the map width. When the
  camera sat far to the right of a map narrower than the view - e.g. the
  20x16 Vault room drawn while the camera still held big-Nexus
  coordinates - `x0` exceeded the width and `row[tx]` raised IndexError.
- Both strips are now clamped to `[0, w)`. `tests/check_small_map_draw.py`
  draws the Vault room, Bazaar and Nexus with the camera at every edge and
  corner, a whole screen past each edge, at 8 rotation angles, with and
  without the canopy overlay; it fails on the old code.

## 6. Test note

`check_areas_trees_bosses.check_generation_budget` now times `RealmSim()` in
a fresh subprocess: inside a long-lived process that already holds one big
realm, a second build runs ~3x slower on some machines (also present at
65552b4). Startup generation - what a player waits for - is ~2 s against the
3 s budget.
