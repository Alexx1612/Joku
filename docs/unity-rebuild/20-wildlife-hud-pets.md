# Batch 8: Ambient Wildlife, Mouse-Driven HUD, Multi-Ability Pet Leveling

## Context

By this point the game had a full loop (classes, combat, dungeons, bosses, vault,
co-op, biome landmark buildings, multi-instance dungeons - see docs 01, 10+).
The user's request that started this batch, verbatim:

> "ok now research blogs wikis and all sort of sources online for things to add
> to the game and make it sort of a plan with multiple (10 minimum) things to
> implement for the games (big features) that will suite well here, also i have
> 2 suggestions i want to implement: 1. make the map more versatile and add
> neutral and peacefull mobs (such as birds and animals which you cant shoot and
> they just idle or run away from you if you shoot near them) and i want you to
> redo the whole hud for all things (like menu the menu a real menu which i can
> also select things or hove them with mouse and same things for all menus make
> them more appealing and compact (start menu and ingame menu for slots stats
> and maybe add some per info and levels to it which he can be fed with items
> and level up so he heals you more (make him be able to heal give mana and
> damage/shoot other enemies all at the same time)"

This decomposed into three concrete asks (a 16-item researched feature roadmap
was also produced but deliberately NOT implemented - it's a future-sessions
backlog, see the plan file referenced in the batch-history memory). The
assistant ran a real web-research pass (RotMG wiki/RealmEye/dev blogs/
RogueBasin) plus 3 parallel codebase-exploration agents before writing a plan,
which the user approved via the standard plan-mode -> ExitPlanMode flow before
any code was touched.

---

## 1. Ambient Wildlife (unshootable, flees when threatened)

### What it is

Small peaceful animals scattered across the open-world biomes - birds, deer,
lizards, herons, hares, moths - that can never be targeted or damaged by
gunfire, wander passively like any other idle mob, and actively flee (moving
directly away, blended with normal wander noise) for a few seconds whenever a
player's bullet lands near them. Purely atmospheric: no aggro, no damage, no
loot, no XP.

### Why the user chose it

Directly requested: "add neutral and peacefull mobs (such as birds and animals
which you cant shoot and they just idle or run away from you if you shoot near
them)" - framed as a way to "make the map more versatile" and give the large
open continent a sense of life beyond combat encounters. A `neutral` flag
already existed in the enemy data table (used by 2 earlier ambient kinds), but
it only ever suppressed aggro - it did not make a mob unshootable, and there
was no flee behavior anywhere in the codebase. The assistant confirmed this gap
by reading the full enemy-AI update loop before designing the fix, rather than
assuming the existing `neutral` flag already covered "can't be shot."

### How it was implemented (Python/pygame)

- **Data-driven flag, not a new enemy subtype.** The shared enemy-definition
  table (a plain dict of per-kind stats: rank, hp, speed, bullet pattern,
  damage, aggro/leash radius) gained one new boolean field, `unshootable`
  (default `False`), alongside the existing `neutral` field. No new class, no
  new inheritance branch - every other mechanic (movement, wander, rendering)
  is completely unaware of it except for two checkpoints.
- **Bullets pass through, full stop.** The single, central bullet-vs-enemy
  collision resolver (the routine every player and enemy bullet in the whole
  simulation funnels through) gained one line at its very top: if the target
  enemy has `unshootable = True`, skip it before any hit-test, damage, status
  effect, or loot roll ever runs. This is the ONLY place damage immunity is
  enforced - deliberately centralized so no future bullet type/status effect
  could accidentally bypass it.
- **Flee state as a plain countdown field**, exactly matching how every other
  timed status effect on an enemy already worked (frozen/bleed/burn/vulnerable
  are all "a float that counts down to zero, checked once per frame"). Two new
  fields: a countdown timer and a remembered "flee from" position.
- **A cheap, opt-in proximity check runs once per simulation tick**, but only
  ever iterates the (small, sparse) subset of currently-alive unshootable
  enemies - never the general enemy population - so cost is negligible even on
  a large map. For each live player bullet, if its distance to an unshootable
  enemy is under a small trigger radius, that enemy's flee countdown is armed
  and its "flee from" position is set to the bullet's current position.
- **Movement priority**: the enemy's own per-frame update function gained a
  new TOPMOST branch, checked before its normal aggro/idle decision tree - "if
  fleeing, move directly away from the remembered threat position, blended
  with the existing ambient wander noise (not a perfectly straight line - it
  reads as a startled animal, not a scripted retreat), decrementing the
  countdown; only fall through to normal aggro/idle behavior once it expires."
- **Content**: 6 new/retrofitted wildlife kinds spread across the existing
  weighted per-biome spawn tables at very low weight (so they're rare ambient
  sightings, not a common encounter) - each one is a genuinely new ANIMAL
  SILHOUETTE, but reuses an existing enemy's base pixel-art shape with a fresh
  color palette, matching this project's own established "minor mobs may reuse
  a shape with a new palette; major/signature mobs must be a genuinely new
  silhouette" art convention (see the design-philosophy doc). One pre-existing
  damageable "totem" decoration-enemy was deliberately left OUT of this change
  even though it also never aggros, because a separate secret-quest mechanic
  depends on totems being killable.
- Because this all lives in the single shared simulation class used by BOTH
  single-player and the authoritative co-op server, co-op got the exact same
  behavior for free with zero networking-specific code.

### Unity rebuild prompt

> Add a `bool IsUnshootable` and a `float FleeTimer` / `Vector2 FleeFromPosition`
> field to the enemy/creature data definition (ScriptableObject or equivalent).
> In the single central projectile-vs-enemy collision handler, skip any enemy
> flagged unshootable before running any other hit logic - no damage, no
> status effect, no loot, ever, for that flag. Each simulation tick, for the
> small subset of currently-alive unshootable creatures only, check distance
> to every active player projectile; if within a small trigger radius (~60
> world units at this game's original scale), arm a ~3-second flee timer and
> remember the projectile's position. In the creature's movement/AI state
> machine, add a state with the HIGHEST priority (checked before idle/aggro)
> that steers directly away from the remembered position, blended with normal
> idle wander noise, until the timer expires. Add half a dozen small-animal
> visual variants (recolors of an existing base creature mesh/sprite are fine
> for "minor" wildlife) and scatter them at low spawn weight across your
> biome/zone spawn tables. Make sure this logic lives in your authoritative
> simulation layer (server or single shared sim), not per-client, so
> multiplayer inherits it automatically.

---

## 2. Full Mouse-Driven HUD/Menu Overhaul

### What it is

Every screen in the game became genuinely mouse-interactive (hover
highlighting + click-to-select), not just keyboard-navigable, while every
existing keyboard path kept working unchanged. Concretely: the class-select
screen, the options/help overlay's interactive menu rows, the death/respawn
screen, and a previously-half-wired trade-panel Accept/Cancel button pair.

### Why the user chose it

Directly requested: "i want you to redo the whole hud for all things (like
menu the menu a real menu which i can also select things or hove them with
mouse and same things for all menus make them more appealing and compact
(start menu and ingame menu for slots stats..." - i.e. every menu, not just
one screen, should support real mouse interaction, matching how modern game
menus behave rather than a keyboard-only fallback.

Before writing a plan, the assistant did a real audit of every existing screen
and found the actual state was uneven: most in-game panels (inventory,
backpack, vault, friends list, context menus) already had full mouse
support built on a consistent, reusable pattern - but class-select was
100%-keyboard-only, the options menu's interactive rows were keyboard-only
(only its close button was clickable), the death screen was Enter-only, and
the trade panel's buttons visually never highlighted on hover despite the
underlying "draw a hoverable button" helper already supporting it. The plan
extended the SAME existing pattern to the gaps rather than introducing a new
UI framework, since the existing one already worked well everywhere else.

A "compactness" pass was explicitly requested too ("make them more
appealing and compact"), but the assistant deliberately did NOT shrink slot/
icon sizes back down, because in an earlier part of the same overall project
the user had explicitly asked for LARGER icons ("item icons were too hard to
see") - reversing that for the sake of "compact" would have contradicted
confirmed prior feedback, so that specific sub-request was flagged back to
the user rather than silently done.

### How it was implemented (Python/pygame)

- **Established convention, extended, not replaced.** Every clickable panel
  in the UI module already followed one pattern: a `*_rects()` function
  (e.g. an equip-slot-rects function, a backpack-slot-rects function) returns
  the on-screen rectangle for every clickable element, and BOTH the drawing
  code and the input-handling code call that same function - so hit-testing
  and rendering can never drift out of sync. There was no shared abstract
  "Button" or "MenuItem" class; each screen hand-rolls its own rects function.
  The fix for each of the 4 gap screens was to add exactly this same shape of
  function, not invent a new one.
- **Hover state is just "does this rect contain the current mouse
  position," recomputed every frame** - a drawing function is given the live
  mouse position and independently decides, per element, whether to render it
  in its "hovered" visual state (a pre-existing helper for drawing a
  bevelled/3D-look button already supported a hovered boolean; it just wasn't
  being passed one at 3 of the 4 gap sites).
- **Class select**: gained a rects function returning one rectangle per
  class-portrait tile; the mouse-down handler gained a branch that, on a
  class-select screen, checks those rects and immediately both selects AND
  confirms that class in one click (mirroring what pressing Enter already
  did for the keyboard-selected class, rather than re-implementing the
  "start a new character" logic a second time).
- **Options/help overlay**: previously ONE keyboard-navigated list plus a
  single clickable close-X. Gained a rects function for its interactive rows;
  clicking a row now fires that row's action exactly the way pressing Enter
  on the keyboard-highlighted row already did (both paths call the same
  underlying action, never duplicated). A genuine bug in the OLD behavior was
  fixed as a side effect: while this overlay was open, mouse clicks used to
  fall straight through to whatever was underneath (inventory, world) - now
  the overlay properly consumes clicks while it's open, the correct behavior
  for a modal.
- **Death screen**: replaced a bare "press Enter" text prompt with a real
  drawn, hoverable button; Enter still works as a shortcut. Single-player and
  the co-op client actually needed slightly different logic here, because
  single-player's "die" flow re-opens full class selection (any class, any
  loadout) while co-op's "die" flow only ever offers "respawn as the SAME
  class you already joined with" (a server-side design choice made earlier)
  - the button correctly routes to whichever of the two flows that mode
  already used for its Enter-key path, rather than incorrectly giving co-op a
  class-reselect option it doesn't support.
- **Trade panel**: its Accept/Cancel buttons were drawn onto an offscreen
  surface first, then the whole surface was blitted onto the screen at an
  offset - so making them hover-aware required translating the live mouse
  position INTO that surface's own local coordinate space (subtract the
  blit's origin) before hit-testing, otherwise every hover check would silently
  compare screen-space coordinates against panel-local rectangles and never
  match. This exact class of bug (forgetting a coordinate-space translation
  when a panel is drawn to an offscreen surface first) is worth calling out
  explicitly for a Unity port, since Unity's own UI layout systems (Canvas,
  RectTransform) handle this translation for you automatically - it's a
  pygame-specific pitfall, not a design decision worth preserving.
- **A real bug was caught only because the new code was actually EXECUTED,
  not just read back.** The class-select rewrite referenced two local
  variables that were never actually defined in that function's scope - a
  leftover from an earlier edit. Every previous manual code review missed it;
  it was only caught because the assistant's own verification step rendered
  the screen for real in a headless test before calling the work done, which
  crashed immediately and pointed at the exact bad reference. This is the
  concrete example this project's testing discipline doc points to for "why
  real execution beats reading code back to yourself."

### Unity rebuild prompt

> Rebuild each menu screen (class select, options/settings, death/respawn,
> trade) as a normal Unity UI Canvas with real Button/Selectable components -
> Unity's UI system gives you hover, click, and keyboard navigation for free
> on every element, which removes the entire "hand-roll a hit-rect list and
> keep it in sync with drawing" problem this project solved manually in
> pygame. Preserve the DESIGN INTENT, not the implementation: every menu
> should support both mouse and keyboard interchangeably, ending on the
> death screen with a "New Character" (single-player) or "Respawn" (co-op,
> same class only) action bound to both a click and Enter, and the options
> overlay should be a true modal that blocks input to whatever is behind it
> while open. Do not literally port the "offscreen-surface-then-blit"
> pattern - it existed only to work around pygame's lack of a scene-graph UI
> system, and Unity's Canvas/RectTransform hierarchy already solves the
> coordinate-space problem it was needed for.

---

## 3. Multi-Ability Pet Leveling + Feeding

### What it is

A hatched companion pet that follows the player and can simultaneously heal
the player, restore their mana, AND attack nearby enemies - all three
abilities running independently and able to fire within the same instant -
instead of the old design where a pet was permanently locked into exactly
one of those three behaviors for its whole lifetime. Each of the 3 abilities
levels up independently by feeding the pet backpack items, capped by the
pet's rarity.

### Why the user chose it

Directly requested, as part of the same message quoted above: "...and maybe
add some per info and levels to it which he can be fed with items and level
up so he heals you more (make him be able to heal give mana and damage/
shoot other enemies all at the same time)." The parenthetical is explicit
and load-bearing: the user specifically objected to a pet only ever doing
ONE of those three things.

Before designing the fix, the assistant checked the REAL game this project
is inspired by (RotMG) and confirmed its actual pets already work exactly
this way - three independently-leveled ability slots per pet, fed
separately - so this wasn't a departure from the source material, it was
catching up to a mechanic the earlier version of this project simply hadn't
gotten to yet.

### How it was implemented (Python/pygame)

- **Old shape**: a pet object had exactly one fixed "family" (heal / mana /
  attack) chosen permanently at hatch time from the egg's kind, and its
  per-frame update function was a single `if family == X / elif family ==
  Y / elif family == Z` chain - structurally, only one branch could EVER
  execute for a given pet, forever.
- **New shape**: a pet holds a small dictionary of exactly 3 independent
  ability "slots" (heal, mana, attack), each tracking its own current level,
  accumulated feed-experience, and its own individual cooldown timer. The
  per-frame update function became a loop/sequence over all 3 slots instead
  of an if/elif chain: each slot independently checks whether ITS OWN
  cooldown has expired and, if so, attempts to fire - meaning heal, mana
  restore, and an attack projectile can all genuinely happen in the exact
  same simulation tick, which is the literal thing that was asked for.
- **Per-level scaling formula, not a fixed lookup table**: each ability's
  magnitude (how much it heals/restores/damages) and cooldown are computed
  live from that ability's own level using a simple multiplicative curve -
  magnitude grows a fixed percentage per level, cooldown shrinks by a fixed
  percentage per level with a floor well above zero so a maxed-out pet still
  has a real, readable cadence rather than firing every instant.
- **Rarity still matters, differently**: an egg's rarity (common through
  legendary) used to directly multiply the pet's single fixed stat block at
  hatch time. Now rarity instead determines (a) the MAXIMUM level each of the
  3 slots can ever reach, and (b) how advanced the pet's "natural specialty"
  ability (inherited from its egg kind) starts at hatch - the other two
  abilities always start at level 1 regardless of rarity, which is what
  actually gives feeding real, ongoing purpose instead of a one-time hatch
  roll.
- **Feeding**: a new player action consumes one backpack item (any item
  except an egg - eggs are hatched, not fed) and grants feed-experience
  proportional to that item's own existing tier/rarity value, split evenly
  across all 3 ability slots; each slot independently levels up once its own
  running experience total crosses a flat per-level threshold, capped and
  clamped at that pet's rarity-derived maximum per slot. This was wired in as
  a new kind of drag-and-drop TARGET (a new small always-visible pet-info
  panel became a legitimate drop zone, exactly like dragging an item onto an
  equip slot already was) rather than a keybind, reusing the exact same
  drag-and-drop plumbing every other item-consumption action in the game
  already used, both in single-player and (mirrored) on the authoritative
  co-op server.
- **Networking/persistence**: the pet's serialized state (used both for
  saving a character to disk and for syncing a player's pet to OTHER
  co-op players) previously only carried its kind and position - a peer's
  view of your pet never reflected how powerful it actually was. It was
  extended to also carry each ability slot's level and accumulated
  experience (still simple, JSON-safe values), so both save/load and
  multiplayer sync now correctly preserve real pet progression.
- **A real regression was found by the user actually playing, not by any
  automated test.** Clicking the new pet-info panel crashed the game
  outright with a Python `TypeError`. Root cause: the panel had been wired
  into the SAME generic "what did the player click on" dispatcher every
  other inventory slot uses, but that dispatcher's fallback code path
  assumed every unrecognized slot type corresponds to a real player
  attribute it could look up by name - the pet panel is a drop-TARGET only
  (you feed items onto it; there's nothing to pick UP and drag out of it),
  so it was never given a real attribute name, and the generic fallback
  choked on that empty case. The fix was a one-line special case ("this slot
  kind is never draggable FROM, full stop") added in both the single-player
  and co-op client input handlers. The lesson generalizes directly to a
  Unity rebuild: when adding a NEW kind of interactive UI slot to an
  existing generic slot-dispatch system, explicitly enumerate what happens
  when nothing can be picked up from it - don't rely on a fallback branch
  written before that slot type existed. The original automated test suite
  for this feature had verified the FEEDING logic directly and verified the
  drag-and-drop rect geometry, but never actually simulated a bare mouse
  click on the new panel with nothing being dragged - a gap in test
  coverage, not just a gap in the feature code.

### Unity rebuild prompt

> Model a pet's power as 3 independent ability components (Heal, Mana,
> Attack), each with its own Level, AccumulatedXP, and cooldown Timer -
> a small array/list of a shared "PetAbility" struct rather than an enum
> discriminating one fixed behavior. Every fixed-timestep tick, iterate all
> 3 abilities and let each independently check its own cooldown and act if
> ready, so all 3 can fire in the same frame. Compute each ability's
> magnitude/cooldown from a simple per-level curve (e.g. magnitude *= 1 +
> 0.15*(level-1), cooldown *= 0.95^(level-1), clamped to a sane floor).
> On hatching, set one ability (matching the egg's declared "specialty") to
> an elevated starting level and leave the other two at level 1; store each
> egg rarity's MAX level cap separately from the starting level. Implement
> feeding as a drag-and-drop (or explicit "Feed" button) action that consumes
> an inventory item and distributes proportional XP across all 3 abilities,
> respecting the per-ability level cap. Serialize per-ability level+XP in
> both your save system and your network replication, not just the pet's
> visual kind/position. When you add the pet-info UI panel, make sure your
> generic "handle a click on any inventory-like slot" code explicitly treats
> it as a non-draggable drop target from day one, rather than assuming every
> slot type is pick-up-able by default.

---

## Verification approach used for this whole batch

Every sub-feature above was checked with real headless execution (constructing
real game objects and simulation state, calling the real update functions, and
asserting on the resulting state), not just by reading the changed code back -
including one wildlife-flee test that actually ran 30 simulated frames and
measured that the fleeing creature's distance from the threat genuinely
increased, and the class-select `NameError` and pet-panel `TypeError` bugs
described above, both of which were only caught this way (one by the
assistant's own pre-release testing, one by the user's actual play session).
The full existing regression suite (a loot-difficulty-distribution check) and
a full-application import smoke test were re-run after every individual
sub-feature, not just once at the very end.
