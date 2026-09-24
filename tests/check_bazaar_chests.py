"""
Regression check for Batch 14 Track J: permanent Bazaar chest containers.

Confirms: chests exist at fixed positions in a fresh Bazaar item list,
opening one behaves like the existing ground-bag floating-window pattern
(no state transition, position-anchored, found via the same
find_nearby_bag/bag_by_id flow), items placed in a chest persist across
multiple open/close cycles (unlike an expiring/emptying ground Bag), and a
chest actually renders as a chest (a real pixel check against
sprites.chest_sprite, not just "an object exists").

Run with: .venv\\Scripts\\python.exe tests\\check_bazaar_chests.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import sprites
from game.entities import (BazaarChest, Bag, spawn_bazaar_chests, find_nearby_bag,
                            bag_by_id, withdraw_from_bag, deposit_to_bag,
                            BAZAAR_CHEST_TILE_POSITIONS, Player)
from game.constants import TILE
from game.items import make_old_boot


def check_chests_exist_at_fixed_positions():
    chests = spawn_bazaar_chests()
    assert len(chests) == len(BAZAAR_CHEST_TILE_POSITIONS) == 4, \
        f"expected {len(BAZAAR_CHEST_TILE_POSITIONS)} chests, got {len(chests)}"
    for chest, (tx, ty) in zip(chests, BAZAAR_CHEST_TILE_POSITIONS):
        assert isinstance(chest, BazaarChest)
        expected = (tx * TILE + TILE // 2, ty * TILE + TILE // 2)
        assert (round(chest.pos.x), round(chest.pos.y)) == expected, \
            f"chest at wrong position: {chest.pos} != {expected}"
    ids = {c.id for c in chests}
    assert len(ids) == 4, "chest ids must be distinct"
    print("check_chests_exist_at_fixed_positions: PASSED")


def check_open_interaction_matches_ground_bag_pattern():
    chests = spawn_bazaar_chests()
    p = Player("wizard", "Tester", pid="p1")
    p.pos = pygame.Vector2(chests[0].pos)

    # find_nearby_bag/bag_by_id are the exact functions the real right-click
    # ("_try_loot") flow uses for ground bags - a chest must work through the
    # identical lookup, with no state transition (unlike the Vault menu).
    found = find_nearby_bag(chests, p.pos, p.pid)
    assert found is chests[0], "chest not findable via the standard bag-lookup flow"
    assert bag_by_id(chests, found.id) is found
    assert found.can_be_taken_by(p.pid) is True, "a shared chest must never gate by 'dropped_by'"
    print("check_open_interaction_matches_ground_bag_pattern: PASSED")


def check_items_persist_across_open_close_cycles():
    chests = spawn_bazaar_chests()
    chest = chests[0]
    boot = make_old_boot()

    p = Player("wizard", "Tester", pid="p1")
    p.backpack = [boot]

    # deposit (backpack -> chest)
    deposited = deposit_to_bag(chests, chest.id, 0, p)
    assert deposited is boot
    assert chest.items == [boot]
    assert p.backpack == [], "item should be removed from backpack once deposited"

    # simulate closing and reopening the window several times - a chest must
    # never be culled the way an emptied/expired ground Bag would be
    for _ in range(5):
        assert chest.update(1.0) is True, "a BazaarChest must never report itself dead"
    assert chest.items == [boot], "chest contents must survive open/close cycles"

    # withdraw (chest -> backpack) via the exact same function ground bags use
    withdrawn = withdraw_from_bag(chests, chest.id, 0, p)
    assert withdrawn is boot
    assert chest.items == [], "chest must still exist and be openable even when empty"
    assert chest.update(1.0) is True, "an EMPTY chest must still survive update() (unlike a Bag)"

    # contrast: a regular Bag DOES die once emptied - confirms the chest's
    # override is the actual behavioral difference being tested, not a no-op
    regular_bag = Bag([boot], chest.pos)
    regular_bag.items = []
    assert regular_bag.update(1.0) is False, "sanity check: a normal Bag dies when emptied"
    print("check_items_persist_across_open_close_cycles: PASSED")


def check_deposit_rejects_when_full():
    chests = spawn_bazaar_chests()
    chest = chests[0]
    p = Player("wizard", "Tester", pid="p1")
    p.backpack = [make_old_boot() for _ in range(9)]
    for i in range(8):
        assert deposit_to_bag(chests, chest.id, 0, p) is not None
    assert chest.is_full()
    before = len(p.backpack)
    assert deposit_to_bag(chests, chest.id, 0, p) is None, "a full chest must reject further deposits"
    assert len(p.backpack) == before, "a rejected deposit must not remove the item from the backpack"
    print("check_deposit_rejects_when_full: PASSED")


def check_visual_chest_rendering():
    empty_img = sprites.chest_sprite(0, filled=False)
    filled_img = sprites.chest_sprite(0, filled=True)
    assert empty_img.get_size() == filled_img.get_size()
    empty_px = pygame.image.tostring(empty_img, "RGBA")
    filled_px = pygame.image.tostring(filled_img, "RGBA")
    assert empty_px != filled_px, "an empty vs. filled chest must render visibly differently"

    # each of the 4 skins must be visually distinct (a real chest icon, not
    # a single flat placeholder reused for every chest)
    skins = [pygame.image.tostring(sprites.chest_sprite(i, filled=True), "RGBA") for i in range(4)]
    assert len(set(skins)) == 4, "all 4 chest skins should be visually distinct"

    surf = pygame.Surface((64, 64), pygame.SRCALPHA)
    cam = lambda pos: (32, 32)
    chest = spawn_bazaar_chests()[0]
    chest.draw(surf, cam)
    # a real chest silhouette must have painted a good number of non-transparent
    # pixels around the drawn point - not left the surface blank
    nonzero = sum(1 for x in range(64) for y in range(64) if surf.get_at((x, y)).a > 0)
    assert nonzero > 50, f"chest.draw() painted too few pixels ({nonzero}) to be a real sprite"
    print("check_visual_chest_rendering: PASSED")


if __name__ == "__main__":
    check_chests_exist_at_fixed_positions()
    check_open_interaction_matches_ground_bag_pattern()
    check_items_persist_across_open_close_cycles()
    check_deposit_rejects_when_full()
    check_visual_chest_rendering()
    print("ALL CHECKS PASSED")
