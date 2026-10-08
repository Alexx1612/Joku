"""
UX batch B (doc 41): Salvage + Smelt at the Forge, the backpack's Sort button, "Stash mats" in a
vault chest, key rebinding (game/binds.py) and the accessibility options (game/access.py).

Run with: python tests/check_ux_batch_b.py
"""
import json
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
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_uxb_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_uxb_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_uxb_ach_")
I.VAULT_DIR = tempfile.mkdtemp(prefix="rr_uxb_vault_")

from game import settings
settings.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(prefix="rr_uxb_set_"), "settings.json")

from game import forge, forge_menu, gems as G, runes, binds, access, ui, options_menu, audio, vfx
from game import constants as C
from game.entities import Player, _mk_bullet

audio.play_theme = lambda *a, **k: None


def _weapon(tier, cls="wizard"):
    rows = I.WEAPONS[cls]
    i = next(i for i, r in enumerate(rows) if r[2] == tier)
    return forge._build("weapon", cls, rows[i], i)


def check_salvage_and_smelt():
    p = Player("wizard", "Scrapper", pid="s")
    p.backpack = [_weapon(3), _weapon(10), I._random_ut("wizard"), I.make_forge_ingot()]
    cat = forge_menu.catalog(p)["salvage"]
    sal = [r for r in cat if r["kind"] == "salvage"]
    assert len(sal) == 2, [r["label"] for r in sal]  # UT and materials are never salvaged
    assert forge.scrap_value(_weapon(3)) == 2 and forge.scrap_value(_weapon(10)) == 5
    smelt = next(r for r in cat if r["kind"] == "smelt")
    assert not smelt["ok"] and "Need 10 Forge Scrap" in smelt["why"]
    low = next(r for r in sal if r["use"][0].tier == 3)
    high = next(r for r in sal if r["use"][0].tier == 10)
    assert not forge_menu.needs_confirm(low) and forge_menu.needs_confirm(high)
    res = forge_menu.apply(p, low)
    assert res["ok"] and p.scrap == 2 and len(p.backpack) == 3
    p.scrap = 12
    smelt = next(r for r in forge_menu.catalog(p)["salvage"] if r["kind"] == "smelt")
    res = forge_menu.apply(p, smelt)
    assert res["ok"] and p.scrap == 2 and sum(1 for it in p.backpack if it.shape == "ingot") == 2
    # scrap is saved with the character and survives the co-op snapshot
    q = Player.from_full_state(json.loads(json.dumps(p.full_state())))
    assert q.scrap == 2
    # the server applies it through the same authoritative path
    import server

    class Sock:
        def __init__(self):
            self.msgs = []

        def sendall(self, data):
            self.msgs += [json.loads(l) for l in data.decode().splitlines() if l.strip()]

    state = server.ServerState()
    me = Player("wizard", "CoopScrap", pid="c0")
    me.backpack = [_weapon(5)]
    sock = Sock()
    s = server.Session("c0", sock, me)
    state.sessions["c0"] = s
    s.zone = server.ZONE_NEXUS
    anvil = next(n for n in state.nexus_npcs if n.npc_id == "hammerstein")
    me.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 40)
    r = next(r for r in forge_menu.catalog(me)["salvage"] if r["kind"] == "salvage")
    server._apply_action(state, s, dict({"action": "forge_apply"}, **forge_menu.recipe_key(me, r)))
    assert sock.msgs[-1]["ok"] and me.scrap == 3 and not me.backpack
    # the Salvage tab draws (with and without anything to salvage)
    fw = forge_menu.ForgeWindow()
    fw.open_window()
    fw.set_tab("salvage")
    fw.draw(screen, p)
    fw.draw(screen, me)
    print("check_salvage_and_smelt: PASSED")


def check_sort_and_stash():
    p = Player("wizard", "Tidy", pid="t")
    gem = G.make_gem("ruby", "flawed")
    ing = I.make_forge_ingot()
    shard = runes.make_rune("rare", "burn")
    w3, w9 = _weapon(3), _weapon(9)
    p.backpack = [gem, w3, ing, shard, w9]
    p.sort_backpack()
    assert p.backpack[:2] == [w9, w3], [it.name for it in p.backpack]
    assert p.backpack.index(gem) < p.backpack.index(ing) < p.backpack.index(shard)
    vault = [None] * (I.VAULT_CHEST_SIZE * 2)
    vault[I.VAULT_CHEST_SIZE] = w3  # chest 2 has one thing in it already
    n = I.stash_materials(p.backpack, vault, 1)
    assert n == 3 and p.backpack == [w9, w3] and vault[I.VAULT_CHEST_SIZE] is w3
    assert {id(x) for x in vault[I.VAULT_CHEST_SIZE + 1:I.VAULT_CHEST_SIZE + 4]} == {id(gem), id(ing), id(shard)}
    # a full chest stops cleanly
    full = [w3] * I.VAULT_CHEST_SIZE
    p.backpack = [G.make_gem("topaz", "flawed")]
    assert I.stash_materials(p.backpack, full, 0) == 0 and len(p.backpack) == 1
    # the Sort button sits in the gap above the backpack and works in single-player
    import main
    g = main.Game()
    g.player_name = "SortSP"
    g.start_run("wizard")
    g.go_nexus()
    g.player.backpack = [G.make_gem("ruby", "flawed"), _weapon(2), _weapon(7)]
    sb = ui.sort_button_rect(g.player)
    first = ui.backpack_slot_rects(g.player)[0]
    assert sb.bottom <= first.y and not any(sb.colliderect(r) for r, _m in ui.panel_tab_rects())
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=sb.center))
    g.handle_events()
    assert [it.tier for it in g.player.backpack][:2] == [7, 2], [it.name for it in g.player.backpack]
    g.draw()
    print("check_sort_and_stash: PASSED")


def check_key_rebinding():
    binds.reset()
    assert binds.to_default(pygame.K_f) == pygame.K_f and binds.to_default(pygame.K_z) == pygame.K_z
    other = binds.set_key("interact", pygame.K_g)
    assert other is None and binds.bound("interact") == pygame.K_g
    assert binds.to_default(pygame.K_g) == pygame.K_f, "G now does what F did"
    assert binds.to_default(pygame.K_f) == pygame.K_UNKNOWN, "F no longer interacts"
    # a used key swaps
    other = binds.set_key("dash", pygame.K_g)
    assert other == "interact" and binds.bound("interact") == pygame.K_LSHIFT and binds.bound("dash") == pygame.K_g
    try:
        binds.set_key("ability", pygame.K_ESCAPE)
        raise AssertionError("Esc must not be bindable")
    except ValueError:
        pass
    assert settings.get("keys") == {"interact": pygame.K_LSHIFT, "dash": pygame.K_g}
    # held keys: Move up on I
    binds.set_key("move_up", pygame.K_i)

    class Keys(dict):
        def __getitem__(self, k):
            return self.get(k, False)

        def __len__(self):
            return 512
    pressed = binds.Pressed(Keys({pygame.K_i: True}))
    assert pressed[pygame.K_w] and not pressed[pygame.K_UP]
    assert binds.Pressed(Keys({pygame.K_UP: True}))[pygame.K_UP], "arrows always move"
    lines = dict(binds.help_lines())
    assert lines["Move"].startswith("I") and lines["Dash / roll"] == "G"
    # the real game: with Interact on Shift, Shift talks to Hammerstein, F doesn't
    import main
    g = main.Game()
    g.player_name = "BindSP"
    g.start_run("wizard")
    g.go_nexus()
    anvil = next(n for n in g.nexus_npcs if n.npc_id == "hammerstein")
    g.player.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 40)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0, unicode="f"))
    g.handle_events()
    assert g.dialogue is None
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LSHIFT, mod=0, unicode=""))
    g.handle_events()
    assert g.dialogue is not None
    g.dialogue = None
    # the window: open from Options, rebind with Enter + a key, reset with R
    labels = [r.label for r in g._menu_items()]
    g._menu_items()[labels.index("Key bindings...")].action()
    assert g.keybinds.open
    kw = g.keybinds
    kw.sel = [a for a, _l, _k in binds.ACTIONS].index("map")
    for k in (pygame.K_RETURN, pygame.K_n):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))
        g.handle_events()
    assert binds.bound("map") == pygame.K_n and "Full map" in kw.msg
    g.draw()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, mod=0, unicode="r"))
    g.handle_events()
    assert settings.get("keys") == {} and binds.bound("interact") == pygame.K_f
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    g.handle_events()
    assert not kw.open and not g.quit_confirm_open
    # the window fits
    for size in ((1366, 820), (1280, 720)):
        C.SCREEN_W, C.SCREEN_H = size
        r = kw.rects()
        assert pygame.Rect(0, 0, *size).contains(r["win"]) and all(r["win"].contains(x) for x in r["rows"])
    C.SCREEN_W, C.SCREEN_H = 1366, 820
    print("check_key_rebinding: PASSED")


def check_accessibility():
    red, orange, white = (235, 60, 50), (255, 150, 40), (240, 240, 240)
    assert access.color(red) == red  # off by default
    for mode in ("deuteranopia", "protanopia"):
        settings.change("colorblind", mode)
        r2, o2 = access.color(red), access.color(orange)
        assert r2 != red and o2 != orange and r2 != o2 and access.color(white) == white, (mode, r2, o2)
        assert r2[2] > 120, "reds turn magenta (lots of blue) - distinct from the yellowed oranges"
    settings.change("colorblind", "tritanopia")
    assert access.color((60, 120, 255)) != (60, 120, 255)
    settings.change("colorblind", "off")
    settings.change("tele_strength", 1.0)
    assert access.tele_alpha(100) == 150
    settings.change("tele_strength", 0.0)
    assert access.tele_alpha(100) == 50
    settings.change("tele_strength", 0.5)
    # everything draws in every mode
    zones = [dict(shape="circle", x=300, y=300, r=60, length=0, width=0, ang=0, t=0.9, life=1.0,
                  color=orange, dmg=5),
             dict(shape="line", x=300, y=300, r=0, length=200, width=20, ang=30, t=0.5, life=1.0,
                  color=red, dmg=5)]
    b = _mk_bullet((400, 400), pygame.Vector2(1, 0), 1, 5, red)
    for mode in ("off", "deuteranopia", "tritanopia"):
        settings.change("colorblind", mode)
        settings.change("bullet_outline", mode != "off")
        settings.change("reduce_flashing", mode != "off")
        vfx.draw_enemy_zones(screen, lambda p: (int(p[0]), int(p[1])), zones)
        b.draw(screen, lambda p: (int(p[0]), int(p[1])))
        ui.draw_blood_pulse(screen, 0.8)
    # the outline really draws a pale rim
    screen.fill((0, 0, 0))
    b.draw(screen, lambda p: (int(p[0]), int(p[1])))
    assert any(screen.get_at((400 + dx, 400))[:3] == (245, 245, 250) for dx in range(b.radius, b.radius + 7))
    # reduced flashing: lightning is a soft glow with no flicker
    from game.sky_fx import SkyFX
    fx = SkyFX()
    fx.update(0.016, {"bolt": None})
    fx.update(0.016, {"bolt": [1, 0, 0]})
    assert fx.flash <= 0.31 and fx._flick == 0
    settings.change("reduce_flashing", False)
    fx2 = SkyFX()
    fx2.update(0.016, {"bolt": None})
    fx2.update(0.016, {"bolt": [1, 0, 0]})
    assert fx2.flash > 0.9
    # text size rebuilds the HUD fonts
    settings.change("text_size", "large")
    assert ui._FONT_S.get_height() >= 16
    settings.change("text_size", "normal")
    assert ui._FONT_S.get_height() <= 15
    settings.change("colorblind", "off")
    settings.change("bullet_outline", False)
    print("check_accessibility: PASSED")


def check_full_options_menu_fits():
    import main
    g = main.Game()
    g.player_name = "MenuSP"
    g.start_run("wizard")
    rows = g._menu_items()
    labels = [r.label for r in rows]
    for want in ("Key bindings...", "Colour-blind palette", "Telegraph strength", "Reduce flashing",
                 "Auto-loot potions / shards / gems"):
        assert want in labels, want
    for text_size in ("normal", "large"):
        settings.change("text_size", text_size)
        for size in ((1366, 820), (1280, 720), (1920, 1080)):
            C.SCREEN_W, C.SCREEN_H = size
            x, y, w, h, *_ = ui._help_panel_geometry(rows)
            assert pygame.Rect(0, 0, *size).contains(pygame.Rect(x, y, w, h)), (text_size, size, (x, y, w, h))
            rects = ui.help_menu_item_rects(rows)
            for i, a in enumerate(rects):
                for bb in rects[i + 1:]:
                    assert not a.colliderect(bb), (size, labels[i])
            ui.draw_help_overlay(pygame.Surface(size), rows, 0, (0, 0))
    settings.change("text_size", "normal")
    C.SCREEN_W, C.SCREEN_H = 1366, 820
    print("check_full_options_menu_fits: PASSED")


if __name__ == "__main__":
    check_salvage_and_smelt()
    check_sort_and_stash()
    check_key_rebinding()
    check_accessibility()
    check_full_options_menu_fits()
    print("\nPASSED: UX batch B checks all green.")
