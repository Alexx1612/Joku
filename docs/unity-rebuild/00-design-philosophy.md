# Design philosophy - how this game was actually built

This doc is not a feature list (the numbered batch docs cover that). It's the
cross-cutting patterns that shaped *every* feature, gathered by reading back
across the entire project history (multiple Claude Code sessions, dozens of
batches, `2026-09-19` through `2026-09-23`). If you're rebuilding this game in
Unity/C#, read this first - it tells you which habits produced a project that
kept shipping cleanly at increasing scale, which of those habits are
Python/pygame-specific plumbing Unity already solves for you, and which are
genuinely engine-agnostic engineering discipline worth keeping regardless of
language or engine.

Every claim below cites the real file/function it came from and the batch
that established it, so you can go verify it against current code rather than
trust this doc blindly - it's itself a snapshot, not live state.

## 1. One simulation core, two front ends

The single most load-bearing architectural decision in this codebase:
`game/realm_sim.py`'s `RealmSim` class is the *entire* game simulation - enemy
AI, loot rolls, ability resolution, dungeon generation and quest state,
day/night, everything that isn't rendering or input. `main.py` (single-player)
and `server.py` (co-op host) both drive **the same `RealmSim` instance type**,
calling the same `update(dt, players)` method every tick. Single-player is
just "a co-op server with exactly one player and no network," not a separate
implementation.

**Why this matters**: single-player and co-op cannot silently drift apart into
two different games, because there is only one place gameplay logic lives.
Every one of the ~9 major batches touched `realm_sim.py` once and both modes
got the feature - no "port this to co-op too" follow-up step ever appeared in
this project's history.

**Unity translation**: this maps directly onto a headless/server-authoritative
simulation class with two thin presentation layers (a local host and a
networked client), which is exactly the client/server split most Unity
multiplayer stacks (Netcode for GameObjects, Mirror, Fish-Net) already expect.
Keep this shape - don't let gameplay logic leak into `MonoBehaviour.Update()`
on presentation-layer objects. The Python-specific detail (a single process
importing the same module twice) goes away, but the *principle* - exactly one
authoritative simulation, thin views on top - is the thing worth preserving.

A corollary pattern worth calling out: **anything baked directly into the
static world grid needs zero new network plumbing**. The per-instance tile
map (`RealmSim.realm_map.grid`) is already synced to co-op clients wholesale,
once, per instance. Batch 4/5/9 deliberately implemented landmark buildings,
decoration props, tall props, and even entire islands as *grid tile content*
rather than as separate tracked entities specifically so co-op support was
free - confirmed via `server._snapshot_for()` needing zero changes for any of
them. When a new piece of world content is static for the lifetime of an
instance, prefer "bake it into the grid" over "track it as an object list" -
in Unity this is the same argument for baking static geometry into a scene/
NavMesh rather than spawning it as networked objects.

## 2. The procedural-first art pipeline (and its one hand-painted override)

Every sprite - player, enemy, boss, tile texture, decoration prop - is
generated from the same primitive: a small ASCII "grid" (one character per
cell) plus a flat-color palette dict, rendered by `game/sprites.py`'s
`_autline_and_render(grid, palette, scale, shaded=True)`:

- **Pass 1**: black outline auto-computed wherever a filled cell touches an
  empty/out-of-bounds cell - never hand-placed.
- **Pass 2**: each filled cell's flat palette color gets a soft top-down
  vertical gradient PLUS a rim-light brightening on cells touching the
  silhouette's top/left edge - both computed automatically from grid position,
  never hand-picked per cell.
- The result is 2x-upscaled via Scale2x (`_scale2x`, a smart pixel-art
  upscaler that extends diagonal edges) then smoothscaled to final size.

This is why the game looks like RotMG's crisp-outline flat-color style with
real depth cues despite every asset being authored as a handful of
`fill_rect`-shaped calls, not painted pixel-by-pixel.

**The hand-painted PNG layer is an *optional override*, never a hard
dependency**: `sprites._load_art(filename, size)` tries to load a PNG first
and returns `None` on any failure (missing file, decode error), and every
sprite-lookup function (`player_sprite`, `enemy_sprite`, `bullet_surface`,
`tall_prop_sprite`, etc.) falls back to the procedural grid render if the PNG
load returns `None`. This was an explicit original requirement and stayed
load-bearing for a real reason: this project ran with **multiple concurrent
Claude Code sessions editing the same repo with no git safety net for most of
its history** (git was only initialized partway through) - a partially-landed
art batch from one session could never break the other session's build,
because the fallback always renders *something* correct.

**Hard-won correctness rule, learned from a real regression (Batch 3
follow-up)**: there are two visually different categories of sprite and they
need *opposite* alpha conventions:
- **Ground-replacing tile textures and flat decoration props** must be
  **100% opaque** - `TileMap.draw()`'s blit path draws them with no color
  fill underneath first, so anything less than fully opaque renders as
  black/glitchy gaps. The first attempt at 5 new decoration kinds used a
  transparent-sprite-silhouette style (correct for characters) and was
  functionally invisible in-game - not just "too subtle," a real rendering
  bug, caught only by sampling actual on-screen pixels, not by inspecting the
  texture file directly.
- **Free-standing/character/tall-prop sprites** (players, enemies, bullets,
  the `totem`/`pole`/`pillar` tall-prop category) genuinely need transparent
  backgrounds, since they're blitted on top of an already-drawn floor tile.

If you rebuild this in Unity, this whole opaque-vs-transparent distinction
disappears on its own - Unity's sprite renderer and tilemap system already
handle this correctly by construction (a Tile asset is a Sprite draw over
whatever's beneath it, alpha works "normally"). It's flagged here only because
it was a real, repeated source of bugs in the from-scratch pygame
implementation and is worth knowing about if anyone ports the actual PNG
assets over rather than re-authoring in Unity's own tools.

**Hard-won style rules from hand-authoring characters** (all 8 player classes,
`rotmg_art_vfx_plan.md` sessions #2-#5), useful if re-deriving character
silhouettes rather than reusing the PNGs directly:
- **One flat color per distinct material only.** Hand-adding a second
  "lighter/darker variant" color for a highlight or shadow on top of a
  material that `_autline_and_render`'s automatic gradient+rim-light *already*
  shades reads as cluttered, not detailed - a real correction after an early
  batch used 13-16 materials per character vs. the reference (Wizard)'s ~8.
  Let the auto-shader supply all the "volume."
- **No fill color may be close to the outline color.** The outline is a fixed
  near-black (`(10,10,12)`); several early boot/cloak colors were dark enough
  that the outline became invisible against them, reading as an
  undifferentiated blob ("looks unfinished"). Floor: keep dark accents at or
  above roughly `(40,35,45)`.
- **A consistent eye/brow *position* across all characters, with per-character
  iris/brow *color*** - keeps faces immediately distinguishable without
  looking like copy-paste.
- **Every character gets one small signature "twist" visual** (a glow accent,
  a distinct silhouette element) - this followed direct user correction after
  an early attempt reused another class's exact silhouette geometry just
  recolored ("please dont reuse assets and make everything special"). The
  convention that eventually settled: *primary, narratively-visible* content
  (player classes, bosses, quest-relevant creatures like `totem`) gets a
  genuinely unique shape; *minor/secondary* content (a second signature mob
  per biome, later ambient-wildlife additions, the Batch 9 shard/choir
  guardian rosters) is explicitly allowed to reuse an existing base grid with
  a new palette - confirmed multiple times as a deliberate, accepted
  efficiency tradeoff, not a violation of the "no reuse" rule, which was about
  primary character art specifically. Apply the same proportionality in
  Unity: spend unique-silhouette budget on what the player will actually
  focus on.

For a from-scratch Unity rebuild, the *engine-agnostic* takeaway is: define a
tiny, consistent authoring primitive (grid+palette, or an equivalent low-effort
format), automate everything mechanical (outline, shading, upscaling) from
that primitive, and reserve hand-authoring effort for shape/color choices that
actually need a human eye. The literal pygame rendering code doesn't port,
but the *workflow* absolutely does - it's the reason this project could ship
70+ enemy kinds, 8 classes, dozens of decoration categories, and full boss
rosters without ever bottlenecking on art production.

## 3. Sound is code, too

Every sound effect and music track is synthesized at runtime from raw
waveforms (`game/audio.py`) - no audio asset files anywhere in the project.
Same underlying philosophy as the sprite pipeline: a small set of parameters
(pitch, wave shape, envelope) drives procedural generation instead of curated
assets, and per-category variation (e.g. `_BARK_PROFILE`'s per-family
growl/moan/hiss/mechanical-groan shapes for mob sounds) comes from tweaking
those parameters, not recording/sourcing more files. In Unity this genuinely
doesn't need porting - Unity's audio/asset pipeline is mature and there's no
reason to hand-roll waveform synthesis there - but it's worth knowing *why*
the original did this (zero external assets, one dependency-free codebase)
if you're deciding what counts as "flavor to preserve" vs. "workaround to
retire."

## 4. UI convention: a `*_rects()` helper per panel, not a widget framework

Every clickable UI surface in `game/ui.py` follows the identical shape: a
`some_thing_rects()` function that returns the hit-test geometry (a list of
`pygame.Rect`s, or `(rect, meaning)` pairs), consumed by BOTH the draw
function (to know where to render) and the input handler (to know what was
clicked) - `equip_slot_rects()`, `backpack_slot_rects()`,
`vault_chest_tab_rects()`, `class_select_tile_rects()`,
`help_menu_item_rects()`, `death_screen_button_rect()`,
`pet_feed_target_rect()`, and so on, dozens of these by the end of the
project. There is no shared `Button`/`Panel`/`Widget` base class anywhere.

This is a deliberate "extend the existing pattern, don't invent a new
abstraction" bias that shows up everywhere in this project, not just UI - see
also section 6 below. It kept every new panel a small, self-contained,
copy-a-neighbor-and-adjust addition instead of a change that had to flow
through a shared framework. The tradeoff is real (some duplication across
`*_rects()` functions that a real widget class would collapse), and it was an
accepted one for a project of this size and pace.

**Unity translation**: Unity's UI systems (uGUI, UI Toolkit) already give you
real widgets with built-in hit-testing, so there's no reason to reproduce the
`*_rects()` pattern literally - use `Button`/`EventTrigger`/UI Toolkit
`VisualElement`s properly. The underlying *principle* worth keeping is the
bias itself: reach for the platform's existing primitive before building a
custom abstraction, and don't over-engineer a shared base class for something
that's naturally just a handful of similar-shaped functions.

## 5. Kind-count-agnostic content registries, with real ID-space discipline

Enemy kinds, decoration props, potions, abilities, dungeon themes - every
"here's a family of interchangeable content" registry in this project is a
plain dict/list that scatter loops and tile-id allocation iterate generically.
Adding a new decoration kind, ambient-wildlife species, or potion stat is
almost always a pure *data* addition (one new dict entry) with **zero**
changes to the code that consumes the registry - confirmed explicitly and
repeatedly (Batch 3's 5 new decoration kinds, Batch 5's 10 more, Batch 9's 20
new mob kinds all landed this way).

The one recurring real bug category this pattern produces is **numeric tile-ID
space collisions** between independently-added registries, and the project
learned two specific hard lessons worth carrying forward verbatim:

1. **Don't eyeball a min/max range as a collision check - verify real
   allocated values.** Because different registries can interleave their
   actual IDs within overlapping *ranges* while never literally colliding
   (e.g. `TALL_PROP_TILE` spans 1000-1209 on paper because it includes both
   a biome/dungeon block *and* a separately-allocated Nexus block, with real
   gaps between them), a naive "do these ranges overlap" glance both under-
   and over-reports collisions. Run an actual pairwise scan of allocated
   values before trusting a new ID block is safe (Batch 5 did this and caught
   a real collision a range-eyeball would have missed).
2. **Two different registries can share a literal string key and silently
   collide even with correct numeric ranges** - the biome named `"cave"` and
   the dungeon *theme* named `"cave"` are different concepts that happened to
   share a string, and an unprefixed `(area_name, kind)` dict key ate 6 IDs
   silently before this was caught (fixed by namespacing dungeon-theme keys
   as `f"dungeon:{theme_name}"`). If two registries key by name and their
   name-spaces can overlap, prefix one of them.

In Unity, this maps onto ScriptableObject-based content registries
(`EnemyDefinition`, `DecorationDefinition` assets in an addressable/resource
folder) rather than hand-maintained numeric tile IDs - Unity's own tilemap and
addressables systems remove the "manually allocate a numeric ID range" problem
entirely, since assets are referenced by GUID/object reference, not a flat
integer you allocate by hand. The *lesson* to keep is the general one: any
time two independently-evolving systems can produce colliding identifiers
(numeric OR string), verify it with a real automated check, not inspection.

## 6. One generic "something happened" broadcast channel

`RealmSim` exposes exactly three per-tick event lists - `self.events` (feed
messages), `self.vfx_events` (particle/screen-shake triggers), and
`self.damage_popups` (floating combat numbers) - reset once per tick via
`begin_tick()` and consumed generically by whatever's watching (single-player
draw loop, or `server.py`'s snapshot builder for every co-op client). Every
new feature that needs to tell the player "X just happened" appends to one of
these three lists rather than inventing a new notification mechanism - the
island mini-quest's completion announcement (Batch 9) explicitly reuses the
exact same `self.events`/`self.vfx_events` pipeline the world-boss-spawn
announcement already used, specifically *because* it's already proven to
reach both single-player and every co-op client with no additional plumbing.

This is the event/vfx equivalent of section 1's "one simulation core" idea:
rather than each feature building its own "tell the client" mechanism,
everything funnels through a small, fixed number of well-understood channels.
In Unity, this is the same argument for a small number of well-typed
`UnityEvent`/C# `event`/signal channels (or a lightweight pub-sub) that every
system publishes onto, rather than each feature wiring its own bespoke
UI-notification code.

## 7. Testing discipline: real execution, not code review, and real scale

This is the single most repeated phrase across this project's entire
history, and it is not a platitude - it caught genuine, would-have-shipped
bugs, over and over, that a code read alone did not catch:

- **Always instantiate real objects and call real methods on a real
  (offscreen) surface/buffer before calling something done.** A `Bullet`
  class missing a `shape` attribute in `__slots__` despite `draw()` already
  referencing `self.shape` compiled cleanly and would have raised
  `AttributeError` on the very first shot fired in a real game - only caught
  by actually firing a bullet and drawing it. `draw_class_select` referencing
  undefined `y0`/`row_h` locals (a leftover from a botched edit) compiled
  cleanly and would have thrown the first time anyone opened class select -
  only caught by an actual headless render. Both are examples of the general
  rule: **Python only checks names/attributes at the moment code actually
  runs that line - `python -m py_compile` proves the file *parses*, nothing
  about whether it *works*.**
- **For anything involving randomness or procedural generation, one seed
  proving something works is not proof it always works.** The unbeatable-
  dungeon geometry bug (Batch 6) is the canonical example: a first fix
  attempt tested clean on the theme it was found in (0/300 failures) and
  would have shipped broken for a *sibling* theme that needed a genuinely
  different fallback (2/300 failures, only caught by testing all affected
  themes, not just the one). The project's standing bar became: sweep
  hundreds of seeds across every affected variant before calling a procedural-
  generation fix done, not one or a handful.
- **Co-op-specific behavior needs a real multi-session round trip, not
  single-player reasoning about what "should" happen over the network.**
  Several real correctness gaps only ever manifested through this: peers
  matching by zone alone silently mixing players from *different* concurrent
  dungeon instances together (Batch 7), per-viewer line-of-sight visibility
  needing to differ between two simultaneously-connected sessions (Batch 3
  follow-up), a client's own pet visual never reflecting the owner's real
  leveled-up state because only 3 raw fields synced (Batch 8). All were
  caught by literally constructing a `ServerState`/multiple `Session`s and
  calling `_snapshot_for()`/`step()` for real, not by reading the code and
  reasoning about what it does.
- **Verify with a technique that exercises the real render code, not GUI
  automation.** Screenshotting the actual running window via OS-level input
  automation (SendKeys/SetForegroundWindow) was tried and found unreliable
  on the dev machine; the technique that consistently worked was a throwaway
  script that imports the real game modules, constructs the real objects,
  calls their real `.draw()` methods onto an offscreen `pygame.Surface`, and
  saves/inspects the result. This exercises the literal same code path the
  live game uses with zero window-focus flakiness. In a Unity rebuild, the
  equivalent is EditMode/PlayMode tests that instantiate real prefabs/
  components and assert on their actual rendered/simulated state, not a
  human tester dragging windows around, and not assertions based only on
  reading the component code.

None of this is Python-specific. If anything it matters *more* in a
statically-typed engine like Unity/C#, since the temptation to trust "it
compiled, therefore it's correct" is stronger there - and it's exactly as
wrong there as it was here.

## 8. Workflow: research-then-plan for big features, real parallel forks for independent ones

Every substantial new feature in this project's later history went through
`ExitPlanMode`/`EnterPlanMode` - a proposed design written up and approved
*before* implementation started, not implemented ad hoc - and for anything
grounded in "how does the real RotMG do this," real web research (wiki pages,
RealmEye, dev blogs) happened *before* the plan was written, not after
("real RotMG-wiki research done first ... before planning" is a recurring
phrase). Plan files were saved to disk (`C:\Users\...\.claude\plans\...`) so
the reasoning behind a design choice survives past the conversation that made
it.

For genuinely independent pieces of work (Batch 4's building-stamping +
semi-3D rendering + hand-painted art, Batch 5's three simultaneous decoration-
registry forks, Batch 6's five-subsystem adversarial audit), this project used
**real concurrent sub-agent forks**, each scoped to a distinct file or
section so they couldn't step on each other, with one explicit,
non-negotiable rule: **re-verify the composed result after all forks land,
never just trust each fork's own isolated self-report.** This is exactly how
the id-collision bugs in section 5 were caught - each individual fork's own
work was locally correct; only integration testing across all of them
together surfaced the real problem.

## 9. Communicate honestly about scope and judgment calls

A writing habit worth calling out because it's part of *how* this project
stayed trustworthy at this scale, not just a nicety: whenever a design
decision wasn't fully grounded (e.g. "could not get precise wiki numbers via
WebSearch, so this balance pass is grounded in X instead - flagging the
distinction so it isn't miscited as wiki-verified later"), or whenever a
choice had a real tradeoff the user hadn't explicitly signed off on (e.g. the
two-portal-touching-in-one-tick co-op edge case in Batch 6, explicitly
surfaced as "needs a deliberate design response" rather than silently picked
by the implementer), the project wrote that down plainly instead of quietly
picking an answer and moving on. Several real design decisions in this
project's history (dungeon difficulty as a portal label vs. a popup choice,
whether a second dungeon-boss phase should be one portal or two) were
resolved by explicitly asking the user rather than guessing. Keep doing this
in a rebuild: a wrong guess costs a rework cycle; an honest "here's the
tradeoff, which do you want" costs one question.

## Quick reference: keep as-is vs. Unity replaces it

| Convention | Keep the *principle* in Unity | Unity-native replacement for the *mechanism* |
|---|---|---|
| One shared simulation core (`RealmSim`) driving both single-player and networked play | Yes - single source of truth for gameplay logic | Server-authoritative simulation class + thin client views (Netcode/Mirror/Fish-Net shape) |
| Grid/palette + auto-shader sprite authoring | Yes - automate the mechanical parts (outline, shading), spend human effort only on shape/color | Could stay a Python pre-processing script emitting PNGs, or become a custom Editor tool; either way, Unity's Sprite/Tilemap import pipeline replaces the runtime rendering |
| Hand-painted-PNG-with-procedural-fallback | Principle (graceful degradation across concurrent editors) less relevant once on real source control | Not needed - Unity assets live in one authoritative repo/version-controlled state |
| Opaque tile texture vs. transparent sprite distinction | N/A - this was a pygame blit-order bug class | Unity's Tilemap/SpriteRenderer already handle this correctly |
| `*_rects()` hit-test-and-draw helper per UI panel | Keep the "reach for the platform primitive first" bias | Real `Button`/`EventTrigger`/UI Toolkit widgets |
| Numeric tile-ID block allocation with manual collision checks | Keep "verify collisions with a real automated check" | ScriptableObject/ addressable references remove manual ID allocation entirely |
| Baking static world content into the tile grid for free network sync | Yes - baked/static content shouldn't cost networked-object overhead | Baked static geometry / NavMesh / non-networked scene content |
| Three generic event-broadcast lists (`events`/`vfx_events`/`damage_popups`) | Yes - a small number of well-typed channels, not one per feature | `UnityEvent`/C# events/a lightweight pub-sub |
| Procedural audio synthesis (no asset files) | No strong reason to keep - was a "zero dependencies" constraint | Unity's audio pipeline, real authored/licensed assets |
| Real headless execution before calling anything done; large-N seed sweeps for procedural gen; real multi-session co-op round trips | Yes, unconditionally - this is the highest-leverage habit in the whole project | EditMode/PlayMode automated tests exercising real instantiated objects |
| Research-then-plan-then-approve for big features; real parallel forks + mandatory re-verification for independent ones | Yes | Same workflow, engine-agnostic |
