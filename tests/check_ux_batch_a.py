"""
UX batch A (doc 41): gear comparison tooltips, the death recap, the loot filter / auto-loot /
loot beams, and the Options menu flowing into two columns when it gets tall.

Run with: python tests/check_ux_batch_a.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import accounts, characters, achievements, items as I
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_ux_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_ux_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_ux_ach_")
I.VAULT_DIR = tempfile.mkdtemp(prefix="rr_ux_vault_")

from game import settings
settings.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(prefix="rr_ux_set_"), "settings.json")

from game import ui, forge, gems as G, runes, death_recap, loot_filter, audio, options_menu
from game import constants as C
from game.entities import Player, Enemy, Bag, _mk_bullet

audio.play_theme = lambda *a, **k: None


def _weapon(tier, cls="wizard"):
    rows = I.WEAPONS[cls]
    i = next(i for i, r in enumerate(rows) if r[2] == tier)
    return forge._build("weapon", cls, rows[i], i)


def _ring(tier):
    r = next(r for r in I.RINGS if r[1] == tier)
    return I.Item(r[0], I.SLOT_RING, tier, "ring", stat_bonus=dict(r[2]))


def check_compare_tooltips():
    p = Player("wizard", "Cmp", pid="c")
    p.weapon = _weapon(5)
    better, worse = _weapon(9), _weapon(2)
    up = ui.compare_lines(better, p.weapon)
    assert up and up[0][0].startswith("^") and "avg damage" in up[0][0] and up[0][1] == ui.UP_COL, up
    down = ui.compare_lines(worse, p.weapon)
    assert down[0][0].startswith("v") and down[0][1] == ui.DOWN_COL, down
    # an empty slot is always an upgrade; the equipped item itself says so
    assert ui.compare_lines(_ring(4), None)[0][0].startswith("^ Nothing equipped")
    assert ui.compare_lines(p.weapon, p.weapon) == [("(equipped)", ui.SAME_COL)]
    # stats compare key by key; consumables never compare
    p.ring = _ring(3)
    lines = ui.compare_lines(_ring(8), p.ring)
    keys = set(_ring(8).stat_bonus) | set(p.ring.stat_bonus)
    assert lines and all(any(k.upper() in t for k in keys) for t, _c in lines), lines
    assert all(c == (ui.UP_COL if t.startswith("^") else ui.DOWN_COL) for t, c in lines)
    assert ui.compare_lines(I.make_forge_ingot(), p.weapon) == []
    # a weapon with stones set: swapping it away warns you
    p.weapon.gems = [["ruby", "regular"]]
    assert any("loses 1 set stone" in t for t, _c in ui.compare_lines(_weapon(6), p.weapon))
    # every tooltip path draws with the comparison (and the Shift side-by-side) without errors
    ui.COMPARE_PLAYER = p
    ui._tooltip(screen, (600, 400), better)
    ui._tooltip(screen, (5, 5), _ring(8))  # clamps on-screen
    ui.COMPARE_PLAYER = None
    ui._tooltip(screen, (600, 400), better)
    print("check_compare_tooltips: PASSED")


def check_death_recap():
    p = Player("wizard", "Recap", pid="r")
    assert death_recap.build(p) is None  # nothing hit you: no recap (and nothing crashes)
    p.hp = p.hp_max = 100
    p.take_damage(10, source=("Goblin", "Rock Throw", False))
    p.take_damage(10, source=("Goblin", "Rock Throw", False))
    p.take_damage(15)  # an untagged hit still logs
    p.take_damage(500, pierce_armor=True, source=("Ash Behemoth", "Magma Slam", True))
    assert not p.alive
    r = death_recap.build(p)
    assert r["killer"] == "Ash Behemoth" and r["attack"] == "Magma Slam" and r["tele"], r
    assert r["last"][0]["who"] == "Ash Behemoth" and len(r["last"]) == 4
    assert r["by_source"][0][0] == "Ash Behemoth" and "telegraphed" in r["tip"]
    import json
    json.dumps(r)  # rides in the co-op snapshot
    # the log is bounded
    q = Player("wizard", "Long", pid="l")
    q.hp = q.hp_max = 10 ** 6
    for i in range(50):
        q.take_damage(1, pierce_armor=True, source=(f"M{i}", "x", False))
    assert len(q.hit_log) == Player.HIT_LOG_LEN
    # real enemies tag their hits: a bullet carries (who, move, telegraphed)
    e = Enemy("goblin", (0, 0))
    info = e.hit_info()
    assert info[0] == "Goblin" and info[1] == "Plain shot"
    assert e.hit_info(contact=True)[1].startswith("Body slam")
    b = _mk_bullet((0, 0), pygame.Vector2(1, 0), 1, 5, (255, 0, 0))
    assert b.src_info is None
    # the sim passes a bullet's info through to the player it hits
    from game.realm_sim import RealmSim
    sim = RealmSim()
    v = Player("wizard", "Victim", pid="v")
    v.pos = sim.spawn_point()
    v.hp = v.hp_max = 1000
    shot = _mk_bullet(v.pos, pygame.Vector2(1, 0), 0.01, 30, (255, 0, 0))
    shot.src_info = ("Lich", "Death Ring", True)
    sim.bullets = [shot]
    sim._resolve_bullet_hits({"v": v})
    assert v.hit_log and v.hit_log[-1]["who"] == "Lich" and v.hit_log[-1]["tele"], v.hit_log
    # single-player: die() keeps the recap and the death screen draws it
    import main
    g = main.Game()
    g.player_name = "RecapSP"
    g.start_run("wizard")
    g.player.take_damage(9999, pierce_armor=True, source=("Mad God", "Red Nova", True))
    g.die()
    assert g.death_info["recap"]["killer"] == "Mad God"
    g.draw()
    rr = death_recap.draw(screen, g.death_info["recap"], ui.death_screen_button_rect().bottom + 14,
                          C.SCREEN_W // 2, ui._FONT_S, ui._FONT_M)
    assert screen.get_rect().contains(rr), rr
    print("check_death_recap: PASSED")


def check_loot_filter_and_auto_loot():
    settings.change("loot_hide_below", 7)
    junk = Bag([_weapon(3), _ring(4)], (0, 0))
    mixed = Bag([_weapon(3), I.make_forge_ingot()], (0, 0))
    good = Bag([_weapon(9)], (0, 0))
    rare = Bag([_weapon(2), I._random_ut("wizard")], (0, 0))
    assert loot_filter.hidden(junk) and not loot_filter.hidden(mixed) and not loot_filter.hidden(good)
    assert not loot_filter.hidden(rare), "anything rare always shows"
    assert loot_filter.summary(rare.items)[2] == "ut"
    assert loot_filter.visible_bags([junk, good]) == [good]
    # the co-op ghost bag carries the same facts
    import coop_client
    ghost = coop_client.GhostBag(junk.net_state())
    assert loot_filter.hidden(ghost) and ghost.top == 4 and ghost.gear_only
    settings.change("loot_hide_below", 0)
    assert not loot_filter.hidden(junk)
    # beams draw for rare bags only (and never crash on ghosts)
    loot_filter.draw_beam(screen, lambda p: (int(p[0]) + 300, int(p[1]) + 300), rare, 0.5)
    loot_filter.draw_beam(screen, lambda p: (300, 300), coop_client.GhostBag(rare.net_state()), 0.5)
    # auto-loot: only the small stuff, only your own bag, only when close
    p = Player("wizard", "Auto", pid="a")
    p.pos = pygame.Vector2(100, 100)
    p.backpack = []
    p.auto_loot = True
    potion = I.make_forge_ingot()
    gem = G.make_gem("ruby", "flawed")
    shard = runes.make_rune("rare", "burn")
    sword = _weapon(8)
    mine = Bag([sword, potion, gem, shard], (110, 100), owner_pid="a")
    theirs = Bag([I.make_forge_ingot()], (100, 110), owner_pid="someone_else")
    far = Bag([G.make_gem("topaz", "flawed")], (400, 400), owner_pid="a")
    bags = [mine, theirs, far]
    events = []
    got = loot_filter.auto_loot(p, bags, events)
    assert {id(x) for x in got} == {id(potion), id(gem), id(shard)}, [x.name for x in got]
    assert mine.items == [sword] and len(theirs.items) == 1 and len(far.items) == 1
    assert len(events) == 3
    p.auto_loot = False
    assert loot_filter.auto_loot(p, [far], []) == []
    # the sim does it every tick for players who opted in (single-player and the co-op server)
    from game.realm_sim import RealmSim
    sim = RealmSim()
    q = Player("wizard", "Walker", pid="w")
    q.pos = sim.spawn_point()
    q.auto_loot = True
    q.backpack = []
    sim.ground_items.append(Bag([I.make_forge_ingot()], q.pos, owner_pid="w"))
    sim.update(1 / 30, {"w": q})
    assert any(it.shape == "ingot" for it in q.backpack), [it.name for it in q.backpack]
    print("check_loot_filter_and_auto_loot: PASSED")


def check_options_menu_fits_in_two_columns():
    rows = options_menu.build_rows(lambda: False, lambda v: None, lambda: False, lambda: None, lambda: None,
                                   lambda: None, full_map=(lambda: False, lambda: None),
                                   leave=("Abandon run", lambda: None),
                                   journal=[("Quest Log", lambda: None), ("Dictionary", lambda: None),
                                            ("Calendar", lambda: None)])
    labels = [r.label for r in rows]
    assert "Auto-loot potions / shards / gems" in labels and "Light beams on rare drops" in labels
    for size in ((1366, 820), (1280, 720), (1920, 1080)):
        C.SCREEN_W, C.SCREEN_H = size
        rects = ui.help_menu_item_rects(rows)
        x, y, w, h, *_ = ui._help_panel_geometry(rows)
        panel = pygame.Rect(x, y, w, h)
        assert pygame.Rect(0, 0, *size).contains(panel), (size, panel)
        for i, a in enumerate(rects):
            assert panel.contains(a), (size, labels[i])
            for b in rects[i + 1:]:
                assert not a.colliderect(b), (size, labels[i])
        surf = pygame.Surface(size)
        ui.draw_help_overlay(surf, rows, 0, (0, 0))
        # every row is still clickable where it's drawn
        hide = labels.index("Hide gear-only bags below")
        before = settings.get("loot_hide_below")
        options_menu.handle_click(rows, rects[hide].center)
        assert settings.get("loot_hide_below") != before
        settings.change("loot_hide_below", 0)
    C.SCREEN_W, C.SCREEN_H = 1366, 820
    print("check_options_menu_fits_in_two_columns: PASSED")


if __name__ == "__main__":
    check_compare_tooltips()
    check_death_recap()
    check_loot_filter_and_auto_loot()
    check_options_menu_fits_in_two_columns()
    print("\nPASSED: UX batch A checks all green.")
