"""
Headless screenshots of the Forge window, the Calendar and the Dictionary (doc 40) into
screenshots/<YYYY-MM-DD>/{forge_menu,calendar_menu,dictionary_redesign}/, each folder with a
NOTES.md caption list. Reuses tools/take_snapshots.py's game setup.

Run with: python tools/snap_ui_windows.py [forge|calendar|dictionary ...]   (no args = all)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import take_snapshots as TS  # noqa: E402  (sets the headless env + temp save dirs)

import pygame  # noqa: E402
import main  # noqa: E402
from game import constants as C  # noqa: E402


class Shots:
    def __init__(self, folder):
        self.dir = os.path.join(TS.OUT, folder)
        os.makedirs(self.dir, exist_ok=True)
        self.notes = []

    def save(self, g, name, caption, draw=True):
        if draw:
            g.draw()
        pygame.image.save(g.screen, os.path.join(self.dir, name + ".png"))
        self.notes.append(f"- `{name}.png` - {caption}")

    def write(self, title):
        with open(os.path.join(self.dir, "NOTES.md"), "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n" + "\n".join(self.notes) + "\n")


def _settle(g, n=3):
    for _ in range(n):
        g.update(1 / 60)


def dictionary():
    sh = Shots("dictionary_redesign")
    g = TS._game()
    _settle(g)
    j = g.journal
    j.open_dictionary("enemy:goblin")
    sh.save(g, "01_mobs_creature", "Mobs: tag badges in the list, CREATURE chip by the title, sprite + stats + map")
    j.open_dictionary("enemy:red_harvester")
    sh.save(g, "02_boss", "A boss entry - BOSS tag, the crown icon")
    j._pick_category("world")
    sh.save(g, "03_world_subheading", "Night & World: world content first, then the TIPS & MECHANICS sub-heading")
    j.open_dictionary("help:blood_moon")
    sh.save(g, "04_mechanic_card", "A MECHANIC entry as a lighter note card with a cog, no stat grid")
    j.open_dictionary("help:stonework")
    sh.save(g, "05_tip_card", "A TIP entry as a note card with a lightbulb")
    j.toggle_tag("tip")
    sh.save(g, "06_chip_tip", "The TIP chip on: every how-to page across all categories")
    j.toggle_tag("boss")
    j.toggle_tag("night_mob")
    j.toggle_tag("tip")
    sh.save(g, "07_chips_or", "BOSS + NIGHT MOB chips: chips OR together")
    j._set_query("red")
    sh.save(g, "08_chips_and_search", "Chips AND search: 'red' within BOSS / NIGHT MOB")
    j._set_query("")
    j.toggle_tag(None)
    j.open_dictionary("npc:hammerstein")
    sh.save(g, "09_npc", "An NPC entry")
    j.open_dictionary("pet:" + next(iter(__import__("game.items", fromlist=["x"]).PET_KINDS)))
    sh.save(g, "10_pet", "A pet entry")
    j.close_all()
    sh.write("Dictionary redesign - tags, chips, note cards")


def _fullscreen(g, size=(1920, 1080)):
    g._resize_canvas(*size)


def _post(g, *events):
    for e in events:
        pygame.event.post(e)
    g.handle_events()


def calendar():
    from game import admin, calendar_ui, ui
    sh = Shots("calendar_menu")
    g = TS._game()
    g.realm_sim.day_time = 120  # bright midday: anything see-through would show the world
    _settle(g)
    admin.run(admin.SPCtx(g), "forecast blood 2")
    g.realm_sim._fc_key = None  # clock_info caches the calendar once a second
    ui.PANEL_OFFSETS.pop("calendar", None)
    # open it from the Options menu (the new Journal > Calendar row)
    g.help_open = True
    rows = g._menu_items()
    g.menu_selected = [r.label for r in rows].index("Calendar")
    sh.save(g, "01_options_row", "Options menu: the new 'Calendar' row under Journal (K still works)")
    rows[g.menu_selected].action()
    cal = g.calendar
    cal.sel = ("night", 0)
    sh.save(g, "02_opaque_window", "The Calendar over bright daylight - fully opaque, title bar, close X, detail card")
    cal.sel = ("night", 1)
    sh.save(g, "03_blood_moon_detail", "Night #2 selected: the BLOOD MOON explained with the real numbers")
    fc = g.realm_sim.clock_info()["forecast"]
    i = next((i for i, f in enumerate(fc) if f[4] in ("storm", "rain") and not f[3]), 2)
    cal.sel = ("night", i)
    sh.save(g, "04_weather_detail", f"Night #{fc[i][0]}: its event, {fc[i][4]} weather and moon explained")
    cal.sel = ("live", 0)
    sh.save(g, "05_live_event_detail", "A live event row: what it does and when it starts/ends")
    # drag by the title bar
    tb = calendar_ui.title_rect()
    start = (tb.x + 100, tb.centery)
    _post(g, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=start),
          pygame.event.Event(pygame.MOUSEMOTION, pos=(start[0] + 240, start[1] + 90), rel=(240, 90), buttons=(1, 0, 0)),
          pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(start[0] + 240, start[1] + 90)))
    cal.sel = ("night", 0)
    sh.save(g, "06_dragged", "Dragged by the title bar (position saved, clamped on-screen)")
    ui.PANEL_OFFSETS.pop("calendar", None)
    cal.filter = {"nights", "blood"}
    sh.save(g, "07_filter_blood_only", "Filter: Blood Moons only, live events hidden")
    cal.filter = {"nights", "live"}
    g.realm_sim.day_time = 300
    _settle(g)
    sh.save(g, "08_at_night", "At night (the time bar's countdown is 'dawn in')")
    _fullscreen(g)
    sh.save(g, "09_fullscreen_1920", "Fullscreen-size canvas (1920x1080)")
    sh.write("Calendar - opaque, movable, explained, in the Options menu")


def _weapons(cls, tier, n):
    from game import forge, items as I
    rows = I.WEAPONS[cls]
    i = next(i for i, r in enumerate(rows) if r[2] == tier)
    return [forge._build("weapon", cls, rows[i], i) for _ in range(n)]


def forge_shots():
    from game import items as I, gems as G, runes, forge_menu
    sh = Shots("forge_menu")
    g = TS._game()
    g.go_nexus()
    _settle(g)
    p = g.player
    anvil = next(n for n in g.nexus_npcs if n.npc_id == "hammerstein")
    p.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 44)
    p.backpack_size = 20
    p.weapon = _weapons("wizard", 11, 1)[0]
    p.weapon.gems = [["ruby", "regular"]]
    p.backpack = (_weapons("wizard", 8, 3) + _weapons("wizard", 12, 3) + _weapons("wizard", 5, 2)
                  + [I.make_forge_ingot(), I._random_ut("wizard")]
                  + [runes.make_rune("rare", "burn") for _ in range(3)] + [runes.make_rune("common", "keen")]
                  + [G.make_gem("ruby", "flawed") for _ in range(3)] + [G.make_gem("sapphire", "flawless")])
    _settle(g)
    # F on Hammerstein -> his chat with "Open the Forge"
    g._try_talk()
    sh.save(g, "01_chat_open_the_forge", "F on Brother Hammerstein: his chat now leads with 'Open the Forge'")
    g._dialogue_choose(0)
    fw = g.forge
    assert fw.is_open()
    fw.sel = 0
    sh.save(g, "02_temper_list", "Temper tab: every recipe, READY / MISSING chips, before -> after, ingredients")
    recs = fw.recipes(p)
    fw.sel = next(i for i, r in enumerate(recs) if not r["ok"])
    sh.save(g, "03_blocked_recipe", "A recipe you can't make yet: red counts, FORGE disabled with the reason")
    fw.sel = next(i for i, r in enumerate(recs) if r["ok"] and forge_menu.needs_confirm(r))
    sh.save(g, "04_t12_needs_confirm", "A T12 -> T13 temper eats rare stuff: FORGE warns it'll ask to confirm")
    fw.press_forge(p)
    sh.save(g, "05_confirm_step", "First click: CONFIRM - click / Enter again, Esc cancels")
    fw.press_forge(p)  # the second press confirms and starts hammering
    fw.update(0.25, p)
    sh.save(g, "06_hammering", "Hammering... (0.6 s animation with sparks before the result)")
    fw.update(0.5, p)
    sh.save(g, "07_result", "The result appears (and lands in the backpack); the list refreshes")
    fw.set_tab("reforge")
    sh.save(g, "08_reforge_ut", "Reforge (UT): needs 2 Forge Ingots - you have 1, so it's disabled")
    fw.set_tab("fuse")
    sh.save(g, "09_fuse_shards", "Fuse Shards: 3 rare -> 1 epic; the lone common shows what's missing")
    fw.set_tab("stonework")
    fw.sel = 0
    sh.save(g, "10_stonework_set", "Stonework / Set: the weapon's sockets with the new stone pulsing in")
    recs = fw.recipes(p)
    fw.sel = next(i for i, r in enumerate(recs) if r["kind"] == "combine")
    sh.save(g, "11_stonework_combine", "Stonework / Combine: 3 Flawed Rubies -> 1 Ruby")
    fw.sel = next(i for i, r in enumerate(recs) if r["kind"] == "pry")
    fw.press_forge(p)
    sh.save(g, "12_pry_confirm", "Stonework / Pry: the stone that shatters is crossed out; confirm step")
    fw.confirm = None
    _fullscreen(g)
    fw.set_tab("temper")
    sh.save(g, "13_fullscreen_1920", "Fullscreen-size canvas (1920x1080)")
    sh.write("The Forge window (Brother Hammerstein, Nexus tavern)")


def pulse():
    """The Blood Moon heartbeat: the same spot at the lub, the dub and the quiet between."""
    from game import realm_sim as rs
    sh = Shots("blood_moon_pulse")
    g = TS._game()
    sim = g.realm_sim
    from game import admin
    admin.run(admin.SPCtx(g), "bloodmoon")  # the real thing: starts a Blood Moon night now
    for _ in range(90):
        g.update(1 / 30)
    sim.enemies = []
    if hasattr(g, "_eyes"):
        g._eyes.level, g._eyes._was_night = 1.0, True
    period = 1.05
    frames = []
    for name, phase, cap in (("01_lub", 0.05, "the LUB - the vignette slams in, the red night swells"),
                             ("02_dub", 0.27, "the softer DUB right after"),
                             ("03_quiet", 0.65, "the quiet between beats - the red sinks back")):
        g._beat_t = phase * period - 1 / 60
        sh.save(g, name, f"Blood Moon heartbeat: {cap}")
        frames.append(g.screen.copy())
    strip = pygame.Surface((C.SCREEN_W // 2 * 3, C.SCREEN_H // 2))
    for i, f in enumerate(frames):
        strip.blit(pygame.transform.smoothscale(f, (C.SCREEN_W // 2, C.SCREEN_H // 2)), (i * C.SCREEN_W // 2, 0))
    pygame.image.save(strip, os.path.join(sh.dir, "04_strip.png"))
    sh.notes.append("- `04_strip.png` - the three moments side by side (lub / dub / quiet)")
    sh.write("Blood Moon heartbeat - the red night pulses instead of glowing")


def ux():
    """UX batches A + B (doc 41)."""
    from game import items as I, gems as G, runes, forge, settings, admin, ui, vfx, death_recap, binds
    from game.entities import Bag
    sh = Shots("ux_batches_a_b")
    g = TS._game()
    _settle(g)
    p = g.player
    # 1) comparison tooltip: hover a better staff in the backpack (Shift for the side-by-side)
    rows = I.WEAPONS["wizard"]
    i9 = next(i for i, r in enumerate(rows) if r[2] == 9)
    p.backpack = [forge._build("weapon", "wizard", rows[i9], i9), G.make_gem("ruby", "flawed"),
                  I.make_forge_ingot(), runes.make_rune("rare", "burn"), forge._build("weapon", "wizard", rows[2], 2)]
    r0 = ui.backpack_slot_rects(p)[0]
    pygame.mouse.set_pos(r0.center)
    g.draw()
    ui._tooltip(g.screen, r0.center, p.backpack[0])
    sh.save(g, "01_compare_tooltip", "Hovering a T9 staff: green ^ / red v against the equipped one", draw=False)
    # 2) loot beams + the loot filter
    sim = g.realm_sim
    base = p.pos + pygame.Vector2(120, -40)
    sim.ground_items = [Bag([I._random_ut("wizard")], base),
                        Bag([forge._build("weapon", "wizard", rows[12], 12)], base + pygame.Vector2(90, 30)),
                        Bag([forge._build("weapon", "wizard", rows[1], 1)], base + pygame.Vector2(-260, 60))]
    settings.change("loot_hide_below", 0)
    sh.save(g, "02_loot_beams", "Loot beams: pink over a UT, cyan over a T13; the plain T2 bag (left) has none")
    settings.change("loot_hide_below", 5)
    sh.save(g, "03_loot_filter_hides_junk", "'Hide gear-only bags below T5': the T2 bag is gone; rare ones always show")
    settings.change("loot_hide_below", 0)
    sim.ground_items = []
    # 3) the Options menu: two columns, Loot / Accessibility / Controls
    g.help_open = True
    items = g._menu_items()
    g.menu_selected = [r.label for r in items].index("Colour-blind palette")
    sh.save(g, "04_options_two_columns", "Options now flow into two columns: Loot, Accessibility, Key bindings...")
    g.help_open = False
    # 4) key bindings
    g._open_keybinds()
    binds.set_key("interact", pygame.K_g)
    g.keybinds.sel = 5
    g.keybinds.capturing = True
    sh.save(g, "05_key_bindings", "Key bindings: Talk moved to G (green = changed), Dash waiting for a key")
    g.keybinds.capturing = False
    g.keybinds.open = False
    binds.reset()
    # 5) accessibility: the same telegraphs in each palette, with outlined bullets
    from game.entities import _mk_bullet
    pos = p.pos
    zones = [dict(shape="circle", x=pos.x + 150, y=pos.y, r=70, length=0, width=0, ang=0, t=0.6, life=1, color=(255, 140, 40), dmg=5),
             dict(shape="line", x=pos.x - 250, y=pos.y + 60, r=0, length=260, width=26, ang=-15, t=0.5, life=1,
                  color=(235, 50, 50), dmg=5)]
    for mode, name in (("off", "06_palette_default"), ("deuteranopia", "07_palette_deutan"),
                       ("tritanopia", "08_palette_tritan")):
        settings.change("colorblind", mode)
        settings.change("bullet_outline", mode != "off")
        g.draw()
        vfx.draw_enemy_zones(g.screen, g.cam, zones)
        for k in range(6):
            _mk_bullet(pos + pygame.Vector2(-120 + k * 30, -110), pygame.Vector2(1, 0), 1, 5,
                       (230, 60, 40)).draw(g.screen, g.cam)
        sh.save(g, name, f"Telegraphs + enemy bullets, colour-blind palette: {mode}"
                + (" (bullets outlined)" if mode != "off" else ""), draw=False)
    settings.change("colorblind", "off")
    settings.change("bullet_outline", False)
    # 6) the Sort button + the Salvage tab
    g.go_nexus()
    _settle(g)
    anvil = next(n for n in g.nexus_npcs if n.npc_id == "hammerstein")
    p.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 44)
    p.backpack_size = 12
    p.backpack = [G.make_gem("ruby", "flawed"), forge._build("weapon", "wizard", rows[3], 3), I.make_forge_ingot(),
                  forge._build("weapon", "wizard", rows[9], 9), runes.make_rune("rare", "burn"),
                  forge._build("weapon", "wizard", rows[6], 6)]
    p.scrap = 7
    sh.save(g, "09_sort_button", "The backpack's new Sort button (above the grid, right)")
    p.sort_backpack()
    sh.save(g, "10_sorted", "After Sort: gear best-first, then stones, materials, shards")
    g.forge.open_window()
    g.forge.set_tab("salvage")
    sh.save(g, "11_salvage_tab", "Forge > Salvage: break gear into Scrap (7 now), 10 Scrap = 1 Forge Ingot")
    g.forge.sel = len(g.forge.recipes(p)) - 1
    sh.save(g, "12_smelt_blocked", "Smelt needs 10 Scrap - disabled with the reason")
    g.forge.close()
    # 7) the death recap
    p.take_damage(30, source=("Goblin", "Rock Throw", False))
    p.take_damage(40, source=("Ash Behemoth", "Magma Slam", True))
    p.take_damage(9999, pierce_armor=True, source=("Ash Behemoth", "Ember Rain", True))
    g.die()
    sh.save(g, "13_death_recap", "YOU DIED now says what did it: the killing blow, the last hits, damage by source, a tip")
    sh.write("UX batches A + B - comparison, death recap, loot, Options, key bindings, accessibility, salvage")


def zoom_shots():
    """Options > Display > Zoom at 125% (the default): what the window actually shows."""
    from game import view_scale, admin
    os.environ["RR_ZOOM"] = "1.25"
    sh = Shots("zoom_125")
    g = TS._game()
    _settle(g)

    def shot(name, caption):
        g.draw()
        pygame.image.save(g.screen, os.path.join(sh.dir, name + ".png"))
        sh.notes.append(f"- `{name}.png` - {caption}")

    shot("01_realm", "The Realm at 125%: the world (you, the mobs, the town) is bigger, the HUD and dock stay full size")
    os.environ["RR_ZOOM"] = "1.0"
    shot("01b_realm_100", "The same spot at 100% for comparison")
    os.environ["RR_ZOOM"] = "1.25"
    g.help_open = True
    shot("02_options", "The Options menu - HUD windows are never zoomed")
    g.help_open = False
    g.journal.open_dictionary("enemy:goblin")
    shot("03_dictionary", "The Dictionary still fits")
    g.journal.close_all()
    g._open_calendar()
    shot("04_calendar", "The Calendar still fits")
    g.calendar.close()
    g.go_nexus()
    _settle(g)
    g.forge.open_window()
    shot("05_forge", "The Forge still fits")
    g.forge.close()
    os.environ.pop("RR_ZOOM", None)
    sh.write("Zoom 125% - the world bigger, the HUD full size")


def world_shots():
    """Doc 42: the new hamlets and island outposts, and the island danger label."""
    from game.constants import TILE
    sh = Shots("world_settlements")
    g = TS._game()
    sim = g.realm_sim
    sim.day_time = 120
    for i, (biome, cx, cy) in enumerate(sim.hamlet_spots[:3]):
        g.player.pos = pygame.Vector2(cx * TILE, (cy + 6) * TILE)
        sim.enemies = [e for e in sim.enemies if e.pos.distance_to(g.player.pos) > 900]
        _settle(g, 4)
        sh.save(g, f"0{i + 1}_hamlet_{biome}", f"A new {biome} hamlet: two doored houses (shelters), a well, a campfire, "
                                               "lamps, a stall")
    for i, op in enumerate(sim.island_outposts[:3]):
        g.player.level = 20
        g.player.pos = pygame.Vector2(op["x"] * TILE, (op["y"] + 5) * TILE)
        sim.enemies = [e for e in sim.enemies if e.pos.distance_to(g.player.pos) > 700]
        _settle(g, 4)
        sh.save(g, f"1{i + 1}_island_outpost", "An island outpost (house, tent, campfire, lamps) - the minimap "
                                              "now says 'Isle: <tier>'")
    sim.day_time = 330
    _settle(g, 4)
    sim.day_time = 330
    sh.save(g, "20_outpost_at_night", "The same outpost at night: the lamps and the campfire light it, the house is "
                                      "a shelter")
    sh.write("More buildings: hamlets on the continent, outposts on the islands")


def art_shots():
    """Doc 43: the repainted mobs, bosses and players, in the game at real size (not a contact sheet)."""
    from game.entities import Enemy, Player
    sh = Shots("art_in_game")
    g = TS._game()
    sim = g.realm_sim
    sim.day_time = 120
    _settle(g, 2)
    base = pygame.Vector2(g.player.pos)
    groups = [
        ("01_wildlife", "Wildlife, repainted (idle / move strips)",
         ["forest_hare", "snow_fox", "deer", "elk", "mountain_goat", "tortoise", "tree_frog", "fire_beetle",
          "flamingo", "ice_penguin", "songbird", "owl", "mushroom_folk", "desert_lizard", "moonpetal"]),
        ("02_shard_island", "Shard-island mobs + mini-bosses, repainted",
         ["ember_wisp", "fury_shard", "rubble_crawler", "spite_spirit", "shard_sentinel", "echo_knight",
          "shattered_golem", "fracture_hound", "cinder_colossus", "ashreach_revenant", "thornrock_colossus"]),
        ("03_choir_island", "Choir-island mobs + mini-bosses, repainted",
         ["tide_wisp", "pearl_acolyte", "brine_crawler", "abyssal_chorister", "coral_sentinel", "kelp_stalker",
          "siren_wraith", "choir_sovereign", "coral_leviathan", "driftbell_matriarch", "abyssal_choirmaster"]),
        ("04_bosses", "The Demon Lord and the Mad God's forms, repainted",
         ["boss", "boss_phase2", "mad_god", "mad_god_phase2", "mad_god_unhinged", "mad_god_livid"]),
    ]
    for name, cap, kinds in groups:
        sim.enemies = []
        cols = 6 if len(kinds) > 6 else 3
        step = 120 if len(kinds) > 6 else 230
        for i, k in enumerate(kinds):
            try:
                e = Enemy(k, base + pygame.Vector2((i % cols - (cols - 1) / 2) * step,
                                                   -140 + (i // cols) * (step * 0.85)))
            except Exception as ex:  # an unknown kind: say so in the notes, keep going
                print("skip", k, ex)
                continue
            e.speed = 0
            e.aggro_range = 0
            sim.enemies.append(e)
        for _ in range(3):
            for e in sim.enemies:
                e.speed = 0
            _settle(g, 1)
        sh.save(g, name, cap)
    sim.enemies = []
    others = []
    for i, cls in enumerate(("warrior", "archer", "priest", "paladin", "rogue", "assassin", "necromancer")):
        o = Player(cls, cls.title(), pid=f"art_{cls}")
        o.pos = base + pygame.Vector2((i - 3) * 90, 110)
        o._is_moving = i % 2 == 0
        o._face_x = -1.0 if i % 3 == 0 else 1.0
        others.append(o)
    g._art_others = others
    orig = g.player.draw

    def draw_all(surf, cam, *a, **kw):
        for o in others:
            o.draw(surf, cam)
        return orig(surf, cam, *a, **kw)
    g.player.draw = draw_all
    g.player.note_shot((1.0, 0.0))
    _settle(g, 1)
    g.player.note_shot((1.0, 0.0))
    sh.save(g, "05_players", "All 8 classes in the world: walking ones step, idle ones breathe, the wizard shoots "
                             "(frames flip with facing)")
    g.player.draw = orig
    sh.write("The repainted art, in the game at real size")


def pins_shots():
    """Doc 42: 'Been there / Not yet' in the Quest Log, and your own map pins."""
    from game.constants import TILE
    sh = Shots("quest_places_and_pins")
    g = TS._game()
    _settle(g)
    p = g.player
    from game import story
    p.story = story.StoryProgress(story.ACT_TOUR)
    for key in ("tavern_town", "oasis_bazaar"):
        p.story.on_event("area", key)
    p.story.on_event("landmark", "forest")
    g.journal.open_quest_log()
    sh.save(g, "01_quest_log_been_there", "The Quest Log: each objective lists where it already counted you and "
                                          "where you haven't been yet")
    g.journal.close_all()
    for dx, dy in ((40, -10), (-60, 25), (15, 70)):
        p.map_pins.append([p.pos.x + dx * TILE, p.pos.y + dy * TILE, f"Pin {len(p.map_pins) + 1}"])
    sh.save(g, "02_pins_in_world", "Your pins in the world: edge arrows with the distance, the tracker list, the "
                                   "corner minimap")
    g.realm_minimap.full_map_open = True
    sh.save(g, "03_pins_full_map", "The full map (M): click anywhere to drop a pin, click a pin to remove it")
    g.realm_minimap.full_map_open = False
    g.journal.open_map(None, "Your pins")
    sh.save(g, "04_pins_quest_map", "The Quest Map shows them too (and a click places one)")
    g.journal.open_dictionary("enemy:goblin")
    sh.save(g, "05_pins_dictionary_map", "...and so does the Dictionary's little map (click it to pin)")
    g.journal.close_all()
    sh.write("Quest places + map pins")


def sweep_shots():
    """A visual sweep of every screen / zone / panel (the 'recheck all there is visually' pass)."""
    from game import realm_sim as rs, items as I
    sh = Shots("visual_sweep")
    g = TS._game()
    g.state = main.STATE_CLASS_SELECT
    sh.save(g, "01_class_select", "Class select")
    g.state = main.STATE_REALM
    _settle(g)
    sh.save(g, "02_realm_day", "The Realm by day (Tavern Town)")
    g.right_panel_mode = "bag2"
    sh.save(g, "03_dock_bag2", "Dock: Bag 2")
    g.right_panel_mode = "shards"
    sh.save(g, "04_dock_shards", "Dock: Shards")
    g.right_panel_mode = "inventory"
    g.realm_sim.day_time = rs.NIGHT_START + 60
    _settle(g, 4)
    g.realm_sim.day_time = rs.NIGHT_START + 60
    if hasattr(g, "_eyes"):
        g._eyes.level, g._eyes._was_night = 1.0, True
    sh.save(g, "05_realm_night", "The Realm at night")
    g.realm_sim.day_time = 120
    g.go_nexus()
    _settle(g, 4)
    sh.save(g, "06_nexus", "The Nexus")
    g.echo_shop_open = True
    sh.save(g, "07_echo_shop", "The Echo Keeper's shop")
    g.echo_shop_open = False
    try:
        g.enter_vault_room()
        _settle(g, 3)
        sh.save(g, "08_vault_room", "The Vault room")
    except Exception as e:
        sh.notes.append(f"- (vault room failed: {e})")
    try:
        from game import admin
        g.go_nexus()
        admin.run(admin.SPCtx(g), "goto bazaar")
        _settle(g, 3)
        sh.save(g, "09_bazaar", "The Bazaar")
        g.go_nexus()
        admin.run(admin.SPCtx(g), "dungeon frozen_crypt medium")
        _settle(g, 6)
        sh.save(g, "10_dungeon", "A dungeon (Frozen Crypt, Medium)")
    except Exception as e:
        sh.notes.append(f"- (bazaar / dungeon failed: {e})")
    g.player.take_damage(9999, pierce_armor=True, source=("Frost Wraith", "Ice Lance", True))
    g.die()
    sh.save(g, "11_death", "The death screen with its recap")
    sh.write("Visual sweep - every screen")


def run(which):
    if "art" in which:
        art_shots()
    if "sweep" in which:
        sweep_shots()
    if "pins" in which:
        pins_shots()
    if "world" in which:
        world_shots()
    if "zoom" in which:
        zoom_shots()
    if "ux" in which:
        ux()
    if "pulse" in which:
        pulse()
    if "forge" in which:
        forge_shots()
    if "calendar" in which:
        calendar()
    if "dictionary" in which:
        dictionary()


if __name__ == "__main__":
    run(sys.argv[1:] or ["forge", "calendar", "dictionary"])
