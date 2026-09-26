"""
Regression check for inventory click semantics (right-click=drop,
double-click=use/equip, single-click reserved for drag/trade/bag-withdraw),
full-inventory drag-swap behavior, and the Vault's independent-per-chest
storage + skins. Covers normal cases and edge cases (slow double-clicks that
should NOT count, clicking two different slots quickly that should NOT
count, depositing into a full chest, withdrawing into a full backpack).

Run with: .venv\\Scripts\\python.exe tests\\check_inventory_and_vault.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

import game.items as items
items.VAULT_DIR = tempfile.mkdtemp()  # isolate from real save data

from game.entities import Player, Bag, withdraw_from_bag
from game.items import Item, SLOT_WEAPON, VAULT_SLOTS, VAULT_CHEST_SIZE, make_potion
import main as main_module


def _sword(name, tier=1):
    return Item(name, SLOT_WEAPON, tier, "sword", min_dmg=1, max_dmg=2)


def check_double_click_semantics():
    game = main_module.Game.__new__(main_module.Game)
    game.player = Player("wizard", "Clicker", pid="p1")
    game.player.backpack = [make_potion("att"), make_potion("deF")]
    game._dblclick_slot, game._dblclick_time, game.DBLCLICK_MS = None, 0, 350
    game.push_feed = lambda *a, **k: None
    game._slot_at = lambda pos: ("backpack", 0)

    # a single click must NOT use the item
    game.drag_from, game.drag_start_pos = ("backpack", 0), (50, 50)
    game._inventory_mouse_up((50, 50))
    assert len(game.player.backpack) == 2, "a single click must not consume/equip"

    # a rapid second click on the SAME slot must use it
    game.drag_from, game.drag_start_pos = ("backpack", 0), (50, 50)
    game._inventory_mouse_up((50, 50))
    assert len(game.player.backpack) == 1, "a rapid double-click on the same slot must use it"

    # edge case: two SLOW clicks (beyond the threshold) must not count as a double-click
    game._dblclick_slot, game._dblclick_time = None, 0
    game.drag_from, game.drag_start_pos = ("backpack", 0), (50, 50)
    game._inventory_mouse_up((50, 50))
    time.sleep(0.5)
    game.drag_from, game.drag_start_pos = ("backpack", 0), (50, 50)
    game._inventory_mouse_up((50, 50))
    assert len(game.player.backpack) == 1, "two clicks slower than the threshold must not double-click"

    # edge case: two rapid clicks on DIFFERENT slots must not count as a double-click
    game.player.backpack = [make_potion("att"), make_potion("deF")]
    game._dblclick_slot, game._dblclick_time = None, 0
    game._slot_at = lambda pos: ("backpack", 0)
    game.drag_from, game.drag_start_pos = ("backpack", 0), (50, 50)
    game._inventory_mouse_up((50, 50))
    game._slot_at = lambda pos: ("backpack", 1)
    game.drag_from, game.drag_start_pos = ("backpack", 1), (60, 60)
    game._inventory_mouse_up((60, 60))
    assert len(game.player.backpack) == 2, "rapid clicks on DIFFERENT slots must not double-click either one"
    print("check_double_click_semantics: PASSED")


def check_right_click_drop():
    from game.realm_sim import RealmSim
    game = main_module.Game.__new__(main_module.Game)
    game.state = main_module.STATE_REALM
    game.player = Player("wizard", "Dropper", pid="p1")
    game.player.backpack = [make_potion("att")]
    game.realm_sim = RealmSim.__new__(RealmSim)
    game.realm_sim.ground_items = []
    game._current_bag_list = lambda: game.realm_sim.ground_items
    game.push_feed = lambda *a, **k: None
    import types
    game._drop_item = types.MethodType(main_module.Game._drop_item, game)
    game._right_click_drop_backpack_slot(0)
    assert len(game.player.backpack) == 0
    assert len(game.realm_sim.ground_items) == 1

    # edge case: right-clicking an out-of-range/empty slot index must not crash
    game._right_click_drop_backpack_slot(5)
    print("check_right_click_drop: PASSED")


def check_bag_swap_on_full_inventory():
    p = Player("wizard", "Swapper", pid="p1")
    p.backpack_size = 4
    p.backpack = [_sword(f"Old{i}") for i in range(4)]
    bag = Bag([_sword("NewSword", 5)], (0, 0))
    result = withdraw_from_bag([bag], bag.id, 0, p, target_idx=2)
    assert result is not None and result.name == "NewSword"
    assert p.backpack[2].name == "NewSword"
    assert len(bag.items) == 1 and bag.items[0].name == "Old2"

    # edge case: target_idx out of range must fall back cleanly (no crash), and
    # since the backpack is still full, a normal (non-swap) withdraw must fail
    r2 = withdraw_from_bag([bag], bag.id, 0, p, target_idx=99)
    assert r2 is None
    print("check_bag_swap_on_full_inventory: PASSED")


def check_vault_independent_chests():
    v = items.load_vault("TestVault_A")
    assert len(v) == VAULT_SLOTS and all(x is None for x in v)

    v[0] = _sword("A")
    v[3 * VAULT_CHEST_SIZE] = _sword("InChest3")
    items.save_vault("TestVault_A", v)
    v2 = items.load_vault("TestVault_A")
    v2[0] = None  # remove from chest 0
    items.save_vault("TestVault_A", v2)
    v3 = items.load_vault("TestVault_A")
    assert v3[3 * VAULT_CHEST_SIZE].name == "InChest3", "chest 3 must be unaffected by removing from chest 0"

    # legacy compact-list migration
    import json
    with open(items._vault_path("LegacyVault"), "w") as f:
        json.dump([_sword("Old1").to_json(), _sword("Old2").to_json()], f)
    migrated = items.load_vault("LegacyVault")
    assert len(migrated) == VAULT_SLOTS
    assert migrated[0].name == "Old1" and migrated[1].name == "Old2"
    assert all(x is None for x in migrated[2:])
    print("check_vault_independent_chests: PASSED")


def check_vault_deposit_withdraw_swap():
    game = main_module.Game.__new__(main_module.Game)
    game.player = Player("wizard", "VaultTester", pid="p1")
    game.player.backpack = [_sword("Sword1")]
    game.vault_items = [None] * VAULT_SLOTS
    lo = 3 * VAULT_CHEST_SIZE
    game.vault_items[lo] = _sword("Existing")
    game.vault_chest = 3
    game.vault_chest_open = 3  # Batch 15: one vault-room chest's bag-style window is open
    game.right_panel_mode = "inventory"  # the normal dock is visible beside an open chest now
    game._current_bag = lambda: None
    game.state = main_module.STATE_VAULT_ROOM

    # plain-click deposit fills the first EMPTY slot of the CURRENT chest
    game.drag_from, game.drag_start_pos = ("backpack", 0), (100, 100)
    game._vault_mouse_up((100, 100))
    assert game.vault_items[lo + 1] is not None and game.vault_items[lo + 1].name == "Sword1"
    assert len(game.player.backpack) == 0

    # drag onto an OCCUPIED vault slot swaps
    game.player.backpack = [_sword("NewBlade", 5)]
    game.drag_from, game.drag_start_pos = ("backpack", 0), (100, 100)
    game._slot_at = lambda pos: ("vault", lo)
    game._vault_mouse_up((999, 999))
    assert game.vault_items[lo].name == "NewBlade"
    assert game.player.backpack[0].name == "Existing"

    # edge case: depositing when the CURRENT chest is completely full must
    # silently no-op (item stays in the backpack), never overflow into another chest
    game.vault_chest = 5
    full_lo = 5 * VAULT_CHEST_SIZE
    for i in range(VAULT_CHEST_SIZE):
        game.vault_items[full_lo + i] = _sword(f"Full{i}")
    game.player.backpack = [_sword("Overflow")]
    game.drag_from, game.drag_start_pos = ("backpack", 0), (200, 200)
    game._vault_mouse_up((200, 200))  # plain click, chest 5 is full
    assert len(game.player.backpack) == 1, "a full chest must reject a deposit, not overflow elsewhere"
    other_lo = 6 * VAULT_CHEST_SIZE
    assert all(game.vault_items[other_lo + i] is None for i in range(VAULT_CHEST_SIZE)), \
        "a rejected deposit must never land in a DIFFERENT chest"
    print("check_vault_deposit_withdraw_swap: PASSED")


def check_vault_chest_skins():
    from game import ui
    from game.items import VAULT_CHEST_COUNT
    assert VAULT_CHEST_COUNT == 12 and len(ui.VAULT_CHEST_SKINS) >= VAULT_CHEST_COUNT, \
        "12 vault chests, each with its own skin"
    assert len(set(ui.VAULT_CHEST_SKINS)) == len(ui.VAULT_CHEST_SKINS), "every chest skin should be distinct"
    print("check_vault_chest_skins: PASSED")


if __name__ == "__main__":
    check_double_click_semantics()
    check_right_click_drop()
    check_bag_swap_on_full_inventory()
    check_vault_independent_chests()
    check_vault_deposit_withdraw_swap()
    check_vault_chest_skins()
    print("PASSED: inventory/vault interaction checks all green.")
