"""
Regression checks for the co-op trade consent + no-item-loss rework (server.py's
trade_invites / reference-based offers), the trade/invite/inspect UI, and the
drag-robustness hardening in both clients (a drag never survives a zone/state
change; a mouse-up with no drag in progress is a no-op, never a crash).

Drives server.py's real ServerState/_apply_action/step headless with fake
sockets; the client checks build real CoopClient/Game objects without a network.

Run with: .venv\\Scripts\\python.exe tests\\check_trade_and_interaction.py
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

import server
from game import constants as C, ui
from game.entities import Player
from game.items import Item, SLOT_WEAPON

SHOT_DIR = os.environ.get("RR_SHOT_DIR")  # optional: save rendered panels here for a manual look


class FakeSock:
    def __init__(self):
        self.msgs = []

    def sendall(self, data):
        for line in data.decode("utf-8").splitlines():
            self.msgs.append(json.loads(line))

    def notices(self):
        return [m["message"] for m in self.msgs if m.get("type") == "trade_notice"]


def _sword(name, tier=1):
    return Item(name, SLOT_WEAPON, tier, "sword", min_dmg=1, max_dmg=2)


_STATE = server.ServerState()  # building the realm is the slow part - reuse one


def _setup():
    state = _STATE
    state.sessions.clear()
    state.trades.clear()
    state.trade_invites.clear()
    state.pending_actions = []
    state.chat_queue = []
    sessions = []
    for i, name in enumerate(("Alice", "Bob", "Cara")):
        p = Player("wizard", name=name, pid=f"p{i}")
        p.pos = server._nexus_spawn_pos(state) + pygame.Vector2(i * 30, 0)
        p.backpack = [_sword(f"{name}Sword{j}") for j in range(2)]
        s = server.Session(f"p{i}", FakeSock(), p)
        state.sessions[s.pid] = s
        sessions.append(s)
    return state, sessions


def _act(state, s, action, **kw):
    server._apply_action(state, s, dict(action=action, **kw))


def _open(state, a, b):
    _act(state, a, "trade_request", pid=b.pid)
    _act(state, b, "trade_invite_accept")
    assert a.trade_id is not None and a.trade_id == b.trade_id
    return state.trades[a.trade_id]


def _tick(state, seconds, dt=0.1):
    for _ in range(int(round(seconds / dt))):
        server.step(state, dt)


def check_invite_accept_opens_trade():
    state, (a, b, _) = _setup()
    _act(state, a, "trade_request", pid=b.pid)
    assert a.trade_id is None and b.trade_id is None, "a request alone must not open a trade"
    assert server._trade_invite_for(state, b)["from_name"] == "Alice"
    assert server._trade_invite_for(state, a) is None
    assert any("sent to Bob" in n for n in a.sock.notices())
    _act(state, b, "trade_invite_accept")
    assert a.trade_id is not None and a.trade_id == b.trade_id
    assert server._trade_invite_for(state, b) is None
    print("check_invite_accept_opens_trade: PASSED")


def check_decline_and_expiry():
    state, (a, b, _) = _setup()
    _act(state, a, "trade_request", pid=b.pid)
    _act(state, b, "trade_invite_decline")
    assert b.trade_id is None and not state.trade_invites
    assert any("declined" in n for n in a.sock.notices())
    _act(state, b, "trade_invite_accept")  # nothing pending any more
    assert b.trade_id is None

    _act(state, a, "trade_request", pid=b.pid)
    _tick(state, server.TRADE_INVITE_SECONDS + 0.5, dt=0.5)
    assert not state.trade_invites and b.trade_id is None
    assert any("expired" in n for n in a.sock.notices())

    # walking away invalidates a pending invite too
    _act(state, a, "trade_request", pid=b.pid)
    b.player.pos += pygame.Vector2(server.TRADE_RANGE * 5, 0)
    server._tick_trades(state, 0.1)
    assert not state.trade_invites
    print("check_decline_and_expiry: PASSED")


def check_mutual_request_opens():
    state, (a, b, _) = _setup()
    _act(state, a, "trade_request", pid=b.pid)
    _act(state, b, "trade_request", pid=a.pid)
    assert a.trade_id is not None and a.trade_id == b.trade_id, "B asking A back must open at once"
    assert not state.trade_invites
    print("check_mutual_request_opens: PASSED")


def check_offers_stay_in_backpack_and_swap():
    state, (a, b, _) = _setup()
    trade = _open(state, a, b)
    a_item, b_item = a.player.backpack[0], b.player.backpack[1]
    _act(state, a, "trade_offer", idx=0)
    _act(state, a, "trade_offer", idx=0)  # offering the same item twice is ignored
    _act(state, b, "trade_offer", idx=1)
    assert len(trade.offer_a) == 1 and len(a.player.backpack) == 2, "offered items stay in the backpack"
    assert server._trade_info_for(state, a)["my_offer_idx"] == [0]
    _act(state, a, "trade_accept")
    _act(state, b, "trade_accept")
    _tick(state, server.TRADE_CONFIRM_SECONDS + 0.3)
    assert a.trade_id is None and trade.id not in state.trades
    assert any(it is b_item for it in a.player.backpack) and not any(it is a_item for it in a.player.backpack)
    assert any(it is a_item for it in b.player.backpack) and not any(it is b_item for it in b.player.backpack)
    assert len(a.player.backpack) == 2 and len(b.player.backpack) == 2
    print("check_offers_stay_in_backpack_and_swap: PASSED")


def check_withdraw_and_cancel_lose_nothing():
    state, (a, b, _) = _setup()
    trade = _open(state, a, b)
    before = list(a.player.backpack)
    _act(state, a, "trade_offer", idx=0)
    _act(state, a, "trade_offer", idx=1)
    _act(state, a, "trade_withdraw", idx=0)
    assert len(trade.offer_a) == 1 and a.player.backpack == before
    # fill the backpack mid-trade (a pickup), unequip into it too, then cancel
    while len(a.player.backpack) < a.player.backpack_size - 1:
        a.player.backpack.append(_sword("Loot"))
    _act(state, a, "unequip", slot="weapon")
    count = len(a.player.backpack)
    _act(state, b, "trade_cancel")
    assert a.trade_id is None and b.trade_id is None
    assert len(a.player.backpack) == count and all(it in a.player.backpack for it in before)
    assert any("cancelled" in n for n in a.sock.notices())
    print("check_withdraw_and_cancel_lose_nothing: PASSED")


def check_full_backpack_shows_reason():
    state, (a, b, _) = _setup()
    trade = _open(state, a, b)
    while len(a.player.backpack) < a.player.backpack_size:
        a.player.backpack.append(_sword("Filler"))
    # Alice gives nothing, receives two - no room
    _act(state, b, "trade_offer", idx=0)
    _act(state, b, "trade_offer", idx=1)
    _act(state, a, "trade_accept")
    _act(state, b, "trade_accept")
    _tick(state, server.TRADE_CONFIRM_SECONDS + 0.3)
    assert a.trade_id == trade.id and trade.id in state.trades, "a full backpack must not cancel the trade"
    info = server._trade_info_for(state, a)
    assert "Alice" in (info["status"] or "") and "full" in info["status"]
    assert not trade.accept_a and not trade.accept_b
    assert len(a.player.backpack) == a.player.backpack_size and len(b.player.backpack) == 2
    # making room + re-accepting completes it
    a.player.backpack = a.player.backpack[:4]
    _act(state, a, "trade_accept")
    _act(state, b, "trade_accept")
    _tick(state, server.TRADE_CONFIRM_SECONDS + 0.3)
    assert a.trade_id is None and len(a.player.backpack) == 6 and len(b.player.backpack) == 0
    print("check_full_backpack_shows_reason: PASSED")


def check_prune_when_offered_item_moves():
    state, (a, b, _) = _setup()
    trade = _open(state, a, b)
    offered = a.player.backpack[0]
    _act(state, a, "trade_offer", idx=0)
    _act(state, a, "trade_offer", idx=1)
    _act(state, a, "trade_accept")
    _act(state, a, "swap_backpack", i=0, j=1)  # moving within the backpack keeps the offer
    server._tick_trades(state, 0.1)
    assert len(trade.offer_a) == 2 and trade.accept_a
    _act(state, a, "equip", idx=a.player.backpack.index(offered))  # equipping it removes it
    server._tick_trades(state, 0.1)
    assert len(trade.offer_a) == 1 and not any(it is offered for it in trade.offer_a)
    assert not trade.accept_a, "a pruned offer must reset accepts"
    assert a.player.weapon is offered
    print("check_prune_when_offered_item_moves: PASSED")


def check_disconnect_mid_trade():
    state, (a, b, _) = _setup()
    _open(state, a, b)
    _act(state, a, "trade_offer", idx=0)
    before = list(a.player.backpack)
    del state.sessions[b.pid]
    server._tick_trades(state, 0.1)
    assert a.trade_id is None and a.player.backpack == before
    print("check_disconnect_mid_trade: PASSED")


def _save(surf, name):
    if SHOT_DIR:
        pygame.image.save(surf, os.path.join(SHOT_DIR, name))


def check_ui_panels_render():
    surf = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    surf.fill((30, 40, 35))
    item = _sword("Test Blade", tier=3)
    trade = {"other_name": "Bob", "my_offer": [item.to_json()], "their_offer": [item.to_json()] * 3,
             "my_accept": True, "their_accept": False, "timer": 2.4,
             "status": "Alice's backpack is too full", "my_offer_idx": [0]}
    ui.draw_trade_panel(surf, trade, "Alice", mouse_pos=ui.trade_offer_slot_rects(mine=True)[0].center)
    assert ui.trade_my_offer_area_rect().contains(ui.trade_offer_slot_rects(mine=True)[7])
    ui.draw_trade_invite(surf, {"from_name": "Bob", "time_left": 17.2}, mouse_pos=(-1, -1))
    acc, dec = ui.trade_invite_button_rects()
    assert not acc.colliderect(dec)
    peer = Player("archer", name="Bob", pid="p1")
    peer.weapon, peer.net_totals = item, {"att": 20, "deF": 5, "spd": 30, "dex": 25, "vit": 10, "wis": 12}
    ui.draw_inspect_panel(surf, peer, mouse_pos=ui.inspect_slot_rects()[0].center)
    panel = ui.inspect_panel_rect()
    assert all(panel.contains(r) for r in ui.inspect_slot_rects()), "inspect slots must fit the panel"
    assert panel.contains(ui.inspect_close_button_rect())
    me = Player("wizard", name="Alice", pid="p0")
    me.backpack = [item, _sword("B")]
    ui.draw_inventory(surf, me, (-1, -1), highlighted={0})
    _save(surf, "trade_invite_inspect.png")
    print("check_ui_panels_render: PASSED")


def check_coop_client_drag_hardening():
    import coop_client

    class FakeLink:
        error = None

        def __init__(self):
            self.sent = []

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

        def pop_dialogue(self):
            return None

    client = coop_client.CoopClient("127.0.0.1", 0, "Tester")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY
    # mouse-up with no drag in progress / no player must be a harmless no-op
    client.drag_from = None
    client._inventory_mouse_up((10, 10))
    client._vault_mouse_up((10, 10))
    client.you = None
    client.drag_from, client.drag_start_pos = ("backpack", 0), (10, 10)
    client._inventory_mouse_up((10, 10))

    me = Player("wizard", name="Tester", pid="p0")
    me.backpack = [_sword("A"), _sword("B")]
    snap = {"zone": "nexus", "you": me.full_state(), "players": [], "chats": [], "trade": None}
    client._apply_snapshot(snap)
    client.drag_from, client.drag_start_pos = ("backpack", 0), (10, 10)
    client.pending_socket = (0, 1)
    snap2 = dict(snap, zone="bazaar", ground_items=[])
    client._apply_snapshot(snap2)  # zone change mid-drag
    assert client.drag_from is None and client.pending_socket is None
    client._inventory_mouse_up((10, 10))
    client.update(0.016)
    client.draw()

    # trade open: a plain click on a backpack item offers it (no equip, no drop)
    trade = {"other_name": "Bob", "my_offer": [], "their_offer": [], "my_accept": False,
             "their_accept": False, "timer": None, "status": None, "my_offer_idx": []}
    client._apply_snapshot(dict(snap2, trade=trade, trade_invite={"from_name": "Cara", "time_left": 9}))
    client.link.sent.clear()
    pos = ui.backpack_slot_rects(client.you)[1].center
    client._trade_click(pos)
    client._inventory_mouse_up(pos)
    assert client.link.sent == [{"type": "action", "action": "trade_offer", "idx": 1}], client.link.sent
    # drag onto "my offer" offers; drag elsewhere off-dock does NOT drop it on the ground
    client.link.sent.clear()
    client._trade_click(pos)
    client._inventory_mouse_up(ui.trade_my_offer_area_rect().center)
    client._trade_click(pos)
    client._inventory_mouse_up((5, C.SCREEN_H // 2))
    assert client.link.sent == [{"type": "action", "action": "trade_offer", "idx": 1}], client.link.sent
    # invite prompt buttons
    client.link.sent.clear()
    assert client._trade_invite_click(ui.trade_invite_button_rects()[1].center)
    assert client.link.sent[-1]["action"] == "trade_invite_decline" and client.trade_invite is None
    # context menu has Inspect; picking it opens the inspect panel for that peer
    peer = Player("archer", name="Bob", pid="p1")
    peer.pos = pygame.Vector2(client.you.pos)
    client.peers = [peer]
    client.context_menu = {"pid": "p1", "name": "Bob", "pos": (300, 300)}
    labels = client._context_menu_labels()
    assert "Inspect" in labels
    rect = ui.context_menu_rects((300, 300), labels)[labels.index("Inspect")]
    client._context_menu_click(rect.center)
    assert client.inspect_pid == "p1"
    client._draw_play(client.screen)
    _save(client.screen, "coop_trade_screen.png")
    print("check_coop_client_drag_hardening: PASSED")


def check_singleplayer_drag_hardening():
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.player.backpack = [_sword("A")]
    game.drag_from = None
    game._inventory_mouse_up((10, 10))
    game._vault_mouse_up((10, 10))
    game._drag_state = game.state
    game.drag_from, game.drag_start_pos = ("backpack", 0), (10, 10)
    game.enter_realm()  # state change mid-drag (portal)
    game.update(0.016)
    assert game.drag_from is None, "a drag must not survive a state change"
    game._inventory_mouse_up((10, 10))
    assert len(game.player.backpack) == 1
    print("check_singleplayer_drag_hardening: PASSED")


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="rr_trade_")
    from game import characters, accounts
    characters.CHAR_DIR = tmp
    accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_trade_acc_")
    check_invite_accept_opens_trade()
    check_decline_and_expiry()
    check_mutual_request_opens()
    check_offers_stay_in_backpack_and_swap()
    check_withdraw_and_cancel_lose_nothing()
    check_full_backpack_shows_reason()
    check_prune_when_offered_item_moves()
    check_disconnect_mid_trade()
    check_ui_panels_render()
    check_coop_client_drag_hardening()
    check_singleplayer_drag_hardening()
    print("PASSED: trade + interaction checks all green.")
