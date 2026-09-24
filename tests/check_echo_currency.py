"""
Regression check for the Batch-12 "Echoes" permadeath currency (account-wide
JSON persistence, award-on-death, and the two permanent power-neutral
unlocks purchasable at the Nexus's Echo Keeper). Covers normal cases (award
+ persist + reload round-trip, a successful purchase applying its real
effect) and edge cases (spending more than the balance must fail cleanly,
the backpack-slot unlock must be capped, the XP boost must never level up
a character).

Run with: .venv\\Scripts\\python.exe tests\\check_echo_currency.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import accounts
from game import constants as C
from game.entities import Player


def _use_temp_accounts_dir():
    """Redirects accounts.ACCOUNTS_DIR to a throwaway temp dir so this test
    never touches the real player's accounts/ folder - mirrors how other
    persistence checks in this suite isolate themselves."""
    tmp = tempfile.mkdtemp(prefix="rr_echo_test_")
    accounts.ACCOUNTS_DIR = tmp
    accounts._LAST_USED_PATH = os.path.join(tmp, "_last_used.txt")
    return tmp


def check_award_persist_reload_round_trip():
    tmp = _use_temp_accounts_dir()
    try:
        name = "EchoTester"
        accounts.touch_account(name)
        assert accounts.get_echoes(name) == 0

        earned = accounts.award_echoes_for_death(name, level=10)
        assert earned == 5, "level 10 should award max(1, 10 // 2) = 5 echoes"
        assert accounts.get_echoes(name) == 5

        # a second death on the same account accumulates, doesn't overwrite
        accounts.award_echoes_for_death(name, level=1)
        assert accounts.get_echoes(name) == 6, "max(1, 1 // 2) = 1 more echo"

        # reload from disk (a fresh load_account call, not the in-memory value)
        # to prove this actually persisted, not just an in-process cache
        reloaded = accounts.load_account(name)
        assert reloaded["echoes"] == 6
        print("check_award_persist_reload_round_trip: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_spend_edge_cases():
    tmp = _use_temp_accounts_dir()
    try:
        name = "BrokeTester"
        accounts.touch_account(name)
        assert accounts.spend_echoes(name, 10) is False, "can't spend echoes you don't have"
        assert accounts.get_echoes(name) == 0, "a failed spend must not touch the balance"

        accounts.add_echoes(name, 5)
        assert accounts.spend_echoes(name, 10) is False, "still can't afford more than the balance"
        assert accounts.get_echoes(name) == 5, "balance must be untouched after a failed spend"

        assert accounts.spend_echoes(name, 5) is True
        assert accounts.get_echoes(name) == 0
        print("check_spend_edge_cases: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_backpack_slot_purchase_has_real_effect():
    tmp = _use_temp_accounts_dir()
    try:
        name = "BackpackBuyer"
        accounts.touch_account(name)
        accounts.add_echoes(name, 1000)

        ok, msg = accounts.buy_backpack_slot(name)
        assert ok, msg
        assert accounts.get_echoes(name) == 1000 - accounts.BACKPACK_SLOT_COST
        assert accounts.get_unlocks(name)["backpack_slots"] == 1

        # buying again costs more (the step) and stacks up to the cap
        ok, msg = accounts.buy_backpack_slot(name)
        assert ok, msg
        assert accounts.get_unlocks(name)["backpack_slots"] == 2

        # capped - a third purchase must be rejected even with plenty of echoes
        balance_before = accounts.get_echoes(name)
        ok, msg = accounts.buy_backpack_slot(name)
        assert not ok, "backpack slots must be capped at MAX_BACKPACK_BONUS_SLOTS"
        assert accounts.get_echoes(name) == balance_before, "a rejected purchase must not spend echoes"

        # the REAL effect: a fresh Player picked up via apply_unlocks actually
        # has a bigger backpack, not just a flag sitting unused in the account file
        p = Player("wizard", name=name, pid="local")
        base_size = p.backpack_size
        accounts.apply_unlocks(p, name)
        assert p.backpack_size == base_size + 2, "apply_unlocks must actually grow backpack_size"
        print("check_backpack_slot_purchase_has_real_effect: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_starting_xp_boost_is_power_neutral():
    tmp = _use_temp_accounts_dir()
    try:
        name = "XpBuyer"
        accounts.touch_account(name)
        accounts.add_echoes(name, 1000)

        ok, msg = accounts.buy_starting_xp_boost(name)
        assert ok, msg
        assert accounts.get_unlocks(name)["starting_xp_boost"] is True

        # buying twice must be rejected (a one-time unlock, not stackable)
        balance_before = accounts.get_echoes(name)
        ok, msg = accounts.buy_starting_xp_boost(name)
        assert not ok
        assert accounts.get_echoes(name) == balance_before

        # the REAL effect: a fresh Player actually starts with the bonus XP...
        p = Player("wizard", name=name, pid="local")
        assert p.xp == 0 and p.level == 1
        accounts.apply_unlocks(p, name)
        assert p.xp == accounts.STARTING_XP_BOOST_AMOUNT
        # ...but it must be small enough to never actually level the character up -
        # that would be real combat power (HP/MP/stat rolls happen on level-up),
        # which contradicts this whole system's power-neutral design constraint
        assert p.level == 1, "the starting XP boost must never trigger a level-up"
        assert accounts.STARTING_XP_BOOST_AMOUNT < C.xp_to_next(1), (
            "the boost amount itself must stay under a single level's requirement")
        print("check_starting_xp_boost_is_power_neutral: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_resume_never_reapplies_unlocks():
    """apply_unlocks is only ever called at fresh-character creation
    (main.py's start_run / server.py's fresh-join branch) - a resumed/loaded
    character must keep whatever backpack_size/xp was actually persisted,
    never get the bonus re-granted on every login."""
    tmp = _use_temp_accounts_dir()
    try:
        name = "ResumeTester"
        accounts.touch_account(name)
        accounts.add_echoes(name, 1000)
        accounts.buy_backpack_slot(name)

        p = Player("wizard", name=name, pid="local")
        accounts.apply_unlocks(p, name)
        assert p.backpack_size == 9

        saved = p.full_state()
        restored = Player.from_full_state(saved)
        assert restored.backpack_size == 9, "a resumed character keeps its already-persisted size"
        # the real regression this guards: NOT calling apply_unlocks again here -
        # if a caller mistakenly did, this would become 10, silently double-granting
        print("check_resume_never_reapplies_unlocks: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    check_award_persist_reload_round_trip()
    check_spend_edge_cases()
    check_backpack_slot_purchase_has_real_effect()
    check_starting_xp_boost_is_power_neutral()
    check_resume_never_reapplies_unlocks()
    print("PASSED: echo currency checks all green.")
