"""
The top event feed ("X is singing! Y has awoken!") must never be written over the quest panel,
wherever the player dragged it: at its default top-left spot, dragged to the middle (the case that
used to overlap), or pushed to the right. Lines go beside it when there is room, else below it.

Run with: python tests/check_feed_clear_of_quest_panel.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()

from game import ui

MESSAGES = [
    ("Abyssal Rumnal is singing! Abyssal Choirmaster has awoken!", (120, 230, 255), 3.0),
    ("Ashioned Shard is flaring! Ashenreach Devourer has awoken!", (255, 160, 60), 3.0),
    ("Driftai Cloister is singing! Driftbell Matriarch has awoken!", (120, 230, 255), 3.0),
    ("Thorn-on-the-Rocks Shard is flaring! Thornrock Colossus has awoken!", (255, 160, 60), 3.0),
]


def _feed_over_panel(size, panel):
    surf = pygame.display.set_mode(size)
    surf.fill((0, 0, 0))
    ui._quest_slot_drawn = (panel, pygame.time.get_ticks())
    assert ui.quest_slot_rect() == panel
    ui.draw_item_feed(surf, MESSAGES)
    hits = 0
    panel = panel.clip(surf.get_rect())
    for x in range(panel.left, panel.right, 2):
        for y in range(panel.top, panel.bottom, 2):
            if surf.get_at((x, y))[:3] != (0, 0, 0):
                hits += 1
    drawn = sum(1 for x in range(0, size[0], 4) for y in range(60, 400, 4) if surf.get_at((x, y))[:3] != (0, 0, 0))
    return hits, drawn


def check_feed_never_covers_the_panel():
    for size in ((1366, 820), (1920, 1080), (1024, 700)):
        pygame.display.set_mode(size)
        play_w = ui.dock_frame_rect().x
        for name, panel in (("default top-left", pygame.Rect(12, 86, 250, 64)),
                            ("dragged to the middle", pygame.Rect(420, 86, 250, 64)),
                            ("dragged right", pygame.Rect(play_w - 300, 80, 250, 80)),
                            ("tall, mid-left", pygame.Rect(200, 70, 300, 160))):
            hits, drawn = _feed_over_panel(size, panel)
            assert drawn > 50, (size, name, "the feed should still be drawn")
            assert hits == 0, (size, name, f"{hits} feed pixels on the quest panel")
    print("check_feed_never_covers_the_panel: PASSED")


def check_no_panel_keeps_centred_feed():
    surf = pygame.display.set_mode((1366, 820))
    surf.fill((0, 0, 0))
    ui._quest_slot_drawn = (None, 0)
    ui.draw_item_feed(surf, MESSAGES[:1])
    xs = [x for x in range(0, 1366, 2) if surf.get_at((x, 98))[:3] != (0, 0, 0)]
    assert xs, "feed drawn"
    mid = (xs[0] + xs[-1]) / 2
    assert abs(mid - (ui.dock_frame_rect().x - 8) / 2) < 40, mid
    print("check_no_panel_keeps_centred_feed: PASSED")


if __name__ == "__main__":
    check_feed_never_covers_the_panel()
    check_no_panel_keeps_centred_feed()
    print("\nPASSED: the event feed stays clear of the quest panel.")
