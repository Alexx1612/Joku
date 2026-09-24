"""
Regression check for discoverable landmark POIs (Batch 12, track J): one
hand-placed, non-combat point of interest per biome, stamped without
overlapping other placed structures, that fires a one-time lore message +
guaranteed bonus loot bag the first time each player gets close - and does
NOT re-fire on later ticks while the same player is still nearby.

Run with: .venv\\Scripts\\python.exe tests\\check_landmarks.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import realm_sim, world
from game.entities import Player


def _build_sim():
    return realm_sim.RealmSim(bonus=False)


def check_landmarks_stamped_one_per_biome_no_collision():
    sim = _build_sim()
    # a rare skip (a biome with fewer than 3 lairs, or a rect collision) is
    # allowed by design - but with ~200 lairs spread over 10 biomes, losing
    # more than a couple to that would indicate a real placement bug
    assert len(sim.landmarks) >= 7, f"expected most/all 10 landmarks to stamp, got {len(sim.landmarks)}"
    seen_biomes = set()
    for lm in sim.landmarks:
        assert lm["biome"] not in seen_biomes, f"duplicate landmark for biome {lm['biome']}"
        seen_biomes.add(lm["biome"])
        assert lm["name"] and lm["lore"], "every landmark needs a real name + lore string"
        tile = sim.realm_map.tile_at(lm["pos"].x, lm["pos"].y)
        assert tile != world.WATER, f"{lm['name']} landed in water"
        # confirm the themed prop cluster actually got written to the grid
        # somewhere in the landmark's own footprint, not just the ground clear
        gx = int(lm["pos"].x // 32)
        gy = int(lm["pos"].y // 32)
        r = world.LANDMARK_RADIUS + 1
        footprint_tiles = {
            sim.realm_map.grid[yy][xx]
            for yy in range(max(0, gy - r), min(len(sim.realm_map.grid), gy + r + 1))
            for xx in range(max(0, gx - r), min(len(sim.realm_map.grid[0]), gx + r + 1))
        }
        assert footprint_tiles & world.TALL_PROP_TILE_IDS, f"{lm['name']} has no prop cluster stamped"
    # no two landmarks should collapse onto (near enough to) the same spot -
    # a real symptom of the overlap-avoidance check silently failing
    for i, a in enumerate(sim.landmarks):
        for b in sim.landmarks[i + 1:]:
            assert a["pos"].distance_to(b["pos"]) > 64, "two landmarks landed suspiciously close together"
    print("check_landmarks_stamped_one_per_biome_no_collision: PASSED")


def check_landmark_discovery_fires_once_not_repeatedly():
    sim = _build_sim()
    assert sim.landmarks, "need at least one landmark for this check to mean anything"
    lm = sim.landmarks[0]

    player = Player("wizard", name="Tester", pid="p1")
    player.pos = pygame.Vector2(lm["pos"])  # standing exactly on it

    # find a seed that guarantees a non-empty elite loot roll so this test
    # doesn't flake on the ~1-in-5 chance every one of roll_loot's elite
    # drop checks fails at once
    seed = None
    for candidate in range(50):
        random.seed(candidate)
        if realm_sim.roll_loot(player.cls_name, "elite", 1.0):
            seed = candidate
            break
    assert seed is not None, "could not find a seed producing non-empty elite loot"

    bags_before = len(sim.ground_items)
    random.seed(seed)
    sim._tick_landmarks([player])

    fired = [e for e in sim.events if e[0] == "p1" and lm["name"] in e[1]]
    assert len(fired) == 1, f"expected exactly one discovery message, got {len(fired)}"
    assert len(sim.ground_items) == bags_before + 1, "expected exactly one bonus loot bag to spawn"

    # simulate the next tick: real callers clear sim.events via begin_tick()
    # every tick, then call update() -> _tick_landmarks() again while the
    # player is STILL standing on top of the landmark
    sim.events = []
    bags_after_first = len(sim.ground_items)
    sim._tick_landmarks([player])
    assert sim.events == [], "landmark re-fired for a player who already discovered it"
    assert len(sim.ground_items) == bags_after_first, "a second bonus loot bag should never spawn"
    print("check_landmark_discovery_fires_once_not_repeatedly: PASSED")


def check_landmark_discovery_is_per_player():
    sim = _build_sim()
    assert sim.landmarks
    lm = sim.landmarks[0]
    p1 = Player("wizard", name="A", pid="p1")
    p1.pos = pygame.Vector2(lm["pos"])
    p2 = Player("archer", name="B", pid="p2")
    p2.pos = pygame.Vector2(lm["pos"].x + 1000, lm["pos"].y + 1000)  # far away

    random.seed(0)
    sim._tick_landmarks([p1, p2])
    assert any(e[0] == "p1" for e in sim.events), "nearby player p1 should have discovered the landmark"
    assert not any(e[0] == "p2" for e in sim.events), "far-away player p2 should NOT have discovered it"

    # now bring p2 close too - it should discover it independently of p1's
    # already-visited state (per-player, not global, tracking)
    sim.events = []
    p2.pos = pygame.Vector2(lm["pos"])
    sim._tick_landmarks([p1, p2])
    assert not any(e[0] == "p1" for e in sim.events), "p1 already discovered it, should not re-fire"
    assert any(e[0] == "p2" for e in sim.events), "p2 should discover it independently on its own first approach"
    print("check_landmark_discovery_is_per_player: PASSED")


if __name__ == "__main__":
    check_landmarks_stamped_one_per_biome_no_collision()
    check_landmark_discovery_fires_once_not_repeatedly()
    check_landmark_discovery_is_per_player()
    print("PASSED: discoverable landmark checks all green.")
