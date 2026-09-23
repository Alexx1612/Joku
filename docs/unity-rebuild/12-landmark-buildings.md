# 12 — Biome landmark buildings + semi-3D wall/totem rendering (Batch 4)

Source: `memory/project_rotmg_batch3_bags_dungeons_bosses.md`, "## Batch 4"
section. **Note on duplication:** the same feature is also described later
in the same memory file under "## Batch 3, part 3" — a near-duplicate
write-up of identical work (same files/functions, same two bugs), evidently
logged twice by two different sessions at different times. Per direct
confirmation from the peer session maintaining `docs/unity-rebuild/00-INDEX.md`
(cross-session message received while this doc was being written), this
write-up treats "Batch 4" as the primary/authoritative source, since it
reads as the more complete of the two entries; "Batch 3, part 3" is folded
in only where it adds detail Batch 4's entry didn't (the original tile-id
ranges, noted below, which Batch 5 later renumbered).

---

## What it is

10 distinct landmark building types, one recognizable structure per biome,
stamped into the open Realm as points of interest — plus a semi-3D
rendering trick (raised walls + standing totem props) that gives these
buildings visual height/depth despite the game's otherwise flat top-down
tile rendering.

## Why

The Realm's biomes (even after the terrain-consolidation pass, doc 10
section H, and the ambient decoration scatter, doc 11 section 2) still had
no strong per-biome visual landmarks — nothing that reads as "a place," only
terrain and scattered small props. This batch was 5 parallel forks, each
building out a subset of the 10 biome-specific structures against a shared
placement/rendering framework.

## How it was implemented

- **Placement**: a building-stamping pass during realm generation
  (`stamp_lair_building`-style helper functions in `game/realm_sim.py`,
  confirmed present via grep — exact call sites not read in full for this
  doc) chooses valid rectangular footprints per biome, respecting existing
  terrain/lair/decoration placement so buildings don't overlap those.
- **Semi-3D rendering trick**: walls are drawn taller than a normal floor
  tile (extending upward on-screen beyond their footprint) and standing
  "totem" props are placed as tall sprites at building corners/entrances,
  which together fake a sense of height/verticality in the otherwise
  strictly top-down flat renderer — the same technique later reused and
  extended in Batch 7's multi-instance rendering work (see doc 15).
- **Tile IDs**: the *original* implementation (per the "Batch 3, part 3"
  entry) used `TALL_PROP_TILE` in the 900-929 range and
  `BUILDING_WALL_TILE` in the 1000-1009 range for the new wall/prop tile
  types. **These exact ranges were later renumbered in Batch 5** (doc 13)
  when 10 more decoration kinds were added and produced a tile-ID
  collision with this range. Per Batch 5's entry in the source memory
  file, the final, current ranges are: `TALL_PROP_TILE` 1000-1101 (plus a
  Nexus-specific sub-range 1207-1209) and `BUILDING_WALL_TILE` 1150-1159;
  treat the original 900-929/1000-1009 ranges as historical only. See doc
  13 for the full current tile-ID map, including the biome/dungeon
  decoration-prop ranges those numbers sit alongside.

## Bugs found and fixed within this batch

1. **Min/max-tiles inversion.** The footprint-size validation for a
   candidate building placement had its minimum and maximum tile-count
   bounds swapped, so the check that was supposed to reject
   too-small/too-large footprints did the opposite of what was intended.
   Fixed by correcting the comparison operators/bound order.
2. **Building-overlap-overwrite.** Two buildings placed in the same
   generation pass could have their footprints overlap and silently
   overwrite each other's tiles (last-write-wins), rather than the
   placement logic detecting and rejecting the collision up front. Fixed by
   checking candidate footprints against all already-placed buildings'
   footprints before committing a stamp, not just against terrain/lairs/
   decorations.

## Unity rebuild prompt

> Add per-biome "landmark building" points of interest: 10 distinct
> structure types (one per biome), stamped into the open world's terrain
> generation as recognizable rectangular footprints that respect existing
> terrain features, resource/spawn placements, and each other (validate a
> candidate footprint against ALL previously-placed footprints in the same
> pass — a same-pass overlap must be rejected, not silently overwritten).
> To fake verticality in an otherwise flat top-down renderer, draw building
> walls taller than a normal floor tile (extending upward past their
> footprint on screen) and place tall standing "totem"/landmark props at
> corners or entrances — this reads as height without needing a true 3D
> renderer. When validating footprint size against min/max tile-count
> bounds, double-check the comparison direction with an explicit test case
> at each boundary (too-small and too-large), since an inverted min/max
> check is a real, easy-to-miss bug class here (both bounds compile fine
> and only manifest as either over- or under-sized buildings passing
> validation).
