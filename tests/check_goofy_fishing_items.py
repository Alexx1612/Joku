"""
Quick regression check for the goofy fishing "junk" tier (see
items._random_junk_catch / RealmSim.fish_action's "junk" branch).

Not a real test suite (see README's v0.3 roadmap), just a standalone script
confirming: the junk tier actually returns a VARIETY of items (not always
the same one), every goofy item is well-formed (valid slot, correctly-typed
stat fields, non-empty flavor text), and the cursed ring's downside is a
real mechanical effect, not just flavor text.

Run with: .venv\\Scripts\\python.exe tests\\check_goofy_fishing_items.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import entities
from game.items import (Item, SLOT_WEAPON, SLOT_ARMOR, SLOT_RING, SLOT_EGG,
                         _random_junk_catch, make_old_boot, make_rubber_duck,
                         make_cursed_ring, make_fishing_net_weapon,
                         make_waterlogged_sandwich, make_egg, PET_KINDS)

VALID_SLOTS = {SLOT_WEAPON, SLOT_ARMOR, SLOT_RING, SLOT_EGG, "consumable"}
ROLLS = 4000


def check_variety():
    random.seed(42)
    names = {_random_junk_catch().name for _ in range(ROLLS)}
    # 7 distinct makers in the table (plain potion + 6 goofy items) - over
    # 4000 rolls every one of them should show up at least once.
    assert len(names) >= 6, f"expected at least 6 distinct junk outcomes over {ROLLS} rolls, got {names}"
    goofy_names = {"Old Boot", "Rubber Duck Ring", "Cursed Ring of Buyer's Remorse",
                   "Tangled Fishing Net", "Waterlogged Sandwich", "Sentient Fish Egg"}
    assert goofy_names.issubset(names), f"missing goofy items: {goofy_names - names}"
    print(f"  variety ok: {len(names)} distinct junk-tier outcomes seen over {ROLLS} rolls")


def _assert_well_formed(item: Item):
    assert isinstance(item, Item)
    assert item.slot in VALID_SLOTS, f"{item.name} has invalid slot {item.slot!r}"
    assert item.description and isinstance(item.description, str), f"{item.name} has no flavor text"
    assert isinstance(item.stat_bonus, dict)
    for k, v in item.stat_bonus.items():
        assert k in ("att", "deF", "spd", "dex", "vit", "wis"), f"{item.name} has bogus stat key {k!r}"
        assert isinstance(v, int), f"{item.name}'s stat_bonus[{k}] is not an int: {v!r}"
    if item.slot == SLOT_WEAPON:
        assert isinstance(item.min_dmg, int) and isinstance(item.max_dmg, int)
        assert 0 <= item.min_dmg <= item.max_dmg, f"{item.name} has a bogus damage range"


def check_well_formed():
    for maker in (make_old_boot, make_rubber_duck, make_cursed_ring,
                  make_fishing_net_weapon, make_waterlogged_sandwich):
        _assert_well_formed(maker())
    egg = make_egg("sentient_fish")
    _assert_well_formed(egg)
    assert egg.pet_kind == "sentient_fish"
    assert "sentient_fish" in PET_KINDS
    print("  well-formed ok: every goofy item + the sentient-fish egg has a valid slot/stats/description")


def check_cursed_downside_is_real():
    p = entities.Player("wizard", name="Tester", pid=1)
    base_att, base_deF = p.total_stat("att"), p.total_stat("deF")
    ring = make_cursed_ring()
    assert ring.stat_bonus.get("att", 0) > 0, "cursed ring should still buff att"
    assert ring.stat_bonus.get("deF", 0) < 0, "cursed ring's downside must be a real negative stat_bonus"
    p.ring = ring
    assert p.total_stat("att") == base_att + ring.stat_bonus["att"], "cursed ring's att bonus didn't apply"
    assert p.total_stat("deF") == base_deF + ring.stat_bonus["deF"], "cursed ring's deF penalty didn't apply"
    assert p.total_stat("deF") < base_deF, "equipping the cursed ring must make the player measurably squishier"
    print("  cursed-ring downside ok: att buffed, deF genuinely reduced once equipped")


def check_fishing_net_is_a_real_but_bad_weapon():
    net = make_fishing_net_weapon()
    assert net.slot == SLOT_WEAPON
    # deliberately weak - a joke weapon, not a buff (real starter weapons roll well above this)
    assert net.max_dmg <= 2, "the fishing net should be a genuinely weak joke weapon"
    print("  fishing-net weapon ok: real SLOT_WEAPON item, deliberately weak damage")


if __name__ == "__main__":
    print("check_goofy_fishing_items:")
    check_variety()
    check_well_formed()
    check_cursed_downside_is_real()
    check_fishing_net_is_a_real_but_bad_weapon()
    print("PASSED")
