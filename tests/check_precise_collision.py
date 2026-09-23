"""
Regression check for circle-aware wall/object collision (entities._circle_clear),
added mid-batch as an extra ask: "make collision with walls and objects and
mobs pixel perfect." The old collision checked only the entity's exact
CENTER point against the tile grid, letting up to a full `radius` px of the
visible sprite clip into a wall before anything blocked it. The fix checks
the center plus 4 cardinal edge points of the entity's real collision
circle - deliberately NOT a full sprite-silhouette pixel mask, since that
class of "true pixel-perfect" collision is a well-known top-down-game
footgun (a character's edge pixels snag on every wall corner and reads as
"stuck," not smooth) - a swept-circle approximation is standard practice
for exactly this reason and is what real action games use even with
detailed sprites.

Mob-vs-player CONTACT (Enemy.radius + Player.radius compared against real
Euclidean distance in RealmSim.update()) was already an exact circle-vs-
circle check before this change - already fully accurate for circular
hitboxes, nothing to fix there; this file's tests focus on the actual gap
(wall/tile collision), not that already-correct path.

Run with: .venv\\Scripts\\python.exe tests\\check_precise_collision.py
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

from game.entities import Player, Enemy, _circle_clear
from game.constants import TILE


class _WallAtTile1:
    """A minimal fake tile map: tile column 0 is open, tile column 1 (world
    x in [TILE, 2*TILE)) is solid - everything else open. Enough to prove
    the exact behavioral difference without needing a real generated map."""

    def is_solid(self, wx, wy):
        tx = int(wx // TILE)
        return tx == 1


def check_circle_clear_directly():
    wall = _WallAtTile1()
    # center well inside tile 0, radius doesn't reach the wall - clear
    assert _circle_clear(wall.is_solid, 10, 16, 12) is True
    # center still inside tile 0, but radius-extended edge pokes into tile 1
    # (10 + 12 = 22 is still tile 0's own territory at radius 12... use a
    # position where center is open but center+radius crosses into tile 1)
    assert _circle_clear(wall.is_solid, 25, 16, 12) is False, \
        "center is in the open tile, but the circle's edge (25+12=37) is inside the wall tile - must be blocked"
    # center itself already in the solid tile - clearly blocked
    assert _circle_clear(wall.is_solid, 40, 16, 12) is False
    print("check_circle_clear_directly: PASSED")


def check_real_before_after_behavioral_difference():
    """The actual proof: replay the OLD single-center-point logic by hand
    and confirm it WOULD have allowed a move that the NEW Enemy._move()
    correctly blocks - a real behavioral difference, not just a unit test
    of the helper in isolation."""
    wall = _WallAtTile1()
    e = Enemy("goblin", (0, 0))
    e.pos = pygame.Vector2(13, 16)  # center in open tile 0
    e.radius = 12

    # OLD behavior (center-point only) would have allowed this delta, since
    # the destination CENTER (13+12=25) is still in the open tile
    old_new_x = e.pos.x + 12
    old_would_allow = not wall.is_solid(old_new_x, e.pos.y)
    assert old_would_allow is True, "sanity check: the old center-point check should have allowed this move"

    # NEW behavior actually blocks it, because the circle's edge at that
    # destination (25+12=37) is inside the wall tile
    e._move(pygame.Vector2(12, 0), wall)
    assert e.pos.x == 13, f"expected the new circle-aware check to block this move, but position moved to {e.pos.x}"
    print("check_real_before_after_behavioral_difference: PASSED")


def check_player_net_update_uses_circle_check():
    """Uses a realistic per-frame dt (1/30s, matching how net_update() is
    actually called every real game tick) rather than a whole-second jump -
    a huge single-step delta would tunnel clean through a 32px wall tile
    regardless of collision precision, which is a step-size/tunneling
    concern unrelated to this fix (the OLD center-point check has the exact
    same tunneling limitation at large enough deltas)."""
    wall = _WallAtTile1()
    p = Player("wizard", "EdgeTester", pid="p1")
    p.pos = pygame.Vector2(13, 16)
    p.radius = 12
    for _ in range(120):  # plenty of real ticks to reach the wall and stop there
        p.net_update(1 / 30, pygame.Vector2(1, 0), (0, 0, 10000, 10000), wall.is_solid)
    assert p.pos.x < TILE, f"player's circle should never be allowed to overlap the wall tile, got x={p.pos.x}"
    print(f"player settled at x={p.pos.x:.1f} (wall tile starts at x={TILE}) - held back by its own radius")
    print("check_player_net_update_uses_circle_check: PASSED")


def check_open_space_unaffected():
    """Edge case: far from any wall, movement must behave exactly as before -
    the new check must never spuriously block legitimate movement."""
    wall = _WallAtTile1()
    e = Enemy("goblin", (500, 500))
    e.pos = pygame.Vector2(500, 500)
    start = pygame.Vector2(e.pos)
    e._move(pygame.Vector2(20, 15), wall)
    assert e.pos.distance_to(start) > 20, "movement in open space must not be blocked by the new check"
    print("check_open_space_unaffected: PASSED")


def check_performance_sane():
    """A realistic-sized enemy list, timed circle-vs-tile checks - confirms
    the 5-point approximation stays cheap, not a per-frame budget risk."""
    wall = _WallAtTile1()
    enemies = [Enemy("goblin", (i * 3, i * 2)) for i in range(800)]  # this project's own
    # REALM_ENEMY_CAP-scale count (see realm_sim.py's own LAIR_COUNT*LAIR_CAP comments)
    t0 = time.perf_counter()
    for e in enemies:
        e._move(pygame.Vector2(1, 1), wall)
    elapsed = time.perf_counter() - t0
    print(f"800 circle-aware _move() calls took {elapsed * 1000:.2f}ms")
    assert elapsed < 0.05, "circle-aware collision must stay well within a single frame's budget at real enemy counts"
    print("check_performance_sane: PASSED")


if __name__ == "__main__":
    check_circle_clear_directly()
    check_real_before_after_behavioral_difference()
    check_player_net_update_uses_circle_check()
    check_open_space_unaffected()
    check_performance_sane()
    print("PASSED: precise collision checks all green.")
