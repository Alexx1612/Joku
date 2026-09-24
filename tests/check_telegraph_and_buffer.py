"""
Regression check for two Batch-12 combat-feel additions:

1. Ranged-mob attack telegraph: a purely-visual `Enemy._pretelegraph` flag
   that turns on in the ~0.2s window right before an aggro'd ranged mob's
   `_fire_cd` reaches 0 and it actually shoots - never gates/changes fire
   timing itself, and must round-trip correctly through `net_state()` into
   `coop_client.GhostEnemy` (server calls `e.net_state()` directly and
   relays it verbatim - see server.py's `_snapshot_for`).
2. Buffered fire input: an early "fire" request (mouse click in
   single-player, or a `fire` input flag in co-op) that lands while the
   weapon is still on cooldown now fires automatically once the cooldown
   clears, as long as that happens within FIRE_BUFFER_WINDOW - instead of
   being silently dropped, but only within that window, not indefinitely.

Run with: .venv\\Scripts\\python.exe tests\\check_telegraph_and_buffer.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
screen = pygame.display.set_mode((800, 600))

from game.entities import Enemy, PRETELEGRAPH_WINDOW
from coop_client import GhostEnemy


def _mk_ranged_enemy(fire_cd, aggro=True, pattern_override=None):
    e = Enemy("imp", pygame.Vector2(100, 100))  # imp: rank=trash, pattern="aimed" (ranged)
    e.aggro = aggro
    e._fire_cd = fire_cd
    if pattern_override is not None:
        e.pattern = pattern_override
    return e


def check_pretelegraph_on_within_window():
    e = _mk_ranged_enemy(fire_cd=0.15)
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert 0 < e._fire_cd <= PRETELEGRAPH_WINDOW
    assert e._pretelegraph is True, "must glow inside the pre-fire window"
    e.draw(screen, lambda pos: (pos.x, pos.y))  # real draw, must not crash
    print("check_pretelegraph_on_within_window: PASSED")


def check_pretelegraph_off_outside_window():
    e = _mk_ranged_enemy(fire_cd=0.6)
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._fire_cd > PRETELEGRAPH_WINDOW
    assert e._pretelegraph is False, "must not glow far from firing"
    e.draw(screen, lambda pos: (pos.x, pos.y))
    print("check_pretelegraph_off_outside_window: PASSED")


def check_pretelegraph_off_when_not_aggro():
    e = _mk_ranged_enemy(fire_cd=0.15, aggro=False)
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._pretelegraph is False, "an idle (non-aggro) mob never telegraphs a shot"
    print("check_pretelegraph_off_when_not_aggro: PASSED")


def check_pretelegraph_off_for_melee_pattern():
    e = _mk_ranged_enemy(fire_cd=0.15, pattern_override="charge")
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._pretelegraph is False, "melee 'charge' pattern has no ranged shot to telegraph"
    print("check_pretelegraph_off_for_melee_pattern: PASSED")


def check_pretelegraph_off_right_after_firing():
    # the tick fire_cd actually crosses <= 0 and the shot is released - the enemy
    # should NOT still show the glow on that exact tick (it just fired, no longer "about to")
    e = _mk_ranged_enemy(fire_cd=0.02)
    e.update(0.05, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._fire_cd > 0, "firing must have reset the cooldown to a new positive interval"
    assert e._pretelegraph is False
    print("check_pretelegraph_off_right_after_firing: PASSED")


def check_pretelegraph_survives_net_roundtrip():
    e = _mk_ranged_enemy(fire_cd=0.15)
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._pretelegraph is True
    state = e.net_state()
    assert state["pretelegraph"] is True

    ghost_on = GhostEnemy(state)
    assert ghost_on._pretelegraph is True
    ghost_on.draw(screen, lambda pos: (pos.x, pos.y))  # shared Enemy.draw, must not crash on a Ghost

    # an older/plain snapshot dict missing the key entirely must default safely to False,
    # not KeyError - defensive against any other net_state producer that hasn't been updated
    ghost_missing = GhostEnemy({"kind": "imp", "x": 0, "y": 0, "hp": 10, "hp_max": 10, "rank": "trash"})
    assert ghost_missing._pretelegraph is False
    print("check_pretelegraph_survives_net_roundtrip: PASSED")


def check_buffered_fire_fires_once_cooldown_clears():
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.enter_realm()
    p, sim = game.player, game.realm_sim

    p._fire_cd = 0.05  # still on cooldown
    game.auto_fire_enabled = True  # deterministic stand-in for "mouse button held" under a dummy driver
    game._handle_firing(p, sim, 0.01)
    assert game._fire_buffer > 0, "an early fire request while on cooldown must arm the buffer"
    assert len(sim.bullets) == 0, "must not fire yet - still on cooldown"

    # click released, cooldown clears - the BUFFERED request should still fire this frame
    game.auto_fire_enabled = False
    p._fire_cd = 0.0
    before = len(sim.bullets)
    game._handle_firing(p, sim, 0.01)
    assert len(sim.bullets) > before, "buffered fire must trigger the instant cooldown clears"
    assert game._fire_buffer == 0.0, "buffer must be consumed, not left armed"
    print("check_buffered_fire_fires_once_cooldown_clears: PASSED")


def check_buffered_fire_expires_if_cooldown_never_clears_in_time():
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.enter_realm()
    p, sim = game.player, game.realm_sim

    p._fire_cd = 0.5  # still well on cooldown
    game.auto_fire_enabled = True
    game._handle_firing(p, sim, 0.01)
    assert game._fire_buffer > 0

    # click released, but cooldown STILL hasn't cleared, and enough time passes that
    # the buffer window itself expires - the click must NOT be remembered forever
    game.auto_fire_enabled = False
    game._handle_firing(p, sim, 1.0)
    assert game._fire_buffer == 0.0, "buffer must fully expire, not linger"

    p._fire_cd = 0.0  # now imagine cooldown finally clears, well after the buffer expired
    before = len(sim.bullets)
    game._handle_firing(p, sim, 0.01)
    assert len(sim.bullets) == before, "an expired buffer must not fire late"
    print("check_buffered_fire_expires_if_cooldown_never_clears_in_time: PASSED")


def check_buffered_fire_clears_while_typing_in_chat():
    import main as main_module
    game = main_module.Game()
    game.start_run("wizard")
    game.enter_realm()
    p, sim = game.player, game.realm_sim

    p._fire_cd = 0.05
    game.auto_fire_enabled = True
    game._handle_firing(p, sim, 0.01)
    assert game._fire_buffer > 0

    game.chat_open = True
    game._handle_firing(p, sim, 0.01)
    assert game._fire_buffer == 0.0, "opening chat must drop any armed fire buffer"
    print("check_buffered_fire_clears_while_typing_in_chat: PASSED")


if __name__ == "__main__":
    check_pretelegraph_on_within_window()
    check_pretelegraph_off_outside_window()
    check_pretelegraph_off_when_not_aggro()
    check_pretelegraph_off_for_melee_pattern()
    check_pretelegraph_off_right_after_firing()
    check_pretelegraph_survives_net_roundtrip()
    check_buffered_fire_fires_once_cooldown_clears()
    check_buffered_fire_expires_if_cooldown_never_clears_in_time()
    check_buffered_fire_clears_while_typing_in_chat()
    print("PASSED: telegraph + buffered-fire checks all green.")
