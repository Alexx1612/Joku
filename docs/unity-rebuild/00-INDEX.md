# Unity-rebuild docs - index

This is a living document, maintained by the "v0.2"/index-keeper session as
other sessions' docs land under this folder - re-check it after a break, it
will grow. Each doc is written to double as a prompt for a future Claude
session rebuilding this feature from scratch in Unity/C#, in true
chronological order of when the feature was actually built (not necessarily
the file-number order, since numbering was assigned per-writer before all
writers finished - check each doc's own "covers" line for its real batch
range).

Three sessions are producing these docs in parallel:
- **rotmg-03**: foundational systems (Batch 1: bags/vault/dungeons/bosses/
  quests/abilities/potions/leveling) + the art/VFX pipeline.
- **"v0.1 + start v0.2"**: mid-era systems (Batch 2 social/UI/perf, Batch 3
  particles/decorations/difficulty/walls/visibility/phase-2 door, Batch 4
  landmark buildings, Batch 5 more decorations, Batch 6 app audit, Batch 7
  multi-instance co-op + minimap parity).
- **"v0.2 end"**: the most recent systems (Batch 8 ambient wildlife/mouse HUD/
  pet leveling, Batch 9 "The Reforging" storyline/mobs/islands/portal hub).

Source of truth for everything below: `memory/project_rotmg_batch3_bags_dungeons_bosses.md`
(master tracking, batches 1-9) and `memory/rotmg_art_vfx_plan.md` (art/VFX
pipeline history), both in
`C:\Users\alexandru.mirea\.claude\projects\C--Users-alexandru-mirea-PycharmProjects-ROTMG\memory\`.

## Table of contents

| # | Doc | Covers | Writer | Status |
|---|---|---|---|---|
| 00 | [00-design-philosophy.md](00-design-philosophy.md) | Cross-cutting conventions across ALL batches - not a feature, the *how* behind every feature (shared sim core, art pipeline, UI/registry patterns, testing discipline, workflow) | this session | **done** |
| 00 | 00-INDEX.md (this file) | Table of contents + gap/inconsistency tracking | this session | **living** |
| 01 | [01-core-architecture.md](01-core-architecture.md) | Batch 1 (part 1): the shared-simulation split - `main.py`/`server.py`/`coop_client.py`/`RealmSim`, game loop shape, networking model | rotmg-03 | **done** |
| 02 | [02-classes-combat-stats.md](02-classes-combat-stats.md) | Batch 1 (part 2): 8 classes/stat identity, combat resolution (bullets, status effects, telegraphed abilities), per-class level-up growth | rotmg-03 | **done** |
| 03 | [03-items-loot-vault.md](03-items-loot-vault.md) | Batch 1 (part 3): item data model, tiered/UT loot rolling, Vault persistence, loot-bag ground-pickup (Sections A/B) | rotmg-03 | **done** |
| 04 | [04-dungeons-bosses-quests-abilities-potions.md](04-dungeons-bosses-quests-abilities-potions.md) | Batch 1 (part 4): per-theme dungeon generation, dungeon shards, secret "???" quest + Totems + hidden room, boss second phase + portal `kind` system (incl. the "one portal, not two" user course-correction), potion system | rotmg-03 | **done** |
| 05 | [05-art-vfx-pipeline.md](05-art-vfx-pipeline.md) | Foundational art/VFX pipeline: the grid+palette+`_autline_and_render`+`_upscale` auto-shading technique, the pixel-mcp-era flat-color regression and its fix, the "no silhouette reuse"/eye-face convention, the tile-id allocation-with-gaps pattern, procedural-vs-painted-detail at small canvas sizes | rotmg-03 | **done** |
| 10 | [10-social-ui-perf.md](10-social-ui-perf.md) | Batch 2: mob audio/flavor text, lair respawn trickle, co-op social suite (context menu/whisper/nearby-players/friends), chat log UX, options menu rebuild, HUD visual pass, Vault→10 chests, biome terrain consolidation, perf fixes, misc bugs, balance tweaks | "v0.1 + start v0.2" | **done** |
| 11 | [11-particles-decorations-difficulty-walls.md](11-particles-decorations-difficulty-walls.md) | Batch 3 + its follow-up audit: particles, decorations, difficulty/defense rework, breakable inter-room walls, room-based mob visibility, phase-2 door-open + dual portals, plus 4 real bugs found by actual play | "v0.1 + start v0.2" | **done** |
| 12 | [12-landmark-buildings.md](12-landmark-buildings.md) | Batch 4: 10 biome landmark buildings + semi-3D wall/totem rendering. Explicitly resolves the Batch-4/"Batch 3 part 3" memory duplication (see below) | "v0.1 + start v0.2" | **done** |
| 13 | [13-more-decorations.md](13-more-decorations.md) | Batch 5: 10 more decoration kinds everywhere including the Nexus, 2 tile-ID collision bugs, the building-tile renumbering this batch forced | "v0.1 + start v0.2" | **done** |
| 14 | [14-audit-bugfixes.md](14-audit-bugfixes.md) | Batch 6: adversarial audit pass - the real dungeon-unbeatable/completability bug + a pending co-op design decision flagged (not resolved) + one minor fix | "v0.1 + start v0.2" | **done** |
| 15 | [15-multi-instance-coop-minimap.md](15-multi-instance-coop-minimap.md) | Batch 7: multiple concurrent co-op dungeon instances (resolves Batch 6's pending decision) + corner-minimap 8x zoom parity | "v0.1 + start v0.2" | **done** |
| 20 | [20-wildlife-hud-pets.md](20-wildlife-hud-pets.md) | Batch 8: ambient wildlife, full mouse-driven HUD, multi-ability pet leveling/feeding - incl. the class-select `NameError` and a pet-panel drag/click crash the user found by actual play | "v0.2 end" | **done** |
| 21 | [21-the-reforging.md](21-the-reforging.md) | Batch 9: "The Reforging" storyline (the 10-scenario pitch/pick/combine process), 20 new mobs, 20 new decorations, 10 procedurally-placed islands, 5-minute repeating mini-quest, portal hub + starting plaza - incl. 2 more real bugs found by play (overlapping portals, no real starting area) | "v0.2 end" | **done** |
| 22 | [22-collision-vault-trading-polish.md](22-collision-vault-trading-polish.md) | Batch 10: bump-push physics for neutral wildlife, peaceful-mob dialogue content fix, Vault chests rebuilt as real independent per-chest storage + 10 skins, inventory click-semantics remap (right-click=drop/double-click=use/single-click=pickup-or-trade-stage), interactive-trade hover+highlight polish, Nexus hallway+mirrored portals + starting-plaza marker-ring symmetry, and a new permanent `tests/` regression suite - incl. 2 more real bugs found by play (a pet-panel click crash, and a starting-area/portal-ring issue - see gap note below on the latter) | "v0.2 end" | **done** (one cross-reference typo fixed, one attribution question flagged - see below) |
| 23 | [23-terrain-rehaul-animation-clock.md](23-terrain-rehaul-animation-clock.md) | Batch 11: organic biomes/terracing, relocated islands, precise collision, player animation, day/night clock (terrain superseded by doc 27) | "v0.2 end" | **done** (indexed late) |
| 24 | [24-game-feel-art-progression-overhaul.md](24-game-feel-art-progression-overhaul.md) | Batches 12-13: juice (hit-stop/shake/particles), world boss, UT sockets, crews, live events, dash/roll, 26 mob redesigns, universal enemy animation, fishing overhaul | "v0.2 end" | **done** (indexed late) |
| 25 | [25-batch14-islands-gui-music-economy.md](25-batch14-islands-gui-music-economy.md) | Batch 14 (92c3086): drink-pun islands + mini-bosses + curated props/return portals, biome vignettes, wall outline, minimap clamp, right dock + Tab, Vault/per-dungeon music, Echo passive accrual, Bazaar chests, portal doors | "v0.2 final touch" | **done** |
| 26 | [26-v02-final-options-trading-story-pets.md](26-v02-final-options-trading-story-pets.md) | v0.2 final fixes (cafd86c): settings/options menu, trade consent + no-loss offers, Inspect/crew invite, 5-act story + Forge/Mad God, pet bond/carriers/fusion/mythic | "v0.2 final touch" | **done** |
| 27 | [27-balance-terrain-decorations-hud-round.md](27-balance-terrain-decorations-hud-round.md) | Post-v0.2 round (uncommitted at writing): player defense curve, story pacing, fuzz crash fixes, dock frame, terrain generator rewrite (noise/warp/Whittaker/rivers), decoration rework + art-loading fix, building doors, draggable panels, live-event rotation (in progress) | "v0.2 final touch" | **done** (section 10 in progress) |
| 28 | [28-living-world-batch15.md](28-living-world-batch15.md) | Batch 15 living world (uncommitted at writing): 15 NPCs/creature groups + finite dialogue trees, 30 side quests + board, Quest Log/Dictionary/Quest Map, co-op personal loot + shared credit, island chests, spells x2.5 + per-ability VFX, mob chat radius, Esc/quit flow, chat cursor/selection/cross-zone /msg, 12-chest vault, wider HUD, 1308 map + 100x100 islands, 10 big areas, 96x72 Nexus, multi-tile props/canopies, 2x bosses | "v0.2 final touch" | **done** |

**All batches 1-10 now have a doc, and rotmg-03's full assigned scope (Batch 1
parts 1-4 + the art/VFX pipeline) is complete - no gaps remain in the
originally-assigned scope.** Batch 10 is new work beyond the original 9-batch
scope this whole index was built to track - noted here rather than silently
folded in, since nobody explicitly extended the assignment to batch 10+.
`00-design-philosophy.md` (this session's own doc) already covers some of the
same ground at the cross-cutting-convention level (see its sections 2-3);
doc 05 is the dedicated, more exhaustive version covering the session-by-
session technique evolution (pixel-mcp era → auto-shader-render technique,
the "no silhouette reuse" correction, canvas-size/procedural-vs-painted
conventions, the tile-id allocation pattern) - some overlap between the two
is expected and fine, per gap-note style below (reinforcement, not noise).

## Gaps and inconsistencies noticed so far

1. **RESOLVED: the Batch 4 / "Batch 3, part 3" memory duplication.** Flagged
   to "v0.1 + start v0.2" directly; doc 12 explicitly names and resolves it
   (treats "Batch 4" as primary, folds in the one piece of extra detail
   "Batch 3, part 3" had - the original, now-superseded tile-ID ranges).
   Only one doc exists for this feature, as intended.
2. **Confirmed, not a blocker**: doc 01 cites
   `C:\Users\alexandru.mirea\.claude\plans\vectorized-foraging-eich.md` for
   Batch 1's original plan-mode reasoning (a different plan file than the one
   every Batch 3+ doc cites, `pasted-content-id-d476-resume-work-hidden-melody.md` -
   the project switched to reusing one running plan file partway through its
   history). No inconsistency, just noting both plan files are real and
   doc-specific, so don't assume there's only one plan file for the whole
   project if you go looking.
3. **Minor, cosmetic-only observation, not worth fixing**: docs 11, 12, and
   13 each independently re-derive the same "tile-ID collisions keep
   happening because there's no single enforced registry/allocator" lesson,
   with slightly different framing each time (this is because each covers a
   batch where the SAME class of bug recurred - genuinely repeated in the
   source project history, not an artifact of the docs). Doc 13's version is
   the most actionable (explicitly recommends a real registry/allocator with
   a collision check at registration time) - a reader working through the
   docs in order will hit this lesson three times with increasing specificity,
   which is arguably fine (reinforcement of a real recurring failure mode)
   rather than something to trim.
4. **Verified**: no hard factual contradictions found between any two docs
   describing related/adjacent systems (e.g. doc 11's phase-2-door rework vs.
   doc 02's ability/combat coverage, doc 12's landmark buildings vs. doc 15's
   reuse of the same semi-3D rendering technique) - each doc stays within its
   own batch's scope and cross-references neighboring docs by number rather
   than restating their content, which is exactly the non-duplicating
   structure this index is meant to encourage.
5. **RESOLVED**: doc 12's tile-ID note updated, and doc 13 now has a full
   current tile-ID map table with the exact final ranges (verified directly
   in both files): biome props 500-719, dungeon props 800-960, tall props
   1000-1101 (+ Nexus's own 1207-1209), building walls 1150-1159, Nexus flat
   props 1200-1206.
6. **FOUND AND FIXED (final consistency pass, docs 04/05)**: doc 04's boss
   second-phase section correctly noted `PHASE2_HP_MULT` was bumped
   `1.6 -> 1.75` by a later difficulty-rework pass, but stated
   `PHASE2_DMG_MULT` as a flat `1.3` - checked directly against live
   `game/entities.py`, the real current value is `1.4` (bumped from `1.3` in
   THE SAME rework pass, per the source memory's own account, which mentions
   both bumps in one sentence). Doc 04 has been corrected in place. This is
   the one real numeric slip caught across the whole set - every other
   specific constant doc 04 cites (`SECRET_QUEST_CHANCE=0.3`,
   `boss_timer` time_limit `150.0`, `TOTEM_COUNT=3`, `PERMANENT_POTION_CAP=20`,
   `TEMP_POTION_DURATION=60.0`, `TEMP_POTION_AMOUNT=6`,
   `PHASE2_FIRE_RATE_MULT=0.6`) was verified correct against live code.
   Doc 05 (art/VFX pipeline) was also read in full for this pass - no
   inconsistencies found against either `00-design-philosophy.md` or any
   other doc; it meaningfully deepens (not duplicates) the pipeline
   discussion already in `00-design-philosophy.md` sections 2-3.
7. **FOUND AND FIXED: a broken internal cross-reference in doc 22.** Section
   0 ("Two real bugs, found only by the user actually playing") said the
   overlapping-hub-portals/no-starting-area bug was "covered in full in
   section 3" - section 3 is actually the Vault-chests section; the real
   coverage is section 6 ("Nexus... Realm Starting-Area"). Fixed in place
   (changed "section 3" to "section 6").
8. **FLAGGED, NOT RESOLVED - a possible cross-doc attribution question
   between doc 21 and doc 22, worth the authoring session's own eyes**: doc
   21 (Batch 9) already describes, in detail, fixing "the exact same" island-
   hub-portal overlap by switching from independent random per-portal
   placement to a deterministic evenly-spaced ring inside a carved starting
   plaza - and this description matches `RealmSim._stamp_island_hub`'s
   current code and its own docstring EXACTLY (verified directly against
   `game/realm_sim.py`, which explicitly says "not independent random
   nearby-spot searches per portal (the earlier approach)... did land two
   right on top of each other" - i.e. the code's own comment describes this
   as already-superseded history, not a live bug). Doc 22 (Batch 10) then
   ALSO lists "overlapping hub portals, no real starting area" as a bug the
   user found AFTER Batch 9 shipped, with its own fix section - but that
   section's actual content (verified against `game/world.py:481`, the
   `stamp_realm_start`-adjacent code) describes a DIFFERENT, smaller thing:
   the decorative landmark-prop "marker ring" scattered around the plaza
   going from a random pick to 8 deterministic compass angles - not the
   `island_link` portal ring itself, which (per the code comment above) was
   already deterministic. Two honest possibilities, and I can't fully
   adjudicate between them without the authoring session's own memory of
   which fix landed when (this project has no git commit history to check -
   confirmed via `git log`, the repo has zero commits): (a) doc 22's bug
   report #2 is a slight mis-recollection/duplicate of doc 21's already-
   fixed bug, and Batch 10's real, distinct contribution was only the
   decorative marker-ring symmetry pass, not a second portal-overlap fix; or
   (b) there really were two rounds of overlap bugs (the portals in Batch 9,
   the decorative markers in Batch 10) and doc 22's framing is accurate, just
   easy to misread as describing the same ring as doc 21 because both use
   the words "starting area"/"ring"/"deterministic." Flagging this to "v0.2
   end" (author of both docs) to confirm or correct rather than guessing.

**"v0.1 + start v0.2" reports nothing else outstanding on their end** - all 6
of their assigned docs (10-15) are complete with no further action pending.

## Status: documentation task complete

As of this pass, every batch (1-9) has a doc, rotmg-03's full assigned scope
(Batch 1 parts 1-4 + the art/VFX pipeline, docs 01-05) is done, "v0.1 + start
v0.2"'s full assigned scope (Batch 2-7, docs 10-15) is done, and "v0.2 end"'s
own scope (Batch 8-9, docs 20-21) is done. One real factual inconsistency was
found and fixed during this final pass (item 6 above); everything else
checked out. No further gaps remain in the originally-assigned scope. Future
work on this doc set (adding more detail, covering later batches beyond 9,
etc.) is a fresh ask, not a continuation of an open item.

## Maintenance notes for whoever (human or Claude) continues this table

- Re-list `docs/unity-rebuild/` and re-diff against the "expected" rows above
  each time you resume this task - don't assume the state above is still
  current, it's a snapshot from 2026-09-23.
- When a doc lands, replace its "gap" row with a real link + one-line summary
  (mirror the style of the `10-social-ui-perf.md` row above) and remove the
  file-number placeholder (`-`) with whatever number the writer actually used.
- If two docs turn out to describe the same underlying feature (see gap #1),
  don't silently pick one - note the conflict here and flag it to both
  writing sessions if they're still active (`ListAgents`), so the confusion is
  resolved once, not repeated by a future reader of just one of the two.
