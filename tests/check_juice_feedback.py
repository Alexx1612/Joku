"""
Regression check for the "juice trio" (hit-stop + screen-shake + impact
particles) added on top of the existing hit-flash/damage-popup feedback.
Covers normal cases (a regular hit on a trash mob, a player getting hit)
and the boss-scaling edge case, plus the real integration path (a full
RealmSim melee-contact tick, not just the isolated dispatch() call) - the
same class of bug this project has been bitten by before (a real call site
not actually wired to a function that works fine in isolation).

Run with: .venv\\Scripts\\python.exe tests\\check_juice_feedback.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game import realm_sim, vfx
from game.entities import Enemy, Bullet, Player


def _reset_vfx_state():
    vfx._particles.clear()
    vfx._rings.clear()
    vfx._shake_mag = 0.0
    vfx._shake_time = 0.0
    vfx._hitstop_until = 0


def check_hitstop_timing():
    _reset_vfx_state()
    assert vfx.apply_hitstop(1 / 30) == 1 / 30, "no hitstop triggered yet - dt must pass through unchanged"

    vfx.trigger_hitstop(50)
    assert vfx.apply_hitstop(1 / 30) == 0.0, "an active hitstop must zero dt"

    # "bigger wins, doesn't stack/shorten" - same rule as trigger_shake
    vfx.trigger_hitstop(10)
    assert vfx.apply_hitstop(1 / 30) == 0.0, "a smaller hitstop must not shorten an already-longer one"

    time.sleep(0.07)  # real wall-clock wait - apply_hitstop is timed off pygame.time.get_ticks(), not dt
    assert vfx.apply_hitstop(1 / 30) == 1 / 30, "hitstop must actually expire on real time and stop hanging"
    print("check_hitstop_timing: PASSED")


def check_dispatch_scales_by_severity():
    _reset_vfx_state()
    vfx.dispatch([("hit_enemy", 0, 0, (255, 220, 90))])
    trash_particles = len(vfx._particles)
    trash_hitstop_active = vfx.apply_hitstop(1 / 30) == 0.0
    assert trash_particles > 0, "hit_enemy must spawn impact particles"
    assert trash_hitstop_active, "hit_enemy must trigger a (small) hitstop"

    _reset_vfx_state()
    vfx.dispatch([("hit_player_by_boss", 0, 0, (255, 90, 90))])
    boss_particles = len(vfx._particles)
    assert boss_particles > trash_particles, "a boss hitting the player must feel heavier than a trash hit"
    print("check_dispatch_scales_by_severity: PASSED")


def check_bullet_hits_enemy_emits_juice_event():
    sim = realm_sim.RealmSim.__new__(realm_sim.RealmSim)
    sim.damage_popups = []
    sim.events = []
    sim.vfx_events = []
    sim.sound_events = []
    sim.obstacles = []
    killer = Player("wizard", "K", pid="p1")

    goblin = Enemy("goblin", (100, 100)); goblin.pos = pygame.Vector2(100, 100)
    b = Bullet((100, 100), (1, 0), 5, "p1", (255, 220, 90), 0, 10, 1.0)
    b.pos = pygame.Vector2(100, 100)
    sim.enemies = [goblin]
    sim.bullets = [b]
    sim._resolve_bullet_hits({"p1": killer})
    kinds = [k for k, *_ in sim.vfx_events]
    assert "hit_enemy" in kinds, "a bullet hitting a normal enemy must emit hit_enemy"
    assert "hit_boss" not in kinds

    sim.vfx_events = []
    boss = Enemy("frost_monarch", (100, 100)); boss.pos = pygame.Vector2(100, 100)
    assert boss.rank == "boss"
    b2 = Bullet((100, 100), (1, 0), 5, "p1", (255, 220, 90), 0, 10, 1.0)
    b2.pos = pygame.Vector2(100, 100)
    sim.enemies = [boss]
    sim.bullets = [b2]
    sim._resolve_bullet_hits({"p1": killer})
    kinds2 = [k for k, *_ in sim.vfx_events]
    assert "hit_boss" in kinds2, "a bullet hitting a boss must emit the heavier hit_boss kind"
    assert "hit_enemy" not in kinds2
    print("check_bullet_hits_enemy_emits_juice_event: PASSED")


def check_enemy_bullet_hits_player_emits_juice_event():
    sim = realm_sim.RealmSim.__new__(realm_sim.RealmSim)
    sim.damage_popups = []
    sim.events = []
    sim.vfx_events = []
    sim.obstacles = []
    sim.enemies = []
    p = Player("wizard", "Target", pid="p1")
    p.pos = pygame.Vector2(50, 50)
    b = Bullet((50, 50), (1, 0), 5, "enemy", (255, 90, 90), 0, 10, 1.0)
    b.pos = pygame.Vector2(50, 50)
    sim.bullets = [b]
    sim._resolve_bullet_hits({"p1": p})
    kinds = [k for k, *_ in sim.vfx_events]
    assert "hit_player" in kinds, "an enemy bullet hitting the player must emit hit_player"
    print("check_enemy_bullet_hits_player_emits_juice_event: PASSED")


def check_melee_contact_emits_juice_event_real_sim():
    """The real integration path: a full RealmSim tick, not an isolated
    method call - the exact class of bug (a working function whose real
    call site was never actually wired up) this project has shipped once."""
    sim = realm_sim.RealmSim(bonus=False)
    p = Player("wizard", "Bumped", pid="p1")
    p.pos = pygame.Vector2(sim.spawn_point())
    p.hp = p.hp_max

    goblin = Enemy("goblin", (p.pos.x, p.pos.y))
    goblin.pos = pygame.Vector2(p.pos)
    goblin.contact_cd = 0.0
    goblin.aggro = True
    sim.enemies = [goblin]
    sim.begin_tick()
    sim.update(1 / 30, {"p1": p})
    kinds = [k for k, *_ in sim.vfx_events]
    assert "hit_player" in kinds, "a real melee contact tick must emit hit_player"

    boss = Enemy("frost_monarch", (p.pos.x, p.pos.y))
    boss.pos = pygame.Vector2(p.pos)
    boss.contact_cd = 0.0
    boss.aggro = True
    p.hp = p.hp_max
    sim.enemies = [boss]
    sim.begin_tick()
    sim.update(1 / 30, {"p1": p})
    kinds2 = [k for k, *_ in sim.vfx_events]
    assert "hit_player_by_boss" in kinds2, "a real melee contact tick from a boss must emit hit_player_by_boss"
    print("check_melee_contact_emits_juice_event_real_sim: PASSED")


if __name__ == "__main__":
    check_hitstop_timing()
    check_dispatch_scales_by_severity()
    check_bullet_hits_enemy_emits_juice_event()
    check_enemy_bullet_hits_player_emits_juice_event()
    check_melee_contact_emits_juice_event_real_sim()
    print("PASSED: juice feedback (hit-stop/shake/impact particles) checks all green.")
