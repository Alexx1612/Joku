# Batch 10: Physical Bump-Push, Vault-as-Permanent-Bags, Inventory Click Remap, Interactive Trading, Nexus Symmetry, Text-Overlap Fixes, and a Real Regression Suite

## Context

After Batch 9 ("The Reforging") shipped, the user asked for a large, wide-ranging
polish pass in one message, then reported two REAL bugs from actually playing it
(a crash clicking the new pet panel, and the new island-hub portals overlapping
each other with no real "starting area"), then asked for a permanent, reusable
automated test suite ("classic recurrent tests to run anytime something new is
added"). This doc covers all of it, in the order it was actually done - it is
also the first batch in this whole project to end with its own committed,
runnable regression suite rather than only throwaway verification scripts.

## 0. Two real bugs, found only by the user actually playing

**Pet panel crash.** Clicking the pet-feeding panel (added in Batch 8) crashed
the game outright. Root cause: the panel had been wired into the same generic
"what did the player click on" dispatcher every other inventory slot uses, but
that dispatcher's fallback branch assumed every unrecognized slot type maps to
a real, named player attribute it could look up - the pet panel is a drop
TARGET only (you feed items onto it; nothing can be picked UP from it), so it
was never given a real attribute name, and the generic fallback crashed trying
to look one up anyway. Fixed with a one-line special case in both the
single-player and co-op input handlers: "this slot kind is never draggable
FROM, full stop." The existing automated tests for that feature had verified
the feeding LOGIC directly and the drag-and-drop rect geometry, but never
actually simulated a bare click on the new panel with nothing selected - a
real gap in test coverage, not just in the feature code, and the direct
motivation for section 7 below (the drag/click test file now does this for
every slot kind, not just the ones a human happened to try).

**Overlapping hub portals, and no real starting area.** This one is actually
Batch 9's own fix, not Batch 10's - it landed in code before doc 21 was
written (which is why doc 21 already describes the fixed, deterministic-
ring design directly, with no "here's the bug" framing). It's mentioned
here only because the user's bug report arrived in the same conversational
stretch as the rest of this batch's asks. Batch 10's OWN, genuinely
distinct portal-related bug - the physical dots were fine, but their
floating text LABELS could still overlap - is covered in section 7
(Text-Overlap Fixes Everywhere).

## 1. Physical Bump-Push for Neutral Wildlife

### What it is

Walking into a neutral, mobile animal (the wildlife added in Batch 8) now
physically shoves it a short distance away, and it visibly decelerates to a
stop over about half a second, instead of the player simply overlapping it
with no reaction at all.

### Why

Directly requested: "you can push neutral and passive mobs around if you walk
into them and they sort of glide away when you bump into them," as part of a
broader "make unit collision look more realistic" ask.

### How it was implemented

- Reused the EXACT SAME field shape as the existing "flee when shot near"
  mechanic (Batch 8) - a decaying countdown timer plus a remembered vector -
  rather than inventing a new state machine: a new `push_time` countdown and
  a `_push_vec` (world-units/sec velocity at the moment of the bump, itself
  divided by a remembered `_push_total` starting duration so it can decay
  smoothly to zero rather than holding constant speed then stopping dead).
- This new "push" locomotion branch was inserted at the very TOP of the
  enemy's per-frame movement decision (even before the existing flee branch),
  so a physical bump always reads as an immediate reaction, never queued
  behind anything else.
- The trigger reuses the EXISTING player-vs-enemy contact-detection block
  (already run every frame for every enemy, previously only ever used to
  apply contact damage) - for a neutral, mobile creature specifically (a
  speed check excludes the one STATIONARY neutral entity, a damageable totem
  decoration used by an unrelated secret-quest mechanic, from ever being
  "pushed" - it should never move at all), it now arms a push instead of
  dealing its already-harmless zero damage. Reusing the SAME per-contact
  cooldown the damage system already had means a continuous bump doesn't
  fire 60 times a second, it re-arms a fresh shove roughly twice a second
  while contact continues - naturally reading as "being nudged repeatedly,"
  not a runaway launch.
- Verified with a real headless test: force an overlap, confirm the creature
  actually moves measurably farther from the player over simulated real
  time, confirm the push fully decays to exactly zero (not lingering), and
  confirm re-triggering mid-glide does not stack/compound velocity beyond
  the intended fixed shove speed.

### Unity rebuild prompt

> Give any "pushable" creature a `PushTimer` and a `PushVelocity` (plus the
> starting duration, to compute a linear decay fraction each frame) using the
> exact same data shape you'd use for any other decaying status effect
> (a stun, a slow) - don't build a separate physics-impulse system just for
> this. In your creature's movement state machine, check "is being pushed"
> with the HIGHEST priority, before flee/aggro/idle, and while active, move
> by `PushVelocity * (PushTimer / PushTotalDuration) * deltaTime` - this
> gives a natural glide-to-a-stop for free with no separate deceleration
> curve to author. Trigger it from your existing player-vs-creature overlap/
> contact detection (reuse whatever per-pair cooldown already gates contact
> damage, if you have one, so a sustained bump re-arms periodically rather
> than firing every physics tick), gated to creatures that are both
> non-hostile AND actually mobile (exclude stationary/decorative "creatures"
> by checking their move speed, not by hardcoding which ones are exempt).

## 2. Peaceful Mob Dialogue - a Real Content Gap Fixed, Not a New System

### What it is

The user asked to "redo peaceful and neutral mobs so they have dialogue or
make sounds" - investigation found the underlying MECHANISM already existed
(an idle-ambience roll that gives any always-passive creature an occasional
flavor line, added incidentally in an earlier batch) but had two real,
separate content bugs that made it read as broken or absent:

1. **Wrong sound family for most wildlife.** Sound effects in this project
   are grouped into a small number of "families" (beast/undead/elemental/
   construct) by creature kind, each with its own pitch/timbre. Two of the
   six wildlife creatures were correctly registered as "beast" (an organic,
   animal-appropriate family); the other four fell through to NO explicit
   registration at all and silently defaulted to "construct" - meaning a
   songbird, deer, desert lizard, and heron were all making a mechanical
   clanging noise instead of an animal sound, with no error anywhere to
   surface the mismatch.
2. **Wrong flavor-line CONTENT for every peaceful creature.** The idle-
   ambience roll always pulled from the same combat-flavored line set every
   aggressive monster in the game uses ("Rrrgh!", "*bares teeth*", "You
   shouldn't be here.") - thematically backwards coming from a fleeing deer,
   even though the delivery mechanism (a speech bubble + a chat-log entry)
   was completely correct.
3. A related, previously-unnoticed bug: a stationary, non-mobile decoration
   object (a damageable totem, also flagged "neutral" for an unrelated
   secret-quest mechanic) was ALSO rolling for and displaying these lines,
   despite being pure scenery that should never "talk" at all.

### How it was fixed

Both wildlife kinds missing from the sound-family registry were added to the
correct ("beast") bucket. A new, genuinely separate flavor-line set
(short, non-verbal, peaceful cues - "*chirps*", "*rustles in the grass*",
"*sniffs the air*") was added, and the line-picking function now branches on
whether the speaking creature is both neutral AND actually mobile: mobile
peaceful wildlife gets the new peaceful set, everything else keeps the
existing per-family combat set, and the stationary decoration object is now
excluded from the idle-ambience roll entirely (checked by move speed, the
same "is this actually a living creature" signal used for the push mechanic
in section 1). Verified with a real, long simulated run confirming a deer
only ever says lines from the new peaceful set, a combat mob only ever says
lines from its own family's combat set with zero cross-contamination, and
the stationary decoration never speaks at all across the whole simulated
window.

### Unity rebuild prompt

> If your game groups creature sound/voice by a "family" or "type" tag
> keyed off species/kind, add an explicit assertion or startup validation
> that EVERY creature kind resolves to a real registered family - a silent
> fallback-to-default (as this project had) can hide a wrong-sound bug
> indefinitely with no error. Give peaceful/ambient creatures their own
> distinct flavor-line or bark content set, separate from combat-monster
> barks, and branch on "is this creature both non-hostile and actually
> mobile" (not just "is it non-hostile") before picking which set to use -
> a purely decorative, stationary "creature" (a destructible prop, a
> quest-object masquerading as an enemy) should usually be excluded from
> ambient dialogue entirely, gated the same way you'd exclude it from any
> other creature-only behavior.

## 3. Vault Chests: Real Independent "Permanent Bags," Not a Shared Shifting List, Plus Skins

### What it is

Each of the 10 Vault chests is now genuinely independent 8-slot storage -
removing an item from chest 3 can never shift a different item in chest 4
into chest 5, the way it silently could before. Depositing while VIEWING a
specific chest always lands in THAT chest, never a different one further
down a shared list. Each chest also now has its own distinct color "skin"
(one of ten - bronze, silver, gold, ruby, emerald, sapphire, amethyst, onyx,
pearl, copper) instead of all ten looking pixel-identical.

### Why

Directly requested: "make skins for vault chest and make them act as
permanent bags just like in rotmg and have the items there." Investigation
found the Vault's real underlying storage was ONE compact, shared list
across all 10 chests, with "which chest" purely a matter of which INDEX
RANGE you were currently paging into - a chest wasn't independent storage at
all, it was a window into a shared array, so removing an early item shifted
every later item's effective chest membership. This diverges from both the
literal ask and from how the real inspiration game's vault chests behave
(genuinely separate bags).

### How it was implemented

- The vault's save format changed from a COMPACT list (only real items, in
  order) to a FIXED-length array (always exactly 80 slots - 10 chests of 8),
  with an explicit "empty" marker for unused slots. Chest N's storage is now
  simply that fixed array's slots `[N*8, N*8+8)`, unconditionally - removing
  slot 3 never touches slot 4 or any other slot, since nothing is ever
  shifted, only individually cleared.
- A one-time, fully automatic migration path handles every existing save
  file transparently: an old-format (compact) file is detected by its shape
  and padded out into the new fixed array, filling sequentially from slot 0
  - a faithful migration, since that sequential order is exactly how those
  items already behaved under the old system.
- Depositing (a plain click, or dragging a specific item onto the vault)
  now fills the first EMPTY slot of whichever chest the player currently has
  open, tracked as real per-session state (both in the single-player game
  state and, mirrored, in the authoritative co-op server's per-connection
  session) rather than "wherever the shared list happens to end."
- Dragging an item onto a SPECIFIC, already-occupied vault or backpack slot
  now SWAPS the two items in place instead of failing - both directions
  (backpack-into-vault and vault-into-backpack), matching the general "drag
  onto something occupied to trade places with it" convention this batch
  also added to plain backpack items (section 4).
- Skins: each chest's little drawn icon now takes a distinct base color from
  a small fixed palette, keyed by chest index, reusing the EXACT SAME
  drawing routine (just recolored) rather than authoring 10 new icons or
  sprites - a cheap, real way to give each container a visual identity.
- Verified with real save/load round trips: a fresh vault is a full 80-slot
  empty array; depositing into chest 3 and then removing an unrelated item
  from chest 0 leaves chest 3 completely untouched; a legacy compact save
  migrates correctly; depositing while a specific chest is completely full
  correctly rejects the deposit (item stays in the backpack) rather than
  silently overflowing into a different chest - the single most important
  edge case, since silently overflowing was exactly the old, broken behavior.

### Unity rebuild prompt

> Model multi-container persistent storage (a bank, a vault, a stash) as ONE
> fixed-size array with a real "empty" sentinel per slot, sliced into
> per-container ranges by simple index math - never as a compact/shifting
> list where a container's membership depends on how many items happen to
> already exist before it. Track "which container is currently open" as
> real state on whatever object represents a connected player/session (not
> just client-side UI state) so a server-authoritative deposit action knows
> exactly where to put the item without the client having to specify a raw
> slot index for every action. Support swap-on-drop-onto-an-occupied-slot
> uniformly across every storage-to-storage transfer path (backpack<->bank,
> backpack<->ground container), not just one of them. Give each container
> instance its own cheap visual identity (a palette swap of one shared icon)
> rather than treating a row of identical containers as visually
> interchangeable.

## 4. Inventory Click Semantics: Right-Click Drops, Double-Click Uses, Single-Click Is For Picking Up/Trading

### What it is

A backpack item's mouse controls were remapped to match the real inspiration
game's own convention: right-click instantly drops an item (no dragging
needed), double-click equips/consumes/hatches/opens it, and a single click
no longer does anything by itself except start a potential drag - it's
reserved for trade-item-offering (a separate system, see section 5) and for
withdrawing one item from an open ground-loot bag with a single click (which
already worked this way and was left unchanged).

### Why

Directly requested: "right click auto drops items from your inv and double
click consumes them and one click is used for when trading and when you want
to take one from a bag." Investigation found the PREVIOUS behavior was a
single plain click already doing the equip/consume action directly (with no
right-click or double-click handling anywhere for inventory slots at all) -
a full remap, not an additive change.

### How it was implemented

- Double-click detection reuses a simple, explicit pattern: record which
  slot and what real-world timestamp a plain click landed on; if the VERY
  NEXT plain click lands on the SAME slot within a short window (350ms),
  treat it as a double-click and fire the old equip/use action; otherwise
  just remember this click as the new "first half" of a potential future
  double-click. Two clicks on DIFFERENT slots never count as a double-click
  for either one, and two clicks slower than the window never count either
  - both real edge cases the automated test suite now checks explicitly,
  not just the straightforward "click twice fast" case.
- Right-click on a backpack slot (scoped only to zones where there's actual
  ground to drop an item onto) reuses the EXACT SAME drop path an item
  already used when dragged off the inventory bar entirely - no new "drop"
  mechanic was invented, just a second, faster way to trigger the existing
  one. Right-click anywhere else keeps its prior, unrelated meaning ("open
  the nearest ground loot bag"), since the two never overlap spatially (one
  only fires when the cursor is actually over an inventory slot).
- This was implemented identically (same detection logic, same event
  ordering) in both the single-player game loop and the co-op client, with
  the co-op client only ever sending the already-existing network actions
  (equip, drop) at the new trigger moments rather than needing any new
  server-side action types.

### Unity rebuild prompt

> Implement double-click as an explicit, timestamped two-click comparison
> (same slot/target within roughly 300-400ms) rather than relying on your
> UI framework's built-in double-click event if that event doesn't let you
> distinguish "same target twice" from "any two clicks close together" -
> test BOTH the same-target-fast case (should fire) and the different-
> target-fast case (should NOT fire) explicitly, since the latter is an easy
> gap to miss. Route right-click on an inventory slot to whatever "drop this
> item" logic already exists elsewhere (a drag-off-the-bar action) rather
> than writing a second, parallel implementation of dropping an item.

## 5. Interactive Trading: Hover Tooltips and a Staged-for-Trade Highlight

### What it is

While trading with another player, hovering any item already offered (by
either side) shows its full item tooltip, and every offered item's slot gets
a soft yellow background tint so it's visually obvious which specific items
are staged, distinct from the separate green "accepted" state of the whole
offer.

### Why

Directly requested ("with items being hoverable and if you click they show
up that you will trade it with a yellowish background"). Investigation found
the underlying trade SYSTEM (drag/click to offer, both sides must
independently accept, a short anti-scam confirmation countdown that resets
on any change) was already fully implemented and working correctly - the
gap was purely in this one panel's visual feedback: no tooltip on hover
anywhere in it, and no visual distinction for an offered item beyond just
"it's drawn in this box."

### How it was implemented

Both additions reuse existing, already-proven building blocks rather than
inventing new ones: the tooltip is the exact same item-tooltip renderer
every other inventory-like panel in the game already calls, and the yellow
highlight is a single tinted rectangle drawn behind an offered item's icon,
computed from the same per-slot loop that was already iterating every
offered item to draw its icon (no new pass over the data). Verified with a
real headless render, including the specific edge case of an empty trade
(nobody has offered anything yet) not crashing when nothing is there to hover.

### Unity rebuild prompt

> When adding hover/highlight polish to an existing, working interactive
> panel, reuse whatever tooltip/highlight primitives your UI framework
> already provides for every OTHER inventory-like panel rather than writing
> panel-specific versions - the goal is visual consistency across every
> place an item can be inspected, not a bespoke trade-panel-only look.

## 6. Nexus: a Real Hallway with Mirrored Side Portals; Realm Starting-Area: a Deliberately Symmetric Marker Ring

### What it is

The Vault and Bazaar entrances in the social hub map moved off the main
fountain plaza's own center line into a pair of mirrored alcoves recessed
into the walls of a short, genuinely walled corridor - a real architectural
hallway feature, with both portals the exact same distance from its
centerline. Separately, the open-Realm starting-area plaza (added in Batch
9) now places its ring of landmark decorations at deterministic, evenly-
spaced compass angles instead of a random scattered selection, echoing the
hub's own now-more-deliberate symmetry.

### Why

Directly requested: "make nexus more symmetric with a hallway and portals
off to the side," alongside "make a starting zone (similar to nexus)."
Investigation of the hub map found it was ALREADY fairly symmetric overall
(a radially-mirrored fountain, four corner statues, banner pillars on all
four walls) with exactly one real asymmetry-by-convenience: the two
secondary portals sat directly on the main plaza's own center row rather
than being treated as their own distinct feature.

### How it was implemented

A short corridor (walled on both long sides) was carved between the
fountain plaza and an existing secondary landmark (a smaller well) that
already sat further out along the same axis - reusing already-empty space
rather than expanding the map or touching the player's arrival point (left
completely untouched, since it sits on a different side of the plaza and
several other fixed-offset positions elsewhere in the codebase are computed
relative to it - moving it would have meant re-deriving multiple other
constants for comparatively little visual gain, a real risk/reward call).
The two portals are placed as symmetric single-tile openings in that
corridor's opposite walls, at the exact same distance from the plaza's
centerline. Verified with a real generated map: exactly one Vault tile and
one Bazaar tile exist, both sit on the identical row, both are the identical
x-distance from the center portal, and both are genuinely walkable (not
accidentally buried in a wall). The Realm starting-area's marker ring was
changed from a random pick among candidate edge tiles to 8 fixed, evenly-
spaced compass-angle positions, verified to still place a real handful of
markers around a freshly generated plaza.

### Unity rebuild prompt

> When asked to make a hub/social-space layout "more symmetric," first
> generate (or otherwise inspect) the actual current layout and check what's
> ALREADY radially/mirror-symmetric before redesigning from scratch - this
> project's hub was already 80% there, and the real fix was a small, scoped
> change (move 2 portals off a shared centerline into a mirrored side
> feature) rather than a full rebuild. Prefer carving new structural
> features (a corridor, alcoves) into space that's already unused in the
> existing layout over moving the player's own spawn/arrival point, which
> is very likely to be a dependency several OTHER fixed-offset positions
> elsewhere in the codebase were computed relative to.

## 7. Text-Overlap Fixes Everywhere - the REAL Batch 10 Portal Bug

### What it is

Every portal's floating name/difficulty label, and every co-op player's
floating name tag, is now drawn with real awareness of every OTHER label
being drawn the same frame - a label that would visually collide with an
already-placed one gets pushed one line-height higher instead of silently
overlapping it. This is a DIFFERENT bug from the physical portal-position
overlap already fixed at the tail end of Batch 9 (see that batch's own
entry, and doc 21's Portal Hub section, which already describes the fixed,
deterministic-ring design directly) - the physical DOTS were already
correctly spaced apart by that earlier fix; this batch's bug was that each
dot's floating TEXT LABEL, rendered well above and centered on it, had no
awareness of any other label at all.

### Why

The user's exact words, later in the same conversation as the rest of this
batch's asks, specifically called out TEXT, not position: "the realms
starting zone should have the portals with a distance between them cause
there a problem with overlapping text[,] same for quests text in dungeon
and other stuff." Investigation (measuring the actual, already-fixed
island-hub portal ring's real on-screen spacing against the actual rendered
width of the island name labels at that font) confirmed a genuine, separate
bug: adjacent hub portals sit about 119px apart on screen, but several
island name labels ("Driftbell Cloister," "Pearlsong Spire") render 130-
155px wide at the font used - wider than the gap between the dots they're
centered on, so their text visibly overlapped even though the portal
graphics themselves never touched. The same investigation found a second,
independent instance of the identical bug class in the co-op client's own
player name tags (drawn the same "one fixed offset above each object,
zero awareness of any other object" way), and confirmed the dungeon quest
panel was NOT actually affected (it's docked in a fixed position beside the
minimap by deliberate design, with nothing else ever drawn in that same
screen region).

### How it was implemented

Both label types were changed from "draw this one object's label
independently" (called once per object, in a loop, with no memory of what
came before) to a genuine batched pass: collect every visible label for
this frame first, sort them by their on-screen horizontal position (for a
deterministic, non-flickering stagger order frame to frame), then place each
one greedily - compute its normal position, and if that would overlap any
label ALREADY placed this pass, push it up by one more line-height and
check again, repeating until clear. This is a small, generic algorithm
(pure rectangle-overlap collision-avoidance) reused identically for both
label types rather than writing two separate implementations, and it
degrades correctly to "no staggering at all" when objects are already far
apart (confirmed by test), so it's safe to apply everywhere unconditionally
rather than only in the specific spot that was reported broken.

### Unity rebuild prompt

> For any floating world-space label drawn above multiple simultaneous
> objects (name tags, waypoint/portal labels, damage numbers), don't place
> each one independently at a fixed offset with no awareness of its
> neighbors - collect all labels to be drawn this frame, sort them by
> screen position for a stable order, and greedily nudge any label that
> would overlap an already-placed one to the next line up, repeating until
> clear. Apply this uniformly to every category of floating label your game
> has (not just the one a bug report happened to mention), and specifically
> test the case with many objects clustered close together (a ring of
> nearby waypoints, a crowded multiplayer party) rather than only the
> default "objects are naturally far apart" case, since that's exactly the
> condition under which independent-per-object placement breaks down.

## 8. A Real, Permanent, Reusable Regression Suite

### What it is

A `tests/` directory of six standalone, dependency-free Python scripts (no
test framework needed, matching this project's pre-existing single test
script's own convention) plus one runner script that discovers and executes
all of them, reporting a clear pass/fail summary - `check_collision_and_
wildlife.py`, `check_inventory_and_vault.py`, `check_hud_and_overlap.py`,
`check_pet_system.py`, `check_reforging_and_nexus.py`, the pre-existing
`check_loot_difficulty.py`, and `run_all_checks.py`.

### Why

Directly requested: "create some classic recurrent tests to run anytime
something new is added and that you will modify if they need to." Every
feature built across this whole project up to now had been verified with
real, working headless test code at the TIME it was built, but that code
almost always lived in a session-scoped scratchpad directory and was
discarded afterward - meaning none of it could be re-run later to catch a
regression from a subsequent, unrelated change (exactly the kind of gap that
let the pet-panel crash in section 0 slip through unnoticed until the user
hit it live).

### How it was implemented

Every script follows the exact same shape as the project's pre-existing
loot-difficulty check: plain Python functions, real game objects
constructed directly (no framework, no mocking library), real `assert`
statements, and a final "PASSED: ..." print on success - chosen specifically
to match what was already there rather than introducing a second testing
convention (pytest, unittest) alongside it. Each file groups checks by
FEATURE AREA (not by which turn/session added them), and each function
explicitly covers BOTH a normal case and at least one real edge case (a
double-click on two different slots, a deposit into a completely full
vault chest, zero-portal and one-portal degenerate cases for the label-
overlap fix, feeding a pet an egg, teleporting via a portal in both single-
player and the authoritative co-op server) - the instruction to test edge
cases, not just happy paths, was taken literally rather than only porting
over the happy-path checks that had already been written ad hoc while
building each feature. The runner script (`run_all_checks.py`) auto-
discovers any file matching `check_*.py`, so adding a new check script for
a future feature requires no registration step anywhere else - drop the
file in, matching the same pattern, and it's picked up automatically the
next time the suite runs.

### Unity rebuild prompt

> Once you have more than one or two features with any kind of automated
> verification, commit to a single, consistent, low-ceremony test
> convention early (Unity's own Test Runner / NUnit-based framework is the
> natural equivalent here) and put every test under one discoverable
> location, grouped by feature area - never leave verification code as
> disposable scratch work that gets thrown away once a feature ships, since
> that's exactly the kind of regression coverage gap that lets an old
> feature silently break when an unrelated later change touches shared
> code. For every test, write at least one deliberate edge case alongside
> the obvious happy-path case - full/empty containers, zero/one/many-object
> degenerate placements, and the exact "two nearly-simultaneous inputs"
> shape (double-click, double-tap) are the categories most worth checking
> explicitly, since they're the ones a quick manual playtest is least
> likely to stumble into by accident.

## Verification approach used for this whole batch

Every mechanism above was checked with real headless execution against real
constructed game objects (players, enemies, a fully generated open-Realm
simulation, a fully generated Nexus map) - not mocked pieces - both at the
time each fix was written AND again afterward once ported into the new
permanent `tests/` suite, confirming the ported versions still pass
unchanged. The full pre-existing regression check and full-application
smoke-import test were re-run clean after the complete batch, and the two
real bugs the user found live (section 0) are now permanently covered by
the new suite specifically so they can never silently regress again.
