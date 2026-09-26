"""
Finishing checks for features earlier batches left partial: rotating live
events (schedule + RR_EVENT override + the server relaying its event to co-op
clients), the Echo Keeper shop in co-op (server-authoritative purchase), and
the pending-UT-socket highlight in the backpack.
"""
import importlib
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

from game import achievements, items, characters, accounts
achievements._DIR = tempfile.mkdtemp(prefix="rr_pf_ach_")
items.VAULT_DIR = tempfile.mkdtemp(prefix="rr_pf_vault_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_pf_char_")
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_pf_acc_")

from game import live_events, ui, world
from game.entities import Player
from game.items import Item, SLOT_WEAPON


def _reload_events(forced=None, rotation="on"):
    if forced is None:
        os.environ.pop("RR_EVENT", None)
    else:
        os.environ["RR_EVENT"] = forced
    os.environ["RR_EVENT_ROTATION"] = rotation
    importlib.reload(live_events)


def check_rotation_schedule_and_override():
    _reload_events(None, "on")
    W, n = live_events.EVENT_WINDOW, len(live_events.SCHEDULE)
    seen = [live_events.current_event(now=k * W + 1) for k in range(n)]
    assert seen == [live_events.SCHEDULE[k % n] for k in range(n)], seen
    assert None in seen and len({e for e in seen if e}) >= 3, "rotation needs real events AND quiet slots"
    assert live_events.current_event(now=5 * W + 10) == live_events.current_event(now=5 * W + W - 1)
    _reload_events("happy_hour", "on")
    assert all(live_events.current_event(now=k * W) == "happy_hour" for k in range(n)), "RR_EVENT forces"
    assert live_events.get_multiplier("xp") == 1.5
    _reload_events("none", "on")
    assert live_events.current_event(now=W + 1) is None, "RR_EVENT=none forces no event"
    _reload_events(None, "off")
    assert live_events.current_event(now=W + 1) is None and live_events.get_multiplier("loot_rolls") == 1.0
    print("check_rotation_schedule_and_override: PASSED")


class FakeSock:
    def __init__(self):
        self.msgs = []

    def sendall(self, data):
        for line in data.decode("utf-8").splitlines():
            self.msgs.append(json.loads(line))


def _nexus_session(state, server, name):
    p = Player("wizard", name=name, pid=name)
    p.pos = server._nexus_spawn_pos(state)
    s = server.Session(name, FakeSock(), p)
    state.sessions[s.pid] = s
    return s


def check_snapshot_carries_server_event():
    import server
    _reload_events("blood_moon_week", "on")
    state = server.ServerState()
    s = _nexus_session(state, server, "EvA")
    assert server._snapshot_for(state, s)["live_event"] == "blood_moon_week"
    _reload_events(None, "off")
    assert server._snapshot_for(state, s)["live_event"] is None
    print("check_snapshot_carries_server_event: PASSED")


def check_coop_echo_purchase():
    import server
    state = server.ServerState()
    s = _nexus_session(state, server, "EchoBuyer")
    grid = state.nexus_map.grid
    keeper = next((x, y) for y in range(len(grid)) for x in range(len(grid[0]))
                  if grid[y][x] == world.ECHO_KEEPER_TILE)
    accounts.touch_account("EchoBuyer")
    accounts.add_echoes("EchoBuyer", 500)
    before_slots, before_echoes = s.player.backpack_size, accounts.get_echoes("EchoBuyer")
    # off the keeper tile: refused (state is still reported, nothing bought)
    server._apply_action(state, s, {"action": "echo_buy", "item": "backpack_slot"})
    assert s.player.backpack_size == before_slots and accounts.get_echoes("EchoBuyer") == before_echoes
    s.player.pos = pygame.Vector2((keeper[0] + 0.5) * 32, (keeper[1] + 0.5) * 32)
    server._apply_action(state, s, {"action": "echo_shop_open"})
    server._apply_action(state, s, {"action": "echo_buy", "item": "backpack_slot"})
    last = [m for m in s.sock.msgs if m.get("type") == "echo_shop_state"][-1]
    assert last["ok"] and s.player.backpack_size == before_slots + 1
    assert accounts.get_echoes("EchoBuyer") < before_echoes and last["echoes"] == accounts.get_echoes("EchoBuyer")
    assert last["unlocks"]["backpack_slots"] == 1
    # the shared row builder shows the next price / owned states from that same data
    rows = accounts.echo_shop_rows(last["unlocks"])
    assert rows[0][1] == "backpack_slot" and "(1/" in rows[0][0]
    print("check_coop_echo_purchase: PASSED")


def check_socket_highlight():
    p = Player("wizard", "Sock", pid="sock")
    p.backpack = [Item("Proc", SLOT_WEAPON, 3, "staff", min_dmg=1, max_dmg=2),
                  Item("Target", SLOT_WEAPON, 5, "staff", min_dmg=3, max_dmg=4)]
    surf = pygame.Surface((1366, 820))
    ui.draw_inventory(surf, p, (-1, -1), socket_pair=(0, 1))
    rect = ui.backpack_slot_rects(p)[1].inflate(4, 4)
    col = surf.get_at((rect.x + rect.w // 2, rect.y + 1))
    assert (col.r, col.g, col.b) == (200, 150, 255), f"pending socket target not highlighted: {col}"
    plain = pygame.Surface((1366, 820))
    ui.draw_inventory(plain, p, (-1, -1))
    assert tuple(plain.get_at((rect.x + rect.w // 2, rect.y + 1)))[:3] != (200, 150, 255)
    print("check_socket_highlight: PASSED")


def check_sp_echo_shop_closes():
    """User report: Enter on "Close" opened chat instead, and the X "didn't work" -
    closing while still on the Echo Keeper tile reopened the shop next frame."""
    import main
    g = main.Game()
    g.state = main.STATE_NEXUS
    g.player = Player("wizard", "ShopCloser", pid="sp")
    g.player_name = "ShopCloser"
    grid = g.nexus_map.grid
    kx, ky = next((x, y) for y in range(len(grid)) for x in range(len(grid[0]))
                  if grid[y][x] == world.ECHO_KEEPER_TILE)
    g.player.pos = pygame.Vector2((kx + 0.5) * 32, (ky + 0.5) * 32)
    g.update(1 / 30)
    assert g.echo_shop_open
    # Enter on the Close row closes it and does NOT open chat
    g.echo_shop_selected = len(g._echo_shop_items()) - 1
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    g.handle_events()
    assert not g.echo_shop_open and not g.chat_open
    for _ in range(5):
        g.update(1 / 30)
    assert not g.echo_shop_open, "closing while still on the tile must not reopen it"
    # the X button works too, after stepping off and back on
    g.player.pos.x += 32 * 3
    g.update(1 / 30)
    g.player.pos.x -= 32 * 3
    g.update(1 / 30)
    assert g.echo_shop_open
    x_rect = ui.echo_shop_close_button_rect(g._echo_shop_items())
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=x_rect.center))
    g.handle_events()
    for _ in range(5):
        g.update(1 / 30)
    assert not g.echo_shop_open
    print("check_sp_echo_shop_closes: PASSED")


if __name__ == "__main__":
    check_rotation_schedule_and_override()
    check_snapshot_carries_server_event()
    check_coop_echo_purchase()
    check_socket_highlight()
    check_sp_echo_shop_closes()
    _reload_events(None, "off")
    print("PASSED: partial-feature checks all green.")
