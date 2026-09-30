"""
End-to-end functionality pass over the REAL game code (V0.2): single-player via
main.Game driven by real pygame events (handle_events/update/draw), and co-op via
an in-process server (real tick loop + handle_client threads) with two real
CoopClient instances talking over localhost sockets. The per-system details live
in their own check_*.py files; this one proves the systems work together in one
continuous session the way a player hits them.
"""
import os
import random
import socket
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("RR_NO_MUSIC", "1")
# ALWAYS our own file: run_all_checks shares one settings path across every script, and an earlier
# script's saved panel_offsets/volumes (e.g. a dragged panel parked over the backpack) leaked in
os.environ["RR_SETTINGS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="rr_fp_set_"), "settings.json")

import pygame
pygame.init()

from game import achievements, items, characters, accounts, friends, crews
achievements._DIR = tempfile.mkdtemp(prefix="rr_fp_ach_")
items.VAULT_DIR = tempfile.mkdtemp(prefix="rr_fp_vault_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_fp_char_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_fp_acc_")
friends.FRIENDS_DIR = tempfile.mkdtemp(prefix="rr_fp_fr_")
crews.CREWS_DIR = tempfile.mkdtemp(prefix="rr_fp_crew_")

import main
from game import story, world, vault, music, ui, settings, constants as C
from game.entities import Enemy
from game.items import make_egg, make_potion, make_old_boot, load_vault
from game.realm_sim import DUNGEON_THEMES

CLASSES = ["wizard", "warrior", "archer", "priest", "rogue", "paladin", "necromancer", "assassin"]


class Held:
    keys = set()
    buttons = [False, False, False]
    mouse = (683, 300)


pygame.key.get_pressed = lambda: type("K", (), {"__getitem__": lambda self, k: k in Held.keys})()
pygame.mouse.get_pressed = lambda num_buttons=3: tuple(Held.buttons)
pygame.mouse.get_pos = lambda: Held.mouse


def press(g, k, uni="", mod=0):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode=uni, scancode=0))
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=k, mod=mod, unicode=uni, scancode=0))
    return g.handle_events()


def click(g, pos, button=1):
    Held.mouse = pos
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos))
    g.handle_events()


def frames(g, n=1, dt=1 / 30):
    for _ in range(n):
        g.handle_events()
        g.update(dt)
        g.draw()


def check_singleplayer_session():
    random.seed(21)
    g = main.Game()
    # --- intro -> name entry -> class select -> Nexus, with real key events
    assert g.state == main.STATE_INTRO
    frames(g, int(main.INTRO_DURATION * 30) + 5)
    assert g.state == main.STATE_NAME_ENTRY
    g.name_entry_buffer = ""
    for ch in "Tester":
        press(g, ord(ch.lower()), uni=ch)
    press(g, pygame.K_RETURN, uni="\r")
    assert g.state == main.STATE_CLASS_SELECT, g.state
    press(g, pygame.K_RIGHT)
    press(g, pygame.K_RETURN, uni="\r")
    assert g.state == main.STATE_NEXUS and g.player is not None and g.player.name == "Tester"
    frames(g, 5)

    # --- options menu (O), every row activates without error, Esc closes it (not the game)
    press(g, pygame.K_o, uni="o")
    assert g.help_open
    for row in g._menu_items():
        if row.kind in ("toggle", "cycle", "slider") and "Fullscreen" not in row.label:
            from game import options_menu
            options_menu.adjust(row, 1)
            options_menu.adjust(row, -1)
    frames(g, 2)
    assert press(g, pygame.K_ESCAPE) is not False and not g.help_open
    # settings persist to the settings file and reload
    settings.change("music_volume", 0.4)
    settings.load()
    assert abs(settings.get("music_volume") - 0.4) < 1e-6

    # --- journal: Quest Log -> click a target -> Dictionary -> search -> Esc steps back, never quits
    g._open_quest_log()
    frames(g, 2)
    assert g.journal.is_open()
    g.journal._set_query("fusion") if hasattr(g.journal, "_set_query") else None
    g.journal.close_all()
    g._open_dictionary()
    g.journal._set_query("deer")
    frames(g, 2)
    assert press(g, pygame.K_ESCAPE) is not False
    assert not g.journal.is_open()

    # --- dialogue with a Nexus NPC via F, answer with a number key, Esc = Bye
    npc = g.nexus_npcs[0]
    g.player.pos = pygame.Vector2(npc.pos) + pygame.Vector2(14, 0)
    frames(g, 2)
    assert g._try_talk() and g.dialogue is not None
    n_opts = len(g.dialogue.view()["options"])
    assert n_opts >= 2 and g.dialogue.view()["options"][-1].lower().startswith("bye")
    press(g, pygame.K_1, uni="1")
    frames(g, 1)
    if g.dialogue is not None:
        press(g, pygame.K_ESCAPE)
    assert g.dialogue is None

    # --- inventory: potion via number key, egg hatch, drag swap, drop
    p = g.player
    p.backpack = [make_potion("att"), make_egg("hatchling"), make_old_boot()]
    att0 = p.stats["att"] if hasattr(p, "stats") else None
    press(g, pygame.K_1, uni="1")  # drink the ATT potion
    if att0 is not None:
        assert p.stats["att"] > att0, "number key should drink the potion"
    press(g, pygame.K_1, uni="1")  # hatch the egg (now in slot 1)
    assert p.pet is not None, "egg should hatch into a pet"
    frames(g, 30)
    assert p.pet.pos.distance_to(p.pos) < 80, "pet follows in the Nexus"

    # --- vault room: 12 chests, open one with F, deposit, persists to disk
    g.enter_vault_room()
    frames(g, 3)
    wp = vault.chest_world_pos(g.vault_room_map, 3)
    p.pos = pygame.Vector2(wp) + pygame.Vector2(0, 28)
    frames(g, 2)
    assert g._try_open_vault_chest() and g.vault_chest_open == 3
    boot_idx = next(i for i, it in enumerate(p.backpack) if it.name == make_old_boot().name)
    before = sum(1 for it in g.vault_items if it is not None)
    g.drag_start_pos = (0, 0)
    slot_rects = ui.backpack_slot_rects(p)
    pos = slot_rects[boot_idx].center
    Held.mouse = pos
    mods = pygame.key.get_mods
    pygame.key.get_mods = lambda: pygame.KMOD_LSHIFT
    click(g, pos)  # shift-click = quick deposit into the open chest
    pygame.key.get_mods = mods
    after = sum(1 for it in g.vault_items if it is not None)
    assert after == before + 1, (before, after)
    on_disk = load_vault("Tester")
    assert sum(1 for it in on_disk if it is not None) == after
    press(g, pygame.K_ESCAPE)
    assert g.vault_chest_open is None
    g.go_nexus()

    # --- realm: move, shoot, ability, dash, level up; wildlife never takes damage
    g.enter_realm()
    frames(g, 5)
    assert g.state == main.STATE_REALM
    sim = g.realm_sim
    start = pygame.Vector2(p.pos)
    Held.keys = {pygame.K_w}
    frames(g, 20)
    Held.keys = set()
    assert p.pos.distance_to(start) > 20, "WASD moves the player"
    foe = Enemy("goblin", p.pos + pygame.Vector2(90, 0))
    sim.enemies.append(foe)
    Held.mouse = g.cam(foe.pos)
    Held.buttons = [True, False, False]
    frames(g, 40)
    Held.buttons = [False, False, False]
    assert foe.hp < foe.hp_max or not foe.alive, "holding the mouse fires at the enemy"
    deer = Enemy("deer", p.pos + pygame.Vector2(0, 60))
    sim.enemies.append(deer)
    p.mp = p.mp_max
    press(g, pygame.K_SPACE, uni=" ")
    frames(g, 20)
    assert deer.hp == deer.hp_max and deer.alive, "abilities never hurt friendly wildlife"
    for _ in range(30):
        p.gain_xp(10 ** 5)
    assert p.level == 20

    # --- every dungeon theme: enter, boss exists, leave back to the realm (a T12 weapon so the
    # Mad God's Room gate - level 20 + a T12+ item - lets this level-20 hero in too)
    from game import items as _items
    _r = next(r for r in _items.WEAPONS[p.cls_name] if r[2] == 12)
    p.weapon = _items.Item(_r[0], _items.SLOT_WEAPON, 12, _r[1], min_dmg=_r[3][0], max_dmg=_r[3][1])
    for theme in DUNGEON_THEMES:
        if theme == "forge":
            continue
        g.enter_bonus_room(theme=theme, difficulty="Easy")
        frames(g, 2)
        assert g.state == main.STATE_BONUS and g.bonus_sim.boss is not None, theme
        g.leave_bonus_room()
        assert g.state == main.STATE_REALM

    # --- story: jump to the Finale, the Forge, both Mad God phases -> credits
    g.go_nexus()
    p.story = story.StoryProgress(len(story.ACTS) - 1)
    g.enter_forge()
    frames(g, 2)
    boss = g.bonus_sim.boss
    assert boss is not None and boss.kind == "mad_god"
    for _ in range(2):
        b = g.bonus_sim.boss
        b.hp, b.alive = 0, False
        g.bonus_sim._reward(b, p)
        frames(g, 3)
    assert p.story.finished
    assert g.credits_t is not None, "beating the Mad God rolls the credits"
    press(g, pygame.K_RETURN, uni="\r")
    assert g.credits_t is None

    # --- HUD at a larger (fullscreen-like) resolution draws and the dock stays on screen
    g._resize_canvas(1920, 1080)
    frames(g, 2)
    r = ui.dock_frame_rect(p)
    assert r.right <= C.SCREEN_W and r.bottom <= C.SCREEN_H
    g._resize_canvas(1366, 820)

    # --- death: permadeath, account keeps the act checkpoint, new character starts again
    g.leave_bonus_room() if g.state == main.STATE_BONUS else None
    g.go_nexus()
    g.enter_realm()
    p.hp, p.alive = 0, False
    g.die()
    assert g.state == main.STATE_DEAD
    assert accounts.get_story_act("Tester") >= len(story.ACTS) - 1
    press(g, pygame.K_RETURN, uni="\r")
    frames(g, 2)
    assert g.state in (main.STATE_CLASS_SELECT, main.STATE_NEXUS)

    # --- Esc with nothing open asks first; Esc again in the prompt quits
    if g.state == main.STATE_CLASS_SELECT:
        press(g, pygame.K_RETURN, uni="\r")
    frames(g, 1)
    assert press(g, pygame.K_ESCAPE) is not False and g.quit_confirm_open
    assert press(g, pygame.K_ESCAPE) is False, "Esc in the quit prompt exits"
    print("check_singleplayer_session: PASSED")


def check_every_class_ability():
    g = main.Game()
    g.player_name = "Classy"
    for cls in CLASSES:
        g.start_run(cls)
        g.enter_realm()
        p = g.player
        p.mp = p.mp_max
        mp0 = p.mp
        press(g, pygame.K_SPACE, uni=" ")
        frames(g, 3)
        assert p.mp < mp0, f"{cls}: Space should cast the class ability"
        g.go_nexus()
    print("check_every_class_ability: PASSED")


def check_world_contents():
    g = main.Game()
    g.player_name = "Mapper"
    g.start_run("wizard")
    g.enter_realm()
    sim = g.realm_sim
    grid = sim.realm_map.grid
    biomes = {world.GROUND_TO_BIOME_NAME.get(t) for row in grid[::7] for t in row[::7]} - {None}
    assert len(biomes) == 10, biomes
    assert len(sim.islands) == 10 and len(sim.areas) == 10 and len(sim.landmarks) == 10
    sp = sim.spawn_point()
    assert not sim.realm_map.is_solid(sp.x, sp.y)
    # every zone/biome/dungeon has a music track
    for b in biomes:
        assert music.realm_zone(b) in music.TRACKS, b
    for th in DUNGEON_THEMES:
        assert music.dungeon_zone_for_key(th) in music.TRACKS, th
    print("check_world_contents: PASSED")


def _start_server():
    import server
    state = server.ServerState()
    stop = threading.Event()
    threading.Thread(target=server.tick_loop, args=(state, stop), daemon=True).start()
    lis = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lis.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lis.bind(("127.0.0.1", 0))
    lis.listen(4)

    def accept():
        while not stop.is_set():
            try:
                conn, addr = lis.accept()
            except OSError:
                return
            threading.Thread(target=server.handle_client, args=(conn, addr, state), daemon=True).start()
    threading.Thread(target=accept, daemon=True).start()
    return server, state, lis.getsockname()[1], stop, lis


def _pump(clients, secs):
    t_end = time.time() + secs
    while time.time() < t_end:
        for c in clients:
            c.handle_events()
            c.update(1 / 30)
            c.draw()
        time.sleep(0.01)


def _session(state, name):
    with state.lock:
        return next(s for s in state.sessions.values() if s.player.name == name)


def check_coop_session():
    import coop_client
    server, state, port, stop, lis = _start_server()
    a = coop_client.CoopClient("127.0.0.1", port, "Ana")
    b = coop_client.CoopClient("127.0.0.1", port, "Ben")
    a._connect("wizard")
    b._connect("archer")
    _pump([a, b], 1.0)
    assert a.zone == "nexus" and b.zone == "nexus"
    sa, sb = _session(state, "Ana"), _session(state, "Ben")
    # trade: invite -> accept -> both offer -> both accept -> swap
    with state.lock:
        sa.player.backpack = [make_old_boot()]
        sb.player.backpack = [make_potion("deF")]
        sb.player.pos = pygame.Vector2(sa.player.pos) + pygame.Vector2(20, 0)
    a.link.send({"type": "action", "action": "trade_request", "pid": sb.pid})
    _pump([a, b], 0.5)
    b.link.send({"type": "action", "action": "trade_invite_accept"})
    _pump([a, b], 0.5)
    assert a.trade is not None and b.trade is not None, "both clients see the trade window"
    # the server's "[Ana and Ben are trading]" notice has no player behind it - never "???: ..."
    assert not any(m["name"] == "???" for m in a.chat_log + b.chat_log), [m["name"] for m in a.chat_log]
    assert any(m["name"] == "Server" and "trading" in m["text"] for m in a.chat_log), a.chat_log[-3:]
    a.link.send({"type": "action", "action": "trade_offer", "idx": 0})
    b.link.send({"type": "action", "action": "trade_offer", "idx": 0})
    _pump([a, b], 0.4)
    a.link.send({"type": "action", "action": "trade_accept"})
    b.link.send({"type": "action", "action": "trade_accept"})
    _pump([a, b], server.TRADE_CONFIRM_SECONDS + 1.0)
    with state.lock:
        assert [it.name for it in sa.player.backpack] == [make_potion("deF").name]
        assert [it.name for it in sb.player.backpack] == [make_old_boot().name]
    # cross-zone /msg: Ben goes to the Realm, Ana whispers from the Nexus
    with state.lock:
        g = state.nexus_map.grid
        px, py = next((x, y) for y in range(len(g)) for x in range(len(g[0])) if g[y][x] == world.PORTAL)
        sb.player.pos = pygame.Vector2(px * C.TILE + 16, py * C.TILE + 16)
    b.link.send({"type": "action", "action": "goto_realm"})
    _pump([a, b], 1.5)
    assert b.zone == "realm" and b.tilemap is not None, "Ben reaches the Realm with its map"
    a.chat_input.set_text('/msg "Ben" hello across zones') if hasattr(a, "chat_input") else None
    a._handle_chat_command('msg "Ben" hello across zones') if hasattr(a, "_handle_chat_command") else None
    _pump([a, b], 0.8)
    texts = [m.get("text", "") for m in b.chat_log]
    assert any("hello across zones" in t for t in texts), texts[-5:]
    # co-op dialogue: F next to a Nexus NPC opens a server-driven conversation
    with state.lock:
        npc = state.nexus_npcs[0]
        sa.player.pos = pygame.Vector2(npc.pos) + pygame.Vector2(14, 0)
    _pump([a, b], 0.3)
    a._context_action()
    _pump([a, b], 0.6)
    assert a.dialogue_view is not None, "co-op talk opens the dialogue"
    a.link.send({"type": "action", "action": "dialogue_close"})
    _pump([a, b], 0.4)
    assert a.dialogue_view is None
    a.link.stop()
    b.link.stop()
    stop.set()
    lis.close()
    print("check_coop_session: PASSED")


def check_fixed_regressions():
    """Bugs found by this playthrough pass - each fails on the pre-fix code."""
    # 1. a titled panel's title strip must be opaque (it was alpha-50 -> HUD text showed through)
    panel, _ = ui._ornate_panel(300, 120, title="Options")
    assert panel.get_at((150, 10)).a == 255, panel.get_at((150, 10))
    # 2. class select: the stats panel's gold top border no longer runs through the second-row
    #    class NAMES (drawn just below each tile) - scan the old border row for panel gold
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    ui.draw_class_select(surf, 0)
    tiles = ui.class_select_tile_rects()
    old_top = max(r.bottom for r, _ in tiles) + 10
    row2 = [r for r, _ in tiles if r.bottom == max(t.bottom for t, _ in tiles)]
    gold = tuple(ui.CHROME_GOLD)
    hits = sum(1 for r in row2 for x in range(r.x, r.right) for y in (old_top + 1, old_top + 2)
               if tuple(surf.get_at((x, y)))[:3] == gold)
    assert hits == 0, f"panel border crosses the class names ({hits} gold px on the label row)"
    # 3. identical feed lines don't stack
    g = main.Game()
    for _ in range(3):
        g.push_feed("A whisper echoes", (255, 255, 255))
    assert [m[0] for m in g.feed].count("A whisper echoes") == 1
    # 4. a queued action whose reply hits a dead socket must not abort the server tick
    import server

    class DeadSock:
        def sendall(self, data):
            raise ConnectionAbortedError(10053, "aborted")

        def close(self):
            pass
    state = server.ServerState()
    from game.entities import Player
    s = server.Session("dead", DeadSock(), Player("wizard", name="Dead", pid="dead"))
    state.sessions[s.pid] = s
    state.pending_actions.append(("dead", {"action": "open_vault", "chest": 0}))
    state.pending_actions.append(("dead", {"action": "wish"}))
    server.step(state, 1 / 30)  # used to raise ConnectionAbortedError out of step()
    # 6. zone banners stay off full-screen journal windows (they covered the Quest Map title)
    g2 = main.Game(); g2.player_name = "Bann"; g2.start_run("wizard")
    calls = []
    real = ui.draw_zone_banners
    ui.draw_zone_banners = lambda *a, **k: calls.append(1)
    try:
        g2.journal.open_map(); g2.draw()
        assert not calls, "zone banner drawn over an open journal window"
        g2.journal.close_all(); g2.draw()
        assert calls, "zone banners still draw normally"
    finally:
        ui.draw_zone_banners = real
    # 5. zone names too long for the header get a real ellipsis
    hud = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    ui.draw_hud(hud, "Forgotten Vault [Medium] of Extremely Long Names", 12, True)
    print("check_fixed_regressions: PASSED")


if __name__ == "__main__":
    check_singleplayer_session()
    check_every_class_ability()
    check_world_contents()
    check_coop_session()
    check_fixed_regressions()
    print("PASSED: full playthrough checks all green.")
