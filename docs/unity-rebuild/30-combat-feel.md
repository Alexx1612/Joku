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
- **Trash vs special mobs** (revision after player feedback): rank `trash` (the common fodder) only gets plain
  basics - `fan` (1-3 bullets), `sine`, `boomerang`, some predictive - no rings, AoEs, dashes or telegraphs, and a
  quieter `shot_small` sound. Ranks `elite` and `boss` (elites, landmark guardians, island anchors, mini-bosses,
  dungeon/world bosses, Mad God) keep the named sets, **hardened** by `moves_for()` via `HARDEN`:
  elite speed x1.18 / cooldown x0.75, boss x1.2 / x0.72 (moves already under `FAST_CD` 1.5 s only x0.9), +1 bullet
  on fans of 3+, a plain single shot becomes a tight double (9 deg), rings x1.2 / x1.3 bullets with >= 2 gaps kept,
  walls +2 bullets (the gap stays), dangerous wind-ups x0.9 (min 0.35 s). Bosses also get `Crossfire` (enraged
  only): an aimed predictive 3-fan x3 burst while 3 ground zones land around the target (`tele_fn="rain"`).
  Enrage cooldown multiplier `PHASE2_CD_MULT` = 0.6. Every elite has >= 2 moves, every boss >= 3.
- Full per-kind move lists: GAME_DATA.md "Attack sets".

## 2. Bullets (`game/entities.py` `Bullet`)
New motions: `sine` (sideways sway), `accel` (speed ramps up, slows to a stop, or stops then re-aims - mines),
`homing` (capped turn rate toward the nearest player), `split` (spawns N shards at end of life). Enemy bullets carry
their source rank so a boss hit can be told apart from trash.

## 3. Telegraphs (`realm_sim` enemy zone queue + `vfx.draw_enemy_zones`)
Ground zones are world-space shapes (circle, line/lane, cone, ring) with a fill and edge alpha
(`ZONE_FILL_ALPHA` 55, `ZONE_EDGE_ALPHA` 200) drawn under entities; damage lands only when the wind-up ends.
Colour code: red (`RED`) aimed lines and dash lanes, orange (`ORANGE`) ground AoE, purple (`PURPLE`) homing.
**Only dangerous moves are telegraphed** (`TELEGRAPHED` = zone / ring / cone / line / dash; `is_dangerous(move)`):
ground AoEs, slams/novas, beams/lance lines, dashes/leaps and boss specials. `M()` defaults `tele` to `"none"`
(no sprite glow, no co-op tell, wind-up capped at 0.12 s) for ordinary aimed shots / fans / volleys / sine / homers.

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

## 6. Balance check (damage/s to a lvl-20 player, standing still / strafing, 2 seeds x 20 s)
Before = the first combat-feel commit (aabeaa3), after = the trash/special revision.

| Kind | Wizard before | Wizard after | Warrior before | Warrior after |
|---|---|---|---|---|
| imp (trash) | 4.2 / 1.7 | 2.0 / 0.7 | 2.6 / 0.9 | 1.6 / 0.4 |
| goblin (trash) | 2.5 / 0.7 | 2.2 / 0.6 | 2.0 / 0.8 | 1.6 / 0.5 |
| fury_shard (trash) | 5.8 / 1.7 | 6.3 / 1.1 | 3.7 / 0.9 | 4.1 / 0.7 |
| scorpion (elite) | 12.2 / 1.8 | 17.6 / 3.4 | 5.8 / 1.3 | 12.8 / 2.0 |
| salamander (elite) | 16.2 / 0.9 | 21.6 / 2.7 | 11.0 / 0.6 | 16.0 / 1.8 |
| yeti (elite) | 7.0 / 0.7 | 15.7 / 2.2 | 4.5 / 0.8 | 9.3 / 1.7 |
| cinder_colossus (mini) | 26.2 / 3.4 | 62.5 / 6.7 | 17.6 / 1.1 | 38.0 / 5.6 |
| choir_sovereign (mini) | 26.5 / 5.4 | 48.0 / 8.6 | 17.6 / 3.6 | 30.0 / 4.4 |
| boss (Vault Guardian) | 33.3 / 6.0 | 56.1 / 11.6 | 21.4 / 3.6 | 36.5 / 7.7 |
| frost_monarch | 23.3 / 5.4 | 47.2 / 8.5 | 14.3 / 3.9 | 30.6 / 5.7 |
| ash_behemoth | 16.5 / 0.5 | 27.2 / 3.2 | 11.6 / 0.5 | 18.7 / 2.2 |
| mad_god | 19.9 / 7.7 | 45.7 / 10.8 | 22.9 / 6.9 | 39.0 / 10.7 |

Trash got easier (plain shots, no specials); special mobs roughly 1.5-2.5x deadlier standing still and 1.5-2x
while strafing (enrage moves like Crossfire are not in these numbers - the harness keeps HP full). A lvl-20 Wizard
(~300 HP) standing still in front of a boss dies in ~5-6 s.

## 7. Tests
`tests/check_combat_feel.py`: trash only has plain untelegraphed basics (and never glows/flags a tell in play);
every elite has >= 2 and every boss >= 3 moves; dangerous primitives are always telegraphed, plain fans never glow;
hardened sets are faster than the raw table and bosses have Crossfire; every hostile kind has an attack set; no regular mob relies on an untelegraphed full
ring; every boss/mini-boss has >= 3 named moves and a phase change; AoE damage only after its telegraph; bullet
motions; shake policy; distinct cached rate-limited SFX; dash wind-up then lunge.
