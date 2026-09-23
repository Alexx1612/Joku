# 10 — Social features, HUD/UX polish, and a performance/bugfix stream (Batch 2)

Covers the long, rapid-fire stream of asks sent while the game's original
foundational plan (Batch 1) was paused. Source: `memory/project_rotmg_batch3_bags_dungeons_bosses.md`,
"## Batch 2" section (near the end of that file — it was written last even
though it covers early-chronology work). Reconstructed from that memory file's
"DONE" rounds 1-6, plus direct verification against the current codebase
(`main.py`, `coop_client.py`, `game/entities.py`, `game/realm_sim.py`,
`game/world.py`, `game/ui.py`, `game/audio.py`).

This was never a single planned batch — it was accumulated in-session across
many small user asks and several real bug reports found by actual play, not
code review. Treat each subsection below as its own feature; they shipped
independently, not as one coordinated design.

---

## A. Mob audio & flavor-text system

**What it is:** Every enemy family growls/moans/hisses with a distinct
synthesized waveform instead of one flat blip, occasionally says a short
flavor line in a speech bubble above itself, and (for neutral wildlife and
bosses specifically) that line also lands in the persistent chat log.

**Why:** The user wanted mobs to feel alive rather than silent damage
sponges. Two follow-up complaints shaped the final rate-limiting: bubbles
were showing the mob's own name (removed), and later a report of mobs
"talking message-over-message, 10 messages per sec" was logged as a known
open issue — the per-mob 20s floor exists but the *aggregate* rate across
an ~800-enemy continent was never separately capped, and the investigation
was still pending when this stream paused.

**How it was implemented:**
- `game/audio.py`'s `_BARK_PROFILE` dict + `_bark_wave()` — one procedurally
  synthesized waveform shape per enemy family (growl/moan/hiss/etc.), not a
  single reused blip.
- `game/entities.py`, `Enemy.MIN_REBARK_INTERVAL = 20.0` (entities.py:754) —
  a hard per-mob floor between flavor lines. The aggro branch and idle
  branch both gate on `self.speech_age > self.MIN_REBARK_INTERVAL`
  (entities.py:888, entities.py:891).
- `ui.MOB_SPEECH_COLOR` — mob speech bubbles render in a distinct yellow,
  and deliberately never show the mob's name (a user-requested removal).
- Neutral mobs originally had an `if not self.neutral:` gate suppressing
  their idle flavor line entirely (sound-only); removed so neutral wildlife
  now has real "words," not just noise. Safe because a neutral mob's
  `self.aggro` is permanently `False`, so it can only ever reach the idle
  branch anyway.
- Persistent-chat-log integration: `Enemy._speech_pending` flag,
  `RealmSim.mob_speech_events` list (reset every tick in `begin_tick()`),
  serialized by `server.py` as `"mob_speech"` in the Realm/Bonus snapshot,
  consumed into `self.chat_log` by both `main.py` and `coop_client.py` (shown
  as e.g. "Forest Hare: *bares teeth*" — the chat log names the speaker even
  though the in-world bubble deliberately doesn't; two different surfaces on
  purpose). Later narrowed to neutral mobs + bosses only (regular aggro'd
  trash/elites keep the in-world bubble but don't spam the log) via a filter
  at the `mob_speech_events` append site: `if e.neutral or e.rank == "boss":`.
  Bosses need no extra code since they're always `aggro=True` and already
  re-trigger via the same rebark timer.

**Known unresolved issue (explicitly flagged, not fixed):** a user report of
far-too-frequent mob chatter was logged as a note-only item — the per-mob
20s floor is confirmed correct in isolation, but the *aggregate* rate across
a large population was never measured or capped. If rebuilding, budget for
either a screen-wide/zone-wide concurrent-speech-bubble cap on top of the
per-mob cooldown, or instrument the real trigger rate under load before
assuming the per-mob gate alone is sufficient.

**Unity rebuild prompt:**
> Build a per-enemy-family bark/vocalization system: each enemy archetype
> (e.g. "beast," "undead," "elemental") has its own short procedural or
> sampled vocalization and a small pool of flavor-text lines. On aggro and
> periodically while idle, an enemy may show a floating speech bubble with a
> flavor line (never its own name) and play its family's bark sound, gated
> by a hard per-enemy cooldown (~20s) so no single enemy spams. Neutral/
> passive wildlife gets idle-only flavor lines (no aggro state). Route
> neutral-wildlife and boss speech into a persistent, scrollable chat/combat
> log (shown with the speaker's name there, unlike the transient bubble);
> regular hostile trash/elite speech stays bubble-only. Before shipping,
> load-test with hundreds of concurrent enemies near the player and add an
> aggregate rate cap (e.g. max N visible speech bubbles at once, or a
> global cooldown) if the per-enemy cooldown alone still produces
> overwhelming simultaneous chatter at scale.

---

## B. Lair "Minecraft-spawner" respawn trickle

**What it is:** A cleared enemy lair doesn't refill while you're standing
next to it — it only trickles enemies back, one at a time, once no player is
within sight range of it.

**Why:** Matches the user's own naming for the mental model ("Minecraft
spawner") — a farmed-out spot should feel actually cleared while you're
there, not instantly restock.

**How:** `game/realm_sim.py` — `LAIR_RESPAWN_SIGHT_RANGE = 700`
(realm_sim.py:149), `LAIR_RESPAWN_INTERVAL = 5.0` (realm_sim.py:150), plus a
per-lair `respawn_cd` timer. The respawn check only fires when
`any(p.pos.distance_to(lair["pos"]) <= LAIR_RESPAWN_SIGHT_RANGE for p in
alive)` is `False` (realm_sim.py:958), and even then respawns at most one
enemy per lair every `LAIR_RESPAWN_INTERVAL` seconds
(`lair["respawn_cd"] = LAIR_RESPAWN_INTERVAL`, realm_sim.py:978).

**Unity rebuild prompt:**
> Implement enemy-lair respawning as a sight-gated trickle: each lair tracks
> its own respawn cooldown. While ANY player remains within a fixed sight
> radius of a lair, it never respawns enemies. Once no player is within that
> radius, the lair may respawn a single enemy, then must wait a fixed
> interval before it's eligible again (so a lair refills gradually over
> real time once abandoned, never all-at-once and never while being farmed).

---

## C. Co-op social suite: context menu, whisper, nearby-players panel, friends

**What it is:** A cluster of co-op-only social features layered on top of
the existing trade system: right-click a nearby player for a quick-action
menu, private `/w` whispers, a panel listing every player within 2 screens
with one-click teleport, and a persistent friends list.

**Why:** Direct user asks for making co-op feel more like a social hub
instead of just shared combat.

**How:**
- **Context menu** (`coop_client.py` only — single-player has no other
  players): `_peer_near_mouse()` finds a nearby player under the cursor,
  `_open_context_menu_for()`/`_context_menu_click()` handle it, drawn via
  `ui.draw_context_menu()`/`context_menu_rects()`. Options: **Chat**
  (pre-fills `/w Name ` in the chat box), **Trade** (sends `trade_request`
  with a specific target `pid` — `server.py`'s `trade_request` handler was
  extended to honor an optional `pid` preference over its previous
  "nearest player" default), **Teleport** (new server action
  `tp_to_player`), **Add/Remove Friend**.
- **Whisper chat**: `/w <name> <message>` command → new server action
  `whisper`, which routes directly to one target session plus an echo back
  to the sender — NOT broadcast to the zone. Appears only in the sender's
  and recipient's `chat_log`, never as an in-world speech bubble (it's
  private by design).
- **Nearby-players panel + TP**: `coop_client.py`'s `_nearby_players()`
  filters `self.peers` (the server already sends every same-zone peer
  unfiltered by distance — confirmed by reading `_snapshot_for`) down to
  `NEARBY_PLAYER_RADIUS` (`2 * max(SCREEN_W, SCREEN_H)`, i.e. "double my
  screen"), drawn via `ui.draw_nearby_players_panel()` with a one-click TP
  button per row.
- **Friends system**: new `game/friends.py` module, same per-account-name
  JSON-file persistence pattern as the existing `accounts.py`. Friends panel
  (`ui.draw_friends_panel`, toggled with the `L` key in `coop_client.py`)
  offers TP/Trade/Remove per row — TP and Trade are only enabled while that
  friend is an actual current peer (i.e. "online" in the same session).

**Unity rebuild prompt:**
> Add a co-op social layer on top of an existing player-to-player trade
> system: (1) a right-click context menu on a nearby player's world sprite
> offering Chat (prefills a private-message box), Trade (requests a trade
> with that specific player, not just whoever's nearest), Teleport-to-them,
> and Add/Remove Friend; (2) a `/whisper <name> <message>` chat command that
> routes privately to one recipient plus an echo to the sender, appearing
> only in their two chat logs, never broadcast; (3) a togglable "nearby
> players" panel listing everyone within a generous radius (e.g. 2 screen
> widths) with a one-click teleport-to-them button per row; (4) a persistent
> per-account friends list (survives logout) with online/offline state and
> quick Trade/Teleport/Remove actions, only enabled while that friend is
> actually online in the current session.

---

## D. Chat log UX: click-to-open, clipboard, expiry, scrollbar

**What it is:** The chat log went from a bare always-tiny box to a real
scrollable, clickable, copy-pasteable, self-expiring log.

**Why:** Direct usability asks across several rounds of this same stream.

**How:**
- Click-to-open: `ui.chat_log_rect`, wired into both `main.py`'s and
  `coop_client.py`'s mouse-down dispatch.
- Clipboard: Ctrl+A select-all (with a real visual highlight,
  `draw_chat_box`'s `selected=` param), Ctrl+C/X copy-out, Ctrl+V paste-in —
  via a new `game/clipboard.py` module (tkinter-based, a lazily-created
  hidden root window, reused across calls rather than recreated each time).
- Expiry: `CHAT_LOG_LIFETIME = 120.0` in both clients — messages are
  filtered out of `self.chat_log` right after the existing per-message
  age-increment loop.
- Scrollbar: a full rewrite of `game/ui.py`'s `chat_log_rect`/
  `draw_chat_log`, plus new `_chat_log_flatten()`/`chat_log_max_scroll()`
  helpers. Constants: `CHAT_LOG_STORE_CAP = 60` (replacing an old
  `CHAT_LOG_CAP = 12`), `CHAT_LOG_VISIBLE_LINES = 14`,
  `CHAT_LOG_SCROLLBAR_W = 8`. A `self.chat_scroll` state field plus
  mouse-wheel-while-hovering-the-log handling in both clients (checked
  *before* falling through to the existing minimap-zoom-on-wheel handler,
  so scrolling chat doesn't accidentally zoom the map).

**Known open gap:** right-click-to-open-the-context-menu currently only
works from a player's on-screen world sprite (`_peer_near_mouse`), not from
their name in a chat log entry — chat log entries would need to carry a
`pid` (currently only `name`/`text`/`age`) plus a click handler on the log's
row positions.

**Unity rebuild prompt:**
> Build a scrollable, persistent chat/log panel: messages accumulate in a
> capped ring buffer (e.g. last 60), only the most recent N (e.g. 14) are
> visible at once, with a real scrollbar/mouse-wheel-scroll (captured before
> any other wheel-bound UI like a minimap zoom). Messages auto-expire after
> a fixed duration (e.g. 2 minutes) independent of the scroll buffer cap.
> Support text selection (select-all, copy, cut, paste) via the OS
> clipboard. Each log entry should store the speaking player's identity
> (not just their display name) so a future feature (e.g. right-click a
> name in the log) can target them the same way right-clicking their
> on-screen sprite does.

---

## E. Options menu modal rebuild

**What it is:** The options/help overlay went from a fixed-size side panel
that could genuinely overflow off both the right edge and the bottom of the
screen, to a real centered, measured, clamped modal.

**Why:** Confirmed real bug (not just a user perception issue) — the old
panel guessed its own width instead of measuring rendered text, and never
clamped its height to the screen.

**How:** `ui.draw_help_overlay()` rewritten: every dimension is now measured
from the actual rendered text, the controls reference became a proper
2-column grid (was one long 13-row list), and the whole panel centers
itself and clamps to the current screen size. Same external call signature,
so no caller changes were needed. A peer art session later re-skinned it
with the shared HUD chrome once it was structurally correct.

**Known open gap:** the overflow/cramped-text bug is fixed and it's been
reskinned, but it's still one flat panel — not the tabbed/sectioned "real
menu like in many other games" the user originally described. Left as an
explicit "ask before building a bigger tabbed redesign" item, not silently
assumed to be needed.

**Unity rebuild prompt:**
> Build an options/help overlay as a real modal dialog: measure its content
> (don't guess dimensions), center it on screen, and clamp its size to fit
> within the current viewport at any resolution. Start with a single
> scrollable/paginated panel; only invest in a tabbed multi-section layout
> if explicitly requested, since a flat panel that actually fits the screen
> correctly may already satisfy the ask.

---

## F. HUD visual pass

**What it is:** A cluster of visual-only HUD changes: a bigger window, bigger
item icons, per-item tier badges, borderless item slots, wall/obstacle
silhouette outlines, and (via a collaborating peer session) a shared
gold-trimmed "chrome" skin applied across every panel.

**Why / user's own framing, quoted/paraphrased from memory:**
- Window size: user explicitly said "bigger window is enough" in response to
  a zoom request — i.e. they wanted more visible space, not actual
  camera/sprite zoom. `C.SCREEN_W/H` raised from 1024x640 to 1366x820; no
  camera-zoom feature was built, and the memory explicitly warns not to
  build one unless asked again.
- Full-map zoom: `game/minimap.py`'s `MAX_ZOOM` raised 3.0 → 8.0 (the M-key
  full-map overlay only; the small corner minimap's own separate zoom cap
  was intentionally left alone in this batch — it was later also bumped to
  match, in Batch 7, once the inconsistency was explicitly pointed out).
- Bigger icons: `SLOT_SIZE` 40 → 52 in `game/ui.py`. Icons are drawn at
  `SLOT_SIZE - 6` everywhere, so this one constant change made every
  equip/backpack/vault/bag-window/dragged-item icon bigger project-wide.
- Tier badges: new `ui._tier_badge(surf, rect, item)` — bottom-right corner,
  black-shadowed for legibility over any icon color, shows the tier number
  or "UT" for untiered items. Called at every item-slot draw site: the
  equip and backpack loops in `draw_inventory`, `draw_bag_window`,
  `draw_vault_screen`'s two grids, and the trade panel. Deliberately NOT
  drawn on `draw_dragged_item` (the floating cursor icon mid-drag) since
  that's not a slot.
- Borderless item slots: `_slot_frame()` gained a `border=True` parameter
  (default preserves old behavior everywhere not explicitly overridden).
  `border=False` is passed only at the item-slot call sites above; every
  other chrome element (context menus, nearby-players/friends rows,
  minimap, tooltips) keeps its border — a scoped fix, not a global style
  change, per "borders don't help identify items" without touching
  unrelated chrome.
- Wall outlines: `game/world.py`'s `TileMap.draw()` now draws a bright
  2px outline (`(235, 225, 195)`) along any edge of a `SOLID` tile that
  borders a non-solid tile or the map edge — this outlines the silhouette
  of an obstacle *cluster*, not a grid over every individual solid tile, so
  it reads as "here's one obstacle" rather than a checkerboard.
- Shared chrome (peer session's work, noted for completeness): one
  gold-trimmed bevel-panel/slot/bar system applied uniformly across every
  panel (player/equip/backpack/bag/vault/trade/context-menu/nearby-players/
  friends/tooltips/minimap/the just-fixed options overlay) — a pure
  redraw pass with zero hit-test/geometry changes.

**Real bug caught and fixed while wiring this:** `PLAYER_PANEL_WIDTH` was a
hardcoded literal (`178`), originally derived from the old `SLOT_SIZE=40`
(the code comment said so explicitly). With `SLOT_SIZE` now 52 this would
have silently misaligned the player panel against the equip/backpack row
below it. Updated to `226` (`4*52 + 3*SLOT_GAP(6)`), verified via a headless
render asserting `PLAYER_PANEL_WIDTH == 4*SLOT_SIZE + 3*SLOT_GAP` exactly.
Left as a literal (not a live expression) because it's defined earlier in
the file than `SLOT_SIZE`/`SLOT_GAP` — flagged explicitly as a trap for
next time: grep for `PLAYER_PANEL_WIDTH` after any future `SLOT_SIZE`
change, don't assume it auto-updated.

**Unity rebuild prompt:**
> Build the inventory/HUD visual language as a small set of shared,
> reusable primitives (a slot frame with an optional border, a tier-badge
> overlay, a panel/bar "chrome" skin) applied consistently across every
> panel (equip, backpack, bag, vault, trade, tooltips, minimap, menus) —
> not one-off per-panel styling. Make slot size, panel dimensions, and
> spacing derive from a small number of shared constants so resizing one
> (e.g. making icons bigger) doesn't silently misalign panels that were
> built against the old value with hardcoded literals — prefer live
> expressions over copied literals wherever the dependency crosses file/
> definition-order boundaries. Draw wall/obstacle outlines as a silhouette
> around each contiguous solid cluster (not a grid over every individual
> tile) so obstacles read as single objects.

---

## G. Vault → 10 chests + drag-and-drop

**What it is:** The vault (bank storage) grew from 7 chests to 10, and its
interaction model changed from click-only to full drag-and-drop, matching
the backpack/bag interaction model.

**How:** `game/items.py`'s `VAULT_CHEST_COUNT` 7 → 10 (`make_vault_room()`
was already generalized enough to need zero layout changes — verified all
10 chests place correctly). A new `("vault", idx)` slot kind was added to
the shared `_slot_at`/`_dragged_item`/`_inventory_mouse_down` drag-and-drop
plumbing; the old click-only `_vault_click` was split into
`_vault_click_extras` (close button + chest tabs — still click-only, since
those aren't item slots) and a new `_vault_mouse_up` (deposit/withdraw via
either drag or a plain click) in both `main.py` and `coop_client.py`.

**Real bug hit mid-implementation, worth recording as process lesson:** a
concurrently-running peer session's unrelated edit to the same file
(`main.py`) raced with this change and silently reverted the new
`_vault_click_extras`/`_vault_mouse_up` method definitions back to the old
single-method version. Caught immediately by a failing smoke test
(`AttributeError: no _vault_mouse_up`), re-applied, re-verified. **Lesson
recorded for future multi-session work on this codebase**: after any edit
to a file also touched by a concurrently-running peer session (`main.py`
and `coop_client.py` specifically, in this project's multi-session
workflow), re-grep for the exact methods/markers just added before
assuming they survived — the race is real, not hypothetical, and was
observed to actually happen here.

**Unity rebuild prompt:**
> Extend the bank/vault storage UI to support the same drag-and-drop
> interaction as the player's main inventory (not a separate click-only
> deposit/withdraw flow) — add the vault's slots as a recognized drag
> source/target alongside backpack and equipment slots in the shared
> inventory input-handling code, while keeping non-item-slot controls
> (close button, chest/tab navigation) as simple clicks.

---

## H. Biome terrain consolidation

**What it is:** The open-world biome regions were re-tuned to form fewer,
larger, more clearly-separated patches instead of many small scattered ones.

**How:** `game/world.py`'s `make_realm()` affinity-field noise frequency
lowered ~1.5x (0.006-0.02 → 0.004-0.0133) and `TIE_MARGIN` narrowed from 0.5
to 0.15. Tuned empirically, not by guessing: a standalone connected-
component analysis script measured that the old parameters produced 6-10
separate scattered patches per biome, and the new parameters consolidate to
roughly 2-4 bigger patches per biome (~2x average size). Per-biome
land-area fairness was checked too and stays in a similar range (worst-case
~0.20 vs ~0.24 before) — going lower than the chosen value was tested and
found to risk a biome getting near-zero territory on an unlucky seed, a
real degenerate case observed during tuning at 2-2.5x the frequency
reduction. Generation time unaffected (frequency doesn't change the number
of noise evaluations).

**Unity rebuild prompt:**
> When tuning a noise-based biome/region generator for "fewer, bigger,
> clearer regions," verify the change with an actual connected-component
> analysis across many seeds (count and size of resulting patches, and
> worst-case per-region land-area share) rather than eyeballing one or two
> generated maps — and push the tuning knob incrementally, checking at each
> step for the point where a region can start receiving near-zero territory
> on an unlucky seed, which is a real failure mode, not just an aesthetic
> tradeoff.

---

## I. Performance fixes

Four separate, independently-measured performance fixes landed in this
stream. Each includes a real before/after measurement, not just a
plausible-sounding change:

1. **Camera-rotation render cost**: `render_rotated_world()` in
   `game/world.py` was using an oversized buffer (1.5x the longer screen
   side instead of the mathematically sufficient diagonal) and calling
   `pygame.transform.rotate()` directly on that full-size buffer every
   rotated frame — measured at ~19ms/frame for the rotate call alone. Fixed
   by sizing the buffer to `hypot(W,H) * 1.05` (the true minimum with no
   empty corners) and rotating a `ROTATE_RENDER_SCALE = 0.5`-downscaled
   copy (`game/world.py:2011`), then scaling the rotated result back up
   with fast nearest-neighbor `pygame.transform.scale` — NOT `smoothscale`,
   which was measured to be slower than doing nothing extra; plain `scale`
   roughly halved the total cost. End-to-end: ~31ms/frame → ~16ms/frame.
2. **Mob dormancy**: `game/realm_sim.py`'s `ACTIVE_SIM_RADIUS = 1600`
   (realm_sim.py:157) — any enemy farther than this from every alive
   player is skipped entirely (no `Enemy.update()` call) each tick, in the
   open Realm only (bonus/dungeon rooms are small enough that every enemy
   there stays active). Measured: ~6.07ms/tick → ~0.32ms/tick for the
   enemy-update portion of `RealmSim.update()` with a full ~800-enemy
   continent — roughly a 95% reduction. Explicitly considered and rejected
   as a further step: lazy lair population (only creating a lair's enemies
   once a player first comes near it, instead of populating all ~200 lairs
   at realm creation) — the dormancy fix alone already eliminated the
   measured CPU cost, so lazy population was judged extra risk for an
   unmeasurable additional gain, deferred unless a future need specifically
   wants mobs to not exist at all far away, not just be inactive.
3. **Positional sound culling ("random sounds after joining realm" bug)**:
   a real, reported bug — `RealmSim.sound_events` never carried a position,
   so every mob hit/death/bark sound anywhere on the ~900x900-tile, ~800-
   enemy continent played at full volume regardless of distance. Fixed by
   changing `sound_events` tuples to `(kind, family, x, y)`
   (`main.py:52`/`coop_client.py:44` define the matching
   `SOUND_HEARING_RADIUS = 900` constant); both client consumption loops
   now distance-cull against that radius before playing
   (`main.py:1165`/`coop_client.py:1196`).
4. **Enemies no longer shoot through walls**: `Enemy.update()`'s firing
   check now also requires `tile_map.has_line_of_sight(...)` — the same
   line-of-sight helper already used for the aggro trigger, which had never
   actually been re-checked before each individual shot once an enemy was
   already aggro'd.

**Unity rebuild prompt:**
> For a large open-world enemy population: (1) skip full per-frame AI/physics
> updates for any enemy beyond a fixed "active simulation radius" of every
> player, measuring the actual before/after cost rather than assuming it
> helps; (2) attach a world position to every gameplay sound event and cull
> playback beyond a fixed hearing radius, rather than playing every sound
> in the world at full volume; (3) re-check line-of-sight before each
> individual ranged-enemy shot, not just once when it first notices the
> player, so it stops firing through walls if the player breaks sightline
> mid-fight; (4) for any camera-rotation or full-screen post-effect,
> profile the actual per-frame cost of the naive approach before optimizing,
> and prefer rendering at reduced resolution + fast upscale over a
> full-resolution expensive filter when the two are visually
> indistinguishable at gameplay scale.

---

## J. Other correctness bugs fixed in this stream

- **Bag window close button had no visible "X"** — it was drawing a blank
  colored square with no glyph; fixed by actually drawing the X.
- **Movement was always world-space, never rotated with the camera** — WASD
  input ignored the current camera rotation entirely, so rotating the view
  (Q/E) made movement feel backwards/sideways. Fixed: `Player.update()`
  gained a `cam_angle` parameter that rotates the raw input vector before
  use; `coop_client.py`'s `_send_input` performs the equivalent rotation
  client-side before sending input to the server (the server itself stays
  angle-agnostic — rotation is purely a client input/render concern,
  correctly).
- **Chat used to pause the entire single-player simulation.** `main.py`'s
  `update()` had `if self.chat_open: return`, freezing enemies/bullets/regen
  while typing. Removed; `Player.update()`/`_handle_firing` now just
  suppress the *local* player's own movement/firing input while typing
  (a `keys=None` convention), without pausing anything else — matching how
  co-op already worked (the server never paused for one client typing).

**Unity rebuild prompt:**
> When implementing camera rotation, always apply the same rotation to raw
> movement input before it's used — never let movement stay in world-space
> while the camera (and thus the player's visual sense of "forward") has
> rotated. When implementing a chat/text-input overlay, suppress only the
> local player's own movement/action input while typing — never pause the
> broader simulation (other entities, other players in multiplayer), so
> typing never becomes an accidental global pause button.

---

## K. Balance tweaks

- **Ranged attack range trimmed ~20%**: `_mk_bullet()`'s default `lifetime`
  reduced 3.0 → 2.4 seconds. This affects any bullet that doesn't pass an
  explicit lifetime override — most ranged player classes and ranged enemy
  patterns; melee classes already pass their own short explicit lifetimes
  and are unaffected. Per the user's own framing: "a little bit smaller
  only," not a large nerf.
- **Weather VFX particle count halved**: `game/weather.py`'s
  `MAX_PARTICLES` 70 → 35, applied uniformly to rain/snow/sand/ash.

**Unity rebuild prompt:**
> Expose projectile lifetime/range and ambient-weather particle density as
> tunable constants with sensible defaults, and treat "make X a little
> smaller/less" requests as small proportional adjustments (roughly
> 15-50%) rather than reworking the underlying system.

---

## L. Process notes for whoever picks this stream back up

- **`GAME_DATA.md`** exists at the repo root: a versioned snapshot of the
  audio sound-effects list, achievements list, and class base-stats table.
  **The user explicitly corrected an earlier assumption here: the game is
  still "v0.2," not "v0.3."** Do not bump the version number in any
  document on your own initiative — only note changes under the existing
  "still v0.2" section until a real version bump is explicitly requested.
- **`tools/export_audio.py`** renders every procedural sound effect to a
  real `.wav` file (not `.mp3` — no encoder was available in this
  environment without adding the project's first-ever non-pygame
  dependency; documented as a known limitation in `GAME_DATA.md`). Re-run it
  any time the audio synthesis code changes.
- **A real cross-session file-edit race was observed and is worth
  remembering** (see section G above for the specific incident): when
  multiple sessions edit the same shared files concurrently, a change can
  be silently reverted by a peer's overlapping edit. Always re-verify your
  own change survived (grep for the specific new symbol) after any edit to
  a file another concurrent session might also be touching, especially
  right after a cross-session coordination message arrives mid-edit.
- **Two items were reported by the user but explicitly deferred as
  "note only, don't touch code yet"** at the point this stream paused (the
  user was out of tokens): the mob-chatter-rate issue (see section A above)
  and a report that "the vault still doesn't have chests" — which
  contradicted what had just been verified in-session (10 chest tiles
  do place correctly, confirmed by direct grid inspection and an offscreen
  render). Three possible explanations were logged, none confirmed: a
  live-vs-offscreen rendering discrepancy, the user actually referring to
  the Nexus's vault-entrance tile (which was never meant to look like a
  chest — only the room's *interior* was), or a genuine bug no headless
  test caught. Resolution requires asking the user directly which they
  meant before guessing further.
- **A separate, never-root-caused report**: a "tiles reset" visual glitch
  while moving across sand/water. Static tile rendering was verified
  byte-identical across camera movement (a real pixel-comparison test, not
  assumption). Water's 3-frame ripple animation is intentional, not the
  bug. Leading (unconfirmed) theory: `WeatherFX.set_kind()` clears all
  particles instantly on any tile-type change, so crossing a biome boundary
  during normal movement could cause rapid weather-effect flicker that
  reads as "tiles resetting." If reproduced again, first establish: does it
  happen standing still or only moving, is it a color/texture flash or a
  full black frame, and does it happen in zones with no weather system
  (Nexus/Bazaar) — any of these would confirm or rule out the theory
  precisely before attempting a fix.

**Unity rebuild prompt:**
> Keep a single running "master tracking" document for any long,
> unstructured stream of small feature/bugfix requests spanning many
> sessions — record what shipped, what was explicitly deferred (and why),
> what's still an open bug report with no confirmed root cause, and any
> process lessons (like file-edit races between concurrent work) so a
> different session or teammate can resume without re-litigating settled
> questions or repeating already-ruled-out theories.
