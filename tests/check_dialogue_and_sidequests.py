"""
Batch 15 Phase 1A regression checks: friendly NPCs (game/npcs.py), dialogue-game
conversations (game/dialogue.py + ui.draw_dialogue), the 30 side quests
(game/sidequests.py), co-op fairness (shared credit + personal loot bags) and island
treasure chests.

Set RR_SHOT_DIR to also save screenshots (dialogue, quest granted, HUD log, NPC).
Run with: .venv\\Scripts\\python.exe tests\\check_dialogue_and_sidequests.py
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
screen = pygame.display.set_mode((100, 100))

from game import accounts, characters, achievements, items as items_mod
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_dlg_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_dlg_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_dlg_ach_")
items_mod.VAULT_DIR = tempfile.mkdtemp(prefix="rr_dlg_vault_")

from game import dialogue, npcs, sidequests, ui
from game.sidequests import QUESTS, SideQuestProgress, make_quest_item
from game.entities import Player, Enemy, ENEMY_KINDS
from game.realm_sim import RealmSim

SHOT_DIR = os.environ.get("RR_SHOT_DIR")
_REALM = []


def _realm():
    if not _REALM:
        _REALM.append(RealmSim())
    return _REALM[0]


def _shot(surf, name):
    if SHOT_DIR:
        os.makedirs(SHOT_DIR, exist_ok=True)
        pygame.image.save(surf, os.path.join(SHOT_DIR, name))


def _player(name="Tester", pid=None, cls="wizard"):
    p = Player(cls, name=name, pid=pid or name)
    p.sidequests = SideQuestProgress()  # empty board - each check adds exactly what it tests
    return p


def check_content_counts():
    people = [k for k, d in npcs.NPCS.items() if d["kind"] == "person"]
    creatures = [k for k, d in npcs.NPCS.items() if d["kind"] == "creature"]
    assert len(people) == 11 and len(creatures) == 4, (len(people), len(creatures))
    assert len(QUESTS) == 30, len(QUESTS)
    for qid, q in QUESTS.items():
        assert q["target"]["kind"] in ("mob", "npc", "area", "boss"), qid
        if q["giver"] is not None:
            assert q["giver"] in npcs.NPCS and qid in npcs.NPCS[q["giver"]]["quests"], qid
        if q["turn_in"] is not None:
            assert q["turn_in"] in npcs.NPCS, qid
    # every neutral wildlife kind can be talked to, and has a sprite
    from game import sprites
    for kind, d in ENEMY_KINDS.items():
        if d.get("neutral") and d.get("unshootable"):
            assert kind in npcs.WILDLIFE_TALK, kind
            assert sprites.enemy_sprite(kind) is not None
    print("check_content_counts: PASSED")


def check_every_tree_is_finite_and_has_bye():
    for npc_id in npcs.NPCS:
        p = _player("Fin" + npc_id)
        assert dialogue.tree_is_finite(npc_id=npc_id, player=p), npc_id
        # and every node always ends with "Bye."
        conv = dialogue.Conversation(_player("Bye" + npc_id), npc_id=npc_id)
        conv.start()
        for _ in range(60):
            v = conv.view()
            if v is None:
                break
            assert v["options"][-1] == dialogue.BYE, (npc_id, v["options"])
            assert len(v["options"]) <= dialogue.MAX_OPTIONS
            if len(v["options"]) == 1:
                break
            conv.choose(0)
        # chat topics collapse across conversations too (not endless)
        again = dialogue.Conversation(conv.player, npc_id=npc_id)
        again.start()
        topic_labels = {t[1] for t in npcs.NPCS[npc_id]["topics"]}
        assert not topic_labels & set(again.view()["options"]), npc_id
    for kind in npcs.WILDLIFE_TALK:
        assert dialogue.tree_is_finite(wildlife_kind=kind, player=_player("W" + kind)), kind
    print("check_every_tree_is_finite_and_has_bye: PASSED")


def _drive_quest(qid, p):
    """Feeds exactly the events a quest needs; returns True once it's done (turned in if needed)."""
    q = QUESTS[qid]
    sq = p.sidequests
    sq.active[qid] = {"have": 0.0, "seen": []}
    key = q["key"][0] if isinstance(q["key"], (tuple, list)) else q["key"]
    ctx = {"count": q.get("group", 1), "night": True, "person": True,
           "biome": (q.get("biomes") or ("forest",))[0]}
    if q["ev"] == "deliver":
        for _ in range(q["need"]):
            p.backpack.append(make_quest_item(q["item"]))
    elif q.get("distinct"):
        for i in range(q["need"]):
            c = dict(ctx, **{q["distinct"]: f"v{i}"})
            sq.on_event(q["ev"], key, q.get("min_time", 1.0), c, player=p)
    else:
        sq.on_event(q["ev"], key, float(q["need"]), ctx, player=p)
    if q["turn_in"] is not None:
        assert sq.ready(qid, p), qid
        ok, _msgs = sq.turn_in(qid, p)
        assert ok, qid
    return qid not in sq.active


def check_all_30_quests_completable():
    for qid in QUESTS:
        p = _player("Q" + qid)
        xp0 = p.xp + p.level * 10 ** 6
        assert _drive_quest(qid, p), f"{qid} did not complete"
        assert (p.xp + p.level * 10 ** 6) > xp0, f"{qid} paid no XP"
        if QUESTS[qid]["giver"] is not None:
            assert qid in p.sidequests.done and not p.sidequests.can_offer(qid)
        if QUESTS[qid]["ev"] == "deliver":
            assert sidequests.count_quest_items(p, QUESTS[qid]["item"]) == 0, "quest items consumed"
    # board: always BOARD_SIZE giver-less quests, refilled after one completes
    p = Player("wizard", name="Boardy", pid="board")
    board = [q for q in p.sidequests.active if QUESTS[q]["giver"] is None]
    assert len(board) == sidequests.BOARD_SIZE
    assert _drive_quest(board[0], p)
    assert len([q for q in p.sidequests.active if QUESTS[q]["giver"] is None]) == sidequests.BOARD_SIZE
    # reset-on-death quests, stand-near group size and night gating
    p = _player("Rules")
    p.sidequests.active["yeti_tag"] = {"have": 2.0, "seen": []}
    p.sidequests.on_death()
    assert p.sidequests.active["yeti_tag"]["have"] == 0
    p.sidequests.active["herd_whisperer"] = {"have": 0.0, "seen": []}
    p.sidequests.on_event("near", "deer", 5.0, {"count": 2})
    assert p.sidequests.active["herd_whisperer"]["have"] == 0, "a group of 2 isn't a herd of 3"
    p.sidequests.on_event("near", "deer", 5.0, {"count": 3})
    assert p.sidequests.active["herd_whisperer"]["have"] == 5
    p.sidequests.active["moth_to_a_flame"] = {"have": 0.0, "seen": []}
    p.sidequests.on_event("near", "cave_moth", 3.0, {"count": 1, "night": False})
    assert p.sidequests.active["moth_to_a_flame"]["have"] == 0
    # full backpack: reward item waits instead of vanishing
    p = _player("Full")
    p.backpack = [make_quest_item("glowcap") for _ in range(p.backpack_size)]
    p.sidequests.active["pest_control"] = {"have": 0.0, "seen": []}
    p.sidequests.on_event("kill", "goblin", 15.0, {}, player=p)
    assert "pest_control" not in p.sidequests.active
    waiting = len(p.sidequests.pending_items)
    p.backpack.pop()
    msgs = p.sidequests.flush(p)
    assert waiting == 0 or msgs, "pending reward claimed once there's room"
    print("check_all_30_quests_completable: PASSED")


def check_persistence_roundtrip():
    p = _player("Persist")
    p.sidequests.accept("bog_brew")
    p.sidequests.on_event("kill", "bog_crawler", 3.0, {})
    p.sidequests.done.append("camel_bell")
    p.sidequests.talked["murk"] = ["brew"]
    p.backpack.append(make_quest_item("glowcap"))
    d = json.loads(json.dumps(p.full_state()))
    q = Player.from_full_state(d)
    assert q.sidequests.active["bog_brew"]["have"] == 3
    assert "camel_bell" in q.sidequests.done and q.sidequests.talked["murk"] == ["brew"]
    assert q.backpack[-1].quest_key == "glowcap"
    # an old save with no side-quest data loads with a fresh board
    del d["sidequests"]
    old = Player.from_full_state(d)
    assert len(old.sidequests.active) == sidequests.BOARD_SIZE and not old.sidequests.done
    # and a pre-Batch-15 item JSON (no quest_key) still loads
    it = make_quest_item("ember_core").to_json()
    it.pop("quest_key")
    assert items_mod.Item.from_json(it).quest_key == ""
    # quest items can't be fed to a pet
    from game.entities import Pet
    p.pet = Pet("hatchling", p.pos)
    assert not p.feed_pet(len(p.backpack) - 1)
    print("check_persistence_roundtrip: PASSED")


def _post_key(key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def _post_click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def check_singleplayer_dialogue_gui():
    import main
    from game import minimap
    g = main.Game()
    g.player_name = "SPTalker"
    g.start_run("wizard")
    g.player.sidequests = SideQuestProgress()
    g.realm_sim = _realm()
    g.realm_minimap = minimap.MinimapState()
    g.state = main.STATE_REALM
    moss = next(n for n in g.realm_sim.npcs if n.npc_id == "mossbeard")
    g.player.pos = pygame.Vector2(moss.pos) + pygame.Vector2(30, 0)
    g.update(1 / 60)
    g.draw()
    _shot(g.screen, "p1a_npc_in_world.png")
    _post_key(pygame.K_f)
    g.handle_events()
    assert g.dialogue is not None and g.dialogue.npc_id == "mossbeard"
    view = g.dialogue.view()
    assert len(view["options"]) >= 3 and view["options"][-1] == dialogue.BYE
    g.draw()
    _shot(g.screen, "p1a_dialogue_options.png")
    # click the quest offer, then accept it with the "1" key
    offer_idx = view["options"].index(npcs.NPCS["mossbeard"]["quests"]["mossbeard_mushrooms"]["label"])
    _post_click(ui.dialogue_option_rects(view)[offer_idx].center)
    g.handle_events()
    assert g.dialogue.node[0] == "offer"
    _post_key(pygame.K_1)
    g.handle_events()
    assert "mossbeard_mushrooms" in g.player.sidequests.active
    g.update(1 / 60)
    g.draw()
    _shot(g.screen, "p1a_quest_granted.png")
    _post_key(pygame.K_ESCAPE)  # Esc = Bye
    g.handle_events()
    assert g.dialogue is None
    # the HUD log now lists the side quest
    g.quest_log_expanded = True
    g.update(1 / 60)
    g.draw()
    _shot(g.screen, "p1a_hud_log_side_quests.png")
    # hand in: bring 6 glowcaps, talk again, the hand-in option comes first
    for _ in range(6):
        g.player.backpack.append(make_quest_item("glowcap"))
    xp_before = g.player.xp + g.player.level * 10 ** 6
    _post_key(pygame.K_f)
    g.handle_events()
    assert g.dialogue.view()["options"][0] == "I've done what you asked."
    _post_key(pygame.K_1)
    g.handle_events()
    assert "mossbeard_mushrooms" in g.player.sidequests.done
    assert sidequests.count_quest_items(g.player, "glowcap") == 0
    assert g.player.xp + g.player.level * 10 ** 6 > xp_before
    _post_key(pygame.K_ESCAPE)
    g.handle_events()
    assert g.dialogue is None
    # animal speak: talking to wildlife in the Realm
    deer = Enemy("deer", g.player.pos + pygame.Vector2(200, 0))
    g.realm_sim.enemies.append(deer)
    g.player.pos = pygame.Vector2(deer.pos) + pygame.Vector2(20, 0)
    far = [n for n in g.realm_sim.npcs if n.pos.distance_to(g.player.pos) < npcs.TALK_RADIUS]
    if not far:
        g._context_action()
        assert g.dialogue is not None and g.dialogue.wildlife_kind == "deer"
        g._dialogue_choose(len(g.dialogue.view()["options"]) - 1)
    g.realm_sim.enemies.remove(deer)
    print("check_singleplayer_dialogue_gui: PASSED")


class FakeSock:
    def __init__(self):
        self.msgs = []

    def sendall(self, data):
        for line in data.decode("utf-8").splitlines():
            self.msgs.append(json.loads(line))

    def last(self, kind):
        return next((m for m in reversed(self.msgs) if m.get("type") == kind), None)


def _server_with(names):
    import server
    state = server.ServerState()
    state.realm_sim = _realm()
    sessions = []
    for name in names:
        p = Player("wizard", name=name, pid=name)
        p.sidequests = SideQuestProgress()
        s = server.Session(name, FakeSock(), p)
        s.zone = server.ZONE_REALM
        state.sessions[name] = s
        sessions.append(s)
    return server, state, sessions


def check_coop_dialogue_and_turn_in():
    server, state, (s,) = _server_with(["CoopTalker"])
    murk = next(n for n in state.realm_sim.npcs if n.npc_id == "murk")
    s.player.pos = pygame.Vector2(murk.pos) + pygame.Vector2(25, 0)
    server._apply_action(state, s, {"action": "fish"})  # F in the Realm -> talks first
    view = s.sock.last("dialogue")["view"]
    assert view and view["name"] == "Madame Murk"
    idx = view["options"].index(npcs.NPCS["murk"]["quests"]["bog_brew"]["label"])
    server._apply_action(state, s, {"action": "dialogue_choice", "idx": idx})
    server._apply_action(state, s, {"action": "dialogue_choice", "idx": 0})  # "I'll do it!"
    assert "bog_brew" in s.player.sidequests.active
    server._apply_action(state, s, {"action": "dialogue_close"})
    assert s.conversation is None and s.sock.last("dialogue")["view"] is None
    # 8 real bog crawler kills through RealmSim._reward
    sim = state.realm_sim
    sim._players_by_pid = {s.pid: s.player}
    for _ in range(8):
        e = Enemy("bog_crawler", s.player.pos + pygame.Vector2(60, 0))
        sim._credit_hit(e, s.pid, 10)
        e.hp, e.alive = 0, False
        sim._reward(e, s.player)
    assert s.player.sidequests.ready("bog_brew", s.player)
    server._apply_action(state, s, {"action": "fish"})
    view = s.sock.last("dialogue")["view"]
    assert view["options"][0] == "I've done what you asked."
    server._apply_action(state, s, {"action": "dialogue_choice", "idx": 0})
    assert "bog_brew" in s.player.sidequests.done
    snap = server._snapshot_for(state, s)
    assert "sidequests" in snap and any(n["id"] == "murk" for n in snap["npcs"])
    print("check_coop_dialogue_and_turn_in: PASSED")


def check_coop_fairness_personal_loot():
    server, state, (a, b) = _server_with(["Alpha", "Bravo"])
    sim = state.realm_sim
    spot = sim.spawn_point() + pygame.Vector2(0, -3 * 32)
    a.player.pos = pygame.Vector2(spot)
    b.player.pos = pygame.Vector2(spot) + pygame.Vector2(30, 0)
    for s in (a, b):
        s.player.sidequests.active["pest_control"] = {"have": 0.0, "seen": []}
    sim._players_by_pid = {a.pid: a.player, b.pid: b.player}
    sim.ground_items = []
    import random
    random.seed(4)
    for _ in range(12):  # enough kills that both players surely get some loot
        e = Enemy("goblin", pygame.Vector2(spot) + pygame.Vector2(10, 10))
        sim._credit_hit(e, a.pid, 5)
        sim._credit_hit(e, b.pid, 5)
        e.hp, e.alive = 0, False
        sim._reward(e, a.player)  # Alpha lands the last hit...
    # ...but Bravo gets the credit too
    assert a.player.sidequests.active["pest_control"]["have"] == 12
    assert b.player.sidequests.active["pest_control"]["have"] == 12
    owners = {g.owner_pid for g in sim.ground_items}
    assert owners == {"Alpha", "Bravo"}, owners
    snap_a = server._snapshot_for(state, a)
    ids_a = {g["id"] for g in snap_a["ground_items"]}
    assert ids_a and all(sim.bag_by_id(i).owner_pid == "Alpha" for i in ids_a)
    bravo_bag = next(g for g in sim.ground_items if g.owner_pid == "Bravo")
    assert bravo_bag.id not in ids_a
    from game.entities import withdraw_from_bag, find_nearby_bag
    before = len(a.player.backpack)
    assert withdraw_from_bag(sim.ground_items, bravo_bag.id, 0, a.player) is None
    assert len(a.player.backpack) == before
    bag = find_nearby_bag(sim.ground_items, bravo_bag.pos, a.pid, radius=400)
    assert bag is None or bag.owner_pid == "Alpha"
    assert withdraw_from_bag(sim.ground_items, bravo_bag.id, 0, b.player) is not None
    print("check_coop_fairness_personal_loot: PASSED")


def check_island_chest_quest_items():
    sim = _realm()
    assert len(sim.island_chests) == len(sim.islands) >= 8
    p = _player("Chesty", cls="archer")
    p.sidequests.accept("camel_bell")
    p.sidequests.accept("rum_run")
    ch = sim.island_chests[0]
    ch["opened"].discard(p.pid)
    p.pos = pygame.Vector2(ch["pos"])
    sim._players_by_pid = {p.pid: p}
    sim.ground_items = []
    assert sim.open_island_chest(p)
    got = [it for g in sim.ground_items if g.owner_pid == p.pid for it in g.items]
    keys = {getattr(it, "quest_key", "") for it in got}
    assert {"camel_bell", "driftwood_rum"} <= keys, keys
    assert any(not getattr(it, "quest_key", "") for it in got), "plus real loot"
    assert not sim.open_island_chest(p), "one opening per player until the island is calmed again"
    # calming the island refills it
    isl = sim.islands[0]
    isl["alive_guardians"] = 1
    boss = Enemy("goblin", isl["pos"])
    boss.island_idx = isl["idx"]
    sim._progress_island_event(boss, p, [p])
    assert not ch["opened"]
    print("check_island_chest_quest_items: PASSED")


def check_npcs_untouchable_and_placed():
    sim = _realm()
    assert len(sim.npcs) >= 12
    for n in sim.npcs:
        assert n not in sim.enemies
        assert not sim.is_solid(n.pos.x, n.pos.y), n.npc_id
    import server
    state = server.ServerState()
    assert any(n.npc_id == "bitterwick" for n in state.nexus_npcs)
    print("check_npcs_untouchable_and_placed: PASSED")


def check_coop_client_dialogue_gui():
    import coop_client
    import server
    state = server.ServerState()
    me = Player("wizard", name="CoopGui", pid="g0")
    me.sidequests.accept("barkeeps_tab")
    bw = next(n for n in state.nexus_npcs if n.npc_id == "bitterwick")
    me.pos = pygame.Vector2(bw.pos) + pygame.Vector2(24, 0)
    conv = dialogue.start_conversation(me, npc=bw)

    class FakeLink:
        error = None
        welcome_pid = "g0"

        def __init__(self):
            self.sent = []
            self.dlg = [{"type": "dialogue", "view": conv.view()}]

        def send(self, obj):
            self.sent.append(obj)

        def get_snapshot(self):
            return None

        def pop_vault_items(self):
            return None, None

        def pop_pending_map(self):
            return None

        pop_bag_state = pop_wish_result = pop_socket_result = pop_pending_map

        def pop_whispers(self):
            return []

        pop_trade_notices = pop_pet_results = pop_echo_shop_states = pop_whispers

        def pop_story(self):
            return [], []

        def pop_dialogue(self):
            return self.dlg.pop() if self.dlg else None

    client = coop_client.CoopClient("127.0.0.1", 0, "CoopGui")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY
    snap = {"zone": "nexus", "you": me.full_state(), "players": [], "chats": [], "trade": None,
            "quest_log": me.story.quest_log(), "sidequests": me.sidequests.log(me),
            "npcs": [n.net_state() for n in state.nexus_npcs]}
    client._apply_snapshot(snap)
    assert client.dialogue_view is not None and client.dialogue_view["name"] == "Barkeep Bitterwick"
    assert any(e["id"] == "barkeeps_tab" for e in client.sidequest_log)
    assert client.npcs and client.npcs[0].npc_id == "bitterwick"
    client.update(0.016)
    client.draw()
    _shot(client.screen, "p1a_coop_dialogue.png")
    _post_key(pygame.K_1)
    client.handle_events()
    assert any(m.get("action") == "dialogue_choice" and m.get("idx") == 0 for m in client.link.sent)
    _post_key(pygame.K_ESCAPE)  # Esc = Bye: closes locally right away
    client.handle_events()
    assert client.dialogue_view is None
    assert client.link.sent[-1]["idx"] == len(conv.view()["options"]) - 1
    print("check_coop_client_dialogue_gui: PASSED")


if __name__ == "__main__":
    check_content_counts()
    check_every_tree_is_finite_and_has_bye()
    check_all_30_quests_completable()
    check_persistence_roundtrip()
    check_npcs_untouchable_and_placed()
    check_island_chest_quest_items()
    check_coop_fairness_personal_loot()
    check_coop_dialogue_and_turn_in()
    check_singleplayer_dialogue_gui()
    check_coop_client_dialogue_gui()
    print("PASSED: dialogue + side quest checks all green.")
