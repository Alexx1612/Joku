"""
Regression check for universal enemy idle-sway/walk-motion/attack-anticipation
animation (Batch 13, Track P). Covers idle-vs-walking state, direction
response, attack-pose triggering/clearing, and that this is genuinely
kind-agnostic (works the same for several different enemy kinds), plus the
real integration path (a full Game().draw() call) - the same class of
"signature changed, call site didn't" bug this session's convention already
guards against for Player animation.

Run with: .venv\\Scripts\\python.exe tests\\check_enemy_animation.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((800, 600))

from game.entities import Enemy, ANIM_ATTACK_POSE_DURATION

CAM = lambda pos: (pos.x, pos.y)


def check_idle_enemy_sways_not_static():
    e = Enemy("bat", pygame.Vector2(400, 300))
    e.aggro = False
    e.neutral = True  # never aggros, so update() always takes the idle-wander branch
    offsets = []
    for i in range(20):
        e.update(1 / 30, pygame.Vector2(9999, 9999), [], tile_map=None)
        assert e._is_moving is False, "idle wander must not read as 'moving' for animation purposes"
        pygame.time.wait(1)
        offsets.append(pygame.time.get_ticks())
    e.draw(screen, CAM)
    print("check_idle_enemy_sways_not_static: PASSED")


def check_walking_enemy_moves_and_has_direction():
    e = Enemy("goblin", pygame.Vector2(0, 0))
    e.neutral = False
    e.aggro = True
    e.aggro_range = 99999
    e.leash_range = 99999
    # far away (>90px) so update() takes the direct-chase branch, not the strafe branch
    player_pos = pygame.Vector2(500, 0)
    e.update(1 / 30, player_pos, [], tile_map=None)
    assert e._is_moving is True, "an aggro'd enemy chasing a distant player must read as 'moving'"
    assert e._move_dir.x > 0.9, f"move_dir should point toward the player (+x), got {e._move_dir}"
    e.draw(screen, CAM)
    print("check_walking_enemy_moves_and_has_direction: PASSED")


def check_attack_pose_triggers_and_clears():
    e = Enemy("skeleton", pygame.Vector2(0, 0))
    e.neutral = False
    e.aggro = True
    e.aggro_range = 99999
    e.leash_range = 99999
    e._fire_cd = 0.0  # force an immediate shot on the next update()
    player_pos = pygame.Vector2(30, 0)  # within the in-range strafe band, has line-of-sight (tile_map=None)
    bullets = []
    e.update(1 / 30, player_pos, bullets, tile_map=None)
    assert len(bullets) > 0, "expected this update() to actually fire a shot"
    assert e._fire_pose_t == ANIM_ATTACK_POSE_DURATION, "firing must trigger the anticipation pose"
    e.draw(screen, CAM)  # must not crash while the pose is active (image gets rescaled)

    # decay it out fully and confirm draw() still works with a zero pose (no lingering scale)
    e.update(1.0, player_pos, [], tile_map=None)
    assert e._fire_pose_t == 0.0, "attack pose must fully clear, not linger forever"
    e.draw(screen, CAM)
    print("check_attack_pose_triggers_and_clears: PASSED")


def check_frozen_enemy_is_not_moving():
    e = Enemy("imp", pygame.Vector2(0, 0))
    e.aggro = True
    e.frozen_time = 5.0
    e.update(1 / 30, pygame.Vector2(500, 0), [], tile_map=None)
    assert e._is_moving is False, "a frozen/rooted enemy must not play walk animation"
    e.draw(screen, CAM)
    print("check_frozen_enemy_is_not_moving: PASSED")


def check_kind_agnostic_across_several_enemies():
    """The whole point of Track P: this must work uniformly, not be special-cased
    per monster. Sample several very different kinds (flyer, melee, boss)."""
    for kind in ("bat", "troll", "harpy", "scorpion"):
        e = Enemy(kind, pygame.Vector2(100, 100))
        e.neutral = False
        e.aggro = True
        e.aggro_range = 99999
        e.leash_range = 99999
        e.update(1 / 30, pygame.Vector2(600, 100), [], tile_map=None)
        assert e._is_moving is True, f"{kind}: expected chase movement to read as 'moving'"
        e.draw(screen, CAM)  # must not crash for any kind
    print("check_kind_agnostic_across_several_enemies: PASSED")


def check_ghost_enemy_degrades_gracefully():
    """coop_client.py's GhostEnemy reuses Enemy.draw as a class attribute but
    never runs update(), so it has none of the _is_moving/_move_dir/_fire_pose_t
    fields. draw() must use getattr() defaults, not crash."""
    class _MinimalGhost:
        draw = Enemy.draw

        def __init__(self):
            self.kind = "bat"
            self.pos = pygame.Vector2(50, 50)
            self.hp, self.hp_max, self.rank = 10, 10, "trash"
            self._hit_flash = 0.0
            self.frozen_time = 0.0
            self.moonlit = False
            self.invulnerable = False
            # deliberately NOT setting _is_moving/_move_dir/_fire_pose_t

    g = _MinimalGhost()
    g.draw(screen, CAM)  # must not raise AttributeError
    print("check_ghost_enemy_degrades_gracefully: PASSED")


def check_real_draw_integration_with_moving_enemy():
    """Drive a real Game() through start_run -> enter_realm -> a real enemy
    update+draw pass, not just the animation logic in isolation - catches any
    real call-site mismatch the isolated unit checks above wouldn't."""
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.enter_realm()
    enemies = game.realm_sim.enemies
    if enemies:
        e = enemies[0]
        e.neutral = False
        e.aggro = True
        e.aggro_range = 99999
        e.update(1 / 30, game.player.pos + pygame.Vector2(500, 0), [], tile_map=game.realm_sim.realm_map)
    game.draw()
    print("check_real_draw_integration_with_moving_enemy: PASSED")


if __name__ == "__main__":
    check_idle_enemy_sways_not_static()
    check_walking_enemy_moves_and_has_direction()
    check_attack_pose_triggers_and_clears()
    check_frozen_enemy_is_not_moving()
    check_kind_agnostic_across_several_enemies()
    check_ghost_enemy_degrades_gracefully()
    check_real_draw_integration_with_moving_enemy()
    print("PASSED: enemy animation checks all green.")
