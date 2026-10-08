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


def run(which):
    if "forge" in which:
        forge_shots()
    if "calendar" in which:
        calendar()
    if "dictionary" in which:
        dictionary()


if __name__ == "__main__":
    run(sys.argv[1:] or ["forge", "calendar", "dictionary"])
