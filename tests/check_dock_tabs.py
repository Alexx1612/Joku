"""
The right dock's 4 tabs: Items (equipment + backpack), Bag 2 (a second 12-slot backpack),
Shards (12 Weapon Shard slots, the top 4 ACTIVE) and Pet.

- Tab cycles (skipping Pet without one); clicking a label picks a tab; dragging onto a
  label opens it
- each tab's 4x3 grid sits where the backpack is and fits on screen; the equip row stays
- real mouse drag-and-drop moves items between the backpack, Bag 2, the Shard slots and
  the equipment (shards only into shard slots), and a full backpack overflows into Bag 2
- the co-op client sends move_item for the new tabs

Run with: .venv\\Scripts\\python.exe tests\\check_dock_tabs.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()

from game import accounts, characters, achievements
accounts.ACCOUNTS_DIR = tempfile.mkdtemp(prefix="rr_tabs_acc_")
characters.CHAR_DIR = tempfile.mkdtemp(prefix="rr_tabs_chr_")
achievements._DIR = tempfile.mkdtemp(prefix="rr_tabs_ach_")

from game import ui, runes, items as I, constants as C
from game.entities import Player

SHOT_DIR = os.environ.get("RR_SHOT_DIR")


def _key(g, k):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))
    g.handle_events()


def _drag(g, a, b):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=a))
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=b, rel=(0, 0), buttons=(1, 0, 0)))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=b))
    g.handle_events()


def check_layout_fits():
    tabs = ui.panel_tab_rects()
    assert [m for _r, m in tabs] == ["inventory", "bag2", "shards", "pet"]
    rects = ui.container_slot_rects()
    assert len(rects) == 12 and all(r.bottom <= C.SCREEN_H - 10 for r in rects)
    eq_bottom = max(r.bottom for r, _s in ui.equip_slot_rects())
    assert min(r.top for r in rects) > eq_bottom, "the grid sits below the equip row"
    frame = ui.dock_frame_rect(Player("wizard", "F", pid="f"))
    assert frame.bottom >= max(r.bottom for r in rects) and frame.bottom <= C.SCREEN_H
    assert ui.next_panel_mode("inventory") == "bag2" and ui.next_panel_mode("shards", has_pet=False) == "inventory"
    print("check_layout_fits: PASSED")


def check_singleplayer_tabs_and_drag():
    import main
    g = main.Game()
    g.player_name = "Tabby"
    g.start_run("wizard")
    p = g.player
    g.state = main.STATE_NEXUS
    assert g._dock_mode() == "inventory"
    _key(g, pygame.K_TAB)
    assert g._dock_mode() == "bag2"
    _key(g, pygame.K_TAB)
    assert g._dock_mode() == "shards"
    _key(g, pygame.K_TAB)
    assert g._dock_mode() == "inventory", "no pet -> Pet is skipped"
    # click a label
    shards_rect = next(r for r, m in ui.panel_tab_rects() if m == "shards")
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=shards_rect.center))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=shards_rect.center))
    g.handle_events()
    assert g._dock_mode() == "shards"
    # backpack shard -> ACTIVE socket by dragging onto the Shards tab label then a socket
    shard = runes.make_rune("rare", "burn")
    sword = I._random_tiered("wizard", 4, 4)
    p.backpack = [shard, sword]
    g.right_panel_mode = "inventory"
    bp = ui.backpack_slot_rects(p)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=bp[0].center))
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=shards_rect.center, rel=(0, 0), buttons=(1, 0, 0)))
    g.handle_events()
    assert g._dock_mode() == "shards", "dragging onto a tab label opens it"
    sock = ui.container_slot_rects()[1]
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=sock.center))
    g.handle_events()
    assert p.rune_slots[1] is shard and shard not in p.backpack
    # a non-shard can't go into a shard slot
    g.right_panel_mode = "inventory"
    _drag_from = ui.backpack_slot_rects(p)[0].center
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=_drag_from))
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=shards_rect.center, rel=(0, 0), buttons=(1, 0, 0)))
    g.handle_events()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=ui.container_slot_rects()[2].center))
    g.handle_events()
    assert p.rune_slots[2] is None and sword in p.backpack
    # backpack -> Bag 2
    bag2_rect = next(r for r, m in ui.panel_tab_rects() if m == "bag2")
    g.right_panel_mode = "inventory"
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=ui.backpack_slot_rects(p)[0].center))
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=bag2_rect.center, rel=(0, 0), buttons=(1, 0, 0)))
    g.handle_events()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=ui.container_slot_rects()[0].center))
    g.handle_events()
    assert p.backpack2 == [sword] and sword not in p.backpack
    # overflow: a full backpack spills pickups into Bag 2
    p.backpack = [I._random_tiered("wizard", 1, 3) for _ in range(p.backpack_size)]
    extra = I._random_tiered("wizard", 2, 2)
    assert p.try_pickup(extra) and p.backpack2[-1] is extra
    for mode in ("inventory", "bag2", "shards"):
        g.right_panel_mode = mode
        g.draw()
        if SHOT_DIR:
            pygame.image.save(g.screen, os.path.join(SHOT_DIR, f"dock_tab_{mode}.png"))
    print("check_singleplayer_tabs_and_drag: PASSED")


def check_coop_client_sends_move_item():
    import coop_client

    class FakeLink:
        error = None
        welcome_pid = "p0"

        def __init__(self):
            self.sent = []

        def send(self, obj):
            self.sent.append(obj)

    client = coop_client.CoopClient("127.0.0.1", 0, "TabCoop")
    client.link = FakeLink()
    client.state = coop_client.STATE_PLAY
    client.zone = "nexus"
    me = Player("wizard", name="TabCoop", pid="p0")
    me.rune_slots[0] = runes.make_rune("epic", "chain")
    client.you = me
    client.right_panel_mode = "shards"
    rects = ui.container_slot_rects()
    client._inventory_mouse_down(rects[0].center)
    assert client.drag_from == ("rune", 0)
    client._inventory_mouse_up(rects[5].center)
    assert client.link.sent and client.link.sent[-1]["action"] == "move_item"
    assert client.link.sent[-1]["from"] == ["rune", 0] and client.link.sent[-1]["to"] == ["rune", 5]
    print("check_coop_client_sends_move_item: PASSED")


if __name__ == "__main__":
    check_layout_fits()
    check_singleplayer_tabs_and_drag()
    check_coop_client_sends_move_item()
    print("PASSED: dock tab checks all green.")
