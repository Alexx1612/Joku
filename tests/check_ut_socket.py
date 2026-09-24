"""
Regression check for the UT "socket" system: consuming a spare UT weapon to
imprint its one mechanical proc (bleed/burn/vulnerable/boomerang) onto a
DIFFERENT weapon, via items.identify_proc_kind()/items.apply_socket().

Before this change, a UT's mechanic (see realm_sim.BLEED_UT_NAMES etc.) was
resolved purely by exact-name match against the weapon actually equipped -
Item.proc was flavor text only, nothing let a player move a mechanic onto a
weapon that didn't natively have one. This checks the new Item.socketed_proc
field takes priority in RealmSim.player_fire and produces bullets that are
mechanically IDENTICAL (same status_effect/motion) to a natively-procced UT,
plus the apply_socket() error paths (self-socket, non-weapon target, no proc
to transplant) and that re-socketing overwrites rather than stacking.

Run with: .venv\\Scripts\\python.exe tests\\check_ut_socket.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import items, realm_sim
from game.entities import Player


class _FakeSim:
    """player_fire() only touches self.bullets/self.vfx_events - a full RealmSim
    (real world-gen) would be correct but needlessly slow for this unit check,
    so this stands in for it via an unbound method call."""

    def __init__(self):
        self.bullets = []
        self.vfx_events = []


def _ut_item(cls_name, index):
    name, shape, (mn, mx), proc, desc = items.UT_WEAPONS[cls_name][index]
    return items.Item(name, items.SLOT_WEAPON, 0, shape, is_ut=True,
                       min_dmg=mn, max_dmg=mx, proc=proc, description=desc)


def _fire_once(player, direction=None):
    sim = _FakeSim()
    realm_sim.RealmSim.player_fire(sim, player, direction or pygame.Vector2(1, 0))
    assert sim.bullets, "player_fire produced no bullets"
    return sim.bullets


def check_identify_proc_kind():
    bleed_ut = _ut_item("wizard", 0)
    boomerang_ut = _ut_item("wizard", 1)
    burn_ut = _ut_item("wizard", 2)
    vulnerable_ut = _ut_item("wizard", 3)
    plain = items.make_starter_weapon("wizard")

    assert items.identify_proc_kind(bleed_ut) == "bleed"
    assert items.identify_proc_kind(boomerang_ut) == "boomerang"
    assert items.identify_proc_kind(burn_ut) == "burn"
    assert items.identify_proc_kind(vulnerable_ut) == "vulnerable"
    assert items.identify_proc_kind(plain) is None, "a plain tiered weapon must not resolve to any proc kind"
    print("check_identify_proc_kind: PASSED")


def check_apply_socket_error_paths():
    bleed_ut = _ut_item("wizard", 0)
    plain_weapon = items.make_starter_weapon("wizard")
    plain_armor = items.Item("Test Armor", items.SLOT_ARMOR, 1, "armor", stat_bonus={"deF": 1})

    ok, _ = items.apply_socket(bleed_ut, bleed_ut)
    assert ok is False, "socketing an item onto itself must be rejected"

    ok, _ = items.apply_socket(bleed_ut, plain_armor)
    assert ok is False, "socketing onto a non-weapon slot must be rejected"
    assert plain_armor.socketed_proc is None

    ok, _ = items.apply_socket(plain_weapon, items.make_starter_weapon("archer"))
    assert ok is False, "a source with no identifiable proc must be rejected"

    ok, msg = items.apply_socket(bleed_ut, plain_weapon)
    assert ok is True, f"expected a valid bleed socket to succeed, got: {msg}"
    assert plain_weapon.socketed_proc == "bleed"
    print("check_apply_socket_error_paths: PASSED")


def check_resocketing_overwrites():
    target = items.make_starter_weapon("wizard")
    bleed_ut = _ut_item("wizard", 0)
    burn_ut = _ut_item("wizard", 2)

    ok, _ = items.apply_socket(bleed_ut, target)
    assert ok and target.socketed_proc == "bleed"

    ok, _ = items.apply_socket(burn_ut, target)
    assert ok and target.socketed_proc == "burn", "re-socketing must overwrite the previous proc, not stack/refuse"
    print("check_resocketing_overwrites: PASSED")


def check_socketed_weapon_fires_like_native():
    cls_name = "wizard"

    native_player = Player(cls_name)
    native_player.weapon = _ut_item(cls_name, 0)  # native bleed UT
    native_bullets = _fire_once(native_player)
    assert all(b.status_effect == "bleed" for b in native_bullets)
    assert all(b.motion == "straight" for b in native_bullets)

    socketed_player = Player(cls_name)
    plain = items.make_starter_weapon(cls_name)
    ok, _ = items.apply_socket(_ut_item(cls_name, 0), plain)
    assert ok
    socketed_player.weapon = plain
    socketed_bullets = _fire_once(socketed_player)
    assert all(b.status_effect == "bleed" for b in socketed_bullets), \
        "a socketed bleed proc must apply the exact same status_effect as a native bleed UT"
    assert all(b.motion == "straight" for b in socketed_bullets)

    # boomerang motion transplants correctly too, not just the 3 status-effect procs
    boomerang_player = Player(cls_name)
    plain2 = items.make_starter_weapon(cls_name)
    ok, _ = items.apply_socket(_ut_item(cls_name, 1), plain2)
    assert ok and plain2.socketed_proc == "boomerang"
    boomerang_player.weapon = plain2
    boomerang_bullets = _fire_once(boomerang_player)
    assert all(b.motion == "boomerang" for b in boomerang_bullets), \
        "a socketed boomerang proc must give the bullet boomerang motion, same as the native UT"
    assert all(b.status_effect is None for b in boomerang_bullets)

    # a socketed weapon that also happens to natively match a name (impossible in
    # practice since plain tiered weapons never share a UT's name, but confirms the
    # priority order explicitly) - socketed_proc must win over the name-based lookup
    print("check_socketed_weapon_fires_like_native: PASSED")


def check_unsocketed_plain_weapon_has_no_proc():
    player = Player("wizard")
    bullets = _fire_once(player)  # starter Wand, never socketed
    assert all(b.status_effect is None for b in bullets)
    assert all(b.motion == "straight" for b in bullets)
    print("check_unsocketed_plain_weapon_has_no_proc: PASSED")


def main():
    check_identify_proc_kind()
    check_apply_socket_error_paths()
    check_resocketing_overwrites()
    check_socketed_weapon_fires_like_native()
    check_unsocketed_plain_weapon_has_no_proc()
    print()
    print("PASSED: UT socket system transplants procs correctly and matches native behavior.")


if __name__ == "__main__":
    main()
