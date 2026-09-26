"""
Regression checks for player-side damage mitigation (constants.player_defense)
and per-class defense growth. Before this pass every lvl-20 class sat on
apply_defense's 10% floor (enemy hits never scale with level, player deF
grows every level), and Priest grew deF like a heavy class.
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()

from game import constants as C
from game import achievements
from game.entities import Player, ENEMY_KINDS, CLASS_BASE, BOSS_KINDS

achievements.unlock = lambda *a, **k: (False, None)  # don't write achievement files from a test


def _lvl20_def(cls, runs=12):
    total = 0
    for seed in range(runs):
        random.seed(seed)
        p = Player(cls, name="DefCheck", pid="DefCheck")
        p.armor = p.ring = p.ability = None
        while p.level < 20:
            p.gain_xp(10 ** 6)
        total += p.deF
    return total / runs


def _avg_hit(rank):
    kinds = BOSS_KINDS if rank == "boss" else [k for k, d in ENEMY_KINDS.items() if d["rank"] == rank and d["dmg"][1] > 0]
    return sum(sum(ENEMY_KINDS[k]["dmg"]) / 2 for k in kinds) / len(kinds)


def check_curve_properties():
    assert C.player_defense(0, 50) == 0
    assert C.player_defense(1, 500) == 1  # a real hit always does at least 1
    assert C.player_defense(20, 0) == 20
    frac = [C.player_defense(100, d, whole=False) / 100 for d in (0, 15, 40, 75, 150)]
    assert all(a > b for a, b in zip(frac, frac[1:])), frac  # more deF always helps...
    assert frac[-1] > 0.3  # ...but never makes you immune
    print("check_curve_properties: PASSED")


def check_lvl20_class_spread():
    defs = {cls: _lvl20_def(cls) for cls in CLASS_BASE}
    tankiest, squishiest = max(defs.values()), min(defs.values())
    for rank in ("trash", "elite", "boss"):
        hit = _avg_hit(rank)
        tank_pct = C.player_defense(hit, tankiest, whole=False) / hit
        squish_pct = C.player_defense(hit, squishiest, whole=False) / hit
        assert 0.40 <= tank_pct <= 0.65, (rank, tank_pct)
        assert 0.80 <= squish_pct <= 0.95, (rank, squish_pct)
    print("  lvl-20 deF:", {k: round(v, 1) for k, v in defs.items()})
    print("check_lvl20_class_spread: PASSED")


def check_priest_not_a_tank():
    priest, wizard, paladin = _lvl20_def("priest"), _lvl20_def("wizard"), _lvl20_def("paladin")
    assert "deF" not in CLASS_BASE["priest"]["growth"]
    assert priest < wizard + 10, (priest, wizard)
    assert paladin > priest * 2, (paladin, priest)
    print("check_priest_not_a_tank: PASSED")


def check_take_damage_uses_curve():
    p = Player("warrior", name="DefCheck", pid="DefCheck")
    p.armor = p.ring = p.ability = None
    p.hp = p.hp_max = 1000
    got = p.take_damage(20)
    assert got == C.player_defense(20, p.total_stat("deF")) and got > 2  # old formula gave the 10% floor
    assert p.take_damage(20, pierce_armor=True) == 20
    print("check_take_damage_uses_curve: PASSED")


if __name__ == "__main__":
    check_curve_properties()
    check_lvl20_class_spread()
    check_priest_not_a_tank()
    check_take_damage_uses_curve()
    print("PASSED: defense balance checks all green.")
