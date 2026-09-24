"""
Batch 14: Echo currency is no longer death-only. RealmSim._reward() now banks
1 real echo to the ACCOUNT immediately for every 1000 cumulative lifetime XP
a player earns (Player._echo_xp_progress, never reset by level-ups - unlike
self.xp), while a separate per-life counter (Player._echoes_this_life) feeds
a 2x bonus on top at permadeath (accounts.award_echoes_for_death). Nothing is
held back until death: a player who never dies keeps every echo they already
banked while playing.

Run with: .venv\\Scripts\\python.exe tests\\check_echo_passive_accrual.py
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
from game import realm_sim
from game.entities import Enemy, Player


def _use_temp_accounts_dir():
    tmp = tempfile.mkdtemp(prefix="rr_echo_passive_test_")
    accounts.ACCOUNTS_DIR = tmp
    accounts._LAST_USED_PATH = os.path.join(tmp, "_last_used.txt")
    return tmp


def _sim():
    return realm_sim.RealmSim(bonus=False)


def check_passive_accrual_across_many_kills():
    """125 trash kills (8 XP each = 1000 XP total) should bank exactly 1 echo,
    live, per threshold crossed - not held back, matching a real long play
    session rather than a single big kill."""
    tmp = _use_temp_accounts_dir()
    try:
        name = "PassiveGrinder"
        accounts.touch_account(name)
        sim = _sim()
        killer = Player("wizard", name=name, pid="local")

        for i in range(1, 126):  # 125 * 8 = 1000
            e = Enemy("bat", (0, 0))
            sim._reward(e, killer)
            if i < 125:
                assert accounts.get_echoes(name) == 0, (
                    f"no echo should bank before the 1000-XP threshold (kill {i}, "
                    f"progress={killer._echo_xp_progress})")
        assert killer._echo_xp_progress == 1000
        assert killer._echoes_this_life == 1, "exactly 1 echo banked at the 1000-XP mark"
        assert accounts.get_echoes(name) == 1, "must be saved to the ACCOUNT immediately, not held"

        # confirm it's a real disk write, not just an in-process value
        reloaded = accounts.load_account(name)
        assert reloaded["echoes"] == 1
        print("check_passive_accrual_across_many_kills: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_single_kill_crossing_threshold_banks_correctly():
    """A single kill landing right on/over a threshold boundary must bank
    the echo immediately, using pre-seeded progress near the boundary (the
    current RANK_XP values top out at 250 for a boss, so a single real kill
    can cross at most one 1000-XP threshold from any starting point - this
    exercises that real boundary precisely rather than an unreachable one)."""
    tmp = _use_temp_accounts_dir()
    try:
        name = "BoundaryTester"
        accounts.touch_account(name)
        sim = _sim()
        killer = Player("wizard", name=name, pid="local")
        killer._echo_xp_progress = 800  # a boss kill (250 XP) will push this to 1050

        boss = Enemy("boss", (0, 0))
        sim._reward(boss, killer)

        assert killer._echo_xp_progress == 1050
        assert killer._echoes_this_life == 1
        assert accounts.get_echoes(name) == 1
        print("check_single_kill_crossing_threshold_banks_correctly: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_threshold_math_handles_multiple_crossings_in_one_gain():
    """The banking formula itself (floor-division delta) is magnitude-
    agnostic - a hypothetically larger single XP gain that spans more than
    one 1000-XP multiple must bank that many echoes at once, not just 1.
    RANK_XP's current values (trash=8, elite=30, boss=250) can never
    naturally produce this in a single kill, so this drives RealmSim's own
    _reward() logic with a synthetic large gain via a stand-in enemy rank
    entry, rather than asserting on unreachable game data."""
    tmp = _use_temp_accounts_dir()
    try:
        name = "BigGainTester"
        accounts.touch_account(name)
        sim = _sim()
        killer = Player("wizard", name=name, pid="local")
        killer._echo_xp_progress = 500

        # Temporarily widen RANK_XP for boss to a large synthetic value to
        # prove the crossing-count math generalizes, then restore it - never
        # leaves shared state mutated for other tests.
        original_boss_xp = realm_sim.RANK_XP["boss"]
        realm_sim.RANK_XP["boss"] = 2600  # 500 + 2600 = 3100 -> crosses 3 thresholds
        try:
            boss = Enemy("boss", (0, 0))
            sim._reward(boss, killer)
        finally:
            realm_sim.RANK_XP["boss"] = original_boss_xp

        assert killer._echo_xp_progress == 3100
        assert killer._echoes_this_life == 3, "500->3100 crosses the 1000/2000/3000 marks = 3 echoes"
        assert accounts.get_echoes(name) == 3
        print("check_threshold_math_handles_multiple_crossings_in_one_gain: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_never_dying_keeps_passive_earnings():
    """A player who logs out mid-session (never dies) must keep every echo
    already banked while playing - passive accrual is not conditional on
    eventually dying."""
    tmp = _use_temp_accounts_dir()
    try:
        name = "SurvivorTester"
        accounts.touch_account(name)
        sim = _sim()
        killer = Player("wizard", name=name, pid="local")
        for _ in range(200):  # plenty to cross a couple thresholds via trash kills
            sim._reward(Enemy("bat", (0, 0)), killer)

        banked = accounts.get_echoes(name)
        assert banked > 0, "passive accrual must have banked something over 200 kills"
        assert banked == killer._echoes_this_life, "no death occurred - no bonus, just what was earned"
        # simulate "logging out": nothing else happens, no death path is called
        reloaded = accounts.load_account(name)
        assert reloaded["echoes"] == banked, "still there on disk with no death ever occurring"
        print("check_never_dying_keeps_passive_earnings: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_death_bonus_is_2x_echoes_this_life():
    tmp = _use_temp_accounts_dir()
    try:
        name = "DeathBonusTester"
        accounts.touch_account(name)
        sim = _sim()
        killer = Player("wizard", name=name, pid="local")
        killer._echo_xp_progress = 4000
        killer._echoes_this_life = 4
        accounts.add_echoes(name, 4)  # simulate the 4 already having been banked live

        bonus = accounts.award_echoes_for_death(name, killer._echoes_this_life)
        assert bonus == 8, "death bonus must be exactly 2x echoes_this_life (2*4=8)"
        assert accounts.get_echoes(name) == 12, "4 already banked + 8 death bonus = 12 total"
        print("check_death_bonus_is_2x_echoes_this_life: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_death_with_zero_echoes_this_life_is_safe():
    """Dying before ever crossing the first 1000-XP threshold must not crash
    and must not produce a negative balance or a bonus out of thin air."""
    tmp = _use_temp_accounts_dir()
    try:
        name = "EarlyDeathTester"
        accounts.touch_account(name)
        killer = Player("wizard", name=name, pid="local")
        assert killer._echoes_this_life == 0

        bonus = accounts.award_echoes_for_death(name, killer._echoes_this_life)
        assert bonus == 0, "0 echoes this life -> 0 death bonus, never negative or fabricated"
        assert accounts.get_echoes(name) == 0
        print("check_death_with_zero_echoes_this_life_is_safe: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_full_state_round_trip_preserves_life_progress():
    """A resumed character (save/load, not a death) must keep its exact
    in-progress echo tracking - otherwise quitting and reloading would
    silently reset the death-bonus multiplier back to 0."""
    p = Player("wizard", name="ResumeEchoTester", pid="local")
    p._echo_xp_progress = 1750
    p._echoes_this_life = 1

    saved = p.full_state()
    restored = Player.from_full_state(saved)
    assert restored._echo_xp_progress == 1750
    assert restored._echoes_this_life == 1
    print("check_full_state_round_trip_preserves_life_progress: PASSED")


if __name__ == "__main__":
    check_passive_accrual_across_many_kills()
    check_single_kill_crossing_threshold_banks_correctly()
    check_threshold_math_handles_multiple_crossings_in_one_gain()
    check_never_dying_keeps_passive_earnings()
    check_death_bonus_is_2x_echoes_this_life()
    check_death_with_zero_echoes_this_life_is_safe()
    check_full_state_round_trip_preserves_life_progress()
    print("PASSED: echo passive accrual checks all green.")
