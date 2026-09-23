# 11 — Particles, decorations, difficulty rework, breakable walls, room visibility, phase-2 doors (Batch 3)

Source: `memory/project_rotmg_batch3_bags_dungeons_bosses.md`, "## Batch 3"
(6 parallel workstreams) and the immediately-following "## Batch 3 follow-up"
section (4 real bugs found by post-batch audit, not by the user). Six forked
sub-agents worked this batch in parallel against disjoint file/system
ownership to avoid collisions.

---

## 1. Hit/death/pickup particle effects

**What it is:** Small particle bursts on enemy hit (a few sparks in the
damage-type's color), enemy death (a bigger multi-directional burst), and
item pickup (a brief upward sparkle).

**Why:** Combat and looting felt flat with zero visual feedback beyond
numbers and sound.

**How:** A new lightweight `Particle` dataclass (position, velocity, color,
lifetime) and a per-frame particle list, spawned at the relevant existing
event sites (damage application, enemy death, item pickup) and drawn as
small fading circles/squares each frame, then pruned once their lifetime
expires. Deliberately capped in count per burst to avoid the same kind of
performance issue later found in ambient weather particles.

**Unity rebuild prompt:**
> Add lightweight, capped particle bursts at combat/pickup feedback moments
> (hit, death, item pickup) using a simple pooled/lifetime-based particle
> system — color-coded by event type (damage type for hits, a distinct
> pickup sparkle), short-lived, and capped per-burst so combat against many
> simultaneous enemies never spikes particle count unboundedly.

---

## 2. Decoration objects scattered across the open world

**What it is:** Non-functional scenery — rocks, bushes, flowers, driftwood,
etc., varied per biome — scattered across the Realm to break up empty
ground tiles.

**Why:** The open world's terrain, even after the biome-consolidation pass
(see doc 10, section H), still read as visually empty between points of
interest.

**How:** A decoration-placement pass during `make_realm()` that scatters a
biome-appropriate decoration set at low density across walkable, non-lair,
non-building tiles, stamped as a rendering-only overlay (no collision, no
gameplay interaction) so it can't block movement or hide a real obstacle.
This is the workstream that the Batch 3 follow-up audit (below) found a
real invisible-decorations bug in.

**Unity rebuild prompt:**
> Scatter purely-cosmetic, non-colliding decoration props across open-world
> terrain at low density, varied per biome, placed only on already-walkable
> tiles that aren't otherwise occupied (no points of interest, no
> buildings, no lairs) — keep the decoration layer strictly visual so it
> can never be confused with, or interfere with, collision geometry.

---

## 3. Difficulty rework

**What it is:** A rebalancing pass across enemy stats/spawn weighting so
difficulty scales more deliberately from early biomes through to dungeon
bosses, rather than the ad hoc numbers from initial content creation.

**How:** Adjustments to `ENEMY_WEIGHTS`/per-kind stat multipliers in
`game/realm_sim.py` and `game/entities.py`'s `ENEMY_KINDS`/`BOSS_KINDS`
tables, tuned by biome tier rather than left at their original
first-draft values.

**Unity rebuild prompt:**
> Treat enemy stat/spawn-weight tables as data to be tuned in a dedicated
> balance pass once content exists, not something to get right on first
> creation — structure enemy definitions (stats, spawn weight, per-biome/
> per-tier applicability) as clearly-separated data so a later balance pass
> can adjust numbers without touching behavior code.

---

## 4. Breakable walls

**What it is:** Certain dungeon walls can be destroyed (by player damage or
a specific interact action) to reveal a shortcut or hidden area, instead of
every wall being permanent.

**How:** A new wall-tile variant flagged as breakable, tracked with its own
HP, rendered with a cracked/damaged texture as it takes hits, replaced with
a floor tile once destroyed. Feeds into the room-visibility and phase-2-door
workstreams below, since a breakable wall changes what's "visible"/
"reachable" mid-dungeon in a way the room-visibility system has to account
for.

**Unity rebuild prompt:**
> Implement breakable walls as a distinct tile variant with its own hit
> points, a damaged-state visual that updates as it's hit, and a clean
> swap to open floor on destruction — and make sure any
> visibility/pathing/room-reveal system treats a broken wall as a live
> topology change, not a static assumption made once at dungeon generation.

---

## 5. Room visibility system (+ the follow-up double-bug)

**What it is:** Dungeon rooms are hidden (fog-of-war-style) until the player
has actually seen into them, rather than the full dungeon layout being
visible/rendered from the start.

**How (original Batch 3 version):** A custom room-visibility calculation
built specifically for this feature.

**Real bug found in the follow-up audit:** the original custom visibility
calculation had two overlapping bugs (a "double-bug" — two separate defects
compounding each other, not one). Rather than debug the custom
implementation further, it was **replaced entirely** with the project's
existing, already-correct `has_line_of_sight()` helper (the same one used
for enemy aggro-gating and, later, enemy ranged-attack gating — see doc 10,
section I item 4) run per-tile against the player's position. Explicit
lesson: a bespoke reimplementation of "can X see Y through walls" is a
likely bug source when a correct, already-tested version of exactly that
primitive exists elsewhere in the codebase — reuse it instead of writing a
second one.

**Unity rebuild prompt:**
> Implement dungeon fog-of-war/room-reveal by reusing a single, well-tested
> line-of-sight primitive (the same one driving enemy aggro/attack
> line-of-sight checks) evaluated from the player's position each frame/tick,
> rather than writing a separate bespoke "room visibility" algorithm — a
> second implementation of the same "can A see B through walls" logic is a
> likely source of subtle, compounding bugs.

---

## 6. Phase-2 door (dungeon progression gate)

**What it is:** A dungeon door that only unlocks once a phase-1 objective
is cleared (e.g. a wave of enemies, a boss's first phase), gating
progression deeper into the dungeon.

**How:** A door tile variant with a locked/unlocked state driven by a
dungeon-specific phase-completion flag, checked each tick, swapped to an
open/walkable state once the gating condition is met.

**Unity rebuild prompt:**
> Implement multi-phase dungeon progression gates as a door tile whose
> locked/unlocked state is driven by an explicit phase-completion flag on
> the dungeon/encounter state, checked continuously — not a one-time
> trigger — so the door reliably opens the moment its condition becomes
> true regardless of exactly when the player reaches it.

---

## Batch 3 follow-up: post-batch adversarial audit (4 real bugs)

A dedicated audit pass after the 6 parallel workstreams landed, looking
specifically for integration bugs between them. Found 4 real issues:

1. **Impossible quest targets.** Some quest/objective generation could
   target a decoration or entity that the difficulty rework or decoration
   placement had since made unreachable/nonexistent in certain
   configurations. Fixed by validating objective targets against what
   actually exists/is reachable at generation time, rather than assuming
   any previously-valid target set remains valid after later systems change
   what gets placed.
2. **Room-visibility double-bug** — see section 5 above; fixed by replacing
   the custom implementation with the existing `has_line_of_sight()`.
3. **Invisible decorations (rendering-model bug).** The decoration
   placement pass (section 2) stamped decorations correctly into the map
   data, but a subset never rendered — traced to a mismatch between the
   decoration system's assumed rendering/layering model and how the
   renderer actually composites tile layers, i.e. decorations were placed
   on a layer the renderer wasn't drawing in the code path that mattered.
   Fixed by aligning decoration rendering with the renderer's actual
   layer-compositing order.
4. **VFX/projectile "punch" pass.** A general polish pass on projectile and
   hit-effect visuals for impact/weight, done as part of the same audit
   once the three correctness bugs above were fixed.

**Explicit process lesson recorded from this follow-up:** after landing
several parallel workstreams that touch overlapping systems (visibility,
placement, rendering, quest generation), run a dedicated integration audit
looking specifically for places where one workstream's assumption was
invalidated by another's change — these bugs were not caught by any
individual workstream's own testing, only by an audit that treated the
combined result as a new system to verify from scratch.

**Unity rebuild prompt:**
> After merging several parallel feature branches/workstreams that touch
> overlapping systems (visibility, procedural placement, rendering,
> objective/quest generation), run a dedicated integration-focused audit
> pass that specifically looks for one workstream's assumption being
> invalidated by another's change (e.g. a decoration placed on a layer the
> renderer doesn't composite, or a quest target that a difficulty/placement
> change made unreachable) — treat the merged result as a new system
> needing its own verification, not just the union of already-tested parts.
