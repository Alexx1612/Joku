"""
Batch 15 Phase 1B regression checks: the Quest Log, Dictionary and Quest Map windows
(game/journal.py + game/codex.py) in single-player and the co-op client, driven by
real pygame events.

Set RR_SHOT_DIR to also save screenshots.
Run with: .venv\\Scripts\\python.exe tests\\check_quest_log_dictionary.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((100, 100))

from game import accounts, characters, achievements, items as items_mod
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_jnl_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_jnl_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_jnl_ach_")
items_mod.VAULT_DIR = tempfile.mkdtemp(prefix="rr_jnl_vault_")

from game import codex, journal, npcs, realm_sim, world, audio
from game.entities import Player, ENEMY_KINDS
from game.items import PET_KINDS

SHOT_DIR = os.environ.get("RR_SHOT_DIR")
audio.play_theme = lambda *a, **k: None  # zone music synthesis isn't what's under test (and is slow)


def _shot(surf, name):
    if SHOT_DIR:
        pygame.image.save(surf, os.path.join(SHOT_DIR, name))


def _key(k, uni="", mod=0):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode=uni, scancode=0))


def _click(pos, button=1):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos))


def _wheel(y):
    pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=y, flipped=False))


def check_dictionary_coverage_and_search():
    ids = {e["id"] for e in codex.entries()}
    for kind in ENEMY_KINDS:
        assert f"enemy:{kind}" in ids, kind
    for npc_id in npcs.NPCS:
        assert f"npc:{npc_id}" in ids, npc_id
    for kind in PET_KINDS:
        assert f"pet:{kind}" in ids, kind
    for key in realm_sim.DUNGEON_THEMES:
        assert f"area:dungeon:{key}" in ids, key
    for i in range(len(realm_sim.ISLAND_NAMES)):
        assert f"area:island:{i}" in ids
    for b in world.LANDMARK_DEFS:
        assert f"area:landmark:{b}" in ids and f"area:{b}" in ids
    cats = {c for c, _l in codex.CATEGORIES}
    assert all(e["cat"] in cats for e in codex.entries())
    assert any(e["id"] == "enemy:deer" for e in codex.search("deer"))
    assert codex.search("fusion")[0]["id"] == "help:fusion"
    assert any(e["id"] == "help:bond" for e in codex.search("bond"))
    assert codex.search("zzzqqq") == []
    # the stats shown come straight from ENEMY_KINDS
    gob = codex.entry("enemy:goblin")
    assert ("HP", ENEMY_KINDS["goblin"]["hp"]) in gob["stats"]
    # every quest target the game can produce resolves to a real entry
    from game import sidequests, story
    for q in sidequests.QUESTS.values():
        eid = codex.entry_for_target(q["target"])
        assert eid and codex.entry(eid), (q["title"], eid)
    for act in story.ACTS:
        for o in act["objectives"]:
            eid = codex.entry_for_target(story.objective_target(o))
            assert eid and codex.entry(eid), (o["id"], eid)
    print("check_dictionary_coverage_and_search: PASSED")


def _sp_game():
    import main
    g = main.Game()
    g.player = Player("wizard", "Journal", pid="sp")
    g.player_name = "Journal"
    g.enter_realm()
    for q in ("barkeeps_tab", "herd_whisperer", "pest_control"):
        g.player.sidequests.accept(q)
    g.update(1 / 30)
    return main, g


def check_singleplayer_windows():
    main, g = _sp_game()
    labels = [r.label for r in g._menu_items()]
    assert "Quest Log" in labels and "Dictionary" in labels
    # open the Quest Log through the O menu row (a real click)
    from game import ui
    g.help_open = True
    rows = g._menu_items()
    idx = labels.index("Quest Log")
    _click(ui.help_menu_item_rects(rows)[idx].center)
    g.handle_events()
    assert g.journal.mode == journal.QUEST_LOG and not g.help_open
    g.draw()
    _shot(g.screen, "p1b_quest_log.png")
    # movement is blocked while it's open
    x0 = g.player.pos.x
    real = pygame.key.get_pressed
    pygame.key.get_pressed = lambda: _Pressed({pygame.K_d})
    try:
        for _ in range(10):
            g.update(1 / 30)
    finally:
        pygame.key.get_pressed = real
    assert abs(g.player.pos.x - x0) < 0.01, "WASD must not move you while the Quest Log is open"
    # scrolling clamps at both ends
    ctx = g._journal_ctx()
    items, total = g.journal._ql_layout(ctx)
    view = g.journal._ql_rects()[1].h
    for _ in range(40):
        _wheel(-1)
    g.handle_events()
    assert g.journal.ql_scroll == max(0, total - view)
    for _ in range(40):
        _wheel(1)
    g.handle_events()
    assert g.journal.ql_scroll == 0
    # clicking a quest's target name opens the Dictionary on that entry
    win, content = g.journal._ql_rects()
    link = next(it for it in items if it["kind"] == "link" and it.get("action") == ("dict", "enemy:deer"))
    pos = (content.x + link["x"] + 3, content.y + link["y"] - g.journal.ql_scroll + 3)
    _click(pos)
    g.handle_events()
    assert g.journal.mode == journal.DICTIONARY and g.journal.sel == "enemy:deer"
    g.draw()
    _shot(g.screen, "p1b_dictionary_deer.png")
    # Esc goes back to the quest log, a second Esc closes it - the game keeps running
    _key(pygame.K_ESCAPE)
    g.handle_events()
    assert g.journal.mode == journal.QUEST_LOG
    _key(pygame.K_ESCAPE)
    assert g.handle_events() is not False
    assert not g.journal.is_open() and not g.quit_confirm_open
    # Map button -> quest map with a marker, tooltip on hover
    g.journal.open_quest_log()
    ctx = g._journal_ctx()
    items, _t = g.journal._ql_layout(ctx)
    btn = next(it for it in items if it["kind"] == "button" and codex.markers_for(it["action"][1], ctx["areas"]))
    _click((content.x + btn["x"] + 5, content.y + btn["y"] - g.journal.ql_scroll + 5))
    g.handle_events()
    assert g.journal.mode == journal.QUEST_MAP
    pts = codex.markers_for(g.journal.map_where, ctx["areas"])
    assert pts, "the quest map must mark where to go"
    sx, sy = g.journal._to_screen(ctx)(pts[0][0], pts[0][1])
    tip = g.journal.map_hover(ctx, (int(sx), int(sy)))
    assert tip and tip.startswith("QUEST:"), tip
    g.journal.draw(g.screen, ctx, (int(sx), int(sy)))
    _shot(g.screen, "p1b_quest_map.png")
    # zoom works and clamps
    for _ in range(20):
        _wheel(1)
    g.handle_events()
    assert g.journal.map_zoom == 8.0
    g.draw()
    g.journal.close_all()
    # dictionary search via typing (keys never reach the game: "m" must not open the map)
    g.journal.open_dictionary()
    for ch in "fusion":
        _key(ord(ch), ch)
    g.handle_events()
    assert g.journal.query == "fusion" and g.journal.sel == "help:fusion"
    assert not g._current_minimap().full_map_open
    _key(pygame.K_a, "a", mod=pygame.KMOD_CTRL)
    _key(pygame.K_BACKSPACE)
    g.handle_events()
    assert g.journal.query == ""
    for ch in "map":
        _key(ord(ch), ch)
    g.handle_events()
    assert not g._current_minimap().full_map_open and g.journal.query == "map"
    g.draw()
    _shot(g.screen, "p1b_dictionary_search.png")
    # category click + pets help page
    g.journal.open_dictionary()
    r = g.journal._dict_rects()
    pets_idx = [c for c, _l in codex.CATEGORIES].index("pets")
    _click(g.journal._cat_rect(r, pets_idx).center)
    g.handle_events()
    assert g.journal.cat == "pets" and g.journal.sel == "help:pets"
    g.draw()
    _shot(g.screen, "p1b_pets_help.png")
    # a plain click on the small HUD quest log opens the full Quest Log
    g.journal.close_all()
    g.draw()
    hud = ui.quest_slot_rect()
    assert hud is not None
    _click(hud.center)
    g.handle_events()
    assert g.journal.mode == journal.QUEST_LOG
    print("check_singleplayer_windows: PASSED")


class _Pressed:
    def __init__(self, keys):
        self.keys = keys

    def __getitem__(self, k):
        return k in self.keys


def check_coop_client_windows_and_snapshot_areas():
    import server
    import coop_client
    # the server ships realm area info once, alongside the map
    state = server.ServerState()
    me = Player("wizard", name="CoopJ", pid="c0")
    s = server.Session("c0", _FakeSock(), me)
    state.sessions["c0"] = s
    s.zone = server.ZONE_REALM
    me.pos = state.realm_sim.spawn_point()
    snap = server._snapshot_for(state, s)
    assert snap["map"] is not None and snap["areas"] and snap["areas"]["landmarks"]
    assert "sidequests_done" in snap
    snap2 = server._snapshot_for(state, s)
    assert snap2["map"] is None and snap2["areas"] is None  # only once

    class FakeLink:
        error = None
        welcome_pid = "c0"

        def __init__(self):
            self.sent = []
            self.map, self.areas = snap["map"], snap["areas"]

        def send(self, obj):
            self.sent.append(obj)

        def get_snapshot(self):
            return None

        def pop_pending_map(self):
            v, self.map = self.map, None
            return v

        def pop_pending_areas(self):
            v, self.areas = self.areas, None
            return v

        def pop_vault_items(self):
            return None, None

        pop_bag_state = pop_wish_result = pop_socket_result = lambda self: None

        def pop_whispers(self):
            return []

        pop_trade_notices = pop_pet_results = pop_echo_shop_states = pop_whispers

        def pop_story(self):
            return [], []

        def pop_dialogue(self):
            return None

    client = coop_client.CoopClient("127.0.0.1", 0, "CoopJ")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY
    client._apply_snapshot(snap)
    assert client.realm_grid is not None and client.realm_areas is not None
    labels = [r.label for r in client._menu_items()]
    assert "Quest Log" in labels and "Dictionary" in labels
    client._open_quest_log()
    assert client.journal.mode == journal.QUEST_LOG
    client.update(0.016)
    client.draw()
    _shot(client.screen, "p1b_coop_quest_log.png")
    # input is frozen for the server while a window is up
    client.link.sent.clear()
    client._send_input(0.016)
    assert client.link.sent and client.link.sent[-1]["move"] == [0.0, 0.0]
    client.journal.open_dictionary("enemy:goblin")
    ctx = client._journal_ctx()
    assert codex.markers_for(codex.entry("enemy:goblin")["where"], ctx["areas"])
    client.draw()
    _key(pygame.K_ESCAPE)
    client.handle_events()
    assert not client.journal.is_open() and not client.quit_confirm_open
    print("check_coop_client_windows_and_snapshot_areas: PASSED")


class _FakeSock:
    def sendall(self, data):
        pass


if __name__ == "__main__":
    check_dictionary_coverage_and_search()
    check_singleplayer_windows()
    check_coop_client_windows_and_snapshot_areas()
    print("PASSED: quest log / dictionary / quest map checks all green.")
