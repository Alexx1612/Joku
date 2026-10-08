# Handoff prompt: Forge menu, Calendar in Options, Dictionary redesign

Paste everything below the line into a new Claude Code chat opened in `C:\Users\alexandru.mirea\PycharmProjects\ROTMG`.

---

You're continuing work on **Realm Reforged**, my Python 3.12 + pygame RotMG-style game. The repo is https://github.com/Alexx1612/Joku, local path `C:\Users\alexandru.mirea\PycharmProjects\ROTMG`, branch `main`. The last release is **v0.2** at commit `1a43ae8`; everything before it is pushed and released.

## My rules (follow all of them)
- Stay on **V0.2** unless I say otherwise.
- Run `python tests/run_all_checks.py` after every batch of changes. It currently has **83 scripts, all green**.
  - Two checks can flake on the random map or on timing: `check_areas_trees_bosses` and `check_big_islands`. If one fails, re-run it alone to confirm.
  - Never "fix" a timing budget by raising it. Windows 11 power throttling is handled by `tests/_timing.py`.
- **Look at screenshots** for any visual work. Render them headless (`SDL_VIDEODRIVER=dummy`), open them with the Read tool, and iterate until they look good.
- **Save screenshots in `screenshots/<YYYY-MM-DD>/<feature>/`**, each folder with a `NOTES.md` giving a one-line caption per shot. Also add a section to the day's `screenshots/<date>/NOTES.md` saying what was done. `tools/take_snapshots.py` is the reusable helper. `screenshots/` is untracked; don't commit it unless I say so.
- All art and music must be original. Procedural or grid art via scripts is fine.
- **Don't commit, push or release without my OK.** Local checkpoint commits after a green batch are fine.
- Releases must work on **Windows AND Linux/Ubuntu**. Pushing a `v*` tag runs GitHub Actions, which builds both and attaches them to the release.
  - To update v0.2: push `main`, then `git tag -f v0.2 <sha>` and `git push -f origin v0.2`, then watch the run with `gh run watch`.
- Keep the game's goofy tone in any text.
- Read `docs/HANDOFF-v0.2-final-final.md` and the docs index `docs/unity-rebuild/00-INDEX.md` (docs 31-39 cover the latest work).
- Write python helper scripts with the Write tool and run them; bash heredocs that contain apostrophes break.
- Update `README.md`, `GAME_DATA.md`, a new `docs/unity-rebuild/40-*.md` (plus its index row) and the handoff doc for everything you change.

## The task (my words)
"i want it so the forge system is a menu when you go to the smith inside the nexus there you can select what to do and forge so its more explicit and make the calendar be inside the menu options and make it much better for gui cause a part of it is transparent and also explain what each event does and also make the calendar menu movable and also remake the dictionary gui so it show a difference between mobs/pets/players from the actual tips on what to do (maybe with a tag like CREATURE, NEUTRAL MOB, TIP, MECHANIC etc)"

That breaks down into four things.

### 1. The Forge becomes a real menu at the smith (Brother Hammerstein, Nexus tavern)
**Today:** everything happens in his **dialogue tree**, as numbered options: temper, reforge, fuse Weapon Shards, and "Stonework" for gems (set, combine, pry). Key code:
- `game/forge.py`:
  - `forge_options(player, limit=3)`: temper / reforge / shard-fuse recipes, as dicts with `kind`, `use`, `ingots`, `result`, ...
  - `apply_forge(player, recipe)`, `temper_result`, `reforge_result`, `ingot_cost`
  - Temper takes any 3 gear items of the same tier and gives 1 of the next tier. T12+ costs Forge Ingots.
- `game/gems.py`:
  - `stonework_options(player, limit=4)` and `apply_stonework(player, opt)`
  - `SET_INGOTS`, `COMBINE_INGOTS`, `socket_count(weapon)` (1/2/3 sockets by tier; UT and Divine get 2)
  - `STONES`, `GRADES`, `RESONANT`
- `game/dialogue.py` (around lines 95-235): the Hammerstein nodes `("stonework",)` and `("forged",)`, which call `forge.forge_options` and `gems.stonework_options`. The options are capped at `MAX_OPTIONS`, so a player with many items can't even SEE every recipe.
- **Co-op:** the server owns the conversation (`server.py` `dialogue_choice` / `_send_dialogue`), so forging there is already authoritative. Keep it authoritative.
- **Visuals that exist:** the `gem_forge` VFX burst, the sounds `forge_hammer`, `forge_success`, `forge_fail`, `gem_set`, `gem_combine`, `gem_pry`, and `game/gem_art.py` for gem icons and the weapon glow.

**Wanted:** F on Hammerstein still opens his chat, but it gets a clear "Open the Forge" option (or the Forge opens straight away; ask me if unsure). The Forge is a dedicated window:
- **Tabs or sections:** Temper, Reforge (UT), Fuse Shards, Stonework (Set / Combine / Pry).
- **Left:** a scrollable list of every possible recipe. No 3-option cap.
- **Right:** a detail panel:
  - the result item's icon and tooltip-style stats, with a before → after comparison for tempering
  - the ingredients, each with its icon and an owned count. Missing ones show in red.
  - the Forge Ingot cost
  - for Stonework: the weapon's sockets drawn as slots with the stones in them, plus the Attuned / Resonant state and what it adds
- **A big FORGE button:**
  - It's disabled, with a reason, when you can't afford the recipe.
  - Destructive actions (Pry, which shatters the stone, and anything consuming T12+ items) get a confirm step.
  - On success: the anvil spark VFX and hammer sound, a short "hammering" animation (0.4-0.8 s), then the result appears.
- **Controls:** mouse plus keyboard (Up/Down, Enter, Esc closes).
- **Co-op:** the window is client-side UI that sends a new authoritative server action (e.g. `forge_apply {kind, ids}`) that re-validates and calls `apply_forge` / `apply_stonework`. Or it drives the dialogue choices; pick whichever is cleaner, but the server must stay the authority.
- **Research to apply** (crafting-menu best practice):
  - a recipe list → detail/preview → (quantity) → confirm flow
  - recipes grouped by category
  - each ingredient shown next to the owned count, shortages highlighted in red
  - the confirm button disabled (with what's missing) instead of failing silently
  - a two-step confirm for expensive or irreversible crafts and one click for cheap ones
  - test text size and contrast on a dark, warm palette

  Sources: [Opsive Crafting Menu docs](https://opsive.com/support/documentation/ultimate-inventory-system/ui/crafting-menu/), [Village Smithy devlog](https://villagesmithydev.itch.io/village-smithy/devlog/1093657/village-smithy-devlog-1-crafting-begins), [Skyrim crafting menu mod](https://nexusmods.com/skyrimspecialedition/mods/81409), [RedM blacksmith menu](https://express-studios.tebex.io/package/blacksmith), [Forge Master](https://tszhinw.itch.io/forge-master).

### 2. The Calendar: move it into the Options menu, make it opaque, explain events, make it movable
**Today:** `game/calendar_ui.py` `draw(surf, clock)` is opened with **K** in `main.py` and `coop_client.py` (`self.calendar_open`; Esc closes it).
- It's a `pygame.SRCALPHA` panel filled `(14, 14, 22, 238)`, so it's **slightly see-through**, and the world and HUD bleed through. I want it fully opaque, with a proper framed look like the other dock panels: `ui._ornate_panel`, `CHROME_GOLD`, the Quest Log / Dictionary window style in `game/journal.py`.
- Data comes from `RealmSim.forecast_view()` / `clock_info()["forecast"]` (7 nights: `[n, eta, phase, blood, weather, event]`) and `live_events.upcoming(n)`.
- Event labels live in `realm_sim.NIGHT_EVENT_LABELS`. The short hints are in `calendar_ui.EVENT_HINT`.

**Wanted:**
- **Options menu:** add a "Calendar" row in `game/options_menu.py` `build_rows(...)`. It's an action row in the "Journal" section next to Quest Log / Dictionary, and opens the calendar. Keep K as a shortcut. Update `ui.HELP_LINES` if needed; `check_settings` checks it.
- **Opaque window:** a solid background and a clear title bar with a close X.
- **Movable:** drag it by its title bar and remember its position. Reuse the existing draggable-panel system: `game/panel_drag.py` `PanelDrag`, `ui.PANEL_OFFSETS`, saved in settings (main.py `self.panel_drag`). Clamp it to the screen.
- **Explain what each event does:** a detail area, or clicking or hovering a night row, shows a full explanation of that night's event, weather and moon phase. For example:
  - The Fog: your light shrinks to x0.6 and there are twice the Shade Stalkers.
  - Hunter: a buffed Stalker tracks one player and drops bonus loot.
  - Lanterns Out: every lamp and window is dark.
  - Midnight Market: the Ghost Merchant trades 3 gear items for 1 a tier higher.
  - The Lamplighter: protect Old Wick (420 HP) until dawn and get the Light of RDV.
  - Blood Moon: hordes every 30 s, the Red Harvester, best loot, +400 XP.
  - Weather effects, e.g. a storm means lightning.
  - The live events too: Double Loot, Happy Hour (+50% XP), Blood Moon Week (Blood Moon chance x2.5), Two-for-One.

  Take the numbers from the constants (`game/night.py`, `game/night_sky.py`, `game/live_events.py`, `game/realm_sim.py`) the way `game/codex_extra.py` does. Optionally add a legend for the icons.
- **Research to apply** (calendar readability):
  - a compact list of what's next, with countdowns, beats a dense grid
  - give icons enough contrast against the background
  - details on demand (click a row → its description, like RuneScape's calendar)
  - let players filter event types and remember the filter
  - make time-to-event explicit

  Sources: [RuneScape Calendar interface](https://runescape.wiki/w/Calendar_(interface)), [GameDev.net events/calendar UI WIP](https://gamedev.net/blogs/entry/1884656-v5-ui-wip-eventscalendar), [Sims 4 calendar readability feedback](https://forums.ea.com/discussions/the-sims-4-feedback-en/%F0%9F%97%93%EF%B8%8F-please-let-us-globally-save-custom-calendars--holidays--ui-fixes/13569185), [Stardew Valley scheduler (countdowns, flagged events)](https://forums.stardewvalley.net/threads/stardew-valley-scheduler-a-free-browser-based-cyclic-calendar-planner.53087/latest), [Stardew calendar overview](https://www.exitlag.com/blog/stardew-valley-calendar/).

### 3. Remake the Dictionary GUI: tell creatures and characters apart from tips and mechanics
**Today:** `game/journal.py`:
- `Journal.open_dictionary`
- `_dict_rects`, `_draw_dictionary` (~line 591), `_draw_entry` (~line 658)
- `_cat_rect` (a vertical category list, `CAT_H = 30`) and `ROW_H = 26`

Its data comes from `game/codex.py` `entries()`. Each entry is a dict `{id, cat, title, sprite, stats, text, where}`.
- **Categories** (`codex.CATEGORIES`, 11): mobs, bosses, friendly, npcs, portals, areas, pets, items, gear, world, story.
- **Help/tip entries** have ids that start with `help:` and are mixed into the same lists as the creatures, which is what I don't like.
- `game/codex_extra.py` adds the Gear & Crafting and Night & World entries.
- `tests/check_dictionary_complete.py` checks that every monster, NPC and listed system has an entry.

**Wanted:**
- **Tags:** every entry gets a clear **type tag**, shown as a coloured chip or badge next to its title in the list AND in the detail view. Derive the tag from the id and data in one function (e.g. `codex.entry_tag(e)`) so new entries get tagged automatically. Suggested tags:

  | Tag | Covers |
  |---|---|
  | `CREATURE` | hostile mobs |
  | `BOSS` | bosses |
  | `NIGHT MOB` | `night_only` |
  | `NEUTRAL` / `WILDLIFE` | neutral, unshootable |
  | `HERB` | night herbs |
  | `NPC` | people |
  | `PET` | pets |
  | `ITEM` / `GEAR` | items |
  | `PLACE` | areas |
  | `DUNGEON` | portals and dungeons |
  | `STORY` | story acts |
  | `TIP` | how-to advice |
  | `MECHANIC` | game-system explanations (`help:*` that describe rules) |

  Decide TIP vs MECHANIC per entry; a small explicit map is fine.
- **Visual split:** mobs, pets, NPCs and players look clearly different from tips and mechanics. For example:
  - Creature and character entries get their sprite, stat block and "Found in" map links.
  - TIP and MECHANIC entries use a lighter "note card" style (an icon such as a lightbulb or gear, no stat grid) so they read as advice, not world content.
  - Within a category, list the creatures first, then a "Tips & mechanics" sub-heading. Or add a top-level filter.
- **Filter chips:** tag chips at the top (multi-select, with clear AND/OR behaviour) that work together with search. Remember the last filter in settings.
- **Accessibility:** use colour AND a text label or icon for each tag, never colour alone (colour-blind players).
- **Fit:** the Dictionary window must still fit on screen at 1366x820 (the current window) and in fullscreen. Keep search, Tab to the next category, Up/Down, the wheel and Esc working; `tests/check_quest_log_dictionary.py` covers them.
- **Research to apply:**
  - keep the tag taxonomy small and consistent
  - make information glanceable
  - pair colour with an icon and label
  - offer filter chips plus search
  - make tip entries visually lighter than world-content entries
  - put real design effort into supplementary screens

  Sources: [Game UI Database / design axioms (Game Developer)](https://www.gamedeveloper.com/design/design-axioms-for-game-ui-s-part-i-data), [Pixune: Game UI design principles](https://pixune.com/blog/game-ui-design/), [Generalist Programmer: game UI best practices](https://generalistprogrammer.com/tutorials/game-ui-design-best-practices), [Virtuall: game UI design principles](https://virtuall.pro/blog/game-ui-design-2f0f4).

  The research on codex tags specifically was thin. If you can, do a quick extra search on how Monster Hunter, Hades, Hollow Knight (Hunter's Journal) and Darkest Dungeon present creature vs. lore vs. tip entries, and cite it in doc 40.

### 4. Tests, docs, screenshots
- **New or updated tests:**
  - `tests/check_forge_menu.py`:
    - every recipe kind is listed and has no cap
    - unaffordable recipes are disabled with a reason
    - temper, reforge, fuse, set, combine and pry work through the menu
    - pry and T12+ need a confirm
    - co-op server action: authoritative, refuses invalid input
    - it draws at 1366x820
  - Extend `tests/check_danger_and_calendar.py`:
    - the Options row opens the calendar
    - the panel is opaque (sample pixels where the world used to show through)
    - dragging moves it and the position persists
    - every event and weather has an explanation
  - Extend `tests/check_dictionary_complete.py`:
    - every entry has a tag
    - creature entries carry creature-type tags
    - every `help:` entry is TIP or MECHANIC
    - filter chips filter correctly
  - Update anything else that breaks: `check_tiers_and_forge`, `check_gem_forging`, `check_weapon_shards`, `check_settings`, `check_quest_log_dictionary`.
- **Screenshots** in `screenshots/<today>/forge_menu/`, `calendar_menu/` and `dictionary_redesign/`, each with a `NOTES.md`. LOOK at every one and fix overlaps, transparency and clipping.
- **Docs:** `docs/unity-rebuild/40-forge-menu-calendar-dictionary.md` (with the research sources), its index row, README controls and features, GAME_DATA if numbers change, and `docs/HANDOFF-v0.2-final-final.md`.
- **Finish:** run the full suite until it's green, make a local checkpoint commit, then ask me before pushing and updating the v0.2 release.

## Useful facts about the codebase
- **Clients:**
  - Single-player is `main.py` (`Game`, states `STATE_NEXUS` / `STATE_REALM` / ...).
  - Co-op is `server.py` (authoritative, plus `game/realm_sim.py` `RealmSim`) and `coop_client.py`.
  - UI drawing lives in `game/ui.py`.
- **Window conventions:**
  - The dock is on the right: `ui._panel_block_x0()` is the play-area width, and `ui.dock_frame_rect()`.
  - Other windows to match: `game/journal.py` (the Quest Log, Quest Map and Dictionary) and the help overlay `ui.draw_help_overlay`.
  - Fonts are consolas; `ui._FONT_S`, `_FONT_M`, `_FONT_L`.
- **Options menu:** `game/options_menu.py`: `Row(kind, label, section, get/set/action)`, `build_rows`, `handle_key`, `handle_click`. `check_settings` checks the row order.
- **Settings:** `game/settings.py` `DEFAULTS`, `settings.get/change`. A new float key is clamped 0..1 automatically.
- **Admin commands:** `game/admin.py`, 63 commands. `/help` in chat lists them. Use them to test quickly, e.g.:
  - `/give`, `/gem ruby perfect 3`, `/shard all`, `/ingots 10`, `/tier 11`
  - `/forecast blood 2`, `/nightevent lamplighter`, `/time night`
- **Dock tabs:** Items / Bag 2 / Shards / Pet. Tab cycles them.
- **Keys:**

  | Key | Does |
  |---|---|
  | F | context action: talk, door, herb, gem vein, fish |
  | J / T | quest log, quest markers |
  | K | calendar |
  | M | map |
  | O | options |
