"""
Precise combat: players fire ~half as often (entities.PLAYER_FIRE_RATE_MULT) but every hit
lands ~1.8x harder (realm_sim.PLAYER_DAMAGE_MULT) - about the same DPS, but a miss now
costs twice as much; aim assist is a tight 7-degree nudge; top-of-range rolls are "heavy"
hits with a gold popup.

Run with: .venv\\Scripts\\python.exe tests\\check_combat_precision.py
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

from game import constants as C
from game import realm_sim as rs, entities as E
from game.realm_sim import RealmSim
from game.entities import Player, Enemy


def check_slower_but_heavier():
    assert E.PLAYER_FIRE_RATE_MULT == 0.55 and rs.PLAYER_DAMAGE_MULT == 1.8
    p = Player("wizard", "Aim", pid="a")
    old_interval = 1.0 / C.attacks_per_sec(p.total_stat("dex"))
    assert abs(p.atk_interval() - old_interval / 0.55) < 1e-6
    sim = RealmSim(bonus=True, theme="cave", difficulty_name="Easy")
    random.seed(3)
    shots = [sim.player_fire(p, pygame.Vector2(1, 0))[0].dmg for _ in range(400)]
    mn, mx = p.weapon.min_dmg, p.weapon.max_dmg
    old_avg = (mn + mx) / 2 * (p.total_stat("att") + 25) / 50
    new_avg = sum(shots) / len(shots)
    assert 1.6 < new_avg / old_avg < 2.0, (new_avg, old_avg)
    dps_ratio = (new_avg / p.atk_interval()) / (old_avg / old_interval)
    assert 0.9 < dps_ratio < 1.1, dps_ratio  # about the same DPS
    print(f"check_slower_but_heavier: PASSED (hit x{new_avg / old_avg:.2f}, DPS x{dps_ratio:.2f})")


def check_aim_cone_and_heavy_hits():
    assert rs.AUTO_AIM_CONE_DEG == 7
    p = Player("warrior", "Heavy", pid="h")
    p.weapon.min_dmg, p.weapon.max_dmg = 10, 30
    sim = RealmSim(bonus=True, theme="cave", difficulty_name="Easy")
    random.seed(1)
    flags = [sim.player_fire(p, pygame.Vector2(1, 0))[0].heavy for _ in range(300)]
    assert 0.05 < sum(flags) / 300 < 0.3, sum(flags)
    # a heavy hit shows the gold popup + crack vfx
    sim.enemies = []
    e = Enemy("goblin", pygame.Vector2(p.pos) + pygame.Vector2(40, 0))
    e.hp = e.hp_max = 10 ** 6
    sim.enemies = [e]
    b = sim.player_fire(p, pygame.Vector2(1, 0))[0]
    b.heavy = True
    b.pos = pygame.Vector2(e.pos)
    sim.bullets = [b]
    sim.begin_tick()
    sim._resolve_bullet_hits({p.pid: p})
    assert any(pp[3] == (255, 160, 30) for pp in sim.damage_popups)
    assert any(v[0] == "heavy_hit" for v in sim.vfx_events)
    print("check_aim_cone_and_heavy_hits: PASSED")


if __name__ == "__main__":
    check_slower_but_heavier()
    check_aim_cone_and_heavy_hits()
    print("PASSED: combat precision checks all green.")
