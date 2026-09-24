"""
Regression check for Batch 14 Track B2 (mini-bosses for islands 6-10).

Islands 6-10 (by ISLAND_NAMES order: Tideglass Sanctum, Thornrock Shard,
Driftbell Cloister, Ashenreach Shard, Abyssal Hymnal) each get one new,
genuinely tougher named mini-boss leading their flare/song wave. This
check confirms: real distinct sprites, the wave-spawn actually includes
the mini-boss, the mini-boss is meaningfully tougher than the regular
anchor guardians, and the per-island reward only fires once the
mini-boss itself (not just its escort) is dead.

Run with: .venv\\Scripts\\python.exe tests\\check_island_mini_bosses_b2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from game import sprites, realm_sim
from game.entities import Enemy, Player, ENEMY_KINDS

B2_KINDS = [
    "tideglass_warden", "thornrock_colossus", "driftbell_matriarch",
    "ashenreach_devourer", "abyssal_choirmaster",
]

BASE_KINDS = [
    "bat", "ghost", "skeleton", "imp", "goblin", "scorpion", "yeti",
    "troll", "harpy", "salamander", "panther", "ghoul", "frost_wraith",
    "cave_lurker",
]


def _pixels(surf):
    return pygame.image.tostring(surf, "RGBA")


def check_sprites_distinct():
    surfs = {k: sprites.enemy_sprite(k) for k in B2_KINDS}
    for k, s in surfs.items():
        assert s is not None and s.get_width() > 0 and s.get_height() > 0, f"{k}: no surface"
    pix = {k: _pixels(s) for k, s in surfs.items()}
    for i, a in enumerate(B2_KINDS):
        for b in B2_KINDS[i + 1:]:
            assert pix[a] != pix[b], f"{a} and {b} are pixel-identical"
        for base in BASE_KINDS:
            assert pix[a] != _pixels(sprites.enemy_sprite(base)), f"{a} pixel-identical to base '{base}'"
    print("check_sprites_distinct: PASSED")


def check_mini_bosses_tougher_than_anchors():
    for kind in B2_KINDS:
        d = ENEMY_KINDS[kind]
        # normalized to "boss" during integration for consistency with B1's
        # mini-bosses (same boss-tier treatment: hit_kind "hit_boss" in vfx,
        # BOSS_KINDS sprite scaling) - both B1 and B2 are meant to be real
        # named mini-bosses, not just tougher elites
        assert d["rank"] == "boss", f"{kind}: expected boss rank, got {d['rank']}"
        assert d["hp"] > ENEMY_KINDS["cinder_warden"]["hp"] * 2, (
            f"{kind}: hp {d['hp']} not meaningfully tougher than an anchor guardian")
        assert d["dmg"][1] >= ENEMY_KINDS["cinder_warden"]["dmg"][1], f"{kind}: dmg not tougher than an anchor"
    print("check_mini_bosses_tougher_than_anchors: PASSED")


def check_wave_spawn_includes_mini_boss():
    sim = realm_sim.RealmSim(bonus=False)
    my_indices = {5, 6, 7, 8, 9}
    for isl in sim.islands:
        if isl["idx"] not in my_indices:
            continue
        isl["cooldown"] = 0.0
        isl["alive_guardians"] = 0
    before = len(sim.enemies)
    sim._tick_island_events(0.0)
    new_enemies = sim.enemies[before:]
    kinds_by_island = {}
    for e in new_enemies:
        idx = getattr(e, "island_idx", None)
        if idx in my_indices:
            kinds_by_island.setdefault(idx, []).append(e.kind)
    # dict renamed to ISLAND_MINI_BOSS during integration (matching B1's
    # naming, which B2's entries were merged into - same dict, all 10
    # islands) - only check THIS test's islands (5-9); islands 0-4 (B1's)
    # weren't cooldown-reset above so they won't have spawned a wave yet
    for idx, expected_boss in realm_sim.ISLAND_MINI_BOSS.items():
        if idx not in my_indices:
            continue
        assert idx in kinds_by_island, f"island {idx}: no wave spawned"
        assert expected_boss in kinds_by_island[idx], (
            f"island {idx}: mini-boss {expected_boss} not in spawned wave {kinds_by_island[idx]}")
    print("check_wave_spawn_includes_mini_boss: PASSED")


def check_reward_requires_mini_boss_dead():
    sim = realm_sim.RealmSim(bonus=False)
    isl = next(i for i in sim.islands if i["idx"] == 6)  # thornrock_colossus
    isl["cooldown"] = 0.0
    isl["alive_guardians"] = 0
    before = len(sim.enemies)
    sim._tick_island_events(0.0)
    wave = sim.enemies[before:]
    wave = [e for e in wave if getattr(e, "island_idx", None) == 6]
    assert any(e.kind == "thornrock_colossus" for e in wave), "wave missing its mini-boss"
    killer = Player("wizard", "Tester", pid="p1")

    boss = next(e for e in wave if e.kind == "thornrock_colossus")
    escorts = [e for e in wave if e.kind != "thornrock_colossus"]

    bags_before = len(sim.ground_items)
    for e in escorts:
        sim._progress_island_event(e, killer)
    assert len(sim.ground_items) == bags_before, "reward fired before the mini-boss died"
    assert isl["alive_guardians"] == 1, "alive_guardians should reflect only the boss remaining"

    # roll_loot's rolls are probabilistic even at max difficulty (a real,
    # pre-existing property of the loot system, not something this track
    # touches) - retry a few times so this test isn't flaky on an unlucky
    # empty roll, while still proving the reward path actually fires.
    for _ in range(20):
        sim._progress_island_event(boss, killer)
        if len(sim.ground_items) > bags_before:
            break
    assert len(sim.ground_items) > bags_before, "reward did not fire once the mini-boss died"
    print("check_reward_requires_mini_boss_dead: PASSED")


if __name__ == "__main__":
    check_sprites_distinct()
    check_mini_bosses_tougher_than_anchors()
    check_wave_spawn_includes_mini_boss()
    check_reward_requires_mini_boss_dead()
