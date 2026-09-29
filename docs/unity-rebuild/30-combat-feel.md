# 30 - Combat feel: enemy attack sets, telegraphs, screen-shake policy, SFX

Polish round on top of "Ends of V0.2" (still v0.2). Replaces the old one-pattern-per-kind enemy firing
(`pattern` = aimed / spread / burst ring / spiral / volley / charge / boss ring) where 16 kinds fired radial rings.

## 1. Attack sets (`game/enemy_attacks.py`)
- `ATTACKS[kind]` = list of moves built with `M(name, fn, windup, cd, tele, sfx, **params)`. A move picks a primitive
  from `PRIMITIVES`: fan, ring (with gaps), half_ring, wall (with a gap), beam, sine, homing, accel, mines, split,
  boomerang, spray, lob, slam, rain, eruption, leap, dash, summon, shell, root_pulse.
- Moves carry `phase` (2 = only after the enrage) and `p2` (only in the `_phase2` dungeon room). `moves_for(kind)`
  resolves the set; the old `pattern` field is only a fallback.
- Enemy state: wind-up timer + `windup_kind` (sent in `net_state` so co-op clients draw the same tell), per-move
  cooldowns, a global gap between moves (`GLOBAL_GAP` 0.35-0.7 s), `ATTACK_RANGE` 620 px.
- Enrage: below `PHASE_BREAK_FRAC` (50%) HP bosses/mini-bosses roar (`PHASE_BREAK_INVULN` 0.8 s, no damage), unlock
  their `phase=2` moves and shorten cooldowns.
- Predictive aim leads the player by their velocity x (distance / bullet speed).
- Full per-kind move lists: GAME_DATA.md "Attack sets".

## 2. Bullets (`game/entities.py` `Bullet`)
New motions: `sine` (sideways sway), `accel` (speed ramps up, slows to a stop, or stops then re-aims - mines),
`homing` (capped turn rate toward the nearest player), `split` (spawns N shards at end of life). Enemy bullets carry
their source rank so a boss hit can be told apart from trash.

## 3. Telegraphs (`realm_sim` enemy zone queue + `vfx.draw_enemy_zones`)
Ground zones are world-space shapes (circle, line/lane, cone, ring) with a fill and edge alpha
(`ZONE_FILL_ALPHA` 55, `ZONE_EDGE_ALPHA` 200) drawn under entities; damage lands only when the wind-up ends.
Colour code: red (`RED`) aimed lines and dash lanes, orange (`ORANGE`) ground AoE, purple (`PURPLE`) homing.

## 4. Screen-shake policy (`game/vfx.py`)
- `vfx.set_listener(pos, pid)` is called every frame by both clients; events carry the player id they concern.
- No shake/hit-stop for: your bullets hitting mobs or bosses, abilities, pet fusion, other players' hits (co-op).
- Local player hit: shake 0.12-0.2 s, magnitude 3-7 scaled by damage vs max HP; hit-stop 40 ms for big hits.
- Boss-sourced hit: 0.25 s at 8 + 70 ms hit-stop.
- Slams / landings / eruptions: 0.2 s at 5, fading to 0 by `SLAM_SHAKE_RANGE` (450 px).
- Boss phase change: 0.6 s at 12; boss death / appearance near you: 0.5 s at 10 within `BOSS_SHAKE_RANGE` (800 px);
  world boss spawn: no shake.

## 5. SFX (`game/audio.py`)
Original synthesized sounds, cached, mixed by the options-menu volumes:
`WEAPON_TYPE` (staff, scepter, wand, bow, dagger, katar, sword, mace), `ABILITY_SOUND` (17 ability styles),
`ENEMY_ATTACK_SOUND` (shot, shotgun, spray, burst, beam, wall, wave, homing, bubble, fire, throw, lob, slam, leap,
dash, dash_windup, windup, summon, shell, root, boss_phase). Rate limit: same sound >= `SFX_MIN_INTERVAL` 0.045 s apart,
<= `SFX_WINDOW_BUDGET` 10 sounds per `SFX_WINDOW` 0.12 s.

## 6. Balance check (damage/s to a still vs strafing lvl-20 Wizard, 2 seeds x 20 s)
| Kind | Before still / strafe | After still / strafe |
|---|---|---|
| goblin | 4.0 / 0.9 | 2.5 / 0.7 |
| scorpion | 2.8 / 1.4 | 12.2 / 1.8 |
| salamander | 6.1 / 1.2 | 16.2 / 0.9 |
| yeti | 6.3 / 1.3 | 7.0 / 0.7 |
| cinder_colossus | 9.1 / 2.6 | 26.2 / 3.4 |
| boss (Vault Guardian) | 16.8 / 9.9 | 33.3 / 6.0 |
| frost_monarch | 16.7 / 12.1 | 23.3 / 5.4 |
| thorn_warden | 7.8 / 6.7 | 12.6 / 1.9 |
| sand_wyrm | 0.9 / 0.0 | 8.7 / 5.6 |
Standing still in a telegraphed attack is punished much harder; a moving player takes about the same or less.

## 7. Tests
`tests/check_combat_feel.py`: every hostile kind has an attack set; no regular mob relies on an untelegraphed full
ring; every boss/mini-boss has >= 3 named moves and a phase change; AoE damage only after its telegraph; bullet
motions; shake policy; distinct cached rate-limited SFX; dash wind-up then lunge.
