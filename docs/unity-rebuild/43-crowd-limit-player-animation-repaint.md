# 43 - The crowd limit, animated players, repainted monsters, a visual sweep

"V0.2 final final fin" session, after doc 42 (b39bf42 was pushed and v0.2 re-tagged first). Your request:

> "recheck all there is visually and redo some models that are with not too many pixels (maybe also the
> characters and their walking idle shoot animations) and maybe set a limit for mob spawn around a player seeing
> area (so there arent that many for when in multiplayer with other 4 persons (maybe make 100% spawn rate for 1
> player then 125% for 2 and 150% for 3 and so on)"

## The crowd limit (`game/realm_sim.py`)
**Rule:** at most **`CROWD_BASE` = 18** hostile monsters within **`CROWD_VIEW_R` = 900 px** of a player. That's about what you can see at the default 125% zoom, plus a margin.

**Groups:** players standing within that radius of each other share a bigger allowance, `group_mult(k) = 1 + 0.25 (k - 1)`:

| Players together | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Multiplier | 100% | 125% | 150% | 175% | 200% |
| Cap | 18 | 22 | 27 | 32 | 36 |

- Players far apart don't add to each other: two solo players each get 18.
- Bosses and world bosses never count and are never blocked.
- `crowd_ok(pos)` is asked by **every** spawn path:
  - lair refills (`_spawn_enemy_lair`)
  - island escorts
  - night spawns (`night._tick_spawns`): one allowance per group, `NIGHT_MOB_CAP x group_mult`
  - Blood Moon hordes (`night._tick_blood_moon`): **one horde per group**, sized `x group_mult`, and stopped early by `crowd_ok`. Before this, each of the 5 players got their own horde stacked on the same spot.
- **Calibration:** a normal day has a median of 5 monsters in view and 9 at the 90th percentile, so the cap only bites in floods (5-player co-op, Blood Moon, stacked lairs).
- **Speed:** `RealmSim.update` keeps `_crowd_alive` (the living players), so the check is a cheap distance pass.

## Players are animated (`game/sprites.py`, `game/entities.py`, `coop_client.py`)
- **Strips:** each class has strips `player_<cls>_idle.png` (4 frames), `_walk.png` (6) and `_shoot.png` (3) in `assets/sprites/v0.2/players/`. Each frame is as wide as the still.
- **Loading:** `sprites.player_frames(cls, which, flip)` loads them, scaled to 48 px and cached per facing. If a strip is missing, it builds a procedural bob / step / recoil from the still.
- **Picking a frame:** `Player.draw` picks it:
  - **Shooting** (`note_shot(direction)`, held for `SHOOT_ANIM` = 0.24 s): plays the 3 shoot frames once.
  - **Walking:** `WALK_FPS` = 10.
  - **Standing:** `IDLE_FPS` = 4, staggered per player so a crowd doesn't breathe in sync.
  - **Facing:** set by aim while shooting, otherwise by walking direction.
  - The old leg circles are gone.
- **Co-op:** snapshots rebuild every `Player`, so `CoopClient._animate_players` keeps a little state per pid:
  - **Walking:** a position change, held for `ANIM_MOVE_HOLD` = 0.18 s so jitter doesn't flicker.
  - **Facing:** from the x-delta.
  - **Shooting:** your own fire input.
- **Class select:** the picked class walks and the others breathe.

## Repainted art (all original, part-based painter)
Each kind has a still, a move strip and an attack strip, plus glow layers where something glows. The scripts reuse `tools/paint_night_sprites.py`, and every one can be re-run.

| Set | Script | Kinds |
|---|---|---|
| Players | `tools/pixel_player_strips.py` | **kept as the chunky pixel art** (your call, 2026-10-09: players and NPCs stay pixelated, a bit bigger than ROTMG). The idle / walk / shoot strips are built from the 128 px stills by moving whole blocks (legs lift, body breathes, lean + chunky muzzle flash), with no repainting or smoothing. The detailed repaint (`tools/paint_player_sprites.py`) is retired. |
| Wildlife | `tools/paint_wildlife_sprites.py` | 19 kinds: hare, snow fox, deer, elk, goat, rat, tortoise, frog, fire beetle, flamingo, heron, penguin, songbird, owl, moth, mushroom folk, lizard, moonpetal, ghostbloom (idle / move; glows: moonpetal, ghostbloom, owl eyes) |
| Shard islands | `tools/paint_shard_island_sprites.py` | 10 mobs + 5 mini-bosses (Cinder Colossus, Rubble Warlord, Ashreach Revenant, Thornrock Colossus, Ashenreach Devourer) |
| Choir islands | `tools/paint_choir_island_sprites.py` | 10 mobs + 5 mini-bosses (Choir Sovereign, Coral Leviathan, Tideglass Warden, Driftbell Matriarch, Abyssal Choirmaster) |
| Bosses | `tools/paint_boss_sprites.py` | the Demon Lord (both phases), the Mad God (phases 1 and 2) |
| Final forms | `tools/paint_madgod_final_sprites.py` | Unhinged (four bone arms, torn robe, broken halo) and Livid (torn bat wings, burning fists and crown); same still sizes as before |

The contact sheets are in `screenshots/2026-10-08/art_*`. In-game shots at real size are in `screenshots/2026-10-08/art_in_game/`.

## Visual sweep fixes
I re-shot every screen (`tools/snap_ui_windows.py sweep`, 11 shots) and fixed what read badly:
- **Event messages and the quest panel:** messages no longer run over the quest panel in the top-left. Lines level with it start to its right (`ui.draw_item_feed`).
- **Dungeon edges:** the void beyond the map edge is black, not the grey screen fill. This is fixed in single-player and co-op.
- **The Shards tab:** the caption was cut off and now reads "ACTIVE = shot sockets".
- **Class select:** it shows the new animated art.

## Tests
`tests/check_crowd_and_animation.py`:
- the group multipliers
- `crowd_ok` blocking a full view but not a far one, and ignoring bosses
- lair refills staying under the cap
- one Blood Moon horde for a group of 3
- night spawns sharing the group allowance
- every class / strip having the right frame count, size and flip
- `note_shot` facing
- the co-op `_animate_players` walking / facing

Shots: `python tools/snap_ui_windows.py art sweep`.
