"""
Regression check for the roaming World Boss incursion (Batch 12, track C):
a rare, time-gated, server-wide-announced boss that spawns far from every
player and is tracked independently of _maybe_spawn_boss's every-40-kill
open-Realm boss.

Run with: .venv\\Scripts\\python.exe tests\\check_world_boss.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import realm_sim
from game.entities import Player


def _fresh_sim():
    return realm_sim.RealmSim(bonus=False)


def check_world_boss_spawns_after_cooldown():
    sim = _fresh_sim()
    p = Player("wizard", "Watcher", pid="p1")
    p.pos = sim.spawn_point()
    players = {"p1": p}

    assert sim.world_boss is None, "no world boss should exist at world-gen"
    sim.world_boss_cd = 0.05  # fast-forward past the real 15-25 minute cooldown

    sim.begin_tick()
    sim.update(0.1, players)

    assert sim.world_boss is not None, "world boss should spawn once its cooldown elapses"
    assert getattr(sim.world_boss, "is_world_boss", False) is True
    assert sim.world_boss in sim.enemies, "the world boss must be a real, simulated Enemy"
    assert sim.world_boss.rank == "boss"
    dist = sim.world_boss.pos.distance_to(p.pos)
    assert dist > 250, f"world boss spawned too close to the only player ({dist:.0f}px) - not a real incursion"

    announced = [msg for _pid, msg, _color in sim.events if "shadow gathers" in msg]
    assert announced, "spawning a world boss must push a server-wide announcement"
    print("check_world_boss_spawns_after_cooldown: PASSED")


def check_world_boss_defeat_and_bonus_loot():
    sim = _fresh_sim()
    p = Player("wizard", "Slayer", pid="p1")
    p.pos = sim.spawn_point()
    players = {"p1": p}
    sim.world_boss_cd = 0.05
    sim.begin_tick()
    sim.update(0.1, players)
    boss = sim.world_boss
    assert boss is not None

    boss.pos = pygame.Vector2(p.pos)
    bags_before = len(sim.ground_items)
    sim._reward(boss, p)
    boss.alive = False
    sim.enemies = [e for e in sim.enemies if e.alive]

    assert sim.world_boss is None, "defeating the world boss must clear the tracking field"
    assert len(sim.ground_items) > bags_before, "a world boss kill should drop real loot bags"
    defeated = [msg for _pid, msg, _color in sim.events if "fallen" in msg]
    assert defeated, "defeating a world boss must push its own announcement"
    print("check_world_boss_defeat_and_bonus_loot: PASSED")


def check_world_boss_never_double_spawns():
    sim = _fresh_sim()
    p = Player("wizard", "Idle", pid="p1")
    p.pos = sim.spawn_point()
    players = {"p1": p}
    sim.world_boss_cd = 0.05
    sim.begin_tick()
    sim.update(0.1, players)
    first = sim.world_boss
    assert first is not None

    # cooldown is already spent; ticking further while one is alive must not spawn a second
    for _ in range(5):
        sim.begin_tick()
        sim.update(1.0, players)
    assert sim.world_boss is first, "a second world boss must never spawn while one is still alive"
    print("check_world_boss_never_double_spawns: PASSED")


def check_bonus_room_never_spawns_world_boss():
    sim = realm_sim.RealmSim(bonus=True, theme="cave")
    p = Player("wizard", "Delver", pid="p1")
    p.pos = pygame.Vector2(0, 0)
    players = {"p1": p}
    sim.world_boss_cd = 0.0
    for _ in range(10):
        sim.begin_tick()
        sim.update(0.2, players)
    assert sim.world_boss is None, "a bonus-room dungeon instance must never spawn the open-Realm world boss"
    print("check_bonus_room_never_spawns_world_boss: PASSED")


if __name__ == "__main__":
    check_world_boss_spawns_after_cooldown()
    check_world_boss_defeat_and_bonus_loot()
    check_world_boss_never_double_spawns()
    check_bonus_room_never_spawns_world_boss()
    print("PASSED: World Boss checks all green.")
