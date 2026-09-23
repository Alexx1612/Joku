# 14 — Adversarial audit pass (Batch 6)

Source: `memory/project_rotmg_batch3_bags_dungeons_bosses.md`, "## Batch 6"
section.

## What it is

A dedicated adversarial audit batch — not new-feature work, but a pass
specifically looking for integration/correctness bugs across everything
landed so far (Batches 3-5: particles/decorations/difficulty/walls/
visibility/doors, landmark buildings, the second decoration pass),
mirroring the same "audit the merged result as its own system" approach
already used successfully in the Batch 3 follow-up (doc 11).

## Why

Given how much had landed across several parallel-forked batches touching
overlapping systems (dungeon generation, room placement, tile IDs,
visibility), a dedicated audit was run before moving on, rather than
assuming each batch's own testing was sufficient in combination.

## Findings and fixes

1. **Real dungeon-unbeatable bug (the significant one).** A specific
   room-placement configuration could generate a dungeon where required
   progression was actually impossible to complete — found and fixed.
   **An explicit "lesson for future room-placement work" was recorded**
   alongside this fix in the memory file: room-placement/dungeon-generation
   logic needs to validate that the generated layout is actually
   completable (every required room/objective reachable given the
   placed doors/walls/gates), not just that it's structurally
   well-formed (no overlaps, no out-of-bounds placement) — a layout can
   pass every structural check and still be unbeatable if reachability
   itself was never verified.
2. **A pending co-op design decision** — flagged during the audit as a
   decision needing to be made (not a bug), rather than resolved
   unilaterally within the audit itself. The specific decision content
   wasn't detailed further in the source memory section available to this
   doc; flagged here for whoever owns co-op-dungeon design next to check
   the original memory file section directly (`## Batch 6`) for the exact
   open question if it's still unresolved.
3. **One minor consistency fix** — a small correctness/consistency
   correction found during the same pass, of lower significance than the
   dungeon-unbeatable bug.

## Unity rebuild prompt

> After a burst of parallel-forked feature work touching procedural
> dungeon/level generation, run a dedicated adversarial audit pass before
> moving on to new features — specifically verify that every generated
> layout is actually *completable*, not just structurally valid (no
> overlaps, no out-of-bounds geometry). A structural-only validation pass
> can pass a layout that is provably unbeatable (a required room or
> objective unreachable given the placed doors/gates/walls) — add an
> explicit reachability/completability check (e.g. a graph traversal from
> the entrance confirming every required node is reachable under the
> gating rules) as a standard post-generation validation step, not just an
> audit-time spot-check.
