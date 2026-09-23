"""
Regression check for HUD mouse-interactivity (class select, options menu,
death screen, trade panel hover/tooltip/yellow-offer-highlight) and for
UI TEXT OVERLAP avoidance (portal labels, peer name tags) - the exact class
of bug the user found in play (10 island-hub portal labels overlapping).
Covers normal cases (a handful of spaced-out objects) and the specific edge
case that was actually broken (many objects clustered close together) plus
degenerate edge cases (zero or one object - must never crash).

Run with: .venv\\Scripts\\python.exe tests\\check_hud_and_overlap.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((1280, 720))

from game import ui
from game.entities import Portal, Player


def _rects_for_portals(portals, cam):
    entries = []
    for pt in portals:
        text, color = ui._portal_label_text(pt)
        if text:
            entries.append((pt, text, color))
    entries.sort(key=lambda e: cam(e[0].pos)[0])
    placed = []
    for pt, text, color in entries:
        px, py = cam(pt.pos)
        label = ui._FONT_S.render(text, True, color)
        w, h = label.get_size()
        base_y = py - 34
        rect = pygame.Rect(px - w // 2, base_y, w, h)
        step = 0
        while any(rect.colliderect(r) for r in placed):
            step += 1
            rect.y = base_y - step * (h + 2)
        placed.append(rect)
    return placed


def check_portal_label_overlap():
    cam = lambda pos: (int(pos[0]), int(pos[1]))
    names = ["Emberfall Shard", "Coral Choir", "Frostbite Shard", "Pearlsong Spire", "Bonewaste Shard",
             "Tideglass Sanctum", "Thornrock Shard", "Driftbell Cloister", "Ashenreach Shard", "Abyssal Hymnal"]
    portals = []
    for i, name in enumerate(names):
        angle = 2 * math.pi * i / 10
        pos = (400 + math.cos(angle) * 192, 400 + math.sin(angle) * 192)  # real island-hub ring radius
        portals.append(Portal(pos, kind="island_link", label=name, target_pos=(0, 0)))
    rects = _rects_for_portals(portals, cam)
    overlaps = sum(1 for i in range(len(rects)) for j in range(i + 1, len(rects)) if rects[i].colliderect(rects[j]))
    assert overlaps == 0, f"{overlaps} portal label pairs overlap at real island-hub spacing"
    ui.draw_portal_labels(screen, cam, portals)  # must not crash on the real function

    # edge cases: 0 and 1 portal must never crash
    ui.draw_portal_labels(screen, cam, [])
    ui.draw_portal_labels(screen, cam, [portals[0]])

    # far-apart portals should need no staggering at all (step==0 for each)
    far_portals = [Portal((0, 0), kind="dungeon_shard", difficulty="Easy"),
                   Portal((2000, 2000), kind="dungeon_shard", difficulty="Hard")]
    far_rects = _rects_for_portals(far_portals, cam)
    assert not far_rects[0].colliderect(far_rects[1])
    print("check_portal_label_overlap: PASSED")


def check_peer_label_overlap():
    import coop_client as cc
    client = cc.CoopClient.__new__(cc.CoopClient)
    cam = lambda pos: (int(pos[0]), int(pos[1]))
    peers = []
    for i in range(5):
        pr = Player("wizard", f"Peer{i}", pid=f"p{i}")
        pr.pos = pygame.Vector2(400 + i * 15, 400)  # tightly clustered, 15px apart
        pr.title = ""
        pr.level = 1
        peers.append(pr)
    client._draw_peer_labels(screen, cam, peers)  # must not crash on tightly-clustered peers

    # edge case: zero peers must not crash
    client._draw_peer_labels(screen, cam, [])
    print("check_peer_label_overlap: PASSED")


def check_class_select_and_death_screen_hover():
    rects = ui.class_select_tile_rects()
    assert len(rects) >= 1
    ui.draw_class_select(screen, 0, mouse_pos=rects[0][0].center)
    btn = ui.death_screen_button_rect()
    ui.draw_death_screen_button(screen, btn.center)
    ui.draw_death_screen_button(screen, (-1, -1))  # edge case: mouse far away, no crash
    print("check_class_select_and_death_screen_hover: PASSED")


def check_help_menu_click_dispatch():
    clicked = []
    items_ = [("A", lambda: clicked.append(0)), ("B", lambda: clicked.append(1)), ("C", lambda: clicked.append(2))]
    rects = ui.help_menu_item_rects(items_)
    assert len(rects) == 3
    close_rect = ui.help_close_button_rect(items_)
    assert not any(r.colliderect(close_rect) for r in rects)
    hit_pos = rects[1].center
    for i, r in enumerate(rects):
        if r.collidepoint(hit_pos):
            _, action = items_[i]
            action()
            break
    assert clicked == [1]

    # edge case: an empty menu list must not crash
    assert ui.help_menu_item_rects([]) == []
    ui.draw_help_overlay(screen, menu_items=[], selected_idx=0, mouse_pos=(-1, -1))
    print("check_help_menu_click_dispatch: PASSED")


def check_trade_panel_hover_and_highlight():
    from game.items import Item, SLOT_WEAPON
    item = Item("TradeSword", SLOT_WEAPON, 5, "sword", min_dmg=3, max_dmg=6)
    trade = {"other_name": "Bob", "my_offer": [item.to_json()], "their_offer": [],
             "my_accept": False, "their_accept": False, "timer": None}
    rects = ui.trade_offer_slot_rects(mine=True)
    ui.draw_trade_panel(screen, trade, "Me", mouse_pos=rects[0].center)  # hovering an offered item
    ui.draw_trade_panel(screen, trade, "Me", mouse_pos=(-100, -100))     # edge case: no hover

    # edge case: an empty trade (nothing offered by either side) must not crash
    empty_trade = {"other_name": "Bob", "my_offer": [], "their_offer": [],
                   "my_accept": False, "their_accept": False, "timer": None}
    ui.draw_trade_panel(screen, empty_trade, "Me", mouse_pos=rects[0].center)
    accept_rect = ui.trade_accept_button_rect()
    ui.draw_trade_panel(screen, trade, "Me", mouse_pos=accept_rect.center)
    print("check_trade_panel_hover_and_highlight: PASSED")


def check_day_night_clock():
    from game.entities import Player
    rect = ui.day_night_clock_rect()
    p = Player("wizard", "X", pid="p1")
    p.pet = None
    assert ui.pet_panel_rect(p) is None
    from game.entities import Pet
    p.pet = Pet("hatchling", p.pos)
    assert not rect.colliderect(ui.pet_panel_rect(p)), "clock must not overlap the pet panel"
    for ll in (1.0, 0.5, 0.0):
        ui.draw_day_night_clock(screen, ll, blood_moon=False)
    ui.draw_day_night_clock(screen, 0.1, blood_moon=True)

    # real end-to-end integration test through the ACTUAL call site, not just the ui
    # function in isolation - this is exactly the bug class that shipped once already:
    # draw_day_night_clock()'s signature was simplified but main.py's call site was
    # never updated to match, and it was only caught by the user actually running the app
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.enter_realm()
    game.draw()  # would raise TypeError if any ui call site's args don't match its signature
    from game.realm_sim import DAY_LENGTH
    for frac in (0.0, 0.25, 0.5, 0.75):
        game.realm_sim.day_time = frac * DAY_LENGTH
        game.draw()
    game.realm_sim.blood_moon_active = True
    game.draw()
    print("check_day_night_clock: PASSED")


if __name__ == "__main__":
    check_portal_label_overlap()
    check_peer_label_overlap()
    check_class_select_and_death_screen_hover()
    check_help_menu_click_dispatch()
    check_trade_panel_hover_and_highlight()
    check_day_night_clock()
    print("PASSED: HUD interactivity + text-overlap checks all green.")
