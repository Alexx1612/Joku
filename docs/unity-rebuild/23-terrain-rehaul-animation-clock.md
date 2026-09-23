# Batch 11: Multi-Octave Terrain, Relocated Islands, Precise Collision, Player Animation, Day/Night Clock

## Context

One large follow-up message with 9 asks: organic (not "diamond-shaped")
biome regions, a visual "levels/stairs" 3D look for terrain, islands moved
to open water at the map's edges with colored wooden walkways, more
biome-matched decorations, weather keyed to biome rather than exact tile,
player walk/idle/fire animation, a day/night GUI clock with Blood Moon tied
in, aggressive mobs also nudging the player on contact, and island
guardians pre-spawned the instant a fresh Realm is generated. A mid-turn
follow-up added a 10th ask: pixel-precise collision between the player and
walls/objects/mobs.

**Process note worth its own callout**: the user explicitly asked for this
batch to be split across multiple parallel agents ("do all the work with
multiple forks... test each then the whole thing"). The 3 largest plan
sections plus the mid-batch collision ask were implemented as 4 agents
running CONCURRENTLY, each in its own isolated git working copy (so 4
agents could safely edit the same core world-generation file at once
without overwriting each other), each writing and running its own
automated tests before reporting back, with a human-equivalent "integrator"
role verifying every diff before merging any of it and re-running the
complete test suite against the fully combined result - not just trusting
each agent's own self-reported "done." One agent's first launch attempt
silently produced no real work at all (a placeholder non-response, no
actual file changes) - caught only by checking for concrete evidence
(whether its isolated working copy actually existed) rather than trusting
the response text, and it was simply relaunched.

## 1. Organic Biome Shapes (Multi-Octave Noise)

### What it is / why

The world's 10 biome regions were classified by "whichever biome's own
mathematical field is locally strongest at this point," but that field was
only a sum of 3 fixed-frequency wave terms - few enough that region
boundaries still read as fairly regular/lobed ("diamond shapes"), a
residue of an even blockier scheme this same field had already replaced
once before. Real, independent web research confirmed the standard fix:
multi-octave ("fractal") noise, where each additional layer doubles in
frequency and halves in strength relative to the last, building a coarse
overall shape with progressively finer detail on top.

### How

The field's term count went from a flat 3 to a real 5-octave sum (each
octave's own random direction/phase, frequency doubling and amplitude
halving from a shared base each step - the same underlying technique
research called "fBm," adapted to this game's specific "sum of directional
waves" field rather than a single sampled noise function). The threshold
for blending two nearly-tied biomes at a boundary was also widened
slightly, favoring a softer edge over the previous "biomes feel too
blended" tuning it had been narrowed from. Verified with a real geometric
measurement (perimeter-to-area ratio per region, sampled across multiple
generated worlds) rather than eyeballing "looks less blocky" - confirmed
every measured region scored well above what a regular/blocky shape would
produce.

### Unity rebuild prompt

> If your procedural region classification uses a small number of
> hand-rolled periodic functions rather than a dedicated noise library,
> extend it to a real multi-octave sum (5 layers, each doubling frequency
> and halving amplitude from a shared base, each with its own random
> phase/direction) rather than adding more terms of equal strength -
> equal-strength terms rarely cancel into a genuinely organic shape, while
> a proper octave falloff naturally produces coarse-shape-plus-fine-detail.
> If you're building this fresh rather than porting existing math, use
> Unity's own multi-octave/fractal Perlin utilities directly instead of
> hand-rolling wave sums. Verify the result with an actual geometric
> irregularity measurement (perimeter/area), not a visual guess.

## 2. Visual Terracing (the "Levels/Stairs" Ask)

### What it is / why

The user wants terrain to look more three-dimensional - "levels to stairs
and walls," not just flat ground with shadows. A genuine multi-level
elevation system (real Z-layers, collision that knows which floor an
entity is standing on) was deliberately ruled out as a much larger,
riskier undertaking than this batch warranted, since every existing
collision/line-of-sight/placement system in the game is flat-2D
throughout - touching all of them for one visual ask would be a poor
trade. Instead, this ships a purely VISUAL terrace: a raised-looking patch
of ground with a shaded "cliff" edge and a couple of "stair" tiles
breaking that edge, while remaining, underneath, a completely normal, flat,
fully walkable tile - reusing the exact shading trick the game already
applied to solid walls (a darker band on any tile's edge facing open
space) and the same "carve a soft-edged circular patch" technique already
used for the game's floating islands.

### How

One new terrace gets stamped per biome, placed at that biome's
second-most-notable location (reusing the exact same "don't overlap an
already-placed landmark" check the game's per-biome landmark buildings
already used) - never overlapping. Its edge and stair tiles are walkable,
never solid; only their appearance differs.

### Unity rebuild prompt

> Before building real multi-level collision, ask whether a purely visual
> "raised look" (a shaded edge + a couple of decorative stair meshes/tiles,
> collision completely unchanged, everything still one flat walkable plane)
> actually satisfies the ask - it very often does for a "make it feel more
> three-dimensional" request, at a fraction of the engineering cost and
> risk of real elevation. If true multi-level movement is later wanted,
> treat it as its own separate, much larger project (Unity's own NavMesh
> layers or a proper Y-axis physics approach), not an incremental add-on to
> a flat 2D collision system.

## 3. Islands Relocated to the Map's Edges + Colored Wooden Walkways

### What it is / why

The game's 10 procedural islands (added in an earlier batch) anchored only
a few tiles past wherever the mainland's coastline happened to be at that
angle - close to shore, not "at the edges of the map in open water" as
requested.

### How

Each island's anchor point now targets a distance close to the map's TRUE
outer water boundary at that angle (reusing the exact same coastline-shape
formula the map's overall continent outline is already built from, rather
than a fixed offset), so islands read as clearly out at sea. Since the
resulting gap between shore and island grew accordingly, a real walkway -
a two-tile-wide line of wooden plank tiles, one distinct color per island
- now bridges that gap, ending at the mainland's actual shore point on one
side and the island's edge on the other. A real bug was caught here by the
implementing agent's own testing before it ever shipped: the walkway's
first version targeted the island's exact center, silently overwriting the
island's own landmark decoration that had just been placed there - caught
by checking what tile the island's center actually contained after
generation, not assumed correct, and fixed by ending the walkway at the
island's edge instead.

### Unity rebuild prompt

> When relocating procedurally-placed points of interest farther from an
> anchor (a coastline, a base position), reuse whatever formula already
> defines that anchor's own true boundary rather than a fixed offset
> distance - a fixed offset degrades as the placement moves, a boundary-
> relative one doesn't. When connecting two procedurally-placed things with
> a path/bridge, target their EDGES, not their exact centers, if either one
> has its own decoration/landmark placed at its center - test this
> explicitly by checking what's actually at the endpoint tile/position
> after generation, since a silent overwrite is easy to miss by eye.

## 4. More, Biome-Matched Decorations + Weather-Per-Biome Bug Fix

Five new scatter-decoration kinds were added, and - more importantly - the
existing decoration roster was changed from "every biome picks uniformly
from the exact same shared list" to a per-biome WEIGHTED pick (forests
favor trees/bushes/flowers, deserts favor rock/boulder/gravel, etc.) so
"matching the biome" is now a real, measurable behavior rather than only a
difference in which hand-painted image happens to render for a given tile
id.

Separately, a real, independently-discovered bug was fixed: ambient
weather (rain/snow/sand/ash particles) was looked up by the EXACT tile id
the player stood on, which only ever matched the 10 base ground tiles -
standing on any decoration tile (a rock, a bush, anything not bare ground)
silently returned no match and turned weather off, flickering on and off
constantly while walking through a decorated area. The fix resolves ANY
tile - ground or decoration - back to its owning biome NAME first, then
looks up weather by biome, so it now stays stable across an entire region
regardless of which exact tile is underfoot.

### Unity rebuild prompt

> Weight decoration/prop selection per biome/zone type (a simple weighted-
> random table keyed by biome name) rather than picking uniformly from one
> shared list, so "matching the biome" is a real, checkable behavior.
> Whenever ambient environmental state (weather, music, ambient sound) is
> derived from "what tile/surface is the player on," resolve through the
> owning REGION/ZONE first rather than the exact surface/prop id - a
> decorative prop placed on top of a region's base ground is a different
> id than that ground, and a raw id-based lookup will silently miss it.

## 5. Player Animation: Walk Cycle, Idle Bob, Fire Recoil

No animation system existed for the player at all - one static image per
class, forever. A lightweight system was added without building a full
sprite-sheet/frame-grid pipeline (the base art is procedurally generated,
not hand-tiled): a slow vertical bob while idle, small alternating "leg"
accents drawn at the sprite's base while walking, and a brief forward
nudge + tint flash on every real shot fired - all driven by the SAME
"use a shared global clock, not a per-instance timer" trick the game's
pre-existing shield-pulse effect already used, specifically because a
per-instance timer only advances for the player actually being simulated
locally - a remote co-op teammate's character is reconstructed from
network snapshots and never runs that local simulation step, so it would
never animate at all under a per-instance-timer design. Under the
shared-clock design, a local player gets the full walk/idle/fire set;
a remote peer gets the idle bob only (an honest, disclosed scope choice,
not a bug) rather than a broken walk cycle.

### Unity rebuild prompt

> For any draw-only animation (a bob, a flash, a nudge) that needs to look
> right on both a locally-simulated character AND ones reconstructed purely
> from network state, drive its TIMING from a shared/global clock rather
> than a per-instance timer that only advances when that specific object is
> locally simulated - Unity's `Time.time` is the direct equivalent. Gate
> WHICH animation plays (walking vs. idle) on real, if imperfect, state
> (even a boolean set only for the locally-controlled character) rather
> than building full networked animation-state replication for a
> lightweight cosmetic feature, unless the game's actual multiplayer design
> already calls for that level of animation fidelity for remote players.

## 6. Day/Night GUI Clock, Blood Moon Lifecycle

A new HUD widget shows a sun icon and a moon icon with a marker sliding
between them as the existing (already-correct) day/night lighting value
rises and falls, recoloring red during a Blood Moon - built entirely from
data the game's lighting system already computed, needing no new network
field. The chance of a Blood Moon occurring also changed from a flat,
independent roll every single night to a "pity counter": the longer it's
been since the last one, the more likely the next one becomes (capped),
giving nights a real structured rhythm instead of pure independent chance.

**A real bug shipped and was caught by the user, not by testing**: the
function's parameter list was simplified partway through implementation
(dropping two parameters it turned out not to need), but one of its two
call sites was never updated to match, and only surfaced as a crash when
the user actually ran the game. The fix was immediate and small, but the
LESSON was applied permanently: the project's automated test for this
feature was rewritten to call through the REAL application entry point
(constructing an actual game session and calling its real draw function)
rather than only testing the drawing function directly in isolation - the
exact kind of integration gap that let a signature mismatch slip through
a function-level test but not a real end-to-end one.

### Unity rebuild prompt

> When simplifying a function's signature partway through implementing a
> feature, immediately grep for every call site before considering the
> change done - a function-level unit test alone will not catch a stale
> caller if the test only ever calls the NEW signature directly. Add at
> least one test per significant UI feature that exercises the REAL
> integration path (construct the actual scene/screen and call its real
> update, not just the drawing function in isolation) specifically to catch
> this class of bug.

## 7. Small, Direct Changes

Aggressive (hostile) mobs now also apply a small knockback on contact,
alongside their existing damage - noticeably weaker/shorter than the
knockback already given to bumped peaceful wildlife, so it reads as a
minor deflection rather than a way to juggle a real enemy around. The
player itself was confirmed to have no push-related state anywhere in its
data model, so there was nothing to disable to guarantee it can never be
pushed - genuinely one-directional by construction, not by a guard check.
Island guardian creatures are now armed and present the instant a fresh
Realm is generated (a one-line change to their starting timer), rather
than only appearing after their first countdown elapsed - every SUBSEQUENT
wave still refreshes on the existing 5-minute cycle unchanged.

## 8. Pixel-Precise Collision (Mid-Batch Addition)

### What it is / why

A late addition: make collision between the player and walls/objects/mobs
more accurate, ideally pixel-perfect. The implementing agent deliberately
did NOT build literal full-sprite-silhouette pixel-mask collision against
walls, and explained why: that specific technique is a well-known top-down
action-game footgun - a character's edge pixels catch on every wall corner
and reads as "getting stuck" rather than smooth movement, which is exactly
why real games in this genre use a smaller, more forgiving collision shape
even when the visible sprite is more detailed.

### How

Movement collision against walls changed from testing a single point (the
entity's exact center) to testing 5 points (the center plus 4 points
spaced around the entity's own real collision radius) - the standard
"swept circle" technique, dramatically more accurate than a bare center
check (which previously let up to a full radius of visible sprite overlap
a wall before anything blocked it) without any of literal pixel-masking's
corner-snagging risk. Verified with a real before/after behavioral test (a
scenario the old center-only check would have wrongly allowed, now
correctly blocked) and a real performance measurement at this game's own
actual enemy-count scale, not just "doesn't crash."

### Unity rebuild prompt

> When asked for "pixel-perfect" collision in a top-down action game,
> implement a genuinely more accurate MULTI-POINT check around the
> entity's real collision shape (its own collider radius/bounds) rather
> than literal per-pixel sprite-mask collision against level geometry -
> the latter is a known source of "stuck on corners" complaints in this
> genre. If a stakeholder specifically wants literal pixel masks after
> understanding this tradeoff, Unity's `Sprite.GetPhysicsShape`/2D
> composite colliders can approximate a sprite's real silhouette, but
> default to the forgiving multi-point/circle approach unless told
> otherwise, and say why in the same conversation rather than silently
> picking one.

## Verification & Integration Process

Every fork wrote and ran its own permanent test file inside its own
isolated working copy before reporting back. The integrating session then,
for every reported change: read the actual diff before trusting any
summary text (one fork's first launch attempt was caught this way -
it returned a placeholder non-answer with zero real files changed, invisible
unless you specifically checked for concrete evidence rather than trusting
the response); applied each verified diff onto the current, ACTUAL working
tree (not a naive merge, since every isolated copy had branched from an
older snapshot that predated several of this same session's smaller
direct changes); explicitly checked for resource-id collisions between two
forks that had each independently claimed a new range of tile ids without
visibility into the other's choice (none were found, but this was checked,
not assumed); copied every new test file into the project's permanent test
suite and re-ran each one against the FULLY INTEGRATED result, not just
each fork's own isolated copy; and re-ran a test one fork had flagged as
occasionally flaky several more times post-integration to confirm it
wasn't a real regression. The complete test suite (12 scripts) passed
clean afterward, alongside the standard full compile sweep and application
smoke test. One real, disclosed cost: world generation time increased
noticeably (roughly 2-4x) from the combined effect of richer noise,
terracing, and larger island/walkway carving all landing together - this
is one-time load time when entering the Realm, not a per-frame cost, and
was flagged plainly rather than hidden or silently left for someone else
to discover.
