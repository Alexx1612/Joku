# 40 - The Forge window, the Calendar in Options, the tagged Dictionary

"V0.2 final final fin" session, after doc 39.

## What you asked for

> "i want it so the forge system is a menu when you go to the smith inside the nexus there you can select what to do and
> forge so its more explicit and make the calendar be inside the menu options and make it much better for gui cause a
> part of it is transparent and also explain what each event does and also make the calendar menu movable and also
> remake the dictionary gui so it show a difference between mobs/pets/players from the actual tips on what to do (maybe
> with a tag like CREATURE, NEUTRAL MOB, TIP, MECHANIC etc)"

Decided with you before building:
- **The Forge:** F on Brother Hammerstein still opens his chat. Its first option is **"Open the Forge"**, and every recipe line has left the chat.
- **The Dictionary:** each category lists world content first, then a **"Tips & mechanics"** sub-heading. Multi-select tag chips sit at the top.

## 1. The Forge window (`game/forge_menu.py`)

### Logic
The logic is pure and needs no pygame.

**Catalog**
- `catalog(player)` returns `{tab: [recipe]}` for four tabs: `temper`, `reforge`, `fuse`, `stonework`.
- It is built from two functions that now take two new optional arguments:
  - `forge.forge_options(player, limit=None, include_blocked=True)`
  - `gems.stonework_options(player, limit=None, include_blocked=True)`
- `limit=None` means **no cap**. The old dialogue showed at most 3 forge and 4 stonework lines.
- The defaults (`limit=3/4`, blocked recipes left out) are unchanged, so older callers behave as before.

**Recipe fields**
- `ok`: whether you can make it now.
- `why`: why not, e.g. "Need 3 T7 gear items (you have 2)", "Need 2 Forge Ingots (you have 1)" or "No free socket on X - pry a stone out first".
- `needs = [(label, icon item, have, need)]`.
- Combine recipes also carry a `result` preview stone.

**What gets listed even if blocked**
- **Temper:** a temper group with one or more items whose line has a next tier.
- **Reforge:** every UT weapon that hasn't been reforged.
- **Fuse:** every shard rarity below mythic.
- **Stonework:**
  - every distinct stone in the backpack, for Set
  - every stone kind+grade below Perfect, for Combine
  - the last stone in the weapon, for Pry

**Sorting**
- Within each tab, recipes you can make come first.
- Stonework keeps the order Set, then Combine, then Pry, and each group gets its sub-header.

**`needs_confirm(r)`** asks for a second click on destructive work:
- **Pry**, because the stone shatters.
- Anything that eats **2 or more Forge Ingots**.
- Anything that eats an item of **T12 or higher** (Forge Ingots excluded, since the rule above covers them).

**`apply(player, r)`**
- It refuses any recipe with `ok=False` and changes nothing. This matters because blocked recipes carry partial ingredient lists.
- Otherwise it dispatches to `forge.apply_forge` or `gems.apply_stonework`.
- It fires `story.on_event("forge")` for temper, reforge and fuse, so Act III still counts. That call moved out of `dialogue.py`.
- It returns `{ok, msg, color, sfx, result, feed}`.

**`recipe_key(player, r)`**
- It returns `{kind, idx, names, label}`: the backpack slots the recipe consumes, their names and the recipe's label.
- This is how a client names a recipe. Items have no ids on the wire, only backpack indices.

**`apply_request(player, req)`** runs on the server:
- It rebuilds **its own** catalog and looks for the recipe whose key is identical.
- It refuses when:
  - nothing matches (stale or made-up indices, names or label, or a bad type): "That recipe isn't possible any more."
  - the match is blocked: it returns that recipe's `why`
  - the recipe needs a confirm and `confirmed` isn't set

### Window (`ForgeWindow`)

**Layout**
- It is modal. The backdrop is dimmed, the panel is an opaque `ui._ornate_panel` with a warm orange frame, and it shows an anvil icon and the title.
- The top right shows your **Forge Ingot count** and a close X.
- **Tabs:** Temper, Reforge (UT), Fuse Shards and Stonework. Each shows a `ready/total` count, green when anything is ready.
- **The left list** scrolls. Each row has:
  - the result icon (greyed out when blocked)
  - a two-line label
  - a **+ READY** or **x MISSING** chip, using colour plus a symbol plus text
- **The right detail panel** shows:
  - **Temper / Reforge / Fuse / Combine:**
    - a "uses" item card and a "you get" item card with an arrow between them (before → after)
    - the stat lines come from `ui.item_stat_lines`, which is now shared with the tooltip
  - **Set / Pry:**
    - "YOUR WEAPON" and its socket count rule
    - the sockets drawn as round slots holding the stones
    - for Set: the new stone **pulses** with a NEW label
    - for Pry: the stone that would shatter is **crossed out in red** with a SHATTERS label
    - next to the sockets: what the weapon's stones add **after** the action (Attuned x1.15 / Resonant x1.3 and the Resonant bonus, from `gems.RESONANT`)
  - **Ingredients:** an icon, the label and `have / need`. A shortfall is red and also gets a "SHORT" text tag.
  - **Forge Ingot cost**, and "Consumes: …" listing the exact items that will go.

**The FORGE button**
- **Disabled:** grey, with the reason in red underneath.
- **Destructive:** shows "Destructive: asks you to confirm."
  - The first press turns it into a red **CONFIRM**, with a note that it can't be undone.
  - The second press (click or Enter) forges. Esc cancels the confirm.
- **Forging:**
  - It plays `forge_hammer`, and the button shows **"Hammering..."** with a small hammer swinging onto an anvil (3 hits with sparks).
  - After `ANIM_TIME = 0.6 s` it applies the recipe.
  - A green result banner (the item's icon and the message) shows for 5 s, the success or stonework sound plays, and the VFX burst at Hammerstein.

**Keys**
- Up/Down (or W/S): move between recipes.
- Left/Right (A/D) and Tab / Shift+Tab: switch tabs.
- Enter or Space: FORGE.
- Esc: cancel the confirm, otherwise close.
- F: close.
- Mouse wheel: scroll.

### Wiring
**Dialogue (`game/dialogue.py`)**
- Hammerstein's root node leads with `OPEN_FORGE = "Open the Forge"`, keyed `("open_forge",)`.
- Choosing it sets `conv.open_forge = True` and ends the chat.
- The old `forge`, `gem` and `stonework` nodes are gone. His tempering, ingot and T14 topics stay.

**Single-player (`main.py`)**
- `self.forge`. `_dialogue_choose` opens the window.
- `_forge_apply` calls `forge_menu.apply`, which also pushes the feed line.
- `_forge_fx` plays the sound plus `forge_sparks` / `gem_forge` at the Anvil.
- The window gets events right after the Journal.
- Every modal check that blocks movement, firing and HUD hovers now includes it.
- It closes when you leave the Nexus.

**Server (`server.py`)**
- `_send_dialogue` adds `"open_forge"` to the `dialogue` message.
- The new action `forge_apply` → `_forge_apply` is only accepted in the **Nexus** and within **`FORGE_REACH = 180` px** of Hammerstein.
- It calls `apply_request`, pushes the feed line to the `story_feed`, and replies `{"type": "forge_result", ok, msg, color, sfx, result: item json}`.
- The backpack itself arrives in the next snapshot, as for every other inventory action.

**Co-op client (`coop_client.py`)**
- `open_forge` opens the window.
- `_forge_apply` re-finds the same recipe (by label) in the **current** `self.you`, which is rebuilt from every snapshot, and sends its key.
- The `NetLink` keeps a `forge_results` queue (`pop_forge_results`), which feeds `ForgeWindow.show_result`.
- While it waits, the button stays on "Hammering...". The client never forges by itself.

## 2. The Calendar (`game/calendar_ui.py`)
`CalendarWindow` is one per client. It replaces the old `calendar_open` flag.

**Opaque**
- It draws a solid backing rect under `ui._ornate_panel`, because the panel's rounded corners are transparent.
- Every pixel inside is opaque. The test fills the screen pure red and samples the whole window.

**Title bar**
- It has a drag grip, "Calendar", the hint "drag the title bar to move - K / Esc closes", and a close X.

**Movable**
- Pressing on the title bar starts the existing `PanelDrag` with the name `"calendar"`.
- The position is saved in `settings.panel_offsets["calendar"]`, with the other dragged panels, and clamped on-screen by `ui._offset_rect`.

**Layout** (960×640, clamped to the screen)
- Left side:
  - **filter chips:** Nights, Blood Moons only, Live events. Each is a checkbox plus a label, and the choice is saved in the new setting `calendar_filter`.
  - the "Now: …" line
  - the 7 night rows:
    - columns: Night, Falls in (countdown), Moon (phase icon + name), Sky (icon + name), Event
    - each event gets **its own icon**, so colour isn't the only cue
    - Blood Moon rows are red
  - 5 clickable live-event rows ("now - ends in" / "starts in")
- Right side: a **detail card** for the **hovered** row, or the **selected** one (row 0 by default).
  - For a night it gives the full explanation of that night's event, the weather and the moon.
  - For a live event it gives what the event does and when it runs.
- Bottom: a **legend** with the moon and blood moon icons, the 4 weather icons and the 6 event icons.

**The explanations come from the game's constants** (like `codex_extra`), so they can't drift.

| Function | Source |
|---|---|
| `event_text` | `night.FOG_LIGHT_MULT`, the Stalker spawn weight x2 (Fog), the new `night.HUNTER_HP_MULT` (2.2, was a literal), Lantern-Eaters x2 (Lanterns Out), the Midnight Market's 3 → 1 a tier higher, `LAMPLIGHTER_HP` / `_WAVE_EVERY` / `_HELP_RADIUS`, `BLOOD_HORDE_EVERY` / `_SIZE`, `BLOOD_MOON_NIGHT_SPEED`, `RUNE_SOURCE_MULT['blood_moon']`, `BLOOD_SURVIVOR_XP` |
| `weather_text` | `night_sky.CLOUD_DARK`, `WEATHER_LIGHT_MULT`, `LIGHTNING_EVERY`, the shooting-star chances |
| `moon_text` | % lit, and the full moon's `FULL_MOON_BLOOD_MULT` |
| `live_text` | `live_events.EVENTS` loot rolls / XP / Blood Moon chance multipliers and `EVENT_WINDOW` |

**Input**
- Clicks inside the window are consumed, along with Esc, Up/Down and the drag.
- **WASD still walks.** It stays non-modal, as before.

**Entry points**
- **Options → Journal → Calendar** is a new row after Quest Log and Dictionary, in both clients.
- **K** still toggles it.
- `ui.HELP_LINES` now reads "Calendar (nights, events): K / Options".

## 3. The Dictionary (`game/codex.py`, `game/journal.py`)

**Tags**
- `codex.TAGS` has 14 tags. Each maps a key to `(label, 3-letter badge, colour, icon)`:
  - CREATURE (skull), BOSS (crown), NIGHT MOB (moon), NEUTRAL (leaf), HERB (flower)
  - NPC (person), PET (paw), ITEM (bag), GEAR (sword), PLACE (pin)
  - DUNGEON (portal; this also covers portals), STORY (book), TIP (lightbulb), MECHANIC (cog)

**`codex.entry_tag(e)`** is the one place a tag is decided, from the id and the game data:

| Id | Tag |
|---|---|
| `enemy:*` | reads `ENEMY_KINDS`: neutral+unshootable → HERB if `herb`, else NEUTRAL; then boss → BOSS; `night_only` → NIGHT MOB; else CREATURE |
| `npc:*` | a person → NPC; a creature group → NEUTRAL |
| `pet:*` | PET |
| `item:ut:*` | GEAR |
| other `item:*` | ITEM |
| `portal:*`, `area:dungeon:*` | DUNGEON |
| other `area:*` | PLACE, with a small override map: `area:gear` and `area:heroic_trials` → MECHANIC, `area:dungeons` and `area:heroic_dungeons` → DUNGEON, `area:locals` → NPC, `area:water` → TIP |
| `story:*` | STORY |
| `help:*` | TIP if it's in the explicit `codex.TIP_IDS` (18 how-to pages), otherwise MECHANIC (22 rule pages) |

- New entries are tagged automatically.
- `entries()` stores `e["tag"]` and adds the tag's label to the search blob, so typing "mechanic" finds them.
- Sorting is now: category, then **world content before notes**, then title.

**Filtering:** `codex.filter_entries(query, cat, tags)`
- Chips **OR** together.
- Chips **AND** with the search.
- When a search or any chip is active, the list spans **every category**.
- `codex.is_note(e)` is true for TIP or MECHANIC.

**Window layout** (still 1080×680 at 1366×820)
- **"Show:" chip row** under the title:
  - an ALL chip, plus the 14 tag chips
  - each chip is a tinted fill, a border, the icon and the label
  - the picked chips are saved in the new setting `dict_tags`
  - clicking a category clears the chips, because categories and chips are two ways to browse
- **Left column:** search plus the 11 categories (`_cat_rect` kept).
- **List:**
  - each row has a 3-letter **tag badge** with its icon, then the title
  - world content comes first, then a gold **"TIPS & MECHANICS"** sub-heading row
  - the sub-heading can't be selected; Up/Down and clicks skip it
- **Detail, world content:**
  - the title, then a **tag chip** next to the category name
  - the sprite box, framed in the tag's colour
  - the stat grid
  - the "Where to find" map, unchanged
- **Detail, TIP / MECHANIC:** a lighter, warm **note card**:
  - a folded corner
  - a big lightbulb (TIP) or cog (MECHANIC) in a ring
  - the title and chip, plus "How-to advice" or "How the game works"
  - no stat grid; the text gets the whole card

**Search picks the best title match**
- Typing a name selects the entry whose title matches, even when it's a tip listed further down.
- So "fusion" selects *Pet fusion* even though the mythic pets that mention fusion are listed first.

## Tests
**New:** `tests/check_forge_menu.py`
- **Catalog:** no cap (6 temper groups and 5 stones all listed); blocked recipes have reasons and applying one changes nothing.
- **Every kind** works through `apply`, and Act III still counts.
- **Confirm rules and the window's keys:**
  - a cheap recipe forges on one press, after the hammering
  - T12 asks once, Esc cancels, and two Enters forge
- **Single-player:** chat → window, a click on FORGE, the feed line, every tab draws, and it closes outside the Nexus.
- **Server `forge_apply`** refuses:
  - stale indices
  - wrong names
  - a forged label
  - junk types
  - an unaffordable recipe
  - a missing confirm
  - a request made far from the Anvil or outside the Nexus

  It accepts the real request, and a repeat of the same request is stale.
- **Co-op round trip** through an in-process server:
  - the open_forge message opens the window
  - the client sends exactly one `forge_apply` and never forges locally
  - the `forge_result` shows the item
  - leaving the Nexus closes the window
- **Draws and fits** at 1366×820, 1920×1080 and 1280×720.

**Extended:** `check_danger_and_calendar`
- `check_calendar_window`:
  - opacity on a red screen
  - every event, weather, moon phase and live event is explained, with the real numbers
  - row click and Up/Down
  - WASD is not swallowed
  - a title-bar drag moves the window by exactly (60, 40), is saved, and clamps on-screen
  - the chips persist; Blood Moons only works, and turning Nights off turns Blood off
  - the close X and Esc both close it
- `check_calendar_in_options_menu`: the Options row sits after Quest Log / Dictionary in both clients, Esc closes the calendar before the quit prompt, and K still works.

**Extended:** `check_dictionary_complete` (`check_every_entry_is_tagged`)
- every entry has a tag, and `entry_tag` agrees with it
- creature entries carry creature tags
- every `help:` entry is TIP or MECHANIC, and `TIP_IDS` all exist
- all 14 tags are in use
- chip OR / AND behaviour
- notes come after world content in every category
- the window's chip clicks work and persist
- the sub-heading position
- everything fits at 1366×820

**Updated:**
- `check_tiers_and_forge` and `check_gem_forging` now go "Open the Forge", then `forge_menu`.
- `check_dialogue_and_sidequests` walks the chat past "Open the Forge".
- `check_quest_log_dictionary` covers the new world-first order and the sub-heading.
- The co-op `FakeLink` stubs got `pop_forge_results`.

## Research applied
**Crafting menus**
- The flow is list → detail/preview → confirm.
- Recipes are grouped by category (tabs, plus Set/Combine/Pry sub-headers).
- Each ingredient is shown next to its owned count, and shortages are red with a text tag.
- The button is disabled and **says what's missing** instead of failing silently.
- There is a two-step confirm for irreversible or expensive crafts, and one click for cheap ones.
- Sources:
  - [Opsive Crafting Menu docs](https://opsive.com/support/documentation/ultimate-inventory-system/ui/crafting-menu/)
  - [Village Smithy devlog](https://villagesmithydev.itch.io/village-smithy/devlog/1093657/village-smithy-devlog-1-crafting-begins)
  - [Skyrim crafting menu mod](https://nexusmods.com/skyrimspecialedition/mods/81409)
  - [RedM blacksmith menu](https://express-studios.tebex.io/package/blacksmith)
  - [Forge Master](https://tszhinw.itch.io/forge-master)

**Calendar readability**
- A compact list of what's next, with explicit countdowns, instead of a dense grid.
- Icons with contrast against the background.
- Details on demand: hover or click a row (RuneScape's calendar does this).
- A persistent event-type filter.
- Sources:
  - [RuneScape Calendar interface](https://runescape.wiki/w/Calendar_(interface))
  - [GameDev.net events/calendar UI WIP](https://gamedev.net/blogs/entry/1884656-v5-ui-wip-eventscalendar)
  - [Sims 4 calendar feedback](https://forums.ea.com/discussions/the-sims-4-feedback-en/%F0%9F%97%93%EF%B8%8F-please-let-us-globally-save-custom-calendars--holidays--ui-fixes/13569185)
  - [Stardew Valley scheduler](https://forums.stardewvalley.net/threads/stardew-valley-scheduler-a-free-browser-based-cyclic-calendar-planner.53087/latest)
  - [Stardew calendar overview](https://www.exitlag.com/blog/stardew-valley-calendar/)

**Codex / game UI**
- A small, consistent taxonomy (14 tags, one per entry).
- Glanceable badges.
- Colour **always paired** with an icon and a label, for colour-blind players.
- Filter chips plus search.
- Tips visually lighter than world content.
- Real design effort on supplementary screens.
- Sources:
  - [Game Developer: design axioms for game UIs](https://www.gamedeveloper.com/design/design-axioms-for-game-ui-s-part-i-data)
  - [Pixune](https://pixune.com/blog/game-ui-design/)
  - [Generalist Programmer](https://generalistprogrammer.com/tutorials/game-ui-design-best-practices)
  - [Virtuall](https://virtuall.pro/blog/game-ui-design-2f0f4)

**How other games split creatures from tips.** This was a quick extra search, and the results were thin, as expected.
- **Monster Hunter** keeps the monster list apart from the hunter's tips.
  - The original *Hunter Notebook* had separate "Monster List" and "Hunter's Tips" sections ([Monster Hunter 3 Hunter Notes](https://monsterhunterwiki.org/wiki/Monster_Hunter_3_Hunter_Notes)).
  - *Wilds*' Field Guide splits creatures into Large Monster, Small Monster, Endemic Life and Aquatic Life ([Deltia's Gaming](https://deltiasgaming.com/?p=154756)).
  - A monster's page holds its approach tips, weaknesses and drops, and they fill in as you learn them ([Destructoid](https://www.destructoid.com/?p=226373)).
  - This is the model for our creature cards: sprite, stats and where to find it. Our TIP / MECHANIC notes are the separate "tips" section.
- **Hollow Knight's Hunter's Journal** is creature-only. Entries fill in with kills (often 1 for a boss, 10-35 for common enemies), and lore and advice live elsewhere ([Hollow Knight Wiki](https://www.hollowknight.wiki/w/Hunter%27s_Journal_(Hollow_Knight))). This supports keeping advice out of the creature list.
- **Hades** has a single Codex with tabs per subject. One player's complaint about Hades II's thinner entries shows that players value rich per-entry detail ([Steam discussion](https://steamcommunity.com/app/1145350/discussions/0/4358998952353352252)).
- **Darkest Dungeon II** puts rules in a separate **glossary**: hold Ctrl for the token list, or open the Escape menu → Token Glossary. Enemy details come from hovering an enemy and pressing Alt ([Steam discussion](https://steamcommunity.com/app/1940340/discussions/0/3838801285234272157), [Pro Game Guides](https://progameguides.com/darkest-dungeon-2/darkest-dungeon-2-beginner-tips/)). That's the same split as our MECHANIC notes versus creature entries.

## Screenshots
Saved under `screenshots/2026-10-08/`, in `forge_menu/` (13 shots), `calendar_menu/` (9) and `dictionary_redesign/` (10), each with a `NOTES.md`.

Made by `tools/snap_ui_windows.py [forge|calendar|dictionary]`, which reuses `tools/take_snapshots.py`'s setup.
