"""
Batch 15 Phase 2 (fixes & UI) regression checks:
  2.1 pets and abilities never hurt friendly wildlife; spell power x2.5 / heals x1.5;
      every ability has its own spell look (vfx styles) that dispatches cleanly
  2.2 mob flavor lines only reach chat within earshot (single-player + server snapshot)
  2.3 Esc closes the open window first, then asks, and Esc in the prompt quits
  2.4 chat: cursor/partial selection/history, log selection WITHOUT chat mode,
      right-click a name in the log, /msg across zones via the server
  2.5 the vault room's 12 chests open one at a time as bag-style windows + persist
  2.6 HUD: clock + minimap span the dock width and everything still fits

Run with: .venv\\Scripts\\python.exe tests\\check_phase2_fixes.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("RR_EVENT_ROTATION", "off")
os.environ.setdefault("RR_SETTINGS_PATH", os.path.join(tempfile.mkdtemp(prefix="rr_p2_set_"), "settings.json"))

import pygame
pygame.init()
screen = pygame.display.set_mode((1366, 820))

from game import achievements, items, characters, accounts
achievements._DIR = tempfile.mkdtemp(prefix="rr_p2_ach_")
items.VAULT_DIR = tempfile.mkdtemp(prefix="rr_p2_vault_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_p2_char_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_p2_acc_")

from game import constants as C, ui, vfx, minimap, options_menu, vault, clipboard
from game.chat_input import ChatInput, LogSelection
from game.entities import Player, Pet, Enemy
from game.items import ABILITIES, ability_power, Item, SLOT_WEAPON, VAULT_CHEST_COUNT, VAULT_CHEST_SIZE
from game import realm_sim as rs

SHOT_DIR = os.environ.get("RR_SHOT_DIR")


def _key(key, mod=0, uni=""):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=uni)


def _shot(surf, name):
    if SHOT_DIR:
        pygame.image.save(surf, os.path.join(SHOT_DIR, name))


def _sword(name):
    return Item(name, SLOT_WEAPON, 3, "sword", min_dmg=1, max_dmg=2)


# ------------------------------------------------------------------ 2.1
def check_pets_and_spells_spare_wildlife():
    sim = rs.RealmSim(bonus=True, theme="cave", difficulty_name="Easy")
    caster = Player("wizard", "Caster", pid="c1")
    caster.pos = pygame.Vector2(sim.spawn_point())
    deer = Enemy("deer", caster.pos + pygame.Vector2(40, 0))
    foe = Enemy("goblin", caster.pos + pygame.Vector2(-40, 0))
    sim.enemies = [deer, foe]
    deer_hp = deer.hp
    for effect in ("nova", "chain", "drain", "freeze"):
        sim._impact_ability_effect({"effect": effect, "pos": pygame.Vector2(caster.pos), "magnitude": 5,
                                    "caster": caster, "radius": 200, "style": "ruin"})
    assert deer.alive and deer.hp == deer_hp, "spells must never hurt friendly wildlife"
    assert foe.hp < foe.hp_max, "spells still hit real enemies"

    pet = Pet("imp_pup", caster.pos)
    bullets = []
    pet.update(1 / 30, caster, [deer], bullets)
    assert not bullets, "a pet must not shoot at friendly wildlife"
    pet.abilities["attack"]["cd"] = 0
    pet.update(1 / 30, caster, [deer, foe], bullets)
    assert bullets, "a pet still attacks real enemies"
    print("check_pets_and_spells_spare_wildlife: PASSED")


def check_spell_power_and_styles():
    by_name = {a[0]: a for cls in ABILITIES.values() for a in cls}
    ruin = Item("Orb of Ruin", "ability", 5, "orb", effect="nova", magnitude=by_name["Orb of Ruin"][4])
    assert ability_power(ruin) == round(40 * 2.5) == 100
    heal = Item("Tome of Rebirth", "ability", 9, "tome", effect="heal", magnitude=55)
    assert ability_power(heal) == round(55 * 1.5)
    haste = Item("Rally Horn", "ability", 1, "horn", effect="haste", magnitude=6)
    assert ability_power(haste) == 6, "haste durations are unchanged"
    # every ability has its own look, and each look dispatches + draws cleanly
    assert set(by_name) <= set(vfx.ABILITY_STYLES), set(by_name) - set(vfx.ABILITY_STYLES)
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    cam = lambda p: (int(p[0]), int(p[1]))
    styles = sorted(set(vfx.ABILITY_STYLES.values()))
    for i, style in enumerate(styles):
        surf.fill((22, 26, 22))
        vfx._particles.clear(); vfx._rings.clear(); vfx._shapes.clear()
        vfx.dispatch([(f"ab_{style}", 683, 420, (255, 255, 255), 540, 380)])
        assert vfx._shapes or vfx._particles or vfx._rings, style
        vfx.update(0.12)
        vfx.draw(surf, cam)
        if SHOT_DIR and i < 24:
            _shot(surf, f"p2_spell_{style}.png")
    print(f"check_spell_power_and_styles: PASSED ({len(styles)} spell looks)")


# ------------------------------------------------------------------ 2.2
def check_mob_speech_earshot():
    events = [("deer", "near", 100.0, 100.0), ("deer", "far", 5000.0, 5000.0)]
    heard = rs.audible_mob_speech(events, pygame.Vector2(120, 90))
    assert heard == [("deer", "near")], heard
    assert rs.audible_mob_speech([("old", "no pos")], (0, 0)) == [("old", "no pos")]
    # the co-op server filters per listener
    import server
    src = open(server.__file__, encoding="utf-8").read()
    assert "audible_mob_speech(sim.mob_speech_events, p_pos)" in src
    import main
    msrc = open(main.__file__, encoding="utf-8").read()
    assert "audible_mob_speech(sim.mob_speech_events, self.player.pos)" in msrc
    print("check_mob_speech_earshot: PASSED")


# ------------------------------------------------------------------ 2.3
def check_esc_chain_and_quit_prompt():
    esc = _key(pygame.K_ESCAPE)
    assert options_menu.quit_confirm_verdict(esc) is True, "Esc in the prompt = quit"
    assert options_menu.quit_confirm_verdict(_key(pygame.K_n)) is False
    assert options_menu.quit_confirm_verdict(_key(pygame.K_RETURN)) is True
    import main
    g = main.Game()
    g.player = Player("wizard", "EscTester", pid="sp")
    g.player_name = "EscTester"
    g.state = main.STATE_NEXUS
    g.player.pos = g.nexus_map.center_world_pos()
    g.help_open = True
    pygame.event.post(esc)
    assert g.handle_events() is not False and not g.help_open and not g.quit_confirm_open, \
        "first Esc closes the open window, not the game"
    pygame.event.post(esc)
    assert g.handle_events() is not False and g.quit_confirm_open, "Esc with nothing open asks first"
    g.draw()
    _shot(g.screen, "p2_quit_prompt.png")
    pygame.event.post(esc)
    assert g.handle_events() is False, "Esc again in the prompt quits"
    print("check_esc_chain_and_quit_prompt: PASSED")
    return g


# ------------------------------------------------------------------ 2.4
def check_chat_input_editing():
    ci = ChatInput()
    for ch in "hello world":
        ci.handle_key(_key(0, uni=ch))
    assert ci.text == "hello world" and ci.cursor == 11
    for _ in range(5):
        ci.handle_key(_key(pygame.K_LEFT, mod=pygame.KMOD_SHIFT))
    assert ci.selected_text() == "world"
    ci.handle_key(_key(0, uni="X"))
    assert ci.text == "hello X"
    ci.handle_key(_key(pygame.K_HOME))
    ci.handle_key(_key(0, uni=">"))
    assert ci.text == ">hello X" and ci.cursor == 1
    ci.handle_key(_key(pygame.K_a, mod=pygame.KMOD_CTRL))
    assert ci.all_selected()
    ci.handle_key(_key(pygame.K_BACKSPACE))
    assert ci.text == ""
    ci.remember("first"); ci.remember("second")
    ci.handle_key(_key(pygame.K_UP))
    assert ci.text == "second"
    ci.handle_key(_key(pygame.K_UP))
    assert ci.text == "first"
    ci.handle_key(_key(pygame.K_DOWN))
    ci.handle_key(_key(pygame.K_DOWN))
    assert ci.text == "", "Down past the newest returns to the (empty) draft"
    assert ci.handle_key(_key(pygame.K_RETURN)) == "submit"
    print("check_chat_input_editing: PASSED")


def check_chat_log_select_without_chat_mode(g):
    import main
    g.quit_confirm_open = False
    g.chat_log = [{"name": "Bob", "text": f"line number {i}", "age": 5.0} for i in range(6)]
    g.chat_scroll = 0
    r = ui.chat_log_rect(g.chat_log)
    a = (r.x + 60, r.y + 8 + 18 * 1 + 4)
    b = (r.x + 60, r.y + 8 + 18 * 3 + 4)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=a))
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=b, rel=(0, 36), buttons=(1, 0, 0)))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=b))
    g.handle_events()
    assert not g.chat_open, "clicking the chat log must not enter chat mode"
    span = g.chat_log_sel.span()
    assert span is not None and span[1] - span[0] == 2, span
    copied = []
    orig = clipboard.set_text
    clipboard.set_text = copied.append
    try:
        pygame.event.post(_key(pygame.K_c, mod=pygame.KMOD_CTRL))
        g.handle_events()
    finally:
        clipboard.set_text = orig
    assert copied and "Bob: line number 1" in copied[0] and "line number 3" in copied[0], copied
    # Enter still opens the input line; the recent lines show above it
    g.chat_log_sel.clear()
    pygame.event.post(_key(pygame.K_RETURN))
    g.handle_events()
    assert g.chat_open
    for ch in "hey there":
        pygame.event.post(_key(0, uni=ch))
    pygame.event.post(_key(pygame.K_LEFT, mod=pygame.KMOD_SHIFT))
    pygame.event.post(_key(pygame.K_LEFT, mod=pygame.KMOD_SHIFT))
    g.handle_events()
    assert g.chat_in.selected_text() == "re"
    g.draw()
    _shot(g.screen, "p2_chat_input.png")
    pygame.event.post(_key(pygame.K_ESCAPE))
    g.handle_events()
    assert not g.chat_open
    print("check_chat_log_select_without_chat_mode: PASSED")


class FakeSock:
    def __init__(self):
        self.msgs = []

    def sendall(self, data):
        for line in data.decode("utf-8").splitlines():
            self.msgs.append(json.loads(line))


def check_cross_zone_msg_and_name_menu():
    import server
    import coop_client
    state = server.ServerState()
    a = server.Session("pa", FakeSock(), Player("wizard", name="Alice", pid="pa"))
    b = server.Session("pb", FakeSock(), Player("warrior", name="Bob Two", pid="pb"))
    a.zone, b.zone = server.ZONE_NEXUS, server.ZONE_REALM  # different zones
    state.sessions = {"pa": a, "pb": b}
    server._apply_action(state, a, {"action": "whisper", "name": "bob two", "text": "psst"})
    got = [m for m in b.sock.msgs if m.get("type") == "whisper"]
    assert got and got[-1]["from"] == "Alice" and got[-1]["text"] == "psst", "whispers cross zones"
    server._apply_action(state, a, {"action": "whisper", "name": "Nobody", "text": "hi"})
    assert any(m.get("error") for m in a.sock.msgs), "unknown names get an error back"
    assert coop_client._split_msg_target('"Bob Two" hello you') == ("Bob Two", "hello you")
    assert coop_client._split_msg_target("Bob hi") == ("Bob", "hi")

    class FakeLink:
        error = None

        def __init__(self):
            self.sent = []

        def send(self, obj):
            self.sent.append(obj)

    client = coop_client.CoopClient("127.0.0.1", 0, "Alice")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY
    client.zone = "nexus"
    client.peers = []
    client.chat_log = [{"name": "Bob Two (whisper)", "text": "psst", "age": 1.0, "sender": "Bob Two"}]
    client.chat_scroll = 0
    r = ui.chat_log_rect(client.chat_log)
    assert client._chat_name_right_click((r.x + 12, r.y + 14)), "right-click on the name opens the menu"
    assert client.context_menu["name"] == "Bob Two"
    disabled = client._context_menu_disabled()
    assert "Trade" in disabled and "Teleport" in disabled, "not-here players can't be traded/teleported to"
    labels = client._context_menu_labels()
    rects = ui.context_menu_rects(client.context_menu["pos"], labels)
    client._context_menu_click(rects[labels.index("Chat")].center)
    assert client.chat_open and client.chat_buffer.startswith("/w Bob Two")
    client.chat_buffer = '/msg "Bob Two" hello'
    client._submit_chat()
    assert client.link.sent[-1] == {"type": "action", "action": "whisper", "name": "Bob Two", "text": "hello"}
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    surf.fill((20, 22, 26))
    ui.draw_chat_log(surf, client.chat_log + [{"name": "Carol", "text": "gg", "age": 1.0}], selection=(0, 0))
    ui.draw_context_menu(surf, (r.x + 12, r.y + 14), "Bob Two", labels, (0, 0), disabled=disabled)
    _shot(surf, "p2_chat_name_menu.png")
    print("check_cross_zone_msg_and_name_menu: PASSED")


# ------------------------------------------------------------------ 2.5
def check_vault_twelve_chests(g):
    import main
    assert VAULT_CHEST_COUNT == 12
    tiles = vault.chest_tiles(g.vault_room_map)
    assert len(tiles) == 12, len(tiles)
    g.quit_confirm_open = g.chat_open = False
    g.state = main.STATE_NEXUS
    g.enter_vault_room()
    assert g.state == main.STATE_VAULT_ROOM and g.vault_chest_open is None
    g.player.pos = vault.chest_world_pos(g.vault_room_map, 5) + pygame.Vector2(0, C.TILE)
    g.player.backpack = [_sword("VaultBlade")]
    pygame.event.post(_key(pygame.K_f))
    g.handle_events()
    assert g.vault_chest_open == 5, "F next to chest 5 opens chest 5"
    # plain click on the backpack item deposits into THIS chest
    g.drag_from, g.drag_start_pos = ("backpack", 0), (50, 50)
    g._vault_mouse_up((50, 50))
    assert g.vault_items[5 * VAULT_CHEST_SIZE] is not None and not g.player.backpack
    g.draw()
    _shot(g.screen, "p2_vault_room_open_chest.png")
    pygame.event.post(_key(pygame.K_ESCAPE))
    g.handle_events()
    assert g.vault_chest_open is None and not g.quit_confirm_open, "Esc closes the chest window first"
    reloaded = items.load_vault(g.player_name)
    assert len(reloaded) == VAULT_CHEST_COUNT * VAULT_CHEST_SIZE
    assert reloaded[5 * VAULT_CHEST_SIZE].name == "VaultBlade", "the deposit persisted"
    g.draw()
    _shot(g.screen, "p2_vault_room.png")
    print("check_vault_twelve_chests: PASSED")


def check_coop_vault_chest():
    import server
    import coop_client
    state = server.ServerState()
    me = Player("wizard", name="CoopVault", pid="cv")
    s = server.Session("cv", FakeSock(), me)
    s.zone = server.ZONE_NEXUS
    state.sessions = {"cv": s}
    me.pos = pygame.Vector2(0, 0)
    import game.world as W
    # walk in through the Nexus vault tile (the server checks it)
    g = state.nexus_map.grid
    vt = next((x, y) for y in range(len(g)) for x in range(len(g[0])) if g[y][x] == W.VAULT_TILE)
    me.pos = pygame.Vector2((vt[0] + 0.5) * C.TILE, (vt[1] + 0.5) * C.TILE)
    server._apply_action(state, s, {"action": "goto_vault_room"})
    assert s.zone == server.ZONE_VAULT_ROOM
    assert any(m.get("type") == "vault_state" and m.get("chest") is None for m in s.sock.msgs),         "entering the room sends fill counts without opening anything"
    me.pos = vault.chest_world_pos(state.vault_room_map, 7) + pygame.Vector2(0, C.TILE)
    me.backpack = [_sword("CoopBlade")]
    server._apply_action(state, s, {"action": "open_vault"})
    opened = [m for m in s.sock.msgs if m.get("type") == "vault_state" and m.get("chest") is not None]
    assert opened and opened[-1]["chest"] == 7, "the chest you stand next to opens"
    server._apply_action(state, s, {"action": "vault_deposit", "idx": 0})
    assert s.vault_items[7 * VAULT_CHEST_SIZE].name == "CoopBlade" and not me.backpack

    client = coop_client.CoopClient("127.0.0.1", 0, "CoopVault")

    class Link:
        def __init__(self, v, c):
            self.v, self.c = v, c

        def pop_vault_items(self):
            v, self.v = self.v, None
            return v, self.c
    link = Link(opened[-1]["items"], 7)
    vault_items, hint = link.pop_vault_items()
    assert hint == 7 and len(vault_items) == VAULT_CHEST_COUNT * VAULT_CHEST_SIZE
    assert client.vault_chest_open is None
    print("check_coop_vault_chest: PASSED")


# ------------------------------------------------------------------ 2.6
def check_hud_widths_and_fit():
    clock = ui.day_night_clock_rect()
    panel_w = ui.PLAYER_PANEL_WIDTH + 12
    assert clock.w == panel_w and clock.x == ui._panel_block_x0() - 6, (clock, panel_w)
    mm_x, mm_y = minimap.corner_origin()
    assert minimap.CORNER_W + 6 == panel_w and mm_x - 3 == clock.x, "minimap frame = dock width"
    assert minimap.CORNER_W > minimap.CORNER_H, "a wide radar"
    assert mm_y - 3 > clock.bottom, "minimap sits below the clock"
    assert ui.zone_info_rect().colliderect(clock), "zone name/kills live in the clock header"
    p = Player("wizard", "HudFit", pid="h")
    p.backpack_size = 8 + accounts.MAX_BACKPACK_BONUS_SLOTS if hasattr(accounts, "MAX_BACKPACK_BONUS_SLOTS") else 10
    bottom = ui.backpack_slot_rects(p)[-1].bottom
    assert bottom < C.SCREEN_H - 10, f"backpack bottom {bottom} must fit the screen"
    print(f"check_hud_widths_and_fit: PASSED (clock {clock.w}w, minimap {minimap.CORNER_W}x{minimap.CORNER_H}, "
          f"backpack bottom {bottom})")


if __name__ == "__main__":
    check_pets_and_spells_spare_wildlife()
    check_spell_power_and_styles()
    check_mob_speech_earshot()
    game = check_esc_chain_and_quit_prompt()
    check_chat_input_editing()
    check_chat_log_select_without_chat_mode(game)
    check_cross_zone_msg_and_name_menu()
    check_vault_twelve_chests(game)
    check_coop_vault_chest()
    check_hud_widths_and_fit()
    print("PASSED: Phase 2 fixes & UI checks all green.")
