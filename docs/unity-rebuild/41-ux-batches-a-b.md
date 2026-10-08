# 41 - UX batches A + B: comparison, death recap, loot, salvage, key bindings, accessibility

"V0.2 final final fin" session, after doc 40.

You asked for 10 UX and gameplay ideas, then chose to build batches A and B. Mid-session you also asked for the Blood Moon's red screen to pulse rather than glow. Batch C is still open: waystones, pings and waypoints, first-hour tips, and the Bounty Board.

## Batch A

### 1. Gear comparison tooltips (`game/ui.py`)
- **Every item tooltip** gets a "vs equipped:" block. This covers backpack, Bag 2, bags, vault, trade, ground and inspect.
  - `ui.COMPARE_PLAYER` is set by each client at the top of `draw()`.
- `ui.compare_lines(item, equipped)` returns green `^` for better and red `v` for worse, per:
  - average damage
  - socket count
  - lost set stones
  - gained or lost proc
  - ability power and MP cost (lower is better)
  - each stat
- An empty slot shows "^ Nothing equipped in this slot". The equipped item itself shows "(equipped)".
- **Hold Shift:** the equipped item's own tooltip appears beside it, headed "EQUIPPED".
- The Forge's "You get" card shows the same lines.

### 2. The death recap (`game/death_recap.py`)
- `Player.take_damage(..., source=(who, what, telegraphed))` keeps the last 12 hits in `Player.hit_log`.
- Every source now tags itself:
  - **Enemy bullets:** a new `Bullet.src_info` slot.
    - It's set from `Enemy.hit_info()`, which reports the move the enemy is firing (`Enemy._cur_move`, set in `_fire_move`). A pattern shot reads "Plain shot".
    - Split bullets inherit it.
  - **Ground zones:** `zone["info"]`, also used by a zone's burst bullets.
  - **Contact hits:** "Body slam (contact)".
  - **Ashlands embers:** tagged as well.
- `build()` returns a JSON-safe dict, stored in `death_info["recap"]` by single-player `die()` and by the co-op server.
- `draw()` shows a panel under YOU DIED:
  - "Killed by X - Attack (N dmg)"
  - whether it was telegraphed
  - the last 5 hits
  - damage by source (bars)
  - one tip: contact, embers, telegraphed, mobbed, or generic
- The Graveyard was deferred, as planned.

### 3. Loot filter, auto-loot and beams (`game/loot_filter.py`)
The new **Options → Loot** section has three settings:
- **Auto-loot** (`auto_loot`, default on):
  - Walking within 40 px of **your own** bag pulls potions, temp potions, materials (Forge Ingots), gems, dungeon shards and Weapon Shards into the backpack (overflowing into Bag 2).
  - Gear is never auto-picked.
  - It runs in `RealmSim.update`, so it's authoritative in co-op. The client sends `auto_loot` with its `input` messages.
- **Hide gear-only bags below T*n*** (`loot_hide_below`: Off / T3 / T5 / T7 / T9 / T11):
  - Such bags aren't drawn and right-click skips them.
  - The co-op `open_bag` action carries the choice, so the server skips them too.
  - Anything rare always shows.
  - `Bag.net_state` now carries `top`, `gear_only` and `rare` for co-op ghosts.
- **Light beams on rare drops** (`loot_beams`): a pulsing column over bags holding:
  - UT (pink)
  - Divine (gold)
  - T12+ (cyan)

### The Options menu flows into two columns
- **Why:** with Loot, Accessibility and Controls it was taller than the screen.
- **How:** `ui._help_panel_geometry` now places whole sections, and moves the next section to a second column (`_OPT_COL_STEP`) when the first would overflow.
- Layout entries carry their column, and `help_menu_item_rects` follows them.
- **A bug fixed on the way:** the selected row's highlight was drawn with alpha straight onto the SRCALPHA panel. That replaced the pixels instead of blending, so the world showed through the highlighted row. It's now blended through a temporary surface.

## Batch B

### 9. Salvage, Smelt, Sort and Stash
- **Forge → Salvage** (a new 5th tab):
  - break a gear item into Forge Scrap: `scrap_value` = max(1, (tier + 1) // 2)
  - UT and Divine items can't be salvaged
  - **Smelt** turns 10 Scrap into 1 Forge Ingot (`forge.SCRAP_PER_INGOT`)
  - salvaging T9+ or a weapon with stones set needs the confirm click
  - Scrap is a per-character counter (`Player.scrap`), saved in `full_state` and shown in the Forge header
  - co-op goes through the same `forge_apply` → `apply_request` path
- **Sort** button: above the backpack grid, at the right of the Items tab.
  - `Player.sort_backpack()` orders gear best-first, then potions, eggs, stones, materials and shards. It's stable.
  - Co-op uses the `sort_backpack` action.
- **"Stash mats"** button in an open vault chest:
  - `items.stash_materials` moves every material, gem and shard from the backpack into that chest's empty slots.
  - Co-op uses the `vault_stash` action.

### 4. Key rebinding (`game/binds.py`)
- **Options → Controls → Key bindings...** opens a window listing 19 actions.
  - Enter or a click rebinds; you then press a key, or Esc to cancel.
  - A key already used by another action swaps the two.
  - Changed keys show in green. R or the button resets everything.
  - Esc, Enter, F11, Backspace and 1-8 can't be bound.
- **How it works without rewriting the input code:**
  - The clients pass every gameplay KEYDOWN/KEYUP through `binds.translate_event`, which turns a bound key into its action's **default** key.
  - A default key whose action moved elsewhere becomes `K_UNKNOWN`.
  - Held keys (WASD, Q/E) read through `binds.Pressed()`.
  - Arrow keys always move.
- The Options screen's Controls list uses `binds.help_lines()`, so it shows your real keys.
- Bindings are saved in `settings["keys"]`.

### 10. Accessibility (`game/access.py`)
The new **Options → Accessibility** section:
- **Colour-blind palette** (Off / Deutan / Protan / Tritan):
  - telegraphs and enemy bullets get their hue remapped, with brightness kept
  - Deutan / Protan: red → magenta, orange → yellow, green → blue
  - Tritan: blue → teal, yellow → pink
- **Outline enemy bullets:** a dark ring and a pale rim, drawn **over** the bullet's glow (drawn under it, the glow hid it).
- **Telegraph strength:** the telegraph alpha multiplied by x0.5 to x1.5.
- **Text size:** Normal or Large (+2 px on the HUD's small and medium fonts, rebuilt in `settings.apply`). The Options panel still fits at 1280×720.
- **Reduce flashing:**
  - lightning is a soft 0.3 glow with no flicker
  - the Blood Moon heartbeat is x0.35
  - the last-moment telegraph blink becomes steady

## The Blood Moon heartbeat (your request)
- `ui.heartbeat_shape(phase)` gives a sharp "lub", a softer "dub" just after, then quiet.
- The red vignette now follows that shape instead of a single fade.
- The **whole red night throbs with it**: `lighting.ambient_color` lifts the Blood Moon ambient by up to +34% and deepens the red on each beat, through `lighting.GRADE["pulse"]`. Both clients set it from `_night_pulse`.
- It used to read as one constant red glow.
- See `screenshots/2026-10-08/blood_moon_pulse/04_strip.png` for the lub, dub and quiet frames side by side.

## Tests
- **`tests/check_ux_batch_a.py`:**
  - comparison lines, and every tooltip draws
  - the recap from tagged hits
  - the log is bounded
  - a bullet's `src_info` reaches the player through the sim
  - single-player `die()` stores the recap and the panel fits on screen
  - the filter (including on co-op ghosts) and beams
  - auto-loot takes only the small stuff, only from your own bag, only when close, and the sim does it every tick
  - the two-column Options menu at three sizes
- **`tests/check_ux_batch_b.py`:**
  - salvage and smelt, including scrap round-tripping through `full_state` and the server path
  - Sort ordering, and the Sort button in-game
  - `stash_materials`, including a full chest
  - rebinding:
    - translate, swap, reserved keys, `Pressed`
    - in-game, a rebound Interact opens the chat and F doesn't
    - the window's Enter → key flow, R resets, Esc closes, and it fits
  - accessibility:
    - the palette changes reds and oranges differently and leaves whites alone
    - telegraph strength
    - every mode draws
    - the outline rim is visible
    - reduced lightning
    - text size
  - the full Options menu fits at three sizes in both text sizes
- **`check_night_horror`:** `_night_sim(blood=True)` now pins tonight's forecast dice. The Blood Moon chance is capped at 50%, so "chance = 1.0" alone was a coin flip that depended on earlier RNG use.

## Screenshots
`screenshots/2026-10-08/ux_batches_a_b/` (13 shots) and `blood_moon_pulse/` (4), made with `python tools/snap_ui_windows.py ux pulse`.
