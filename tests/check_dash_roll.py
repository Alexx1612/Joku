"""
Regression check for the universal dash/roll ability (Player.try_dash(),
Player.net_update()'s dash-movement branch, Player.take_damage()'s
i-frame short-circuit) - Batch 12's "give dodging bullet patterns a
skill-expression layer" ask.

Deliberately NOT a per-class ability (unlike the existing Space-bar
class abilities in game/items.py's ABILITIES table) - one shared kit,
bound to Left/Right Shift, gated by a cooldown so it reads as "a few
real dodges per fight," not a spammable panic button, with i-frames
that last exactly as long as the burst itself (no bonus invincibility
once you're back in manual control).

Run with: .venv\\Scripts\\python.exe tests\\check_dash_roll.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((100, 100))

from game.entities import Player
from game.constants import TILE


class _OpenWorld:
    """No walls anywhere - isolates dash movement/i-frame behavior from
    collision, which check_dash_wall_collision below tests separately."""

    def is_solid(self, wx, wy):
        return False


class _WallAtTile3:
    """Tile column 3 (world x in [3*TILE, 4*TILE)) is solid, everything
    else open - same minimal-fake-map convention as check_precise_collision.py."""

    def is_solid(self, wx, wy):
        return int(wx // TILE) == 3


def check_dash_moves_further_than_normal_walk():
    """A dash over its own duration must cover noticeably more ground than
    normal WASD movement would in the same timeframe - otherwise it isn't
    a real burst, just cosmetic."""
    world = _OpenWorld()
    bounds = (0, 0, 100000, 100000)

    walker = Player("wizard", "Walker", pid="p1")
    walker.pos = pygame.Vector2(0, 0)
    walker.facing = pygame.Vector2(1, 0)
    dasher = Player("wizard", "Dasher", pid="p2")
    dasher.pos = pygame.Vector2(0, 0)
    dasher.facing = pygame.Vector2(1, 0)

    started = dasher.try_dash()
    assert started is True, "a fresh Player must be able to dash immediately (no cooldown yet)"

    dt = 1 / 60
    elapsed = 0.0
    while elapsed < Player.DASH_DURATION:
        walker.net_update(dt, pygame.Vector2(1, 0), bounds, world.is_solid)
        dasher.net_update(dt, pygame.Vector2(0, 0), bounds, world.is_solid)
        elapsed += dt

    walk_dist = walker.pos.distance_to((0, 0))
    dash_dist = dasher.pos.distance_to((0, 0))
    print(f"normal walk covered {walk_dist:.1f}px, dash covered {dash_dist:.1f}px "
          f"over {Player.DASH_DURATION:.2f}s")
    assert dash_dist > walk_dist * 1.3, (
        f"dash ({dash_dist:.1f}px) should clearly outrun a normal full-speed walk "
        f"({walk_dist:.1f}px) over the same window - it's meant to read as a real burst")
    assert dasher._dash_time <= 0.0, "dash should have fully expired by the end of its own duration"
    print("check_dash_moves_further_than_normal_walk: PASSED")


def check_iframes_block_damage_then_expire():
    world = _OpenWorld()
    bounds = (0, 0, 100000, 100000)
    p = Player("wizard", "IframeTester", pid="p1")
    p.pos = pygame.Vector2(0, 0)
    p.facing = pygame.Vector2(1, 0)

    p.try_dash()
    assert p._dash_iframes > 0.0, "try_dash() must grant i-frames immediately"
    real = p.take_damage(9999)
    assert real == 0, f"damage taken during active i-frames must be fully negated, got {real}"
    assert p.hp == p.hp_max, "HP must be untouched while i-framed"

    # advance past the i-frame window (and the dash itself) with real per-tick dt
    dt = 1 / 60
    elapsed = 0.0
    while elapsed < Player.DASH_IFRAMES + 0.05:
        p.net_update(dt, pygame.Vector2(0, 0), bounds, world.is_solid)
        elapsed += dt
    assert p._dash_iframes <= 0.0, "i-frames must actually expire, not last forever"

    real2 = p.take_damage(30)
    assert real2 > 0, "damage taken after i-frames expire must apply normally again"
    assert p.hp < p.hp_max, "HP must actually drop once i-frames are gone"
    print("check_iframes_block_damage_then_expire: PASSED")


def check_dash_respects_wall_collision():
    """A dash aimed straight into a wall must stop at the wall, exactly
    like normal movement - _circle_clear is reused, not bypassed."""
    wall = _WallAtTile3()
    bounds = (0, 0, 100000, 100000)
    p = Player("wizard", "WallTester", pid="p1")
    p.pos = pygame.Vector2(3 * TILE - p.radius - 2, 16)  # just short of the wall tile
    p.facing = pygame.Vector2(1, 0)
    p.try_dash()

    dt = 1 / 60
    elapsed = 0.0
    while elapsed < Player.DASH_DURATION + 0.05:
        p.net_update(dt, pygame.Vector2(0, 0), bounds, wall.is_solid)
        elapsed += dt

    assert p.pos.x < 3 * TILE, (
        f"dash must never clip through a solid tile, got x={p.pos.x:.1f} (wall starts at {3 * TILE})")
    print(f"dash stopped at x={p.pos.x:.1f} (wall tile starts at x={3 * TILE})")
    print("check_dash_respects_wall_collision: PASSED")


def check_dash_cooldown_blocks_immediate_reuse():
    world = _OpenWorld()
    bounds = (0, 0, 100000, 100000)
    p = Player("wizard", "CooldownTester", pid="p1")
    p.pos = pygame.Vector2(0, 0)
    p.facing = pygame.Vector2(1, 0)

    assert p.try_dash() is True
    assert p.try_dash() is False, "a second dash attempt immediately after the first must be blocked by cooldown"

    # let the dash itself finish, but stay well inside the longer cooldown window
    dt = 1 / 60
    elapsed = 0.0
    while elapsed < Player.DASH_DURATION + 0.05:
        p.net_update(dt, pygame.Vector2(0, 0), bounds, world.is_solid)
        elapsed += dt
    assert p._dash_time <= 0.0, "dash duration itself should be over by now"
    assert p._dash_cd > 0.0, "cooldown should still be running well past the dash's own short duration"
    assert p.try_dash() is False, "still on cooldown - must still refuse a new dash"

    # advance the rest of the way through the cooldown
    elapsed = 0.0
    while elapsed < Player.DASH_COOLDOWN:
        p.net_update(dt, pygame.Vector2(0, 0), bounds, world.is_solid)
        elapsed += dt
    assert p.try_dash() is True, "once the cooldown fully expires, a new dash must be allowed again"
    print("check_dash_cooldown_blocks_immediate_reuse: PASSED")


if __name__ == "__main__":
    check_dash_moves_further_than_normal_walk()
    check_iframes_block_damage_then_expire()
    check_dash_respects_wall_collision()
    check_dash_cooldown_blocks_immediate_reuse()
    print("PASSED: dash/roll checks all green.")
