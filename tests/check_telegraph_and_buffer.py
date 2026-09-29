"""
Regression check for two Batch-12 combat-feel additions:

1. Mob attack telegraph: `Enemy._pretelegraph` is on for the whole WIND-UP of
   a move (game/enemy_attacks.py - every move is telegraphed before it fires,
   dashes with a red lane), off once it fires, and round-trips through
   `net_state()` into `coop_client.GhostEnemy` together with its colour
   (`wk`: aim/aoe/homing).
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

from game.entities import Enemy
from coop_client import GhostEnemy


def _mk_ranged_enemy(ready=True, aggro=True, kind="imp"):
    """imp: rank=trash, moves = Ember Flick (aimed/predictive) + Cinder Triplet.
    Since the combat-feel rework every attack starts with a WIND-UP (the
    telegraph) instead of a hidden _fire_cd window - `ready` makes its next
    move available immediately."""
    e = Enemy(kind, pygame.Vector2(100, 100))
    e.aggro = aggro
    if ready:
        e._atk_gap = 0.0
        for k in e._atk_cds:
            e._atk_cds[k] = 0.0
    else:
        e._atk_gap = 5.0
    return e


def check_pretelegraph_on_within_window():
    e = _mk_ranged_enemy()
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._windup is not None and e._pretelegraph is True, "a starting move must glow (wind-up)"
    assert e._windup_kind in ("aim", "aoe", "homing")
    e.draw(screen, lambda pos: (pos.x, pos.y))  # real draw, must not crash
    print("check_pretelegraph_on_within_window: PASSED")


def check_pretelegraph_off_outside_window():
    e = _mk_ranged_enemy(ready=False)
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._pretelegraph is False, "must not glow while no move is winding up"
    e.draw(screen, lambda pos: (pos.x, pos.y))
    print("check_pretelegraph_off_outside_window: PASSED")


def check_pretelegraph_off_when_not_aggro():
    e = _mk_ranged_enemy(aggro=False)
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._pretelegraph is False, "an idle (non-aggro) mob never telegraphs a shot"
    print("check_pretelegraph_off_when_not_aggro: PASSED")


def check_pretelegraph_off_for_melee_pattern():
    # renamed intent: melee DASHES are telegraphed too now - a red lane shows where it will lunge
    e = _mk_ranged_enemy(kind="panther")
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._pretelegraph is True and e._windup["move"]["tele"] == "dash"
    assert any(z["shape"] == "line" for z in e._new_zones), "a dash wind-up must push its lane telegraph"
    print("check_pretelegraph_off_for_melee_pattern (dash lane telegraph): PASSED")


def check_pretelegraph_off_right_after_firing():
    # the tick the wind-up completes and the shot is released - no longer "about to"
    e = _mk_ranged_enemy()
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    total = e._windup["total"]
    bullets = []
    e.update(total + 0.01, pygame.Vector2(400, 100), bullets, tile_map=None)
    assert bullets, "the move must fire when its wind-up ends"
    assert e._pretelegraph is False
    print("check_pretelegraph_off_right_after_firing: PASSED")


def check_pretelegraph_survives_net_roundtrip():
    e = _mk_ranged_enemy()
    e.update(0.001, pygame.Vector2(400, 100), [], tile_map=None)
    assert e._pretelegraph is True
    state = e.net_state()
    assert state["pretelegraph"] is True and state["wk"] == e._windup_kind

    ghost_on = GhostEnemy(state)
    assert ghost_on._pretelegraph is True and ghost_on._windup_kind == e._windup_kind
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
