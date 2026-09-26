"""
Quick regression check for the host-settable rotating live-event system
(game/live_events.py): the RR_EVENT environment variable should meaningfully
change (a) how much loot a kill drops (items.roll_loot) and (b) how likely
a Blood Moon is on the first night (realm_sim.RealmSim._update_day_night),
with no event active behaving exactly as before.

Not a real test suite (see README's v0.3 roadmap), just a standalone script
- see tests/check_loot_difficulty.py for the established pattern this
follows (real behavioral measurement, not just "it compiles").

Run with: .venv\\Scripts\\python.exe tests\\check_live_events.py
"""
import importlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

os.environ["RR_EVENT_ROTATION"] = "off"  # baseline = truly no event, whatever the clock says
from game import live_events
from game import items
from game import realm_sim

ROLLS = 4000
NIGHT_TRIALS = 4000


def _set_event(name):
    """Sets RR_EVENT and reloads live_events in place - items.py/realm_sim.py
    hold a reference to the live_events MODULE object (not a copied function),
    so reloading it here is visible to them without re-importing anything."""
    if name is None:
        os.environ.pop("RR_EVENT", None)
    else:
        os.environ["RR_EVENT"] = name
    importlib.reload(live_events)


def _avg_loot_count(rank, rolls=ROLLS):
    random.seed(7777)
    total = 0
    for _ in range(rolls):
        total += len(items.roll_loot("wizard", rank, 0.5))
    return total / rolls


def _first_night_blood_moon_rate(trials=NIGHT_TRIALS):
    sim = realm_sim.RealmSim(bonus=False)
    hits = 0
    for _ in range(trials):
        sim.day_time = 0.0
        sim._was_night = False
        sim._nights_since_blood_moon = 0
        sim.blood_moon_active = False
        for _ in range(int(realm_sim.DAY_LENGTH) + 2):
            was_night_before = sim._was_night
            sim._update_day_night(1.0)
            if sim._was_night and not was_night_before:
                if sim.blood_moon_active:
                    hits += 1
                break
    return hits / trials


def main():
    failures = []

    print("-- loot_rolls multiplier (double_loot) --")
    _set_event(None)
    baseline_trash = _avg_loot_count("trash")
    baseline_boss = _avg_loot_count("boss")
    _set_event("double_loot")
    boosted_trash = _avg_loot_count("trash")
    boosted_boss = _avg_loot_count("boss")
    _set_event(None)
    print(f"  trash: baseline={baseline_trash:.3f}  double_loot={boosted_trash:.3f}")
    print(f"  boss:  baseline={baseline_boss:.3f}  double_loot={boosted_boss:.3f}")
    # "double" should roughly double the expected count (loose bound - avoid flakiness)
    if boosted_trash < baseline_trash * 1.6:
        failures.append(f"double_loot trash avg ({boosted_trash:.3f}) did not meaningfully "
                         f"exceed baseline*1.6 ({baseline_trash * 1.6:.3f})")
    if boosted_boss < baseline_boss * 1.6:
        failures.append(f"double_loot boss avg ({boosted_boss:.3f}) did not meaningfully "
                         f"exceed baseline*1.6 ({baseline_boss * 1.6:.3f})")

    print("-- blood_moon_chance multiplier (blood_moon_week) --")
    _set_event(None)
    baseline_rate = _first_night_blood_moon_rate()
    _set_event("blood_moon_week")
    boosted_rate = _first_night_blood_moon_rate()
    _set_event(None)
    print(f"  first-night Blood Moon rate: baseline={baseline_rate:.3f} "
          f"(expected ~{realm_sim.BLOOD_MOON_CHANCE:.3f}), "
          f"blood_moon_week={boosted_rate:.3f} (expected ~{min(0.5, realm_sim.BLOOD_MOON_CHANCE * 2.5):.3f})")
    if boosted_rate <= baseline_rate * 1.5:
        failures.append(f"blood_moon_week rate ({boosted_rate:.3f}) did not meaningfully exceed "
                         f"baseline*1.5 ({baseline_rate * 1.5:.3f})")
    expected_baseline = realm_sim.BLOOD_MOON_CHANCE
    if abs(baseline_rate - expected_baseline) > 0.03:
        failures.append(f"no-event Blood Moon rate ({baseline_rate:.3f}) drifted from the plain "
                         f"BLOOD_MOON_CHANCE constant ({expected_baseline:.3f}) by more than 0.03 - "
                         f"live_events may be leaking a multiplier when no event is active")

    print("-- unknown RR_EVENT value is ignored, not a crash --")
    _set_event("not_a_real_event")
    if live_events.ACTIVE_EVENT is not None:
        failures.append("an unrecognized RR_EVENT value was accepted instead of falling back to None")
    if live_events.active_label() is not None:
        failures.append("active_label() returned a label with no real active event")
    _set_event(None)

    print()
    if failures:
        print(f"FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("PASSED: live events (double_loot, blood_moon_week) meaningfully change behavior; "
          "no event behaves exactly as baseline; unknown events are ignored safely.")


if __name__ == "__main__":
    main()
