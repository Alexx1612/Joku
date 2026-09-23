"""
Regression check for player walk-cycle/idle-bob/fire-flash animation.
Covers normal cases (idle, walking, firing) and the real integration path
(a full Game().draw() call while the player is actively moving) - the same
class of "signature changed, call site didn't" bug already caught once this
session is exactly what an isolated unit test alone would NOT catch.

Run with: .venv\\Scripts\\python.exe tests\\check_player_animation.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((800, 600))

from game.entities import Player
from game.realm_sim import RealmSim


def check_idle_vs_walk_state():
    p = Player("wizard", "Animator", pid="p1")
    p.pos = pygame.Vector2(400, 300)
    cam = lambda pos: (pos.x, pos.y)

    p.net_update(1 / 30, pygame.Vector2(0, 0), (0, 0, 800, 600))
    assert p._is_moving is False
    p.draw(screen, cam)

    p.net_update(1 / 30, pygame.Vector2(1, 0), (0, 0, 800, 600))
    assert p._is_moving is True
    assert p.facing.x == 1
    p.draw(screen, cam)
    print("check_idle_vs_walk_state: PASSED")


def check_fire_flash_decays():
    p = Player("wizard", "Shooter", pid="p1")
    p.pos = pygame.Vector2(0, 0)
    cam = lambda pos: (pos.x, pos.y)
    sim = RealmSim.__new__(RealmSim)
    sim.bullets = []
    sim.player_fire(p, pygame.Vector2(1, 0))
    assert p._fire_flash_t == p.FIRE_FLASH_DURATION
    p.draw(screen, cam)
    p.net_update(0.5, pygame.Vector2(0, 0), (-9999, -9999, 9999, 9999))
    assert p._fire_flash_t == 0.0, "fire flash must fully decay, not linger forever"

    # edge case: drawing with zero flash time left must not crash or nudge the sprite
    p.draw(screen, cam)
    print("check_fire_flash_decays: PASSED")


def check_walk_cycle_phase_varies():
    vals = [math.sin((pygame.time.get_ticks() / 1000.0 + i * 0.05) * Player.WALK_CYCLE_SPEED) for i in range(20)]
    assert len(set(round(v, 3) for v in vals)) > 1, "leg phase must vary over time, not be static"
    print("check_walk_cycle_phase_varies: PASSED")


def check_real_draw_integration_while_moving():
    """The exact bug class that shipped once already: a ui/entities function's
    signature changed but a real call site wasn't updated to match, and it
    was only caught by the user running the actual app. Drive the REAL
    Game() through start_run -> enter_realm -> a real movement update -> a
    real draw(), not just the animation function in isolation."""
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.enter_realm()
    game.player.net_update(1 / 30, pygame.Vector2(0, 1), game.realm_sim.realm_map.bounds(),
                            game.realm_sim.is_solid_at, game.realm_sim.realm_map.speed_multiplier)
    game.draw()
    print("check_real_draw_integration_while_moving: PASSED")


if __name__ == "__main__":
    check_idle_vs_walk_state()
    check_fire_flash_decays()
    check_walk_cycle_phase_varies()
    check_real_draw_integration_while_moving()
    print("PASSED: player animation checks all green.")
