# 31 - Telegraph accuracy: a warning never lies

"V0.2 final final" session, on top of doc 30. Player report: *"some mobs show a red area of attack but if you move
it aims towards you, so the warning isn't accurate; some attacks go in a line and warn you to leave a circle, but the
shots go past it."* Both were real.

## 1. Root causes (before)
- **Re-aim at fire time.** The wind-up stored `tele_dir`, but when the wind-up ended the move fired from a *fresh*
  context aimed at the player's current position. Only moves flagged `use_tele` used the stored direction, so bullet
  walls, ring gaps, sweeps and half-rings all tracked you after the warning.
- **Circle warnings on bullet moves.** `tele="ring"` drew a non-damaging orange circle around the mob, but the
  moves behind it fired rings, half-rings, sweeps or streams of bullets that flew far past it (about 420 px against
  circles of 55-190 px).
- **Chained dashes** re-aimed with no lane. **Slam bursts** aimed at whoever was nearest when the slam landed.
  **Crossfire** drew ground circles but also fired predictive volleys that ignored them.
- **Sprays**: the cone vanished while the spray was still going. **Root Burst** drew 160 px but rooted at 170 px.

## 2. The rule now
Everything random or aimed about a move is decided at wind-up start, stored, drawn, and fired exactly as drawn:
- direction (`tele_dir`)
- a ring's rotation, which fixes where its gaps are
- a wall's gap
- a slam or leap burst's facing (`burst_ang` on the zone)

`enemy_attacks._dir_for` returns `c.tele_dir` whenever one exists. `p_ring` takes its base angle from `tele_dir`.
`p_wall` takes its gap from `e._wall_gap`.

## 3. Telegraph shapes
| Shape | Used for | Drawn as |
|---|---|---|
| `line` | beams, lances, snares, bullet walls, dash lanes | red lane, as long as the bullets really fly (`reach(m)`); walls also cut their real gap out of the lane (green-edged stripe) |
| `cone` | sprays | orange cone lasting the whole spray (`windup + (repeat-1)*gap`), radius = spray reach x 1.12 |
| `spokes` (new) | every bullet move that used to warn with a circle (rings, half-rings, fan sweeps, accel shots, sine streams, shell follow-ups), plus slam/leap bursts and the Sand Wyrm's surfacing ring | one short arrow per bullet direction (`spoke_angles(m, d)`, every sweep step included), max 150 px; ring gaps show as missing arrows |
| `circle` | real ground AoEs (lob, rain, eruption, slam impact, root pulse) and summons | orange / green circle; the circle is the hit area |

Other rules:
- A mob stays planted through the repeats of a telegraphed non-dash move, so spokes and cones stay anchored where they were drawn.
- Chained dashes get their own short wind-up and a new lane from where the mob landed.
- Crossfire is a pure 6-circle rain; all of its damage comes from the warned circles.
- Heroic mobs fire faster bullets, so their lanes and cones are drawn longer by `bullet_speed_mult`.
- Co-op: `zone_snapshot` rows get an optional 11th element: the spoke angles, or a wall's `[gap_off, gap_w]`.

## 4. Test
`tests/check_telegraph_accuracy.py` does this for every telegraphed move of every special mob:
1. Force the move.
2. Strafe the player sideways through the whole wind-up.
3. Assert that every bullet flies along a drawn spoke (±3°), or inside the drawn lane/cone.
4. For walls, assert no bullet sits in the drawn gap.
5. For dashes, assert each dash follows its own lane.
6. For slam bursts, assert the bullets follow their spokes.

It was mutation-tested: restoring the old `use_tele`-only rule makes it fail.
