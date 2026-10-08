"""
The Forge window (game/forge_menu.py): Brother Hammerstein's chat -> "Open the Forge" -> every
recipe in four tabs, no cap; blocked recipes listed with the reason; temper / reforge / fuse /
set / combine / pry all work through the menu; destructive work needs a second press; the
co-op server's "forge_apply" re-finds the recipe itself and refuses anything stale or made up;
the window draws at 1366x820 and at a fullscreen size.

Run with: python tests/check_forge_menu.py
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
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_fm_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_fm_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_fm_ach_")
I.VAULT_DIR = tempfile.mkdtemp(prefix="rr_fm_vault_")

from game import forge, forge_menu, gems as G, runes, dialogue, npcs, story, audio, sidequests
from game import constants as C
from game.entities import Player

audio.play_theme = lambda *a, **k: None


def _weapons(tier, n, cls="wizard"):
    rows = I.WEAPONS[cls]
    i = next(i for i, r in enumerate(rows) if r[2] == tier)
    return [forge._build("weapon", cls, rows[i], i) for _ in range(n)]


def _player(name="Smith"):
    p = Player("wizard", name, pid=name)
    p.backpack_size = 40
    p.sidequests = sidequests.SideQuestProgress()
    p.story = story.StoryProgress(story.ACT_GEAR)
    p.weapon = _weapons(11, 1)[0]  # 3 sockets
    return p


def _ids(p, items):
    return [next(i for i, b in enumerate(p.backpack) if b is it) for it in items]


def check_catalog_has_no_cap():
    p = _player()
    p.backpack = sum((_weapons(t, 3) for t in (1, 2, 3, 4, 5, 6)), [])
    p.backpack += [G.make_gem(k, "flawed") for k in ("ruby", "sapphire", "topaz", "emerald", "amethyst")]
    cat = forge_menu.catalog(p)
    assert set(cat) == {k for k, _l in forge_menu.TABS}
    tempers = [r for r in cat["temper"] if r["ok"]]
    assert len(tempers) == 6, [r["label"] for r in cat["temper"]]
    sets = [r for r in cat["stonework"] if r["kind"] == "set" and r["ok"]]
    assert len(sets) == 5, [r["label"] for r in cat["stonework"]]
    # the old dialogue caps stay as the default (anything else calling them is unchanged)
    assert len(forge.forge_options(p)) == 3 and len(G.stonework_options(p)) == 4
    print("check_catalog_has_no_cap: PASSED")


def check_blocked_recipes_have_reasons():
    p = _player()
    p.backpack = (_weapons(7, 2) + _weapons(13, 3) + [I.make_forge_ingot(), I._random_ut("wizard")]
                  + [runes.make_rune("rare", "burn")] + [G.make_gem("ruby", "flawed") for _ in range(2)]
                  + [G.make_gem("sapphire", "perfect")])
    cat = forge_menu.catalog(p)
    t7 = next(r for r in cat["temper"] if "T7" in r["label"])
    assert not t7["ok"] and "Need 3 T7" in t7["why"] and "you have 2" in t7["why"], t7["why"]
    t13 = next(r for r in cat["temper"] if "T13" in r["label"])
    assert not t13["ok"] and "Forge Ingots" in t13["why"] and "you have 1" in t13["why"], t13["why"]
    assert ("Forge Ingot", t13["needs"][1][1], 1, 2) == t13["needs"][1]
    ref = cat["reforge"][0]
    assert not ref["ok"] and "2 Forge Ingots" in ref["why"]
    fuse = cat["fuse"][0]
    assert not fuse["ok"] and "rare Shards" in fuse["why"]
    comb = next(r for r in cat["stonework"] if r["kind"] == "combine")
    assert not comb["ok"] and "you have 2" in comb["why"]
    perfect = next(r for r in cat["stonework"] if r["kind"] == "set" and r["gem"].gem_grade == "perfect")
    assert not perfect["ok"] and "Ingot" in perfect["why"]
    # applying a blocked recipe does nothing at all
    before = list(p.backpack)
    for r in (t7, t13, ref, fuse, comb, perfect):
        res = forge_menu.apply(p, r)
        assert not res["ok"] and res["sfx"] == "forge_fail" and res["msg"] == r["why"]
    assert p.backpack == before and not G.stones_in(p.weapon)
    # no weapon: Set explains why
    p.weapon = None
    s = next(r for r in forge_menu.catalog(p)["stonework"] if r["kind"] == "set")
    assert not s["ok"] and "Equip a weapon" in s["why"]
    print("check_blocked_recipes_have_reasons: PASSED")


def check_every_kind_works_through_the_menu():
    p = _player()
    p.backpack = (_weapons(8, 3) + [I._random_ut("wizard"), I.make_forge_ingot(), I.make_forge_ingot()]
                  + [runes.make_rune("rare", "burn") for _ in range(3)]
                  + [G.make_gem("ruby", "flawed") for _ in range(3)] + [G.make_gem("topaz", "regular")])
    cat = forge_menu.catalog(p)
    res = forge_menu.apply(p, next(r for r in cat["temper"] if r["ok"]))
    assert res["ok"] and res["result"].tier == 9 and res["result"] in p.backpack
    assert p.story.done.get("gear_forge")  # Act III still counts it
    res = forge_menu.apply(p, forge_menu.catalog(p)["reforge"][0])
    assert res["ok"] and res["result"].name.startswith(forge.REFORGED_PREFIX)
    assert not any(it.shape == "ingot" for it in p.backpack)
    res = forge_menu.apply(p, forge_menu.catalog(p)["fuse"][0])
    assert res["ok"] and res["result"].rune_rarity == "epic"
    st = forge_menu.catalog(p)["stonework"]
    res = forge_menu.apply(p, next(r for r in st if r["kind"] == "combine"))
    assert res["ok"] and res["result"].name == "Ruby" and res["sfx"] == "gem_combine"
    st = forge_menu.catalog(p)["stonework"]
    res = forge_menu.apply(p, next(r for r in st if r["kind"] == "set" and r["gem"].gem_kind == "topaz"))
    assert res["ok"] and G.stones_in(p.weapon) == [("topaz", "regular")] and res["sfx"] == "gem_set"
    pry = next(r for r in forge_menu.catalog(p)["stonework"] if r["kind"] == "pry")
    res = forge_menu.apply(p, pry)
    assert res["ok"] and not G.stones_in(p.weapon) and res["sfx"] == "gem_pry"
    print("check_every_kind_works_through_the_menu: PASSED")


def check_confirm_rules_and_window_keys():
    p = _player()
    p.backpack = _weapons(8, 3) + _weapons(12, 3) + [I.make_forge_ingot()]
    p.weapon.gems = [["ruby", "regular"]]
    cat = forge_menu.catalog(p)
    t8 = next(r for r in cat["temper"] if "T8" in r["label"])
    t12 = next(r for r in cat["temper"] if "T12" in r["label"])
    pry = next(r for r in cat["stonework"] if r["kind"] == "pry")
    assert not forge_menu.needs_confirm(t8) and forge_menu.needs_confirm(t12) and forge_menu.needs_confirm(pry)
    assert forge_menu.needs_confirm({"kind": "reforge", "use": [I._random_ut("wizard")],
                                     "ingots": [I.make_forge_ingot()] * 2, "label": "x"})
    fw = forge_menu.ForgeWindow()
    fx = []
    fw.on_fx = lambda key, col=None: fx.append(key)
    fw.open_window()
    # cheap: one press forges (after the hammering)
    fw.sel = fw.recipes(p).index(next(r for r in fw.recipes(p) if "T8" in r["label"]))
    assert fw.press_forge(p) == "forging" and fx[-1] == "forge_hammer"
    fw.update(forge_menu.ANIM_TIME / 2, p)
    assert fw.anim is not None and any(it.tier == 8 for it in p.backpack), "nothing happens mid-swing"
    fw.update(forge_menu.ANIM_TIME, p)
    assert fw.result and fw.result["ok"] and fx[-1] == "forge_success" and not any(it.tier == 8 for it in p.backpack)
    # T12: the first press only asks; Esc cancels; two presses forge
    fw.sel = fw.recipes(p).index(next(r for r in fw.recipes(p) if "T12" in r["label"]))
    assert fw.press_forge(p) == "confirm" and fw.confirm
    fw.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""), p)
    assert fw.confirm is None and fw.is_open(), "Esc cancels the confirm first"
    fw.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="\r"), p)
    assert fw.confirm and fw.anim is None
    fw.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="\r"), p)
    assert fw.anim is not None
    fw.update(1.0, p)
    assert any(it.tier == 13 for it in p.backpack), [it.name for it in p.backpack]
    # blocked: pressing does nothing but the fail sound
    fw.set_tab("reforge")
    assert fw.press_forge(p) is None  # no UT -> nothing listed
    fw.set_tab("temper")
    fw.sel = 0
    if fw.selected(p) is not None and not fw.selected(p)["ok"]:
        assert fw.press_forge(p) == "blocked" and fx[-1] == "forge_fail"
    # tabs by keyboard; Esc closes
    fw.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0, unicode=""), p)
    assert fw.tab == "reforge"
    fw.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0, unicode="\t"), p)
    assert fw.tab == "fuse"
    fw.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""), p)
    assert not fw.is_open()
    print("check_confirm_rules_and_window_keys: PASSED")


def check_chat_opens_the_forge_in_single_player():
    import main
    g = main.Game()
    g.player_name = "ForgeSP"
    g.start_run("wizard")
    g.go_nexus()
    anvil = next(n for n in g.nexus_npcs if n.npc_id == "hammerstein")
    g.player.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 40)
    g.player.backpack = _weapons(3, 3)
    assert g._try_talk() and g.dialogue.view()["options"][0] == dialogue.OPEN_FORGE
    g._dialogue_choose(0)
    assert g.dialogue is None and g.forge.is_open()
    # the window is modal: a click on the FORGE button forges, WASD doesn't walk
    r = g.forge.rects()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=r["button"].center))
    g.handle_events()
    assert g.forge.anim is not None
    for _ in range(60):
        g.update(1 / 30)
        g.draw()
    assert any(it.tier == 4 for it in g.player.backpack) and g.forge.result["ok"]
    assert any("hammers away" in m[0] for m in g.feed), g.feed[:3]
    # every tab draws, and the window fits the screen
    for k, _l in forge_menu.TABS:
        g.forge.set_tab(k)
        g.draw()
    assert screen.get_rect().contains(r["win"])
    # leaving the Nexus closes it
    g.enter_realm()
    g.update(1 / 30)
    assert not g.forge.is_open()
    print("check_chat_opens_the_forge_in_single_player: PASSED")


class _FakeSock:
    def __init__(self):
        self.msgs = []

    def sendall(self, data):
        for line in data.decode("utf-8").splitlines():
            if line.strip():
                self.msgs.append(json.loads(line))

    def close(self):
        pass

    def last(self, kind):
        return next((m for m in reversed(self.msgs) if m.get("type") == kind), None)


def check_server_forge_apply_is_authoritative():
    import server
    state = server.ServerState()
    me = _player("CoopSmith")
    sock = _FakeSock()
    s = server.Session("c0", sock, me)
    state.sessions["c0"] = s
    s.zone = server.ZONE_NEXUS
    anvil = next(n for n in state.nexus_npcs if n.npc_id == "hammerstein")
    me.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 40)
    me.backpack = _weapons(5, 3) + _weapons(12, 3) + [I.make_forge_ingot()] + _weapons(9, 2)
    # the chat hands over to the window
    s.conversation = dialogue.start_conversation(me, npc=anvil)
    server._apply_action(state, s, {"action": "dialogue_choice", "idx": 0})
    d = sock.last("dialogue")
    assert d["open_forge"] is True and d["view"] is None and s.conversation is None

    def send(key, **extra):
        server._apply_action(state, s, dict({"action": "forge_apply"}, **key, **extra))
        return sock.last("forge_result")

    cat = forge_menu.catalog(me)
    t5 = next(r for r in cat["temper"] if "T5" in r["label"])
    key5 = forge_menu.recipe_key(me, t5)
    assert key5["idx"] == [0, 1, 2]
    # made-up / stale requests never match
    assert not send(dict(key5, idx=[0, 1, 7]))["ok"]
    assert not send(dict(key5, names=["Excalibur"] * 3))["ok"]
    assert not send(dict(key5, label="Temper 3 T5 weapons -> [T14] Free Loot"))["ok"]
    assert not send({"kind": "temper", "idx": "nope", "names": None, "label": 5})["ok"]
    assert len(me.backpack) == 9
    # unaffordable: the T9 pair
    t9 = next(r for r in cat["temper"] if "T9" in r["label"])
    res = send(forge_menu.recipe_key(me, t9))
    assert not res["ok"] and "Need 3 T9" in res["msg"]
    # T12 needs confirmed=True
    t12 = next(r for r in cat["temper"] if "T12" in r["label"])
    k12 = forge_menu.recipe_key(me, t12)
    res = send(k12)
    assert not res["ok"] and "confirm" in res["msg"]
    # not at the Anvil / not in the Nexus
    me.pos = pygame.Vector2(anvil.pos.x + 900, anvil.pos.y)
    assert not send(key5)["ok"]
    me.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 40)
    s.zone = server.ZONE_REALM
    assert "Anvil" in send(key5)["msg"]
    s.zone = server.ZONE_NEXUS
    assert len(me.backpack) == 9
    # the real thing
    res = send(key5)
    assert res["ok"] and res["result"]["tier"] == 6 and res["sfx"] == "forge_success"
    assert any(it.tier == 6 for it in me.backpack) and len(me.backpack) == 7
    assert any("hammers away" in m[0] for m in s.story_feed)
    # the same request again is now stale (those slots hold other things)
    assert not send(key5)["ok"]
    k12 = forge_menu.recipe_key(me, next(r for r in forge_menu.catalog(me)["temper"] if "T12" in r["label"]))
    res = send(k12, confirmed=True)
    assert res["ok"] and res["result"]["tier"] == 13 and not any(it.shape == "ingot" for it in me.backpack)
    print("check_server_forge_apply_is_authoritative: PASSED")


def check_coop_client_window_round_trip():
    import coop_client

    class FakeLink:
        error = None
        welcome_pid = "c0"

        def __init__(self):
            self.sent, self.dialogues, self.results = [], [], []

        def send(self, obj):
            self.sent.append(obj)

        def get_snapshot(self):
            return None

        def pop_pending_map(self):
            return None

        pop_pending_areas = pop_pending_map

        def pop_vault_items(self):
            return None, None

        pop_bag_state = pop_wish_result = pop_socket_result = lambda self: None

        def pop_whispers(self):
            return []

        pop_trade_notices = pop_pet_results = pop_echo_shop_states = pop_whispers

        def pop_forge_results(self):
            out, self.results = self.results, []
            return out

        def pop_story(self):
            return [], []

        def pop_dialogue(self):
            return self.dialogues.pop(0) if self.dialogues else None

    import server
    state = server.ServerState()
    me = _player("CoopF")
    sock = _FakeSock()
    s = server.Session("c0", sock, me)
    state.sessions["c0"] = s
    s.zone = server.ZONE_NEXUS
    anvil = next(n for n in state.nexus_npcs if n.npc_id == "hammerstein")
    me.pos = pygame.Vector2(anvil.pos.x, anvil.pos.y + 40)
    me.backpack = _weapons(4, 3)
    client = coop_client.CoopClient("127.0.0.1", 0, "CoopF")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY

    def tick(n=1):
        for _ in range(n):
            client._apply_snapshot(server._snapshot_for(state, s))
            client.update(1 / 30)
            client.draw()

    # the server's "Open the Forge" reply opens the client's window
    s.conversation = dialogue.start_conversation(me, npc=anvil)
    server._apply_action(state, s, {"action": "dialogue_choice", "idx": 0})
    client.link.dialogues.append(sock.last("dialogue"))
    tick()
    assert client.zone == "nexus" and client.forge.is_open()
    assert [it.tier for it in client.you.backpack] == [4, 4, 4]
    client.forge.press_forge(client.you)
    tick(60)  # the hammering takes forge_menu.ANIM_TIME; new snapshots (a fresh client.you) keep coming
    sent = [m for m in client.link.sent if m.get("action") == "forge_apply"]
    assert len(sent) == 1 and sent[0]["idx"] == [0, 1, 2] and sent[0]["kind"] == "temper", sent
    assert client.forge.waiting and len(me.backpack) == 3, "the client never forges by itself"
    # the server does it and answers
    server._apply_action(state, s, sent[0])
    client.link.results.append(sock.last("forge_result"))
    tick()
    assert not client.forge.waiting and client.forge.result["ok"] and client.forge.result["result"].tier == 5
    assert [it.tier for it in client.you.backpack] == [5]
    # leaving the Nexus closes it
    s.zone = server.ZONE_REALM
    me.pos = state.realm_sim.spawn_point()
    tick()
    assert not client.forge.is_open()
    print("check_coop_client_window_round_trip: PASSED")


def check_draws_and_fits():
    p = _player()
    p.backpack = (_weapons(8, 3) + _weapons(13, 3) + [I.make_forge_ingot(), I._random_ut("wizard")]
                  + [runes.make_rune("rare", "burn") for _ in range(3)]
                  + [G.make_gem("ruby", "flawed") for _ in range(3)] + [G.make_gem("diamond", "perfect")])
    p.weapon.gems = [["ruby", "regular"], ["ruby", "flawless"]]
    fw = forge_menu.ForgeWindow()
    fw.open_window()
    for size in ((1366, 820), (1920, 1080), (1280, 720)):
        C.SCREEN_W, C.SCREEN_H = size
        surf = pygame.Surface(size)
        r = fw.rects()
        assert surf.get_rect().contains(r["win"]), (size, r["win"])
        assert r["win"].contains(r["detail"]) and r["win"].contains(r["list"]) and r["detail"].contains(r["button"])
        for k, _l in forge_menu.TABS:
            fw.set_tab(k)
            for i in range(len(fw.recipes(p))):
                fw.sel = i
                fw.draw(surf, p, (r["button"].centerx, r["button"].centery))
    C.SCREEN_W, C.SCREEN_H = 1366, 820
    # an empty backpack draws the "nothing here" messages
    q = _player("Empty")
    q.backpack = []
    for k, _l in forge_menu.TABS:
        fw.set_tab(k)
        fw.draw(pygame.Surface((1366, 820)), q)
    print("check_draws_and_fits: PASSED")


if __name__ == "__main__":
    check_catalog_has_no_cap()
    check_blocked_recipes_have_reasons()
    check_every_kind_works_through_the_menu()
    check_confirm_rules_and_window_keys()
    check_chat_opens_the_forge_in_single_player()
    check_server_forge_apply_is_authoritative()
    check_coop_client_window_round_trip()
    check_draws_and_fits()
    print("\nPASSED: forge menu checks all green.")
