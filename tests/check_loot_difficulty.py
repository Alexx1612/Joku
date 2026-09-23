"""
Quick regression check for per-mob loot difficulty scaling (see
entities.difficulty_fraction / items.roll_loot's `difficulty` param).

Not a real test suite (see README's v0.3 roadmap - that hasn't been built yet),
just a standalone script that rolls loot many times for the easiest and
hardest mob of each rank and confirms the average tier ACTUALLY shifts
- not just "it compiles" - and that it never shifts the wrong direction or
breaks a rank's own tier envelope.

Run with: .venv\\Scripts\\python.exe tests\\check_loot_difficulty.py
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
from game.items import roll_loot, SLOT_EGG

ROLLS = 20000
CLASS = "wizard"

RANK_TIER_ENVELOPE = {"trash": (1, 3), "elite": (1, 11), "boss": (7, 11)}


def _tiered_stats(kind, rolls=ROLLS):
    """Rolls loot `rolls` times for `kind` and returns (avg_tier, tier_counter,
    n_tiered_drops) over every TIERED (non-UT, non-egg) item that dropped."""
    rank = entities.ENEMY_KINDS[kind]["rank"]
    difficulty = entities.difficulty_fraction(kind)
    random.seed(1234)  # same RNG stream for every kind so only `difficulty` differs
    tiers = []
    for _ in range(rolls):
        for _bag_color, item in roll_loot(CLASS, rank, difficulty):
            # eggs always drop at a flat tier=1 regardless of rank/difficulty (pre-
            # existing behavior, untouched by this change) - only weapon/armor/
            # ring/ability drops go through the difficulty-nudged tier bands
            if item.tier and not item.is_ut and item.slot != SLOT_EGG:
                tiers.append(item.tier)
    avg = sum(tiers) / len(tiers) if tiers else 0.0
    return avg, tiers


def _extremes_for_rank(rank):
    kinds = [k for k, d in entities.ENEMY_KINDS.items() if d["rank"] == rank]
    easiest = min(kinds, key=entities.difficulty_fraction)
    hardest = max(kinds, key=entities.difficulty_fraction)
    return easiest, hardest


def main():
    failures = []
    print(f"{'rank':7s} {'easy mob':16s} {'avg tier':9s} | {'hard mob':16s} {'avg tier':9s} | shift")
    for rank in ("trash", "elite", "boss"):
        easy_kind, hard_kind = _extremes_for_rank(rank)
        easy_avg, easy_tiers = _tiered_stats(easy_kind)
        hard_avg, hard_tiers = _tiered_stats(hard_kind)
        shift = hard_avg - easy_avg
        print(f"{rank:7s} {easy_kind:16s} {easy_avg:9.3f} | {hard_kind:16s} {hard_avg:9.3f} | +{shift:.3f}")

        lo, hi = RANK_TIER_ENVELOPE[rank]
        if not all(lo <= t <= hi for t in easy_tiers + hard_tiers):
            failures.append(f"{rank}: a rolled tier fell outside the rank's own [{lo},{hi}] envelope")
        if hard_avg <= easy_avg:
            failures.append(f"{rank}: hardest mob ({hard_kind}, avg {hard_avg:.3f}) did not "
                             f"out-drop the easiest ({easy_kind}, avg {easy_avg:.3f})")
        min_expected_shift = 0.3  # a real, noticeable shift - not just noise
        if shift < min_expected_shift:
            failures.append(f"{rank}: shift of {shift:.3f} tiers is smaller than the "
                             f"expected minimum ({min_expected_shift})")

    # the easiest mob of each rank must still be able to reach that rank's full
    # original ceiling (macro-structure/bag-odds are untouched, only the floor moves)
    for rank in ("trash", "elite", "boss"):
        easy_kind, _ = _extremes_for_rank(rank)
        _, tiers = _tiered_stats(easy_kind)
        lo, hi = RANK_TIER_ENVELOPE[rank]
        if rank != "boss" and max(tiers, default=0) < hi - 1:
            # elite/trash draw from more than one weapon/armor/ring/ability table,
            # so the observed max should land at or within 1 of the band's own top
            failures.append(f"{rank}: easiest mob ({easy_kind}) never rolled near the "
                             f"rank's top tier ({hi}) across {ROLLS} rolls - ceiling may be broken")

    print()
    if failures:
        print(f"FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("PASSED: loot difficulty scaling shifts the tier distribution as intended.")


if __name__ == "__main__":
    main()
