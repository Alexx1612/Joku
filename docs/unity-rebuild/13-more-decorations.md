# 13 — 10 more decoration kinds, everywhere including the Nexus (Batch 5)

Source: `memory/project_rotmg_batch3_bags_dungeons_bosses.md`, "## Batch 5"
section.

## What it is

10 additional cosmetic decoration kinds beyond the original ambient set from
Batch 3 (doc 11, section 2), and — unlike that first pass, which was
Realm-only — this batch extended decoration placement to every zone
including the Nexus hub itself, not just the open-world biomes.

## Why

The original decoration pass covered the open Realm; the Nexus (the social
hub every player spends time in between runs) and other non-Realm zones
still read as visually sparser than the biomes now did, once landmark
buildings (doc 12) and the first decoration pass had already raised the bar
for how "finished" a space was expected to look.

## How it was implemented

A second decoration-kind table (10 new entries) feeding the same
non-colliding, rendering-only placement mechanism established in Batch 3,
extended to run during Nexus generation as well as Realm generation —
reusing the existing placement primitive rather than writing a second one,
consistent with this project's established pattern of extending a working
system instead of duplicating it.

## Bugs found and fixed within this batch

Two separate tile-ID collision bugs, both a direct consequence of adding
new tile-type ranges into a growing, shared numeric ID space without a
single source of truth for what's already allocated:

1. A new decoration tile ID collided with an existing tile ID already in
   use elsewhere (two different tile types silently sharing one numeric ID,
   so one would render/behave as the other depending on which definition
   "won").
2. A second, separate collision of the same class, found and fixed
   independently of the first.

**This is also where Batch 4/"Batch 3 part 3"'s original `TALL_PROP_TILE`
(900-929) and `BUILDING_WALL_TILE` (1000-1009) ranges got renumbered** (see
doc 12) — the 10 new decoration kinds added in this batch needed IDs in a
range that overlapped what landmark buildings had claimed, so the building
tile ranges were moved to make room. The final, current tile-ID map (per
Batch 5's entry in the source memory file) is:

| Range | Purpose |
|---|---|
| 500-719 | Biome ambient decoration props (Batch 3 + this batch, open Realm) |
| 800-960 | Dungeon decoration props |
| 1000-1101 | `TALL_PROP_TILE` (landmark-building totems/tall props, doc 12) |
| 1150-1159 | `BUILDING_WALL_TILE` (landmark-building walls, doc 12) |
| 1200-1206 | Nexus flat decoration props |
| 1207-1209 | Nexus-specific tall props |

**Process lesson worth carrying forward** (matches the pattern already
called out in doc 11's follow-up section, and reinforced independently
here): every batch that adds new tile-type IDs in this codebase has hit a
collision, because there is no single enforced registry/allocator for the
shared tile-ID numeric space — each addition currently just picks an
apparently-free range by inspection.

## Unity rebuild prompt

> When extending a decoration/prop system, reuse the exact same
> non-colliding placement primitive already established for the first pass
> (don't write a second placement algorithm), and extend it to run in every
> zone that needs decoration (hub/social areas included, not just the
> primary open-world generation), rather than treating the hub as
> out-of-scope by default. Manage tile/prop-type IDs through a single
> enforced registry or auto-incrementing allocator with a collision check
> at registration time — not by each new feature manually picking an
> apparently-unused numeric range by inspection, which has reliably
> produced ID collisions here every time new tile types were added across
> multiple batches of work.
